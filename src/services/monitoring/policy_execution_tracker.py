"""
Policy Execution Tracker - Track real-time policy executions

Monitors and tracks when automation policies are actually executed:
- Prompt Generation (Step 0)
- Task Breakdown (Step 1)
- Plan Mode Decision (Step 2)
- Model Selection (Step 4)
- Skill/Agent Selection (Step 5)
- Tool Optimization (Step 6)

Reads from:
- ~/.claude/memory/logs/policy-hits.log
- ~/.claude/memory/.blocking-enforcer-state.json

Provides real-time metrics for dashboard.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import sys

# Add path for portable imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.path_resolver import get_data_dir


class PolicyExecutionTracker:
    """Track policy executions and provide metrics"""

    def __init__(self):
        self.memory_dir = get_data_dir()
        self.policy_log = self.memory_dir / 'logs' / 'policy-hits.log'
        self.enforcer_state = self.memory_dir / '.blocking-state.json'
        self.tracker_cache = get_data_dir() / 'policy_execution_cache.json'

    def get_enforcer_state(self):
        """
        Get current blocking enforcer state.
        Derives state from most recent flow-trace.json pipeline steps.
        Falls back to .blocking-enforcer-state.json if it exists.
        """
        # Try .blocking-enforcer-state.json first (legacy)
        try:
            if self.enforcer_state.exists():
                with open(self.enforcer_state, 'r') as f:
                    state = json.load(f)
                # Use the file if it exists; optionally skip if it's older than 1 hour
                ts = state.get('session_start_time')
                is_recent = True
                if ts:
                    try:
                        age = datetime.now() - datetime.fromisoformat(ts)
                        is_recent = age.total_seconds() < 3600
                    except Exception:
                        is_recent = True  # Can't determine age, treat as valid
                if is_recent or ts is None:
                    return {
                        'session_started': state.get('session_started', False),
                        'standards_loaded': state.get('standards_loaded', False),
                        'prompt_generated': state.get('prompt_generated', False),
                        'tasks_created': state.get('tasks_created', False),
                        'plan_mode_decided': state.get('plan_mode_decided', False),
                        'model_selected': state.get('model_selected', False),
                        'skills_agents_checked': state.get('skills_agents_checked', False),
                        'context_checked': state.get('context_checked', False),
                        'total_violations': state.get('total_violations', 0),
                        'last_violation': state.get('last_violation'),
                        'session_start_time': state.get('session_start_time')
                    }
        except Exception:
            pass

        # Derive from most recent flow-trace.json
        try:
            sessions_dir = self.memory_dir / 'logs' / 'sessions'
            if sessions_dir.exists():
                trace_files = sorted(
                    sessions_dir.glob('*/flow-trace.json'),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )
                if trace_files:
                    data = json.loads(trace_files[0].read_text(encoding='utf-8', errors='ignore'))
                    pipeline = data.get('pipeline', [])
                    fd = data.get('final_decision', {})
                    meta = data.get('meta', {})

                    # Check which steps passed successfully
                    step_passed = {}
                    for step in pipeline:
                        step_name = step.get('step', '')
                        # A step "passed" if it has duration_ms recorded (ran) and no error
                        step_passed[step_name] = step.get('duration_ms', -1) >= 0

                    return {
                        'session_started': step_passed.get('LEVEL_1_SESSION', False),
                        'standards_loaded': step_passed.get('LEVEL_2_STANDARDS', False),
                        'prompt_generated': step_passed.get('LEVEL_3_STEP_3_0', False),
                        'tasks_created': step_passed.get('LEVEL_3_STEP_3_1', False),
                        'plan_mode_decided': step_passed.get('LEVEL_3_STEP_3_2', False),
                        'model_selected': step_passed.get('LEVEL_3_STEP_3_4', False),
                        'skills_agents_checked': step_passed.get('LEVEL_3_STEP_3_5', False),
                        'context_checked': step_passed.get('LEVEL_1_CONTEXT', False),
                        'total_violations': 0,
                        'last_violation': None,
                        'session_start_time': meta.get('flow_start'),
                        'session_id': fd.get('session_id')
                    }
        except Exception as e:
            print(f"Error deriving enforcer state from flow-trace: {e}")

        return {
            'session_started': False,
            'standards_loaded': False,
            'prompt_generated': False,
            'tasks_created': False,
            'plan_mode_decided': False,
            'model_selected': False,
            'skills_agents_checked': False,
            'context_checked': False,
            'total_violations': 0,
            'last_violation': None,
            'session_start_time': None
        }

    def parse_policy_log(self, hours=24):
        """
        Parse recent policy executions.
        Primary source: flow-trace.json pipeline steps (always available).
        Fallback: policy-hits.log (if it exists with matching format).
        """
        executions = []
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Step name to policy category mapping
        step_to_category = {
            'LEVEL_MINUS_1': 'Auto-Fix Enforcement',
            'LEVEL_1_CONTEXT': 'Context Management',
            'LEVEL_1_SESSION': 'Session Management',
            'LEVEL_2_STANDARDS': 'Standards System',
            'LEVEL_3_STEP_3_0': 'Prompt Generation',
            'LEVEL_3_STEP_3_1': 'Task Breakdown',
            'LEVEL_3_STEP_3_2': 'Plan Mode',
            'LEVEL_3_STEP_3_3': 'Context Check',
            'LEVEL_3_STEP_3_4': 'Model Selection',
            'LEVEL_3_STEP_3_5': 'Skill/Agent',
            'LEVEL_3_STEP_3_6': 'Tool Optimization',
            'LEVEL_3_STEP_3_7': 'Failure Prevention',
            'LEVEL_3_STEP_3_8': 'Parallel Analysis',
            'LEVEL_3_STEP_3_9': 'Task Execution',
            'LEVEL_3_STEP_3_10': 'Session Save',
            'LEVEL_3_STEP_3_11': 'Git Auto-Commit',
            'LEVEL_3_STEP_3_12': 'Logging'
        }

        # Parse flow-trace.json files (primary source)
        sessions_dir = self.memory_dir / 'logs' / 'sessions'
        if sessions_dir.exists():
            try:
                trace_files = sorted(
                    sessions_dir.glob('*/flow-trace.json'),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )[:200]

                for tf in trace_files:
                    try:
                        data = json.loads(tf.read_text(encoding='utf-8', errors='ignore'))
                        meta = data.get('meta', {})
                        flow_start = meta.get('flow_start', '')

                        if not flow_start:
                            continue

                        try:
                            timestamp = datetime.fromisoformat(flow_start[:19])
                        except ValueError:
                            continue

                        if timestamp < cutoff_time:
                            continue

                        fd = data.get('final_decision', {})
                        session_id = fd.get('session_id', meta.get('session_id', ''))

                        for step in data.get('pipeline', []):
                            step_name = step.get('step', '')
                            category = step_to_category.get(step_name, 'Other')
                            duration_ms = step.get('duration_ms', 0)
                            status = 'SUCCESS' if duration_ms >= 0 else 'SKIPPED'

                            executions.append({
                                'timestamp': step.get('timestamp', flow_start)[:19],
                                'policy_name': step.get('name', step_name),
                                'policy_category': category,
                                'status': status,
                                'message': step.get('decision', f'{step_name} executed in {duration_ms}ms'),
                                'duration_ms': duration_ms,
                                'session_id': session_id
                            })

                    except Exception:
                        continue

            except Exception as e:
                print(f"Error parsing flow-trace files: {e}")

        # Also try policy-hits.log as supplementary source
        try:
            if self.policy_log.exists():
                with open(self.policy_log, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            if line.startswith('['):
                                timestamp_end = line.index(']')
                                timestamp_str = line[1:timestamp_end]
                                timestamp = datetime.fromisoformat(timestamp_str)
                                if timestamp < cutoff_time:
                                    continue
                                rest = line[timestamp_end + 1:].strip()
                                parts = rest.split('|')
                                if len(parts) >= 3:
                                    policy_name = parts[0].strip()
                                    status = parts[1].strip()
                                    message = parts[2].strip()
                                    executions.append({
                                        'timestamp': timestamp.isoformat(),
                                        'policy_name': policy_name,
                                        'policy_category': self._categorize_policy(policy_name),
                                        'status': status,
                                        'message': message
                                    })
                        except (ValueError, IndexError):
                            continue
        except Exception as e:
            print(f"Error parsing policy log: {e}")

        return executions

    def _categorize_policy(self, policy_name):
        """Categorize policy by type"""
        policy_name_lower = policy_name.lower()

        if 'prompt' in policy_name_lower or 'generation' in policy_name_lower:
            return 'Prompt Generation'
        elif 'task' in policy_name_lower or 'breakdown' in policy_name_lower:
            return 'Task Breakdown'
        elif 'plan' in policy_name_lower or 'mode' in policy_name_lower:
            return 'Plan Mode'
        elif 'model' in policy_name_lower or 'selection' in policy_name_lower:
            return 'Model Selection'
        elif 'skill' in policy_name_lower or 'agent' in policy_name_lower:
            return 'Skill/Agent'
        elif 'tool' in policy_name_lower or 'optimization' in policy_name_lower:
            return 'Tool Optimization'
        elif 'context' in policy_name_lower:
            return 'Context Management'
        elif 'commit' in policy_name_lower or 'git' in policy_name_lower:
            return 'Git Auto-Commit'
        elif 'session' in policy_name_lower:
            return 'Session Management'
        elif 'daemon' in policy_name_lower:
            return 'Daemon'
        else:
            return 'Other'

    def get_execution_stats(self, hours=24):
        """Get execution statistics for the last N hours"""
        executions = self.parse_policy_log(hours)

        # Count by category
        category_counts = defaultdict(int)
        status_counts = defaultdict(int)

        for exec_data in executions:
            category_counts[exec_data['policy_category']] += 1
            status_counts[exec_data['status']] += 1

        # Calculate execution rate (per hour)
        total_executions = len(executions)
        execution_rate = total_executions / hours if hours > 0 else 0

        # Get recent executions (last 10)
        recent_executions = sorted(
            executions,
            key=lambda x: x['timestamp'],
            reverse=True
        )[:10]

        return {
            'total_executions': total_executions,
            'execution_rate_per_hour': round(execution_rate, 2),
            'by_category': dict(category_counts),
            'by_status': dict(status_counts),
            'recent_executions': recent_executions,
            'timeframe_hours': hours
        }

    def get_execution_timeline(self, hours=24):
        """Get execution timeline data for charting"""
        executions = self.parse_policy_log(hours)

        # Group by hour
        hourly_counts = defaultdict(int)

        for exec_data in executions:
            timestamp = datetime.fromisoformat(exec_data['timestamp'])
            hour_key = timestamp.strftime('%Y-%m-%d %H:00')
            hourly_counts[hour_key] += 1

        # Sort by time
        sorted_hours = sorted(hourly_counts.keys())

        return {
            'labels': sorted_hours,
            'data': [hourly_counts[hour] for hour in sorted_hours]
        }

    def get_policy_health(self):
        """Get overall policy health status"""
        enforcer_state = self.get_enforcer_state()
        recent_stats = self.get_execution_stats(hours=1)

        # Calculate health score (0-100)
        health_score = 0

        # Session started (20 points)
        if enforcer_state['session_started']:
            health_score += 20

        # Recent executions (30 points)
        if recent_stats['total_executions'] > 0:
            health_score += min(30, recent_stats['total_executions'] * 3)

        # All steps completed (50 points)
        completed_steps = sum([
            enforcer_state['standards_loaded'],
            enforcer_state['prompt_generated'],
            enforcer_state['tasks_created'],
            enforcer_state['plan_mode_decided'],
            enforcer_state['model_selected'],
            enforcer_state['skills_agents_checked'],
            enforcer_state['context_checked']
        ])
        health_score += int((completed_steps / 7) * 50)

        # Determine status
        if health_score >= 80:
            status = 'EXCELLENT'
            status_class = 'success'
        elif health_score >= 60:
            status = 'GOOD'
            status_class = 'info'
        elif health_score >= 40:
            status = 'FAIR'
            status_class = 'warning'
        else:
            status = 'POOR'
            status_class = 'danger'

        return {
            'health_score': health_score,
            'status': status,
            'status_class': status_class,
            'enforcer_state': enforcer_state,
            'recent_activity': recent_stats['total_executions'],
            'violations': enforcer_state['total_violations']
        }

    def get_enforcement_status(self):
        """Get detailed enforcement status for all steps"""
        enforcer_state = self.get_enforcer_state()

        steps = [
            {
                'id': 'session',
                'name': 'Session Start',
                'layer': 'SYNC',
                'completed': enforcer_state['session_started'],
                'required': True
            },
            {
                'id': 'context',
                'name': 'Context Check',
                'layer': 'SYNC',
                'completed': enforcer_state['context_checked'],
                'required': True
            },
            {
                'id': 'standards',
                'name': 'Standards Loaded',
                'layer': 'STANDARDS',
                'completed': enforcer_state['standards_loaded'],
                'required': True
            },
            {
                'id': 'prompt',
                'name': 'Prompt Generation',
                'layer': 'EXECUTION',
                'completed': enforcer_state['prompt_generated'],
                'required': True
            },
            {
                'id': 'tasks',
                'name': 'Task Breakdown',
                'layer': 'EXECUTION',
                'completed': enforcer_state['tasks_created'],
                'required': True
            },
            {
                'id': 'plan',
                'name': 'Plan Mode Decision',
                'layer': 'EXECUTION',
                'completed': enforcer_state['plan_mode_decided'],
                'required': True
            },
            {
                'id': 'model',
                'name': 'Model Selection',
                'layer': 'EXECUTION',
                'completed': enforcer_state['model_selected'],
                'required': True
            },
            {
                'id': 'skills',
                'name': 'Skills/Agents Check',
                'layer': 'EXECUTION',
                'completed': enforcer_state['skills_agents_checked'],
                'required': True
            }
        ]

        completed_count = sum(1 for step in steps if step['completed'])
        total_count = len(steps)
        completion_percentage = int((completed_count / total_count) * 100)

        return {
            'steps': steps,
            'completed_count': completed_count,
            'total_count': total_count,
            'completion_percentage': completion_percentage
        }


# Standalone test
if __name__ == '__main__':
    tracker = PolicyExecutionTracker()

    print("=" * 70)
    print("POLICY EXECUTION TRACKER - TEST")
    print("=" * 70)
    print()

    # Test enforcer state
    print("[1] Enforcer State:")
    state = tracker.get_enforcer_state()
    for key, value in state.items():
        print(f"  {key}: {value}")
    print()

    # Test execution stats
    print("[2] Execution Stats (Last 24h):")
    stats = tracker.get_execution_stats(hours=24)
    print(f"  Total: {stats['total_executions']}")
    print(f"  Rate: {stats['execution_rate_per_hour']}/hour")
    print(f"  By Category: {stats['by_category']}")
    print()

    # Test health
    print("[3] Policy Health:")
    health = tracker.get_policy_health()
    print(f"  Score: {health['health_score']}/100")
    print(f"  Status: {health['status']}")
    print(f"  Recent Activity: {health['recent_activity']}")
    print()

    # Test enforcement status
    print("[4] Enforcement Status:")
    status = tracker.get_enforcement_status()
    print(f"  Progress: {status['completed_count']}/{status['total_count']} ({status['completion_percentage']}%)")
    for step in status['steps']:
        check = '[CHECK]' if step['completed'] else '[CROSS]'
        print(f"  {check} {step['name']} ({step['layer']})")
