"""
Memory System Integration Monitor - Monitor all Claude Memory System components.

Provides comprehensive health monitoring for the Claude Memory System v3.2.0
(3-Level Architecture). Tracks hook script presence, policy enforcement statistics,
context optimization, failure prevention, model selection distribution, session
memory usage, and git auto-commit activity.

Reads from:
  - ~/.claude/scripts/ (hook script presence checks)
  - ~/.claude/memory/logs/policy-hits.log (enforcement events)
  - ~/.claude/memory/logs/sessions/*/flow-trace.json (model distribution, sessions)
  - ~/.claude/memory/logs/auto-enforcement.log (auto-fix events)
  - ~/.claude/memory/logs/git-auto-commit.log (commit history)
  - ~/.claude/memory/logs/failures.log (failure prevention events)
  - ~/.claude/memory/failure-kb.json (failure knowledge base)
  - ~/.claude/memory/.cache/ (context cache stats)

Key responsibilities:
  - Report hook script status (replaces daemon process monitoring removed in v3.3.0)
  - Compute a 100-point health score: hooks (60pts) + policies (20pts) + session activity (20pts)
  - Provide per-component statistics for policy, context, failure prevention, and git commits
  - Return a complete system overview for the dashboard health card

Classes:
  MemorySystemMonitor: Central monitor for all Claude Memory System components.
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add path resolver for portable paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.path_resolver import get_data_dir, get_logs_dir, get_scripts_dir, get_policies_dir
from collections import defaultdict


class MemorySystemMonitor:
    """Monitor Claude Memory System v3.2.0 (3-Level Architecture) health, policies, and automation.

    Provides methods to check hook script availability, compute health scores,
    gather policy enforcement statistics, context optimization data, failure
    prevention metrics, model selection distribution, session memory usage,
    and git auto-commit history.

    Attributes:
        memory_dir (Path): Root data directory (~/.claude/memory).
        logs_dir (Path): Path to the logs subdirectory.
        sessions_dir (Path): Path to the sessions state directory.
        daemons (list[str]): Legacy daemon name list (kept for reference only;
            daemons were removed in v3.3.0 and replaced with hooks).
    """

    def __init__(self):
        self.memory_dir = get_data_dir()
        self.logs_dir = self.memory_dir / 'logs'
        self.sessions_dir = self.memory_dir / 'sessions'

        # Daemon tracking (10 core daemons)
        self.daemons = [
            'context-daemon',
            'session-auto-save-daemon',
            'preference-auto-tracker',  # Fixed: was preference-tracker-daemon
            'skill-auto-suggester',     # Fixed: was skill-suggester-daemon
            'commit-daemon',             # Fixed: was git-auto-commit-daemon
            'session-pruning-daemon',
            'pattern-detection-daemon',
            'failure-prevention-daemon',
            'token-optimization-daemon', # NEW: Added
            'health-monitor-daemon'      # NEW: Added
        ]

    def get_daemon_status(self):
        """Return the status of the three core Claude Code hook scripts.

        Daemons were removed in v3.3.0 and replaced with Claude Code hooks.
        Checks whether each hook script file exists in get_scripts_dir() and
        reports 'running' (file present) or 'stopped' (file absent).

        Returns:
            list[dict]: One record per hook script, each with keys:
                name (str): Friendly script identifier.
                status (str): 'running' if the file exists, 'stopped' otherwise.
                pid (None): Always None (hooks have no persistent PIDs).
                last_activity (str or None): Last modification timestamp 'YYYY-MM-DD HH:MM:SS'.
                description (str): Human-readable description of the hook's role.
                type (str): Always 'hook'.
        """
        scripts_dir = get_scripts_dir()

        # Map hook scripts to friendly names (replaces daemon list)
        hook_scripts = [
            ('3-level-flow.py', '3-level-flow', 'UserPromptSubmit hook - runs 3-level architecture'),
            ('clear-session-handler.py', 'clear-session-handler', 'UserPromptSubmit hook - session state management'),
            ('stop-notifier.py', 'stop-notifier', 'Stop hook - session summary and voice notification'),
        ]

        statuses = []
        for script_file, name, description in hook_scripts:
            script_path = scripts_dir / script_file
            exists = script_path.exists()
            status = {
                'name': name,
                'status': 'running' if exists else 'stopped',
                'pid': None,
                'last_activity': None,
                'description': description,
                'type': 'hook'
            }

            if exists:
                try:
                    mtime = datetime.fromtimestamp(script_path.stat().st_mtime)
                    status['last_activity'] = mtime.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass

            statuses.append(status)

        return statuses

    def _is_process_running(self, pid):
        """Check if a process is currently running (cross-platform).

        Attempts to use psutil for process existence check. Falls back to
        os.kill(pid, 0) on platforms without psutil.

        Args:
            pid (int): Process ID to check.

        Returns:
            bool: True if the process is running, False otherwise.
        """
        try:
            import psutil
            return psutil.pid_exists(pid)
        except ImportError:
            # Fallback for systems without psutil
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

    def get_policy_enforcement_stats(self):
        """Get policy enforcement statistics aggregated from policy-hits.log.

        Reads the last 100 entries from policy-hits.log and groups them
        by policy name. Also captures recent activity for the dashboard.

        Returns:
            dict: Enforcement stats with keys:
                total_enforcements (int): Total number of log entries.
                by_policy (dict): Map of policy name to hit count.
                recent_activity (list[dict]): Last 10 entries as
                    {timestamp, policy, action} dicts.
        """
        policy_hits_file = self.logs_dir / 'policy-hits.log'

        if not policy_hits_file.exists():
            return {'total_enforcements': 0, 'by_policy': {}, 'recent_activity': []}

        try:
            lines = policy_hits_file.read_text().splitlines()

            by_policy = defaultdict(int)
            recent_activity = []

            for line in lines[-100:]:  # Last 100 entries
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 2:
                        policy_name = parts[1].strip()
                        by_policy[policy_name] += 1

                        if len(recent_activity) < 10:
                            recent_activity.append({
                                'timestamp': parts[0].strip() if len(parts) > 0 else '',
                                'policy': policy_name,
                                'action': parts[2].strip() if len(parts) > 2 else ''
                            })

            return {
                'total_enforcements': len(lines),
                'by_policy': dict(by_policy),
                'recent_activity': recent_activity
            }
        except Exception as e:
            print(f"Error reading policy hits: {e}")
            return {'total_enforcements': 0, 'by_policy': {}, 'recent_activity': []}

    def get_context_optimization_stats(self):
        """Get context optimization and cache usage statistics.

        Reads from the .cache/ directory and context-related log files
        to compute cache file counts, total cache size, cache hit counts,
        estimated token savings, and number of optimizations applied.

        Returns:
            dict: Cache and optimization stats with keys:
                cache_size (int): Total cache size in bytes.
                cached_files (int): Number of cached JSON files.
                cache_hits (int): Count of 'CACHE HIT' entries in context-cache.log.
                token_savings (int): Estimated tokens saved (cache_hits * 500).
                optimizations_applied (int): Lines in optimizations.log.
        """
        cache_dir = self.memory_dir / '.cache'

        stats = {
            'cache_size': 0,
            'cached_files': 0,
            'cache_hits': 0,
            'token_savings': 0,
            'optimizations_applied': 0
        }

        if cache_dir.exists():
            try:
                cached_files = list(cache_dir.glob('*.json'))
                stats['cached_files'] = len(cached_files)

                # Calculate total cache size
                total_size = sum(f.stat().st_size for f in cached_files)
                stats['cache_size'] = total_size

                # Read cache hits from log
                cache_log = self.logs_dir / 'context-cache.log'
                if cache_log.exists():
                    lines = cache_log.read_text().splitlines()
                    stats['cache_hits'] = len([l for l in lines if 'CACHE HIT' in l])
                    stats['token_savings'] = stats['cache_hits'] * 500  # Estimated
            except Exception as e:
                print(f"Error reading cache stats: {e}")

        # Read optimization log
        opt_log = self.logs_dir / 'optimizations.log'
        if opt_log.exists():
            try:
                lines = opt_log.read_text().splitlines()
                stats['optimizations_applied'] = len(lines)
            except Exception:
                pass

        return stats

    def get_failure_prevention_stats(self):
        """Get failure prevention and auto-fix statistics.

        Reads failures.log for total prevented failures and auto-fix counts,
        categorizing by tool (Bash, Edit, Read, Grep). Also reads
        failure-kb.json to count learned patterns.

        Returns:
            dict: Failure prevention stats with keys:
                failures_prevented (int): Total entries in failures.log.
                auto_fixes_applied (int): Lines with 'FIXED' in failures.log.
                patterns_learned (int): Total patterns in failure-kb.json.
                by_tool (dict): Map of tool name to auto-fix count.
                recent_fixes (list): Reserved for future use (currently empty).
        """
        failures_file = self.logs_dir / 'failures.log'
        kb_file = self.memory_dir / 'failure-kb.json'

        stats = {
            'failures_prevented': 0,
            'auto_fixes_applied': 0,
            'patterns_learned': 0,
            'by_tool': {},
            'recent_fixes': []
        }

        # Read failures log
        if failures_file.exists():
            try:
                lines = failures_file.read_text().splitlines()
                stats['failures_prevented'] = len(lines)

                by_tool = defaultdict(int)
                for line in lines[-50:]:
                    if 'FIXED' in line:
                        stats['auto_fixes_applied'] += 1
                        if 'Bash:' in line:
                            by_tool['Bash'] += 1
                        elif 'Edit:' in line:
                            by_tool['Edit'] += 1
                        elif 'Read:' in line:
                            by_tool['Read'] += 1
                        elif 'Grep:' in line:
                            by_tool['Grep'] += 1

                stats['by_tool'] = dict(by_tool)
            except Exception as e:
                print(f"Error reading failures log: {e}")

        # Read KB
        if kb_file.exists():
            try:
                kb_data = json.loads(kb_file.read_text())
                for tool, patterns in kb_data.items():
                    if isinstance(patterns, list):
                        stats['patterns_learned'] += len(patterns)
            except Exception:
                pass

        return stats

    def get_model_selection_distribution(self):
        """Return model selection distribution across recent sessions.

        Reads up to 200 most-recent flow-trace.json files and counts how often
        each model class (haiku, sonnet, opus) was selected via
        final_decision.model_selected.

        Returns:
            dict: Model distribution with keys:
                total_requests (int): Sessions with a model_selected value.
                haiku (int): Count of haiku selections.
                sonnet (int): Count of sonnet selections.
                opus (int): Count of opus selections.
                haiku_percent (float): Percentage of haiku selections.
                sonnet_percent (float): Percentage of sonnet selections.
                opus_percent (float): Percentage of opus selections.
        """
        stats = {
            'total_requests': 0,
            'haiku': 0,
            'sonnet': 0,
            'opus': 0,
            'haiku_percent': 0,
            'sonnet_percent': 0,
            'opus_percent': 0
        }

        sessions_dir = self.logs_dir / 'sessions'
        if not sessions_dir.exists():
            return stats

        try:
            trace_files = sorted(
                sessions_dir.glob('*/flow-trace.json'),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )[:200]

            for tf in trace_files:
                try:
                    data = json.loads(tf.read_text(encoding='utf-8', errors='ignore'))
                    fd = data.get('final_decision', {})
                    model = fd.get('model_selected', '').lower()
                    if not model:
                        continue
                    stats['total_requests'] += 1
                    if 'haiku' in model:
                        stats['haiku'] += 1
                    elif 'sonnet' in model:
                        stats['sonnet'] += 1
                    elif 'opus' in model:
                        stats['opus'] += 1
                except Exception:
                    continue

            if stats['total_requests'] > 0:
                stats['haiku_percent'] = round((stats['haiku'] / stats['total_requests']) * 100, 1)
                stats['sonnet_percent'] = round((stats['sonnet'] / stats['total_requests']) * 100, 1)
                stats['opus_percent'] = round((stats['opus'] / stats['total_requests']) * 100, 1)

        except Exception as e:
            print(f"Error reading model distribution: {e}")

        return stats

    def get_session_memory_stats(self):
        """Get session memory storage and usage statistics.

        Counts session directories in logs/sessions/ and computes total disk
        usage. Sessions with a flow-trace.json modified within the last 7 days
        are counted as active. Also reads session-pruning.log for pruned count.

        Returns:
            dict: Session memory stats with keys:
                total_sessions (int): Total number of session directories.
                active_sessions (int): Sessions modified within the last 7 days.
                pruned_sessions (int): Count of 'PRUNED' entries in pruning log.
                total_size_mb (float): Total disk usage of all session data in MB.
        """
        stats = {
            'total_sessions': 0,
            'active_sessions': 0,
            'pruned_sessions': 0,
            'total_size_mb': 0
        }

        # Session log dirs are under logs/sessions/ (contain flow-trace.json)
        log_sessions_dir = self.logs_dir / 'sessions'
        if log_sessions_dir.exists():
            try:
                session_dirs = [d for d in log_sessions_dir.iterdir() if d.is_dir()]
                stats['total_sessions'] = len(session_dirs)

                total_size = 0
                for session_dir in session_dirs:
                    # Check if session is active (flow-trace.json modified in last 7 days)
                    trace_file = session_dir / 'flow-trace.json'
                    if trace_file.exists():
                        mtime = datetime.fromtimestamp(trace_file.stat().st_mtime)
                        if datetime.now() - mtime < timedelta(days=7):
                            stats['active_sessions'] += 1

                    # Calculate size
                    for file in session_dir.rglob('*'):
                        if file.is_file():
                            total_size += file.stat().st_size

                stats['total_size_mb'] = round(total_size / (1024 * 1024), 2)
            except Exception as e:
                print(f"Error reading session stats: {e}")

        # Check pruning log
        prune_log = self.logs_dir / 'session-pruning.log'
        if prune_log.exists():
            try:
                lines = prune_log.read_text().splitlines()
                stats['pruned_sessions'] = len([l for l in lines if 'PRUNED' in l])
            except Exception:
                pass

        return stats

    def get_git_autocommit_stats(self):
        """Get git auto-commit activity statistics from git-auto-commit.log.

        Parses git-auto-commit.log to count total commits, commits today,
        commits this week, and returns the last 10 commit log lines.

        Returns:
            dict: Git auto-commit stats with keys:
                total_commits (int): Total lines with 'COMMIT' in the log.
                commits_today (int): Commits since midnight today.
                commits_this_week (int): Commits in the last 7 days.
                recent_commits (list[str]): Last 10 log lines containing 'COMMIT'.
        """
        git_log = self.logs_dir / 'git-auto-commit.log'

        stats = {
            'total_commits': 0,
            'commits_today': 0,
            'commits_this_week': 0,
            'recent_commits': []
        }

        if git_log.exists():
            try:
                lines = git_log.read_text().splitlines()
                stats['total_commits'] = len([l for l in lines if 'COMMIT' in l])

                now = datetime.now()
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                week_start = now - timedelta(days=7)

                for line in lines:
                    if '[' in line and ']' in line:
                        try:
                            timestamp_str = line.split('[')[1].split(']')[0]
                            timestamp = datetime.fromisoformat(timestamp_str)

                            if timestamp >= today_start:
                                stats['commits_today'] += 1
                            if timestamp >= week_start:
                                stats['commits_this_week'] += 1
                        except Exception:
                            pass

                # Get recent commits
                for line in lines[-10:]:
                    if 'COMMIT' in line:
                        stats['recent_commits'].append(line)
            except Exception as e:
                print(f"Error reading git log: {e}")

        return stats

    def get_system_health_score(self):
        """Calculate the overall memory system health score (0-100).

        Hooks-based scoring formula (daemons removed in v3.3.0):
            - 60 points: Three hook scripts present in scripts_dir (20 pts each).
            - 20 points: Three core policy scripts present (prorated).
            - 20 points: Session log traces exist:
                * 20 pts if any trace modified within last 24 hours.
                * 10 pts if traces exist but none are recent.

        Returns:
            dict: Health score breakdown with keys:
                overall_score (float): Total score 0-100.
                hooks_health (float): Hook script component score.
                policy_health (float): Policy script component score.
                session_activity (float): Session activity component score.
                hooks_present (int): Number of hook scripts found.
                hooks_total (int): Total expected hook scripts (3).
                status (str): 'healthy' (>=80), 'degraded' (>=60), or 'critical' (<60).
        """
        scripts_dir = get_scripts_dir()

        # 60pts: Hook scripts (3 scripts, 20pts each)
        hook_scripts = ['3-level-flow.py', 'clear-session-handler.py', 'stop-notifier.py']
        hooks_present = sum(1 for s in hook_scripts if (scripts_dir / s).exists())
        hooks_score = int((hooks_present / len(hook_scripts)) * 60)

        # 20pts: Core policy scripts present
        policy_scripts = ['auto-fix-enforcer.py', 'context-monitor-v2.py', 'pre-tool-enforcer.py']
        policies_present = sum(1 for s in policy_scripts if (scripts_dir / s).exists())
        policy_score = int((policies_present / len(policy_scripts)) * 20)

        # 20pts: Session logs exist and are recent
        sessions_dir = self.logs_dir / 'sessions'
        session_score = 0
        if sessions_dir.exists():
            recent_traces = list(sessions_dir.glob('*/flow-trace.json'))
            if recent_traces:
                # Check if any session is in last 24h
                cutoff = datetime.now() - timedelta(hours=24)
                recent = [t for t in recent_traces if datetime.fromtimestamp(t.stat().st_mtime) > cutoff]
                session_score = 20 if recent else 10  # 10 if traces exist but not recent

        total_score = hooks_score + policy_score + session_score

        return {
            'overall_score': round(total_score, 1),
            'hooks_health': round(hooks_score, 1),
            'policy_health': round(policy_score, 1),
            'session_activity': round(session_score, 1),
            'hooks_present': hooks_present,
            'hooks_total': len(hook_scripts),
            'status': 'healthy' if total_score >= 80 else 'degraded' if total_score >= 60 else 'critical'
        }

    def get_system_overview(self):
        """Get a high-level system overview dict for the dashboard.

        Returns:
            dict: Overview with keys:
                health_score (float): Overall health score (0-100).
                status (str): 'healthy', 'degraded', or 'critical'.
                hooks_present (int): Number of hook scripts found.
                hooks_total (int): Total expected hook scripts.
                daemons (list[dict]): Hook script status list from get_daemon_status().
                timestamp (str): ISO-format current timestamp.
        """
        health = self.get_system_health_score()
        return {
            'health_score': health['overall_score'],
            'status': health['status'],
            'hooks_present': health['hooks_present'],
            'hooks_total': health['hooks_total'],
            'daemons': self.get_daemon_status(),
            'timestamp': datetime.now().isoformat()
        }

    def get_comprehensive_stats(self):
        """Get all memory system statistics aggregated in one call.

        Combines all monitoring categories into a single dict for efficient
        full-system health reporting.

        Returns:
            dict: All stats with keys:
                system_health (dict): Health score and status.
                daemons (list): Hook script status list.
                policies (dict): Policy enforcement stats.
                context_optimization (dict): Cache and optimization stats.
                failure_prevention (dict): Failure and auto-fix stats.
                model_selection (dict): Model usage distribution.
                session_memory (dict): Session storage stats.
                git_autocommit (dict): Git commit activity.
                timestamp (str): ISO-format current timestamp.
        """
        return {
            'system_health': self.get_system_health_score(),
            'daemons': self.get_daemon_status(),
            'policies': self.get_policy_enforcement_stats(),
            'context_optimization': self.get_context_optimization_stats(),
            'failure_prevention': self.get_failure_prevention_stats(),
            'model_selection': self.get_model_selection_distribution(),
            'session_memory': self.get_session_memory_stats(),
            'git_autocommit': self.get_git_autocommit_stats(),
            'timestamp': datetime.now().isoformat()
        }

    def get_policy_status(self):
        """Get the active/inactive status for all policies based on their file existence.

        Checks whether each policy's .md file exists in the policies directory
        and returns a list of policy status dicts. Policies with files present
        are marked as active.

        Returns:
            list[dict]: Policy status records, each with:
                name (str): Human-readable policy name.
                file (str): Relative path to the policy .md file.
                status (str): 'active' (always set).
                exists (bool): True if the policy file exists on disk.
                active (bool): True if file exists and status is 'active'.
        """
        # Paths relative to memory_dir matching actual 3-level layout
        policies = [
            {'name': 'Core Skills Mandate',
             'file': '03-execution-system/05-skill-agent-selection/core-skills-mandate.md',
             'status': 'active'},
            {'name': 'Model Selection',
             'file': '03-execution-system/04-model-selection/model-selection-enforcement.md',
             'status': 'active'},
            {'name': 'Auto Plan Mode',
             'file': '03-execution-system/02-plan-mode/auto-plan-mode-suggestion-policy.md',
             'status': 'active'},
            {'name': 'Session Memory',
             'file': '01-sync-system/session-management/session-memory-policy.md',
             'status': 'active'},
            {'name': 'Task Breakdown',
             'file': '03-execution-system/01-task-breakdown/automatic-task-breakdown-policy.md',
             'status': 'active'},
            {'name': 'Tool Optimization',
             'file': '03-execution-system/06-tool-optimization/tool-usage-optimization-policy.md',
             'status': 'active'},
            {'name': 'Prompt Generation',
             'file': '03-execution-system/00-prompt-generation/prompt-generation-policy.md',
             'status': 'active'},
            {'name': 'User Preferences',
             'file': '01-sync-system/user-preferences/user-preferences-policy.md',
             'status': 'active'},
            {'name': 'Session Pruning',
             'file': '01-sync-system/session-management/session-pruning-policy.md',
             'status': 'active'},
            {'name': 'Coding Standards',
             'file': '02-standards-system/coding-standards-enforcement-policy.md',
             'status': 'active'},
        ]

        policies_dir = get_policies_dir()
        for policy in policies:
            policy_file = policies_dir / policy['file']
            policy['exists'] = policy_file.exists()
            policy['active'] = policy['exists'] and policy['status'] == 'active'

        return policies
