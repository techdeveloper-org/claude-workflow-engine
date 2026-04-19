"""
Tests for CallGraph.compute_call_paths depth and path limits (issue #207).

Verifies:
- Default max_depth is 30 (was 15 before issue #207).
- Default max_paths is 500 (was 200 before issue #207).
- Both defaults can be overridden via CLAUDE_CG_MAX_DEPTH / CLAUDE_CG_MAX_PATHS
  environment variables at module load time.
- Explicit kwargs override the env defaults for a single call.
- A deep call chain (16 hops, above the old cap) is now reachable.
- When max_paths is hit, a warning is logged and results are returned
  (no exception).

Windows-safe: ASCII only, no Unicode characters.
"""

import importlib
import logging

import pytest

from langgraph_engine.parsers.graph_model import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_PATHS,
    CallGraph,
    make_call_edge,
    make_method_node,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_chain_graph(length):
    """Build a linear call graph chain of 'length' methods: m0 -> m1 -> ... -> m(length-1)."""
    g = CallGraph()
    for i in range(length):
        fqn = "chain.py::m%d" % i
        g.methods[fqn] = make_method_node(
            fqn,
            "m%d" % i,
            "chain.py",
            line=i + 1,
            parent_class=None,
        )
    for i in range(length - 1):
        src = "chain.py::m%d" % i
        dst = "chain.py::m%d" % (i + 1)
        g.edges.append(make_call_edge(src, dst, line=i + 1))
    # Mark edges as already resolved so get_edges() returns them directly
    g._resolved_edges = list(g.edges)
    return g


def _build_star_graph(fanout):
    """Build a 2-level star: root -> c0, c1, ..., c(fanout-1)."""
    g = CallGraph()
    g.methods["star.py::root"] = make_method_node("star.py::root", "root", "star.py", line=1, parent_class=None)
    for i in range(fanout):
        fqn = "star.py::c%d" % i
        g.methods[fqn] = make_method_node(fqn, "c%d" % i, "star.py", line=i + 2, parent_class=None)
        g.edges.append(make_call_edge("star.py::root", fqn, line=i + 2))
    g._resolved_edges = list(g.edges)
    return g


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeCallPathsDefaults:
    """Defaults must be the new values (30 / 500), not the old (15 / 200)."""

    def test_default_max_depth_is_30(self):
        assert DEFAULT_MAX_DEPTH == 30

    def test_default_max_paths_is_500(self):
        assert DEFAULT_MAX_PATHS == 500


class TestComputeCallPathsDepth:
    """A chain of 16 hops must be reachable -- above the old max_depth=15 cap."""

    def test_chain_of_16_hops_is_reached(self):
        # Before #207 a 16-hop chain was silently truncated at depth 15.
        # With the new default (30) it should reach the full chain.
        g = _build_chain_graph(16)
        paths = g.compute_call_paths()
        assert len(paths) >= 1, "at least one path should be emitted"
        # The longest path should cover the full chain (16 nodes).
        max_len = max(len(p["path"]) for p in paths)
        assert max_len == 16, "expected 16-hop path, got %d" % max_len

    def test_explicit_max_depth_kwarg_overrides_default(self):
        g = _build_chain_graph(20)
        # Clamp to 5 -- path should be at most 5 nodes deep.
        paths = g.compute_call_paths(max_depth=5)
        assert all(len(p["path"]) <= 5 for p in paths)

    def test_chain_deeper_than_max_depth_is_truncated(self):
        g = _build_chain_graph(10)
        paths = g.compute_call_paths(max_depth=3)
        # No path should exceed 3 nodes with max_depth=3.
        assert all(len(p["path"]) <= 3 for p in paths)


class TestComputeCallPathsPathsLimit:
    """max_paths must cap path emission and emit a warning when hit."""

    def test_wide_star_is_capped_by_max_paths(self):
        g = _build_star_graph(fanout=50)
        paths = g.compute_call_paths(max_paths=10)
        assert len(paths) <= 10

    def test_hitting_max_paths_logs_warning(self, caplog):
        g = _build_star_graph(fanout=10)
        with caplog.at_level(logging.WARNING, logger="langgraph_engine.parsers.graph_model"):
            g.compute_call_paths(max_paths=5)
        # Check that a warning was emitted mentioning the cap.
        matching = [
            rec for rec in caplog.records if "max_paths" in rec.getMessage() and "truncated" in rec.getMessage()
        ]
        assert matching, "expected a max_paths truncation warning"


class TestComputeCallPathsEnvVarOverride:
    """Env vars CLAUDE_CG_MAX_DEPTH / CLAUDE_CG_MAX_PATHS must tune module defaults."""

    def test_env_var_changes_module_default_on_reimport(self, monkeypatch):
        # Set env var and re-import the module to pick up the new default.
        monkeypatch.setenv("CLAUDE_CG_MAX_DEPTH", "7")
        monkeypatch.setenv("CLAUDE_CG_MAX_PATHS", "13")

        import langgraph_engine.parsers.graph_model as gm

        importlib.reload(gm)
        try:
            assert gm.DEFAULT_MAX_DEPTH == 7
            assert gm.DEFAULT_MAX_PATHS == 13
        finally:
            # Restore the real defaults for the rest of the test session.
            monkeypatch.delenv("CLAUDE_CG_MAX_DEPTH", raising=False)
            monkeypatch.delenv("CLAUDE_CG_MAX_PATHS", raising=False)
            importlib.reload(gm)

    def test_invalid_env_var_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_CG_MAX_DEPTH", "not_a_number")
        monkeypatch.setenv("CLAUDE_CG_MAX_PATHS", "")

        import langgraph_engine.parsers.graph_model as gm

        importlib.reload(gm)
        try:
            # Must fall back to the coded defaults, not raise.
            assert gm.DEFAULT_MAX_DEPTH == 30
            assert gm.DEFAULT_MAX_PATHS == 500
        finally:
            monkeypatch.delenv("CLAUDE_CG_MAX_DEPTH", raising=False)
            monkeypatch.delenv("CLAUDE_CG_MAX_PATHS", raising=False)
            importlib.reload(gm)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
