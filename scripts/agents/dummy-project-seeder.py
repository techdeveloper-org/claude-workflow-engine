#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dummy Project Data Seeder for Computer Use E2E Testing

Creates 10 realistic sessions representing a complete project lifecycle,
all seeded without needing real hooks or API calls.

Sessions simulate:
  1. Initial project setup
  2. Create user auth API
  3. Add login page UI
  4. Fix login bug on mobile
  5. Refactor DB models
  6. Add unit tests
  7. Commit and push changes
  8. Deploy to docker
  9. Optimize API performance
 10. Update documentation
"""

import json
import random
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict


class DummyProjectSeeder:
    """Seed dummy project data for E2E testing"""

    def __init__(self):
        self.memory_base = Path.home() / ".claude" / "memory"
        self.logs_dir = self.memory_base / "logs"
        self.sessions_dir = self.logs_dir / "sessions"
        self.sessions_created = 0

        # Ensure directories exist
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def generate_session_id(self) -> str:
        """Generate a unique session ID like SESSION-20260308-182033-HH2N"""
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        random_suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"SESSION-{timestamp}-{random_suffix}"

    def create_flow_trace(self, session_id: str, task_type: str, model: str, agent: str) -> Dict:
        """Create a complete 25-step flow-trace.json"""
        base_time = datetime.now() - timedelta(hours=random.randint(1, 24))
        end_time = base_time + timedelta(seconds=random.randint(30, 180))

        pipeline = []

        # Level -1: Auto-Fix Enforcement
        pipeline.append(
            {
                "step": "LEVEL_MINUS_1",
                "name": "Auto-Fix Enforcement",
                "level": -1,
                "order": 0,
                "is_blocking": True,
                "status": "PASSED",
                "timestamp": base_time.isoformat(),
                "duration_ms": 124,
                "policy": {
                    "script": "auto-fix-enforcer.py",
                    "version": "2.0.0",
                    "rules_applied": [
                        "check_python_available",
                        "check_critical_files_present",
                        "check_blocking_enforcer_initialized",
                        "check_session_state_valid",
                    ],
                },
                "policy_output": {
                    "exit_code": 0,
                    "status": "SUCCESS",
                    "checks": {
                        "python": "OK",
                        "critical_files": "OK",
                        "blocking_enforcer": "OK",
                        "session_state": "OK",
                    },
                },
                "decision": "PROCEED - All systems operational",
                "errors": [],
                "warnings": [],
            }
        )

        # Level 1: Sync System (Context Management + Session Management)
        level_1_steps = [
            {
                "step": "LEVEL_1_CONTEXT",
                "name": "Context Management",
                "policy": "context-monitor.py",
                "duration_ms": 89,
            },
            {
                "step": "LEVEL_1_SESSION",
                "name": "Session Management",
                "policy": "session-manager-v2.py",
                "duration_ms": 76,
            },
            {
                "step": "LEVEL_1_PATTERN",
                "name": "Pattern Detection",
                "policy": "pattern-detector.py",
                "duration_ms": 45,
            },
        ]

        for i, step_info in enumerate(level_1_steps):
            timestamp = base_time + timedelta(milliseconds=sum(s["duration_ms"] for s in pipeline))
            pipeline.append(
                {
                    "step": step_info["step"],
                    "name": step_info["name"],
                    "level": 1,
                    "order": len(pipeline),
                    "is_blocking": False,
                    "status": "PASSED",
                    "timestamp": timestamp.isoformat(),
                    "duration_ms": step_info["duration_ms"],
                    "policy": {"script": step_info["policy"], "version": "1.0.0"},
                    "policy_output": {"exit_code": 0, "status": "SUCCESS"},
                    "errors": [],
                    "warnings": [],
                }
            )

        # Level 2: Standards System (3 policies)
        level_2_steps = [
            {
                "step": "LEVEL_2_CODE_STYLE",
                "name": "Code Style Standards",
                "policy": "code-style-enforcer.py",
                "duration_ms": 134,
            },
            {
                "step": "LEVEL_2_SECURITY",
                "name": "Security Standards",
                "policy": "security-enforcer.py",
                "duration_ms": 98,
            },
            {
                "step": "LEVEL_2_DOCUMENTATION",
                "name": "Documentation Standards",
                "policy": "documentation-enforcer.py",
                "duration_ms": 67,
            },
        ]

        for step_info in level_2_steps:
            timestamp = base_time + timedelta(milliseconds=sum(s["duration_ms"] for s in pipeline))
            pipeline.append(
                {
                    "step": step_info["step"],
                    "name": step_info["name"],
                    "level": 2,
                    "order": len(pipeline),
                    "is_blocking": False,
                    "status": "PASSED",
                    "timestamp": timestamp.isoformat(),
                    "duration_ms": step_info["duration_ms"],
                    "policy": {"script": step_info["policy"], "version": "2.0.0"},
                    "policy_output": {"exit_code": 0, "status": "SUCCESS"},
                    "errors": [],
                    "warnings": [],
                }
            )

        # Level 3: Execution System (12 steps per spec)
        level_3_steps = [
            "Prompt Generation",
            "Task Breakdown",
            "Plan Mode Check",
            "Blockers Analysis",
            "Model Selection",
            "Skill/Agent Selection",
            "Tool Optimization",
            "Action Execution",
            "Response Generation",
            "Progress Tracking",
            "Git Commit Handling",
            "Session Finalization",
        ]

        for i, step_name in enumerate(level_3_steps):
            timestamp = base_time + timedelta(milliseconds=sum(s["duration_ms"] for s in pipeline))
            step_num = i + 1
            pipeline.append(
                {
                    "step": f"LEVEL_3_STEP_{step_num}",
                    "name": step_name,
                    "level": 3,
                    "order": len(pipeline),
                    "is_blocking": False,
                    "status": "PASSED",
                    "timestamp": timestamp.isoformat(),
                    "duration_ms": random.randint(50, 200),
                    "policy": {
                        "script": f"step-{step_num}-{step_name.lower().replace(' ', '-')}.py",
                        "version": "3.0.0",
                    },
                    "policy_output": {"exit_code": 0, "status": "SUCCESS"},
                    "errors": [],
                    "warnings": [],
                }
            )

        # Additional Level 3 steps (13-19: policies for execution)
        # Total: 1 + 3 + 3 + 12 + 6 = 25 steps
        execution_policies = [
            "Post-Tool Tracking",
            "Context Optimization",
            "Task State Updates",
            "Error Handling",
            "Session Chaining",
            "Final Checkpoint",
        ]

        for i, policy_name in enumerate(execution_policies):
            timestamp = base_time + timedelta(milliseconds=sum(s["duration_ms"] for s in pipeline))
            step_num = 13 + i
            pipeline.append(
                {
                    "step": f"LEVEL_3_POLICY_{step_num}",
                    "name": policy_name,
                    "level": 3,
                    "order": len(pipeline),
                    "is_blocking": False,
                    "status": "PASSED",
                    "timestamp": timestamp.isoformat(),
                    "duration_ms": random.randint(40, 150),
                    "policy": {
                        "script": f"policy-{step_num}-{policy_name.lower().replace(' ', '-')}.py",
                        "version": "3.0.0",
                    },
                    "policy_output": {"exit_code": 0, "status": "SUCCESS"},
                    "errors": [],
                    "warnings": [],
                }
            )

        return {
            "_schema_version": "2.0",
            "meta": {
                "flow_version": "5.1.0",
                "script": "3-level-flow.py",
                "mode": "standard",
                "flow_start": base_time.isoformat(),
                "flow_end": end_time.isoformat(),
                "duration_seconds": (end_time - base_time).total_seconds(),
                "session_id": session_id,
                "log_dir": str(self.sessions_dir / session_id),
                "platform": "win32",
                "python_version": "3.13.12",
                "session_status": "COMPLETED",
                "message_number": 1,
                "task_type": task_type,
                "model": model,
                "agent": agent,
                "complexity_score": random.randint(3, 9),
            },
            "user_input": {
                "prompt": f"{task_type}: Implement changes for {agent}",
                "prompt_length": 80,
                "received_at": base_time.isoformat(),
                "source": "Computer Use Test Seeder",
            },
            "pipeline": pipeline,
        }

    def create_session_summary(self, session_id: str, task_type: str, model: str, agent: str) -> Dict:
        """Create a session-summary.json"""
        return {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "task_type": task_type,
            "model": model,
            "agent": agent,
            "status": "completed",
            "policies_executed": 25,
            "policies_passed": 25,
            "policies_failed": 0,
            "success_rate": 100.0,
        }

    def seed_dummy_sessions(self) -> None:
        """Create 10 dummy sessions"""
        sessions_data = [
            ("Design", "claude-opus-4-6", "ui-ux-designer"),
            ("API Creation", "claude-sonnet-4-6", "spring-boot-microservices"),
            ("UI/UX", "claude-sonnet-4-6", "ui-ux-designer"),
            ("Bug Fix", "claude-haiku-4-5-20251001", "qa-testing-agent"),
            ("Refactoring", "claude-sonnet-4-6", "python-backend-engineer"),
            ("Testing", "claude-haiku-4-5-20251001", "qa-testing-agent"),
            ("DevOps", "claude-sonnet-4-6", "devops-engineer"),
            ("Documentation", "claude-haiku-4-5-20251001", "python-backend-engineer"),
            ("Performance", "claude-sonnet-4-6", "python-backend-engineer"),
            ("Security", "claude-opus-4-6", "qa-testing-agent"),
        ]

        for task_type, model, agent in sessions_data:
            session_id = self.generate_session_id()
            session_dir = self.sessions_dir / session_id

            # Create session directory
            session_dir.mkdir(parents=True, exist_ok=True)

            # Create flow-trace.json
            flow_trace = self.create_flow_trace(session_id, task_type, model, agent)
            flow_file = session_dir / "flow-trace.json"
            with open(flow_file, "w") as f:
                json.dump(flow_trace, f, indent=2)

            # Create session-summary.json
            summary = self.create_session_summary(session_id, task_type, model, agent)
            summary_file = session_dir / "session-summary.json"
            with open(summary_file, "w") as f:
                json.dump(summary, f, indent=2)

            # Create flags directory with task-breakdown-pending.json
            flags_dir = session_dir / "flags"
            flags_dir.mkdir(exist_ok=True)
            flag_file = flags_dir / "task-breakdown-pending.json"
            with open(flag_file, "w") as f:
                json.dump(
                    {"session_id": session_id, "created_at": datetime.now().isoformat(), "pending": True}, f, indent=2
                )

            self.sessions_created += 1
            print(f"[OK] Created session {self.sessions_created}/10: {session_id}")
            print(f"   Task: {task_type} | Model: {model} | Agent: {agent}")

        # Update or create session-progress.json
        progress_file = self.logs_dir / "session-progress.json"
        progress_data = {
            "total_sessions": self.sessions_created,
            "tasks_created": self.sessions_created,
            "tasks_completed": self.sessions_created,
            "success_rate": 100.0,
            "last_updated": datetime.now().isoformat(),
            "sessions": [s for s, _, _ in sessions_data],
        }
        with open(progress_file, "w") as f:
            json.dump(progress_data, f, indent=2)

        # Update policy-hits.log
        policy_log = self.logs_dir / "policy-hits.log"
        with open(policy_log, "a") as f:
            for i, (task_type, model, agent) in enumerate(sessions_data, 1):
                f.write(f"[{datetime.now().isoformat()}] Session {i}: {task_type} | {model} | {agent}\n")

    def run(self) -> None:
        """Main entry point"""
        print("=" * 80)
        print("DUMMY PROJECT SEEDER - Computer Use E2E Testing")
        print("=" * 80)
        print()

        self.seed_dummy_sessions()

        print()
        print("=" * 80)
        print(f"[OK] SEEDING COMPLETE: {self.sessions_created} sessions created")
        print("=" * 80)
        print()
        print("Next steps:")
        print("1. Start Flask dashboard:  python run.py")
        print("2. Run pre-flight checks:  python scripts/agents/verify-computer-use-prerequisites.py")
        print("3. Run E2E tests:          python scripts/agents/computer-use-agent.py --run-tests")
        print()


def main():
    """CLI entry point"""
    seeder = DummyProjectSeeder()
    seeder.run()


if __name__ == "__main__":
    main()
