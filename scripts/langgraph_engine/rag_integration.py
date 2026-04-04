"""
RAG Integration Layer for LangGraph Pipeline.

Stores every node's decision in Vector DB and provides RAG-first
lookup before LLM calls. If similar past decision exists with high
confidence, returns it directly - saving LLM inference time.

Collections used:
  node_decisions - Per-node decision history with full context
  sessions       - Session-level summaries (existing)
  flow_traces    - Step-level execution data (existing)

Usage:
  from langgraph_engine.rag_integration import RAGLayer
  rag = RAGLayer(session_id, project)

  # Store after node completes
  rag.store(step="step0", decision={...}, user_prompt="...", context={...})
"""

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

# Add src/mcp to path for vector DB imports
_SRC_MCP_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "mcp"
if str(_SRC_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_MCP_DIR))


def _compute_codebase_hash(project_root):
    # type: (str) -> str
    """Return a short structural fingerprint of the project codebase.

    Hashes the sorted list of top-level Python module file names (not
    their content) under project_root.  Cheap to compute (~1ms), stable
    across sessions, and different enough between distinct projects to
    prevent RAG cross-project false positives.

    Returns "" on any error so callers can treat empty as "unknown".
    """
    try:
        root = Path(project_root)
        if not root.is_dir():
            return ""
        py_names = sorted(
            p.name
            for p in root.rglob("*.py")
            if not any(part.startswith(".") for part in p.parts) and "__pycache__" not in str(p)
        )
        if not py_names:
            return ""
        digest = hashlib.sha1("|".join(py_names[:200]).encode("utf-8", errors="replace")).hexdigest()[:12]
        return digest
    except Exception:
        return ""


# Default confidence threshold - above this, RAG result replaces LLM call
RAG_CONFIDENCE_THRESHOLD = 0.82

# Step-specific thresholds (some steps need higher confidence)
STEP_THRESHOLDS = {
    "step0": 0.85,  # Task analysis - needs high match
    "step1": 0.80,  # Plan mode decision - binary, easier to match
    "step2": 0.88,  # Plan execution - complex, needs very close match
    "step5": 0.82,  # Skill selection - moderate
    "step7": 0.90,  # Final prompt - needs near-exact for reuse
    "step8": 0.78,  # Issue label - simple classification
    "step11": 0.85,  # PR review - needs high confidence
    "step13": 0.80,  # Docs update - moderate
    "step14": 0.75,  # Summary - low stakes
}

# Maximum number of RAG results to consider
RAG_MAX_RESULTS = 5


def _get_vector_functions():
    """Lazy import vector DB functions to avoid import-time failures."""
    try:
        from vector_db_mcp_server import (
            _embed_text,
            _generate_point_id,
            _get_qdrant_client,
            vector_bulk_index,
            vector_search_similar,
        )

        return {
            "search": vector_search_similar,
            "bulk_index": vector_bulk_index,
            "client": _get_qdrant_client,
            "embed": _embed_text,
            "point_id": _generate_point_id,
            "available": True,
        }
    except ImportError:
        return {"available": False}
    except Exception:
        return {"available": False}


