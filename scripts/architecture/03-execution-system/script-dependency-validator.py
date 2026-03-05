#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script Dependency Validator (v1.0)
Script Name: script-dependency-validator.py
Version: 1.0.0
Last Modified: 2026-03-05
Description: Validates that:
  1. All script dependencies are present
  2. Scripts can call each other safely
  3. Artifacts (JSON, flags) have schema versions
  4. No circular dependencies exist
  5. Dependency DAG is healthy

Usage:
  python script-dependency-validator.py --validate  # Check all dependencies
  python script-dependency-validator.py --report     # Print dependency graph (JSON)

Hook Type: Utility (called by 3-level-flow.py Level 1.6)
Windows-Safe: No Unicode chars (ASCII only, cp1252 compatible)
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Windows-safe encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Use ide_paths if available (for IDE-installed deployments), else fallback
try:
    _scripts_parent = Path(__file__).parent.parent.parent  # scripts/architecture/03-execution-system -> scripts
    import sys as _sys
    _sys.path.insert(0, str(_scripts_parent))
    from ide_paths import MEMORY_BASE, SCRIPTS_DIR
except ImportError:
    MEMORY_BASE = Path.home() / '.claude' / 'memory'
    SCRIPTS_DIR = Path.home() / '.claude' / 'scripts'

# SCRIPTS_DIR in the source repo (for dev mode)
_REPO_SCRIPTS_DIR = Path(__file__).parent.parent.parent  # scripts/ directory

LOG_FILE = MEMORY_BASE / 'logs' / 'policy-hits.log'

# =============================================================================
# DEPENDENCY GRAPH
# Maps each hook/entry script to the scripts it directly calls/imports.
# Update this dict whenever a new script-to-script dependency is introduced.
# =============================================================================
DEPENDENCY_GRAPH = {
    '3-level-flow.py': [
        'clear-session-handler.py',
        'auto-fix-enforcer.py',
        'context-monitor-v2.py',
        'session-id-generator.py',
        'session-summary-manager.py',
        'session-chain-manager.py',
        'metrics-emitter.py',
        'policy-executor.py',
    ],
    'pre-tool-enforcer.py': [
        'metrics-emitter.py',
    ],
    'post-tool-tracker.py': [
        'session-summary-manager.py',
        'metrics-emitter.py',
    ],
    'clear-session-handler.py': [
        'session-chain-manager.py',
        'session-id-generator.py',
        'session-summary-manager.py',
    ],
    'stop-notifier.py': [
        'session-summary-manager.py',
        'voice-notifier.py',
    ],
    'auto-fix-enforcer.py': [
        'session-id-generator.py',
    ],
}

# =============================================================================
# ARTIFACT SCHEMA VERSIONS
# Defines expected schema versions for cross-script shared JSON artifacts.
# Scripts that write these files should include '_schema_version' at the root.
# =============================================================================
ARTIFACT_SCHEMAS = {
    'flow-trace.json': {
        'version': '2.0',
        'description': 'Full pipeline trace written by 3-level-flow.py',
        'required_fields': ['meta', 'user_input', 'pipeline', 'final_decision', 'status'],
        'schema_key': '_schema_version',
        'writer': '3-level-flow.py',
    },
    'session-progress.json': {
        'version': '1.5',
        'description': 'Per-session tool usage and progress state',
        'required_fields': ['session_id', 'tool_counts', 'total_progress'],
        'schema_key': '_schema_version',
        'writer': 'post-tool-tracker.py / 3-level-flow.py',
    },
    'session-summary.json': {
        'version': '2.1',
        'description': 'Accumulated per-request session data',
        'required_fields': ['version', 'session_id', 'requests'],
        'schema_key': 'version',
        'writer': 'session-summary-manager.py',
    },
}


# =============================================================================
# LOGGING
# =============================================================================

