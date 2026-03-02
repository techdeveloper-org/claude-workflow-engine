"""
Memory System Integration Monitor
Monitors all Claude Memory System v3.2.0 (3-Level Architecture) components, policies, and automation
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
    """Monitor Claude Memory System v3.2.0 (3-Level Architecture) health, policies, and automation"""

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
        """
        Get status of memory system hooks (daemons removed in v3.3.0).
        Now reports on the 3 Claude Code hook scripts instead of daemon PIDs.
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
        """Check if process is running (cross-platform)"""
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
        """Get policy enforcement statistics from policy-hits.log"""
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
        """Get context optimization and cache statistics"""
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
        """Get failure prevention statistics"""
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
        """
        Get model selection distribution stats.
        Reads from flow-trace.json final_decision.model_selected.
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
        """Get session memory statistics"""
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
        """Get git auto-commit statistics"""
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
        """
        Calculate overall memory system health score.
        Hooks-based scoring (daemons removed in v3.3.0):
        - 60pts: Hook scripts present in current/ directory
        - 20pts: Core policy scripts present
        - 20pts: Session logs exist (system is active)
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
        """Get a high-level system overview dict"""
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
        """Get all memory system statistics in one call"""
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
        """Get status of all policies from the actual policy directory structure"""
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
