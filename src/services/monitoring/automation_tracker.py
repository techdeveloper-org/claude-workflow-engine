"""
Automation System Tracker - Track Claude Memory System automation components.

Monitors the automation features embedded in the 3-Level Architecture and
surfaced via flow-trace.json session data. Tracks session-start recommendations
derived from the most recent session, task breakdown enforcement statistics
(complexity distribution, average tasks per session), and git auto-commit activity.

Reads from:
  - ~/.claude/memory/logs/sessions/*/flow-trace.json (primary source)
  - ~/.claude/memory/.last-automation-check.json (legacy fallback)
  - ~/.claude/memory/logs/git-auto-commit.log (commit statistics)

Key responsibilities:
  - Return session-start recommendations (model, skills, context status) from
    the most recent flow-trace.json final_decision
  - Compute task breakdown statistics: avg task count, complexity distribution,
    plan mode usage, and recent breakdowns
  - Retrieve git auto-commit statistics (total commits, recent entries)
  - Combine all automation statistics in a single comprehensive call

Classes:
  AutomationTracker: Tracks all Claude Memory System automation components.
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add path resolver for portable paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.path_resolver import get_data_dir, get_logs_dir
from collections import defaultdict


class AutomationTracker:
    """Track Claude Memory System automation components and session recommendations.

    Reads flow-trace.json session files and legacy automation state files to
    produce statistics about session recommendations, task breakdowns, and
    git commit activity.

    Attributes:
        memory_dir (Path): Root data directory (~/.claude/memory).
        logs_dir (Path): Path to the logs subdirectory.
        sessions_dir (Path): Path to the sessions state directory.
    """

    def __init__(self):
        self.memory_dir = get_data_dir()
        self.logs_dir = self.memory_dir / 'logs'
        self.sessions_dir = self.memory_dir / 'sessions'

    def get_auto_commit_stats(self):
        """Get git auto-commit automation statistics from git-auto-commit.log.

        Reads git-auto-commit.log and counts total commit events and
        automatically triggered commit events. Returns the last 10 commit lines.

        Returns:
            dict: Git auto-commit stats with keys:
                total_commits (int): Lines containing 'COMMIT' in the log.
                commits_today (int): Always 0 (not yet implemented for this method).
                auto_triggered (int): Lines where 'AUTO' appears in the log.
                recent_commits (list[str]): Last 10 lines containing 'COMMIT'.
        """
        git_log = self.logs_dir / 'git-auto-commit.log'
        stats = {
            'total_commits': 0,
            'commits_today': 0,
            'auto_triggered': 0,
            'recent_commits': []
        }
        if git_log.exists():
            try:
                lines = git_log.read_text(encoding='utf-8', errors='ignore').splitlines()
                stats['total_commits'] = len([l for l in lines if 'COMMIT' in l])
                stats['auto_triggered'] = len([l for l in lines if 'AUTO' in l.upper()])
                stats['recent_commits'] = [l for l in lines[-10:] if 'COMMIT' in l]
            except Exception as e:
                stats['error'] = str(e)
        return stats

    def get_session_start_recommendations(self):
        """Return the latest session-start recommendations for the dashboard.

        Primary source: reads the most recent flow-trace.json file in the sessions
        log directory and extracts model, skill/agent, context status, and standards
        from final_decision.

        Fallback: reads .last-automation-check.json (legacy format) when no session
        traces exist.

        Returns:
            dict: Recommendation data with keys:
                available (bool): True when recommendations could be loaded.
                timestamp (str): ISO flow start time.
                session_id (str): Session identifier from the last run.
                model_recommendation (str): Recommended model (e.g. 'SONNET').
                model_reason (str): Reason for the model recommendation.
                skills_recommended (list[str]): Recommended skill names.
                agents_recommended (list[str]): Recommended agent names.
                context_status (str): 'GREEN', 'YELLOW', 'ORANGE', or 'RED'.
                context_percentage (float): Context window usage percentage.
                standards_active (int): Active standards count.
                rules_active (int): Active rules count.
                task_type (str): Detected task type.
                complexity (int): Complexity score.
                tech_stack (list[str]): Detected technologies.
                optimizations_needed (list[str]): Recommended optimizations.
                source (str): 'flow-trace' or 'check-file'.
            On failure returns dict with available=False and error/message keys.
        """
        sessions_dir = self.logs_dir / 'sessions'

        # Fallback: check legacy .last-automation-check.json
        def _load_from_check_file():
            check_file = self.memory_dir / '.last-automation-check.json'
            if not check_file.exists():
                return None
            try:
                data = json.loads(check_file.read_text(encoding='utf-8', errors='ignore'))
                return {
                    'available': True,
                    'model_recommendation': data.get('model', 'SONNET'),
                    'skills_recommended': data.get('skills', []),
                    'agents_recommended': [],
                    'context_status': data.get('context_status', 'GREEN'),
                    'context_percentage': data.get('context_percentage', 0),
                    'source': 'check-file'
                }
            except Exception:
                return None

        if not sessions_dir.exists():
            fallback = _load_from_check_file()
            if fallback:
                return fallback
            return {
                'available': False,
                'message': 'No sessions found. Send a message to Claude Code first.',
                'recommendations': None
            }

        try:
            trace_files = sorted(
                sessions_dir.glob('*/flow-trace.json'),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

            if not trace_files:
                fallback = _load_from_check_file()
                if fallback:
                    return fallback
                return {
                    'available': False,
                    'message': 'No flow-trace sessions found.',
                    'recommendations': None
                }

            data = json.loads(trace_files[0].read_text(encoding='utf-8', errors='ignore'))
            fd = data.get('final_decision', {})
            meta = data.get('meta', {})

            # Derive context status from LEVEL_1_CONTEXT step
            context_status = 'UNKNOWN'
            context_pct = fd.get('context_pct', 0)
            if context_pct < 70:
                context_status = 'GREEN'
            elif context_pct < 80:
                context_status = 'YELLOW'
            elif context_pct < 85:
                context_status = 'ORANGE'
            else:
                context_status = 'RED'

            # Derive skill/agent recommendation
            skill_or_agent = fd.get('skill_or_agent', 'adaptive-skill-intelligence')
            skills_recommended = fd.get('supplementary_skills', [])
            agents_recommended = []
            if 'agent' in skill_or_agent.lower() or skill_or_agent.endswith('-engineer') or skill_or_agent.endswith('-agent'):
                agents_recommended = [skill_or_agent]
            else:
                if skill_or_agent and skill_or_agent != 'adaptive-skill-intelligence':
                    skills_recommended = [skill_or_agent] + skills_recommended

            return {
                'available': True,
                'timestamp': meta.get('flow_start', datetime.now().isoformat()),
                'session_id': fd.get('session_id', ''),
                'model_recommendation': fd.get('model_selected', 'SONNET'),
                'model_reason': fd.get('model_reason', ''),
                'skills_recommended': skills_recommended,
                'agents_recommended': agents_recommended,
                'context_status': context_status,
                'context_percentage': context_pct,
                'standards_active': fd.get('standards_active', 0),
                'rules_active': fd.get('rules_active', 0),
                'task_type': fd.get('task_type', ''),
                'complexity': fd.get('complexity', 0),
                'tech_stack': fd.get('tech_stack', []),
                'optimizations_needed': ['offset/limit'] if context_pct >= 70 else [],
                'source': 'flow-trace'
            }

        except Exception as e:
            return {
                'available': False,
                'error': str(e),
                'message': 'Failed to read flow-trace recommendations'
            }

    def _is_process_running(self, pid):
        """Check if a process is currently running.

        Attempts psutil.pid_exists first, falls back to os.kill(pid, 0)
        on systems without psutil.

        Args:
            pid (int): Process ID to check.

        Returns:
            bool: True if the process is running, False otherwise.
        """
        try:
            import psutil
            return psutil.pid_exists(pid)
        except ImportError:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

    def get_task_breakdown_stats(self):
        """Track task breakdown enforcement statistics across sessions.

        Reads up to 200 most-recent flow-trace.json files and aggregates task
        count and complexity data from final_decision.

        Returns:
            dict: Task breakdown stats with keys:
                total_analyses (int): Sessions with final_decision data.
                tasks_required (int): Sessions where task_count >= 3.
                phases_required (int): Sessions where task_count >= 5 or complexity >= 10.
                complexity_distribution (dict): Map of complexity bucket label to count.
                recent_breakdowns (list[dict]): Last 10 breakdowns with timestamp,
                    task_count, complexity, task_type, model, plan_mode, session_id.
                avg_tasks_per_session (float): Average task_count.
                avg_complexity (float): Average complexity score.
        """
        stats = {
            'total_analyses': 0,
            'tasks_required': 0,
            'phases_required': 0,
            'complexity_distribution': defaultdict(int),
            'recent_breakdowns': [],
            'avg_tasks_per_session': 0,
            'avg_complexity': 0
        }

        sessions_dir = self.logs_dir / 'sessions'
        if not sessions_dir.exists():
            stats['complexity_distribution'] = {}
            return stats

        try:
            trace_files = sorted(
                sessions_dir.glob('*/flow-trace.json'),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )[:200]

            total_tasks = 0
            total_complexity = 0

            for tf in trace_files:
                try:
                    data = json.loads(tf.read_text(encoding='utf-8', errors='ignore'))
                    fd = data.get('final_decision', {})
                    complexity = fd.get('complexity', 0)
                    task_count = fd.get('task_count', 1)

                    if not fd:
                        continue

                    stats['total_analyses'] += 1
                    total_complexity += complexity
                    total_tasks += task_count

                    # Track breakdown thresholds
                    if task_count >= 3:
                        stats['tasks_required'] += 1
                    if task_count >= 5 or complexity >= 10:
                        stats['phases_required'] += 1

                    # Track complexity distribution (bucket into 0-4, 5-9, 10-14, 15+)
                    if complexity <= 4:
                        stats['complexity_distribution']['simple (0-4)'] += 1
                    elif complexity <= 9:
                        stats['complexity_distribution']['moderate (5-9)'] += 1
                    elif complexity <= 14:
                        stats['complexity_distribution']['complex (10-14)'] += 1
                    else:
                        stats['complexity_distribution']['very_complex (15+)'] += 1

                    # Store recent (last 10)
                    if len(stats['recent_breakdowns']) < 10:
                        stats['recent_breakdowns'].append({
                            'timestamp': data.get('meta', {}).get('flow_start', datetime.now().isoformat()),
                            'task_count': task_count,
                            'complexity': complexity,
                            'task_type': fd.get('task_type', ''),
                            'model': fd.get('model_selected', ''),
                            'plan_mode': fd.get('plan_mode', False),
                            'session_id': fd.get('session_id', '')
                        })

                except Exception:
                    continue

            # Calculate averages
            if stats['total_analyses'] > 0:
                stats['avg_tasks_per_session'] = round(total_tasks / stats['total_analyses'], 1)
                stats['avg_complexity'] = round(total_complexity / stats['total_analyses'], 1)

            # Convert defaultdict to regular dict
            stats['complexity_distribution'] = dict(stats['complexity_distribution'])

        except Exception as e:
            stats['error'] = str(e)
            stats['complexity_distribution'] = dict(stats['complexity_distribution'])

        return stats

    def get_task_tracker_stats(self):
        """Get task auto-tracker statistics for automatic progress updates.

        Returns placeholder statistics. Full implementation will track
        automatic task progress updates from the post-tool-tracker hook.

        Returns:
            dict: Task tracker stats with keys:
                enabled (bool): Always True (feature is enabled).
                total_tasks_tracked (int): Always 0 (not yet implemented).
                auto_updates (int): Always 0 (not yet implemented).
                manual_updates (int): Always 0 (not yet implemented).
                completion_rate (int): Always 0 (not yet implemented).
                average_progress_updates (int): Always 0 (not yet implemented).
        """
        # This would read from task tracking logs
        # For now, return placeholder
        return {
            'enabled': True,
            'total_tasks_tracked': 0,
            'auto_updates': 0,
            'manual_updates': 0,
            'completion_rate': 0,
            'average_progress_updates': 0
        }

    def get_comprehensive_automation_stats(self):
        """Get all automation statistics aggregated in one call.

        Combines session-start recommendations, task breakdown statistics,
        and task tracker stats into a single dict for efficient dashboard rendering.

        Returns:
            dict: All automation stats with keys:
                session_start (dict): Output of get_session_start_recommendations().
                task_breakdown (dict): Output of get_task_breakdown_stats().
                task_tracker (dict): Output of get_task_tracker_stats().
                timestamp (str): ISO-format current timestamp.
        """
        return {
            'session_start': self.get_session_start_recommendations(),
            'task_breakdown': self.get_task_breakdown_stats(),
            'task_tracker': self.get_task_tracker_stats(),
            'timestamp': datetime.now().isoformat()
        }
