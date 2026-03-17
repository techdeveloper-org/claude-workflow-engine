"""
Acceptance Criteria Test for Level 2 Standards Integration.

Tests all 8 acceptance criteria defined in the task specification.
Run from project root with: python -m scripts.langgraph_engine.test_standards_ac
Or: cd <project_root> && python scripts/langgraph_engine/test_standards_ac.py
"""

import sys
import tempfile
from pathlib import Path

# Ensure the project root (parent of scripts/) is on the path so the
# langgraph_engine package can be imported with its relative imports intact.
_project_root = Path(__file__).parent.parent
if str(_project_root / "scripts") not in sys.path:
    sys.path.insert(0, str(_project_root / "scripts"))

# Package-relative imports (relative imports work once parent package is on path)
from langgraph_engine.standards_integration import STANDARDS_INTEGRATION_POINTS, apply_standards_at_step
from langgraph_engine.standard_selector import (
    detect_project_type,
    detect_framework,
    resolve_conflicts,
    select_standards,
    PRIORITY_CUSTOM,
    PRIORITY_TEAM,
    PRIORITY_FRAMEWORK,
    PRIORITY_LANGUAGE,
)
from langgraph_engine.standards_schema import StandardsSchema, build_standard_dict


def test_ac1_integration_points():
    """AC1: 5 integration points defined and documented."""
    assert len(STANDARDS_INTEGRATION_POINTS) == 5
    assert set(STANDARDS_INTEGRATION_POINTS.keys()) == {
        "step_1", "step_2", "step_5", "step_10", "step_13"
    }
    expected_locs = {
        "step_1": "Plan mode decision",
        "step_2": "Plan execution",
        "step_5": "Skill selection",
        "step_10": "Code review",
        "step_13": "Documentation",
    }
    for k, v in STANDARDS_INTEGRATION_POINTS.items():
        assert "location" in v, f"{k} missing location"
        assert "purpose" in v, f"{k} missing purpose"
        assert "trigger" in v, f"{k} missing trigger"
        assert "description" in v, f"{k} missing description"
        assert v["location"] == expected_locs[k], f"{k} location mismatch"
    print("AC1 PASS: 5 integration points defined and documented")


def test_ac2_project_type_detection():
    """AC2: Project type detection works."""
    markers = {
        "python": ("setup.py", ""),
        "java": ("pom.xml", "<project/>"),
        "javascript": ("package.json", '{"name": "test"}'),
        "go": ("go.mod", "module test"),
        "rust": ("Cargo.toml", "[package]"),
    }
    for expected_type, (filename, content) in markers.items():
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / filename).write_text(content, encoding="utf-8")
            detected = detect_project_type(d)
            assert detected == expected_type, f"Expected {expected_type} via {filename}, got {detected}"

    # TypeScript via tsconfig.json
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "tsconfig.json").write_text("{}", encoding="utf-8")
        assert detect_project_type(d) == "typescript"

    # C# via .csproj
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "App.csproj").write_text("<Project/>", encoding="utf-8")
        assert detect_project_type(d) == "csharp"

    print("AC2 PASS: Project type detection works (Python/Java/JS/TS/Go/Rust/C#)")


def test_ac3_framework_detection():
    """AC3: Framework detection works."""
    # Python frameworks
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "manage.py").write_text("", encoding="utf-8")
        assert detect_framework(d, "python") == "django"

    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "app.py").write_text("from flask import Flask", encoding="utf-8")
        assert detect_framework(d, "python") == "flask"

    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")
        assert detect_framework(d, "python") == "fastapi"

    # Java frameworks
    with tempfile.TemporaryDirectory() as d:
        pom = "<project><dependencies><artifactId>spring-boot-starter</artifactId></dependencies></project>"
        (Path(d) / "pom.xml").write_text(pom, encoding="utf-8")
        assert detect_framework(d, "java") == "spring-boot"

    with tempfile.TemporaryDirectory() as d:
        pom = "<project><dependencies><artifactId>quarkus-core</artifactId></dependencies></project>"
        (Path(d) / "pom.xml").write_text(pom, encoding="utf-8")
        assert detect_framework(d, "java") == "quarkus"

    # JS frameworks
    for fw, deps in [
        ("react", '{"dependencies": {"react": "18"}}'),
        ("angular", '{"dependencies": {"@angular/core": "16"}}'),
        ("vue", '{"dependencies": {"vue": "3"}}'),
    ]:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "package.json").write_text(deps, encoding="utf-8")
            assert detect_framework(d, "javascript") == fw, f"Expected {fw}"

    print("AC3 PASS: Framework detection works (Flask/Django/FastAPI, Spring-Boot/Quarkus, React/Angular/Vue)")


