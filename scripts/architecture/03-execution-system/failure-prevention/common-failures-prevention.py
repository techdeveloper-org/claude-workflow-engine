#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Common Failures Prevention Policy - Enterprise Consolidated System (v3.0)

CONSOLIDATED SCRIPT - Maps to:
  policies/03-execution-system/failure-prevention/common-failures-prevention.md

Consolidates ALL 9 source scripts (109.7K total):
  1. failure-detector.py          (14K)  - Failure pattern detection and analysis
  2. failure-detector-v2.py       (13K)  - Enhanced detection with regex patterns
  3. pre-execution-checker.py     (12K)  - Pre-execution failure prevention
  4. failure-solution-learner.py  (12K)  - Learn solutions from successful fixes
  5. update-failure-kb.py         (13K)  - Update failure knowledge base
  6. failure-learner.py           (12K)  - Learn from failure patterns
  7. failure-pattern-extractor.py  (8K)  - Extract failure patterns
  8. windows-python-unicode-checker.py (7K) - Windows Python Unicode issues
  9. common-failures-prevention.py (28K) - Previous stub (fully expanded here)

ZERO LOGIC LOSS - Every class, method, and function from all 9 scripts is
preserved and merged into this unified enterprise-grade policy enforcement system.

Class Structure:
  - FailureDetector              Multi-layer failure detection (v1 + v2 merged)
  - PreExecutionChecker          Prevent failures before tool execution
  - FailureLearner               Learn from failure patterns and progressions
  - FailureSolutionLearner       Extract and reinforce solutions from past fixes
  - FailurePatternExtractor      Extract patterns and suggest solutions
  - FailureKBManager             Manage project-specific and global KB
  - WindowsPythonUnicodeChecker  Windows-specific Unicode failure prevention
  - CommonFailuresPreventionPolicy  Unified policy interface (enforce/validate/report)

CLI Modes:
  --enforce     Initialize all failure prevention subsystems
  --validate    Check compliance and readiness
  --report      Generate failure statistics and prevention report
  --detect      Analyze logs for failure patterns
  --check       Pre-execution check for tool call
  --learn       Learn from detection results
  --analyze     Analyze and extract patterns
  --kb-status   Show knowledge base status

Failure Categories Covered:
  - Command execution failures
  - File operation failures
  - Git operation failures
  - API integration failures
  - Database operation failures
  - Unicode/encoding failures (Windows-specific)
  - Resource exhaustion
  - Circular dependencies
  - Type errors
  - Missing dependencies

Usage:
  python common-failures-prevention-policy.py --enforce
  python common-failures-prevention-policy.py --validate
  python common-failures-prevention-policy.py --report
  python common-failures-prevention-policy.py --detect
  python common-failures-prevention-policy.py --check --tool Bash --params '{"command":"del file.txt"}'
  python common-failures-prevention-policy.py --learn --project my-project
  python common-failures-prevention-policy.py --analyze --with-solutions
  python common-failures-prevention-policy.py --kb-status

