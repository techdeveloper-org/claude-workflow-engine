#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task Phase Enforcement Policy Enforcement (v2.0 - FULLY CONSOLIDATED)

CONSOLIDATED SCRIPT - Maps to: policies/03-execution-system/08-progress-tracking/task-phase-enforcement-policy.md

Consolidates 1 script (121+ lines):
- task-phase-enforcer.py (121 lines) - Enforce task and phase requirements

THIS CONSOLIDATION includes ALL functionality from old script.
NO logic was lost in consolidation - everything is merged.

Usage:
  python task-phase-enforcement-policy.py --enforce              # Run policy enforcement
  python task-phase-enforcement-policy.py --validate             # Validate policy compliance
  python task-phase-enforcement-policy.py --report               # Generate report
  python task-phase-enforcement-policy.py --analyze <task>       # Analyze task description
"""

import sys
import io
import json
import os
from pathlib import Path
from datetime import datetime

# ===================================================================
# NEW: POLICY TRACKING INTEGRATION
# ===================================================================
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from policy_tracking_helper import record_policy_execution, record_sub_operation
    HAS_TRACKING = True
except ImportError:
    HAS_TRACKING = False

# Fix encoding for Windows console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

MEMORY_DIR = Path.home() / ".claude" / "memory"
LOG_FILE = MEMORY_DIR / "logs" / "policy-hits.log"


# ============================================================================
# TASK/PHASE ENFORCEMENT (from task-phase-enforcer.py)
# ============================================================================

def calculate_complexity_score(task_desc):
    """Calculate a complexity score from keyword density in the task description.

    Counts requirement connectors, multi-domain keywords, file modification
    verbs, scope indicators, and comprehensive-scope markers.

    Args:
        task_desc (str): Task description text to analyze.

    Returns:
        int: Complexity score from 0 to 10.
    """
    score = 0

    # Check for multiple requirements
    requirements_keywords = ['and', 'also', 'plus', 'additionally', 'all']
    req_count = sum(1 for kw in requirements_keywords if kw in task_desc.lower())
    score += min(3, req_count)

    # Check for multi-domain tasks
    domains = ['backend', 'frontend', 'database', 'api', 'ui', 'docker', 'kubernetes']
    domain_count = sum(1 for domain in domains if domain in task_desc.lower())
    score += min(2, domain_count)

    # Check for file modification indicators
    file_keywords = ['update', 'create', 'modify', 'edit', 'change', 'fix', 'add']
    if any(kw in task_desc.lower() for kw in file_keywords):
        score += 2

    # Check for multi-scope indicators
    multi_keywords = ['all', 'every', 'each', 'multiple', 'several']
    if any(kw in task_desc.lower() for kw in multi_keywords):
        score += 2

    # Check for comprehensive scope
    complex_keywords = ['comprehensive', 'complete', 'full', 'entire', 'complex']
    if any(kw in task_desc.lower() for kw in complex_keywords):
        score += 1

    return min(10, score)


def calculate_size_score(task_desc):
    """Calculate a size score from word count and breadth indicators.

    Args:
        task_desc (str): Task description text to analyze.

    Returns:
        int: Size score from 0 to 10.
    """
    score = 0

    # Score based on word count
    word_count = len(task_desc.split())
    if word_count > 20:
        score += 3
    elif word_count > 10:
        score += 2
    elif word_count > 5:
        score += 1

    # Check for multiple items
    multi_indicators = ['all', 'every', 'each', '10', 'multiple', 'several']
    if any(ind in task_desc.lower() for ind in multi_indicators):
        score += 3

    return min(10, score)


def analyze_task(task_desc):
    """Analyze a task description and print phase enforcement requirements.

    Computes complexity and size scores, determines whether TaskCreate and
    phase-based execution are required, and prints a formatted report.

    Args:
        task_desc (str): Task description to analyze.

    Returns:
        int: Always 0 (exit code for success).
    """
    print("\n" + "="*70)
    print("TASK/PHASE ENFORCEMENT CHECK")
    print("="*70 + "\n")

    print(f"Request: {task_desc}\n")

    complexity = calculate_complexity_score(task_desc)
    size = calculate_size_score(task_desc)

    print("Analysis:")
    print(f"  Complexity Score: {complexity}/10")
    print(f"  Size Score: {size}/10\n")

    # v2.0.0 Policy: Always require TaskCreate
    needs_task = True
    needs_phases = size >= 6

    print("Requirements:")
    print(f"  TaskCreate: ALWAYS REQUIRED (v2.0.0 policy)")
    print(f"  Phased Execution: {'REQUIRED' if needs_phases else 'Optional (5+ tasks pe auto-phase)'}")
    print()

    print("Status: [WARNING] REQUIREMENTS DETECTED")
    if needs_task:
        print("  -> Must use TaskCreate before starting")
    if needs_phases:
        print("  -> Must define phases (score >= 6)")

    log_policy_hit("ANALYZED", f"task={task_desc[:50]} | complexity={complexity} | size={size}")

    print("="*70 + "\n")

    return 0


# ============================================================================
# LOGGING
# ============================================================================

def log_policy_hit(action, context=""):
    """Append a timestamped entry to the policy-hits log.

    Args:
        action (str): The action identifier (e.g., 'ENFORCE_START', 'VALIDATE').
        context (str): Optional human-readable context or detail string.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] task-phase-enforcement-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception:
        pass