def test_ac4_schema_validation():
    """AC4: Standards schema validates YAML files (required_fields, type_checks, semver)."""
    schema = StandardsSchema()

    # Valid standard
    valid, errs = schema.validate(
        build_standard_dict("1.0.0", "python", {"naming": {"functions": "snake_case"}}, "flask", True)
    )
    assert valid and not errs, f"Valid standard should pass: {errs}"

    # Missing required field (enforced)
    v, e = schema.validate({"version": "1.0.0", "project_type": "python", "rules": {"naming": {}}})
    assert not v and any("enforced" in err for err in e)

    # Bad semver
    v, e = schema.validate({"version": "x.y", "project_type": "python", "enforced": True, "rules": {"naming": {}}})
    assert not v and any("semver" in err for err in e)

    # Type mismatch (enforced as string instead of bool)
    v, e = schema.validate({"version": "1.0.0", "project_type": "python", "enforced": "yes", "rules": {"naming": {}}})
    assert not v and any("bool" in err for err in e)

    # Unknown project_type
    v, e = schema.validate({"version": "1.0.0", "project_type": "cobol", "enforced": True, "rules": {"naming": {}}})
    assert not v and any("cobol" in err for err in e)

    # Empty rules
    v, e = schema.validate({"version": "1.0.0", "project_type": "python", "enforced": True, "rules": {}})
    assert not v and any("at least one" in err for err in e)

    print("AC4 PASS: Standards schema validates (required_fields, type_checks, semver)")


def test_ac5_conflict_resolution():
    """AC5: Conflicts resolved by priority (custom=4 > team=3 > framework=2 > language=1)."""
    assert PRIORITY_CUSTOM == 4
    assert PRIORITY_TEAM == 3
    assert PRIORITY_FRAMEWORK == 2
    assert PRIORITY_LANGUAGE == 1

    # All four levels define the same key 'x' - custom should win
    stds = [
        {"id": "lang", "source": "language_standards", "priority": PRIORITY_LANGUAGE, "rules": {"x": "lang", "y": "lang"}},
        {"id": "fw", "source": "framework_standards", "priority": PRIORITY_FRAMEWORK, "rules": {"x": "fw"}},
        {"id": "team", "source": "team_standards", "priority": PRIORITY_TEAM, "rules": {"x": "team"}},
        {"id": "custom", "source": "custom_standards", "priority": PRIORITY_CUSTOM, "rules": {"x": "custom"}},
    ]
    merged = resolve_conflicts(stds)
    assert merged["x"] == "custom", f"custom(4) should win, got: {merged['x']}"
    assert merged["y"] == "lang", f"Non-conflicting key from lang should survive, got: {merged['y']}"

    # Partial conflict: team vs language
    stds2 = [
        {"id": "lang", "source": "language_standards", "priority": PRIORITY_LANGUAGE, "rules": {"a": "lang"}},
        {"id": "team", "source": "team_standards", "priority": PRIORITY_TEAM, "rules": {"a": "team"}},
    ]
    merged2 = resolve_conflicts(stds2)
    assert merged2["a"] == "team", f"team(3) should beat language(1), got: {merged2['a']}"

    print("AC5 PASS: Conflicts resolved by priority (custom=4 > team=3 > framework=2 > language=1)")


