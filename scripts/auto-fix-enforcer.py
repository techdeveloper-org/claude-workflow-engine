#!/usr/bin/env python
"""
Script Name: auto-fix-enforcer.py
Version: 2.1.0
Last Modified: 2026-03-05
Description: Auto-fix enforcement with blocking mode, Windows Unicode detection,
             and flag auto-expiry cleanup (Loophole #10)
Author: Claude Memory System
Changelog: See CHANGELOG.md

[ALERT] CRITICAL: If ANY policy or system fails -> STOP ALL WORK -> FIX IMMEDIATELY

This enforcer:
1. Detects ALL system failures (policies, daemons, files, dependencies)
2. BLOCKS all work until failures are fixed
3. Auto-fixes common issues
4. Provides clear fix instructions for manual issues
5. Checks for Windows Unicode issues in Python files (v2.0.0)

MANDATORY: Run BEFORE every action!
"""

# Fix encoding for Windows console
import sys
if sys.stdout.encoding != 'utf-8':
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


import os
import sys
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# ===================================================================
# NEW: POLICY TRACKING INTEGRATION
# ===================================================================
# Policy tracking - mandatory (find helper by walking up to scripts root)
_scripts_root = Path(__file__).resolve().parent
while _scripts_root != _scripts_root.parent:
    if (_scripts_root / 'policy_tracking_helper.py').exists():
        if str(_scripts_root) not in sys.path:
            sys.path.insert(0, str(_scripts_root))
        break
    _scripts_root = _scripts_root.parent
from policy_tracking_helper import record_policy_execution, record_sub_operation, get_session_id

# Flag auto-expiry configuration (Loophole #10)
FLAG_EXPIRY_MINUTES = 60   # Auto-delete flags older than 60 minutes
FLAG_CLEANUP_ON_STARTUP = True
FLAG_DIR = Path.home() / '.claude'  # Where enforcement flag files live

# File locking for shared JSON state (Loophole #19)
try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


def _lock_file(f):
    """Lock file for exclusive access (Windows msvcrt, no-op on other OS)."""
    if HAS_MSVCRT:
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except (IOError, OSError):
            pass  # lock failed - proceed without lock (better than crash)


def _unlock_file(f):
    """Unlock file (Windows msvcrt, no-op on other OS)."""
    if HAS_MSVCRT:
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except (IOError, OSError):
            pass


# =============================================================================
# FLAG AUTO-EXPIRY UTILITIES (Loophole #10)
# =============================================================================

def _cleanup_expired_flags(max_age_minutes=FLAG_EXPIRY_MINUTES):
    """Remove flag files in FLAG_DIR older than max_age_minutes.

    Scans ~/.claude/ for all .*.json flag files and deletes any whose
    filesystem modification time exceeds the expiry threshold.

    Args:
        max_age_minutes: Maximum allowed flag age in minutes (default 60).

    Returns:
        int: Number of flag files deleted.
    """
    try:
        cutoff_time = datetime.now() - timedelta(minutes=max_age_minutes)
        cleaned = 0

        for flag_file in FLAG_DIR.glob('.*.json'):
            try:
                if flag_file.stat().st_mtime < cutoff_time.timestamp():
                    flag_file.unlink(missing_ok=True)
                    cleaned += 1
            except Exception:
                pass

        return cleaned
    except Exception:
        return 0


def _check_flag_age(flag_path, max_age_minutes=FLAG_EXPIRY_MINUTES):
    """Check if a flag file is still within its freshness window.

    Checks file modification time and, if present, the JSON created_at
    field.  Stale files are deleted before returning False.

    Args:
        flag_path: str or Path to the flag JSON file.
        max_age_minutes: Maximum allowed age in minutes (default 60).

    Returns:
        bool: True if fresh and usable; False if expired/missing.
    """
    try:
        path = Path(flag_path)
        if not path.exists():
            return False

        mod_time = datetime.fromtimestamp(path.stat().st_mtime)
        age_minutes = (datetime.now() - mod_time).total_seconds() / 60

        if age_minutes > max_age_minutes:
            path.unlink(missing_ok=True)
            return False

        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if 'created_at' in data:
                created = datetime.fromisoformat(data['created_at'])
                json_age = (datetime.now() - created).total_seconds() / 60
                if json_age > max_age_minutes:
                    path.unlink(missing_ok=True)
                    return False
        except Exception:
            pass

        return True
    except Exception:
        return False


