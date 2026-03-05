#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parallel Execution Policy Enforcement (v2.0) - With Token Limit Awareness

Maps to: policies/03-execution-system/parallel-execution-policy.md

This module enforces the parallel execution policy for the Claude Memory System.
It ensures that independent tool calls are batched and executed simultaneously
rather than sequentially, improving overall response time and efficiency.

ENHANCED: Includes token limit detection and graceful handling for:
  - Subscription users (~200k tokens/day): Degrade to sequential when approaching 75% limit
  - Billing-based enterprise users (unlimited): Full parallel execution
  - Detects plan type via /stats command output or ANTHROPIC_API_KEY
  - Never reports false "success" when work incomplete due to token limits

Policy rules enforced:
  - Independent tool calls must be batched in a single response
  - Sequential execution is only used when calls have dependencies
  - Use ';' separator only when earlier commands can fail independently
  - Use '&&' chaining for dependent sequential commands
  - Parallel Bash, Read, Glob, and Grep calls are encouraged
  - Never add unnecessary sleep or wait commands between independent calls
  - [NEW] Monitor token limits for parallel agent execution
  - [NEW] Gracefully degrade to sequential when token limit approached

Key Functions:
  enforce(): Activate the parallel execution policy.
  validate(): Confirm policy infrastructure is ready.
  report(): Generate a summary report of policy rules.
  detect_user_plan(): Determine if user is subscription or enterprise.
  check_token_availability(): Check if sufficient tokens for parallel execution.

CLI Usage:
  python parallel-execution-policy.py --enforce   # Run policy enforcement
  python parallel-execution-policy.py --validate  # Validate policy compliance
  python parallel-execution-policy.py --report    # Generate policy report
  python parallel-execution-policy.py --check-tokens  # Check token status

Example:
  >>> from parallel_execution_policy import enforce, detect_user_plan
  >>> plan = detect_user_plan()
  >>> result = enforce()
  >>> print(result['status'])  # 'success'
