#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Policy Tracker - Track detailed execution of all policies

This utility tracks every policy execution across all levels with:
- Input parameters
- Output results
- Decisions made
- Sub-operations
- Timing information
- Complete audit trail

Version: 1.0.0
Last Modified: 2026-03-05
Windows-Safe: No Unicode chars (ASCII only, cp1252 compatible)
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Windows-safe encoding
if sys.platform == 'win32':
    import io
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# File locking for shared JSON state
try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


class PolicyTracker:
    """
    Track detailed policy execution data for audit trails and flow tracing.

    Maintains comprehensive records of:
    - Each policy's input parameters
    - Each policy's output results
    - Decisions made by each policy
    - Sub-operations within policies
    - Execution timing (milliseconds)
    - Policy sequencing across levels
    """

    def __init__(self, session_id: str):
        """
        Initialize PolicyTracker for a session.

        Args:
            session_id (str): Unique session identifier (SESSION-...)
        """
        self.session_id = session_id
        self.session_dir = Path.home() / '.claude' / 'memory' / 'logs' / 'sessions' / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.flow_trace_file = self.session_dir / 'flow-trace.json'
        self.policies_executed = []
        self.current_level = None
        self.level_start_time = None
        self.level_policies = []

    def start_level(self, level: int, level_name: str):
        """
        Mark the start of a new execution level.

        Args:
            level (int): Level number (-1, 1, 2, 3)
            level_name (str): Human-readable level name
        """
        self.current_level = level
        self.level_name = level_name
        self.level_start_time = datetime.now()
        self.level_policies = []

    def record_policy_execution(
        self,
        policy_name: str,
        policy_script: str,
        policy_type: str,
        input_params: Dict[str, Any],
        output_results: Dict[str, Any],
        decision: str,
        duration_ms: int,
        sub_operations: Optional[List[Dict]] = None
    ):
        """
        Record a complete policy execution with all details.

        Args:
            policy_name (str): Name of policy (e.g., 'session-id-generator')
            policy_script (str): Script filename that enforced policy
            policy_type (str): Type (e.g., 'Policy Script', 'Utility Hook')
            input_params (dict): Input parameters passed to policy
            output_results (dict): Results returned by policy
            decision (str): Human-readable decision made
            duration_ms (int): Execution time in milliseconds
            sub_operations (list, optional): List of sub-operations
        """
        policy_record = {
            "order": len(self.level_policies) + 1,
            "policy_name": policy_name,
            "policy_script": policy_script,
            "policy_type": policy_type,
            "level": self.current_level,
            "timestamp": datetime.now().isoformat(),
            "duration_ms": duration_ms,
            "input": input_params,
            "output": output_results,
            "decision": decision
        }

        if sub_operations:
            policy_record["sub_operations"] = sub_operations

        self.level_policies.append(policy_record)
        self.policies_executed.append(policy_record)

    def record_sub_operation(
        self,
        operation_name: str,
        input_params: Dict[str, Any],
        output_results: Dict[str, Any],
        duration_ms: int
    ) -> Dict[str, Any]:
        """
        Record a sub-operation within a policy.

        Args:
            operation_name (str): Name of sub-operation
            input_params (dict): Operation input
            output_results (dict): Operation output
            duration_ms (int): Operation duration

        Returns:
            dict: Sub-operation record
        """
        sub_op = {
            "operation": operation_name,
            "timestamp": datetime.now().isoformat(),
            "duration_ms": duration_ms,
            "input": input_params,
            "output": output_results
        }
        return sub_op

    def finalize_level(self) -> Dict[str, Any]:
        """
        Finalize a level's execution and calculate totals.

        Returns:
            dict: Level summary with all policies
        """
        if not self.level_start_time:
            return {}

        level_duration_ms = int((datetime.now() - self.level_start_time).total_seconds() * 1000)

        level_record = {
            "level": self.current_level,
            "level_name": self.level_name,
            "timestamp": self.level_start_time.isoformat(),
            "duration_ms": level_duration_ms,
            "policies_executed_count": len(self.level_policies),
            "policies_executed": self.level_policies
        }

        return level_record

    def generate_flow_trace(self, meta: Dict[str, Any], user_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate complete flow-trace.json structure.

        Args:
            meta (dict): Metadata (version, session_id, timing)
            user_input (dict): User prompt and metadata

        Returns:
            dict: Complete flow-trace JSON structure
        """
        flow_trace = {
            "meta": meta,
            "user_input": user_input,
            "policies_by_level": {},
            "all_policies_executed": [],
            "execution_summary": {
                "total_policies_executed": len(self.policies_executed),
                "total_duration_ms": sum(p.get("duration_ms", 0) for p in self.policies_executed),
                "slowest_policies": self._get_slowest_policies(5),
                "fastest_policies": self._get_fastest_policies(5)
            },
            "decisions_timeline": self._get_decisions_timeline()
        }

        # Organize by level
        for level in [-1, 1, 2, 3]:
            level_policies = [p for p in self.policies_executed if p.get("level") == level]
            if level_policies:
                flow_trace["policies_by_level"][f"level_{level}"] = level_policies

        flow_trace["all_policies_executed"] = self.policies_executed

        return flow_trace

    def _get_slowest_policies(self, count: int) -> List[Dict]:
        """Get slowest executing policies."""
        sorted_policies = sorted(
            self.policies_executed,
            key=lambda p: p.get("duration_ms", 0),
            reverse=True
        )
        return sorted_policies[:count]

    def _get_fastest_policies(self, count: int) -> List[Dict]:
        """Get fastest executing policies."""
        sorted_policies = sorted(
            self.policies_executed,
            key=lambda p: p.get("duration_ms", 0)
        )
        return sorted_policies[:count]

    def _get_decisions_timeline(self) -> List[Dict]:
        """Get chronological timeline of all decisions."""
        timeline = []
        for policy in self.policies_executed:
            timeline.append({
                "timestamp": policy.get("timestamp"),
                "level": policy.get("level"),
                "policy": policy.get("policy_name"),
                "decision": policy.get("decision")
            })
        return timeline

    def save_flow_trace(self, flow_trace: Dict[str, Any]):
        """
        Save flow-trace.json to disk.

        Args:
            flow_trace (dict): Complete flow-trace structure
        """
        try:
            self.flow_trace_file.write_text(
                json.dumps(flow_trace, indent=2),
                encoding='utf-8'
            )
        except Exception as e:
            print(f"[ERROR] Failed to save flow-trace.json: {e}")

    def load_flow_trace(self) -> Optional[Dict[str, Any]]:
        """
        Load existing flow-trace.json from disk.

        Returns:
            dict: Existing flow-trace or None
        """
        if not self.flow_trace_file.exists():
            return None

        try:
            return json.loads(
                self.flow_trace_file.read_text(encoding='utf-8')
            )
        except Exception as e:
            print(f"[ERROR] Failed to load flow-trace.json: {e}")
            return None

    def append_policy_to_trace(self, policy_record: Dict[str, Any]):
        """
        Append a policy execution to existing flow-trace.

        Args:
            policy_record (dict): Policy execution record
        """
        flow_trace = self.load_flow_trace()
        if not flow_trace:
            return

        if "all_policies_executed" not in flow_trace:
            flow_trace["all_policies_executed"] = []

        flow_trace["all_policies_executed"].append(policy_record)

        # Update summary
        flow_trace["execution_summary"]["total_policies_executed"] = len(
            flow_trace["all_policies_executed"]
        )

        self.save_flow_trace(flow_trace)


def example_usage():
    """Example of how to use PolicyTracker."""
    tracker = PolicyTracker("SESSION-20260305-180752-DR8R")

    # Level -1: Auto-Fix
    tracker.start_level(-1, "Auto-Fix Enforcement")

    sub_ops = [
        tracker.record_sub_operation(
            operation_name="check_python_available",
            input_params={"required_version": "3.8+"},
            output_results={"found": True, "version": "3.9.0"},
            duration_ms=20
        ),
        tracker.record_sub_operation(
            operation_name="check_critical_files",
            input_params={"files": ["3-level-flow.py", "session-id-generator.py"]},
            output_results={"all_found": True},
            duration_ms=25
        )
    ]

    tracker.record_policy_execution(
        policy_name="auto-fix-enforcer",
        policy_script="auto-fix-enforcer.py",
        policy_type="Level -1 Hook",
        input_params={"trigger": "user_prompt_received"},
        output_results={"status": "SUCCESS", "checks_passed": 7},
        decision="PROCEED - All systems operational",
        duration_ms=145,
        sub_operations=sub_ops
    )

    print("[OK] Policy tracking example complete")


if __name__ == "__main__":
    example_usage()
