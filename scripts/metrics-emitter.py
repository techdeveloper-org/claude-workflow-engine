#!/usr/bin/env python3
"""
Script Name: metrics-emitter.py
Version: 1.0.0
Last Modified: 2026-03-05
Description: Fire-and-forget telemetry emitter for the Claude Memory System.
             Appends structured JSONL records to ~/.claude/memory/logs/metrics.jsonl.
             NEVER blocks. All errors are silently swallowed.

Output format: JSONL (one JSON object per line)
Output file  : ~/.claude/memory/logs/metrics.jsonl

Record types:
  hook_execution    - emitted once per hook script invocation (total wall time)
  enforcement_event - emitted when a blocking enforcement action fires
  policy_step       - emitted after each numbered policy step completes
  flag_lifecycle    - emitted on flag write / flag clear events
  context_sample    - emitted when context % is sampled during a session

Design rules:
  - Every public function is wrapped in try/except that silently passes
  - No function raises an exception to the caller
  - File I/O is append-only (no read-modify-write race)
  - Timestamps are ISO-8601 UTC-aware strings
  - Windows-safe: ASCII-only print statements
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _metrics_file() -> Path:
    """Return the path to metrics.jsonl, creating parent dirs if needed.

    Falls back to a temporary directory path when the home-directory path
    cannot be created, ensuring callers never receive an exception.

    Returns:
        ``Path`` object pointing to the metrics JSONL file. Parent
        directories are created if they do not exist.
    """
    try:
        p = Path.home() / '.claude' / 'memory' / 'logs' / 'metrics.jsonl'
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        # Fallback to a temp location so callers never explode
        return Path(os.environ.get('TEMP', '/tmp')) / 'metrics.jsonl'


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Uses ``datetime.now(timezone.utc).isoformat()`` for a timezone-aware
    string. Falls back to a UTC suffix appended manually on older runtimes.

    Returns:
        ISO-8601 timestamp string with UTC timezone info.
    """
    try:
        return datetime.now(timezone.utc).isoformat()
    except Exception:
        return datetime.utcnow().isoformat() + 'Z'


def _append(record: dict) -> None:
    """
    Append one JSON record to metrics.jsonl (fire-and-forget).
    Uses line-buffered open so each append is atomic for single records.
    """
    try:
        record.setdefault('ts', _now_iso())
        record.setdefault('pid', os.getpid())
        line = json.dumps(record, ensure_ascii=True) + '\n'
        with open(_metrics_file(), 'a', encoding='utf-8', errors='replace') as fh:
            fh.write(line)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public emit functions
# ---------------------------------------------------------------------------

def emit_hook_execution(hook_name: str, duration_ms: int,
                        session_id: str = '', exit_code: int = 0,
                        extra: dict = None) -> None:
    """
    Emit a record that captures one full hook script execution.

    Parameters
    ----------
    hook_name   : name of the hook script (e.g. '3-level-flow.py')
    duration_ms : wall-clock time the hook took to run, in milliseconds
    session_id  : current session ID (empty string if unknown)
    exit_code   : exit code the hook is about to return (0 = success)
    extra       : optional dict of additional key/value pairs to include
    """
    try:
        record = {
            'type': 'hook_execution',
            'hook': hook_name,
            'duration_ms': int(duration_ms),
            'session_id': str(session_id),
            'exit_code': int(exit_code),
        }
        if extra and isinstance(extra, dict):
            record.update({k: v for k, v in extra.items()
                           if k not in record})
        _append(record)
    except Exception:
        pass


def emit_enforcement_event(hook_name: str, event_type: str,
                           tool_name: str = '', reason: str = '',
                           blocked: bool = False,
                           session_id: str = '',
                           extra: dict = None) -> None:
    """
    Emit a record when an enforcement action occurs (block or hint).

    Parameters
    ----------
    hook_name  : hook script that raised the event
    event_type : one of: 'checkpoint_block', 'task_breakdown_block',
                 'skill_selection_block', 'unicode_block', 'windows_cmd_block',
                 'hint_emitted', 'flag_written', 'flag_cleared'
    tool_name  : tool being called when enforcement fires (may be empty)
    reason     : human-readable reason string
    blocked    : True if the tool call was blocked (exit 1/2), False for hint
    session_id : current session ID
    extra      : optional additional fields
    """
    try:
        record = {
            'type': 'enforcement_event',
            'hook': hook_name,
            'event_type': str(event_type),
            'tool_name': str(tool_name),
            'reason': str(reason)[:200],
            'blocked': bool(blocked),
            'session_id': str(session_id),
        }
        if extra and isinstance(extra, dict):
            record.update({k: v for k, v in extra.items()
                           if k not in record})
        _append(record)
    except Exception:
        pass


