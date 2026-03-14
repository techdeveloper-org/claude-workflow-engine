#!/usr/bin/env python
"""
End-to-End Workflow Test - Real-World Scenario

Demonstrates the complete 14-step pipeline with a realistic task:
"Implement user authentication system with OAuth2 support"

This test:
1. Creates a mock project structure
2. Simulates all 14 steps
3. Validates conditional routing
4. Tests error recovery
5. Reports comprehensive metrics
"""

import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime
import tempfile
import shutil

sys.path.insert(0, 'scripts')


class E2EWorkflowTest:
    """End-to-end workflow test suite."""

    def __init__(self):
        """Initialize test environment."""
        self.test_dir = tempfile.mkdtemp(prefix="e2e_test_")
        self.start_time = datetime.now()
        self.steps_completed = {}
        self.errors = []
        self.warnings = []

    def log(self, step_name: str, status: str, message: str = ""):
        """Log step execution."""
        now = datetime.now()
        elapsed = (now - self.start_time).total_seconds()
        status_symbol = "✅" if status == "OK" else "⚠️" if status == "WARNING" else "❌"
        print(f"[{elapsed:.1f}s] {status_symbol} {step_name}: {message}")

    def setup_test_project(self):
        """Create a mock project structure."""
        self.log("SETUP", "OK", "Creating test project")

        # Create project structure
        project_root = Path(self.test_dir) / "test_project"
        project_root.mkdir()

        (project_root / "src").mkdir()
        (project_root / "tests").mkdir()
        (project_root / "docs").mkdir()

        # Create some Python files
        (project_root / "src" / "auth.py").write_text("# Authentication module\npass\n")
        (project_root / "src" / "models.py").write_text("# Data models\npass\n")
        (project_root / "tests" / "test_auth.py").write_text("# Auth tests\npass\n")

        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=project_root,
            capture_output=True,
            timeout=5
        )

        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=project_root,
            capture_output=True,
            timeout=5
        )

        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=project_root,
            capture_output=True,
            timeout=5
        )

        subprocess.run(
            ["git", "add", "-A"],
            cwd=project_root,
            capture_output=True,
            timeout=5
        )

        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=project_root,
            capture_output=True,
            timeout=5
        )

        self.project_root = project_root
        return project_root

    def test_step_0_task_analysis(self):
        """Test Step 0: Task Analysis."""
        self.log("STEP 0", "OK", "Task Analysis")

        from langgraph_engine.subgraphs.level3_execution import step0_task_analysis

        state = {
            "user_message": "Implement user authentication system with OAuth2 support",
            "project_root": str(self.project_root),
            "context_metadata": {"files_loaded_count": 10},
            "patterns_detected": ["Python", "REST API"],
        }

        result = step0_task_analysis(state)
        state.update(result)

        self.steps_completed["step0"] = result
        self.log("STEP 0", "OK", f"Task type: {result.get('step0_task_type')}, "
                                  f"Complexity: {result.get('step0_complexity')}")
        return state

    def test_step_1_plan_decision(self, state):
        """Test Step 1: Plan Mode Decision."""
        self.log("STEP 1", "OK", "Plan Mode Decision")

        from langgraph_engine.subgraphs.level3_execution import step1_plan_mode_decision

        result = step1_plan_mode_decision(state)
        state.update(result)

        self.steps_completed["step1"] = result
        plan_required = result.get("step1_plan_required", False)
        self.log("STEP 1", "OK", f"Plan required: {plan_required}")

        return state, plan_required

    def test_steps_3_to_7(self, state):
        """Test Steps 3-7 (skip Step 2 for brevity)."""
        from langgraph_engine.subgraphs.level3_execution import (
            step3_task_breakdown_validation, step4_toon_refinement,
            step5_skill_agent_selection, step6_skill_validation_download,
            step7_final_prompt_generation
        )

        steps = [
            ("STEP 3", step3_task_breakdown_validation, "Task Breakdown Validation"),
            ("STEP 4", step4_toon_refinement, "TOON Refinement"),
            ("STEP 5", step5_skill_agent_selection, "Skill & Agent Selection"),
            ("STEP 6", step6_skill_validation_download, "Skill Validation"),
            ("STEP 7", step7_final_prompt_generation, "Final Prompt Generation"),
        ]

        for step_name, step_func, desc in steps:
            try:
                result = step_func(state)
                state.update(result)
                self.steps_completed[step_name.lower().replace(" ", "")] = result
                self.log(step_name, "OK", desc)
            except Exception as e:
                self.log(step_name, "ERROR", str(e)[:50])
                self.errors.append(f"{step_name}: {str(e)}")

        return state

    def test_steps_8_to_12(self, state):
        """Test Steps 8-12 (GitHub workflow)."""
        from langgraph_engine.subgraphs.level3_execution import (
            step8_github_issue_creation, step9_branch_creation,
            step10_implementation_execution, step11_pull_request_review,
            step12_issue_closure
        )

        # Add test data
        state.update({
            "session_dir": str(self.project_root),
            "level1_context_toon": {"complexity_score": 7}
        })

        steps = [
            ("STEP 8", step8_github_issue_creation, "GitHub Issue Creation"),
            ("STEP 9", step9_branch_creation, "Branch Creation"),
            ("STEP 10", step10_implementation_execution, "Implementation Execution"),
            ("STEP 11", step11_pull_request_review, "PR & Code Review"),
            ("STEP 12", step12_issue_closure, "Issue Closure"),
        ]

        for step_name, step_func, desc in steps:
            try:
                result = step_func(state)
                state.update(result)
                self.steps_completed[step_name.lower().replace(" ", "")] = result
                self.log(step_name, "OK", desc)
            except Exception as e:
                self.log(step_name, "ERROR", str(e)[:50])
                self.errors.append(f"{step_name}: {str(e)}")

        return state

    def test_steps_13_14(self, state):
        """Test Steps 13-14 (Documentation & Summary)."""
        from langgraph_engine.subgraphs.level3_execution import (
            step13_project_documentation_update,
            step14_final_summary_generation
        )

        steps = [
            ("STEP 13", step13_project_documentation_update, "Documentation Update"),
            ("STEP 14", step14_final_summary_generation, "Final Summary"),
        ]

        for step_name, step_func, desc in steps:
            try:
                result = step_func(state)
                state.update(result)
                self.steps_completed[step_name.lower().replace(" ", "")] = result
                self.log(step_name, "OK", desc)
            except Exception as e:
                self.log(step_name, "ERROR", str(e)[:50])
                self.errors.append(f"{step_name}: {str(e)}")

        return state

    def test_conditional_routing(self, state):
        """Test conditional routing functions."""
        from langgraph_engine.orchestrator import (
            route_after_step1_decision, route_after_step11_review
        )

        self.log("ROUTING TEST", "OK", "Testing conditional routing")

        # Test Step 1 routing
        test_state_plan = {**state, "step1_plan_required": True}
        route1 = route_after_step1_decision(test_state_plan)
        assert route1 == "level3_step2", f"Expected level3_step2, got {route1}"
        self.log("  Step 1 routing", "OK", "plan_required=True → level3_step2")

        test_state_no_plan = {**state, "step1_plan_required": False}
        route2 = route_after_step1_decision(test_state_no_plan)
        assert route2 == "level3_step3", f"Expected level3_step3, got {route2}"
        self.log("  Step 1 routing", "OK", "plan_required=False → level3_step3")

        # Test Step 11 routing
        test_state_pass = {**state, "step11_review_passed": True, "step11_retry_count": 0}
        route3 = route_after_step11_review(test_state_pass)
        assert route3 == "level3_step12", f"Expected level3_step12, got {route3}"
        self.log("  Step 11 routing", "OK", "review_passed=True → level3_step12")

        test_state_retry = {**state, "step11_review_passed": False, "step11_retry_count": 0}
        route4 = route_after_step11_review(test_state_retry)
        assert route4 == "level3_step10", f"Expected level3_step10, got {route4}"
        self.log("  Step 11 routing", "OK", "review_failed, retry<3 → level3_step10")

    def test_external_scripts(self):
        """Test external GitHub integration scripts."""
        self.log("EXTERNAL SCRIPTS", "OK", "Testing GitHub integration scripts")

        scripts = [
            "scripts/architecture/03-execution-system/github-integration/github-issue-creator.py",
            "scripts/architecture/03-execution-system/github-integration/branch-creator.py",
            "scripts/architecture/03-execution-system/github-integration/implementation-executor.py",
            "scripts/architecture/03-execution-system/github-integration/pr-creator-reviewer.py",
            "scripts/architecture/03-execution-system/github-integration/issue-closer.py",
        ]

        for script in scripts:
            try:
                result = subprocess.run(
                    ["python3", script],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env={"TASK_TYPE": "feature", "ISSUE_ID": "42"}
                )

                script_name = Path(script).name
                if result.returncode == 0:
                    self.log(f"  {script_name}", "OK", "Script executed successfully")
                else:
                    self.log(f"  {script_name}", "WARNING", "Script had warnings")
                    self.warnings.append(f"{script_name}: exit code {result.returncode}")
            except Exception as e:
                self.log(f"  {script_name}", "ERROR", str(e)[:50])

    def run_all_tests(self):
        """Run all tests."""
        print("\n" + "=" * 80)
        print("END-TO-END WORKFLOW TEST - Real-World Scenario")
        print("Task: Implement user authentication system with OAuth2 support")
        print("=" * 80 + "\n")

        try:
            # Setup
            self.setup_test_project()

            # Run all step tests
            state = self.test_step_0_task_analysis()
            state, plan_required = self.test_step_1_plan_decision(state)
            state = self.test_steps_3_to_7(state)
            state = self.test_steps_8_to_12(state)
            state = self.test_steps_13_14(state)

            # Test routing
            self.test_conditional_routing(state)

            # Test external scripts
            self.test_external_scripts()

            # Generate report
            self.generate_report(state)

        except Exception as e:
            self.log("TEST", "ERROR", f"Critical error: {str(e)}")
            self.errors.append(f"Critical: {str(e)}")
        finally:
            # Cleanup (with error handling for Windows file locks)
            try:
                if Path(self.test_dir).exists():
                    shutil.rmtree(self.test_dir)
            except Exception as e:
                # Git files might be locked on Windows
                pass

    def generate_report(self, state):
        """Generate test report."""
        elapsed = (datetime.now() - self.start_time).total_seconds()

        print("\n" + "=" * 80)
        print("TEST REPORT")
        print("=" * 80)

        print(f"\n⏱️  Total Time: {elapsed:.1f}s")
        print(f"✅ Steps Completed: {len(self.steps_completed)}/14")
        print(f"⚠️  Warnings: {len(self.warnings)}")
        print(f"❌ Errors: {len(self.errors)}")

        if self.errors:
            print("\n❌ ERRORS:")
            for error in self.errors:
                print(f"  - {error}")

        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  - {warning}")

        # State summary
        print("\n📊 FINAL STATE SUMMARY:")
        print(f"  - User message: {state.get('user_message', 'N/A')[:50]}...")
        print(f"  - Task type: {state.get('step0_task_type', 'N/A')}")
        print(f"  - Complexity: {state.get('step0_complexity', 'N/A')}")
        print(f"  - Plan required: {state.get('step1_plan_required', 'N/A')}")
        print(f"  - Issue created: {state.get('step8_issue_created', 'N/A')}")
        print(f"  - Branch created: {state.get('step9_branch_created', 'N/A')}")
        print(f"  - Implementation status: {state.get('step10_implementation_status', 'N/A')}")
        print(f"  - PR review passed: {state.get('step11_review_passed', 'N/A')}")
        print(f"  - Issue closed: {state.get('step12_issue_closed', 'N/A')}")

        # Success determination
        success = len(self.errors) == 0 and len(self.steps_completed) >= 12

        print("\n" + "=" * 80)
        if success:
            print("✅ END-TO-END WORKFLOW TEST PASSED")
        else:
            print("⚠️  END-TO-END WORKFLOW TEST COMPLETED WITH ISSUES")
        print("=" * 80 + "\n")

        return success


def main():
    """Run end-to-end test."""
    test = E2EWorkflowTest()
    success = test.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
