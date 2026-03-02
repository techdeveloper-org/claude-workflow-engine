"""
Session Tracker
Tracks and manages Claude sessions with unique IDs
"""

import os
import json
from pathlib import Path
import sys

# Add path resolver for portable paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.path_resolver import get_data_dir, get_logs_dir
from datetime import datetime
import uuid

class SessionTracker:
    def __init__(self):
        self.memory_dir = get_data_dir()
        self.sessions_dir = self.memory_dir / 'sessions'
        self.session_logs_dir = self.memory_dir / 'logs' / 'sessions'
        self.progress_file = self.memory_dir / 'logs' / 'session-progress.json'

    def get_current_session(self):
        """Get current active session from session-progress.json (written by hooks)"""
        try:
            if self.progress_file.exists():
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    progress = json.load(f)
                session_id = progress.get('session_id', '')
                if session_id:
                    # Build session data from progress + flow-trace
                    started_at = progress.get('started_at', datetime.now().isoformat())
                    try:
                        start_time = datetime.fromisoformat(started_at)
                    except Exception:
                        start_time = datetime.now()
                    duration = (datetime.now() - start_time).total_seconds()

                    session = {
                        'session_id': session_id,
                        'start_time': started_at,
                        'status': 'active',
                        'duration_minutes': round(duration / 60, 1),
                        'metrics': {
                            'tokens_used': 0,
                            'policies_hit': progress.get('total_progress', 0),
                            'context_optimizations': progress.get('context_estimate_pct', 0),
                            'failures_prevented': 0,
                            'model_switches': 0,
                            'errors': progress.get('errors_seen', 0),
                            'tasks_completed': progress.get('tasks_completed', 0),
                            'tool_counts': progress.get('tool_counts', {}),
                        },
                        'activities': []
                    }
                    return session
        except Exception as e:
            print(f"Error reading current session: {e}")

        return self._create_empty_session()

    def _create_empty_session(self):
        """Return an empty session placeholder (no fake file creation)"""
        return {
            'session_id': 'no-active-session',
            'start_time': datetime.now().isoformat(),
            'status': 'idle',
            'duration_minutes': 0,
            'metrics': {
                'tokens_used': 0, 'policies_hit': 0, 'context_optimizations': 0,
                'failures_prevented': 0, 'model_switches': 0, 'errors': 0
            },
            'activities': []
        }

    def update_session_metrics(self):
        """Update current session metrics from logs"""
        session = self.get_current_session()

        # Read policy-hits.log for this session
        policy_log = self.memory_dir / 'logs' / 'policy-hits.log'

        if policy_log.exists():
            try:
                with open(policy_log, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                # Get lines from current session start time
                session_start = datetime.fromisoformat(session['start_time'])

                context_opts = 0
                failures_prevented = 0
                policies_hit = 0

                for line in lines:
                    # Parse timestamp
                    import re
                    match = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', line)
                    if match:
                        try:
                            log_time = datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
                            if log_time >= session_start:
                                policies_hit += 1
                                if 'CONTEXT_OPTIMIZATION' in line:
                                    context_opts += 1
                                elif 'FAILURE_PREVENTION' in line:
                                    failures_prevented += 1
                        except:
                            pass

                session['metrics']['policies_hit'] = policies_hit
                session['metrics']['context_optimizations'] = context_opts
                session['metrics']['failures_prevented'] = failures_prevented

                # Save updated session
                with open(self.current_session_file, 'w', encoding='utf-8') as f:
                    json.dump(session, f, indent=2)

            except Exception as e:
                print(f"Error updating session metrics: {e}")

        return session

    def end_current_session(self):
        """End current session and save to history"""
        session = self.get_current_session()

        session['end_time'] = datetime.now().isoformat()
        session['status'] = 'completed'

        # Calculate final duration
        start_time = datetime.fromisoformat(session['start_time'])
        end_time = datetime.fromisoformat(session['end_time'])
        duration = (end_time - start_time).total_seconds()
        session['duration_minutes'] = round(duration / 60, 1)

        # Add to history
        history = self.get_sessions_history()
        history.append(session)

        # Keep only last 50 sessions
        if len(history) > 50:
            history = history[-50:]

        # Save history
        with open(self.sessions_history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2)

        # Remove current session file
        if self.current_session_file.exists():
            self.current_session_file.unlink()

        return session

    def get_sessions_history(self):
        """Get all previous sessions"""
        if self.sessions_history_file.exists():
            try:
                with open(self.sessions_history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading sessions history: {e}")

        return []

    def get_last_session(self):
        """Get the last completed session"""
        history = self.get_sessions_history()
        if history:
            return history[-1]
        return None

    def compare_sessions(self, session1, session2):
        """Compare two sessions"""
        if not session1 or not session2:
            return None

        comparison = {
            'session1': {
                'id': session1['session_id'],
                'duration': session1.get('duration_minutes', 0),
                'metrics': session1.get('metrics', {})
            },
            'session2': {
                'id': session2['session_id'],
                'duration': session2.get('duration_minutes', 0),
                'metrics': session2.get('metrics', {})
            },
            'differences': {}
        }

        # Calculate differences
        metrics1 = session1.get('metrics', {})
        metrics2 = session2.get('metrics', {})

        for key in metrics1.keys():
            val1 = metrics1.get(key, 0)
            val2 = metrics2.get(key, 0)
            diff = val2 - val1

            if val1 > 0:
                percent = round((diff / val1) * 100, 1)
            else:
                percent = 0 if val2 == 0 else 100

            comparison['differences'][key] = {
                'value': diff,
                'percent': percent,
                'direction': 'up' if diff > 0 else 'down' if diff < 0 else 'same'
            }

        return comparison

    def get_session_logs(self, session_id):
        """Get logs for a specific session"""
        # This would require session-specific logging
        # For now, return empty list
        return []

    def get_all_sessions_summary(self):
        """Get summary of all sessions"""
        history = self.get_sessions_history()
        current = self.get_current_session()

        total_sessions = len(history)
        if current['status'] == 'active':
            total_sessions += 1

        # Calculate averages
        if history:
            avg_duration = sum(s.get('duration_minutes', 0) for s in history) / len(history)
            avg_policies = sum(s.get('metrics', {}).get('policies_hit', 0) for s in history) / len(history)
            avg_optimizations = sum(s.get('metrics', {}).get('context_optimizations', 0) for s in history) / len(history)
        else:
            avg_duration = 0
            avg_policies = 0
            avg_optimizations = 0

        return {
            'total_sessions': total_sessions,
            'current_session': current,
            'last_session': self.get_last_session(),
            'averages': {
                'duration': round(avg_duration, 1),
                'policies_hit': round(avg_policies, 1),
                'optimizations': round(avg_optimizations, 1)
            }
        }
