#!/usr/bin/env python3
"""
Implementation Helpers for Architecture Gap Fixes
Simplifies Phase 1, 2, 3 implementations
"""

import json
from datetime import datetime
from typing import TypedDict, Optional, List
from pathlib import Path


# ============================================================================
# PHASE 1: ERROR INFRASTRUCTURE
# ============================================================================

class ErrorLog:
    """Unified error logging system"""

    def __init__(self, session_id: str, log_dir: str = "~/.claude/logs"):
        self.session_id = session_id
        self.log_dir = Path(log_dir).expanduser() / "sessions" / session_id
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.error_file = self.log_dir / "errors.log"
        self.decision_file = self.log_dir / "decisions.log"
        self.metrics_file = self.log_dir / "metrics.json"

    def log_error(self, step: str, error: str, severity: str = "ERROR"):
        """Log error with timestamp"""
        message = f"[{datetime.now().isoformat()}] [{step}] [{severity}] {error}\n"
        with open(self.error_file, "a") as f:
            f.write(message)
        print(f"❌ {step}: {error}")

    def log_decision(self, step: str, decision: str, reasoning: str):
        """Log decision point"""
        message = f"[{datetime.now().isoformat()}] [{step}] {decision}\n  Reasoning: {reasoning}\n"
        with open(self.decision_file, "a") as f:
            f.write(message)
        print(f"🔵 {step}: {decision}")

    def log_metric(self, step: str, metric_name: str, value: float):
        """Track metrics"""
        metrics = {}
        if self.metrics_file.exists():
            metrics = json.loads(self.metrics_file.read_text())

        if step not in metrics:
            metrics[step] = {}

        metrics[step][metric_name] = value
        self.metrics_file.write_text(json.dumps(metrics, indent=2))


