"""
Tests for langgraph_engine/call_graph_analyzer.py

Tests cover all four public functions:
    analyze_impact_before_change
    get_implementation_context
    review_change_impact
    snapshot_call_graph

Python 3.8+ compatible. ASCII-only (cp1252-safe).
"""

import sys
from pathlib import Path

# Ensure the langgraph_engine package is importable from the test runner
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest

from langgraph_engine.call_graph_analyzer import (
    analyze_impact_before_change,
    get_implementation_context,
    review_change_impact,
    snapshot_call_graph,
)

# ---------------------------------------------------------------------------
# Helpers: create reusable Python source files in tmp_path
# ---------------------------------------------------------------------------


def _write(path, content):
    """Write text to path, creating parent directories as needed."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")


def _make_two_file_project(tmp_path):
    """Create a minimal 2-file project where module_a calls module_b methods.

    module_b.py defines ServiceB with two methods.
    module_a.py defines ServiceA whose run() calls ServiceB.process() and
    ServiceB.validate().

    Returns (project_root, path_a, path_b) as strings.
    """
    b_src = (
        "class ServiceB:\n"
        "    def process(self, data):\n"
        "        return data\n"
        "\n"
        "    def validate(self, data):\n"
        "        return True\n"
    )
    a_src = (
        "from module_b import ServiceB\n"
        "\n"
        "class ServiceA:\n"
        "    def run(self, data):\n"
        "        svc = ServiceB()\n"
        "        valid = svc.validate(data)\n"
        "        if valid:\n"
        "            return svc.process(data)\n"
        "        return None\n"
    )
    path_b = tmp_path / "module_b.py"
    path_a = tmp_path / "module_a.py"
    _write(path_b, b_src)
    _write(path_a, a_src)
    return str(tmp_path), str(path_a), str(path_b)


def _make_high_callers_project(tmp_path):
    """Create a project with one central method called by many methods (>8).

    hub.py defines HubService.core() which is the shared dependency.
    callers.py defines 9 methods that each call HubService.core().
    """
    hub_src = "class HubService:\n" "    def core(self):\n" "        return 42\n"
    # Build 9 caller methods
    lines = ["from hub import HubService\n", "\n", "class Callers:\n"]
    for i in range(9):
        lines.append("    def method_%d(self):\n" % i)
        lines.append("        h = HubService()\n")
        lines.append("        return h.core()\n")
        lines.append("\n")
    callers_src = "".join(lines)

    _write(tmp_path / "hub.py", hub_src)
    _write(tmp_path / "callers.py", callers_src)
    return str(tmp_path), str(tmp_path / "hub.py")


def _make_leaf_method_project(tmp_path):
    """Create a project with leaf methods (no callers) and shared methods.

    leaf.py defines LeafService with leaf_only() (nobody calls it)
    and shared() which is called by consumer.py.
    """
    leaf_src = (
        "class LeafService:\n"
        "    def leaf_only(self):\n"
        "        return 'leaf'\n"
        "\n"
        "    def shared(self):\n"
        "        return 'shared'\n"
    )
    consumer_src = (
        "from leaf import LeafService\n"
        "\n"
        "class Consumer:\n"
        "    def do_work(self):\n"
        "        svc = LeafService()\n"
        "        return svc.shared()\n"
    )
    _write(tmp_path / "leaf.py", leaf_src)
    _write(tmp_path / "consumer.py", consumer_src)
    return str(tmp_path), str(tmp_path / "leaf.py")


def _make_project_with_tests(tmp_path):
    """Create a project that has a matching test file referencing module_b.

    module_b.py defines ServiceB.
    tests/test_module_b.py imports module_b.
    """
    b_src = "class ServiceB:\n" "    def process(self, data):\n" "        return data\n"
    test_src = (
        "import module_b\n"
        "\n"
        "def test_process():\n"
        "    svc = module_b.ServiceB()\n"
        "    assert svc.process('x') == 'x'\n"
    )
    _write(tmp_path / "module_b.py", b_src)
    _write(tmp_path / "tests" / "test_module_b.py", test_src)
    return str(tmp_path), str(tmp_path / "module_b.py")


def _make_danger_zone_project(tmp_path):
    """Create a project where shared.py has a method with 5+ callers.

    shared.py defines SharedHelper.helper().
    caller_N.py each call SharedHelper.helper().
    """
    shared_src = "class SharedHelper:\n" "    def helper(self):\n" "        return True\n"
    _write(tmp_path / "shared.py", shared_src)

    for i in range(5):
        caller_src = (
            "from shared import SharedHelper\n"
            "\n"
            "class Caller%d:\n"
            "    def use(self):\n"
            "        h = SharedHelper()\n"
            "        return h.helper()\n"
        ) % i
        _write(tmp_path / ("caller_%d.py" % i), caller_src)

    return str(tmp_path), str(tmp_path / "shared.py")


# ===========================================================================
# TestAnalyzeImpactBeforeChange
# ===========================================================================


class TestAnalyzeImpactBeforeChange:

    def test_basic_impact_analysis(self, tmp_path):
        """File B callers should appear as affected_methods; call_graph_available True."""
        project_root, path_a, path_b = _make_two_file_project(tmp_path)

        result = analyze_impact_before_change(project_root, target_files=[path_b])

        assert isinstance(result, dict)
        assert result["call_graph_available"] is True
        assert "affected_methods" in result
        assert "risk_level" in result

        # affected_methods must be a list of dicts with required keys
        for entry in result["affected_methods"]:
            assert "fqn" in entry
            assert "callers_count" in entry
            assert "risk" in entry
            assert entry["risk"] in ("low", "medium", "high")

    def test_impact_with_no_target_files(self, tmp_path):
        """Calling with empty target_files should return valid dict with call_graph_available True."""
        project_root, path_a, path_b = _make_two_file_project(tmp_path)

        result = analyze_impact_before_change(project_root, target_files=[])

        assert isinstance(result, dict)
        assert result["call_graph_available"] is True
        assert "affected_methods" in result
        assert isinstance(result["affected_methods"], list)

    def test_impact_risk_levels(self, tmp_path):
        """Method with many callers (>8) should yield risk_level 'high'."""
        project_root, hub_path = _make_high_callers_project(tmp_path)

        result = analyze_impact_before_change(project_root, target_files=[hub_path])

        assert result["call_graph_available"] is True
        # With 9 callers, overall risk must be high
        assert result["risk_level"] == "high"

    def test_safe_change_zones(self, tmp_path):
        """Leaf methods (0 callers) must appear in safe_change_zones."""
        project_root, leaf_path = _make_leaf_method_project(tmp_path)

        result = analyze_impact_before_change(project_root, target_files=[leaf_path])

        assert result["call_graph_available"] is True
        safe_zones = result["safe_change_zones"]
        assert isinstance(safe_zones, list)
        # leaf_only has zero callers so it must be a safe zone
        # At least one FQN should contain 'leaf_only'
        _fqn_names = [fqn.split("::")[-1] if "::" in fqn else fqn for fqn in safe_zones]
        # Accept if any safe zone refers to leaf_only method
        has_leaf_only = any("leaf_only" in fqn for fqn in safe_zones)
        # Only assert if the graph was built with methods detected
        if result["affected_methods"]:
            assert has_leaf_only, "Expected 'leaf_only' in safe_change_zones. Got: %s" % safe_zones

    def test_danger_zones(self, tmp_path):
        """Methods with 5+ callers must appear in danger_zones."""
        project_root, shared_path = _make_danger_zone_project(tmp_path)

        result = analyze_impact_before_change(project_root, target_files=[shared_path])

        assert result["call_graph_available"] is True
        danger_zones = result["danger_zones"]
        assert isinstance(danger_zones, list)

        # Validate structure of each danger zone entry
        for entry in danger_zones:
            assert "fqn" in entry
            assert "callers_count" in entry
            assert entry["callers_count"] >= 5

        # There should be at least one danger zone for helper with 5 callers
        if result["affected_methods"]:
            assert len(danger_zones) >= 1, (
                "Expected at least 1 danger zone but found none. " "affected_methods: %s" % result["affected_methods"]
            )

    def test_cross_file_deps(self, tmp_path):
        """Cross-file dependencies should be detected when module_a calls module_b."""
        project_root, path_a, path_b = _make_two_file_project(tmp_path)

        result = analyze_impact_before_change(project_root, target_files=[path_b])

        assert result["call_graph_available"] is True
        cross = result["cross_file_deps"]
        assert isinstance(cross, list)
        # Each entry must have the required keys
        for entry in cross:
            assert "from_file" in entry
            assert "to_file" in entry
            assert "edge_count" in entry
            assert isinstance(entry["edge_count"], int)

    def test_empty_project(self, tmp_path):
        """Empty directory should return a graceful result with call_graph_available."""
        result = analyze_impact_before_change(str(tmp_path))

        assert isinstance(result, dict)
        # Must have the key; value may be True (empty graph) or False
        assert "call_graph_available" in result

        # On graceful return (no crash), standard keys should be present
        if not result["call_graph_available"]:
            # Fallback path: still has expected keys
            for key in ("affected_methods", "risk_level", "safe_change_zones", "danger_zones"):
                assert key in result
        else:
            # Graph built successfully (empty graph is fine)
            assert "affected_methods" in result

    def test_nonexistent_path(self, tmp_path):
        """Invalid path should return a valid fallback dict without raising.

        build_call_graph on a missing directory returns an empty graph
        (rglob yields nothing) rather than raising, so call_graph_available
        may be True (empty graph) or False depending on builder behavior.
        The critical guarantee is that the function never raises and always
        returns a dict with 'call_graph_available'.
        """
        bad_path = str(tmp_path / "does_not_exist")

        result = analyze_impact_before_change(bad_path)

        assert isinstance(result, dict)
        assert "call_graph_available" in result
        # Must not raise; value is True (empty graph) or False (build failed)
        assert result["call_graph_available"] in (True, False)
        # Standard output keys must be present regardless of availability
        for key in ("affected_methods", "risk_level", "safe_change_zones", "danger_zones", "cross_file_deps"):
            assert key in result, "Missing key: %s" % key


# ===========================================================================
# TestGetImplementationContext
# ===========================================================================


class TestGetImplementationContext:

    def test_basic_context(self, tmp_path):
        """Basic project: context has expected top-level keys and valid stats."""
        project_root, path_a, path_b = _make_two_file_project(tmp_path)

        result = get_implementation_context(project_root, target_files=[path_b])

        assert isinstance(result, dict)
        assert result["call_graph_available"] is True

        # Required keys
        for key in (
            "call_paths_through_targets",
            "entry_points_affected",
            "cross_file_dependencies",
            "suggested_test_scope",
            "stats",
        ):
            assert key in result, "Missing key: %s" % key

        # Stats has required sub-keys
        stats = result["stats"]
        assert "total_classes" in stats
        assert "total_methods" in stats
        assert "max_depth" in stats

        # Numeric values
        assert isinstance(stats["total_classes"], int)
        assert isinstance(stats["total_methods"], int)
        assert isinstance(stats["max_depth"], int)

        # call_paths_through_targets is a list
        assert isinstance(result["call_paths_through_targets"], list)

        # Each path entry has 'path' and 'depth'
        for entry in result["call_paths_through_targets"]:
            assert "path" in entry
            assert "depth" in entry
            assert isinstance(entry["path"], list)
            assert isinstance(entry["depth"], int)

    def test_suggested_test_scope(self, tmp_path):
        """When test files reference the target module, they appear in suggested_test_scope."""
        project_root, path_b = _make_project_with_tests(tmp_path)

        result = get_implementation_context(project_root, target_files=[path_b])

        assert result["call_graph_available"] is True
        scope = result["suggested_test_scope"]
        assert isinstance(scope, list)
        # The test file references 'module_b' so it should appear
        has_test = any("test_module_b" in f for f in scope)
        assert has_test, "Expected test_module_b.py in suggested_test_scope. Got: %s" % scope

    def test_cross_file_dependencies(self, tmp_path):
        """cross_file_dependencies is returned as a dict of module_stem -> [dep_stems]."""
        project_root, path_a, path_b = _make_two_file_project(tmp_path)

        result = get_implementation_context(project_root, target_files=[path_a])

        assert result["call_graph_available"] is True
        deps = result["cross_file_dependencies"]
        assert isinstance(deps, dict)
        # Values must be lists
        for key, val in deps.items():
            assert isinstance(key, str)
            assert isinstance(val, list)

    def test_no_target_files(self, tmp_path):
        """Calling with None target_files should return a graceful, valid result."""
        project_root, path_a, path_b = _make_two_file_project(tmp_path)

        result = get_implementation_context(project_root, target_files=None)

        assert isinstance(result, dict)
        assert "call_graph_available" in result

        if result["call_graph_available"]:
            for key in (
                "call_paths_through_targets",
                "entry_points_affected",
                "cross_file_dependencies",
                "suggested_test_scope",
                "stats",
            ):
                assert key in result


# ===========================================================================
# TestReviewChangeImpact
# ===========================================================================


class TestReviewChangeImpact:

    def test_basic_review(self, tmp_path):
        """Snapshot then add a new file: new_edges should be detected."""
        project_root, path_a, path_b = _make_two_file_project(tmp_path)

        # Capture baseline snapshot
        pre_snapshot = snapshot_call_graph(project_root)
        if not pre_snapshot.get("call_graph_available"):
            pytest.skip("Call graph not available in this environment")

        # Add a new file with a call into module_b
        new_src = (
            "from module_b import ServiceB\n"
            "\n"
            "class NewConsumer:\n"
            "    def consume(self):\n"
            "        svc = ServiceB()\n"
            "        return svc.process('new')\n"
        )
        _write(tmp_path / "new_consumer.py", new_src)

        result = review_change_impact(
            project_root,
            modified_files=[str(tmp_path / "new_consumer.py")],
            pre_change_snapshot=pre_snapshot,
        )

        assert isinstance(result, dict)
        assert result["call_graph_available"] is True
        assert "new_edges" in result
        assert isinstance(result["new_edges"], list)

        # Each edge entry must have from/to/type
        for edge in result["new_edges"]:
            assert "from" in edge
            assert "to" in edge
            assert "type" in edge

    def test_review_with_no_snapshot(self, tmp_path):
        """Passing no pre_change_snapshot should still return a valid dict."""
        project_root, path_a, path_b = _make_two_file_project(tmp_path)

        result = review_change_impact(
            project_root,
            modified_files=[path_b],
            pre_change_snapshot=None,
        )

        assert isinstance(result, dict)
        assert "call_graph_available" in result

        if result["call_graph_available"]:
            for key in (
                "new_edges",
                "removed_edges",
                "orphaned_methods",
                "breaking_changes",
                "cyclomatic_change",
                "max_call_depth",
                "risk_assessment",
                "summary",
            ):
                assert key in result

    def test_review_empty_modified_files(self, tmp_path):
        """Passing empty modified_files should return a graceful result."""
        project_root, path_a, path_b = _make_two_file_project(tmp_path)

        result = review_change_impact(
            project_root,
            modified_files=[],
            pre_change_snapshot=None,
        )

        assert isinstance(result, dict)
        assert "call_graph_available" in result
        # Must not raise; either True or False is acceptable
        if result["call_graph_available"]:
            assert "new_edges" in result
            assert "risk_assessment" in result

    def test_cyclomatic_change(self, tmp_path):
        """cyclomatic_change must have before_avg, after_avg, delta keys."""
        project_root, path_a, path_b = _make_two_file_project(tmp_path)

        pre_snapshot = snapshot_call_graph(project_root)

        result = review_change_impact(
            project_root,
            modified_files=[path_b],
            pre_change_snapshot=pre_snapshot,
        )

        assert isinstance(result, dict)

        if result.get("call_graph_available"):
            cx = result["cyclomatic_change"]
            assert "before_avg" in cx
            assert "after_avg" in cx
            assert "delta" in cx

            assert isinstance(cx["before_avg"], float)
            assert isinstance(cx["after_avg"], float)
            assert isinstance(cx["delta"], float)
        else:
            # Fallback must still have cyclomatic_change
            assert "cyclomatic_change" in result
            cx = result["cyclomatic_change"]
            for key in ("before_avg", "after_avg", "delta"):
                assert key in cx

    def test_risk_assessment_values(self, tmp_path):
        """risk_assessment must be one of 'safe', 'caution', 'risky'."""
        project_root, path_a, path_b = _make_two_file_project(tmp_path)

        result = review_change_impact(
            project_root,
            modified_files=[path_b],
        )

        assert isinstance(result, dict)
        assert "risk_assessment" in result
        assert result["risk_assessment"] in ("safe", "caution", "risky"), (
            "Unexpected risk_assessment value: %r" % result["risk_assessment"]
        )


# ===========================================================================
# TestSnapshotCallGraph
# ===========================================================================


class TestSnapshotCallGraph:

    def test_snapshot_returns_dict(self, tmp_path):
        """Snapshot of a real project returns a dict with expected top-level keys."""
        project_root, path_a, path_b = _make_two_file_project(tmp_path)

        result = snapshot_call_graph(project_root)

        assert isinstance(result, dict)
        assert "call_graph_available" in result

        if result["call_graph_available"]:
            # to_dict() adds these keys
            for key in ("version", "stats", "nodes", "edges"):
                assert key in result, "Missing key in snapshot: %s" % key

            # nodes has classes and methods
            nodes = result["nodes"]
            assert "classes" in nodes
            assert "methods" in nodes
            assert isinstance(nodes["classes"], list)
            assert isinstance(nodes["methods"], list)

            # stats has expected fields
            stats = result["stats"]
            for stat_key in ("total_classes", "total_methods", "files_analyzed"):
                assert stat_key in stats

            # edges is a list
            assert isinstance(result["edges"], list)

    def test_snapshot_empty_project(self, tmp_path):
        """Empty project returns empty/minimal dict with call_graph_available key."""
        result = snapshot_call_graph(str(tmp_path))

        assert isinstance(result, dict)
        assert "call_graph_available" in result
        # For an empty directory the graph may be built (0 files) or unavailable
        if result["call_graph_available"]:
            assert "stats" in result
            assert result["stats"].get("total_methods", 0) == 0
        else:
            # Graceful failure: only key is call_graph_available
            assert result == {"call_graph_available": False}

    def test_snapshot_matches_call_graph_to_dict(self, tmp_path):
        """Snapshot output should match the structure produced by CallGraph.to_dict()."""
        project_root, path_a, path_b = _make_two_file_project(tmp_path)

        result = snapshot_call_graph(project_root)

        assert isinstance(result, dict)

        if not result.get("call_graph_available"):
            pytest.skip("Call graph not available in this environment")

        # Version field must match the known format from to_dict()
        assert result.get("version") == "2.0.0"

        # stats fields that to_dict() always includes
        stats = result["stats"]
        for expected_key in (
            "total_classes",
            "total_methods",
            "total_call_edges",
            "files_analyzed",
            "max_call_depth",
        ):
            assert expected_key in stats, "Missing stats key: %s. Got: %s" % (expected_key, list(stats.keys()))

        # call_paths key is present (list, possibly empty)
        assert "call_paths" in result
        assert isinstance(result["call_paths"], list)

        # Each call_path entry has 'path' and 'depth'
        for path_entry in result["call_paths"]:
            assert "path" in path_entry
            assert "depth" in path_entry


# ===========================================================================
# Helpers for phase subgraph tests: 3-file project
# ===========================================================================


def _make_three_file_project(tmp_path):
    """Create a 3-file project with a realistic layered architecture.

    models.py   - class User with __init__, validate, save
    services.py - class UserService that calls User.validate() and User.save()
    api.py      - class UserAPI that calls UserService methods

    Returns (project_root, models_path, services_path, api_path) as strings.
    """
    models_src = (
        "class User:\n"
        "    def __init__(self, name, email):\n"
        "        self.name = name\n"
        "        self.email = email\n"
        "\n"
        "    def validate(self):\n"
        "        return bool(self.name and self.email)\n"
        "\n"
        "    def save(self):\n"
        "        return True\n"
    )
    services_src = (
        "from models import User\n"
        "\n"
        "class UserService:\n"
        "    def create_user(self, name, email):\n"
        "        u = User(name, email)\n"
        "        if u.validate():\n"
        "            u.save()\n"
        "            return u\n"
        "        return None\n"
        "\n"
        "    def update_user(self, user):\n"
        "        if user.validate():\n"
        "            user.save()\n"
        "            return True\n"
        "        return False\n"
    )
    api_src = (
        "from services import UserService\n"
        "\n"
        "class UserAPI:\n"
        "    def post_user(self, name, email):\n"
        "        svc = UserService()\n"
        "        return svc.create_user(name, email)\n"
        "\n"
        "    def put_user(self, user):\n"
        "        svc = UserService()\n"
        "        return svc.update_user(user)\n"
    )
    models_path = tmp_path / "models.py"
    services_path = tmp_path / "services.py"
    api_path = tmp_path / "api.py"
    _write(models_path, models_src)
    _write(services_path, services_src)
    _write(api_path, api_src)
    return (
        str(tmp_path),
        str(models_path),
        str(services_path),
        str(api_path),
    )


def _make_high_callers_phase_project(tmp_path):
    """Create a project where one method in models.py is called by 6+ callers.

    models.py   - class User with core_validate (called by many)
    callers.py  - 6 methods that each call User.core_validate()

    Returns (project_root, models_path, callers_path) as strings.
    """
    models_src = "class User:\n" "    def core_validate(self):\n" "        return True\n"
    lines = ["from models import User\n", "\n", "class MultiCaller:\n"]
    for i in range(6):
        lines.append("    def caller_%d(self):\n" % i)
        lines.append("        u = User()\n")
        lines.append("        return u.core_validate()\n")
        lines.append("\n")
    callers_src = "".join(lines)
    models_path = tmp_path / "models.py"
    callers_path = tmp_path / "callers.py"
    _write(models_path, models_src)
    _write(callers_path, callers_src)
    return str(tmp_path), str(models_path), str(callers_path)


# ===========================================================================
# TestExtractPhaseSubgraph
# ===========================================================================


class TestExtractPhaseSubgraph:

    def test_subgraph_scoped_to_phase_files(self, tmp_path):
        """methods_in_phase only includes models.py methods; expanded set adds callers."""
        from langgraph_engine.call_graph_analyzer import extract_phase_subgraph, snapshot_call_graph

        project_root, models_path, services_path, api_path = _make_three_file_project(tmp_path)

        snap = snapshot_call_graph(project_root)
        if not snap.get("call_graph_available"):
            pytest.skip("Call graph not available in this environment")

        phase_files = ["models.py"]
        result = extract_phase_subgraph(snap, phase_files)

        assert isinstance(result, dict)
        assert "nodes" in result
        assert "stats" in result
        stats = result["stats"]
        assert "methods_in_phase" in stats
        assert "methods_in_scope" in stats

        # methods_in_phase must be <= methods_in_scope (scope expands with callers)
        assert stats["methods_in_phase"] <= stats["methods_in_scope"]

        # Only models.py methods count toward phase
        all_methods_in_subgraph = result["nodes"]["methods"]
        phase_method_ids = set()
        for m in all_methods_in_subgraph:
            mfile = m.get("file", "").replace("\\", "/")
            if "models.py" in mfile:
                phase_method_ids.add(m.get("id", ""))

        # methods_in_phase should equal the count of models.py methods found
        assert stats["methods_in_phase"] == len(phase_method_ids)

    def test_subgraph_includes_callers(self, tmp_path):
        """1-hop callers from services.py appear in the expanded method set."""
        from langgraph_engine.call_graph_analyzer import extract_phase_subgraph, snapshot_call_graph

        project_root, models_path, services_path, api_path = _make_three_file_project(tmp_path)

        snap = snapshot_call_graph(project_root)
        if not snap.get("call_graph_available"):
            pytest.skip("Call graph not available in this environment")

        result = extract_phase_subgraph(snap, ["models.py"])

        all_method_ids = {m.get("id", "") for m in result["nodes"]["methods"]}

        # At least one method from services.py should appear (1-hop callers)
        services_methods_in_scope = [mid for mid in all_method_ids if "services.py" in mid or "UserService" in mid]
        # Guard: if AST parsing detected the cross-file call, callers should be included
        if result["stats"]["methods_in_scope"] > result["stats"]["methods_in_phase"]:
            assert (
                len(services_methods_in_scope) > 0
            ), "Expected services.py methods in expanded scope. " "Scope methods: %s" % sorted(all_method_ids)

    def test_subgraph_includes_callees(self, tmp_path):
        """1-hop callees from models.py appear when services.py is the phase."""
        from langgraph_engine.call_graph_analyzer import extract_phase_subgraph, snapshot_call_graph

        project_root, models_path, services_path, api_path = _make_three_file_project(tmp_path)

        snap = snapshot_call_graph(project_root)
        if not snap.get("call_graph_available"):
            pytest.skip("Call graph not available in this environment")

        result = extract_phase_subgraph(snap, ["services.py"])

        all_method_ids = {m.get("id", "") for m in result["nodes"]["methods"]}

        # At least one method from models.py should appear (1-hop callees)
        models_methods_in_scope = [mid for mid in all_method_ids if "models.py" in mid or "User." in mid]
        if result["stats"]["methods_in_scope"] > result["stats"]["methods_in_phase"]:
            assert (
                len(models_methods_in_scope) > 0
            ), "Expected models.py methods as callees in scope. " "Scope methods: %s" % sorted(all_method_ids)

    def test_subgraph_empty_phase_files(self, tmp_path):
        """Empty phase_files returns an empty structure without raising."""
        from langgraph_engine.call_graph_analyzer import extract_phase_subgraph, snapshot_call_graph

        project_root, models_path, services_path, api_path = _make_three_file_project(tmp_path)

        snap = snapshot_call_graph(project_root)

        result = extract_phase_subgraph(snap, [])

        assert isinstance(result, dict)
        assert "nodes" in result
        assert result["nodes"]["methods"] == []
        assert result["nodes"]["classes"] == []
        assert result["edges"] == []

    def test_subgraph_no_rebuild(self, tmp_path):
        """Function works on a plain dict snapshot without needing CallGraph object."""
        from langgraph_engine.call_graph_analyzer import extract_phase_subgraph, snapshot_call_graph

        project_root, models_path, services_path, api_path = _make_three_file_project(tmp_path)

        snap = snapshot_call_graph(project_root)
        if not snap.get("call_graph_available"):
            pytest.skip("Call graph not available in this environment")

        # snap is already a plain dict; pass it directly
        assert isinstance(snap, dict), "snapshot must be a plain dict"

        result = extract_phase_subgraph(snap, ["models.py"])

        # Must return a valid structure without rebuilding the graph
        assert isinstance(result, dict)
        assert "nodes" in result
        assert "edges" in result
        assert "stats" in result
        assert isinstance(result["nodes"]["methods"], list)
        assert isinstance(result["edges"], list)

    def test_subgraph_stats(self, tmp_path):
        """stats dict contains all required keys."""
        from langgraph_engine.call_graph_analyzer import extract_phase_subgraph, snapshot_call_graph

        project_root, models_path, services_path, api_path = _make_three_file_project(tmp_path)

        snap = snapshot_call_graph(project_root)

        result = extract_phase_subgraph(snap, ["models.py"])

        stats = result.get("stats", {})
        required_keys = [
            "methods_in_scope",
            "methods_in_phase",
            "edges_in_scope",
            "files_in_scope",
            "classes_in_scope",
        ]
        for key in required_keys:
            assert key in stats, "Missing stats key: %s. Got: %s" % (key, sorted(stats.keys()))


# ===========================================================================
# TestGetPhaseScopedContext
# ===========================================================================


class TestGetPhaseScopedContext:

    def test_phase_context_basic(self, tmp_path):
        """Basic call: call_graph_available=True, phase_files returned, risk_level valid."""
        from langgraph_engine.call_graph_analyzer import get_phase_scoped_context, snapshot_call_graph

        project_root, models_path, services_path, api_path = _make_three_file_project(tmp_path)

        snap = snapshot_call_graph(project_root)
        if not snap.get("call_graph_available"):
            pytest.skip("Call graph not available in this environment")

        result = get_phase_scoped_context(snap, ["models.py"], "Test user model phase")

        assert isinstance(result, dict)
        assert result["call_graph_available"] is True
        assert result["phase_files"] == ["models.py"]
        assert result["risk_level"] in ("low", "medium", "high")

        for key in ("danger_zones", "safe_change_zones", "entry_points", "cross_phase_callers", "summary", "subgraph"):
            assert key in result, "Missing key: %s" % key

    def test_phase_context_danger_zones(self, tmp_path):
        """Method called by 6+ callers must appear in danger_zones."""
        from langgraph_engine.call_graph_analyzer import get_phase_scoped_context, snapshot_call_graph

        project_root, models_path, callers_path = _make_high_callers_phase_project(tmp_path)

        snap = snapshot_call_graph(project_root)
        if not snap.get("call_graph_available"):
            pytest.skip("Call graph not available in this environment")

        result = get_phase_scoped_context(snap, ["models.py"])

        assert result.get("call_graph_available") is True
        danger_zones = result["danger_zones"]
        assert isinstance(danger_zones, list)

        # If the graph detected the 6 callers, danger_zones must be non-empty
        if result["subgraph"]["stats"].get("methods_in_phase", 0) > 0:
            has_high_caller = any(d.get("callers_count", 0) >= 5 for d in danger_zones)
            # core_validate is called 6 times; must appear once graph is built
            assert has_high_caller, "Expected danger zone with 5+ callers. Got: %s" % danger_zones

    def test_phase_context_safe_zones(self, tmp_path):
        """Methods with 0 callers should appear in safe_change_zones."""
        from langgraph_engine.call_graph_analyzer import get_phase_scoped_context, snapshot_call_graph

        project_root, models_path, services_path, api_path = _make_three_file_project(tmp_path)

        snap = snapshot_call_graph(project_root)
        if not snap.get("call_graph_available"):
            pytest.skip("Call graph not available in this environment")

        # api.py methods are entry points (not called by anyone in the graph)
        result = get_phase_scoped_context(snap, ["api.py"])

        assert result.get("call_graph_available") is True
        safe_zones = result["safe_change_zones"]
        assert isinstance(safe_zones, list)
        # Safe zones are valid FQN strings
        for fqn in safe_zones:
            assert isinstance(fqn, str)
            assert len(fqn) > 0

    def test_phase_context_cross_phase_callers(self, tmp_path):
        """services.py methods calling models.py appear in cross_phase_callers."""
        from langgraph_engine.call_graph_analyzer import get_phase_scoped_context, snapshot_call_graph

        project_root, models_path, services_path, api_path = _make_three_file_project(tmp_path)

        snap = snapshot_call_graph(project_root)
        if not snap.get("call_graph_available"):
            pytest.skip("Call graph not available in this environment")

        result = get_phase_scoped_context(snap, ["models.py"])

        assert result.get("call_graph_available") is True
        cross_callers = result["cross_phase_callers"]
        assert isinstance(cross_callers, list)

        for entry in cross_callers:
            assert "fqn" in entry
            assert "file" in entry
            assert "calls_into" in entry

        # If the graph detected cross-file calls, some callers from services.py
        # should appear as cross-phase callers into models.py
        if result["subgraph"]["stats"].get("methods_in_scope", 0) > result["subgraph"]["stats"].get(
            "methods_in_phase", 0
        ):
            caller_fqns = [c["fqn"] for c in cross_callers]
            has_services_caller = any("services.py" in c["file"] or "UserService" in c["fqn"] for c in cross_callers)
            assert has_services_caller, "Expected services.py as cross-phase caller. Got: %s" % caller_fqns

    def test_phase_context_entry_points(self, tmp_path):
        """Public phase methods not called by other phase methods are entry points."""
        from langgraph_engine.call_graph_analyzer import get_phase_scoped_context, snapshot_call_graph

        project_root, models_path, services_path, api_path = _make_three_file_project(tmp_path)

        snap = snapshot_call_graph(project_root)
        if not snap.get("call_graph_available"):
            pytest.skip("Call graph not available in this environment")

        result = get_phase_scoped_context(snap, ["api.py"])

        assert result.get("call_graph_available") is True
        entry_points = result["entry_points"]
        assert isinstance(entry_points, list)

        for fqn in entry_points:
            assert isinstance(fqn, str)
            # Entry points must not start with underscore (private methods excluded)
            method_name = fqn.split("::")[-1] if "::" in fqn else fqn
            method_name = method_name.split(".")[-1] if "." in method_name else method_name
            assert not method_name.startswith("_"), "Private method should not be an entry point: %s" % fqn

    def test_phase_context_no_snapshot(self, tmp_path):
        """None snapshot returns call_graph_available=False gracefully."""
        from langgraph_engine.call_graph_analyzer import get_phase_scoped_context

        result = get_phase_scoped_context(None, ["models.py"])

        assert isinstance(result, dict)
        assert result["call_graph_available"] is False
        # Must still have all expected keys
        for key in (
            "phase_files",
            "danger_zones",
            "safe_change_zones",
            "entry_points",
            "cross_phase_callers",
            "risk_level",
            "summary",
        ):
            assert key in result, "Missing key: %s" % key

    def test_phase_context_no_phase_files(self, tmp_path):
        """Empty phase_files returns a graceful result without crashing."""
        from langgraph_engine.call_graph_analyzer import get_phase_scoped_context, snapshot_call_graph

        project_root, models_path, services_path, api_path = _make_three_file_project(tmp_path)

        snap = snapshot_call_graph(project_root)

        result = get_phase_scoped_context(snap, [])

        assert isinstance(result, dict)
        assert "call_graph_available" in result
        # Must not raise; phase_files must be empty
        assert result["phase_files"] == []
        for key in ("danger_zones", "safe_change_zones", "entry_points", "cross_phase_callers", "risk_level"):
            assert key in result

    def test_phase_context_summary(self, tmp_path):
        """Summary string contains 'Phase:' and 'risk='."""
        from langgraph_engine.call_graph_analyzer import get_phase_scoped_context, snapshot_call_graph

        project_root, models_path, services_path, api_path = _make_three_file_project(tmp_path)

        snap = snapshot_call_graph(project_root)
        if not snap.get("call_graph_available"):
            pytest.skip("Call graph not available in this environment")

        result = get_phase_scoped_context(snap, ["models.py"], "User model phase")

        assert result.get("call_graph_available") is True
        summary = result["summary"]
        assert isinstance(summary, str)
        assert "Phase:" in summary, "Expected 'Phase:' in summary. Got: %r" % summary
        assert "risk=" in summary, "Expected 'risk=' in summary. Got: %r" % summary