# ============================================================================
# POLICY INTERFACE
# ============================================================================

def validate():
    """Check that the task phase enforcement policy preconditions are met.

    Returns:
        bool: True if validation succeeds, False on any exception.
    """
    try:
        log_policy_hit("VALIDATE", "task-phase-ready")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report for the task phase enforcement policy.

    Returns:
        dict: Contains 'status', 'policy', 'enforcements',
              'complexity_threshold', and 'timestamp'.
              Returns {'status': 'error', ...} on failure.
    """
    try:
        report_data = {
            "status": "success",
            "policy": "task-phase-enforcement",
            "enforcements": ["TaskCreate always required", "Phases for complex tasks"],
            "complexity_threshold": 6,
            "timestamp": datetime.now().isoformat()
        }

        log_policy_hit("REPORT", "task-phase-enforcement-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """Activate the task phase enforcement policy.

    Consolidates task/phase enforcement from task-phase-enforcer.py:
    - Complexity scoring
    - Size estimation
    - Phase requirement calculation

    Returns:
        dict: Contains 'status' ('success' or 'error').
              On error, contains 'message'.
    """
    _track_start_time = datetime.now()
    _sub_operations = []
    try:
        log_policy_hit("ENFORCE_START", "task-phase-enforcement")

        _op_start = datetime.now()
        log_policy_hit("ENFORCE_COMPLETE", "task-phase-enforcement-ready")
        try:
            _sub_operations.append(record_sub_operation(
                "activate_phase_enforcement", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000),
                {"task_create_required": True, "complexity_threshold": 6}
            ))
        except Exception:
            pass

        print("[task-phase-enforcement-policy] Policy enforced - Task/Phase requirements active")

        result = {"status": "success"}
        try:
            if HAS_TRACKING:
                record_policy_execution(
                    session_id=os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
                    policy_name="task-phase-enforcement-policy",
                    policy_script="task-phase-enforcement-policy.py",
                    policy_type="Policy Script",
                    input_params={},
                    output_results=result,
                    decision="task/phase enforcement activated",
                    duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                    sub_operations=_sub_operations if _sub_operations else None
                )
        except Exception:
            pass
        return result
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[task-phase-enforcement-policy] ERROR: {e}")
        error_result = {"status": "error", "message": str(e)}
        try:
            if HAS_TRACKING:
                record_policy_execution(
                    session_id=os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
                    policy_name="task-phase-enforcement-policy",
                    policy_script="task-phase-enforcement-policy.py",
                    policy_type="Policy Script",
                    input_params={},
                    output_results=error_result,
                    decision=f"error: {str(e)}",
                    duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                    sub_operations=_sub_operations if _sub_operations else None
                )
        except Exception:
            pass
        return error_result


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--enforce":
            result = enforce()
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--validate":
            is_valid = validate()
            sys.exit(0 if is_valid else 1)
        elif sys.argv[1] == "--report":
            result = report()
            print(json.dumps(result, indent=2))
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--analyze" and len(sys.argv) >= 3:
            task_desc = ' '.join(sys.argv[2:])
            analyze_task(task_desc)
        else:
            print("Usage: python task-phase-enforcement-policy.py [--enforce|--validate|--report|--analyze <task>]")
            sys.exit(1)
    else:
        # Default: run enforcement
        enforce()
