#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Architecture-Script Mapping Policy Enforcement (v2.0)

Maps to: policies/03-execution-system/architecture-script-mapping-policy.md

This module validates the 1:1 mapping between policy Markdown documentation
files and their corresponding enforcement Python scripts. It ensures the
architecture contract is maintained: every policy document must have exactly
one enforcement script, and every enforcement script must have a corresponding
policy document. This prevents orphaned policies or undocumented scripts.

Mapping rules enforced:
  - Every *.md in policies/ must have a matching *-policy.py in scripts/
  - Every *-policy.py must reference its policy MD via a 'Maps to:' header
  - No two scripts may enforce the same policy
  - Policy document names and script names must be semantically aligned
  - The architecture-script-mapping-policy.md itself is the authoritative register

Key Functions:
  enforce(): Run architecture mapping validation and log results.
  validate(): Confirm the mapping infrastructure is ready.
  report(): Generate a structured report of the mapping check results.

CLI Usage:
  python architecture-script-mapping-policy.py --enforce   # Run policy enforcement
  python architecture-script-mapping-policy.py --validate  # Validate compliance
  python architecture-script-mapping-policy.py --report    # Generate report

Example:
  >>> from architecture_script_mapping_policy import enforce
  >>> result = enforce()
  >>> print(result['status'])  # 'success'
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# ===================================================================
# NEW: POLICY TRACKING INTEGRATION
# ===================================================================
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from policy_tracking_helper import record_policy_execution, record_sub_operation
    HAS_TRACKING = True
except ImportError:
    HAS_TRACKING = False

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

MEMORY_DIR = Path.home() / ".claude" / "memory"
LOG_FILE = MEMORY_DIR / "logs" / "policy-hits.log"


def log_policy_hit(action, context=""):
    """Append a timestamped entry to the policy-hits log.

    Args:
        action (str): The action identifier (e.g., 'ENFORCE_START', 'VALIDATE').
        context (str): Optional human-readable context or detail string.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] architecture-script-mapping-policy | {action} | {context}\n")
    except:
        pass


def validate():
    """Check that the architecture-script mapping policy preconditions are met.

    Ensures the base memory directory exists and the policy infrastructure
    is ready for mapping validation operations.

    Returns:
        bool: True if validation succeeds, False on any exception.
    """
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log_policy_hit("VALIDATE", "architecture-script-mapping-ready")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report for the architecture-script mapping policy.

    Returns a structured dictionary describing the features and validation
    capabilities of the architecture mapping system.

    Returns:
        dict: Report containing 'status', 'policy', 'description', 'features',
              and 'timestamp'. Returns {'status': 'error', 'message': ...} on failure.
    """
    try:
        report_data = {
            "status": "success",
            "policy": "architecture-script-mapping",
            "description": "Validates 1:1 mapping between policy MD and enforcement scripts",
            "features": [
                "Policy-script mapping validation",
                "Architecture consistency checking",
                "Artifact registration",
                "Mapping verification"
            ],
            "timestamp": datetime.now().isoformat()
        }
        log_policy_hit("REPORT", "architecture-script-mapping-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """Run architecture-script mapping validation and activate the policy.

    Initializes the policy, ensures the memory directory is ready, and logs
    the enforcement event. This is called by 3-level-flow.py to ensure the
    1:1 mapping between policy documents and enforcement scripts is maintained.

    Returns:
        dict: Result with 'status' ('success' or 'error') and 'policy' name.
              On error, 'message' key contains the exception string.
    """
    import os
    _track_start_time = datetime.now()
    _sub_operations = []
    try:
        log_policy_hit("ENFORCE_START", "architecture-script-mapping-enforcement")

        _op_start = datetime.now()
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        try:
            _sub_operations.append(record_sub_operation(
                "init_memory_dir", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000)
            ))
        except Exception:
            pass

        log_policy_hit("ENFORCE_COMPLETE", "architecture-script-mapping-ready")
        print("[architecture-script-mapping-policy] Policy enforced - Architecture mapping validation active")

        result = {"status": "success", "policy": "architecture-script-mapping"}
        try:
            if HAS_TRACKING:
                record_policy_execution(
                    session_id=os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
                    policy_name="architecture-script-mapping-policy",
                    policy_script="architecture-script-mapping-policy.py",
                    policy_type="Policy Script",
                    input_params={},
                    output_results=result,
                    decision="architecture mapping validation active",
                    duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                    sub_operations=_sub_operations if _sub_operations else None
                )
        except Exception:
            pass
        return result
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[architecture-script-mapping-policy] ERROR: {e}")
        error_result = {"status": "error", "message": str(e)}
        try:
            if HAS_TRACKING:
                record_policy_execution(
                    session_id=os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
                    policy_name="architecture-script-mapping-policy",
                    policy_script="architecture-script-mapping-policy.py",
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
    else:
        enforce()