Version: 3.0.0
"""

import sys
import os
import re
import json
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Tuple, Any

# ===================================================================
# NEW: POLICY TRACKING INTEGRATION
# ===================================================================
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from policy_tracking_helper import record_policy_execution, record_sub_operation
    HAS_TRACKING = True
except ImportError:
    HAS_TRACKING = False

# ---------------------------------------------------------------------------
# WINDOWS ENCODING FIX - Must be first executable code
# ---------------------------------------------------------------------------
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
elif sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ---------------------------------------------------------------------------
# GLOBAL CONFIGURATION
# ---------------------------------------------------------------------------

MEMORY_DIR = Path.home() / ".claude" / "memory"
LOGS_DIR = MEMORY_DIR / "logs"
SESSIONS_DIR = MEMORY_DIR / "sessions"
DAEMON_LOGS_DIR = LOGS_DIR / "daemons"

FAILURES_LOG = LOGS_DIR / "failures.log"
POLICY_LOG = LOGS_DIR / "policy-hits.log"
HEALTH_LOG = LOGS_DIR / "health.log"
DETECTION_OUTPUT = LOGS_DIR / "failure-detection.json"
KB_FILE = MEMORY_DIR / "failure-kb.json"
SOLUTION_LEARNING_LOG = LOGS_DIR / "solution-learning.log"
GLOBAL_KB_MD = MEMORY_DIR / "common-failures-prevention.md"

# Learning progression thresholds (from failure-learner.py)
LEARNING_THRESHOLDS = {
    "monitoring_to_learning": 2,
    "learning_to_confirmed": 5,
    "confirmed_to_global": 10,
    "confidence_threshold": 0.7,
}

# Pre-execution auto-fix confidence threshold
AUTO_FIX_THRESHOLD = 0.75

# Log analysis window
ANALYSIS_DAYS = 30
MAX_LOG_LINES = 1000

# ---------------------------------------------------------------------------
# FAILURE PATTERN REGISTRY
# Merged from: failure-detector.py FAILURE_PATTERNS + failure-detector-v2.py
# error_patterns + additional enterprise categories
# ---------------------------------------------------------------------------

# Keyword-based detection signatures (from failure-detector.py)
FAILURE_SIGNATURES = {
    "encoding_error": {
        "keywords": ["UnicodeEncodeError", "charmap", "encoding", "utf-8"],
        "severity": "medium",
        "category": "encoding"
    },
    "file_not_found": {
        "keywords": ["FileNotFoundError", "No such file", "cannot find"],
        "severity": "medium",
        "category": "filesystem"
    },
    "permission_denied": {
        "keywords": ["PermissionError", "Permission denied", "Access denied"],
        "severity": "high",
        "category": "permissions"
    },
    "timeout": {
        "keywords": ["TimeoutError", "timeout", "timed out"],
        "severity": "medium",
        "category": "performance"
    },
    "import_error": {
        "keywords": ["ImportError", "ModuleNotFoundError", "No module named"],
        "severity": "high",
        "category": "dependencies"
    },
    "syntax_error": {
        "keywords": ["SyntaxError", "invalid syntax"],
        "severity": "high",
        "category": "code"
    },
    "type_error": {
        "keywords": ["TypeError", "type object"],
        "severity": "medium",
        "category": "code"
    },
    "attribute_error": {
        "keywords": ["AttributeError", "has no attribute"],
        "severity": "medium",
        "category": "code"
    },
    "value_error": {
        "keywords": ["ValueError", "invalid literal"],
        "severity": "medium",
        "category": "validation"
    },
    "key_error": {
        "keywords": ["KeyError", "key not found"],
        "severity": "medium",
        "category": "data"
    },
    "git_error": {
        "keywords": ["git error", "fatal: not a git", "git command failed"],
        "severity": "medium",
        "category": "git"
    },
    "network_error": {
        "keywords": ["ConnectionError", "Network", "Connection refused"],
        "severity": "high",
        "category": "network"
    },
    "resource_exhaustion": {
        "keywords": ["MemoryError", "out of memory", "disk full", "no space left"],
        "severity": "critical",
        "category": "resources"
    },
    "circular_dependency": {
        "keywords": ["circular import", "circular dependency", "ImportError: cannot import"],
        "severity": "high",
        "category": "dependencies"
    },
    "database_error": {
        "keywords": ["DatabaseError", "OperationalError", "IntegrityError", "sqlite3"],
        "severity": "high",
        "category": "database"
    },
    "api_error": {
        "keywords": ["APIError", "HTTPError", "RequestException", "401", "403", "500"],
        "severity": "medium",
        "category": "api"
    },
}

# Regex-based detection patterns (from failure-detector-v2.py error_patterns)
REGEX_ERROR_PATTERNS = [
    # Bash command errors
    (r'bash: (.+): command not found', 'bash_command_not_found', 'Bash'),
    (r'(.+): No such file or directory', 'file_not_found', 'Bash'),
    (r'Permission denied', 'permission_denied', 'Bash'),

    # Edit tool errors
    (r'String to replace not found: (.+)', 'edit_string_not_found', 'Edit'),
    (r'File not read before editing', 'edit_without_read', 'Edit'),

    # Read tool errors
    (r'File content \((\d+) tokens\) exceeds maximum', 'file_too_large', 'Read'),
    (r'File does not exist: (.+)', 'file_not_exist', 'Read'),

    # Grep errors
    (r'No matches found for pattern: (.+)', 'grep_no_matches', 'Grep'),

    # Python errors
    (r'ModuleNotFoundError: No module named (.+)', 'python_module_not_found', 'Bash'),
    (r'ImportError: (.+)', 'python_import_error', 'Bash'),
    (r'SyntaxError: (.+)', 'python_syntax_error', 'Bash'),

    # Git errors
    (r'fatal: not a git repository', 'git_not_repository', 'Bash'),
    (r'error: pathspec (.+) did not match any file', 'git_pathspec_error', 'Bash'),

    # General errors
    (r'ERROR: (.+)', 'general_error', 'Unknown'),
    (r'FAILED: (.+)', 'general_failure', 'Unknown'),

    # Resource errors
    (r'MemoryError', 'memory_error', 'Bash'),
    (r'OSError: \[Errno 28\]', 'disk_full', 'Bash'),

    # API errors
    (r'HTTPError: (\d+)', 'http_error', 'Bash'),
    (r'ConnectionRefusedError', 'connection_refused', 'Bash'),

    # Database errors
    (r'sqlite3\.OperationalError: (.+)', 'sqlite_error', 'Bash'),
    (r'IntegrityError: (.+)', 'db_integrity_error', 'Bash'),
]

# Windows Unicode replacement map (from windows-python-unicode-checker.py)
UNICODE_REPLACEMENTS = {
    # Emojis
    '\U0001f4dd': '[LOG]',
    '\u2705': '[OK]',
    '\u274c': '[ERROR]',
    '\U0001f6a8': '[ALERT]',
    '\U0001f50d': '[SEARCH]',
    '\U0001f4ca': '[CHART]',
    '\U0001f3af': '[TARGET]',
    '\U0001f527': '[WRENCH]',
    '\U0001f534': '[RED]',
    '\U0001f7e2': '[GREEN]',
    '\U0001f7e1': '[YELLOW]',
    '\U0001f535': '[BLUE]',
    '\u26a0\ufe0f': '[WARNING]',
    '\U0001f4a1': '[BULB]',
    '\U0001f4c1': '[FOLDER]',
    '\U0001f4c4': '[PAGE]',
    '\U0001f4cb': '[CLIPBOARD]',
    '\U0001f9e0': '[BRAIN]',
    '\u26a1': '[LIGHTNING]',
    '\U0001f389': '[PARTY]',
    '\U0001f916': '[ROBOT]',
    '\U0001f3d7\ufe0f': '[BUILDING]',
    # Special symbols
    '\u2192': '->',
    '\u2190': '<-',
    '\u2191': '^',
    '\u2193': 'v',
    '\u2713': '[CHECK]',
    '\u2717': '[X]',
    '\u2022': '-',
    '\u2605': '*',
    '\u25b6': '>',
    '\u25c0': '<',
    '\u25a0': '#',
    '\u25a1': '[ ]',
    '\u2550': '=',
    '\u2551': '|',
    '\u2502': '|',
    '\u2500': '-',
    '\u2514': '+',
    '\u251c': '+',
    '\u2524': '+',
    '\u252c': '+',
    '\u2534': '+',
    '\u253c': '+',
    # Additional symbols used in codebase
    '\u2192': '->',
    '\u2713': '[CHECK]',
    '\u2717': '[X]',
    '\u26a0': '[WARN]',
    '\u25cf': '*',
    '\u25cb': 'o',
    '\u25c6': '[*]',
    '\u25c7': '[o]',
    '\u25b2': '^',
    '\u25bc': 'v',
}


# ===========================================================================
# SECTION 1: UTILITY FUNCTIONS
# ===========================================================================

def log_policy_hit(action: str, context: str = "") -> None:
    """
    Log policy execution event to policy-hits.log.

    Args:
        action: The action being logged (e.g., ENFORCE_START, KB_LOADED)
        context: Additional context string for the log entry
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] common-failures-prevention | {action} | {context}\n"
        POLICY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(POLICY_LOG, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Warning: Could not write to log: {e}", file=sys.stderr)


def log_learning_event(event_type: str, details: str) -> None:
    """
    Log a learning event to solution-learning.log.

    Args:
        event_type: Type of learning event (e.g., SOLUTION_LEARNED, SOLUTION_UPDATED)
        details: Details about the learning event
    """
    try:
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {event_type} | {details}\n"
        SOLUTION_LEARNING_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(SOLUTION_LEARNING_LOG, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Warning: Could not write to learning log: {e}", file=sys.stderr)


def get_current_project() -> Optional[str]:
    """
    Get current project name from working directory.

    Returns:
        Project name string or None if unable to determine
    """
    try:
        return Path.cwd().name
    except Exception:
        return None


def load_global_kb() -> Dict:
    """
    Load the global failure knowledge base from disk.

    Returns:
        Dictionary containing the KB, or empty dict if not found/invalid
    """
    if not KB_FILE.exists():
        return {}
    try:
        return json.loads(KB_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_global_kb(kb: Dict) -> bool:
    """
    Save the global failure knowledge base to disk.

    Args:
        kb: Knowledge base dictionary to save

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        KB_FILE.parent.mkdir(parents=True, exist_ok=True)
        KB_FILE.write_text(json.dumps(kb, indent=2), encoding='utf-8')
        return True
    except Exception as e:
        print(f"Error saving global KB: {e}", file=sys.stderr)
        return False


def load_project_kb(project_name: str) -> Dict:
    """
    Load project-specific failure knowledge base.

    Args:
        project_name: Name of the project

    Returns:
        Dictionary with 'patterns' and 'metadata' keys
    """
    session_dir = SESSIONS_DIR / project_name
    kb_file = session_dir / "failures.json"

    if not kb_file.exists():
        return {"patterns": {}, "metadata": {}}

    try:
        with open(kb_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"patterns": {}, "metadata": {}}


def save_project_kb(project_name: str, kb_data: Dict) -> bool:
    """
    Save project-specific failure knowledge base.

    Args:
        project_name: Name of the project
        kb_data: Knowledge base data to save

    Returns:
        True if saved successfully, False otherwise
    """
    session_dir = SESSIONS_DIR / project_name
    kb_file = session_dir / "failures.json"

    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        with open(kb_file, 'w', encoding='utf-8') as f:
            json.dump(kb_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving project KB: {e}", file=sys.stderr)
        return False


def load_detection_results() -> Optional[Dict]:
    """
    Load the most recent failure detection results from disk.

    Returns:
        Detection results dict or None if not available
    """
    if not DETECTION_OUTPUT.exists():
        return None
    try:
        with open(DETECTION_OUTPUT, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading detection results: {e}", file=sys.stderr)
        return None


def save_detection_output(report: Dict) -> None:
    """
    Save failure detection report to JSON file.

    Args:
        report: Detection report dictionary to save
    """
    try:
        DETECTION_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with open(DETECTION_OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        log_policy_hit(
            "detection-saved",
            f"{report.get('summary', {}).get('unique_patterns', 0)} patterns detected"
        )
    except Exception as e:
        print(f"Error saving detection output: {e}", file=sys.stderr)


# ===========================================================================
# SECTION 2: FAILURE DETECTOR CLASS
# Merges: failure-detector.py + failure-detector-v2.py
# ===========================================================================

class FailureDetector:
    """
    Multi-layer failure detection combining keyword-based and regex-based
    detection strategies.

    Sources merged:
      - failure-detector.py: log analysis, keyword detection, aggregation
      - failure-detector-v2.py: FailureDetectorV2 class, regex patterns,
        log file analysis, KB update integration
    """

    def __init__(self):
        """Initialize the FailureDetector with all pattern registries."""
        self.memory_dir = MEMORY_DIR
        self.logs_dir = LOGS_DIR
        self.failures_log = FAILURES_LOG
        self.policy_log = POLICY_LOG
        self.health_log = HEALTH_LOG
        self.daemon_logs_dir = DAEMON_LOGS_DIR

        # Keyword signatures for broad detection (failure-detector.py)
        self.failure_signatures = FAILURE_SIGNATURES

        # Regex patterns for precise detection (failure-detector-v2.py)
        self.regex_patterns = REGEX_ERROR_PATTERNS

    # -----------------------------------------------------------------------
    # Keyword-based detection (from failure-detector.py)
    # -----------------------------------------------------------------------

    def detect_failure_signature(self, text: str) -> Optional[Dict]:
        """
        Detect failure pattern from text using keyword matching.

        Args:
            text: Text to search for failure signatures

        Returns:
            Dictionary with signature, severity, category, matched_keyword
            or None if no failure detected
        """
        text_lower = text.lower()

        for signature, pattern in self.failure_signatures.items():
            for keyword in pattern["keywords"]:
                if keyword.lower() in text_lower:
                    return {
                        "signature": signature,
                        "severity": pattern["severity"],
                        "category": pattern["category"],
                        "matched_keyword": keyword
                    }

        # Generic error detection as fallback
        if "error" in text_lower or "failed" in text_lower or "exception" in text_lower:
            return {
                "signature": "generic_error",
                "severity": "low",
                "category": "unknown",
                "matched_keyword": "error/failed/exception"
            }

        return None

    def extract_failure_context(self, log_line: str) -> Optional[Dict]:
        """
        Extract structured context from a log line.

        Expected format: [timestamp] source | action | context

        Args:
            log_line: Raw log line to parse

        Returns:
            Dictionary with timestamp, source, action, context keys
            or None if parsing fails
        """
        try:
            if not log_line.startswith('['):
                return None

            parts = log_line.split('|', 2)
            if len(parts) < 3:
                return None

            timestamp_source = parts[0].strip()
            action = parts[1].strip()
            context = parts[2].strip()

            timestamp_match = re.match(r'\[([^\]]+)\]', timestamp_source)
            if not timestamp_match:
                return None

            timestamp_str = timestamp_match.group(1)
            source = timestamp_source[len(timestamp_match.group(0)):].strip()

            return {
                "timestamp": timestamp_str,
                "source": source,
                "action": action,
                "context": context,
                "full_line": log_line
            }

        except Exception:
            return None

    def analyze_failure_log(self, max_lines: int = MAX_LOG_LINES) -> List[Dict]:
        """
        Analyze failures.log for failure patterns over the last 30 days.

        Args:
            max_lines: Maximum number of log lines to analyze

        Returns:
            List of failure dictionaries with signature, severity, category
        """
        if not self.failures_log.exists():
            return []

        failures = []
        cutoff_time = datetime.now() - timedelta(days=ANALYSIS_DAYS)

        try:
            with open(self.failures_log, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            for line in lines[-max_lines:]:
                context = self.extract_failure_context(line)
                if not context:
                    continue

                # Filter by time window
                try:
                    log_time = datetime.strptime(context["timestamp"], "%Y-%m-%d %H:%M:%S")
                    if log_time < cutoff_time:
                        continue
                except Exception:
                    pass

                signature = self.detect_failure_signature(context["context"])

                if signature:
                    failure = {
                        "timestamp": context["timestamp"],
                        "source": context["source"],
                        "action": context["action"],
                        "context": context["context"],
                        "signature": signature["signature"],
                        "severity": signature["severity"],
                        "category": signature["category"],
                        "matched_keyword": signature["matched_keyword"]
                    }
                    failures.append(failure)

        except Exception as e:
            print(f"Error analyzing failure log: {e}", file=sys.stderr)

        return failures

    def analyze_policy_log(self, max_lines: int = MAX_LOG_LINES) -> List[Dict]:
        """
        Analyze policy-hits.log for prevented failures.

        Args:
            max_lines: Maximum number of log lines to analyze

        Returns:
            List of prevented failure event dictionaries
        """
        if not self.policy_log.exists():
            return []

        prevented = []
        cutoff_time = datetime.now() - timedelta(days=ANALYSIS_DAYS)

        try:
            with open(self.policy_log, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            for line in lines[-max_lines:]:
                if "prevented" not in line.lower() and "failure-prevention" not in line.lower():
                    continue

                context = self.extract_failure_context(line)
                if not context:
                    continue

                try:
                    log_time = datetime.strptime(context["timestamp"], "%Y-%m-%d %H:%M:%S")
                    if log_time < cutoff_time:
                        continue
                except Exception:
                    pass

                prevented.append({
                    "timestamp": context["timestamp"],
                    "source": context["source"],
                    "action": context["action"],
                    "context": context["context"]
                })

        except Exception as e:
            print(f"Error analyzing policy log: {e}", file=sys.stderr)

        return prevented

    def aggregate_failures(self, failures: List[Dict]) -> Dict:
        """
        Aggregate failures by signature for reporting.

        Args:
            failures: List of failure event dictionaries

        Returns:
            Dictionary keyed by signature with count, severity, examples
        """
        aggregated = defaultdict(lambda: {
            "count": 0,
            "severity": "low",
            "category": "unknown",
            "first_seen": None,
            "last_seen": None,
            "examples": []
        })

        for failure in failures:
            sig = failure["signature"]
            agg = aggregated[sig]

            agg["count"] += 1
            agg["severity"] = failure["severity"]
            agg["category"] = failure["category"]

            if not agg["first_seen"] or failure["timestamp"] < agg["first_seen"]:
                agg["first_seen"] = failure["timestamp"]

            if not agg["last_seen"] or failure["timestamp"] > agg["last_seen"]:
                agg["last_seen"] = failure["timestamp"]

            if len(agg["examples"]) < 3:
                agg["examples"].append({
                    "timestamp": failure["timestamp"],
                    "context": failure["context"][:200]
                })

        return dict(aggregated)

    def generate_detection_report(self, failures: List[Dict], prevented: List[Dict]) -> Dict:
        """
        Generate a comprehensive detection report.

        Args:
            failures: List of detected failure events
            prevented: List of prevented failure events

        Returns:
            Report dictionary with summary, patterns, and prevention log
        """
        aggregated = self.aggregate_failures(failures)

        return {
            "generated": datetime.now().isoformat(),
            "summary": {
                "total_failures": len(failures),
                "unique_patterns": len(aggregated),
                "prevented_failures": len(prevented),
                "analysis_period_days": ANALYSIS_DAYS
            },
            "failures_by_signature": aggregated,
            "prevention_log": prevented[-10:]
        }

    # -----------------------------------------------------------------------
    # Regex-based detection (from failure-detector-v2.py FailureDetectorV2)
    # -----------------------------------------------------------------------

    def parse_log_line_v2(self, line: str) -> Optional[Dict]:
        """
        Parse a log line using the v2 format: [timestamp] LEVEL | message.

        Args:
            line: Raw log line string

        Returns:
            Dictionary with timestamp, level, message keys or None
        """
        match = re.match(r'\[([^\]]+)\]\s+(\w+)\s*\|\s*(.+)', line)
        if match:
            timestamp_str, level, message = match.groups()
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except Exception:
                timestamp = None
            return {
                'timestamp': timestamp,
                'level': level,
                'message': message,
                'raw': line
            }
        return None

    def detect_failure_in_message(self, message: str) -> Optional[Dict]:
        """
        Detect failure pattern in message using regex patterns.

        Args:
            message: Log message string to analyze

        Returns:
            Dictionary with failure_type, tool, pattern, params
            or None if no match found
        """
        for pattern, failure_type, tool in self.regex_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                params = match.groups()[0] if match.groups() else None
                return {
                    'failure_type': failure_type,
                    'tool': tool,
                    'pattern': pattern,
                    'params': params,
                    'full_message': message
                }
        return None

    def analyze_log_file_v2(self, log_file: Path) -> List[Dict]:
        """
        Analyze a log file for failures using v2 regex detection.

        Args:
            log_file: Path to the log file to analyze

        Returns:
            List of failure event dictionaries
        """
        if not log_file.exists():
            return []

        failures = []

        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    parsed = self.parse_log_line_v2(line)
                    if not parsed:
                        continue

                    if parsed['level'] in ['ERROR', 'CRITICAL', 'FAILED']:
                        failure = self.detect_failure_in_message(parsed['message'])
                        if failure:
                            failure['timestamp'] = parsed['timestamp']
                            failure['log_file'] = str(log_file.name)
                            failures.append(failure)

        except Exception as e:
            print(f"Error analyzing {log_file}: {e}", file=sys.stderr)

        return failures

    def analyze_all_logs_v2(self) -> List[Dict]:
        """
        Analyze all log files using v2 regex detection.

        Returns:
            Combined list of failure events from all log files
        """
        all_failures = []

        for log_file in [self.failures_log, self.policy_log, self.health_log]:
            if log_file.exists():
                all_failures.extend(self.analyze_log_file_v2(log_file))

        if self.daemon_logs_dir.exists():
            for log_file in self.daemon_logs_dir.glob('*.log'):
                all_failures.extend(self.analyze_log_file_v2(log_file))

        return all_failures

    def group_failures_v2(self, failures: List[Dict]) -> Dict:
        """
        Group failures by (failure_type, tool) tuple.

        Args:
            failures: List of failure event dictionaries

        Returns:
            Dictionary keyed by (failure_type, tool) with failure lists
        """
        grouped = defaultdict(list)
        for failure in failures:
            key = (failure['failure_type'], failure['tool'])
            grouped[key].append(failure)
        return dict(grouped)

    def calculate_signature_v2(self, failure: Dict) -> str:
        """
        Calculate unique signature string for a failure.

        Args:
            failure: Failure event dictionary

        Returns:
            Signature string in format "Tool:failure_type"
        """
        return f"{failure['tool']}:{failure['failure_type']}"

    def extract_pattern_data_v2(self, grouped_failures: Dict) -> List[Dict]:
        """
        Extract structured pattern data from grouped failures.

        Args:
            grouped_failures: Dictionary of failures grouped by type/tool

        Returns:
            List of pattern dictionaries with frequency, confidence, samples
        """
        patterns = []

        for (failure_type, tool), failure_list in grouped_failures.items():
            params_list = [f['params'] for f in failure_list if f['params']]
            frequency = len(failure_list)
            sample_messages = [f['full_message'] for f in failure_list[:3]]
            confidence = min(1.0, frequency / 10.0)

            first_ts = failure_list[0].get('timestamp')
            last_ts = failure_list[-1].get('timestamp')

            pattern = {
                'pattern_id': f"{tool.lower()}_{failure_type}",
                'failure_type': failure_type,
                'tool': tool,
                'frequency': frequency,
                'confidence': round(confidence, 2),
                'sample_params': params_list[:5],
                'sample_messages': sample_messages,
                'first_seen': first_ts.isoformat() if first_ts else None,
                'last_seen': last_ts.isoformat() if last_ts else None,
            }
            patterns.append(pattern)

        return patterns

    def get_statistics(self, failures: List[Dict]) -> Dict:
        """
        Get statistical summary of failures by tool and type.

        Args:
            failures: List of failure event dictionaries

        Returns:
            Statistics dictionary with totals and breakdowns
        """
        if not failures:
            return {
                'total_failures': 0,
                'unique_types': 0,
                'by_tool': {},
                'by_type': {}
            }

        by_tool = defaultdict(int)
        by_type = defaultdict(int)

        for failure in failures:
            by_tool[failure.get('tool', 'Unknown')] += 1
            by_type[failure.get('failure_type', 'unknown')] += 1

        return {
            'total_failures': len(failures),
            'unique_types': len(set(f.get('failure_type', '') for f in failures)),
            'by_tool': dict(by_tool),
            'by_type': dict(by_type)
        }

    def update_kb_from_patterns(self, patterns: List[Dict]) -> Dict:
        """
        Update the global failure knowledge base with newly detected patterns.

        Args:
            patterns: List of pattern dictionaries to add/update in KB

        Returns:
            Updated knowledge base dictionary
        """
        kb = load_global_kb()

        for pattern in patterns:
            tool = pattern['tool']
            if tool not in kb:
                kb[tool] = []

            existing_idx = None
            for i, p in enumerate(kb[tool]):
                if p['pattern_id'] == pattern['pattern_id']:
                    existing_idx = i
                    break

            if existing_idx is not None:
                kb[tool][existing_idx]['frequency'] += pattern['frequency']
                kb[tool][existing_idx]['confidence'] = min(
                    1.0, kb[tool][existing_idx]['frequency'] / 10.0
                )
                kb[tool][existing_idx]['last_seen'] = pattern['last_seen']
            else:
                kb[tool].append(pattern)

        save_global_kb(kb)
        return kb

    def run_full_detection(self) -> Dict:
        """
        Run complete multi-layer failure detection across all log sources.

        Returns:
            Comprehensive detection report dictionary
        """
        failures_v1 = self.analyze_failure_log()
        prevented = self.analyze_policy_log()
        failures_v2 = self.analyze_all_logs_v2()

        report = self.generate_detection_report(failures_v1, prevented)
        report['v2_analysis'] = {
            'total_regex_failures': len(failures_v2),
            'statistics': self.get_statistics(failures_v2)
        }

        return report


# ===========================================================================
# SECTION 3: PRE-EXECUTION CHECKER CLASS
# Source: pre-execution-checker.py PreExecutionChecker (complete)
# ===========================================================================

class PreExecutionChecker:
    """
    Check and prevent tool call failures before execution by consulting
    the failure knowledge base.

    Source: pre-execution-checker.py - complete PreExecutionChecker class
    """

    def __init__(self):
        """Initialize checker with KB loaded from disk."""
        self.memory_dir = MEMORY_DIR
        self.kb_file = KB_FILE
        self.kb = self._load_kb()
        self.auto_fix_threshold = AUTO_FIX_THRESHOLD

    def _load_kb(self) -> Dict:
        """
        Load failure knowledge base from disk.

        Returns:
            KB dictionary or empty dict if not available
        """
        return load_global_kb()

    def reload_kb(self) -> None:
        """Reload the knowledge base from disk (refreshes in-memory cache)."""
        self.kb = self._load_kb()

    def check_bash_command(self, command: str) -> Dict:
        """
        Check a Bash command for known failure patterns and apply auto-fixes.

        Checks for Windows commands used in Unix context and translates them
        based on solutions stored in the knowledge base.

        Args:
            command: The bash command string to check

        Returns:
            Results dictionary with issues, fixed_command, auto_fix_applied
        """
        results = {
            'tool': 'Bash',
            'original_command': command,
            'issues': [],
            'fixed_command': command,
            'auto_fix_applied': False
        }

        if 'Bash' not in self.kb:
            return results

        bash_patterns = self.kb['Bash']
        for pattern in bash_patterns:
            if pattern['failure_type'] == 'bash_command_not_found':
                solution = pattern.get('solution', {})
                if solution.get('type') == 'translate':
                    mapping = solution.get('mapping', {})

                    for win_cmd, unix_cmd in mapping.items():
                        if re.search(rf'\b{re.escape(win_cmd)}\b', command):
                            results['issues'].append({
                                'type': 'windows_command',
                                'command': win_cmd,
                                'suggestion': unix_cmd,
                                'confidence': pattern['confidence']
                            })

                            if pattern['confidence'] >= self.auto_fix_threshold:
                                results['fixed_command'] = re.sub(
                                    rf'\b{re.escape(win_cmd)}\b',
                                    unix_cmd,
                                    results['fixed_command']
                                )
                                results['auto_fix_applied'] = True

        return results

    def check_edit_params(self, old_string: str) -> Dict:
        """
        Check Edit tool old_string parameter for known failure patterns.

        Detects line number prefixes that cause edit_string_not_found failures
        and strips them when confidence is high enough.

        Args:
            old_string: The old_string parameter value to check

        Returns:
            Results dictionary with issues, fixed_old_string, auto_fix_applied
        """
        results = {
            'tool': 'Edit',
            'original_old_string': old_string,
            'issues': [],
            'fixed_old_string': old_string,
            'auto_fix_applied': False
        }

        if 'Edit' not in self.kb:
            return results

        edit_patterns = self.kb['Edit']
        for pattern in edit_patterns:
            if pattern['failure_type'] == 'edit_string_not_found':
                solution = pattern.get('solution', {})
                if solution.get('type') == 'strip_prefix':
                    strip_pattern = solution.get('pattern')

                    if strip_pattern and re.match(strip_pattern, old_string):
                        results['issues'].append({
                            'type': 'line_number_prefix',
                            'pattern': strip_pattern,
                            'confidence': pattern['confidence']
                        })

                        if pattern['confidence'] >= self.auto_fix_threshold:
                            results['fixed_old_string'] = re.sub(
                                strip_pattern, '', old_string
                            )
                            results['auto_fix_applied'] = True

        return results

    def check_read_params(self, file_path: str, params: Dict) -> Dict:
        """
        Check Read tool parameters for large file issues.

        Detects when a large file is being read without offset/limit
        parameters and auto-adds them to prevent token limit failures.

        Args:
            file_path: Path to the file being read
            params: Full parameter dictionary for the Read tool

        Returns:
            Results dictionary with issues, fixed_params, auto_fix_applied
        """
        results = {
            'tool': 'Read',
            'file_path': file_path,
            'original_params': params,
            'issues': [],
            'fixed_params': params.copy(),
            'auto_fix_applied': False
        }

        try:
            file_path_obj = Path(file_path)
            if file_path_obj.exists():
                line_count = sum(
                    1 for _ in open(file_path, encoding='utf-8', errors='ignore')
                )

                if line_count > 500 and 'offset' not in params and 'limit' not in params:
                    results['issues'].append({
                        'type': 'file_too_large',
                        'line_count': line_count,
                        'suggestion': 'Add offset and limit parameters',
                        'confidence': 0.9
                    })

                    if 0.9 >= self.auto_fix_threshold:
                        results['fixed_params']['offset'] = 0
                        results['fixed_params']['limit'] = 500
                        results['auto_fix_applied'] = True
        except Exception:
            pass

        return results

    def check_grep_params(self, params: Dict) -> Dict:
        """
        Check Grep tool parameters for missing head_limit.

        Detects when head_limit is missing which can cause excessive output.

        Args:
            params: Full parameter dictionary for the Grep tool

        Returns:
            Results dictionary with issues, fixed_params, auto_fix_applied
        """
        results = {
            'tool': 'Grep',
            'original_params': params,
            'issues': [],
            'fixed_params': params.copy(),
            'auto_fix_applied': False
        }

        if 'head_limit' not in params or params['head_limit'] == 0:
            results['issues'].append({
                'type': 'missing_head_limit',
                'suggestion': 'Add head_limit parameter',
                'confidence': 0.8
            })

            if 0.8 >= self.auto_fix_threshold:
                results['fixed_params']['head_limit'] = 100
                results['auto_fix_applied'] = True

        return results

    def check_tool_call(self, tool: str, params: Dict) -> Dict:
        """
        Main entry point for checking any tool call before execution.

        Dispatches to the appropriate tool-specific checker based on tool name.

        Args:
            tool: Name of the tool (Bash, Edit, Read, Grep, etc.)
            params: Tool parameters dictionary

        Returns:
            Results dictionary appropriate for the tool type
        """
        if tool == 'Bash':
            command = params.get('command', '')
            return self.check_bash_command(command)
        elif tool == 'Edit':
            old_string = params.get('old_string', '')
            return self.check_edit_params(old_string)
        elif tool == 'Read':
            file_path = params.get('file_path', '')
            return self.check_read_params(file_path, params)
        elif tool == 'Grep':
            return self.check_grep_params(params)
        else:
            return {
                'tool': tool,
                'original_params': params,
                'issues': [],
                'auto_fix_applied': False
            }

    def get_kb_stats(self) -> Dict:
        """
        Get knowledge base statistics for monitoring and reporting.

        Returns:
            Statistics dictionary with total_patterns, by_tool, high_confidence
        """
        stats = {
            'total_patterns': 0,
            'by_tool': {},
            'high_confidence': 0
        }

        for tool, patterns in self.kb.items():
            stats['by_tool'][tool] = len(patterns)
            stats['total_patterns'] += len(patterns)

            for pattern in patterns:
                if pattern.get('confidence', 0) >= 0.75:
                    stats['high_confidence'] += 1

        return stats


# ===========================================================================
# SECTION 4: FAILURE LEARNER CLASS
# Source: failure-learner.py (complete)
# ===========================================================================

class FailureLearner:
    """
    Analyzes failure patterns and updates the knowledge base with learning
    about pattern progressions (monitoring -> learning -> confirmed -> global).

    Source: failure-learner.py - complete module logic
    """

    def __init__(self):
        """Initialize with learning thresholds from global config."""
        self.thresholds = LEARNING_THRESHOLDS
        self.memory_dir = MEMORY_DIR

    def analyze_pattern_progression(self, pattern_data: Dict, current_count: int) -> Dict:
        """
        Analyze pattern and determine status progression based on occurrence count.

        Progression states:
          monitoring -> learning -> confirmed -> global_candidate

        Args:
            pattern_data: Existing pattern data dictionary with current status
            current_count: Current occurrence count from detection

        Returns:
            Dictionary with new status, count, confidence, status_changed flag
        """
        old_status = pattern_data.get("status", "monitoring")

        if current_count >= self.thresholds["confirmed_to_global"]:
            new_status = "global_candidate"
        elif current_count >= self.thresholds["learning_to_confirmed"]:
            new_status = "confirmed"
        elif current_count >= self.thresholds["monitoring_to_learning"]:
            new_status = "learning"
        else:
            new_status = "monitoring"

        confidence = min(0.95, current_count / self.thresholds["confirmed_to_global"])

        return {
            "status": new_status,
            "count": current_count,
            "confidence": confidence,
            "status_changed": new_status != old_status,
            "old_status": old_status
        }

    def learn_from_detection(self, project_name: str, detection_results: Dict) -> Optional[Dict]:
        """
        Learn from detection results and update the project-specific KB.

        Processes each detected failure signature, calculates progression,
        and updates the project KB with new learning.

        Args:
            project_name: Name of the project to update KB for
            detection_results: Detection results from FailureDetector

        Returns:
            Learning result dictionary or None if learning failed
        """
        if not detection_results:
            print("No detection results to learn from")
            return None

        kb = load_project_kb(project_name)

        if "patterns" not in kb:
            kb["patterns"] = {}
        if "metadata" not in kb:
            kb["metadata"] = {}

        kb["metadata"]["last_learning"] = datetime.now().isoformat()
        kb["metadata"]["project"] = project_name

        failures_by_sig = detection_results.get("failures_by_signature", {})
        learned_patterns = []

        for signature, data in failures_by_sig.items():
            current_count = data.get("count", 0)

            if signature not in kb["patterns"]:
                kb["patterns"][signature] = {
                    "signature": signature,
                    "category": data.get("category", "unknown"),
                    "severity": data.get("severity", "low"),
                    "first_seen": data.get("first_seen"),
                    "last_seen": data.get("last_seen"),
                    "count": 0,
                    "status": "monitoring",
                    "confidence": 0.0,
                    "examples": []
                }

            pattern = kb["patterns"][signature]
            progression = self.analyze_pattern_progression(pattern, current_count)

            pattern["count"] = progression["count"]
            pattern["status"] = progression["status"]
            pattern["confidence"] = progression["confidence"]
            pattern["last_seen"] = data.get("last_seen")
            pattern["severity"] = data.get("severity", "low")

            if "examples" in data:
                pattern["examples"] = data["examples"][:3]

            if progression["status_changed"]:
                log_policy_hit(
                    "status-change",
                    f"{signature}: {progression['old_status']} -> {progression['status']} "
                    f"(count={current_count})"
                )

                learned_patterns.append({
                    "signature": signature,
                    "old_status": progression["old_status"],
                    "new_status": progression["status"],
                    "count": current_count,
                    "confidence": progression["confidence"]
                })

        if save_project_kb(project_name, kb):
            log_policy_hit(
                "kb-updated",
                f"project={project_name}, patterns={len(kb['patterns'])}, "
                f"learned={len(learned_patterns)}"
            )

        return {
            "project": project_name,
            "total_patterns": len(kb["patterns"]),
            "learned_patterns": learned_patterns,
            "kb_path": f"sessions/{project_name}/failures.json"
        }

    def find_global_candidates(self, project_name: str) -> List[Dict]:
        """
        Find patterns ready for promotion to the global knowledge base.

        Args:
            project_name: Project to check for promotion candidates

        Returns:
            List of pattern dictionaries that meet promotion criteria
        """
        kb = load_project_kb(project_name)
        patterns = kb.get("patterns", {})
        candidates = []

        for signature, pattern in patterns.items():
            if (pattern.get("status") == "global_candidate" and
                    pattern.get("confidence", 0) >= self.thresholds["confidence_threshold"]):
                candidates.append({
                    "signature": signature,
                    "count": pattern.get("count", 0),
                    "confidence": pattern.get("confidence", 0),
                    "severity": pattern.get("severity", "low"),
                    "category": pattern.get("category", "unknown"),
                    "examples": pattern.get("examples", [])
                })

        return candidates

    def promote_to_global(self, candidates: List[Dict]) -> int:
        """
        Promote confirmed patterns to the global knowledge base.

        Args:
            candidates: List of candidate pattern dictionaries

        Returns:
            Number of patterns successfully promoted
        """
        if not candidates:
            print("No candidates for promotion")
            return 0

        print(f"Promoting {len(candidates)} patterns to global KB...")
        promoted = 0

        for candidate in candidates:
            print(f"  [CHECK] {candidate['signature']} (confidence: {candidate['confidence']:.1%})")
            promoted += 1

        if promoted > 0:
            log_policy_hit("promoted-to-global", f"{promoted} patterns promoted")

        return promoted


# ===========================================================================
# SECTION 5: FAILURE SOLUTION LEARNER CLASS
# Source: failure-solution-learner.py FailureSolutionLearner (complete)
# ===========================================================================

class FailureSolutionLearner:
    """
    Learns solutions from successful fixes and updates the knowledge base
    with solution mappings and confidence reinforcement.

    Source: failure-solution-learner.py - complete FailureSolutionLearner class
    """

    def __init__(self):
        """Initialize with KB and learning log paths."""
        self.memory_dir = MEMORY_DIR
        self.kb_file = KB_FILE
        self.learning_log = SOLUTION_LEARNING_LOG
        self.learning_log.parent.mkdir(parents=True, exist_ok=True)

    def load_kb(self) -> Dict:
        """
        Load knowledge base from disk.

        Returns:
            KB dictionary or empty dict
        """
        return load_global_kb()

    def save_kb(self, kb: Dict) -> None:
        """
        Save knowledge base to disk.

        Args:
            kb: Knowledge base dictionary to persist
        """
        save_global_kb(kb)

    def learn_solution(
        self,
        tool: str,
        failure_type: str,
        solution: Dict,
        confidence: float = 0.8
    ) -> Dict:
        """
        Learn a solution for a specific failure type and tool combination.

        If the pattern already exists, the solution is updated and confidence
        increased. If new, the pattern is added to the KB.

        Args:
            tool: Tool name (Bash, Edit, Read, Grep)
            failure_type: Type of failure being solved
            solution: Solution dictionary with type and description
            confidence: Initial confidence level (0.0 - 1.0)

        Returns:
            Updated knowledge base dictionary
        """
        kb = self.load_kb()

        if tool not in kb:
            kb[tool] = []

        pattern_id = f"{tool.lower()}_{failure_type.lower()}"
        existing_idx = None
        for i, pattern in enumerate(kb[tool]):
            if pattern['pattern_id'] == pattern_id:
                existing_idx = i
                break

        if existing_idx is not None:
            kb[tool][existing_idx]['solution'] = solution
            kb[tool][existing_idx]['confidence'] = min(
                1.0, kb[tool][existing_idx]['confidence'] + 0.1
            )
            kb[tool][existing_idx]['frequency'] = (
                kb[tool][existing_idx].get('frequency', 0) + 1
            )
            log_learning_event(
                'SOLUTION_UPDATED',
                f"{pattern_id} | confidence={kb[tool][existing_idx]['confidence']}"
            )
        else:
            new_pattern = {
                'pattern_id': pattern_id,
                'failure_type': failure_type,
                'tool': tool,
                'solution': solution,
                'confidence': confidence,
                'frequency': 1,
                'learned_at': datetime.now().isoformat()
            }
            kb[tool].append(new_pattern)
            log_learning_event(
                'SOLUTION_LEARNED',
                f"{pattern_id} | confidence={confidence}"
            )

        self.save_kb(kb)
        return kb

    def learn_from_fix(
        self,
        tool: str,
        failure_message: str,
        fix_applied: str
    ) -> Optional[Dict]:
        """
        Learn from a successful fix by detecting failure type and building solution.

        Analyzes the failure message to determine the failure type, then
        creates a structured solution from the fix description.

        Args:
            tool: Tool that experienced the failure
            failure_message: The error message that was produced
            fix_applied: Description of the fix that resolved the failure

        Returns:
            Updated KB dictionary or None if failure type not recognized
        """
        failure_type = self._detect_failure_type(failure_message)
        if not failure_type:
            return None

        solution = self._create_solution_from_fix(fix_applied)
        if not solution:
            return None

        return self.learn_solution(tool, failure_type, solution)

    def _detect_failure_type(self, message: str) -> Optional[str]:
        """
        Detect failure type from an error message string.

        Args:
            message: Error message to classify

        Returns:
            Failure type string or None if unrecognized
        """
        message_lower = message.lower()

        if 'command not found' in message_lower:
            return 'command_not_found'
        elif 'string to replace not found' in message_lower or 'string not found' in message_lower:
            return 'string_not_found'
        elif 'file too large' in message_lower or 'exceeds maximum' in message_lower:
            return 'file_too_large'
        elif 'no matches' in message_lower:
            return 'no_matches'
        elif 'permission denied' in message_lower:
            return 'permission_denied'
        elif 'not a git repository' in message_lower:
            return 'not_git_repository'
        elif 'unicode' in message_lower or 'encoding' in message_lower:
            return 'encoding_error'
        elif 'module not found' in message_lower or 'no module named' in message_lower:
            return 'module_not_found'
        elif 'syntax error' in message_lower:
            return 'syntax_error'
        else:
            return None

    def _create_solution_from_fix(self, fix: str) -> Optional[Dict]:
        """
        Create a structured solution dictionary from a fix description string.

        Args:
            fix: Human-readable description of the fix applied

        Returns:
            Solution dictionary with type and description, or None if empty
        """
        if not fix:
            return None

        fix_lower = fix.lower()

        if 'translate' in fix_lower or 'replace' in fix_lower:
            return {'type': 'translate', 'description': fix}
        elif 'strip' in fix_lower or 'remove prefix' in fix_lower:
            return {'type': 'strip_prefix', 'description': fix}
        elif 'add offset' in fix_lower or 'add limit' in fix_lower:
            return {'type': 'add_params', 'description': fix}
        elif 'encoding' in fix_lower or 'unicode' in fix_lower:
            return {'type': 'encoding_fix', 'description': fix}
        else:
            return {'type': 'custom', 'description': fix}

    def reinforce_solution(self, pattern_id: str) -> Optional[Dict]:
        """
        Reinforce a solution when it is successfully applied.

        Increases confidence and frequency count for the given pattern,
        indicating the solution is working well in practice.

        Args:
            pattern_id: The pattern_id string to reinforce

        Returns:
            Updated pattern dictionary or None if pattern not found
        """
        kb = self.load_kb()

        for tool, patterns in kb.items():
            for pattern in patterns:
                if pattern['pattern_id'] == pattern_id:
                    pattern['frequency'] = pattern.get('frequency', 0) + 1
                    pattern['confidence'] = min(1.0, pattern['confidence'] + 0.05)

                    log_learning_event(
                        'SOLUTION_REINFORCED',
                        f"{pattern_id} | confidence={pattern['confidence']}"
                    )

                    self.save_kb(kb)
                    return pattern

        return None

    def get_learning_stats(self) -> Dict:
        """
        Get comprehensive statistics about the solution learning system.

        Returns:
            Statistics dictionary with totals, confidence distribution,
            and recently learned patterns
        """
        kb = self.load_kb()

        stats = {
            'total_patterns': 0,
            'by_tool': {},
            'by_confidence': {
                'high': 0,
                'medium': 0,
                'low': 0
            },
            'recently_learned': []
        }

        for tool, patterns in kb.items():
            stats['by_tool'][tool] = len(patterns)
            stats['total_patterns'] += len(patterns)

            for pattern in patterns:
                confidence = pattern.get('confidence', 0)
                if confidence >= 0.8:
                    stats['by_confidence']['high'] += 1
                elif confidence >= 0.5:
                    stats['by_confidence']['medium'] += 1
                else:
                    stats['by_confidence']['low'] += 1

                if 'learned_at' in pattern:
                    stats['recently_learned'].append({
                        'pattern_id': pattern['pattern_id'],
                        'tool': tool,
                        'learned_at': pattern['learned_at'],
                        'confidence': confidence
                    })

        stats['recently_learned'].sort(key=lambda x: x['learned_at'], reverse=True)
        stats['recently_learned'] = stats['recently_learned'][:10]

        return stats


# ===========================================================================
# SECTION 6: FAILURE PATTERN EXTRACTOR CLASS
# Source: failure-pattern-extractor.py FailurePatternExtractor (complete)
# ===========================================================================

class FailurePatternExtractor:
    """
    Analyzes failures to identify common patterns, calculate confidence scores,
    and suggest solutions for recurring failure types.

    Source: failure-pattern-extractor.py - complete FailurePatternExtractor class
    """

    def __init__(self):
        """Initialize with path to failures log."""
        self.memory_dir = MEMORY_DIR
        self.failures_log = FAILURES_LOG

    def load_failures(self) -> List[Dict]:
        """
        Load raw failure records from the failures log file.

        Parses the log format: [timestamp] TYPE | STATUS | details

        Returns:
            List of failure dictionaries with timestamp, type, status, details
        """
        if not self.failures_log.exists():
            return []

        failures = []
        try:
            with open(self.failures_log, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    parts = line.split('|')
                    if len(parts) >= 3:
                        failures.append({
                            'timestamp': parts[0].strip(),
                            'type': parts[1].strip(),
                            'status': parts[2].strip() if len(parts) > 2 else '',
                            'details': parts[3].strip() if len(parts) > 3 else '',
                            'raw': line
                        })
        except Exception:
            pass

        return failures

    def extract_tool_from_type(self, failure_type: str) -> str:
        """
        Extract tool name from a failure type string.

        Uses underscore convention: bash_command_not_found -> Bash

        Args:
            failure_type: Failure type string in snake_case

        Returns:
            Capitalized tool name or 'Unknown'
        """
        if '_' in failure_type:
            parts = failure_type.split('_')
            return parts[0].capitalize()
        return 'Unknown'

    def group_by_similarity(self, failures: List[Dict]) -> Dict:
        """
        Group failures by type and analyze similarity within groups.

        Args:
            failures: List of raw failure dictionaries

        Returns:
            Dictionary keyed by failure_type with count, common_patterns, samples
        """
        by_type = defaultdict(list)
        for failure in failures:
            by_type[failure['type']].append(failure)

        grouped = {}
        for failure_type, failure_list in by_type.items():
            details_list = [f['details'] for f in failure_list]
            common = self._find_common_patterns(details_list)

            grouped[failure_type] = {
                'count': len(failure_list),
                'common_patterns': common,
                'samples': failure_list[:5]
            }

        return grouped

    def _find_common_patterns(self, strings: List[str]) -> List[str]:
        """
        Find common word patterns appearing in multiple strings.

        Uses a 30% threshold: words must appear in at least 30% of strings.

        Args:
            strings: List of strings to analyze

        Returns:
            List of common words/patterns
        """
        if not strings:
            return []

        word_counts = Counter()
        for s in strings:
            words = set(re.findall(r'\b\w+\b', s))
            word_counts.update(words)

        threshold = max(1, len(strings) * 0.3)
        return [word for word, count in word_counts.items() if count >= threshold]

    def calculate_confidence(self, pattern_data: Dict) -> float:
        """
        Calculate confidence score for a pattern based on occurrence count.

        Confidence tiers:
          >= 10 occurrences: 1.0
          >= 5 occurrences:  0.8
          >= 3 occurrences:  0.6
          < 3 occurrences:   0.4

        Args:
            pattern_data: Pattern dictionary with count field

        Returns:
            Confidence score between 0.0 and 1.0
        """
        count = pattern_data.get('count', 0)

        if count >= 10:
            return 1.0
        elif count >= 5:
            return 0.8
        elif count >= 3:
            return 0.6
        else:
            return 0.4

    def extract_patterns(self) -> List[Dict]:
        """
        Extract all failure patterns from the failures log.

        Loads failures, groups by similarity, and builds structured pattern
        objects with frequency, confidence, and sample failures.

        Returns:
            List of pattern dictionaries sorted by frequency (descending)
        """
        failures = self.load_failures()
        if not failures:
            return []

        grouped = self.group_by_similarity(failures)
        patterns = []

        for failure_type, data in grouped.items():
            tool = self.extract_tool_from_type(failure_type)

            pattern = {
                'pattern_id': failure_type.lower(),
                'failure_type': failure_type,
                'tool': tool,
                'frequency': data['count'],
                'confidence': self.calculate_confidence(data),
                'common_patterns': data['common_patterns'],
                'sample_failures': [
                    {
                        'timestamp': f['timestamp'],
                        'details': f['details']
                    }
                    for f in data['samples']
                ]
            }
            patterns.append(pattern)

        patterns.sort(key=lambda x: x['frequency'], reverse=True)
        return patterns

    def suggest_solutions(self, pattern: Dict) -> List[Dict]:
        """
        Suggest solutions for a given failure pattern.

        Uses known solution mappings based on failure type keywords.

        Args:
            pattern: Pattern dictionary with failure_type field

        Returns:
            List of solution suggestion dictionaries
        """
        suggestions = []
        failure_type = pattern['failure_type'].lower()

        if 'command_not_found' in failure_type:
            suggestions.append({
                'type': 'translate',
                'description': 'Translate Windows command to Unix equivalent',
                'action': 'Add command mapping to KB'
            })
        elif 'string_not_found' in failure_type:
            suggestions.append({
                'type': 'strip_prefix',
                'description': 'Remove line number prefixes',
                'action': 'Strip line number prefix before edit'
            })
        elif 'file_too_large' in failure_type:
            suggestions.append({
                'type': 'add_params',
                'description': 'Add offset/limit parameters',
                'action': 'Force offset/limit for large files'
            })
        elif 'no_matches' in failure_type:
            suggestions.append({
                'type': 'improve_pattern',
                'description': 'Pattern too specific or incorrect',
                'action': 'Review and improve search pattern'
            })
        elif 'encoding' in failure_type or 'unicode' in failure_type:
            suggestions.append({
                'type': 'encoding_fix',
                'description': 'Replace Unicode characters with ASCII equivalents',
                'action': 'Run WindowsPythonUnicodeChecker.auto_fix_unicode()'
            })
        elif 'permission' in failure_type:
            suggestions.append({
                'type': 'permissions',
                'description': 'Insufficient file or directory permissions',
                'action': 'Check and fix file permissions before operation'
            })
        elif 'git' in failure_type:
            suggestions.append({
                'type': 'git_check',
                'description': 'Ensure working directory is a git repository',
                'action': 'Verify git repo exists before git operations'
            })
        elif 'module' in failure_type or 'import' in failure_type:
            suggestions.append({
                'type': 'dependency',
                'description': 'Required Python module not installed',
                'action': 'Run pip install for missing module'
            })
        else:
            suggestions.append({
                'type': 'manual_review',
                'description': 'Requires manual analysis',
                'action': 'Review failure details'
            })

        return suggestions


# ===========================================================================
# SECTION 7: FAILURE KB MANAGER CLASS
# Source: update-failure-kb.py FailurePattern + FailureKB classes (complete)
# ===========================================================================

class FailurePattern:
    """
    Data model for a single failure pattern in the project-specific KB.

    Source: update-failure-kb.py FailurePattern class (complete)
    """

    def __init__(self, signature: str, details: str):
        """
        Initialize a new FailurePattern.

        Args:
            signature: Unique signature string identifying this failure type
            details: Human-readable description of the failure
        """
        self.signature = signature
        self.details = details
        self.frequency = 1
        self.first_seen = datetime.now()
        self.last_seen = datetime.now()
        self.status = "Monitoring"  # Monitoring -> Learning -> Confirmed -> Global
        self.confidence = 0.0
        self.solution = None
        self.preventions_successful = 0
        self.preventions_attempted = 0

    def to_dict(self) -> Dict:
        """
        Serialize the pattern to a dictionary for JSON storage.

        Returns:
            Dictionary representation of this pattern
        """
        return {
            'signature': self.signature,
            'details': self.details,
            'frequency': self.frequency,
            'first_seen': self.first_seen.isoformat(),
            'last_seen': self.last_seen.isoformat(),
            'status': self.status,
            'confidence': self.confidence,
            'solution': self.solution,
            'preventions_successful': self.preventions_successful,
            'preventions_attempted': self.preventions_attempted
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'FailurePattern':
        """
        Deserialize a FailurePattern from a dictionary.

        Args:
            data: Dictionary containing pattern fields

        Returns:
            FailurePattern instance populated from data
        """
        pattern = cls(data['signature'], data['details'])
        pattern.frequency = data['frequency']
        pattern.first_seen = datetime.fromisoformat(data['first_seen'])
        pattern.last_seen = datetime.fromisoformat(data['last_seen'])
        pattern.status = data['status']
        pattern.confidence = data['confidence']
        pattern.solution = data.get('solution')
        pattern.preventions_successful = data.get('preventions_successful', 0)
        pattern.preventions_attempted = data.get('preventions_attempted', 0)
        return pattern


class FailureKBManager:
    """
    Manages project-specific failure knowledge base with pattern lifecycle
    management (Monitoring -> Learning -> Confirmed -> Global promotion).

    Source: update-failure-kb.py FailureKB class (complete)
    """

    def __init__(self, project_name: str):
        """
        Initialize the KB manager for a specific project.

        Args:
            project_name: Name of the project this KB belongs to
        """
        self.project_name = project_name
        self.home = Path.home()
        self.session_dir = SESSIONS_DIR / project_name
        self.failures_file = self.session_dir / "failures.md"
        self.failures_json = self.session_dir / "failures.json"
        self.global_kb_md = GLOBAL_KB_MD
        self.patterns: Dict[str, FailurePattern] = {}

        self._load()

    def _load(self) -> None:
        """Load existing patterns from JSON storage on disk."""
        if self.failures_json.exists():
            try:
                with open(self.failures_json, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for pattern_data in data.get('patterns', []):
                        pattern = FailurePattern.from_dict(pattern_data)
                        self.patterns[pattern.signature] = pattern
            except Exception as e:
                print(f"Warning: Could not load KB: {e}", file=sys.stderr)

    def _save(self) -> None:
        """Save patterns to JSON and regenerate markdown report."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        with open(self.failures_json, 'w', encoding='utf-8') as f:
            json.dump({
                'project': self.project_name,
                'last_updated': datetime.now().isoformat(),
                'patterns': [p.to_dict() for p in self.patterns.values()]
            }, f, indent=2)

        self._generate_markdown()

    def _generate_markdown(self) -> None:
        """Generate a human-readable markdown report of current KB state."""
        total_failures = sum(p.frequency for p in self.patterns.values())
        active_patterns = [
            p for p in self.patterns.values()
            if p.status in ['Confirmed', 'Learning']
        ]
        confirmed_patterns = [p for p in self.patterns.values() if p.status == 'Confirmed']
        monitoring_patterns = [p for p in self.patterns.values() if p.status == 'Monitoring']

        total_preventions = sum(p.preventions_attempted for p in self.patterns.values())
        successful_preventions = sum(p.preventions_successful for p in self.patterns.values())
        prevention_rate = (
            (successful_preventions / total_preventions * 100)
            if total_preventions > 0 else 0
        )

        try:
            with open(self.failures_file, 'w', encoding='utf-8') as f:
                f.write(f"# Failure Memory: {self.project_name}\n\n")
                f.write(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"**Total Failures Recorded:** {total_failures}\n")
                f.write(f"**Patterns Learned:** {len(self.patterns)}\n")
                f.write(f"**Prevention Success Rate:** {prevention_rate:.1f}%\n\n")
                f.write("---\n\n")

                f.write("## Quick Stats\n\n")
                f.write("| Metric | Value |\n")
                f.write("|--------|-------|\n")
                f.write(f"| Total Failures | {total_failures} |\n")
                f.write(f"| Active Patterns | {len(active_patterns)} |\n")
                f.write(f"| Confirmed Patterns | {len(confirmed_patterns)} |\n")
                f.write(f"| Under Observation | {len(monitoring_patterns)} |\n")
                f.write(f"| Prevention Success Rate | {prevention_rate:.1f}% |\n\n")
                f.write("---\n\n")

                f.write("## Active Patterns (Auto-Applied)\n\n")
                if confirmed_patterns:
                    for pattern in confirmed_patterns:
                        f.write(f"### {pattern.signature}\n\n")
                        f.write(f"**Status:** Confirmed\n")
                        f.write(f"**Frequency:** {pattern.frequency} occurrences\n")
                        f.write(f"**Confidence:** {pattern.confidence:.0f}%\n")
                        f.write(f"**First Seen:** {pattern.first_seen.strftime('%Y-%m-%d')}\n")
                        if pattern.solution:
                            f.write(f"**Solution:** {pattern.solution}\n")
                        f.write(
                            f"**Prevention Stats:** "
                            f"{pattern.preventions_successful}/{pattern.preventions_attempted} "
                            f"successful\n\n"
                        )
                        f.write(f"**Details:** {pattern.details}\n\n")
                        f.write("---\n\n")
                else:
                    f.write("*(No confirmed patterns yet)*\n\n")

                f.write("## Learning Patterns (Being Validated)\n\n")
                learning_patterns = [
                    p for p in self.patterns.values() if p.status == 'Learning'
                ]
                if learning_patterns:
                    for pattern in learning_patterns:
                        f.write(f"### {pattern.signature}\n\n")
                        f.write(f"**Status:** Learning\n")
                        f.write(f"**Frequency:** {pattern.frequency} occurrences\n")
                        f.write(f"**First Seen:** {pattern.first_seen.strftime('%Y-%m-%d')}\n")
                        f.write(f"**Details:** {pattern.details}\n\n")
                        f.write("---\n\n")
                else:
                    f.write("*(No learning patterns)*\n\n")

                f.write("## Failed Attempts (Under Observation)\n\n")
                if monitoring_patterns:
                    for pattern in monitoring_patterns:
                        f.write(f"### {pattern.signature}\n\n")
                        f.write(f"**Status:** Monitoring\n")
                        f.write(f"**First Seen:** {pattern.first_seen.strftime('%Y-%m-%d')}\n")
                        f.write(f"**Details:** {pattern.details}\n\n")
                        f.write("*Waiting for 2nd occurrence to confirm pattern...*\n\n")
                        f.write("---\n\n")
                else:
                    f.write("*(No patterns under observation)*\n\n")

        except Exception as e:
            print(f"Warning: Could not generate markdown report: {e}", file=sys.stderr)

    def log_failure(
        self,
        signature: str,
        details: str,
        solution: Optional[str] = None
    ) -> str:
        """
        Log a new failure or update an existing pattern.

        Handles the full pattern lifecycle: new patterns start as Monitoring,
        advance to Learning at 2 occurrences, Confirmed at 3+ with high confidence.

        Args:
            signature: Unique failure signature string
            details: Human-readable failure description
            solution: Optional solution string if known

        Returns:
            Status message describing what was logged/updated
        """
        if signature in self.patterns:
            pattern = self.patterns[signature]
            pattern.frequency += 1
            pattern.last_seen = datetime.now()

            if pattern.frequency >= 2 and pattern.status == 'Monitoring':
                pattern.status = 'Learning'
            elif pattern.frequency >= 3 and pattern.status == 'Learning':
                if pattern.confidence >= 80:
                    pattern.status = 'Confirmed'

            if solution:
                pattern.solution = solution

            self._save()
            return (
                f"Pattern updated: {signature} "
                f"(frequency: {pattern.frequency}, status: {pattern.status})"
            )
        else:
            pattern = FailurePattern(signature, details)
            if solution:
                pattern.solution = solution
            self.patterns[signature] = pattern
            self._save()
            return f"New pattern logged: {signature} (status: Monitoring)"

    def log_prevention(self, signature: str, success: bool) -> None:
        """
        Log a prevention attempt for tracking effectiveness.

        Updates prevention counters and recalculates confidence based on
        the ratio of successful to total preventions.

        Args:
            signature: Failure signature that prevention was attempted for
            success: Whether the prevention was successful
        """
        if signature in self.patterns:
            pattern = self.patterns[signature]
            pattern.preventions_attempted += 1
            if success:
                pattern.preventions_successful += 1
            pattern.confidence = (
                (pattern.preventions_successful / pattern.preventions_attempted) * 100
            )
            self._save()

    def check_pattern(self, signature: str) -> Optional[Dict]:
        """
        Check if a pattern exists and return its solution if available.

        Only returns solutions for patterns in Learning or Confirmed state
        with confidence >= 80%.

        Args:
            signature: Failure signature to look up

        Returns:
            Solution dictionary or None if pattern not found/not ready
        """
        if signature in self.patterns:
            pattern = self.patterns[signature]
            if pattern.status in ['Learning', 'Confirmed'] and pattern.confidence >= 80:
                return {
                    'found': True,
                    'solution': pattern.solution,
                    'confidence': pattern.confidence,
                    'status': pattern.status
                }
        return None

    def check_promotion_eligibility(self) -> List[str]:
        """
        Check which patterns are eligible for global KB promotion.

        Criteria: status=Confirmed, confidence=100%, frequency>=5

        Returns:
            List of signature strings eligible for promotion
        """
        eligible = []
        for signature, pattern in self.patterns.items():
            if (pattern.status == 'Confirmed' and
                    pattern.confidence == 100 and
                    pattern.frequency >= 5):
                eligible.append(signature)
        return eligible


# ===========================================================================
# SECTION 8: WINDOWS PYTHON UNICODE CHECKER CLASS
# Source: windows-python-unicode-checker.py (complete)
# ===========================================================================

class WindowsPythonUnicodeChecker:
    """
    Prevents UnicodeEncodeError by detecting and optionally fixing Unicode
    characters in Python files before execution on Windows.

    Source: windows-python-unicode-checker.py - complete module logic
    """

    def __init__(self):
        """Initialize with the global Unicode replacement map."""
        self.replacements = UNICODE_REPLACEMENTS

    def is_windows(self) -> bool:
        """
        Check if the current platform is Windows.

        Returns:
            True if running on Windows (win32), False otherwise
        """
        return sys.platform == 'win32'

    def check_file_for_unicode(self, file_path: str) -> Dict:
        """
        Check a Python file for Unicode characters that will cause issues on Windows.

        Only checks .py files and only reports issues on Windows platforms.
        On non-Windows platforms, returns a SKIP status.

        Args:
            file_path: Path to the Python file to check

        Returns:
            Result dictionary with status (PASS/FAIL/SKIP/ERROR) and details
        """
        if not self.is_windows():
            return {'status': 'SKIP', 'reason': 'Not Windows - Unicode allowed'}

        if not file_path.endswith('.py'):
            return {'status': 'SKIP', 'reason': 'Not a Python file'}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            unicode_chars = re.findall(r'[\u0080-\uffff]', content)

            if not unicode_chars:
                return {'status': 'PASS', 'reason': 'No Unicode characters found'}

            unique_chars = set(unicode_chars)
            char_details = []

            for char in unique_chars:
                replacement = self.replacements.get(char, '[?]')
                count = content.count(char)
                char_details.append({
                    'char': char,
                    'unicode': f'U+{ord(char):04X}',
                    'replacement': replacement,
                    'count': count
                })

            return {
                'status': 'FAIL',
                'reason': (
                    f'Found {len(unique_chars)} Unicode characters that will cause '
                    f'UnicodeEncodeError on Windows'
                ),
                'file': file_path,
                'characters': char_details,
                'total_occurrences': len(unicode_chars)
            }

        except Exception as e:
            return {'status': 'ERROR', 'reason': str(e)}

    def auto_fix_unicode(self, file_path: str, backup: bool = True) -> bool:
        """
        Automatically fix Unicode characters in a Python file.

        Replaces all known Unicode characters with ASCII equivalents.
        Optionally creates a backup before modifying.

        Args:
            file_path: Path to the Python file to fix
            backup: Whether to create a .backup-unicode backup file first

        Returns:
            True if fixes were applied, False otherwise
        """
        if not self.is_windows():
            print("[INFO] Not Windows - no fix needed")
            return False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if backup:
                backup_path = file_path + '.backup-unicode'
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"[BACKUP] Created backup: {backup_path}")

            original_content = content
            replacements_made = 0

            for unicode_char, ascii_replacement in self.replacements.items():
                if unicode_char in content:
                    count = content.count(unicode_char)
                    content = content.replace(unicode_char, ascii_replacement)
                    replacements_made += count
                    print(
                        f"[FIX] Replaced {count}x "
                        f"(U+{ord(unicode_char):04X}) with '{ascii_replacement}'"
                    )

            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"[OK] Fixed {replacements_made} Unicode characters in {file_path}")
                return True
            else:
                print("[INFO] No replacements needed")
                return False

        except Exception as e:
            print(f"[ERROR] Failed to fix file: {e}")
            return False

    def scan_directory(self, directory: str) -> List[Tuple[str, Dict]]:
        """
        Scan a directory recursively for Python files with Unicode issues.

        Args:
            directory: Path to directory to scan

        Returns:
            List of (file_path, result) tuples for files with issues
        """
        found_issues = []
        try:
            python_files = Path(directory).rglob('*.py')
            for py_file in python_files:
                result = self.check_file_for_unicode(str(py_file))
                if result['status'] == 'FAIL':
                    found_issues.append((str(py_file), result))
        except Exception as e:
            print(f"[ERROR] Scan failed: {e}")
        return found_issues

    def sanitize_text(self, text: str) -> str:
        """
        Replace problematic Unicode characters in a text string.

        Args:
            text: Input string to sanitize

        Returns:
            String with Unicode characters replaced by ASCII equivalents
        """
        if not isinstance(text, str):
            return text
        result = text
        for unicode_char, replacement in self.replacements.items():
            result = result.replace(unicode_char, replacement)
        return result

    def check_unicode_compatibility(self, text: str) -> List[Dict]:
        """
        Check if a text string contains problematic Unicode characters.

        Args:
            text: Text to analyze

        Returns:
            List of issue dictionaries with character, replacement, occurrences
        """
        issues = []
        for unicode_char, replacement in self.replacements.items():
            if unicode_char in text:
                issues.append({
                    "character": unicode_char,
                    "replacement": replacement,
                    "occurrences": text.count(unicode_char)
                })
        return issues


# ===========================================================================
# SECTION 9: COMMON FAILURES PREVENTION POLICY (UNIFIED INTERFACE)
# The main policy class that orchestrates all subsystems
# ===========================================================================

class CommonFailuresPreventionPolicy:
    """
    Unified policy interface for the enterprise failure prevention system.

    Orchestrates all 8 subsystems:
      1. FailureDetector           - Multi-layer detection
      2. PreExecutionChecker       - Pre-execution validation
      3. FailureLearner            - Pattern learning
      4. FailureSolutionLearner    - Solution learning
      5. FailurePatternExtractor   - Pattern extraction
      6. FailureKBManager          - KB management
      7. WindowsPythonUnicodeChecker - Unicode prevention

    Provides the standard policy interface:
      enforce()   - Initialize all subsystems and run full enforcement
      validate()  - Check system compliance and readiness
      report()    - Generate comprehensive failure statistics
    """

    def __init__(self):
        """Initialize all failure prevention subsystems."""
        self.detector = FailureDetector()
        self.checker = PreExecutionChecker()
        self.learner = FailureLearner()
        self.solution_learner = FailureSolutionLearner()
        self.extractor = FailurePatternExtractor()
        self.unicode_checker = WindowsPythonUnicodeChecker()

    def enforce(self) -> Dict:
        """
        Run full policy enforcement across all failure prevention subsystems.

        Steps:
          1. Load and validate failure KB
          2. Run multi-layer failure detection on all logs
          3. Generate detection report and save to disk
          4. Run pattern learning analysis
          5. Update project-specific KB with learning results
          6. Report enforcement summary

        Returns:
            Dictionary with status, kb_patterns, detected_failures,
            prevented_failures, learning_patterns
        """
        _track_start_time = datetime.now()
        _sub_operations = []
        try:
            log_policy_hit("ENFORCE_START", "common-failures-prevention-enforcement")

            # Step 1: Load failure KB and validate
            _op_start = datetime.now()
            self.checker.reload_kb()
            kb_stats = self.checker.get_kb_stats()
            log_policy_hit("KB_LOADED", f"{kb_stats['total_patterns']} patterns loaded")
            try:
                _sub_operations.append(record_sub_operation(
                    "load_failure_kb", "success",
                    int((datetime.now() - _op_start).total_seconds() * 1000),
                    {"kb_patterns": kb_stats['total_patterns']}
                ))
            except Exception:
                pass

            # Step 2: Run full detection (both keyword and regex)
            _op_start = datetime.now()
            failures_v1 = self.detector.analyze_failure_log()
            prevented = self.detector.analyze_policy_log()
            failures_v2 = self.detector.analyze_all_logs_v2()

            log_policy_hit(
                "ANALYSIS_COMPLETE",
                f"{len(failures_v1)} keyword-failures, "
                f"{len(failures_v2)} regex-failures, "
                f"{len(prevented)} prevented"
            )
            try:
                _sub_operations.append(record_sub_operation(
                    "run_failure_detection", "success",
                    int((datetime.now() - _op_start).total_seconds() * 1000),
                    {"failures_v1": len(failures_v1), "failures_v2": len(failures_v2), "prevented": len(prevented)}
                ))
            except Exception:
                pass

            # Step 3: Generate and save detection report
            report_data = self.detector.generate_detection_report(failures_v1, prevented)
            report_data['v2_statistics'] = self.detector.get_statistics(failures_v2)
            save_detection_output(report_data)

            # Step 4: Run pattern extraction
            _op_start = datetime.now()
            patterns = self.extractor.extract_patterns()
            try:
                _sub_operations.append(record_sub_operation(
                    "extract_patterns", "success",
                    int((datetime.now() - _op_start).total_seconds() * 1000),
                    {"extracted_patterns": len(patterns)}
                ))
            except Exception:
                pass

            # Step 5: Update project KB with learning results
            project = get_current_project()
            learning_result = None
            if project:
                learning_result = self.learner.learn_from_detection(project, report_data)

            # Step 6: Update global KB from v2 patterns
            if failures_v2:
                grouped = self.detector.group_failures_v2(failures_v2)
                v2_patterns = self.detector.extract_pattern_data_v2(grouped)
                if v2_patterns:
                    self.detector.update_kb_from_patterns(v2_patterns)

            learned_count = len(learning_result.get('learned_patterns', [])) if learning_result else 0
            log_policy_hit(
                "ENFORCE_COMPLETE",
                f"Enforcement complete - {len(patterns)} patterns extracted, "
                f"{learned_count} learned"
            )
            print(
                f"[common-failures-prevention] Policy enforced - "
                f"{len(patterns)} patterns extracted"
            )

            result = {
                "status": "success",
                "kb_patterns": kb_stats['total_patterns'],
                "detected_failures": len(failures_v1),
                "regex_failures": len(failures_v2),
                "prevented_failures": len(prevented),
                "extracted_patterns": len(patterns),
                "learning_patterns": learned_count
            }
            try:
                if HAS_TRACKING:
                    record_policy_execution(
                        session_id=os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
                        policy_name="common-failures-prevention",
                        policy_script="common-failures-prevention.py",
                        policy_type="Policy Script",
                        input_params={},
                        output_results=result,
                        decision=f"detected {len(failures_v1)} failures, extracted {len(patterns)} patterns",
                        duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                        sub_operations=_sub_operations if _sub_operations else None
                    )
            except Exception:
                pass
            return result

        except Exception as e:
            log_policy_hit("ENFORCE_ERROR", str(e))
            print(f"[common-failures-prevention] ERROR: {e}")
            error_result = {"status": "error", "message": str(e)}
            try:
                if HAS_TRACKING:
                    record_policy_execution(
                        session_id=os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
                        policy_name="common-failures-prevention",
                        policy_script="common-failures-prevention.py",
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

    def validate(self) -> bool:
        """
        Validate policy compliance and system readiness.

        Checks that all required directories and files are accessible,
        and that the KB can be loaded without errors.

        Returns:
            True if all validation checks pass, False otherwise
        """
        try:
            log_policy_hit("VALIDATE", "failure-prevention-ready")

            # Check required directories exist or can be created
            for directory in [MEMORY_DIR, LOGS_DIR, SESSIONS_DIR]:
                directory.mkdir(parents=True, exist_ok=True)

            # Validate KB is loadable
            kb = load_global_kb()
            kb_stats = self.checker.get_kb_stats()

            # Validate log paths are writable
            POLICY_LOG.parent.mkdir(parents=True, exist_ok=True)

            log_policy_hit(
                "VALIDATE_SUCCESS",
                f"failure-prevention-validated | kb_patterns={kb_stats['total_patterns']}"
            )
            return True

        except Exception as e:
            log_policy_hit("VALIDATE_ERROR", str(e))
            return False

    def report(self) -> Dict:
        """
        Generate a comprehensive failure prevention compliance report.

        Analyzes all logs, extracts patterns, and compiles statistics
        from all subsystems into a unified report.

        Returns:
            Report dictionary with status, totals, patterns, learning stats
        """
        try:
            failures = self.detector.analyze_failure_log()
            prevented = self.detector.analyze_policy_log()

            report_data = self.detector.generate_detection_report(failures, prevented)
            save_detection_output(report_data)

            kb_stats = self.checker.get_kb_stats()
            learning_stats = self.solution_learner.get_learning_stats()
            patterns = self.extractor.extract_patterns()

            return {
                "status": "success",
                "policy": "common-failures-prevention",
                "generated": datetime.now().isoformat(),
                "summary": report_data['summary'],
                "kb_stats": kb_stats,
                "learning_stats": learning_stats,
                "extracted_patterns": len(patterns),
                "top_patterns": [
                    {
                        "pattern_id": p['pattern_id'],
                        "frequency": p['frequency'],
                        "confidence": p['confidence']
                    }
                    for p in patterns[:5]
                ]
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def run_detect_mode(self, output_json: bool = False) -> int:
        """
        Run detection mode: analyze logs and print report.

        Args:
            output_json: If True, output raw JSON instead of formatted report

        Returns:
            Exit code (0 = success)
        """
        print("[SEARCH] Analyzing failure logs...")
        failures = self.detector.analyze_failure_log()
        prevented = self.detector.analyze_policy_log()

        if not failures and not prevented:
            print("[CHECK] No failures detected in last 30 days")
            return 0

        report_data = self.detector.generate_detection_report(failures, prevented)
        save_detection_output(report_data)

        if output_json:
            print(json.dumps(report_data, indent=2))
            return 0

        print("\n" + "=" * 70)
        print("[CHART] FAILURE DETECTION REPORT")
        print("=" * 70)
        print(f"\nPeriod: Last {ANALYSIS_DAYS} days")
        print(f"Generated: {report_data['generated']}")

        summary = report_data['summary']
        print(f"\nSummary:")
        print(f"   Total failures:      {summary['total_failures']}")
        print(f"   Unique patterns:     {summary['unique_patterns']}")
        print(f"   Prevented failures:  {summary['prevented_failures']}")

        if report_data.get('failures_by_signature'):
            print(f"\n[ALERT] Failures by Pattern:")
            sorted_sigs = sorted(
                report_data['failures_by_signature'].items(),
                key=lambda x: x[1]['count'],
                reverse=True
            )
            for sig, data in sorted_sigs:
                print(f"\n   {sig} ({data['severity']})")
                print(f"      Count:    {data['count']}")
                print(f"      Category: {data['category']}")
                print(f"      Last seen: {data['last_seen']}")
                if data.get('examples'):
                    print(f"      Example: {data['examples'][0]['context'][:100]}...")

        if report_data.get('prevention_log'):
            print(f"\n[CHECK] Recent Preventions ({len(report_data['prevention_log'])}):")
            for prev in report_data['prevention_log'][-5:]:
                print(f"   [{prev['timestamp']}] {prev['context'][:80]}...")

        print("\n" + "=" * 70)
        print(f"[FLOPPY] Full report saved to: {DETECTION_OUTPUT}")
        print("=" * 70)

        log_policy_hit(
            "analysis-complete",
            f"{summary['total_failures']} failures, {summary['unique_patterns']} patterns"
        )
        return 0

    def run_learn_mode(self, project_name: Optional[str], promote: bool = False) -> int:
        """
        Run learning mode: update project KB from detection results.

        Args:
            project_name: Project to learn for (defaults to current directory)
            promote: If True, promote confirmed patterns to global KB

        Returns:
            Exit code (0 = success, 1 = failure)
        """
        project = project_name or get_current_project()

        if not project:
            print("[CROSS] Could not determine project name")
            print("   Use --project <name> to specify")
            return 1

        detection_results = load_detection_results()

        if not detection_results:
            print("[CROSS] No failure detection results found")
            print("   Run: python common-failures-prevention-policy.py --detect")
            return 1

        print(f"[BRAIN] Learning from failure patterns...")
        print(f"   Project: {project}")

        learning_result = self.learner.learn_from_detection(project, detection_results)

        if not learning_result:
            print("[CROSS] Learning failed")
            return 1

        print("=" * 70)
        print("[LIBRARY] LEARNING RESULTS")
        print("=" * 70)
        print(f"\nProject: {learning_result['project']}")
        print(f"Total patterns tracked: {learning_result['total_patterns']}")
        print(f"Patterns learned (status changed): {len(learning_result['learned_patterns'])}")

        if learning_result['learned_patterns']:
            print(f"\nStatus Changes:")
            for pattern in learning_result['learned_patterns']:
                print(f"   {pattern['signature']}")
                print(f"      {pattern['old_status']} -> {pattern['new_status']}")
                print(f"      Count: {pattern['count']}, Confidence: {pattern['confidence']:.1%}")

        print(f"\n[FLOPPY] KB saved to: {learning_result['kb_path']}")

        if promote:
            candidates = self.learner.find_global_candidates(project)
            if candidates:
                print("\n" + "=" * 70)
                print("[GLOBE] GLOBAL PROMOTION")
                print("=" * 70)
                promoted = self.learner.promote_to_global(candidates)
                if promoted > 0:
                    print(f"\n[CHECK] {promoted} patterns promoted to global KB")
            else:
                print("\n[PAUSE] No patterns ready for global promotion yet")

        print("\n" + "=" * 70)
        print("[CHECK] LEARNING COMPLETE")
        print("=" * 70)
        return 0

    def run_analyze_mode(
        self,
        with_solutions: bool = False,
        output_file: Optional[str] = None
    ) -> int:
        """
        Run analyze mode: extract patterns from failures log.

        Args:
            with_solutions: If True, include solution suggestions in output
            output_file: Optional path to write pattern JSON output

        Returns:
            Exit code (0 = success, 1 = no patterns found)
        """
        print("Extracting failure patterns...")
        patterns = self.extractor.extract_patterns()

        if not patterns:
            print("No patterns found")
            return 1

        print(f"Found {len(patterns)} patterns")

        if with_solutions:
            for pattern in patterns:
                pattern['suggested_solutions'] = self.extractor.suggest_solutions(pattern)

        output_data = {
            'extracted_at': (
                self.extractor.failures_log.stat().st_mtime
                if self.extractor.failures_log.exists()
                else None
            ),
            'total_patterns': len(patterns),
            'patterns': patterns
        }

        if output_file:
            output_path = Path(output_file)
            output_path.write_text(json.dumps(output_data, indent=2))
            print(f"Patterns saved to: {output_file}")
        else:
            print(json.dumps(output_data, indent=2))

        return 0

    def run_kb_status_mode(self) -> int:
        """
        Run KB status mode: show knowledge base statistics.

        Returns:
            Exit code (0 = success)
        """
        print("=" * 70)
        print("FAILURE KNOWLEDGE BASE STATUS")
        print("=" * 70)

        kb_stats = self.checker.get_kb_stats()
        learning_stats = self.solution_learner.get_learning_stats()

        print(f"\nGlobal KB ({KB_FILE}):")
        print(f"   Total patterns:   {kb_stats['total_patterns']}")
        print(f"   High confidence:  {kb_stats['high_confidence']}")

        if kb_stats['by_tool']:
            print(f"\n   Patterns by tool:")
            for tool, count in kb_stats['by_tool'].items():
                print(f"      {tool}: {count}")

        print(f"\nSolution Learning Stats:")
        print(f"   Total patterns:   {learning_stats['total_patterns']}")
        print(f"   High confidence:  {learning_stats['by_confidence']['high']}")
        print(f"   Medium confidence:{learning_stats['by_confidence']['medium']}")
        print(f"   Low confidence:   {learning_stats['by_confidence']['low']}")

        if learning_stats['recently_learned']:
            print(f"\n   Recently learned:")
            for item in learning_stats['recently_learned'][:5]:
                print(
                    f"      {item['pattern_id']} (conf={item['confidence']:.2f}) "
                    f"@ {item['learned_at'][:19]}"
                )

        print("\n" + "=" * 70)
        return 0

    def run_check_mode(self, tool: str, params_json: str) -> int:
        """
        Run pre-execution check mode for a specific tool call.

        Args:
            tool: Tool name to check (Bash, Edit, Read, Grep)
            params_json: JSON string of tool parameters

        Returns:
            Exit code (0 = pass, 1 = issues found)
        """
        try:
            params = json.loads(params_json)
        except Exception:
            print(f"ERROR: Invalid JSON params: {params_json}", file=sys.stderr)
            return 1

        self.checker.reload_kb()
        result = self.checker.check_tool_call(tool, params)
        print(json.dumps(result, indent=2))

        return 1 if result.get('issues') else 0


# ===========================================================================
# SECTION 10: CLI INTERFACE
# Full CLI with all modes from all 9 source scripts
# ===========================================================================

def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the complete argument parser for all CLI modes.

    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        description=(
            "Common Failures Prevention Policy v3.0 - "
            "Enterprise failure prevention and learning system"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  --enforce           Run full policy enforcement (default)
  --validate          Check system compliance and readiness
  --report            Generate failure statistics report
  --detect            Analyze logs for failure patterns
  --check             Pre-execution check for tool call
  --learn             Learn from detection results
  --analyze           Extract and analyze failure patterns
  --kb-status         Show knowledge base status

Examples:
  python common-failures-prevention-policy.py --enforce
  python common-failures-prevention-policy.py --validate
  python common-failures-prevention-policy.py --report
  python common-failures-prevention-policy.py --detect --json
  python common-failures-prevention-policy.py --check --tool Bash --params '{"command":"del file.txt"}'
  python common-failures-prevention-policy.py --learn --project my-project --promote
  python common-failures-prevention-policy.py --analyze --with-solutions --output patterns.json
  python common-failures-prevention-policy.py --kb-status
        """
    )

    # Policy interface modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--enforce',
        action='store_true',
        help='Run full policy enforcement (default if no mode specified)'
    )
    mode_group.add_argument(
        '--validate',
        action='store_true',
        help='Validate policy compliance and system readiness'
    )
    mode_group.add_argument(
        '--report',
        action='store_true',
        help='Generate comprehensive failure statistics report'
    )
    mode_group.add_argument(
        '--detect',
        action='store_true',
        help='Analyze logs for failure patterns (from failure-detector.py)'
    )
    mode_group.add_argument(
        '--check',
        action='store_true',
        help='Pre-execution check for tool call (from pre-execution-checker.py)'
    )
    mode_group.add_argument(
        '--learn',
        action='store_true',
        help='Learn from detection results (from failure-learner.py)'
    )
    mode_group.add_argument(
        '--analyze',
        action='store_true',
        help='Extract and analyze failure patterns (from failure-pattern-extractor.py)'
    )
    mode_group.add_argument(
        '--kb-status',
        action='store_true',
        dest='kb_status',
        help='Show knowledge base status'
    )
    mode_group.add_argument(
        '--check-all',
        action='store_true',
        dest='check_all',
        help='Load KB and run all checks (compatibility mode for 3-level-flow)'
    )

    # Detection options
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON'
    )
    parser.add_argument(
        '--analyze-logs',
        action='store_true',
        dest='analyze_logs',
        help='Alias for --detect (backward compatibility)'
    )

    # Pre-execution check options
    parser.add_argument(
        '--tool',
        type=str,
        help='Tool name for --check mode (Bash, Edit, Read, Grep)'
    )
    parser.add_argument(
        '--params',
        type=str,
        help='Tool parameters as JSON string for --check mode'
    )

    # Learning options
    parser.add_argument(
        '--project',
        type=str,
        default=None,
        help='Project name for --learn mode (default: current directory)'
    )
    parser.add_argument(
        '--promote',
        action='store_true',
        help='Promote confirmed patterns to global KB (use with --learn)'
    )

    # Pattern extraction options
    parser.add_argument(
        '--with-solutions',
        action='store_true',
        dest='with_solutions',
        help='Include solution suggestions (use with --analyze)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output file path for pattern data (use with --analyze)'
    )

    # v2 detection options
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show failure statistics'
    )
    parser.add_argument(
        '--update-kb',
        action='store_true',
        dest='update_kb',
        help='Update knowledge base from detected patterns'
    )
    parser.add_argument(
        '--test-detection',
        action='store_true',
        dest='test_detection',
        help='Test failure detection with sample messages'
    )

    # Unicode checker options
    parser.add_argument(
        '--unicode-check',
        type=str,
        dest='unicode_check',
        metavar='FILE',
        help='Check a Python file for Unicode issues'
    )
    parser.add_argument(
        '--unicode-fix',
        type=str,
        dest='unicode_fix',
        metavar='FILE',
        help='Fix Unicode issues in a Python file'
    )
    parser.add_argument(
        '--scan-dir',
        type=str,
        dest='scan_dir',
        metavar='DIR',
        help='Scan directory for Python files with Unicode issues'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        dest='no_backup',
        help='Skip backup when fixing Unicode (use with --unicode-fix)'
    )

    return parser


def run_test_detection(policy: CommonFailuresPreventionPolicy) -> int:
    """
    Run built-in detection tests with sample failure messages.

    Args:
        policy: Policy instance to use for testing

    Returns:
        Exit code (0 = all tests passed)
    """
    print("Testing failure detection...")

    test_messages = [
        "bash: del: command not found",
        "String to replace not found: old_text",
        "File content (100000 tokens) exceeds maximum",
        "ModuleNotFoundError: No module named pandas",
        "fatal: not a git repository",
        "ERROR: Connection timeout",
        "UnicodeEncodeError: 'charmap' codec can't encode character",
        "PermissionError: [Errno 13] Permission denied",
        "SyntaxError: invalid syntax",
    ]

    all_passed = True
    for msg in test_messages:
        result = policy.detector.detect_failure_in_message(msg)
        sig = policy.detector.detect_failure_signature(msg)
        if result or sig:
            failure_type = result['failure_type'] if result else sig['signature']
            print(f"[OK] Detected: {failure_type}")
        else:
            print(f"[MISS] Not detected: {msg}")
            all_passed = False

    if all_passed:
        print("\n[OK] All tests passed!")
    else:
        print("\n[WARN] Some messages were not detected")

    return 0 if all_passed else 1


def main() -> int:
    """
    Main entry point for the Common Failures Prevention Policy CLI.

    Parses arguments, initializes the policy, and dispatches to the
    appropriate mode handler.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    parser = build_argument_parser()

    # If no arguments provided, run default enforcement silently
    if len(sys.argv) == 1:
        policy = CommonFailuresPreventionPolicy()
        result = policy.enforce()
        return 0 if result.get("status") == "success" else 1

    args = parser.parse_args()
    policy = CommonFailuresPreventionPolicy()

    # ---------------------------------------------------------------------------
    # POLICY INTERFACE MODES
    # ---------------------------------------------------------------------------

    if args.enforce:
        result = policy.enforce()
        return 0 if result.get("status") == "success" else 1

    if args.validate:
        is_valid = policy.validate()
        if is_valid:
            print("[OK] Failure prevention system validated successfully")
        else:
            print("[ERROR] Validation failed - check logs for details")
        return 0 if is_valid else 1

    if args.report:
        result = policy.report()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("=" * 70)
            print("FAILURE PREVENTION COMPLIANCE REPORT")
            print("=" * 70)
            print(f"\nGenerated: {result.get('generated', 'N/A')}")
            print(f"Status:    {result.get('status', 'unknown')}")

            summary = result.get('summary', {})
            print(f"\nFailure Summary:")
            print(f"   Total failures:     {summary.get('total_failures', 0)}")
            print(f"   Unique patterns:    {summary.get('unique_patterns', 0)}")
            print(f"   Prevented:          {summary.get('prevented_failures', 0)}")

            kb_stats = result.get('kb_stats', {})
            print(f"\nKnowledge Base:")
            print(f"   Total patterns:     {kb_stats.get('total_patterns', 0)}")
            print(f"   High confidence:    {kb_stats.get('high_confidence', 0)}")

            print(f"\nExtracted Patterns: {result.get('extracted_patterns', 0)}")

            top = result.get('top_patterns', [])
            if top:
                print(f"\nTop Patterns:")
                for p in top:
                    print(f"   {p['pattern_id']}: {p['frequency']}x (conf={p['confidence']:.2f})")

            print("\n" + "=" * 70)

        return 0 if result.get("status") == "success" else 1

    # ---------------------------------------------------------------------------
    # DETECTION MODES
    # ---------------------------------------------------------------------------

    if args.detect or args.analyze_logs:
        return policy.run_detect_mode(output_json=args.json)

    if args.stats:
        failures = policy.detector.analyze_all_logs_v2()
        stats = policy.detector.get_statistics(failures)
        print(json.dumps(stats, indent=2))
        return 0

    if args.update_kb:
        print("Analyzing log files...")
        failures = policy.detector.analyze_all_logs_v2()
        print(f"Found {len(failures)} failure events")

        if failures:
            grouped = policy.detector.group_failures_v2(failures)
            print(f"Found {len(grouped)} unique failure patterns")
            patterns = policy.detector.extract_pattern_data_v2(grouped)
            print("Updating knowledge base...")
            kb = policy.detector.update_kb_from_patterns(patterns)
            total = sum(len(v) for v in kb.values())
            print(f"Knowledge base updated: {total} total patterns")
            print(f"Saved to: {KB_FILE}")
        else:
            print("No failures detected in logs")
        return 0

    # ---------------------------------------------------------------------------
    # PRE-EXECUTION CHECK MODE
    # ---------------------------------------------------------------------------

    if args.check:
        if not args.tool or not args.params:
            print("ERROR: --check requires --tool and --params", file=sys.stderr)
            return 1
        return policy.run_check_mode(args.tool, args.params)

    if args.check_all:
        policy.checker.reload_kb()
        stats = policy.checker.get_kb_stats()
        print(f"Failure KB loaded: {stats.get('total_patterns', 0)} patterns")
        return 0

    # ---------------------------------------------------------------------------
    # LEARNING MODE
    # ---------------------------------------------------------------------------

    if args.learn:
        return policy.run_learn_mode(args.project, promote=args.promote)

    # ---------------------------------------------------------------------------
    # PATTERN ANALYSIS MODE
    # ---------------------------------------------------------------------------

    if args.analyze:
        return policy.run_analyze_mode(
            with_solutions=args.with_solutions,
            output_file=args.output
        )

    # ---------------------------------------------------------------------------
    # KB STATUS MODE
    # ---------------------------------------------------------------------------

    if args.kb_status:
        return policy.run_kb_status_mode()

    # ---------------------------------------------------------------------------
    # TEST MODE
    # ---------------------------------------------------------------------------

    if args.test_detection:
        return run_test_detection(policy)

    # ---------------------------------------------------------------------------
    # UNICODE CHECKER MODES
    # ---------------------------------------------------------------------------

    if args.unicode_fix:
        print(f"[FIXING] {args.unicode_fix}")
        success = policy.unicode_checker.auto_fix_unicode(
            args.unicode_fix, backup=not args.no_backup
        )
        return 0 if success else 1

    if args.unicode_check:
        print(f"[CHECKING] {args.unicode_check}")
        result = policy.unicode_checker.check_file_for_unicode(args.unicode_check)
        print(f"\n[STATUS] {result['status']}")
        print(f"[REASON] {result['reason']}")

        if result['status'] == 'FAIL':
            print(f"\n[UNICODE CHARACTERS FOUND]")
            for char_info in result.get('characters', []):
                print(
                    f"  - ({char_info['unicode']}): {char_info['count']}x "
                    f"-> Suggested: '{char_info['replacement']}'"
                )
            print(f"\n[ACTION] Run with --unicode-fix to automatically replace")
            return 1
        return 0

    if args.scan_dir:
        print(f"[SCANNING] {args.scan_dir}")
        found_issues = policy.unicode_checker.scan_directory(args.scan_dir)

        if found_issues:
            print(f"\n[ISSUES] Found {len(found_issues)} files with Unicode characters:")
            for file_path, result in found_issues:
                print(f"\n  File: {file_path}")
                print(f"  Characters: {result.get('total_occurrences', 0)} total")
            print(f"\n[ACTION] Run --unicode-fix on each file to fix")
            return 1
        else:
            print("[OK] No Unicode issues found")
            return 0

    # Default: show help if nothing matched
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