class BackupManager:
    """Safe backup and rollback"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.backup_dir = Path("~/.claude/logs").expanduser() / "sessions" / session_id / "backup"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def backup_file(self, file_path: str, step: str):
        """Backup file before modification"""
        file_path = Path(file_path)
        backup_file = self.backup_dir / f"{step}_{file_path.name}.bak"

        if file_path.exists():
            backup_file.write_bytes(file_path.read_bytes())
            return True
        return False

    def restore_file(self, file_path: str, step: str):
        """Restore file from backup"""
        file_path = Path(file_path)
        backup_file = self.backup_dir / f"{step}_{file_path.name}.bak"

        if backup_file.exists():
            file_path.write_bytes(backup_file.read_bytes())
            return True
        return False


# ============================================================================
# PHASE 1: TOON VALIDATION
# ============================================================================

class TOONValidator:
    """TOON schema validation"""

    REQUIRED_FIELDS = [
        "session_id",
        "timestamp",
        "version",
        "complexity_score",
        "files_loaded_count",
        "context",
    ]

    OPTIONAL_FIELDS = [
        "model_preferences",
        "execution_constraints",
        "caching_metadata",
    ]

    @classmethod
    def validate(cls, toon: dict) -> tuple[bool, List[str]]:
        """Validate TOON structure"""
        errors = []

        # Check required fields
        for field in cls.REQUIRED_FIELDS:
            if field not in toon:
                errors.append(f"Missing required field: {field}")

        # Validate types
        if "complexity_score" in toon:
            if not isinstance(toon["complexity_score"], int) or not (1 <= toon["complexity_score"] <= 10):
                errors.append("complexity_score must be int between 1-10")

        if "files_loaded_count" in toon:
            if not isinstance(toon["files_loaded_count"], int):
                errors.append("files_loaded_count must be int")

        return len(errors) == 0, errors

    @classmethod
    def create_valid_toon(cls, session_id: str, complexity_score: int, files_loaded: int) -> dict:
        """Create valid TOON object"""
        return {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "complexity_score": min(max(complexity_score, 1), 10),  # Clamp 1-10
            "files_loaded_count": files_loaded,
            "context": {
                "files": [],
                "srs": False,
                "readme": False,
                "claude_md": False,
            },
            "model_preferences": {},
            "execution_constraints": {},
            "caching_metadata": {},
        }


# ============================================================================
# PHASE 1: COMPLEXITY CALCULATION
# ============================================================================

class ComplexityCalculator:
    """Calculate project complexity"""

    @staticmethod
    def calculate(project_path: str) -> int:
        """Calculate complexity score 1-10"""
        import os

        path = Path(project_path)
        if not path.exists():
            return 3  # Default for unknown

        # Count files
        py_files = len(list(path.rglob("*.py")))
        total_files = len(list(path.rglob("*")))

        # Count lines of code
        loc = 0
        for py_file in path.rglob("*.py"):
            try:
                loc += len(py_file.read_text().splitlines())
            except:
                pass

        # Calculate score
        score = 3  # Base

        if py_files < 5:
            score = 2
        elif py_files < 20:
            score = 4
        elif py_files < 50:
            score = 6
        elif py_files < 100:
            score = 7
        else:
            score = 8

        if loc < 1000:
            score = min(score, 3)
        elif loc < 5000:
            score = min(score, 6)
        else:
            score = min(score, 9)

        return min(max(score, 1), 10)

    @staticmethod
    def should_plan(complexity_score: int) -> bool:
        """Determine if planning is required"""
        if complexity_score >= 6:
            return True
        return False


# ============================================================================
# PHASE 1: CHECKPOINT SYSTEM
# ============================================================================

class CheckpointManager:
    """Save and restore execution state"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.checkpoint_dir = (
            Path("~/.claude/logs").expanduser() / "sessions" / session_id / "checkpoints"
        )
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, step: int, state: dict) -> bool:
        """Save state after step completion"""
        checkpoint_file = self.checkpoint_dir / f"step-{step:02d}.json"

        checkpoint_data = {
            "step": step,
            "timestamp": datetime.now().isoformat(),
            "state": state,
        }

        try:
            checkpoint_file.write_text(json.dumps(checkpoint_data, indent=2, default=str))
            return True
        except Exception as e:
            print(f"❌ Checkpoint save failed: {e}")
            return False

    def load_checkpoint(self, step: int) -> Optional[dict]:
        """Load state from checkpoint"""
        checkpoint_file = self.checkpoint_dir / f"step-{step:02d}.json"

        if not checkpoint_file.exists():
            return None

        try:
            data = json.loads(checkpoint_file.read_text())
            return data.get("state")
        except Exception as e:
            print(f"❌ Checkpoint load failed: {e}")
            return None

    def get_last_checkpoint(self) -> tuple[Optional[int], Optional[dict]]:
        """Get most recent checkpoint"""
        checkpoints = sorted(self.checkpoint_dir.glob("step-*.json"))

        if not checkpoints:
            return None, None

        last = checkpoints[-1]
        step = int(last.stem.split("-")[1])
        state = self.load_checkpoint(step)

        return step, state


# ============================================================================
# PHASE 2: TOKEN BUDGET
# ============================================================================

class TokenBudget:
    """Manage token budget across steps"""

    TOTAL_BUDGET = 10000

    ALLOCATIONS = {
        "step_1": 500,  # Plan decision
        "step_2": 3000,  # Plan execution (most expensive)
        "step_3": 400,  # Task breakdown
        "step_5": 500,  # Skill selection
        "step_7": 2000,  # Prompt generation
        "reserve": 2600,  # Safety buffer
    }

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.usage = {}
        self.budget_file = (
            Path("~/.claude/logs").expanduser() / "sessions" / session_id / "token_budget.json"
        )

    def can_proceed(self, step: str, estimated_tokens: int) -> bool:
        """Check if we have budget"""
        remaining = self._get_remaining_budget()
        return estimated_tokens <= remaining

    def record_usage(self, step: str, tokens_used: int):
        """Record token usage"""
        self.usage[step] = tokens_used
        self._save_budget()

    def _get_remaining_budget(self) -> int:
        """Calculate remaining tokens"""
        used = sum(self.usage.values())
        return self.TOTAL_BUDGET - used

    def _save_budget(self):
        """Save budget file"""
        data = {
            "total": self.TOTAL_BUDGET,
            "used": sum(self.usage.values()),
            "remaining": self._get_remaining_budget(),
            "usage_by_step": self.usage,
        }
        self.budget_file.parent.mkdir(parents=True, exist_ok=True)
        self.budget_file.write_text(json.dumps(data, indent=2))


