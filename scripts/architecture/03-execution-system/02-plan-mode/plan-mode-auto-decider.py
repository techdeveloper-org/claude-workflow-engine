#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Plan Mode Auto-Decider (Phase 4)
Automatically decides when to enter plan mode - no user confirmation needed

PHASE 4 AUTOMATION - SMART PLAN MODE DECISION
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Fix encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Import blocking-policy-enforcer using importlib
try:
    import importlib.util

    MEMORY_PATH = Path.home() / '.claude' / 'memory'
    spec = importlib.util.spec_from_file_location(
        "blocking_policy_enforcer",
        MEMORY_PATH / 'blocking-policy-enforcer.py'
    )
    blocking_policy_enforcer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(blocking_policy_enforcer)

    DIRECT_IMPORT_AVAILABLE = True
except Exception as e:
    print(f"Warning: Could not import blocking-policy-enforcer: {e}", file=sys.stderr)
    import subprocess
    DIRECT_IMPORT_AVAILABLE = False


class PlanModeAutoDecider:
    """
    Automatically decides when plan mode is needed
    Thresholds:
    - Score 0-9: NO plan mode (proceed directly)
    - Score 10-19: AUTO ENTER plan mode
    - Score 20+: MANDATORY plan mode
    """

    def __init__(self):
        self.memory_path = Path.home() / '.claude' / 'memory'
        self.logs_path = self.memory_path / 'logs'
        self.plan_log = self.logs_path / 'plan-mode-decisions.log'

    def _llm_risk_score(self, task_info):
        """Use local LLM to evaluate task risk contextually.

        Calls Ollama to analyze the task description and return a risk
        score (0-30) based on actual understanding of the task.

        Args:
            task_info: Dict with task metadata (user_message, service_count, etc.)

        Returns:
            int or None: Risk score from LLM (0-30), or None if unavailable.
        """
        try:
            from urllib import request as _urllib_request
            import json as _json

            user_msg = task_info.get('user_message', '')
            if not user_msg:
                return None

            prompt = (
                "Evaluate the RISK SCORE (0-30) for this coding task. "
                "Return ONLY JSON: {\"risk_score\": number, \"reason\": \"string\"}\n\n"
                "Scoring guide:\n"
                "- 0-5: Simple/safe (read files, small edits, docs, config)\n"
                "- 6-12: Moderate (single feature, one service, standard patterns)\n"
                "- 13-20: High (multi-service, database schema, auth/security)\n"
                "- 21-30: Critical (architecture redesign, data migration, breaking changes)\n\n"
                "Risk factors: multi-service impact, database changes, security-critical, "
                "architecture changes, novel problems, many files affected\n\n"
                f"Task: {user_msg[:300]}\n"
            )
            if task_info.get('service_count', 0) > 0:
                prompt += f"Services affected: {task_info['service_count']}\n"
            if task_info.get('file_count', 0) > 0:
                prompt += f"Files affected: {task_info['file_count']}\n"

            # Auto-detect Ollama model
            model = 'qwen2.5:7b'
            try:
                req = _urllib_request.Request('http://127.0.0.1:11434/api/tags')
                with _urllib_request.urlopen(req, timeout=2) as resp:
                    data = _json.loads(resp.read().decode('utf-8'))
                    installed = [m['name'] for m in data.get('models', [])]
                    for preferred in ['qwen3:4b', 'qwen2.5:7b', 'qwen2.5:3b', 'granite4:3b']:
                        if preferred in installed:
                            model = preferred
                            break
            except Exception:
                pass

            payload = _json.dumps({
                'model': model,
                'messages': [
                    {'role': 'system', 'content': 'You evaluate coding task risk. Return ONLY valid JSON.'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 100,
                'temperature': 0.1,
                'response_format': {'type': 'json_object'},
            }).encode('utf-8')

            req = _urllib_request.Request(
                'http://127.0.0.1:11434/v1/chat/completions',
                data=payload,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )

            with _urllib_request.urlopen(req, timeout=30) as resp:
                result = _json.loads(resp.read().decode('utf-8'))
                content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                parsed = _json.loads(content)
                risk = parsed.get('risk_score', parsed.get('score', None))
                if risk is not None:
                    return max(0, min(30, int(risk)))
        except Exception:
            pass
        return None

    def calculate_risk_score(self, task_info):
        """
        Calculate risk score (0-30)
        Higher = more risky = needs plan mode

        Uses LLM classification first for contextual understanding,
        falls back to hardcoded heuristics if LLM unavailable.
        """
        # Try LLM-based risk evaluation first
        llm_score = self._llm_risk_score(task_info)
        if llm_score is not None:
            return llm_score

        # Fallback: hardcoded heuristics
        score = 0

        # Multi-service impact
        service_count = task_info.get('service_count', 0)
        if service_count > 3:
            score += 10
        elif service_count > 1:
            score += 5

        # Database changes
        if task_info.get('database_changes', False):
            score += 7

        # Security critical
        if task_info.get('security_critical', False):
            score += 8

        # No similar examples
        if task_info.get('no_examples', False):
            score += 6

        # Architecture changes
        if task_info.get('architecture_change', False):
            score += 10

        # Novel problem
        if task_info.get('novel_problem', False):
            score += 8

        # New framework/technology
        if task_info.get('new_technology', False):
            score += 5

        # Integration complexity
        if task_info.get('complex_integration', False):
            score += 6

        # File count
        file_count = task_info.get('file_count', 0)
        if file_count > 15:
            score += 7
        elif file_count > 10:
            score += 4
        elif file_count > 5:
            score += 2

        return min(score, 30)

    def decide(self, complexity_score, risk_score):
        """
        Make plan mode decision

        Rules:
        - Total < 10: NO plan mode
        - Total 10-19: YES plan mode (auto-enter)
        - Total 20+: MANDATORY plan mode
        """
        total_score = complexity_score + risk_score

        if total_score < 10:
            return {
                'decision': 'NO',
                'reason': 'Simple task - proceed directly without plan mode',
                'total_score': total_score,
                'auto_enter': False,
                'mandatory': False
            }
        elif total_score < 20:
            return {
                'decision': 'YES',
                'reason': 'Moderate complexity/risk - plan mode recommended',
                'total_score': total_score,
                'auto_enter': True,
                'mandatory': False
            }
        else:
            return {
                'decision': 'MANDATORY',
                'reason': 'High complexity/risk - plan mode required',
                'total_score': total_score,
                'auto_enter': True,
                'mandatory': True
            }

    def get_plan_mode_benefits(self, decision):
        """Get benefits of using plan mode for this task"""
        benefits = []

        if decision['total_score'] >= 20:
            benefits = [
                'Prevent costly mistakes in complex implementation',
                'Validate architecture decisions upfront',
                'Identify dependencies and conflicts early',
                'Get user approval before major changes',
                'Reduce rework and debugging time'
            ]
        elif decision['total_score'] >= 10:
            benefits = [
                'Better understand scope and approach',
                'Identify potential issues early',
                'Get user alignment on strategy',
                'More organized implementation'
            ]
        else:
            benefits = [
                'Not needed - task is straightforward'
            ]

        return benefits

    def auto_decide(self, task_info):
        """
        Main entry point - automatic decision
        Returns decision with full context
        """
        # Get complexity from task info
        complexity_score = task_info.get('complexity_score', 0)

        # Calculate risk
        risk_score = self.calculate_risk_score(task_info)

        # Make decision
        decision = self.decide(complexity_score, risk_score)

        # Get benefits
        benefits = self.get_plan_mode_benefits(decision)

        result = {
            'complexity_score': complexity_score,
            'risk_score': risk_score,
            'decision': decision['decision'],
            'reason': decision['reason'],
            'total_score': decision['total_score'],
            'auto_enter': decision['auto_enter'],
            'mandatory': decision['mandatory'],
            'benefits': benefits,
            'timestamp': datetime.now().isoformat()
        }

        # Log decision
        self.log_decision(result)

        # Mark as decided in blocking enforcer
        if decision['decision'] != 'NO':
            try:
                if DIRECT_IMPORT_AVAILABLE:
                    # Direct method call
                    enforcer = blocking_policy_enforcer.BlockingPolicyEnforcer()
                    enforcer.mark_complete('plan_mode_decided')
                else:
                    # Fallback to subprocess
                    import subprocess
                    subprocess.run(
                        ['python', str(self.memory_path / 'blocking-policy-enforcer.py'),
                         '--mark-plan-mode-decided'],
                        capture_output=True,
                        timeout=5,
                        creationflags=0x08000000 if sys.platform == 'win32' else 0
                    )
            except:
                pass

        return result

    def log_decision(self, result):
        """Log decision"""
        self.logs_path.mkdir(parents=True, exist_ok=True)

        log_entry = {
            'timestamp': result['timestamp'],
            'decision': result['decision'],
            'total_score': result['total_score'],
            'auto_enter': result['auto_enter']
        }

        with open(self.plan_log, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')

    def print_result(self, result):
        """Print formatted result"""
        print(f"\n{'='*70}")
        print(f"[TARGET] Plan Mode Auto-Decider (Phase 4)")
        print(f"{'='*70}\n")

        print(f"[CHART] Scores:")
        print(f"   Complexity: {result['complexity_score']}/30")
        print(f"   Risk: {result['risk_score']}/30")
        print(f"   Total: {result['total_score']}/60")

        print(f"\n[OK] Decision: {result['decision']}")
        print(f"   Reason: {result['reason']}")

        if result['auto_enter']:
            print(f"\n🚀 Action: AUTO-ENTERING PLAN MODE")
            if result['mandatory']:
                print(f"   Status: MANDATORY (no skip option)")
            else:
                print(f"   Status: RECOMMENDED (can skip if needed)")

        print(f"\n[BULB] Benefits:")
        for benefit in result['benefits']:
            print(f"   - {benefit}")

        print(f"\n{'='*70}\n")


def main():
    """CLI usage"""
    import argparse

    parser = argparse.ArgumentParser(description='Plan Mode Auto-Decider (Phase 4)')
    parser.add_argument('--task-info', required=True, help='Task information (JSON)')

    if len(sys.argv) < 2:
        sys.exit(0)
    args = parser.parse_args()

    try:
        task_info = json.loads(args.task_info)
    except json.JSONDecodeError:
        print(f"[ERROR] Invalid JSON task info: {args.task_info}")
        sys.exit(1)

    decider = PlanModeAutoDecider()
    result = decider.auto_decide(task_info)

    decider.print_result(result)

    # Exit with code based on decision
    # 0 = NO plan mode
    # 1 = YES plan mode (recommended)
    # 2 = MANDATORY plan mode
    if result['decision'] == 'NO':
        sys.exit(0)
    elif result['decision'] == 'YES':
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == '__main__':
    main()