def test_ac6_traceability():
    """AC6: Standards selection documented with traceability."""
    result = select_standards(".", "test-traceability-session")
    assert "traceability" in result

    t = result["traceability"]
    assert "detection_steps" in t, "Missing detection_steps"
    assert "sources_checked" in t, "Missing sources_checked"
    assert "priority_chain" in t, "Missing priority_chain"
    assert "custom(4) > team(3) > framework(2) > language(1)" in t["priority_chain"]

    # Verify sources_checked includes all 4 tiers
    sources = [s["source"] for s in t["sources_checked"]]
    assert "custom_standards" in sources
    assert "team_standards" in sources
    assert "framework_standards" in sources
    assert "language_standards" in sources

    # Verify each source entry has priority documented
    for s in t["sources_checked"]:
        assert "priority" in s, f"Missing priority in source {s.get('source')}"

    print("AC6 PASS: Standards selection documented with traceability")


def test_ac7_orchestrator_hooks():
    """AC7: Integration hooks wired into orchestrator graph."""
    from langgraph_engine.orchestrator import create_flow_graph

    graph = create_flow_graph()
    nodes = list(graph.nodes.keys())

    expected_hooks = [
        "level3_standards_hook_step1",
        "level3_standards_hook_step2",
        "level3_standards_hook_step5",
        "level3_standards_hook_step10",
        "level3_standards_hook_step13",
        "level2_select_standards",
    ]
    for hook in expected_hooks:
        assert hook in nodes, f"Missing graph node: {hook}"

    print("AC7 PASS: Integration hooks wired into orchestrator graph (6 standards nodes)")


def test_ac8_utf8_ascii_safe():
    """AC8: All code uses UTF-8 encoding and ASCII-safe practices."""
    files = [
        "standard_selector.py",
        "standards_integration.py",
        "standards_schema.py",
    ]
    engine_dir = Path(__file__).parent.parent / "scripts" / "langgraph_engine"
    for fname in files:
        fpath = engine_dir / fname
        content = fpath.read_text(encoding="utf-8")
        # Verify no non-ASCII characters
        content.encode("ascii", errors="strict")

    print("AC8 PASS: All code uses UTF-8 encoding and ASCII-safe practices")


def test_apply_all_hooks():
    """Integration test: apply all 5 hooks against a realistic FlowState."""
    mock_state = {
        "session_id": "integration-test-123",
        "project_root": ".",
        "is_java_project": False,
        "standards_loaded": True,
        "standards_count": 3,
        "level2_status": "OK",
        "tool_optimization_rules": {"read_max_lines": 500, "grep_max_results": 100},
        "standards_merged_rules": {"naming": {"functions": "snake_case"}},
        "standards_selection": {
            "project_type": "python",
            "framework": "flask",
            "traceability": {"priority_chain": "custom(4) > team(3) > framework(2) > language(1)"},
        },
        "detected_framework": "flask",
        "step5_skill": "python-backend-engineer",
        "step5_agent": "",
    }

    for step_num in [1, 2, 5, 10, 13]:
        state_copy = dict(mock_state)
        result = apply_standards_at_step(step_num, state_copy)
        flag = f"standards_applied_step{step_num}"
        assert result.get(flag) is True, f"standards_applied_step{step_num} not set"

    print("Integration test PASS: All 5 hooks apply correctly against realistic FlowState")


if __name__ == "__main__":
    tests = [
        test_ac1_integration_points,
        test_ac2_project_type_detection,
        test_ac3_framework_detection,
        test_ac4_schema_validation,
        test_ac5_conflict_resolution,
        test_ac6_traceability,
        test_ac7_orchestrator_hooks,
        test_ac8_utf8_ascii_safe,
        test_apply_all_hooks,
    ]

    print("=" * 60)
    print("LEVEL 2 STANDARDS INTEGRATION - ACCEPTANCE CRITERIA TESTS")
    print("=" * 60)
    print()

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as exc:
            print(f"FAIL {test_fn.__name__}: {exc}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed}/{len(tests)} tests passed, {failed} failed")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
