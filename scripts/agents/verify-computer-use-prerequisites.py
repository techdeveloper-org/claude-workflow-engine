#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pre-Flight Verification for Computer Use E2E Testing

Checks that ALL prerequisites are met before running Computer Use tests:
1. All 25 policies execute successfully
2. Output files saved to correct locations
3. Dashboard reads and displays data correctly
4. Data flow integrity verified
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple


class PreFlightChecker:
    """Verify Computer Use testing prerequisites"""

    def __init__(self):
        self.memory_base = Path.home() / ".claude" / "memory"
        self.logs_dir = self.memory_base / "logs"
        self.results: List[Tuple[str, bool, str]] = []

    def check(self, name: str, condition: bool, details: str = ""):
        """Record a check result"""
        status = "[OK]" if condition else "[FAIL]"
        self.results.append((name, condition, details))
        print(f"{status} {name}")
        if details:
            print(f"   {details}")

    def verify_policy_execution(self) -> bool:
        """Check that all 25 policies executed successfully"""
        print("\n=== 1. POLICY EXECUTION CHECK ===\n")

        # Get latest session with valid flow-trace
        sessions_dir = self.logs_dir / "sessions"
        if not sessions_dir.exists():
            self.check("Sessions directory", False, "No sessions directory found")
            return False

        latest_session = None

        # Look for the most recent session with a valid flow-trace.json containing steps
        for session_dir in sorted(sessions_dir.iterdir(), reverse=True):
            if not session_dir.is_dir():
                continue
            flow_trace = session_dir / "flow-trace.json"
            if not flow_trace.exists():
                continue
            try:
                with open(flow_trace) as f:
                    data = json.load(f)
                pipeline = data.get("pipeline", [])
                if len(pipeline) > 0:
                    latest_session = session_dir
                    break
            except Exception:
                continue

        if not latest_session:
            self.check("Latest session found", False, "No recent sessions with flow data")
            return False

        flow_trace = latest_session / "flow-trace.json"

        try:
            with open(flow_trace) as f:
                data = json.load(f)

            pipeline = data.get("pipeline", [])
            total_steps = len(pipeline)
            passed_steps = sum(1 for step in pipeline if step.get("status") == "PASSED")
            failed_steps = sum(1 for step in pipeline if step.get("status") == "FAILED")

            self.check("Flow trace structure", total_steps > 0, f"Pipeline has {total_steps} steps")

            self.check("All 25 policies present", total_steps == 25, f"Found {total_steps}/25 steps")

            self.check(
                "All policies PASSED", passed_steps == total_steps, f"{passed_steps} passed, {failed_steps} failed"
            )

            return passed_steps == total_steps

        except Exception as e:
            self.check("Parse flow trace", False, str(e))
            return False

    def verify_output_files(self) -> bool:
        """Check that all required output files exist and are recent"""
        print("\n=== 2. OUTPUT FILES CHECK ===\n")

        checks_passed = True

        # Check policy-hits.log
        policy_log = self.logs_dir / "policy-hits.log"
        if policy_log.exists():
            size = policy_log.stat().st_size
            self.check("policy-hits.log", size > 0, f"Size: {size} bytes")
        else:
            self.check("policy-hits.log", False, "File not found")
            checks_passed = False

        # Check session-progress.json
        progress_file = self.logs_dir / "session-progress.json"
        if progress_file.exists():
            try:
                with open(progress_file) as f:
                    data = json.load(f)
                self.check("session-progress.json", True, f"Tasks created: {data.get('tasks_created', 0)}")
            except Exception as e:
                self.check("session-progress.json", False, str(e))
                checks_passed = False
        else:
            self.check("session-progress.json", False, "File not found")
            checks_passed = False

        # Check for recent task-breakdown flags
        sessions_dir = self.logs_dir / "sessions"
        flags_found = 0
        if sessions_dir.exists():
            for session_dir in sessions_dir.iterdir():
                flag_file = session_dir / "flags" / "task-breakdown-pending.json"
                if flag_file.exists():
                    flags_found += 1

        self.check("Task breakdown flags", flags_found > 0, f"Found {flags_found} active enforcement flags")

        return checks_passed

    def verify_dashboard(self) -> bool:
        """Check that Flask dashboard is accessible and working"""
        print("\n=== 3. DASHBOARD CHECK ===\n")

        dashboard_url = "http://localhost:5000"
        checks_passed = True

        # Check if dashboard is running
        try:
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", dashboard_url],
                capture_output=True,
                timeout=5,
                text=True,
            )
            status_code = result.stdout.strip()
            dashboard_up = status_code.startswith("2") or status_code.startswith("3")

            self.check("Dashboard running", dashboard_up, f"HTTP {status_code}")

            if not dashboard_up:
                checks_passed = False

        except Exception as e:
            self.check("Dashboard running", False, str(e))
            checks_passed = False

        # Check sessions API
        try:
            result = subprocess.run(
                ["curl", "-s", f"{dashboard_url}/api/3level-flow/sessions"], capture_output=True, timeout=5, text=True
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                session_count = len(data.get("sessions", []))
                self.check("Dashboard /api/3level-flow/sessions", session_count > 0, f"Sessions found: {session_count}")
            else:
                self.check("Dashboard /api/3level-flow/sessions", False, "API call failed")
                checks_passed = False

        except Exception as e:
            self.check("Dashboard /api/3level-flow/sessions", False, str(e))
            checks_passed = False

        return checks_passed

    def verify_data_freshness(self) -> bool:
        """Check that data is recent (created within last hour)"""
        print("\n=== 4. DATA FRESHNESS CHECK ===\n")

        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        flow_trace_recent = False
        sessions_dir = self.logs_dir / "sessions"

        if sessions_dir.exists():
            for session_dir in sessions_dir.iterdir():
                flow_trace = session_dir / "flow-trace.json"
                if flow_trace.exists():
                    mtime = datetime.fromtimestamp(flow_trace.stat().st_mtime)
                    if mtime > one_hour_ago:
                        flow_trace_recent = True
                        self.check("Recent flow-trace.json", True, f"Modified: {mtime.strftime('%H:%M:%S')}")
                        break

        if not flow_trace_recent:
            self.check("Recent flow-trace.json", False, "No recent session traces found")

        return flow_trace_recent

    def run_all_checks(self) -> bool:
        """Run all pre-flight checks"""
        print("=" * 70)
        print("COMPUTER USE E2E TESTING - PRE-FLIGHT VERIFICATION")
        print("=" * 70)

        checks = [
            self.verify_policy_execution,
            self.verify_output_files,
            self.verify_dashboard,
            self.verify_data_freshness,
        ]

        all_passed = all(check() for check in checks)

        print("\n" + "=" * 70)
        print("VERIFICATION SUMMARY")
        print("=" * 70)

        passed = sum(1 for _, result, _ in self.results if result)
        total = len(self.results)

        print(f"\nChecks Passed: {passed}/{total}")

        if all_passed:
            print("\n[OK] ALL PRE-FLIGHT CHECKS PASSED!")
            print("\n[launch] Ready to run Computer Use tests:")
            print("   python scripts/agents/computer-use-agent.py --run-tests")
        else:
            print("\n[FAIL] SOME CHECKS FAILED")
            print("\n[WARN]  Computer Use testing is NOT READY")
            print("\nFailed checks:")
            for name, result, details in self.results:
                if not result:
                    print(f"   - {name}")
                    if details:
                        print(f"     {details}")

        return all_passed


def main():
    """Entry point"""
    checker = PreFlightChecker()
    success = checker.run_all_checks()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