def _ensure_node_decisions_collection():
    """Create node_decisions collection if it doesn't exist."""
    try:
        vf = _get_vector_functions()
        if not vf["available"]:
            return False

        client = vf["client"]()
        if client is None:
            return False

        existing = {c.name for c in client.get_collections().collections}
        if "node_decisions" not in existing:
            from qdrant_client.models import Distance, VectorParams

            client.create_collection(
                collection_name="node_decisions",
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
        return True
    except Exception:
        return False


class RAGLayer:
    """RAG integration layer for the LangGraph pipeline.

    Provides store() and lookup() for every pipeline node.
    Stores decisions with full context for future retrieval.
    """

    def __init__(self, session_id: str = "", project: str = "", project_root: str = ""):
        self.session_id = session_id
        self.project = project or (Path(project_root).name if project_root else "")
        self.project_root = project_root
        self._vf = None
        self._available = None
        self._stats = {
            "lookups": 0,
            "hits": 0,
            "misses": 0,
            "stores": 0,
            "errors": 0,
            "llm_calls_saved": 0,
        }

    @property
    def available(self):
        # type: () -> bool
        """Check if vector DB is available."""
        if self._available is None:
            self._vf = _get_vector_functions()
            self._available = self._vf.get("available", False)
            if self._available:
                _ensure_node_decisions_collection()
        return self._available

    def lookup(
        self,
        step,  # type: str
        query,  # type: str
        context=None,  # type: Optional[Dict]
        threshold=None,  # type: Optional[float]
    ):
        # type: (...) -> Optional[Dict]
        """Search for similar past decisions before making an LLM call.

        Args:
            step: Pipeline step name (e.g., "step0", "step1", "step5")
            query: The query/prompt that would be sent to LLM
            context: Additional context (task_type, complexity, etc.)
            threshold: Override confidence threshold for this lookup

        Returns:
            Dict with past decision if found with sufficient confidence,
            None if no good match (should proceed with LLM call).

            Format: {
                "decision": <the past decision dict>,
                "confidence": 0.87,
                "source_session": "session-...",
                "source_step": "step0",
                "rag_hit": True,
            }
        """
        if not self.available:
            return None

        self._stats["lookups"] += 1

        # Determine threshold
        min_score = threshold or STEP_THRESHOLDS.get(step, RAG_CONFIDENCE_THRESHOLD)

        try:
            # Build search text combining step context + query
            search_text = "{} {} {}".format(step, self.project, query)
            if context:
                task_type = context.get("task_type", "")
                complexity = context.get("complexity", "")
                framework = context.get("framework", "")
                if task_type:
                    search_text += " {}".format(task_type)
                if complexity:
                    search_text += " complexity:{}".format(complexity)
                if framework:
                    search_text += " {}".format(framework)

            # Search node_decisions collection with step filter
            result_json = self._vf["search"](
                query=search_text,
                collection="node_decisions",
                limit=RAG_MAX_RESULTS,
                min_score=min_score,
                filter_field="step",
                filter_value=step,
            )

            result = json.loads(result_json)

            if not result.get("success") or not result.get("matches"):
                self._stats["misses"] += 1
                return None

            # Get best match
            best = result["matches"][0]
            score = best.get("score", 0)
            payload = best.get("payload", {})

            if score < min_score:
                self._stats["misses"] += 1
                return None

            # Validate the match is for same project type/framework
            if context:
                stored_task_type = payload.get("task_type", "")
                query_task_type = context.get("task_type", "")
                if stored_task_type and query_task_type:
                    if stored_task_type != query_task_type:
                        # Different task type - lower confidence
                        score *= 0.8
                        if score < min_score:
                            self._stats["misses"] += 1
                            return None

                # Cross-project guard: penalise heavily when codebase fingerprints differ.
                # Prevents "Add login to dashboard" in Project A matching Project B's cached
                # plan even when the task text is identical (RAG score 0.95+).
                query_hash = context.get("codebase_hash", "")
                stored_hash = payload.get("codebase_hash", "")
                if query_hash and stored_hash and query_hash != stored_hash:
                    score *= 0.65
                    if score < min_score:
                        self._stats["misses"] += 1
                        return None

            self._stats["hits"] += 1
            self._stats["llm_calls_saved"] += 1

            # Parse stored decision
            decision_raw = payload.get("decision", "{}")
            try:
                decision = json.loads(decision_raw) if isinstance(decision_raw, str) else decision_raw
            except (ValueError, TypeError):
                decision = {"raw": decision_raw}

            return {
                "decision": decision,
                "confidence": round(score, 4),
                "source_session": payload.get("session_id", ""),
                "source_step": payload.get("step", step),
                "source_project": payload.get("project", ""),
                "rag_hit": True,
                "indexed_at": payload.get("indexed_at", ""),
            }

        except Exception:
            self._stats["errors"] += 1
            return None

    def store(
        self,
        step,  # type: str
        decision,  # type: Dict[str, Any]
        user_prompt="",  # type: str
        context=None,  # type: Optional[Dict]
    ):
        # type: (...) -> bool
        """Store a node's decision in the vector DB for future RAG lookups.

        Args:
            step: Pipeline step name (e.g., "step0", "step1")
            decision: The decision/output from this node
            user_prompt: Original user prompt for this session
            context: Additional context (task_type, complexity, etc.)

        Returns:
            True if stored successfully, False otherwise.
        """
        if not self.available:
            return False

        try:
            # Build embedding text from step + decision + context
            decision_text = json.dumps(decision, default=str)[:2000]
            context_text = ""
            task_type = ""
            complexity = 0
            framework = ""

            if context:
                task_type = context.get("task_type", "")
                complexity = context.get("complexity", 0)
                framework = context.get("framework", "")
                context_text = " {} complexity:{} {}".format(task_type, complexity, framework)

            embed_text = "{} {} {} {}{}".format(
                step,
                self.project,
                user_prompt[:500],
                decision_text[:500],
                context_text,
            )

            vector = self._vf["embed"](embed_text)

            from qdrant_client.models import PointStruct

            codebase_hash = _compute_codebase_hash(self.project_root) if self.project_root else ""

            point = PointStruct(
                id=self._vf["point_id"](),
                vector=vector,
                payload={
                    "session_id": self.session_id,
                    "project": self.project,
                    "step": step,
                    "decision": decision_text,
                    "user_prompt": user_prompt[:1000],
                    "task_type": task_type,
                    "complexity": complexity,
                    "framework": framework,
                    "codebase_hash": codebase_hash,
                    "indexed_at": datetime.now().isoformat(),
                },
            )

            client = self._vf["client"]()
            if client:
                client.upsert(collection_name="node_decisions", points=[point])
                self._stats["stores"] += 1
                return True

            return False

        except Exception:
            self._stats["errors"] += 1
            return False

    def store_session_summary(
        self,
        summary,  # type: str
        task_type="",  # type: str
        skill="",  # type: str
        agent="",  # type: str
        final_status="",  # type: str
        steps_completed=0,  # type: int
    ):
        # type: (...) -> bool
        """Store full session summary in sessions collection for cross-session learning.

        Called at pipeline end (level3_output) to capture the complete picture.
        """
        if not self.available:
            return False

        try:
            from vector_db_mcp_server import vector_index_session

            result_json = vector_index_session(
                session_id=self.session_id,
                project=self.project,
                summary="{} {} {} {} {}".format(task_type, skill, agent, final_status, summary)[:2000],
                tool_count=steps_completed,
                context_pct=0.0,
                duration_min=0.0,
                tags=",".join(filter(None, [task_type, skill, agent, final_status])),
            )
            result = json.loads(result_json)
            return result.get("success", False)
        except Exception:
            return False

    def store_flow_trace(
        self,
        level,  # type: str
        step,  # type: str
        status,  # type: str
        description,  # type: str
        recommendations="",  # type: str
    ):
        # type: (...) -> bool
        """Store a flow trace entry for step-level tracking."""
        if not self.available:
            return False

        try:
            from vector_db_mcp_server import vector_index_flow_trace

            result_json = vector_index_flow_trace(
                session_id=self.session_id,
                level=level,
                step=step,
                status=status,
                description=description,
                recommendations=recommendations,
            )
            result = json.loads(result_json)
            return result.get("success", False)
        except Exception:
            return False

    def get_stats(self):
        # type: () -> Dict[str, int]
        """Return RAG usage statistics for this session."""
        return dict(self._stats)

    def get_hit_rate(self):
        # type: () -> float
        """Return RAG cache hit rate as percentage."""
        total = self._stats["lookups"]
        if total == 0:
            return 0.0
        return round((self._stats["hits"] / total) * 100, 1)


# Module-level singleton for easy access across nodes
_rag_instance = None  # type: Optional[RAGLayer]


def get_rag_layer(
    session_id="",  # type: str
    project="",  # type: str
    project_root="",  # type: str
):
    # type: (...) -> RAGLayer
    """Get or create the RAG layer singleton for this pipeline run."""
    global _rag_instance
    if _rag_instance is None or (session_id and _rag_instance.session_id != session_id):
        _rag_instance = RAGLayer(session_id, project, project_root)
    return _rag_instance
