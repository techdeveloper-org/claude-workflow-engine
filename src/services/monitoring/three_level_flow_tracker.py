"""
Three Level Flow Tracker
Parses and tracks executions of the 3-level architecture flow from session logs.

Reads from:
  ~/.claude/memory/logs/sessions/SESSION-xxx/
    00-session-start.log
    01-level-minus-1.log
    02-level-1-sync.log
    03-level-2-standards.log
    04-level-3-execution.log
    flow-trace.json          (NEW: from 3-level-flow.py v3.0.0+, richer data)
  ~/.claude/memory/logs/auto-enforcement.log

v3.0.0 enhancements (from flow-trace.json):
  - tech_stack: detected from project files (flask, spring-boot, angular, etc.)
  - agent_type: 'agent' or 'skill'
  - supplementary_skills: list of extra skills alongside the agent
  - execution_mode: 'parallel' or 'sequential'
  - model_reason: why that model was selected
  - flow_version: script version that generated the trace
  - full pipeline A-to-Z traceability via /api/3level-flow/pipeline/<session_id>
"""

import re
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.path_resolver import get_data_dir


class ThreeLevelFlowTracker:
    """Track and parse 3-level architecture flow executions from session logs"""

    def __init__(self):
        self.memory_dir = get_data_dir()
        self.sessions_dir = self.memory_dir / 'logs' / 'sessions'
        self.policy_hits_log = self.memory_dir / 'logs' / 'policy-hits.log'

    # -------------------------------------------------------------------------
    # Session Discovery
    # -------------------------------------------------------------------------

    def get_session_dirs(self, limit=50):
        """List session directories sorted by most recent"""
        if not self.sessions_dir.exists():
            return []

        dirs = [d for d in self.sessions_dir.iterdir() if d.is_dir()]
        dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        return dirs[:limit]

    # -------------------------------------------------------------------------
    # Single Session Parsing
    # -------------------------------------------------------------------------

    def parse_session(self, session_dir):
        """Parse a single session directory and return structured data"""
        session_id = session_dir.name
        session_data = {
            'session_id': session_id,
            'started': None,
            'user_prompt': None,
            'mode': 'summary',
            'level_minus_1': {'status': 'unknown'},
            'level_1': {'context_pct': None, 'session_id': None},
            'level_2': {
                'standards': None, 'rules': None, 'status': 'unknown',
                'common_standards': None, 'common_rules': None,
                'microservices_standards': None, 'microservices_rules': None,
                'microservices_active': None,
            },
            'level_3': {
                'complexity': None,
                'task_type': None,
                'tasks': None,
                'plan_required': False,
                'context_pct': None,
                'model': None,
                'skill_agent': None,
                'duration': None,
                'status': 'unknown',
                'steps': {}
            },
            'overall_status': 'unknown',
            'duration': None,
            # New fields from 3-level-flow.py v3.0.0+ (flow-trace.json)
            'tech_stack': [],
            'agent_type': None,
            'supplementary_skills': [],
            'execution_mode': None,
            'model_reason': None,
            'flow_version': None,
            'has_trace_json': False,
        }

        try:
            self._parse_session_start(session_dir, session_data)
            self._parse_level_minus_1(session_dir, session_data)
            self._parse_level_1(session_dir, session_data)
            self._parse_level_2(session_dir, session_data)
            self._parse_level_3(session_dir, session_data)
            # Enrich with flow-trace.json if available (3-level-flow.py v3.0.0+)
            self._parse_flow_trace_json(session_dir, session_data)

            # Derive overall status
            l1 = session_data['level_minus_1']['status']
            l3 = session_data['level_3']['status']
            if l1 in ('PASS', 'SUCCESS') and l3 in ('OK', 'ok'):
                session_data['overall_status'] = 'success'
            elif l1 == 'FAIL':
                session_data['overall_status'] = 'failed'
            elif l3 == 'FAIL':
                session_data['overall_status'] = 'failed'
            else:
                session_data['overall_status'] = 'partial'

        except Exception as e:
            session_data['parse_error'] = str(e)

        return session_data

    def _parse_session_start(self, session_dir, data):
        """Parse 00-session-start.log"""
        log_file = session_dir / '00-session-start.log'
        if not log_file.exists():
            return
        content = log_file.read_text(encoding='utf-8', errors='ignore')

        # Session ID
        m = re.search(r'Session ID:\s+(\S+)', content)
        if m:
            data['session_id'] = m.group(1)

        # Started timestamp
        m = re.search(r'Started:\s+(\S+)', content)
        if m:
            try:
                data['started'] = datetime.fromisoformat(m.group(1)).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                data['started'] = m.group(1)

        # Mode
        m = re.search(r'Mode:\s+(\S+)', content)
        if m:
            data['mode'] = m.group(1)

        # User prompt
        m = re.search(r'User Prompt:\s+(.+)', content)
        if m:
            data['user_prompt'] = m.group(1).strip()

    def _parse_level_minus_1(self, session_dir, data):
        """Parse 01-level-minus-1.log"""
        log_file = session_dir / '01-level-minus-1.log'
        if not log_file.exists():
            return
        content = log_file.read_text(encoding='utf-8', errors='ignore')

        checks = {}
        for check_num in range(1, 8):
            m = re.search(rf'\[{check_num}/\d+\]\s+(.+?):\s+(\S+)', content)
            if m:
                checks[m.group(1).strip()] = m.group(2).strip()

        # Determine pass/fail - support both SUCCESS and PASS wording
        status = 'PASS'
        content_upper = content.upper()
        if 'STATUS: FAIL' in content_upper or ('FAIL' in content_upper and 'SUCCESS' not in content_upper):
            status = 'FAIL'
        elif any(kw in content_upper for kw in ['STATUS: SUCCESS', 'STATUS: PASS', '[OK]', 'ALL SYSTEMS OPERATIONAL']):
            status = 'PASS'

        data['level_minus_1'] = {
            'status': status,
            'checks': checks,
            'message': 'All systems operational' if status == 'PASS' else 'System failures detected'
        }

    def _parse_level_1(self, session_dir, data):
        """Parse 02-level-1-sync.log"""
        log_file = session_dir / '02-level-1-sync.log'
        if not log_file.exists():
            return
        content = log_file.read_text(encoding='utf-8', errors='ignore')

        ctx = None
        m = re.search(r'Current Usage:\s+([\d.]+)%', content)
        if m:
            ctx = float(m.group(1))

        sid = None
        m = re.search(r'Session ID:\s+(\S+)', content)
        if m:
            sid = m.group(1)

        ctx_status = 'GREEN'
        if ctx is not None:
            if ctx >= 85:
                ctx_status = 'RED'
            elif ctx >= 70:
                ctx_status = 'YELLOW'

        data['level_1'] = {
            'context_pct': ctx,
            'context_status': ctx_status,
            'session_id': sid
        }

    def _parse_level_2(self, session_dir, data):
        """Parse 03-level-2-standards.log - supports both old single-block and new 2.1/2.2 format"""
        log_file = session_dir / '03-level-2-standards.log'
        if not log_file.exists():
            return
        content = log_file.read_text(encoding='utf-8', errors='ignore')

        standards = None
        rules = None
        common_standards = None
        common_rules = None
        micro_standards = None
        micro_rules = None
        micro_active = None

        # New format: Level 2.1 / 2.2 sub-level output
        m = re.search(r'Common Standards:\s+(\d+)', content)
        if m:
            common_standards = int(m.group(1))
        m = re.search(r'Common Rules Loaded:\s+(\d+)', content)
        if m:
            common_rules = int(m.group(1))
        m = re.search(r'Microservices Standards:\s+(\d+)', content)
        if m:
            micro_standards = int(m.group(1))
            micro_active = True
        m = re.search(r'Microservices Rules Loaded:\s+(\d+)', content)
        if m:
            micro_rules = int(m.group(1))
        if 'SKIPPED' in content and 'Microservices' in content:
            micro_active = False

        # Old format fallback
        m = re.search(r'Total Standards:\s+(\d+)', content)
        if m:
            standards = int(m.group(1))
        m_r = re.search(r'(?<!Common |Microservices )Rules Loaded:\s+(\d+)', content)
        if not standards:
            m2 = re.search(r'Standards Loaded:\s+(\d+)', content)
            if m2:
                standards = int(m2.group(1))
        if not rules:
            m3 = re.search(r'Rules Loaded:\s+(\d+)', content)
            if m3:
                rules = int(m3.group(1))

        # Compute totals from sub-levels if available
        if common_standards is not None:
            standards = (common_standards or 0) + (micro_standards or 0)
            rules = (common_rules or 0) + (micro_rules or 0)

        data['level_2'] = {
            'standards': standards,
            'rules': rules,
            'status': 'OK' if standards is not None else 'unknown',
            'common_standards': common_standards,
            'common_rules': common_rules,
            'microservices_standards': micro_standards,
            'microservices_rules': micro_rules,
            'microservices_active': micro_active,
        }

    def _parse_level_3(self, session_dir, data):
        """Parse 04-level-3-execution.log"""
        log_file = session_dir / '04-level-3-execution.log'
        if not log_file.exists():
            return
        content = log_file.read_text(encoding='utf-8', errors='ignore')

        steps = {}

        # [3.0] Prompt Generation: Complexity=3, Type=Database
        m = re.search(r'\[3\.0\] Prompt Generation:\s+Complexity=(\d+),\s+Type=(\S+)', content)
        if m:
            steps['3.0'] = {'name': 'Prompt Generation', 'complexity': int(m.group(1)), 'type': m.group(2)}
            data['level_3']['complexity'] = int(m.group(1))
            data['level_3']['task_type'] = m.group(2)

        # [3.1] Task Breakdown: 2 tasks
        m = re.search(r'\[3\.1\] Task Breakdown:\s+(\d+)\s+tasks?', content)
        if m:
            steps['3.1'] = {'name': 'Task Breakdown', 'tasks': int(m.group(1))}
            data['level_3']['tasks'] = int(m.group(1))

        # [3.2] Plan Mode: NOT required (complexity 3)
        m = re.search(r'\[3\.2\] Plan Mode:\s+(.+?)(?:\n|$)', content)
        if m:
            plan_text = m.group(1).strip()
            steps['3.2'] = {'name': 'Plan Mode', 'value': plan_text}
            data['level_3']['plan_required'] = 'required' in plan_text.lower() and 'NOT' not in plan_text

        # [3.3] Context Check: 80.0%
        m = re.search(r'\[3\.3\] Context Check:\s+([\d.]+)%', content)
        if m:
            steps['3.3'] = {'name': 'Context Check', 'pct': float(m.group(1))}
            data['level_3']['context_pct'] = float(m.group(1))

        # [3.4] Model Selection: HAIKU
        m = re.search(r'\[3\.4\] Model Selection:\s+(\S+)', content)
        if m:
            steps['3.4'] = {'name': 'Model Selection', 'model': m.group(1)}
            data['level_3']['model'] = m.group(1)

        # [3.5] Skill/Agent: xxx
        m = re.search(r'\[3\.5\] Skill/Agent:\s+(.+?)(?:\n|$)', content)
        if m:
            steps['3.5'] = {'name': 'Skill/Agent', 'value': m.group(1).strip()}
            data['level_3']['skill_agent'] = m.group(1).strip()

        # [3.6] to [3.12] - check presence
        for step_num, step_name in [
            ('3.6', 'Tool Optimization'),
            ('3.7', 'Failure Prevention'),
            ('3.8', 'Parallel Analysis'),
            ('3.9', 'Execute Tasks'),
            ('3.10', 'Session Save'),
            ('3.11', 'Auto-Commit'),
            ('3.12', 'Logging'),
        ]:
            m = re.search(rf'\[{re.escape(step_num)}\]\s+.+?:\s+(.+?)(?:\n|$)', content)
            if m:
                steps[step_num] = {'name': step_name, 'value': m.group(1).strip()}

        # Duration
        m = re.search(r'Duration:\s+([\d.]+)s', content)
        if m:
            data['level_3']['duration'] = float(m.group(1))
            data['duration'] = float(m.group(1))

        # Status
        if '[OK]' in content or 'Status: [OK]' in content:
            data['level_3']['status'] = 'OK'
        elif 'FAIL' in content:
            data['level_3']['status'] = 'FAIL'

        data['level_3']['steps'] = steps

    def _parse_flow_trace_json(self, session_dir, data):
        """
        Parse flow-trace.json for richer data from 3-level-flow.py v3.0.0+.
        Enriches session_data with tech_stack, agent_type, supplementary_skills,
        execution_mode, model_reason, flow_version.
        Falls back gracefully if file doesn't exist (older sessions).
        """
        trace_file = session_dir / 'flow-trace.json'
        if not trace_file.exists():
            return

        try:
            with open(trace_file, 'r', encoding='utf-8', errors='ignore') as f:
                trace = json.load(f)
        except Exception:
            return

        data['has_trace_json'] = True

        # Meta info
        meta = trace.get('meta', {})
        data['flow_version'] = meta.get('flow_version')

        # User input - more accurate prompt from hook stdin
        user_input = trace.get('user_input', {})
        if user_input.get('prompt'):
            data['user_prompt'] = user_input['prompt']

        # Final decision - compact summary of all policy decisions
        fd = trace.get('final_decision', {})
        if fd:
            data['tech_stack'] = fd.get('tech_stack') or []
            data['supplementary_skills'] = fd.get('supplementary_skills') or []
            data['execution_mode'] = fd.get('execution_mode')
            data['model_reason'] = fd.get('model_reason')

            # Enrich level_3 from final_decision (more accurate than .log regex)
            model_val = fd.get('model_selected') or fd.get('model')
            if model_val:
                data['level_3']['model'] = model_val
            if fd.get('complexity') is not None:
                data['level_3']['complexity'] = fd['complexity']
            if fd.get('task_type'):
                data['level_3']['task_type'] = fd['task_type']
            if fd.get('task_count') is not None:
                data['level_3']['tasks'] = fd['task_count']
            if fd.get('plan_mode') is not None:
                data['level_3']['plan_required'] = fd['plan_mode']
            if fd.get('context_pct') is not None:
                data['level_3']['context_pct'] = fd['context_pct']
            if fd.get('skill_or_agent'):
                data['level_3']['skill_agent'] = fd['skill_or_agent']

            # Enrich level_2 from final_decision (new 2.1/2.2 sub-level data)
            if fd.get('common_standards') is not None:
                data['level_2']['common_standards'] = fd['common_standards']
            if fd.get('common_rules') is not None:
                data['level_2']['common_rules'] = fd['common_rules']
            if fd.get('microservices_standards') is not None:
                data['level_2']['microservices_standards'] = fd['microservices_standards']
            if fd.get('microservices_rules') is not None:
                data['level_2']['microservices_rules'] = fd['microservices_rules']
            if fd.get('microservices_active') is not None:
                data['level_2']['microservices_active'] = fd['microservices_active']

        # Agent type and supplementary skills from pipeline step 3.5
        for step in trace.get('pipeline', []):
            if step.get('step') == 'LEVEL_3_STEP_3_5':
                step_out = step.get('policy_output', {})
                if step_out.get('selected_type'):
                    data['agent_type'] = step_out['selected_type']
                if step_out.get('supplementary_skills'):
                    data['supplementary_skills'] = step_out['supplementary_skills']
                break

        # Duration from meta (more accurate than .log regex)
        if meta.get('duration_seconds') and not data.get('duration'):
            data['duration'] = meta['duration_seconds']
            data['level_3']['duration'] = meta['duration_seconds']

        # Set started from flow_start if not already set from .log files
        if not data.get('started') and meta.get('flow_start'):
            try:
                data['started'] = datetime.fromisoformat(meta['flow_start'][:19]).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                data['started'] = meta['flow_start'][:19]

        # Level -1 and Level 3 status from pipeline (more accurate than .log parsing)
        level3_steps_seen = 0
        for step in trace.get('pipeline', []):
            step_name = step.get('step', '')

            if step_name == 'LEVEL_MINUS_1':
                step_out = step.get('policy_output', {})
                status = step_out.get('status', '')
                if status in ('SUCCESS', 'PASS'):
                    data['level_minus_1']['status'] = 'PASS'
                elif status in ('FAILED', 'FAIL'):
                    data['level_minus_1']['status'] = 'FAIL'
                checks = step_out.get('checks', {})
                if checks:
                    data['level_minus_1']['checks'] = checks

            if step_name.startswith('LEVEL_3_STEP_'):
                level3_steps_seen += 1

        # Level 3 status: OK if we saw at least 5 execution steps
        if level3_steps_seen >= 5:
            data['level_3']['status'] = 'OK'
        elif fd.get('proceed', False) and level3_steps_seen > 0:
            data['level_3']['status'] = 'OK'

    # -------------------------------------------------------------------------
    # Aggregated Stats
    # -------------------------------------------------------------------------

    def get_recent_sessions(self, limit=10):
        """Return list of recent parsed sessions"""
        session_dirs = self.get_session_dirs(limit=limit)
        sessions = []
        for session_dir in session_dirs:
            parsed = self.parse_session(session_dir)
            sessions.append(parsed)
        return sessions

    def get_flow_stats(self, limit=100):
        """Return aggregated statistics across recent sessions"""
        sessions = self.get_recent_sessions(limit=limit)

        total = len(sessions)
        successful = sum(1 for s in sessions if s['overall_status'] in ('success', 'partial'))
        failed = sum(1 for s in sessions if s['overall_status'] == 'failed')

        # Model distribution
        model_dist = defaultdict(int)
        for s in sessions:
            model = s['level_3'].get('model')
            if model:
                model_dist[model] += 1

        # Task type distribution
        type_dist = defaultdict(int)
        for s in sessions:
            task_type = s['level_3'].get('task_type')
            if task_type:
                type_dist[task_type] += 1

        # Complexity stats
        complexities = [s['level_3']['complexity'] for s in sessions if s['level_3'].get('complexity')]
        avg_complexity = round(sum(complexities) / len(complexities), 1) if complexities else 0

        # Plan mode rate
        plan_count = sum(1 for s in sessions if s['level_3'].get('plan_required'))
        plan_rate = round((plan_count / total) * 100, 1) if total > 0 else 0

        # Context usage from Level 1
        ctx_values = [s['level_1']['context_pct'] for s in sessions if s['level_1'].get('context_pct') is not None]
        avg_context = round(sum(ctx_values) / len(ctx_values), 1) if ctx_values else 0

        # Latest standards info from Level 2
        standards_info = {'standards': None, 'rules': None}
        for s in sessions:
            if s['level_2'].get('standards') is not None:
                standards_info = {
                    'standards': s['level_2']['standards'],
                    'rules': s['level_2']['rules']
                }
                break

        # Average duration
        durations = [s['duration'] for s in sessions if s.get('duration')]
        avg_duration = round(sum(durations) / len(durations), 1) if durations else 0

        # Tech stack distribution (from flow-trace.json, 3-level-flow.py v3.0.0+)
        tech_dist = defaultdict(int)
        for s in sessions:
            for tech in s.get('tech_stack', []):
                tech_dist[tech] += 1

        # Execution mode distribution (parallel vs sequential)
        exec_dist = defaultdict(int)
        for s in sessions:
            mode = s.get('execution_mode')
            if mode:
                exec_dist[mode] += 1

        # Agent type distribution (agent vs skill)
        agent_dist = defaultdict(int)
        for s in sessions:
            atype = s.get('agent_type')
            if atype:
                agent_dist[atype] += 1

        # Trace JSON availability (how many sessions have rich data)
        has_trace = sum(1 for s in sessions if s.get('has_trace_json'))

        return {
            'total_sessions': total,
            'successful': successful,
            'failed': failed,
            'partial': total - successful - failed,
            'success_rate': round((successful / total) * 100, 1) if total > 0 else 0,
            'model_distribution': dict(model_dist),
            'type_distribution': dict(type_dist),
            'avg_complexity': avg_complexity,
            'plan_mode_rate': plan_rate,
            'avg_context_usage': avg_context,
            'standards_info': standards_info,
            'avg_duration_seconds': avg_duration,
            # New fields from 3-level-flow.py v3.0.0+
            'tech_stack_distribution': dict(tech_dist),
            'execution_mode_distribution': dict(exec_dist),
            'agent_type_distribution': dict(agent_dist),
            'sessions_with_trace_json': has_trace,
        }

    def get_latest_execution(self):
        """
        Return the most recent session execution.
        Fast path: reads latest-flow-trace.json directly (written by 3-level-flow.py v3.0.0+).
        Falls back to scanning session dirs for older sessions.
        """
        # Fast path: latest-flow-trace.json is always the most recent run
        latest_trace = self.memory_dir / 'logs' / 'latest-flow-trace.json'
        if latest_trace.exists():
            try:
                with open(latest_trace, 'r', encoding='utf-8', errors='ignore') as f:
                    trace = json.load(f)
                session_id = trace.get('meta', {}).get('session_id', 'UNKNOWN')
                session_dir = self.sessions_dir / session_id
                if session_dir.exists():
                    return self.parse_session(session_dir)
                # Session dir missing - build from trace directly
                return self._build_session_from_trace(trace)
            except Exception:
                pass

        # Fallback: scan session dirs
        sessions = self.get_recent_sessions(limit=1)
        return sessions[0] if sessions else None

    def _build_session_from_trace(self, trace):
        """Build a session data dict directly from a flow-trace.json dict (no log files)"""
        meta = trace.get('meta', {})
        fd = trace.get('final_decision', {})
        user_input = trace.get('user_input', {})

        session_id = meta.get('session_id', 'UNKNOWN')
        data = {
            'session_id': session_id,
            'started': meta.get('flow_start'),
            'user_prompt': user_input.get('prompt'),
            'mode': meta.get('mode', 'summary'),
            'level_minus_1': {'status': 'PASS'},
            'level_1': {
                'context_pct': fd.get('context_pct'),
                'context_status': 'GREEN',
                'session_id': session_id
            },
            'level_2': {
                'standards': fd.get('standards_active'),
                'rules': fd.get('rules_active'),
                'status': 'OK',
                'common_standards': fd.get('common_standards'),
                'common_rules': fd.get('common_rules'),
                'microservices_standards': fd.get('microservices_standards'),
                'microservices_rules': fd.get('microservices_rules'),
                'microservices_active': fd.get('microservices_active'),
            },
            'level_3': {
                'complexity': fd.get('complexity'),
                'task_type': fd.get('task_type'),
                'tasks': fd.get('task_count'),
                'plan_required': fd.get('plan_mode', False),
                'context_pct': fd.get('context_pct'),
                'model': fd.get('model_selected'),
                'skill_agent': fd.get('skill_or_agent'),
                'duration': meta.get('duration_seconds'),
                'status': 'OK' if trace.get('status') == 'COMPLETED' else 'unknown',
                'steps': {}
            },
            'overall_status': 'success' if trace.get('status') == 'COMPLETED' else 'partial',
            'duration': meta.get('duration_seconds'),
            'tech_stack': fd.get('tech_stack') or [],
            'agent_type': None,
            'supplementary_skills': fd.get('supplementary_skills') or [],
            'execution_mode': fd.get('execution_mode'),
            'model_reason': fd.get('model_reason'),
            'flow_version': meta.get('flow_version'),
            'has_trace_json': True,
        }

        # Level -1 status from pipeline
        for step in trace.get('pipeline', []):
            if step.get('step') == 'LEVEL_MINUS_1':
                status = step.get('policy_output', {}).get('status', '')
                data['level_minus_1']['status'] = 'PASS' if status in ('SUCCESS', 'PASS') else 'FAIL'
                break

        # Agent type from pipeline step 3.5
        for step in trace.get('pipeline', []):
            if step.get('step') == 'LEVEL_3_STEP_3_5':
                step_out = step.get('policy_output', {})
                data['agent_type'] = step_out.get('selected_type')
                break

        return data

    def get_policy_hits_today(self, hours=24):
        """Count policy enforcement hits in the last N hours from policy-hits.log"""
        if not self.policy_hits_log.exists():
            return {'total': 0, 'success': 0, 'failed': 0}

        cutoff = datetime.now() - timedelta(hours=hours)
        total = success = failed = 0

        try:
            with open(self.policy_hits_log, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    m = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', line)
                    if m:
                        try:
                            ts = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
                            if ts >= cutoff:
                                total += 1
                                if 'FAIL' in line.upper() or 'ERROR' in line.upper():
                                    failed += 1
                                else:
                                    success += 1
                        except Exception:
                            pass
        except Exception:
            pass

        return {'total': total, 'success': success, 'failed': failed}