def log_policy_hit(action, context=''):
    """Log validation event to policy-hits.log."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] script-dependency-validator | {action} | {context}\n")
    except Exception:
        pass


# =============================================================================
# SCRIPT RESOLUTION
# =============================================================================

def find_script(script_name):
    """Find a script by name in SCRIPTS_DIR (deployed) or repo scripts dir.

    Searches:
      1. Deployed scripts dir (~/.claude/scripts/) - flat and recursive
      2. Source repo scripts dir (scripts/) - flat and recursive

    Args:
        script_name: Filename to find (e.g. '3-level-flow.py').

    Returns:
        Path if found, None otherwise.
    """
    search_roots = [SCRIPTS_DIR, _REPO_SCRIPTS_DIR]

    for root in search_roots:
        if not root.exists():
            continue
        # Direct (flat) lookup first - fastest
        candidate = root / script_name
        if candidate.exists():
            return candidate
        # Recursive search
        for match in root.rglob(script_name):
            if match.is_file():
                return match

    return None


# =============================================================================
# DEPENDENCY VALIDATION
# =============================================================================

def validate_dependencies():
    """Check that every dependency in DEPENDENCY_GRAPH can be located on disk.

    Returns:
        tuple: (all_found: bool, missing: list[str])
               all_found is True when zero dependencies are missing.
               missing contains human-readable '<parent> depends on <dep> (NOT FOUND)' strings.
    """
    missing = []

    for script, deps in DEPENDENCY_GRAPH.items():
        for dep in deps:
            if not find_script(dep):
                missing.append(f"{script} depends on {dep} (NOT FOUND)")

    total_deps = sum(len(d) for d in DEPENDENCY_GRAPH.values())
    if missing:
        log_policy_hit('VALIDATE_ERROR', f'Missing {len(missing)}/{total_deps} dependencies')
        return False, missing

    log_policy_hit('VALIDATE_SUCCESS', f'All {total_deps} dependencies found across {len(DEPENDENCY_GRAPH)} scripts')
    return True, []


# =============================================================================
# CIRCULAR DEPENDENCY DETECTION
# =============================================================================

def detect_circular_dependencies():
    """Detect cycles in DEPENDENCY_GRAPH using iterative DFS.

    Performs a depth-first search over the dependency graph.  Any back-edge
    (where the neighbour is on the current recursion stack) represents a cycle
    and is recorded in the returned list.

    Returns:
        list[str]: Human-readable cycle descriptions like
                   'Cycle: A -> B -> C -> A'. Empty list means no cycles.
    """
    visited = set()
    rec_stack = set()
    cycles = []

    def dfs(node, path):
        visited.add(node)
        rec_stack.add(node)

        for neighbor in DEPENDENCY_GRAPH.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, path + [neighbor])
            elif neighbor in rec_stack:
                # Back edge found -> cycle
                cycle_start = path.index(neighbor) if neighbor in path else 0
                cycle_path = path[cycle_start:] + [neighbor]
                cycles.append('Cycle: ' + ' -> '.join(cycle_path))

        rec_stack.discard(node)

    for script in DEPENDENCY_GRAPH:
        if script not in visited:
            dfs(script, [script])

    return cycles


# =============================================================================
# ARTIFACT SCHEMA VALIDATION
# =============================================================================

def validate_artifact_schemas():
    """Check that existing artifact files include a schema version field.

    Scans session log directories for known artifact filenames and verifies
    each readable file carries the expected schema key defined in
    ARTIFACT_SCHEMAS.  Files that are missing the key are flagged as issues.

    Returns:
        list[str]: Issue descriptions. Empty list means all checked files are valid.
    """
    issues = []
    trace_dir = MEMORY_BASE / 'logs' / 'sessions'

    if not trace_dir.exists():
        # No sessions yet - nothing to validate, not an error
        return issues

    for artifact_name, schema_info in ARTIFACT_SCHEMAS.items():
        schema_key = schema_info['schema_key']
        files_checked = 0
        files_missing_key = 0

        for artifact_file in trace_dir.rglob(artifact_name):
            files_checked += 1
            try:
                raw = artifact_file.read_text(encoding='utf-8', errors='replace')
                data = json.loads(raw)
                if schema_key not in data:
                    files_missing_key += 1
                    issues.append(
                        f"{artifact_name}: {artifact_file.name} missing '{schema_key}' "
                        f"(expected version '{schema_info['version']}')"
                    )
            except json.JSONDecodeError:
                issues.append(f"{artifact_name}: {artifact_file.name} is not valid JSON")
            except Exception as exc:
                issues.append(f"{artifact_name}: {artifact_file.name} read error: {exc}")

    return issues


# =============================================================================
# REPORT GENERATION
# =============================================================================

def generate_report():
    """Build a complete dependency validation report dict.

    Runs all three validations (dependency existence, circular detection,
    artifact schema checks) and assembles results into a single report
    suitable for JSON output.

    Returns:
        dict: Report with keys including 'overall_status', 'dependencies_valid',
              'missing_dependencies', 'circular_dependencies', 'artifact_issues',
              'scripts_total', 'dependencies_total', 'artifacts', 'timestamp'.
    """
    report = {
        'timestamp': datetime.now().isoformat(),
        'scripts_total': len(DEPENDENCY_GRAPH),
        'dependencies_total': sum(len(d) for d in DEPENDENCY_GRAPH.values()),
        'artifacts': ARTIFACT_SCHEMAS,
    }

    # 1. Dependency existence
    valid, missing = validate_dependencies()
    report['dependencies_valid'] = valid
    report['missing_dependencies'] = missing

    # 2. Circular dependency detection
    cycles = detect_circular_dependencies()
    report['circular_dependencies'] = cycles
    report['no_cycles'] = len(cycles) == 0

    # 3. Artifact schema validation
    schema_issues = validate_artifact_schemas()
    report['artifact_issues'] = schema_issues

    # Critical check: dependency existence + no cycles (blocks callers if FAIL)
    critical_ok = valid and report['no_cycles']
    report['overall_status'] = 'PASS' if critical_ok else 'FAIL'

    # Advisory check: artifact schema versions (informational - never blocks flow)
    # Artifact issues are expected for pre-existing files written before Improvement #6
    report['artifact_advisory'] = 'OK' if not schema_issues else f'WARN:{len(schema_issues)}'
    report['status'] = 'success'

    return report


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def enforce():
    """Run validation and print a summary line.  Used when called with no args
    or from 3-level-flow.py integration.

    Returns:
        dict: The generated report (same as generate_report()).
    """
    try:
        log_policy_hit('VALIDATE_START', 'script-dependency-validation')
        report = generate_report()

        if report['overall_status'] == 'PASS':
            log_policy_hit(
                'VALIDATE_PASS',
                f"{report['scripts_total']} scripts, "
                f"{report['dependencies_total']} dependencies valid, "
                f"no cycles"
            )
            print(
                f"[script-dependency-validator] PASS: "
                f"{report['scripts_total']} scripts, "
                f"{report['dependencies_total']} deps, "
                f"no cycles"
            )
        else:
            missing_count = len(report.get('missing_dependencies', []))
            cycle_count = len(report.get('circular_dependencies', []))
            artifact_count = len(report.get('artifact_issues', []))
            log_policy_hit(
                'VALIDATE_FAIL',
                f"missing={missing_count}, cycles={cycle_count}, "
                f"artifact_issues={artifact_count}"
            )
            print(
                f"[script-dependency-validator] WARN: "
                f"missing={missing_count}, "
                f"cycles={cycle_count}, "
                f"artifact_issues={artifact_count}"
            )

        return report

    except Exception as exc:
        log_policy_hit('VALIDATE_ERROR', str(exc))
        err_report = {
            'status': 'error',
            'overall_status': 'FAIL',
            'message': str(exc),
            'timestamp': datetime.now().isoformat(),
        }
        print(f"[script-dependency-validator] ERROR: {exc}", file=sys.stderr)
        return err_report


if __name__ == '__main__':
    if len(sys.argv) > 1:
        flag = sys.argv[1]

        if flag == '--validate':
            result = enforce()
            sys.exit(0 if result.get('overall_status') == 'PASS' else 1)

        elif flag == '--report':
            report = generate_report()
            print(json.dumps(report, indent=2, ensure_ascii=False))
            sys.exit(0 if report.get('overall_status') == 'PASS' else 0)  # always 0 for --report

        elif flag in ('--help', '-h'):
            print(__doc__)
            sys.exit(0)

        else:
            print(f"Unknown flag: {flag}. Use --validate or --report.", file=sys.stderr)
            sys.exit(1)
    else:
        # Default: run enforce (non-blocking summary)
        result = enforce()
        sys.exit(0)  # Never block the calling hook
