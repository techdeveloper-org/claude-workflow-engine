"""
Vector DB RAG MCP Server - Qdrant-based semantic storage for workflow data.

Provides vector storage and retrieval for tool calls, sessions, flow traces,
and per-node pipeline decisions.
Uses Qdrant local mode (no external server needed) with sentence-transformers
embeddings for semantic search.

Backend: Qdrant (local/in-memory), sentence-transformers (all-MiniLM-L6-v2)
Transport: stdio

Collections (4):
  tool_calls      - Tool execution records with semantic search
  sessions        - Session summaries and context
  flow_traces     - Flow execution traces with step-level data
  node_decisions  - Per-node LangGraph pipeline decisions for RAG recommendations

Tools (11):
  vector_index_tool_call, vector_index_session, vector_index_flow_trace,
  vector_search_similar, vector_search_sessions, vector_search_traces,
  vector_get_collection_stats, vector_delete_collection,
  vector_health_check, vector_bulk_index, vector_index_node_decision
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure src/mcp/ is in path for base package imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

from base.response import to_json
from base.decorators import mcp_tool_handler
from base.clients import QdrantManager, EmbeddingManager

mcp = FastMCP(
    "vector-db",
    instructions="Vector DB RAG for semantic search over workflow data (Qdrant local mode)"
)

# Collection definitions (kept local for clarity alongside the tools that use them)
COLLECTIONS = {
    "tool_calls": {
        "size": 384,  # all-MiniLM-L6-v2 output dimension
        "distance": "Cosine",
    },
    "sessions": {
        "size": 384,
        "distance": "Cosine",
    },
    "flow_traces": {
        "size": 384,
        "distance": "Cosine",
    },
    "node_decisions": {
        "size": 384,
        "distance": "Cosine",
    },
}


def _generate_point_id() -> int:
    """Generate unique point ID based on timestamp."""
    import hashlib
    ts = str(time.time_ns())
    return int(hashlib.md5(ts.encode()).hexdigest()[:15], 16)


# =============================================================================
# TOOL 1: INDEX TOOL CALL
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def vector_index_tool_call(
    tool_name: str,
    status: str,
    duration_ms: int = 0,
    project: str = "",
    complexity: int = 0,
    session_id: str = "",
    description: str = "",
) -> dict:
    """Index a tool call record into the vector database.

    Args:
        tool_name: Name of the tool (e.g., 'Edit', 'Bash', 'Read')
        status: Execution status ('success', 'error', 'blocked')
        duration_ms: Execution duration in milliseconds
        project: Project name or path
        complexity: Task complexity (1-10)
        session_id: Session identifier
        description: Text description of what the tool did
    """
    client = QdrantManager.instance().get_or_raise()

    embed_text = f"{tool_name} {status} {description} {project}"
    vector = EmbeddingManager.instance().embed(embed_text)

    from qdrant_client.models import PointStruct

    point = PointStruct(
        id=_generate_point_id(),
        vector=vector,
        payload={
            "tool_name": tool_name,
            "status": status,
            "duration_ms": duration_ms,
            "project": project,
            "complexity": complexity,
            "session_id": session_id,
            "description": description,
            "indexed_at": datetime.now().isoformat(),
        },
    )

    client.upsert(collection_name="tool_calls", points=[point])

    return {
        "collection": "tool_calls",
        "tool_name": tool_name,
        "point_id": point.id,
    }


# =============================================================================
# TOOL 2: INDEX SESSION
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def vector_index_session(
    session_id: str,
    project: str = "",
    summary: str = "",
    tool_count: int = 0,
    context_pct: float = 0.0,
    duration_min: float = 0.0,
    tags: str = "",
) -> dict:
    """Index a session summary into the vector database.

    Args:
        session_id: Session identifier
        project: Project name or path
        summary: Text summary of the session
        tool_count: Number of tool calls in session
        context_pct: Context usage percentage (0-100)
        duration_min: Session duration in minutes
        tags: Comma-separated tags
    """
    client = QdrantManager.instance().get_or_raise()

    embed_text = f"{summary} {project} {tags}"
    vector = EmbeddingManager.instance().embed(embed_text)

    from qdrant_client.models import PointStruct

    point = PointStruct(
        id=_generate_point_id(),
        vector=vector,
        payload={
            "session_id": session_id,
            "project": project,
            "summary": summary,
            "tool_count": tool_count,
            "context_pct": context_pct,
            "duration_min": duration_min,
            "tags": [t.strip() for t in tags.split(",") if t.strip()],
            "indexed_at": datetime.now().isoformat(),
        },
    )

    client.upsert(collection_name="sessions", points=[point])

    return {
        "collection": "sessions",
        "session_id": session_id,
        "point_id": point.id,
    }


# =============================================================================
# TOOL 3: INDEX FLOW TRACE
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def vector_index_flow_trace(
    session_id: str,
    level: str = "",
    step: str = "",
    status: str = "",
    context_pct: float = 0.0,
    description: str = "",
    recommendations: str = "",
) -> dict:
    """Index a flow trace step into the vector database.

    Args:
        session_id: Session identifier
        level: Pipeline level ('level_minus1', 'level1', 'level2', 'level3')
        step: Step name or number
        status: Step status ('OK', 'FAILED', 'SKIPPED')
        context_pct: Context usage at this step
        description: What happened at this step
        recommendations: Any recommendations from this step
    """
    client = QdrantManager.instance().get_or_raise()

    embed_text = f"{level} {step} {status} {description} {recommendations}"
    vector = EmbeddingManager.instance().embed(embed_text)

    from qdrant_client.models import PointStruct

    point = PointStruct(
        id=_generate_point_id(),
        vector=vector,
        payload={
            "session_id": session_id,
            "level": level,
            "step": step,
            "status": status,
            "context_pct": context_pct,
            "description": description,
            "recommendations": recommendations,
            "indexed_at": datetime.now().isoformat(),
        },
    )

    client.upsert(collection_name="flow_traces", points=[point])

    return {
        "collection": "flow_traces",
        "session_id": session_id,
        "step": step,
        "point_id": point.id,
    }


# =============================================================================
# TOOL 4: SEARCH SIMILAR (generic across collections)
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def vector_search_similar(
    query: str,
    collection: str = "tool_calls",
    limit: int = 5,
    min_score: float = 0.5,
    filter_field: str = "",
    filter_value: str = "",
) -> dict:
    """Search for semantically similar records in any collection.

    Args:
        query: Natural language search query
        collection: Collection to search ('tool_calls', 'sessions', 'flow_traces')
        limit: Maximum results to return (1-20)
        min_score: Minimum similarity score (0.0-1.0)
        filter_field: Optional payload field to filter on
        filter_value: Value for the filter field
    """
    client = QdrantManager.instance().get_or_raise()

    if collection not in COLLECTIONS:
        raise ValueError(f"Unknown collection: {collection}")

    vector = EmbeddingManager.instance().embed(query)
    limit = max(1, min(limit, 20))

    query_filter = None
    if filter_field and filter_value:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        query_filter = Filter(
            must=[FieldCondition(key=filter_field, match=MatchValue(value=filter_value))]
        )

    results = client.search(
        collection_name=collection,
        query_vector=vector,
        limit=limit,
        score_threshold=min_score,
        query_filter=query_filter,
    )

    matches = []
    for hit in results:
        matches.append({
            "id": hit.id,
            "score": round(hit.score, 4),
            "payload": hit.payload,
        })

    return {
        "collection": collection,
        "query": query,
        "matches": matches,
        "total_matches": len(matches),
    }


# =============================================================================
# TOOL 5: SEARCH SESSIONS
# =============================================================================

@mcp.tool()
def vector_search_sessions(
    query: str,
    limit: int = 5,
    project: str = "",
) -> str:
    """Search for similar past sessions by description.

    Args:
        query: Natural language query (e.g., 'sessions about MCP migration')
        limit: Maximum results
        project: Filter by project name
    """
    filter_field = "project" if project else ""
    return vector_search_similar(
        query=query,
        collection="sessions",
        limit=limit,
        filter_field=filter_field,
        filter_value=project,
    )


# =============================================================================
# TOOL 6: SEARCH TRACES
# =============================================================================

@mcp.tool()
def vector_search_traces(
    query: str,
    limit: int = 5,
    level: str = "",
    status: str = "",
) -> str:
    """Search for similar flow trace steps.

    Args:
        query: Natural language query (e.g., 'steps that failed with encoding')
        limit: Maximum results
        level: Filter by level ('level1', 'level2', 'level3')
        status: Filter by status ('OK', 'FAILED')
    """
    filter_field = ""
    filter_value = ""
    if level:
        filter_field = "level"
        filter_value = level
    elif status:
        filter_field = "status"
        filter_value = status

    return vector_search_similar(
        query=query,
        collection="flow_traces",
        limit=limit,
        filter_field=filter_field,
        filter_value=filter_value,
    )


# =============================================================================
# TOOL 7: COLLECTION STATS
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def vector_get_collection_stats(collection: str = "all") -> dict:
    """Get statistics for vector database collections.

    Args:
        collection: Collection name or 'all' for all collections
    """
    client = QdrantManager.instance().get_or_raise()

    collections_to_check = (
        list(COLLECTIONS.keys()) if collection == "all"
        else [collection]
    )

    stats = {}
    total_points = 0
    for col_name in collections_to_check:
        if col_name not in COLLECTIONS:
            continue
        try:
            info = client.get_collection(col_name)
            count = info.points_count or 0
            total_points += count
            stats[col_name] = {
                "points_count": count,
                "vectors_count": info.vectors_count or 0,
                "status": str(info.status),
                "vector_size": COLLECTIONS[col_name]["size"],
            }
        except Exception as e:
            stats[col_name] = {"error": str(e)}

    # DB size on disk
    db_path = QdrantManager.DB_PATH
    db_size_kb = 0
    if db_path.exists():
        db_size_kb = sum(
            f.stat().st_size for f in db_path.rglob("*") if f.is_file()
        ) / 1024

    return {
        "collections": stats,
        "total_points": total_points,
        "db_path": str(db_path),
        "db_size_kb": round(db_size_kb, 1),
    }


# =============================================================================
# TOOL 8: DELETE COLLECTION
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def vector_delete_collection(collection: str) -> dict:
    """Delete a vector collection and all its data.

    Args:
        collection: Collection name to delete
    """
    client = QdrantManager.instance().get_or_raise()

    if collection not in COLLECTIONS:
        raise ValueError(f"Unknown collection: {collection}")

    client.delete_collection(collection)

    # Recreate empty collection
    from qdrant_client.models import VectorParams, Distance
    config = COLLECTIONS[collection]
    dist = getattr(Distance, config["distance"].upper(), Distance.COSINE)
    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=config["size"], distance=dist),
    )

    return {
        "collection": collection,
        "action": "deleted_and_recreated",
    }


# =============================================================================
# TOOL 9: HEALTH CHECK
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def vector_health_check() -> dict:
    """Check vector database health and dependencies."""
    health = {
        "qdrant_available": False,
        "embeddings_available": False,
        "collections": {},
        "db_path": str(QdrantManager.DB_PATH),
    }

    # Check Qdrant
    client = QdrantManager.instance().get()
    if client is not None:
        health["qdrant_available"] = True
        for col_name in COLLECTIONS:
            try:
                info = client.get_collection(col_name)
                health["collections"][col_name] = {
                    "status": str(info.status),
                    "points": info.points_count or 0,
                }
            except Exception:
                health["collections"][col_name] = {"status": "ERROR"}

    # Check embeddings
    embedding_mgr = EmbeddingManager.instance()
    model = embedding_mgr.get()
    if model is not None:
        health["embeddings_available"] = True
        health["embedding_model"] = "all-MiniLM-L6-v2"
        health["embedding_dim"] = 384

    health["healthy"] = health["qdrant_available"] and health["embeddings_available"]

    return health


# =============================================================================
# TOOL 10: BULK INDEX
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def vector_bulk_index(
    collection: str,
    records_json: str,
) -> dict:
    """Bulk index multiple records into a collection.

    Args:
        collection: Target collection ('tool_calls', 'sessions', 'flow_traces')
        records_json: JSON array of record objects to index.
            Each record should have a 'text' field for embedding plus payload fields.
    """
    client = QdrantManager.instance().get_or_raise()

    if collection not in COLLECTIONS:
        raise ValueError(f"Unknown collection: {collection}")

    records = json.loads(records_json)
    if not isinstance(records, list):
        raise ValueError("records_json must be a JSON array")

    from qdrant_client.models import PointStruct

    points = []
    errors = []
    for i, record in enumerate(records):
        try:
            text = record.pop("text", "")
            if not text:
                text = json.dumps(record)
            vector = EmbeddingManager.instance().embed(text)
            record["indexed_at"] = datetime.now().isoformat()
            points.append(PointStruct(
                id=_generate_point_id(),
                vector=vector,
                payload=record,
            ))
        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    if points:
        # Batch upsert in chunks of 100
        for chunk_start in range(0, len(points), 100):
            chunk = points[chunk_start:chunk_start + 100]
            client.upsert(collection_name=collection, points=chunk)

    return {
        "collection": collection,
        "indexed": len(points),
        "errors": len(errors),
        "error_details": errors[:5] if errors else [],
    }


# =============================================================================
# TOOL 11: INDEX NODE DECISION
# =============================================================================

@mcp.tool()
@mcp_tool_handler
def vector_index_node_decision(
    session_id: str,
    project: str = "",
    step: str = "",
    decision: str = "",
    user_prompt: str = "",
    task_type: str = "",
    complexity: int = 0,
    framework: str = "",
) -> dict:
    """Index a pipeline node decision for RAG-based recommendation.

    Args:
        session_id: Session identifier
        project: Project name
        step: Pipeline step (e.g., 'step0', 'step1', 'step5')
        decision: JSON string of the node's decision/output
        user_prompt: Original user prompt (truncated)
        task_type: Task classification (bug, feature, etc.)
        complexity: Task complexity (1-10)
        framework: Detected framework (flask, spring-boot, etc.)
    """
    client = QdrantManager.instance().get_or_raise()

    embed_text = f"{step} {project} {task_type} {user_prompt[:500]} {decision[:500]}"
    vector = EmbeddingManager.instance().embed(embed_text)

    from qdrant_client.models import PointStruct

    point = PointStruct(
        id=_generate_point_id(),
        vector=vector,
        payload={
            "session_id": session_id,
            "project": project,
            "step": step,
            "decision": decision[:3000],
            "user_prompt": user_prompt[:1000],
            "task_type": task_type,
            "complexity": complexity,
            "framework": framework,
            "indexed_at": datetime.now().isoformat(),
        },
    )

    client.upsert(collection_name="node_decisions", points=[point])

    return {
        "collection": "node_decisions",
        "session_id": session_id,
        "step": step,
        "point_id": point.id,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