def emit_policy_step(step_name: str, level: int, passed: bool,
                     duration_ms: int = 0, session_id: str = '',
                     details: dict = None) -> None:
    """
    Emit a record after a numbered policy step completes.

    Parameters
    ----------
    step_name   : e.g. 'LEVEL_1_CONTEXT', 'LEVEL_3_STEP_3_4_MODEL'
    level       : top-level policy level (-1, 1, 2, or 3)
    passed      : True if the step completed successfully
    duration_ms : time the step took (0 if not measured)
    session_id  : current session ID
    details     : optional dict of step-specific output values
    """
    try:
        record = {
            'type': 'policy_step',
            'step': str(step_name),
            'level': int(level),
            'passed': bool(passed),
            'duration_ms': int(duration_ms),
            'session_id': str(session_id),
        }
        if details and isinstance(details, dict):
            record['details'] = {k: v for k, v in details.items()}
        _append(record)
    except Exception:
        pass


def emit_flag_lifecycle(flag_type: str, action: str,
                        session_id: str = '', reason: str = '',
                        extra: dict = None) -> None:
    """
    Emit a record when an enforcement flag is written or cleared.

    Parameters
    ----------
    flag_type  : 'checkpoint', 'task_breakdown', or 'skill_selection'
    action     : 'write' or 'clear'
    session_id : session the flag belongs to
    reason     : why the flag was written / cleared
    extra      : optional additional fields
    """
    try:
        record = {
            'type': 'flag_lifecycle',
            'flag_type': str(flag_type),
            'action': str(action),
            'session_id': str(session_id),
            'reason': str(reason)[:200],
        }
        if extra and isinstance(extra, dict):
            record.update({k: v for k, v in extra.items()
                           if k not in record})
        _append(record)
    except Exception:
        pass


def emit_context_sample(context_pct: float, session_id: str = '',
                        source: str = '', tool_name: str = '',
                        extra: dict = None) -> None:
    """
    Emit a context-usage sample at a point in time.

    Parameters
    ----------
    context_pct : context window used, 0-100 float
    session_id  : current session ID
    source      : which script sampled this (e.g. 'post-tool-tracker')
    tool_name   : tool that just ran before this sample (may be empty)
    extra       : optional additional fields
    """
    try:
        record = {
            'type': 'context_sample',
            'context_pct': round(float(context_pct), 2),
            'session_id': str(session_id),
            'source': str(source),
            'tool_name': str(tool_name),
        }
        if extra and isinstance(extra, dict):
            record.update({k: v for k, v in extra.items()
                           if k not in record})
        _append(record)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CLI self-test (python metrics-emitter.py)
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print('[metrics-emitter] Running self-test...')
    emit_hook_execution('test-hook.py', 123, session_id='SESSION-TEST-001', exit_code=0)
    emit_enforcement_event('pre-tool-enforcer.py', 'task_breakdown_block',
                           tool_name='Write', reason='task-breakdown-pending flag found',
                           blocked=True, session_id='SESSION-TEST-001')
    emit_policy_step('LEVEL_3_STEP_3_4_MODEL', level=3, passed=True,
                     duration_ms=5, session_id='SESSION-TEST-001',
                     details={'model': 'SONNET', 'complexity': 8})
    emit_flag_lifecycle('skill_selection', 'write',
                        session_id='SESSION-TEST-001',
                        reason='step_3_5_skill_selection_required')
    emit_context_sample(72.5, session_id='SESSION-TEST-001',
                        source='post-tool-tracker', tool_name='Edit')
    mf = _metrics_file()
    print(f'[metrics-emitter] Wrote 5 test records to: {mf}')
    try:
        with open(mf, 'r', encoding='utf-8') as fh:
            lines = [l.strip() for l in fh if l.strip()]
        print(f'[metrics-emitter] Total records in file: {len(lines)}')
        print(f'[metrics-emitter] Last record: {lines[-1]}')
    except Exception as e:
        print(f'[metrics-emitter] Could not verify output: {e}')
    print('[metrics-emitter] Self-test complete.')