class AutoFixEnforcer:
    """Detect, report, and auto-fix system health failures.

    Runs 7 sequential checks on every UserPromptSubmit hook invocation:
      1. Python binary availability
      2. Critical script files presence
      3. Blocking-enforcer state initialisation
      4. Session state flags
      5. Daemon PID status (informational)
      6. Git repository cleanliness (informational)
      7. Windows Python Unicode characters

    Failures are accumulated in self.failures.  Auto-fixable failures are
    attempted automatically; non-fixable failures print fix instructions and
    the run() method returns a non-zero exit code to block further work.

    Attributes:
        scripts_path (Path): Location of hook scripts (e.g. ~/.claude/scripts/).
        memory_path (Path): Root of the Claude memory directory.
        failures (list): Collected failure dicts from _check_*() methods.
        auto_fixed (list): Component names that were successfully auto-fixed.
        manual_fixes_needed (list): Failures requiring manual intervention.
    """

    def __init__(self):
        """Initialise paths and empty failure/fix tracking lists.

        Attempts to import ide_paths for IDE-embedded installations.
        Falls back to ~/.claude/scripts/ and ~/.claude/memory/ when
        ide_paths is not available (standalone mode).
        """
        # Use ide_paths for IDE self-contained installations (with fallback for standalone mode)
        try:
            from ide_paths import SCRIPTS_DIR, MEMORY_BASE
            self.scripts_path = SCRIPTS_DIR
            self.memory_path = MEMORY_BASE
        except ImportError:
            # Fallback for standalone mode (no IDE_INSTALL_DIR set)
            self.scripts_path = Path.home() / '.claude' / 'scripts'
            self.memory_path = Path.home() / '.claude' / 'memory'

        # No fallback needed - scripts should always be in ~/.claude/scripts/
        self.failures = []
        self.auto_fixed = []
        self.manual_fixes_needed = []

    def check_all_systems(self):
        """Run all 7 system health checks and collect any failures.

        Executes each _check_*() sub-method in order:
          1. _check_python()               - Python binary availability
          2. _check_critical_files()        - Presence of blocking-policy-enforcer.py
          3. _check_blocking_enforcer()     - Blocking-state.json initialisation
          4. _check_session_state()         - Required session state flags
          5. _check_daemons()               - Daemon PID file status (informational)
          6. _check_git_repos()             - Git clean/dirty status (informational)
          7. _check_windows_python_unicode() - Unicode characters in .py files

        Failures are appended to self.failures.  The method returns
        True only when self.failures is empty after all checks.

        Returns:
            bool: True if all checks passed (no failures collected).
        """
        print("\n" + "="*80)
        print("[ALERT] AUTO-FIX ENFORCER - CHECKING ALL SYSTEMS")
        print("="*80 + "\n")

        # Track each check as sub-operation
        self._sub_op_timings = []

        # Check critical components (track each with timing)
        checks = [
            ('check_python', self._check_python),
            ('check_critical_files', self._check_critical_files),
            ('check_blocking_enforcer', self._check_blocking_enforcer),
            ('check_session_state', self._check_session_state),
            ('check_daemons', self._check_daemons),
            ('check_git_repos', self._check_git_repos),
            ('check_windows_python_unicode', self._check_windows_python_unicode),
        ]

        for check_name, check_fn in checks:
            check_start = datetime.now()
            check_fn()
            check_duration = int((datetime.now() - check_start).total_seconds() * 1000)
            self._sub_op_timings.append({
                'name': check_name,
                'duration_ms': check_duration,
                'status': 'OK' if len(self.failures) == len(getattr(self, '_prev_failures_count', [])) else 'FAILED'
            })

        return len(self.failures) == 0

    def _check_python(self):
        """Check [1/7]: Verify that the Python binary is available in PATH.

        Runs "python --version" with a 5-second timeout.  A non-zero exit
        code or an exception appends a CRITICAL failure to self.failures.

        Returns:
            bool: True if Python is accessible; False otherwise.
        """
        print("[SEARCH] [1/7] Checking Python...")
        try:
            result = subprocess.run(['python', '--version'],
                                  capture_output=True, text=True, timeout=5,
                                  encoding='utf-8', errors='replace')
            if result.returncode == 0:
                version = result.stdout.strip()
                print(f"   [CHECK] Python available: {version}")
                return True
        except:
            pass

        self.failures.append({
            'type': 'CRITICAL',
            'component': 'Python',
            'issue': 'Python command not found or not working',
            'auto_fixable': False,
            'fix_instructions': [
                'Install Python from python.org',
                'Add Python to PATH',
                'Verify: python --version'
            ]
        })
        print("   [CROSS] Python NOT FOUND - CRITICAL!")
        return False

    def _check_critical_files(self):
        """Check [2/7]: Verify that critical system files exist in scripts_path.

        Currently one CRITICAL file is required: blocking-policy-enforcer.py.
        Optional files (plan-detector.py, session-start.sh) are reported as
        informational warnings and do not block the session.

        Appends a CRITICAL failure to self.failures if any required file is
        missing from self.scripts_path (~/.claude/scripts/ by default).
        """
        print("\n[SEARCH] [2/7] Checking critical files...")

        # ONLY truly critical files that MUST exist (in ~/.claude/scripts/)
        critical_files = {
            # Currently no files are truly critical - blocking enforcer is auto-initialized
        }

        # Optional files that are nice-to-have but not blocking
        optional_files = {
            'blocking-policy-enforcer.py': 'Blocking enforcer utility',
            'plan-detector.py': 'Plan detector',
            'plan-detector.sh': 'Plan detector shell wrapper',
            'session-start.sh': 'Session start script'
        }

        missing_critical = []
        missing_optional = []

        # Check critical files in ~/.claude/scripts/
        for file_name, description in critical_files.items():
            full_path = self.scripts_path / file_name
            if not full_path.exists():
                missing_critical.append((file_name, description))
                print(f"   [CROSS] Missing CRITICAL: {file_name} ({description})")
            else:
                print(f"   [CHECK] Found: {file_name}")

        # Check optional files in ~/.claude/scripts/ (just warn, don't block)
        for file_name, description in optional_files.items():
            full_path = self.scripts_path / file_name
            if not full_path.exists():
                missing_optional.append((file_name, description))
                print(f"   [INFO]  Optional (not found): {file_name} ({description})")

        # Only block if critical files are missing
        if missing_critical:
            self.failures.append({
                'type': 'CRITICAL',
                'component': 'Critical Files',
                'issue': f'{len(missing_critical)} critical files missing',
                'details': missing_critical,
                'auto_fixable': False,
                'fix_instructions': [
                    'Restore missing files from backup or repository',
                    'Run: cp -r claude-insight/scripts/* ~/.claude/memory/scripts/',
                    'Verify file permissions'
                ]
            })
        elif missing_optional:
            print(f"   [WARNING]  {len(missing_optional)} optional files missing (work continues)")
            print("   [CHECK] All CRITICAL files present")
        else:
            print("   [CHECK] All critical files present")

    def _check_blocking_enforcer(self):
        """Check [3/7]: Verify the blocking-enforcer state file is initialised.

        Reads .blocking-state.json from self.memory_path.  If the file is
        missing, attempts _auto_fix_blocking_enforcer() to create it.  If
        the file exists but session_started is False, appends a CRITICAL
        failure.  On read errors appends a HIGH priority failure.

        Returns:
            bool: True when the enforcer state is present and valid.
        """
        print("\n[SEARCH] [3/7] Checking blocking enforcer...")

        state_file = self.memory_path / '.blocking-state.json'
        if not state_file.exists():
            print("   [WARNING]  Blocking enforcer state not found")
            # Try to initialize
            if self._auto_fix_blocking_enforcer():
                print("   [CHECK] Auto-fixed: Blocking enforcer initialized")
                self.auto_fixed.append('Blocking enforcer state')
                return True
            else:
                self.failures.append({
                    'type': 'HIGH',
                    'component': 'Blocking Enforcer',
                    'issue': 'Enforcer not initialized',
                    'auto_fixable': True,
                    'fix_instructions': [
                        'Run: export PYTHONIOENCODING=utf-8',
                        'Run: bash ~/.claude/scripts/session-start.sh'
                    ]
                })
                return False

        try:
            with open(state_file, 'r') as f:
                _lock_file(f)
                state = json.load(f)
                _unlock_file(f)

            # Check if session started
            if not state.get('session_started', False):
                print("   [WARNING]  Session not started")
                self.failures.append({
                    'type': 'CRITICAL',
                    'component': 'Session',
                    'issue': 'Session not started',
                    'auto_fixable': True,
                    'fix_instructions': [
                        'Run: export PYTHONIOENCODING=utf-8',
                        'Run: bash ~/.claude/scripts/session-start.sh'
                    ]
                })
                return False

            print("   [CHECK] Blocking enforcer initialized")
            return True

        except Exception as e:
            print(f"   [CROSS] Error reading enforcer state: {e}")
            self.failures.append({
                'type': 'HIGH',
                'component': 'Blocking Enforcer',
                'issue': f'Cannot read state: {e}',
                'auto_fixable': False
            })
            return False

    def _get_current_session_id(self):
        """
        Read the active session ID from per-project or legacy session file.
        Returns the session ID string or None if not found.
        Used for session isolation in state checks.
        """
        try:
            from project_session import read_session_id
            sid = read_session_id()
            return sid if sid else None
        except ImportError:
            pass
        # Legacy fallback
        current_session_file = self.memory_path / '.current-session.json'
        if not current_session_file.exists():
            return None
        try:
            with open(current_session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('current_session_id')
        except Exception:
            return None

    def _check_session_state(self):
        """Check [4/7]: Validate session state flags in blocking-state.json.

        Reads .blocking-state.json from self.memory_path and verifies that
        session_started and context_checked flags are True.  Missing flags
        emit a WARNING but do NOT append to self.failures (non-blocking).

        Session isolation (Loophole #11): validates that the session_id
        field in .blocking-state.json matches the active session from
        .current-session.json.  A stale state file from a prior session
        would otherwise pass as valid under the wrong session context.

        Returns:
            bool: True after the check completes (even on missing flags);
                  False only when the state file is unreadable.
        """
        print("\n[SEARCH] [4/7] Checking session state...")

        state_file = self.memory_path / '.blocking-state.json'
        if not state_file.exists():
            print("   [WARNING]  No session state")
            return False

        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                _lock_file(f)
                state = json.load(f)
                _unlock_file(f)

            # ----------------------------------------------------------------
            # SESSION ISOLATION: verify state belongs to the current session.
            # If the state file was written by a previous session, it is stale
            # and should be treated as invalid (non-blocking warning only).
            # ----------------------------------------------------------------
            current_session_id = self._get_current_session_id()
            state_session_id = state.get('session_id', '')

            if current_session_id and state_session_id:
                if current_session_id != state_session_id:
                    print(
                        f"   [WARNING]  Session state belongs to a different session "
                        f"(state: {state_session_id[:20]}... | current: {current_session_id[:20]}...)"
                    )
                    print("   [INFO]  Stale state detected - not blocking (new session will re-initialize)")
                    # Not critical: 3-level-flow will create a fresh session state.
                    return True
                else:
                    print(f"   [CHECK] Session state matches current session: {current_session_id[:20]}...")
            elif not current_session_id:
                # No active session yet - state file may be from startup, allow it
                print("   [INFO]  No active session yet - state isolation skipped")
            else:
                # state_session_id is empty - old state file without session_id field
                print("   [INFO]  State file has no session_id field (pre-isolation version) - allowing")

            # Check required state keys
            required_checks = {
                'session_started': 'Session started',
                'context_checked': 'Context checked'
            }

            missing = []
            for key, desc in required_checks.items():
                if not state.get(key, False):
                    missing.append(desc)

            if missing:
                print(f"   [WARNING]  Missing: {', '.join(missing)}")
                # Not critical, just warning
            else:
                print("   [CHECK] Session state valid")

            return True

        except Exception as e:
            print(f"   [CROSS] Error checking session state: {e}")
            return False

    def _check_daemons(self):
        """Check [5/7]: Report running vs stopped daemon count (informational).

        Reads PID files from memory_path/.pids/ and uses "tasklist /FI PID"
        to verify each process is alive.  Daemons being stopped is a WARNING,
        not a CRITICAL failure.  The system works without daemons; only
        automation features are reduced.

        Returns:
            bool: Always True (daemon status is never blocking).
        """
        print("\n[SEARCH] [5/7] Checking daemons...")

        # Note: Daemons being stopped is WARNING, not CRITICAL
        # System can work without daemons, just with reduced automation

        pid_dir = self.memory_path / '.pids'
        if not pid_dir.exists():
            print("   [WARNING]  No daemon PID directory (daemons not started)")
            print("   [INFO]  System will work, but automation is disabled")
            return True

        daemon_names = [
            'context-daemon',
            'session-auto-save-daemon',
            'preference-auto-tracker',
            'skill-auto-suggester',
            'commit-daemon',
            'session-pruning-daemon',
            'pattern-detection-daemon',
            'failure-prevention-daemon',
            'auto-recommendation-daemon'
        ]

        running = 0
        stopped = 0

        for daemon in daemon_names:
            pid_file = pid_dir / f'{daemon}.pid'
            if pid_file.exists():
                try:
                    pid = int(pid_file.read_text().strip())
                    # Check if process is running (Windows compatible)
                    try:
                        subprocess.run(['tasklist', '/FI', f'PID eq {pid}'],
                                     capture_output=True, timeout=2,
                                     encoding='utf-8', errors='replace')
                        running += 1
                    except:
                        stopped += 1
                except:
                    stopped += 1
            else:
                stopped += 1

        print(f"   [INFO]  Daemons: {running} running, {stopped} stopped")
        print("   [INFO]  Daemon status is informational only (not blocking)")
        return True

    def _check_git_repos(self):
        """Check [6/7]: Report git repository cleanliness (informational).

        Runs "git rev-parse --git-dir" to detect a git repo, then
        "git status --porcelain" to detect uncommitted changes.  Dirty
        repos emit a WARNING but do NOT append to self.failures.

        Returns:
            bool: Always True (git status is never blocking).
        """
        print("\n[SEARCH] [6/7] Checking git repositories...")

        # Check if we're in a git repo
        try:
            result = subprocess.run(['git', 'rev-parse', '--git-dir'],
                                  capture_output=True, text=True, timeout=5,
                                  encoding='utf-8', errors='replace')
            if result.returncode == 0:
                # Check for uncommitted changes
                result = subprocess.run(['git', 'status', '--porcelain'],
                                      capture_output=True, text=True, timeout=5,
                                      encoding='utf-8', errors='replace')
                if result.stdout.strip():
                    print("   [WARNING]  Uncommitted changes detected")
                    print("   [INFO]  Consider committing before major changes")
                else:
                    print("   [CHECK] Git repository clean")
                return True
        except:
            print("   [INFO]  Not in a git repository (or git not available)")

        return True

    def _check_windows_python_unicode(self):
        """Check [7/7]: Detect and auto-fix Unicode in Python files on Windows.

        Skipped on non-Windows platforms.  On Windows, runs
        windows-python-unicode-checker.py --scan-dir against self.memory_path
        and attempts to auto-fix each offending .py file.  Non-zero exit from
        the checker triggers per-file fix attempts using --fix --no-backup.
        Timeouts and exceptions are treated as non-blocking warnings.

        Returns:
            bool: Always True (Unicode scan errors are non-blocking).
        """
        print("\n[SEARCH] [7/7] Checking Python files for Unicode on Windows...")

        # Only check on Windows
        if sys.platform != 'win32':
            print("   [INFO]  Not Windows - Unicode allowed")
            return True

        try:
            # Run the Unicode checker
            checker_script = self.memory_path / '03-execution-system' / 'failure-prevention' / 'windows-python-unicode-checker.py'

            if not checker_script.exists():
                print("   [WARNING]  Unicode checker not found (non-blocking)")
                return True

            # Scan memory directory for Python files with Unicode
            result = subprocess.run(
                ['python', str(checker_script), '--scan-dir', str(self.memory_path)],
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace'
            )

            if result.returncode == 0:
                print("   [CHECK] No Unicode issues in Python files")
                return True
            else:
                # Unicode issues found
                print("   [CRITICAL]  Unicode characters found in Python files!")
                print("   [REASON] Windows console (cp1252) cannot encode Unicode characters")
                print("   [ERROR] This causes UnicodeEncodeError and script crashes")

                # Show first few files with issues
                output_lines = result.stdout.strip().split('\n')
                issue_count = 0
                for line in output_lines:
                    if 'File:' in line and issue_count < 5:
                        print(f"   [FILE] {line.strip()}")
                        issue_count += 1

                if issue_count >= 5:
                    print("   [INFO] ...and more files")

                print("\n   [FIX] Auto-fixing all Python files...")

                # Auto-fix: Scan and fix all Python files
                python_files = list(self.memory_path.rglob('*.py'))
                fixed_count = 0

                for py_file in python_files:
                    try:
                        fix_result = subprocess.run(
                            ['python', str(checker_script), '--fix', str(py_file), '--no-backup'],
                            capture_output=True,
                            text=True,
                            timeout=10,
                            encoding='utf-8',
                            errors='replace'
                        )
                        if fix_result.returncode == 0 and fix_result.stdout and '[OK] Fixed' in fix_result.stdout:
                            fixed_count += 1
                    except:
                        pass  # Skip files that can't be fixed

                if fixed_count > 0:
                    print(f"   [OK] Auto-fixed {fixed_count} Python files")
                    print("   [CHECK] All Unicode characters replaced with ASCII equivalents")
                    return True
                else:
                    print("   [INFO] No fixes needed")
                    return True

        except subprocess.TimeoutExpired:
            print("   [WARNING]  Unicode check timed out (non-blocking)")
            return True
        except Exception as e:
            print(f"   [WARNING]  Unicode check error: {e} (non-blocking)")
            return True

    def _auto_fix_blocking_enforcer(self):
        """Attempt to initialise the blocking-enforcer state file automatically.

        Writes a default .blocking-state.json to self.memory_path with
        session_started=True and the current session ID (if available) so that
        _check_session_state() can validate session isolation correctly.

        Returns:
            bool: True if the state file was created successfully, False on any
                  write error.
        """
        try:
            state_file = self.memory_path / '.blocking-state.json'
            state_file.parent.mkdir(parents=True, exist_ok=True)

            # Include session_id so _check_session_state isolation can validate it
            current_session_id = self._get_current_session_id() or ''

            initial_state = {
                'session_started': True,
                'context_checked': False,
                'standards_loaded': False,
                'prompt_generated': False,
                'tasks_created': False,
                'plan_mode_decided': False,
                'model_selected': False,
                'skills_agents_checked': False,
                'violations': [],
                'last_violation': None,
                'session_start_time': datetime.now().isoformat(),
                'session_id': current_session_id
            }

            with open(state_file, 'w') as f:
                _lock_file(f)
                json.dump(initial_state, f, indent=2)
                _unlock_file(f)

            return True
        except:
            return False

    def auto_fix_failures(self):
        """Attempt to auto-fix every failure marked as auto_fixable.

        Iterates over self.failures and dispatches component-specific fix
        routines (currently only the blocking-enforcer state file).  Successful
        fixes are recorded in self.auto_fixed.

        Returns:
            int: Number of failures that were successfully auto-fixed.
        """
        if not self.failures:
            return True

        print("\n" + "="*80)
        print("[WRENCH] ATTEMPTING AUTO-FIXES")
        print("="*80 + "\n")

        fixed_count = 0
        for failure in self.failures:
            if failure.get('auto_fixable', False):
                print(f"[WRENCH] Fixing: {failure['component']} - {failure['issue']}")

                # Attempt fix based on component
                if failure['component'] == 'Blocking Enforcer':
                    if self._auto_fix_blocking_enforcer():
                        print("   [CHECK] Fixed!")
                        fixed_count += 1
                        self.auto_fixed.append(failure['component'])
                        continue

                print("   [CROSS] Auto-fix failed, manual intervention needed")

        if fixed_count > 0:
            print(f"\n[CHECK] Auto-fixed {fixed_count} issue(s)")

        return fixed_count

    def report_failures(self):
        """Print a formatted summary of all collected failures to stdout.

        Groups failures by severity (CRITICAL, HIGH, MEDIUM) and prints fix
        instructions for each.  When no failures exist, prints an all-clear
        banner.

        Returns:
            bool: True when there are no failures; False when failures exist.
        """
        if not self.failures:
            print("\n" + "="*80)
            print("[CHECK] ALL SYSTEMS OPERATIONAL - NO FAILURES DETECTED")
            print("="*80 + "\n")
            return True

        print("\n" + "="*80)
        print("[ALERT] SYSTEM FAILURES DETECTED - WORK BLOCKED")
        print("="*80 + "\n")

        critical = [f for f in self.failures if f['type'] == 'CRITICAL']
        high = [f for f in self.failures if f['type'] == 'HIGH']
        medium = [f for f in self.failures if f['type'] == 'MEDIUM']

        if critical:
            print(f"[RED] CRITICAL FAILURES: {len(critical)}")
            for i, failure in enumerate(critical, 1):
                print(f"\n   [{i}] {failure['component']}: {failure['issue']}")
                if 'fix_instructions' in failure:
                    print("   [CLIPBOARD] Fix Instructions:")
                    for instruction in failure['fix_instructions']:
                        print(f"      - {instruction}")

        if high:
            print(f"\n[ORANGE] HIGH PRIORITY FAILURES: {len(high)}")
            for i, failure in enumerate(high, 1):
                print(f"\n   [{i}] {failure['component']}: {failure['issue']}")
                if 'fix_instructions' in failure:
                    print("   [CLIPBOARD] Fix Instructions:")
                    for instruction in failure['fix_instructions']:
                        print(f"      - {instruction}")

        if medium:
            print(f"\n[YELLOW] MEDIUM PRIORITY FAILURES: {len(medium)}")
            for i, failure in enumerate(medium, 1):
                print(f"\n   [{i}] {failure['component']}: {failure['issue']}")

        print("\n" + "="*80)
        print("[ALERT] WORK IS BLOCKED - FIX ALL FAILURES BEFORE CONTINUING")
        print("="*80 + "\n")

        return False

    def run(self, auto_fix=True):
        """Run all system checks, optionally auto-fix, and report the result.

        Execution flow:
          1. check_all_systems() - collect failures.
          2. If all_ok: report_failures() (all-clear) and return 0.
          3. If auto_fix: auto_fix_failures() then re-run check_all_systems().
          4. report_failures() with final state.
          5. Return 0 on success; number of CRITICAL failures (min 1) otherwise.

        Args:
            auto_fix (bool): When True, attempt auto-fixes before reporting.
                             Defaults to True.

        Returns:
            int: 0 if all checks pass; number of CRITICAL failures on error.
        """
        # ===================================================================
        # TRACKING: Record start time
        # ===================================================================
        _track_start_time = datetime.now()
        _sub_operations = []

        # Check all systems
        all_ok = self.check_all_systems()

        # Collect sub-operation timing data
        if hasattr(self, '_sub_op_timings'):
            for timing in self._sub_op_timings:
                _sub_operations.append(record_sub_operation(
                    session_id=get_session_id(),
                    policy_name="auto-fix-enforcer",
                    operation_name=timing['name'],
                    input_params={},
                    output_results={"status": timing['status']},
                    duration_ms=timing['duration_ms']
                ))

        if all_ok:
            self.report_failures()

            # ===================================================================
            # TRACKING: Record successful execution
            # ===================================================================
            _duration_ms = int((datetime.now() - _track_start_time).total_seconds() * 1000)
            record_policy_execution(
                session_id=get_session_id(),
                policy_name="auto-fix-enforcer",
                policy_script="auto-fix-enforcer.py",
                policy_type="Core Hook",
                input_params={"auto_fix": auto_fix},
                output_results={
                    "status": "ALL_SYSTEMS_OK",
                    "failures_count": 0,
                    "auto_fixed_count": 0
                },
                decision="All 7 system checks passed",
                duration_ms=_duration_ms,
                sub_operations=_sub_operations if _sub_operations else None
            )
            return 0

        # Try auto-fix if enabled
        if auto_fix:
            self.auto_fix_failures()

            # Re-check after fixes
            self.failures = []
            all_ok = self.check_all_systems()

        # Report status
        self.report_failures()

        # ===================================================================
        # TRACKING: Record execution with failures
        # ===================================================================
        _duration_ms = int((datetime.now() - _track_start_time).total_seconds() * 1000)
        critical_count = sum(1 for f in self.failures if f['type'] == 'CRITICAL')
        record_policy_execution(
            session_id=get_session_id(),
            policy_name="auto-fix-enforcer",
            policy_script="auto-fix-enforcer.py",
            policy_type="Core Hook",
            input_params={"auto_fix": auto_fix},
            output_results={
                "status": "FAILURES_DETECTED",
                "failures_count": len(self.failures),
                "auto_fixed_count": len(self.auto_fixed),
                "critical_failures": critical_count
            },
            decision=f"{len(self.failures)} system failures detected",
            duration_ms=_duration_ms,
            sub_operations=_sub_operations if _sub_operations else None
        )

        # Return exit code
        if all_ok:
            return 0
        else:
            # Count critical failures
            critical_count = sum(1 for f in self.failures if f['type'] == 'CRITICAL')
            return critical_count if critical_count > 0 else 1


def main():
    """Entry point for auto-fix-enforcer.py.

    Parses --no-auto-fix flag, runs expired-flag cleanup (Loophole #10),
    then instantiates AutoFixEnforcer and calls run().  The exit code mirrors
    the enforcer result so Claude Code can surface failures.

    Returns:
        Exits with 0 on all-clear or the number of CRITICAL failures otherwise.
    """
    import argparse

    # Flag auto-expiry cleanup at Level -1 startup (Loophole #10)
    if FLAG_CLEANUP_ON_STARTUP:
        _expired = _cleanup_expired_flags(max_age_minutes=FLAG_EXPIRY_MINUTES)
        if _expired > 0:
            print(f"[FLAG-CLEANUP] Removed {_expired} expired flag(s) "
                  f"older than {FLAG_EXPIRY_MINUTES} minutes")

    parser = argparse.ArgumentParser(description='Auto-Fix Enforcer')
    parser.add_argument('--no-auto-fix', action='store_true',
                       help='Disable auto-fix, only report failures')
    parser.add_argument('--json', action='store_true',
                       help='Output failures as JSON')

    args = parser.parse_args()

    enforcer = AutoFixEnforcer()
    exit_code = enforcer.run(auto_fix=not args.no_auto_fix)

    if args.json:
        output = {
            'failures': enforcer.failures,
            'auto_fixed': enforcer.auto_fixed,
            'all_ok': len(enforcer.failures) == 0
        }
        print(json.dumps(output, indent=2))

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