# ============================================================================
# PHASE 3: METRICS & MONITORING
# ============================================================================

class MetricsCollector:
    """Collect execution metrics"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.metrics = {}
        self.metrics_file = (
            Path("~/.claude/logs").expanduser() / "sessions" / session_id / "metrics.json"
        )

    def record_step(self, step: int, duration: float, status: str, tokens: int = 0):
        """Record step execution metrics"""
        self.metrics[f"step_{step}"] = {
            "duration_seconds": duration,
            "status": status,  # "SUCCESS", "FAILED", "SKIPPED"
            "tokens_used": tokens,
            "timestamp": datetime.now().isoformat(),
        }
        self._save()

    def summary(self) -> dict:
        """Get execution summary"""
        total_time = sum(m.get("duration_seconds", 0) for m in self.metrics.values())
        total_tokens = sum(m.get("tokens_used", 0) for m in self.metrics.values())
        successful = sum(1 for m in self.metrics.values() if m.get("status") == "SUCCESS")

        return {
            "total_time_seconds": total_time,
            "total_tokens": total_tokens,
            "successful_steps": successful,
            "total_steps": len(self.metrics),
            "success_rate": successful / len(self.metrics) if self.metrics else 0,
        }

    def _save(self):
        """Save metrics to file"""
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        self.metrics_file.write_text(json.dumps(self.metrics, indent=2))


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    # Example 1: Error logging
    print("=" * 60)
    print("EXAMPLE 1: Error Logging")
    print("=" * 60)

    error_log = ErrorLog("session-20260313-001")
    error_log.log_decision("Step 1", "Plan Required", "Complexity score 7 >= threshold 6")
    error_log.log_metric("Step 2", "tokens_used", 450)
    error_log.log_error("Step 6", "Network timeout", severity="WARNING")

    # Example 2: TOON validation
    print("\n" + "=" * 60)
    print("EXAMPLE 2: TOON Validation")
    print("=" * 60)

    toon = TOONValidator.create_valid_toon(
        session_id="session-20260313-001", complexity_score=7, files_loaded=3
    )
    is_valid, errors = TOONValidator.validate(toon)
    print(f"TOON valid: {is_valid}")
    print(f"TOON: {json.dumps(toon, indent=2)}")

    # Example 3: Complexity calculation
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Complexity Calculation")
    print("=" * 60)

    complexity = ComplexityCalculator.calculate(".")
    should_plan = ComplexityCalculator.should_plan(complexity)
    print(f"Project complexity: {complexity}/10")
    print(f"Plan required: {should_plan}")

    # Example 4: Checkpointing
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Checkpointing")
    print("=" * 60)

    checkpoint = CheckpointManager("session-20260313-001")
    checkpoint.save_checkpoint(
        1, {"toon": toon, "decision": "planning_required", "status": "complete"}
    )
    loaded = checkpoint.load_checkpoint(1)
    print(f"Saved checkpoint step 1: {loaded is not None}")

    # Example 5: Token budget
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Token Budget")
    print("=" * 60)

    budget = TokenBudget("session-20260313-001")
    can_proceed = budget.can_proceed("step_2", 2500)
    print(f"Can proceed with 2500 tokens for step_2: {can_proceed}")
    budget.record_usage("step_1", 450)
    budget.record_usage("step_2", 2100)

    # Example 6: Metrics
    print("\n" + "=" * 60)
    print("EXAMPLE 6: Metrics Collection")
    print("=" * 60)

    metrics = MetricsCollector("session-20260313-001")
    metrics.record_step(1, 2.5, "SUCCESS", 450)
    metrics.record_step(2, 45.3, "SUCCESS", 2100)
    metrics.record_step(3, 5.2, "SUCCESS", 300)

    summary = metrics.summary()
    print(f"Summary: {json.dumps(summary, indent=2)}")

    print("\n✅ All examples completed!")
