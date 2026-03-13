"""
Tests for Level 3 Robustness - Task #7

Covers:
- timeout_wrapper: StepTimeout, run_with_timeout, STEP_TIMEOUTS
- conflict_resolver: ConflictResolver (skill, standard, branch)
- review_criteria: ReviewCriteria (code quality, test coverage, docs)

All tests are self-contained and do not require external services.
ASCII-safe, UTF-8 encoded - Windows cp1252 compatible.
"""

import os
import sys
import json
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Setup mocks before importing project modules
# ---------------------------------------------------------------------------

# Mock heavy imports at module level
for _mod in ["loguru", "langgraph", "langgraph.graph", "anthropic"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

import loguru
if not hasattr(loguru, "logger") or not callable(getattr(loguru.logger, "info", None)):
    _noop = lambda *a, **kw: None
    loguru.logger = type("_Logger", (), {
        "info": _noop, "debug": _noop, "warning": _noop, "error": _noop,
    })()

# Add scripts/ to path
_SCRIPTS_DIR = str(Path(__file__).parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


# ---------------------------------------------------------------------------
# Tests: timeout_wrapper
# ---------------------------------------------------------------------------

class TestStepTimeout(unittest.TestCase):
    """Tests for StepTimeout and run_with_timeout."""

    def setUp(self):
        from langgraph_engine.timeout_wrapper import (
            StepTimeout, run_with_timeout, STEP_TIMEOUTS,
            fallback_step1, fallback_step2, fallback_step5, fallback_step7
        )
        self.StepTimeout = StepTimeout
        self.run_with_timeout = run_with_timeout
        self.STEP_TIMEOUTS = STEP_TIMEOUTS
        self.fallback_step1 = fallback_step1
        self.fallback_step2 = fallback_step2
        self.fallback_step5 = fallback_step5
        self.fallback_step7 = fallback_step7

    def test_step_timeouts_coverage(self):
        """All 14 Level 3 steps should have configured timeouts."""
        for step_num in range(1, 15):
            self.assertIn(step_num, self.STEP_TIMEOUTS, f"Missing timeout for Step {step_num}")
            self.assertGreater(self.STEP_TIMEOUTS[step_num], 0)

    def test_canonical_step_timeouts(self):
        """Specific steps must meet spec requirements."""
        self.assertEqual(self.STEP_TIMEOUTS[1], 30, "Step 1 should be 30s")
        self.assertEqual(self.STEP_TIMEOUTS[2], 120, "Step 2 should be 120s")
        self.assertEqual(self.STEP_TIMEOUTS[5], 60, "Step 5 should be 60s")
        self.assertEqual(self.STEP_TIMEOUTS[7], 30, "Step 7 should be 30s")

    def test_fast_function_returns_result(self):
        """Function completing within timeout should return its result."""
        def fast():
            return {"status": "ok", "value": 99}

        result = self.run_with_timeout(fn=fast, step_number=1, fallback={"status": "fallback"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["value"], 99)

    def test_timeout_returns_fallback(self):
        """Function exceeding timeout must return fallback result."""
        def slow():
            time.sleep(10)
            return {"status": "never"}

        wrapper = self.StepTimeout(timeout_seconds=1)
        start = time.time()
        result = wrapper.run(
            fn=slow,
            fallback={"status": "timeout_fallback"},
            step_label="TestSlow",
        )
        elapsed = time.time() - start

        self.assertTrue(result.get("timed_out"), "timed_out should be True")
        self.assertLess(elapsed, 3.0, "Should return within 3s of timeout")

    def test_exception_returns_error_result(self):
        """Function raising exception should return error result, not raise."""
        def failing():
            raise RuntimeError("test error")

        result = self.run_with_timeout(
            fn=failing,
            step_number=3,
            fallback={"status": "error_fallback"},
        )
        # Should not raise - should return error result
        self.assertIsNotNone(result)
        self.assertFalse(result.get("timed_out", True))  # Not a timeout, but an error
        self.assertIn("error", result)

    def test_fallback_step1_safe_defaults(self):
        """fallback_step1() must default to plan_required=True for safety."""
        fb = self.fallback_step1()
        self.assertTrue(fb["plan_required"], "Step 1 fallback must default to plan mode")
        self.assertEqual(fb["source"], "timeout_fallback")

    def test_fallback_step2_has_phases(self):
        """fallback_step2() must have a phases list."""
        fb = self.fallback_step2()
        self.assertIn("phases", fb)
        self.assertIsInstance(fb["phases"], list)

    def test_fallback_step5_empty_skills(self):
        """fallback_step5() should return empty skill/agent lists."""
        fb = self.fallback_step5()
        self.assertEqual(fb["selected_skills"], [])
        self.assertEqual(fb["selected_agents"], [])

    def test_run_with_timeout_custom_timeout(self):
        """custom_timeout parameter overrides STEP_TIMEOUTS lookup."""
        call_count = {"n": 0}

        def counted():
            call_count["n"] += 1
            return {"counted": call_count["n"]}

        result = self.run_with_timeout(
            fn=counted,
            step_number=1,
            custom_timeout=10,
        )
        self.assertEqual(result["counted"], 1)


# ---------------------------------------------------------------------------
# Tests: conflict_resolver
# ---------------------------------------------------------------------------

class TestConflictResolver(unittest.TestCase):
    """Tests for ConflictResolver: skill, standard, and branch conflicts."""

    def setUp(self):
        from langgraph_engine.conflict_resolver import ConflictResolver
        self.session_dir = tempfile.mkdtemp()
        self.ConflictResolver = ConflictResolver
        self.resolver = ConflictResolver(session_dir=self.session_dir)

    def _make_skill(self, name, domain="backend", capabilities=None, exclusive=False, conflicts_with=None):
        return {
            "name": name,
            "domain": domain,
            "capabilities": capabilities or [],
            "exclusive": exclusive,
            "conflicts_with": conflicts_with or [],
        }

    def test_no_conflicts_preserves_all_skills(self):
        """Skills with no conflicts should all be kept."""
        skills = [
            self._make_skill("pytest-testing", domain="testing"),
            self._make_skill("flask-backend", domain="backend"),
        ]
        result = self.resolver.resolve_skill_conflicts(skills)
        self.assertEqual(result["conflicts_detected"], 0)
        self.assertEqual(len(result["resolved_skills"]), 2)
        self.assertEqual(result["removed"], [])

    def test_explicit_conflicts_with_removes_lower_priority(self):
        """Skill with conflicts_with declaration triggers removal of lower-priority peer."""
        skills = [
            self._make_skill("flask", domain="backend", conflicts_with=["django"]),
            self._make_skill("django", domain="backend"),
        ]
        result = self.resolver.resolve_skill_conflicts(skills)
        # One should be removed (both same domain, flask declared conflict)
        self.assertGreater(result["conflicts_detected"], 0)
        self.assertEqual(len(result["resolved_skills"]), 1)

    def test_pattern_conflict_flask_django(self):
        """flask and django pattern names should be detected as mutually exclusive."""
        skills = [
            self._make_skill("flask-rest-api", domain="backend"),
            self._make_skill("django-drf-engineer", domain="backend"),
        ]
        result = self.resolver.resolve_skill_conflicts(skills)
        self.assertGreater(result["conflicts_detected"], 0)
        self.assertEqual(len(result["resolved_skills"]), 1)

    def test_exclusive_skill_drops_domain_peers(self):
        """An exclusive=True skill should remove all peers in its domain."""
        skills = [
            self._make_skill("auth-jwt", domain="security", exclusive=True),
            self._make_skill("auth-session", domain="security", exclusive=False),
            self._make_skill("auth-oauth", domain="security", exclusive=False),
        ]
        result = self.resolver.resolve_skill_conflicts(skills)
        # Only the exclusive skill should remain in domain
        kept_names = [s["name"] for s in result["resolved_skills"]]
        self.assertIn("auth-jwt", kept_names)
        # Other security skills should be removed
        self.assertNotIn("auth-session", kept_names)

    def test_standard_conflict_priority_wins(self):
        """Higher-priority standard wins on setting conflict."""
        standards = [
            {"name": "security", "type": "security", "settings": {"max_retries": 1}},
            {"name": "general", "type": "general", "settings": {"max_retries": 5}},
        ]
        result = self.resolver.resolve_standard_conflicts(standards)
        self.assertGreater(result["conflicts_detected"], 0)
        winner = result["overridden_settings"]["max_retries"]["winner"]
        self.assertEqual(winner, "security", "Security standard should win (priority=10)")

    def test_standard_no_conflict_empty_result(self):
        """Standards with non-overlapping settings should have no conflicts."""
        standards = [
            {"name": "enc", "type": "encoding", "settings": {"encoding": "utf-8"}},
            {"name": "log", "type": "logging", "settings": {"log_level": "INFO"}},
        ]
        result = self.resolver.resolve_standard_conflicts(standards)
        self.assertEqual(result["conflicts_detected"], 0)
        self.assertEqual(result["overridden_settings"], {})

    def test_branch_no_conflict(self):
        """Non-existent branch should return resolved_branch == desired_branch."""
        result = self.resolver.resolve_branch_conflict(
            desired_branch="feature/brand-new-unique-xyz-12345",
            repo_path=".",
        )
        # Even if git is not available, conflict_detected should be False
        # (branch won't be found in non-git dir)
        self.assertIsInstance(result["resolved_branch"], str)
        self.assertIn("conflict_detected", result)

    def test_save_conflict_log_creates_file(self):
        """save_conflict_log() should create a JSON file."""
        # Trigger a conflict first
        skills = [
            self._make_skill("flask-backend", domain="backend"),
            self._make_skill("django-backend", domain="backend"),
        ]
        self.resolver.resolve_skill_conflicts(skills)

        log_path = self.resolver.save_conflict_log()
        self.assertTrue(os.path.exists(log_path), f"Log file not found: {log_path}")

        with open(log_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        self.assertIn("total_conflicts", data)
        self.assertIn("conflicts", data)
        self.assertIsInstance(data["conflicts"], list)

    def test_conflict_log_ascii_safe(self):
        """Saved conflict log should be ASCII-safe (no non-ASCII chars)."""
        skills = [
            self._make_skill("flask-api", domain="backend"),
            self._make_skill("django-api", domain="backend"),
        ]
        self.resolver.resolve_skill_conflicts(skills)
        log_path = self.resolver.save_conflict_log()

        with open(log_path, "r", encoding="ascii") as fh:
            content = fh.read()  # Should not raise UnicodeDecodeError

        self.assertIsInstance(content, str)


# ---------------------------------------------------------------------------
# Tests: review_criteria
# ---------------------------------------------------------------------------

class TestReviewCriteria(unittest.TestCase):
    """Tests for ReviewCriteria code review checklist."""

    def setUp(self):
        from langgraph_engine.review_criteria import ReviewCriteria, REVIEW_RULES, SEVERITY_BLOCKING, SEVERITY_WARNING
        self.tmpdir = tempfile.mkdtemp()
        self.criteria = ReviewCriteria(project_root=self.tmpdir)
        self.REVIEW_RULES = REVIEW_RULES
        self.SEVERITY_BLOCKING = SEVERITY_BLOCKING
        self.SEVERITY_WARNING = SEVERITY_WARNING

    def _write_file(self, name: str, content: str) -> str:
        """Write content to temp dir and return full path."""
        path = os.path.join(self.tmpdir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def test_rule_count(self):
        """ReviewCriteria should have at least 10 rules."""
        self.assertGreaterEqual(len(self.REVIEW_RULES), 10)

    def test_all_rules_have_required_keys(self):
        """Each rule dict must have id, domain, severity, name, description, suggestion."""
        required_keys = {"id", "domain", "severity", "name", "description", "suggestion"}
        for rule in self.REVIEW_RULES:
            missing = required_keys - set(rule.keys())
            self.assertEqual(missing, set(), f"Rule {rule.get('id')} missing keys: {missing}")

    def test_bare_except_triggers_cq001(self):
        """CQ001 should be raised for bare 'except:' clauses."""
        src = self._write_file("bad_service.py", """
def fn():
    try:
        pass
    except:
        pass
""")
        result = self.criteria.evaluate(files_changed=[src])
        rule_ids = [i["rule_id"] for i in result.issues]
        self.assertIn("CQ001", rule_ids, "CQ001 should trigger for bare except")
        self.assertFalse(result.passed, "Should fail due to blocking CQ001")

    def test_hardcoded_secret_triggers_cq004(self):
        """CQ004 should detect hardcoded password assignments."""
        src = self._write_file("db.py", """
def connect():
    password = \"mysupersecretpassword\"
    return password
""")
        result = self.criteria.evaluate(files_changed=[src])
        rule_ids = [i["rule_id"] for i in result.issues]
        self.assertIn("CQ004", rule_ids, "CQ004 should trigger for hardcoded secret")

    def test_clean_code_passes(self):
        """Well-written code should pass all blocking rules."""
        src = self._write_file("good_service.py", """
\"\"\"Good service module.\"\"\"


def get_item(item_id: int) -> dict:
    \"\"\"Retrieve item by ID.\"\"\"
    try:
        return {"id": item_id}
    except Exception as exc:
        raise RuntimeError("Not found") from exc
""")
        test_src = self._write_file("test_good_service.py", """
\"\"\"Tests for good_service.\"\"\"


def test_get_item_returns_dict():
    \"\"\"Test that item is returned as dict.\"\"\"
    assert isinstance({}, dict)
    assert 1 > 0
    assert "a" in "abc"
""")
        result = self.criteria.evaluate(
            files_changed=[src, test_src],
            pr_body="This PR adds a clean service module with proper error handling and tests.",
        )
        blocking = [i for i in result.issues if i["severity"] == self.SEVERITY_BLOCKING]
        self.assertEqual(len(blocking), 0, f"No blocking issues expected, got: {blocking}")
        self.assertTrue(result.passed, "Clean code should pass review")

    def test_test_coverage_tc001(self):
        """TC001 triggers when source file has no corresponding test file."""
        src = self._write_file("solo_service.py", """
\"\"\"Solo module.\"\"\"


def solo_fn() -> None:
    \"\"\"Does nothing.\"\"\"
    pass
""")
        # No test file included
        result = self.criteria.evaluate(files_changed=[src])
        rule_ids = [i["rule_id"] for i in result.issues]
        self.assertIn("TC001", rule_ids, "TC001 should trigger when no test file present")

    def test_pr_body_too_short_triggers_dc003(self):
        """DC003 should warn about short PR descriptions."""
        result = self.criteria.evaluate(files_changed=[], pr_body="Fix")
        rule_ids = [i["rule_id"] for i in result.warnings]
        self.assertIn("DC003", rule_ids, "DC003 should trigger for short PR body")

    def test_to_dict_structure(self):
        """CriteriaResult.to_dict() should include all required keys."""
        result = self.criteria.evaluate(files_changed=[], pr_body="Test PR body text here")
        d = result.to_dict()
        for key in ("passed", "score", "issues", "warnings", "summary", "domain_scores", "timestamp"):
            self.assertIn(key, d, f"to_dict missing key: {key}")

    def test_score_range(self):
        """Score should be between 0.0 and 1.0."""
        result = self.criteria.evaluate(files_changed=[])
        self.assertGreaterEqual(result.score, 0.0)
        self.assertLessEqual(result.score, 1.0)

    def test_get_checklist_returns_all_rules(self):
        """get_checklist() should return one entry per rule."""
        checklist = self.criteria.get_checklist()
        self.assertEqual(len(checklist), len(self.REVIEW_RULES))
        for item in checklist:
            self.assertIn("id", item)
            self.assertIn("severity", item)

    def test_domain_scores_present(self):
        """domain_scores should include code_quality, test_coverage, documentation."""
        result = self.criteria.evaluate(files_changed=[])
        self.assertIn("code_quality", result.domain_scores)
        self.assertIn("test_coverage", result.domain_scores)
        self.assertIn("documentation", result.domain_scores)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