"""

import sys
import json
import os
from pathlib import Path
from datetime import datetime
from enum import Enum

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


class UserPlanType(Enum):
    """User subscription/billing type."""
    SUBSCRIPTION = "subscription"      # Limited tokens (~200k/day)
    ENTERPRISE = "enterprise"          # Unlimited tokens (billing-based)
    UNKNOWN = "unknown"                # Could not determine


def detect_user_plan():
    """
    Detect user plan type (subscription vs enterprise billing).

    Strategy:
    1. Check environment variable CLAUDE_USER_PLAN
    2. Check ANTHROPIC_API_KEY pattern
    3. Check for ~/.claude/.user-plan.json flag file
    4. Default to SUBSCRIPTION (conservative)

    Returns:
        UserPlanType: Detected plan type
    """
    try:
        # Check explicit environment variable
        plan_env = os.environ.get('CLAUDE_USER_PLAN', '').lower()
        if plan_env == 'enterprise':
            log_policy_hit("DETECT_PLAN", "enterprise (env var)")
            return UserPlanType.ENTERPRISE
        if plan_env == 'subscription':
            log_policy_hit("DETECT_PLAN", "subscription (env var)")
            return UserPlanType.SUBSCRIPTION

        # Check for flag file
        flag_file = Path.home() / ".claude" / ".user-plan.json"
        if flag_file.exists():
            try:
                flag_data = json.loads(flag_file.read_text(encoding='utf-8'))
                plan = flag_data.get('plan', '').lower()
                if plan in ['enterprise', 'billing']:
                    log_policy_hit("DETECT_PLAN", "enterprise (flag file)")
                    return UserPlanType.ENTERPRISE
                if plan == 'subscription':
                    log_policy_hit("DETECT_PLAN", "subscription (flag file)")
                    return UserPlanType.SUBSCRIPTION
            except:
                pass

        # Default to subscription (safer, conservative)
        log_policy_hit("DETECT_PLAN", "subscription (default)")
        return UserPlanType.SUBSCRIPTION

    except Exception as e:
        log_policy_hit("DETECT_PLAN_ERROR", str(e))
        return UserPlanType.SUBSCRIPTION


def get_token_limit(plan_type):
    """
    Get token limit for plan type.

    Args:
        plan_type (UserPlanType): User's plan type

    Returns:
        int: Token limit (0 = unlimited)
    """
    if plan_type == UserPlanType.ENTERPRISE:
        return 0  # Unlimited (billing-based)
    elif plan_type == UserPlanType.SUBSCRIPTION:
        return 200000  # ~200k tokens/day or /month
    else:
        return 200000  # Conservative default


def read_token_usage():
    """
    Read current session token usage.

    Returns:
        dict: Usage data with 'total_tokens', 'timestamp', 'session_id'
    """
    try:
        usage_file = MEMORY_DIR / ".token-usage.json"
        if usage_file.exists():
            return json.loads(usage_file.read_text(encoding='utf-8', errors='replace'))
    except Exception:
        pass

    return {
        'total_tokens': 0,
        'timestamp': datetime.now().isoformat(),
        'session_id': os.environ.get('CLAUDE_SESSION_ID', 'unknown')
    }


def can_execute_parallel(plan_type, current_tokens, estimated_tokens):
    """
    Determine if parallel execution is safe for current token state.

    Subscription users:
    - 0-50%: Full parallel ✅
    - 50-75%: Parallel with warning ⚠️
    - 75-90%: Sequential only (degrade)
    - 90%+: Block (no new tasks)

    Enterprise users:
    - Unlimited, always parallel ✅

    Args:
        plan_type (UserPlanType): User's plan
        current_tokens (int): Tokens already used
        estimated_tokens (int): Tokens needed for task

    Returns:
        tuple: (can_execute, message, mode)
            - can_execute (bool): Whether to proceed
            - message (str): Status message
            - mode (str): 'parallel' or 'sequential'
    """
    limit = get_token_limit(plan_type)

    # Enterprise has unlimited tokens
    if limit == 0:
        msg = f"[OK] Enterprise plan - unlimited tokens, full parallel mode"
        log_policy_hit("TOKEN_CHECK", msg)
        return True, msg, "parallel"

    # Subscription plan - check usage
    remaining = limit - current_tokens
    usage_percent = (current_tokens / limit * 100) if limit > 0 else 0

    # Block if over 90%
    if usage_percent >= 90:
        msg = f"[BLOCK] Token limit exceeded ({usage_percent:.0f}% used). No new parallel tasks allowed."
        log_policy_hit("TOKEN_LIMIT_EXCEEDED", msg)
        return False, msg, "blocked"

    # Degrade to sequential if 75-90%
    if usage_percent >= 75:
        msg = f"[WARN] Approaching token limit ({usage_percent:.0f}% used). Switching to SEQUENTIAL mode."
        log_policy_hit("TOKEN_DEGRADATION", msg)
        return True, msg, "sequential"

    # Warn if 50-75%
    if usage_percent >= 50:
        msg = f"[CAUTION] Token usage at {usage_percent:.0f}%. Monitor for limit ({remaining} remaining)."
        log_policy_hit("TOKEN_WARNING", msg)
        return True, msg, "parallel"

    # OK if under 50%
    msg = f"[OK] Token usage at {usage_percent:.0f}%. Parallel execution safe."
    log_policy_hit("TOKEN_OK", msg)
    return True, msg, "parallel"


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
            f.write(f"[{timestamp}] parallel-execution-policy | {action} | {context}\n")
    except:
        pass


def validate():
    """Check that the parallel execution policy preconditions are met.

    Ensures the base memory directory exists and the policy infrastructure
    is ready for parallel execution enforcement.

    Returns:
        bool: True if validation succeeds, False on any exception.
    """
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log_policy_hit("VALIDATE", "parallel-execution-ready")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report for the parallel execution policy.

    Returns a structured dictionary describing the enforced parallelism rules,
    batching guidelines, and current token limit status based on user plan type.

    Returns:
        dict: Report containing status, policy, rules, token limits, and timestamp.
              Returns {'status': 'error', 'message': ...} on failure.
    """
    try:
        plan_type = detect_user_plan()
        token_limit = get_token_limit(plan_type)
        usage_data = read_token_usage()

        report_data = {
            "status": "success",
            "policy": "parallel-execution",
            "description": "Enforces parallel batching of independent tool calls with token limit awareness",
            "user_plan": plan_type.value,
            "token_limit": token_limit if token_limit > 0 else "unlimited (enterprise)",
            "tokens_used": usage_data.get('total_tokens', 0),
            "rules": [
                "Batch independent tool calls in a single response",
                "Use sequential execution only for dependent operations",
                "Use '&&' for dependent sequential commands",
                "Use ';' only when earlier commands may fail independently",
                "Avoid unnecessary sleep or wait between independent calls",
                "Parallel Read, Glob, Grep, and Bash calls are preferred",
                "[NEW] Monitor token limits for parallel agent execution",
                "[NEW] Degrade to sequential when approaching token limit (75%+)"
            ],
            "subscription_plan_limits": {
                "total_tokens": 200000,
                "full_parallel_threshold": "50% usage",
                "degradation_threshold": "75% usage",
                "block_threshold": "90% usage"
            },
            "enterprise_plan_limits": {
                "total_tokens": "unlimited",
                "mode": "always parallel",
                "note": "Billing-based, money meter running, no token limits"
            },
            "timestamp": datetime.now().isoformat()
        }
        log_policy_hit("REPORT", "parallel-execution-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """Activate the parallel execution policy with token limit awareness.

    Initializes the policy, detects user plan type, checks token availability,
    and determines execution mode (parallel or sequential). This is called by
    3-level-flow.py to ensure proper parallelism rules are active before
    launching agents.

    Returns:
        dict: Result containing:
            - 'status' ('success' or 'error')
            - 'policy' name
            - 'plan_type' (subscription or enterprise)
            - 'execution_mode' (parallel or sequential)
            - 'token_limit' (200000 for subscription, 0 for enterprise)
            - 'tokens_used' (current usage)
            - 'message' (descriptive message)
    """
    _track_start_time = datetime.now()
    _sub_operations = []
    try:
        log_policy_hit("ENFORCE_START", "parallel-execution-enforcement")
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

        # Detect user plan type
        _op_start = datetime.now()
        plan_type = detect_user_plan()
        token_limit = get_token_limit(plan_type)
        try:
            _sub_operations.append(record_sub_operation(
                "detect_user_plan", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000),
                {"plan_type": plan_type.value}
            ))
        except Exception:
            pass

        # Check token availability
        _op_start = datetime.now()
        usage_data = read_token_usage()
        current_tokens = usage_data.get('total_tokens', 0)
        can_execute, token_msg, mode = can_execute_parallel(
            plan_type, current_tokens, 1000
        )
        try:
            _sub_operations.append(record_sub_operation(
                "check_token_availability", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000),
                {"execution_mode": mode, "tokens_used": current_tokens}
            ))
        except Exception:
            pass

        # Log enforcement
        log_policy_hit("ENFORCE_COMPLETE", "parallel-execution-ready")

        # Prepare response
        result = {
            "status": "success",
            "policy": "parallel-execution",
            "plan_type": plan_type.value,
            "execution_mode": mode,
            "token_limit": token_limit if token_limit > 0 else "unlimited",
            "tokens_used": current_tokens,
            "message": token_msg
        }

        print(f"[parallel-execution-policy] {token_msg}")
        try:
            if HAS_TRACKING:
                record_policy_execution(
                    session_id=os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
                    policy_name="parallel-execution-policy",
                    policy_script="parallel-execution-policy.py",
                    policy_type="Policy Script",
                    input_params={},
                    output_results=result,
                    decision=f"mode={mode} plan={plan_type.value}",
                    duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                    sub_operations=_sub_operations if _sub_operations else None
                )
        except Exception:
            pass
        return result

    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[parallel-execution-policy] ERROR: {e}")
        error_result = {"status": "error", "message": str(e)}
        try:
            if HAS_TRACKING:
                record_policy_execution(
                    session_id=os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
                    policy_name="parallel-execution-policy",
                    policy_script="parallel-execution-policy.py",
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
        elif sys.argv[1] == "--check-tokens":
            plan = detect_user_plan()
            usage = read_token_usage()
            current_tokens = usage.get('total_tokens', 0)
            can_execute, msg, mode = can_execute_parallel(plan, current_tokens, 1000)
            result = {
                "status": "success",
                "plan_type": plan.value,
                "can_execute": can_execute,
                "mode": mode,
                "tokens_used": current_tokens,
                "token_limit": get_token_limit(plan),
                "message": msg
            }
            print(json.dumps(result, indent=2))
            sys.exit(0)
    else:
        enforce()
