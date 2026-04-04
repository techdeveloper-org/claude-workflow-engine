"""
Tests for RAG Integration Layer (rag_integration.py).

Tests the RAGLayer class which provides vector DB based
caching and recommendation for LangGraph pipeline nodes.

CHANGE LOG (v1.15.0):
  Removed TestRAGLookupInRunStep -- per-node RAG cache removed from _run_step.
  Removed _RAG_ELIGIBLE_STEPS test -- constant no longer exists.
  Updated test_thresholds_defined_for_llm_steps -- steps 1, 2, 5, 7 removed.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts to path for imports
_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


class TestRAGLayerInit:
    """Test RAGLayer initialization and availability checks."""

    def test_rag_layer_creation(self):
        from langgraph_engine.rag_integration import RAGLayer

        rag = RAGLayer(session_id="test-session", project="test-project")
        assert rag.session_id == "test-session"
        assert rag.project == "test-project"

    def test_rag_layer_from_project_root(self):
        from langgraph_engine.rag_integration import RAGLayer

        rag = RAGLayer(project_root="/home/user/projects/my-app")
        assert rag.project == "my-app"

    def test_rag_stats_initial(self):
        from langgraph_engine.rag_integration import RAGLayer

        rag = RAGLayer()
        stats = rag.get_stats()
        assert stats["lookups"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["stores"] == 0

    def test_hit_rate_zero_lookups(self):
        from langgraph_engine.rag_integration import RAGLayer

        rag = RAGLayer()
        assert rag.get_hit_rate() == 0.0


class TestRAGLookup:
    """Test RAG lookup functionality."""

    @patch("langgraph_engine.rag_integration._get_vector_functions")
    def test_lookup_returns_none_when_unavailable(self, mock_vf):
        from langgraph_engine.rag_integration import RAGLayer

        mock_vf.return_value = {"available": False}
        rag = RAGLayer(session_id="s1")
        rag._available = False
        result = rag.lookup(step="step0", query="fix auth bug")
        assert result is None

    @patch("langgraph_engine.rag_integration._get_vector_functions")
    def test_lookup_returns_none_on_no_matches(self, mock_vf):
        from langgraph_engine.rag_integration import RAGLayer

        mock_search = MagicMock(
            return_value=json.dumps(
                {
                    "success": True,
                    "matches": [],
                    "total_matches": 0,
                }
            )
        )
        mock_vf.return_value = {
            "available": True,
            "search": mock_search,
            "client": MagicMock(return_value=MagicMock()),
            "embed": MagicMock(),
            "point_id": MagicMock(),
        }

        rag = RAGLayer(session_id="s1", project="test")
        rag._vf = mock_vf.return_value
        rag._available = True
        result = rag.lookup(step="step0", query="fix auth bug")
        assert result is None
        assert rag._stats["misses"] == 1

    @patch("langgraph_engine.rag_integration._get_vector_functions")
    def test_lookup_returns_hit_on_high_confidence(self, mock_vf):
        from langgraph_engine.rag_integration import RAGLayer

        mock_search = MagicMock(
            return_value=json.dumps(
                {
                    "success": True,
                    "matches": [
                        {
                            "id": 123,
                            "score": 0.92,
                            "payload": {
                                "step": "step0",
                                "decision": '{"task_type": "Bug Fix", "complexity": 3}',
                                "session_id": "old-session",
                                "project": "test",
                                "task_type": "Bug Fix",
                                "indexed_at": "2026-03-16T10:00:00",
                            },
                        }
                    ],
                    "total_matches": 1,
                }
            )
        )
        mock_vf.return_value = {
            "available": True,
            "search": mock_search,
            "client": MagicMock(return_value=MagicMock()),
            "embed": MagicMock(),
            "point_id": MagicMock(),
        }

        rag = RAGLayer(session_id="s1", project="test")
        rag._vf = mock_vf.return_value
        rag._available = True
        result = rag.lookup(step="step0", query="fix auth bug")
        assert result is not None
        assert result["rag_hit"] is True
        assert result["confidence"] >= 0.85
        assert result["decision"]["task_type"] == "Bug Fix"
        assert rag._stats["hits"] == 1
        assert rag._stats["llm_calls_saved"] == 1

    @patch("langgraph_engine.rag_integration._get_vector_functions")
    def test_lookup_rejects_different_task_type(self, mock_vf):
        from langgraph_engine.rag_integration import RAGLayer

        mock_search = MagicMock(
            return_value=json.dumps(
                {
                    "success": True,
                    "matches": [
                        {
                            "id": 123,
                            "score": 0.86,
                            "payload": {
                                "step": "step0",
                                "decision": '{"task_type": "Feature"}',
                                "session_id": "old-session",
                                "project": "test",
                                "task_type": "Feature",
                            },
                        }
                    ],
                }
            )
        )
        mock_vf.return_value = {
            "available": True,
            "search": mock_search,
            "client": MagicMock(return_value=MagicMock()),
            "embed": MagicMock(),
            "point_id": MagicMock(),
        }

        rag = RAGLayer(session_id="s1", project="test")
        rag._vf = mock_vf.return_value
        rag._available = True
        # Pass different task type in context - should lower confidence below threshold
        result = rag.lookup(
            step="step0",
            query="fix auth bug",
            context={"task_type": "Bug Fix"},
        )
        # Score 0.86 * 0.8 = 0.688, below step0 threshold of 0.85
        assert result is None


class TestRAGStore:
    """Test RAG store functionality."""

    @patch("langgraph_engine.rag_integration._get_vector_functions")
    def test_store_returns_false_when_unavailable(self, mock_vf):
        from langgraph_engine.rag_integration import RAGLayer

        mock_vf.return_value = {"available": False}
        rag = RAGLayer()
        rag._available = False
        result = rag.store(step="step0", decision={"task_type": "Bug Fix"})
        assert result is False

    @patch("langgraph_engine.rag_integration._get_vector_functions")
    def test_store_success(self, mock_vf):
        from langgraph_engine.rag_integration import RAGLayer

        mock_client = MagicMock()
        mock_vf.return_value = {
            "available": True,
            "search": MagicMock(),
            "client": MagicMock(return_value=mock_client),
            "embed": MagicMock(return_value=[0.1] * 384),
            "point_id": MagicMock(return_value=12345),
        }

        rag = RAGLayer(session_id="s1", project="test")
        rag._vf = mock_vf.return_value
        rag._available = True

        # Mock qdrant_client.models for PointStruct import inside store()
        with patch.dict(
            "sys.modules",
            {
                "qdrant_client": MagicMock(),
                "qdrant_client.models": MagicMock(),
            },
        ):
            result = rag.store(
                step="step0",
                decision={"task_type": "Bug Fix", "complexity": 3},
                user_prompt="Fix the authentication bug",
                context={"task_type": "Bug Fix", "complexity": 3},
            )
        assert result is True
        assert rag._stats["stores"] == 1
        mock_client.upsert.assert_called_once()


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_get_rag_layer_singleton(self):
        from langgraph_engine.rag_integration import get_rag_layer

        rag1 = get_rag_layer(session_id="s1", project="p1")
        rag2 = get_rag_layer(session_id="s1", project="p1")
        assert rag1 is rag2  # Same session = same instance

    def test_get_rag_layer_new_session(self):
        from langgraph_engine.rag_integration import get_rag_layer

        rag1 = get_rag_layer(session_id="s1")
        rag2 = get_rag_layer(session_id="s2")
        assert rag1 is not rag2  # Different session = new instance


class TestStepThresholds:
    """Test step-specific confidence thresholds."""

    def test_thresholds_defined_for_active_steps(self):
        from langgraph_engine.rag_integration import STEP_THRESHOLDS

        # Active steps that still have thresholds defined (steps 1,2,5,7 removed in v1.13-1.15)
        active_steps = ["step0", "step8", "step11", "step13", "step14"]
        for step in active_steps:
            assert step in STEP_THRESHOLDS, "Missing threshold for {}".format(step)
            assert 0.5 <= STEP_THRESHOLDS[step] <= 1.0, "Invalid threshold for {}".format(step)

    def test_step7_has_highest_threshold(self):
        from langgraph_engine.rag_integration import STEP_THRESHOLDS

        # Step 7 (final prompt) should have the highest threshold
        assert STEP_THRESHOLDS["step7"] >= 0.90

    def test_step14_has_lowest_threshold(self):
        from langgraph_engine.rag_integration import STEP_THRESHOLDS

        # Step 14 (summary) has lowest stakes
        assert STEP_THRESHOLDS["step14"] <= 0.80


class TestSkillSelectionRAGBoost:
    """Test the RAG boost in skill_selection_criteria.py."""

    def test_rag_boost_returns_zero_no_skill_name(self):
        from langgraph_engine.skill_selection_criteria import _get_rag_skill_boost

        task = {"task_type": "Bug Fix"}
        skill = {"name": ""}
        assert _get_rag_skill_boost(task, skill) == 0.0

    @patch("langgraph_engine.skill_selection_criteria._load_cross_project_patterns")
    def test_pattern_boost_with_matching_patterns(self, mock_patterns):
        from langgraph_engine.skill_selection_criteria import _get_rag_skill_boost

        mock_patterns.return_value = {
            "patterns": [
                {"name": "python", "confidence": 0.8, "projects": ["p1", "p2"]},
                {"name": "flask", "confidence": 0.7, "projects": ["p1"]},
            ]
        }
        task = {"task_type": "Bug Fix"}
        skill = {"name": "python-flask-backend"}
        boost = _get_rag_skill_boost(task, skill)
        # Should get pattern boost for matching "python" and "flask"
        assert boost > 0
        assert boost <= 0.15
