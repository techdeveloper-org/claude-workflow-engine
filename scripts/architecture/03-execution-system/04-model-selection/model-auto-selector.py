#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Model Auto-Selector (Step 6)
Automatically selects the appropriate Claude model based on complexity and risk

PHASE 3 AUTOMATION - SMART MODEL SELECTION
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


class ModelAutoSelector:
    """
    Automatically selects Claude model based on:
    - Complexity score (from task breakdown)
    - Risk factors (security, multi-service, etc.)
    - Plan mode decision
    - Task type
    """

    def __init__(self):
        self.memory_path = Path.home() / '.claude' / 'memory'
        self.logs_path = self.memory_path / 'logs'
        self.model_log = self.logs_path / 'model-selection.log'

        # Model costs per million tokens (updated 2026-02-28)
        # Haiku 4.5 "The Executor": $1/$5, Sonnet 4.6 "The Workhorse": $3/$15, Opus 4.6 "The Strategist": $5/$25
        self.model_costs = {
            'haiku': {'input': 1.0, 'output': 5.0},
            'sonnet': {'input': 3.0, 'output': 15.0},
            'opus': {'input': 5.0, 'output': 25.0}
        }

        # Model metadata
        self.model_info = {
            'haiku': {'id': 'claude-haiku-4-5-20251001', 'nickname': 'The Executor', 'context': '200K'},
            'sonnet': {'id': 'claude-sonnet-4-6', 'nickname': 'The Workhorse', 'context': '200K (1M beta)'},
            'opus': {'id': 'claude-opus-4-6', 'nickname': 'The Strategist', 'context': '200K (1M beta)'}
        }

    def calculate_complexity_score(self, task_info):
        """
        Calculate complexity score from task information
        Returns: 0-30 scale
        """
        score = 0

        # Base complexity from task type
        task_type = task_info.get('task_type', '').lower()
        if task_type in ['create', 'implement', 'build']:
            score += 10
        elif task_type in ['fix', 'debug', 'refactor']:
            score += 7
        elif task_type in ['update', 'modify']:
            score += 5
        elif task_type in ['analyze', 'review']:
            score += 3

        # File count complexity
        file_count = task_info.get('file_count', 0)
        if file_count > 10:
            score += 8
        elif file_count > 5:
            score += 5
        elif file_count > 2:
            score += 3

        # Service count (microservices)
        service_count = task_info.get('service_count', 0)
        if service_count > 3:
            score += 7
        elif service_count > 1:
            score += 4

        # Database changes
        if task_info.get('database_changes', False):
            score += 5

        # Security critical
        if task_info.get('security_critical', False):
            score += 6

        # No existing examples
        if task_info.get('no_examples', False):
            score += 5

        return min(score, 30)  # Cap at 30

    def calculate_risk_factors(self, task_info):
        """
        Calculate risk factors that might require model upgrade
        Returns: list of risk factors
        """
        risks = []

        if task_info.get('security_critical', False):
            risks.append('security_critical')

        if task_info.get('multi_service', False):
            risks.append('multi_service')

        if task_info.get('database_changes', False):
            risks.append('database_changes')

        if task_info.get('no_examples', False):
            risks.append('no_examples')

        if task_info.get('architecture_change', False):
            risks.append('architecture_change')

        if task_info.get('novel_problem', False):
            risks.append('novel_problem')

        return risks

    def select_model(self, complexity_score, risks, plan_mode=False):
        """
        Select appropriate model based on complexity and risks

        Rules:
        - Plan mode → OPUS (mandatory)
        - Score 0-4 (SIMPLE) → HAIKU
        - Score 5-9 (MODERATE) → HAIKU or SONNET (risk-based)
        - Score 10-19 (COMPLEX) → SONNET
        - Score 20+ (VERY_COMPLEX) → SONNET or OPUS
        - Risk overrides → Upgrade model
        """
        # Rule 1: Plan mode always uses OPUS
        if plan_mode:
            return {
                'model': 'opus',
                'reason': 'Plan mode requires OPUS for comprehensive planning',
                'confidence': 'high'
            }

        # Rule 2: Simple tasks (0-4)
        if complexity_score <= 4:
            base_model = 'haiku'

            # Check for risk overrides
            critical_risks = ['security_critical', 'novel_problem']
            if any(risk in risks for risk in critical_risks):
                return {
                    'model': 'sonnet',
                    'reason': f'Upgraded from HAIKU to SONNET due to: {", ".join(risks)}',
                    'confidence': 'high'
                }

            return {
                'model': base_model,
                'reason': f'Simple task (score: {complexity_score})',
                'confidence': 'high'
            }

        # Rule 3: Moderate tasks (5-9)
        elif complexity_score <= 9:
            # Use HAIKU if no risks
            if not risks:
                return {
                    'model': 'haiku',
                    'reason': f'Moderate task without risks (score: {complexity_score})',
                    'confidence': 'medium'
                }

            # Upgrade to SONNET if risks present
            return {
                'model': 'sonnet',
                'reason': f'Moderate task with risks: {", ".join(risks)} (score: {complexity_score})',
                'confidence': 'high'
            }

        # Rule 4: Complex tasks (10-19)
        elif complexity_score <= 19:
            base_model = 'sonnet'

            # Check for OPUS-level risks
            opus_risks = ['architecture_change', 'novel_problem']
            if any(risk in risks for risk in opus_risks):
                return {
                    'model': 'opus',
                    'reason': f'Complex task with critical risks: {", ".join(risks)} (score: {complexity_score})',
                    'confidence': 'high'
                }

            return {
                'model': base_model,
                'reason': f'Complex task (score: {complexity_score})',
                'confidence': 'high'
            }

        # Rule 5: Very complex tasks (20+)
        else:
            # Default to SONNET, upgrade to OPUS for architecture/novel
            opus_risks = ['architecture_change', 'novel_problem']
            if any(risk in risks for risk in opus_risks):
                return {
                    'model': 'opus',
                    'reason': f'Very complex with critical risks: {", ".join(risks)} (score: {complexity_score})',
                    'confidence': 'high'
                }

            return {
                'model': 'sonnet',
                'reason': f'Very complex task (score: {complexity_score})',
                'confidence': 'medium'
            }

    def estimate_cost(self, model, estimated_tokens):
        """
        Estimate cost for selected model
        """
        input_cost = (estimated_tokens * self.model_costs[model]['input']) / 1_000_000
        output_cost = (estimated_tokens * self.model_costs[model]['output']) / 1_000_000
        total_cost = input_cost + output_cost

        return {
            'input_cost': round(input_cost, 4),
            'output_cost': round(output_cost, 4),
            'total_cost': round(total_cost, 4),
            'estimated_tokens': estimated_tokens
        }

    def suggest_alternatives(self, selected_model, complexity_score):
        """
        Suggest alternative models with trade-offs
        """
        alternatives = []

        if selected_model == 'sonnet':
            # Suggest HAIKU if borderline
            if complexity_score <= 10:
                alternatives.append({
                    'model': 'haiku',
                    'reason': 'Cheaper (~3x), fastest, near-frontier intelligence',
                    'cost_savings': '67%'
                })

            # Suggest OPUS if high complexity
            if complexity_score >= 15:
                alternatives.append({
                    'model': 'opus',
                    'reason': 'Highest intelligence, catches subtle edge cases',
                    'cost_increase': '~1.67x'
                })

        elif selected_model == 'haiku':
            alternatives.append({
                'model': 'sonnet',
                'reason': 'Stronger reasoning if task is harder than expected',
                'cost_increase': '~3x'
            })

        elif selected_model == 'opus':
            alternatives.append({
                'model': 'sonnet',
                'reason': 'May be sufficient for execution after planning',
                'cost_savings': '40%'
            })

        return alternatives

    def auto_select(self, task_info, estimated_tokens=10000, allow_override=True):
        """
        Main entry point - automatically select model

        Args:
            task_info: Dict with task information
            estimated_tokens: Estimated token usage
            allow_override: Allow user override

        Returns: Selection result
        """
        # Calculate complexity and risks
        complexity_score = self.calculate_complexity_score(task_info)
        risks = self.calculate_risk_factors(task_info)
        plan_mode = task_info.get('plan_mode', False)

        # Select model
        selection = self.select_model(complexity_score, risks, plan_mode)

        # Estimate cost
        cost = self.estimate_cost(selection['model'], estimated_tokens)

        # Suggest alternatives
        alternatives = self.suggest_alternatives(selection['model'], complexity_score)

        result = {
            'selected_model': selection['model'],
            'reason': selection['reason'],
            'confidence': selection['confidence'],
            'complexity_score': complexity_score,
            'risks': risks,
            'cost_estimate': cost,
            'alternatives': alternatives,
            'allow_override': allow_override,
            'timestamp': datetime.now().isoformat()
        }

        # Log selection
        self.log_selection(result)

        # Mark as selected in blocking enforcer
        try:
            if DIRECT_IMPORT_AVAILABLE:
                # Direct method call
                enforcer = blocking_policy_enforcer.BlockingPolicyEnforcer()
                enforcer.mark_complete('model_selected')
            else:
                # Fallback to subprocess
                import subprocess
                subprocess.run(
                    ['python', str(self.memory_path / 'blocking-policy-enforcer.py'),
                     '--mark-model-selected'],
                    capture_output=True,
                    timeout=5,
                    creationflags=0x08000000 if sys.platform == 'win32' else 0
                )
        except:
            pass

        return result

    def log_selection(self, result):
        """Log model selection"""
        self.logs_path.mkdir(parents=True, exist_ok=True)

        log_entry = {
            'timestamp': result['timestamp'],
            'model': result['selected_model'],
            'complexity': result['complexity_score'],
            'risks': result['risks'],
            'confidence': result['confidence']
        }

        with open(self.model_log, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')

    def print_result(self, result):
        """Print formatted result"""
        print(f"\n{'='*70}")
        print(f"🤖 Model Auto-Selector (Step 6)")
        print(f"{'='*70}\n")

        print(f"📊 Analysis:")
        print(f"   Complexity Score: {result['complexity_score']}/30")

        if result['risks']:
            print(f"   Risk Factors: {', '.join(result['risks'])}")
        else:
            print(f"   Risk Factors: None")

        print(f"\n✅ Selected Model: {result['selected_model'].upper()}")
        print(f"   Reason: {result['reason']}")
        print(f"   Confidence: {result['confidence'].upper()}")

        print(f"\n💰 Cost Estimate (for {result['cost_estimate']['estimated_tokens']:,} tokens):")
        print(f"   Input: ${result['cost_estimate']['input_cost']:.4f}")
        print(f"   Output: ${result['cost_estimate']['output_cost']:.4f}")
        print(f"   Total: ${result['cost_estimate']['total_cost']:.4f}")

        if result['alternatives']:
            print(f"\n💡 Alternatives:")
            for alt in result['alternatives']:
                print(f"   • {alt['model'].upper()}: {alt['reason']}")
                if 'cost_savings' in alt:
                    print(f"     Cost savings: {alt['cost_savings']}")
                if 'cost_increase' in alt:
                    print(f"     Cost increase: {alt['cost_increase']}")

        if result['allow_override']:
            print(f"\n⚠️  Override available if needed")

        print(f"\n{'='*70}\n")


def main():
    """CLI usage - simplified for LangGraph"""
    # Check for complexity argument (simple mode for LangGraph)
    if len(sys.argv) > 1 and sys.argv[1].startswith('--complexity='):
        # LangGraph simple mode: python model-auto-selector.py --complexity=7
        try:
            complexity = int(sys.argv[1].split('=')[1])
        except (ValueError, IndexError):
            complexity = 5

        # Get context percentage if provided
        context_pct = 50
        for arg in sys.argv[2:]:
            if arg.startswith('--context='):
                try:
                    context_pct = int(arg.split('=')[1])
                except (ValueError, IndexError):
                    pass

        # Select model based on complexity
        if complexity <= 3:
            selected_model = 'haiku'
            reason = f'Simple task (complexity {complexity}) - fast, efficient'
        elif complexity <= 7:
            selected_model = 'sonnet'
            reason = f'Medium task (complexity {complexity}) - balanced power and cost'
            # Upgrade if context is high
            if context_pct > 75:
                selected_model = 'opus'
                reason = f'Medium task (complexity {complexity}) with high context ({context_pct}%) - upgraded to opus'
        else:
            selected_model = 'opus'
            reason = f'Complex task (complexity {complexity}) - maximum capability needed'

        # Estimate token usage
        estimated_tokens = max(1000, complexity * 2000)

        # Calculate costs
        model_cost = {
            'haiku': {'input': 1.0, 'output': 5.0},
            'sonnet': {'input': 3.0, 'output': 15.0},
            'opus': {'input': 5.0, 'output': 25.0}
        }

        costs = model_cost[selected_model]
        input_tokens = estimated_tokens // 3
        output_tokens = (estimated_tokens * 2) // 3

        cost_estimate = {
            'estimated_tokens': estimated_tokens,
            'input_cost': (input_tokens / 1_000_000) * costs['input'],
            'output_cost': (output_tokens / 1_000_000) * costs['output'],
            'total_cost': ((input_tokens / 1_000_000) * costs['input']) + ((output_tokens / 1_000_000) * costs['output'])
        }

        # Build alternatives
        alternatives = []
        if selected_model != 'haiku' and complexity <= 5:
            alternatives.append({'model': 'haiku', 'reason': 'Cost savings'})
        if selected_model != 'sonnet' and complexity >= 5:
            alternatives.append({'model': 'sonnet', 'reason': 'Balanced option'})
        if selected_model != 'opus' and complexity >= 8:
            alternatives.append({'model': 'opus', 'reason': 'Maximum capability'})

        output = {
            'selected_model': selected_model,
            'reason': reason,
            'complexity': complexity,
            'context_percentage': context_pct,
            'alternatives': alternatives,
            'cost_estimate': {
                'total_cost': f'${cost_estimate["total_cost"]:.4f}',
                'input_cost': f'${cost_estimate["input_cost"]:.4f}',
                'output_cost': f'${cost_estimate["output_cost"]:.4f}',
                'estimated_tokens': estimated_tokens
            }
        }

        print(json.dumps(output))
        sys.exit(0)

    # Original full mode
    import argparse

    parser = argparse.ArgumentParser(description='Model Auto-Selector (Step 6)')
    parser.add_argument('--task-info', help='Task information (JSON)')
    parser.add_argument('--estimated-tokens', type=int, default=10000, help='Estimated token usage')
    parser.add_argument('--no-override', action='store_true', help='Disable override option')

    if len(sys.argv) < 2:
        sys.exit(0)

    try:
        args = parser.parse_args()
    except SystemExit:
        sys.exit(0)

    if not args.task_info:
        sys.exit(0)

    try:
        task_info = json.loads(args.task_info)
    except json.JSONDecodeError:
        print(f"Invalid JSON task info")
        sys.exit(1)

    selector = ModelAutoSelector()
    result = selector.auto_select(
        task_info,
        estimated_tokens=args.estimated_tokens,
        allow_override=not args.no_override
    )

    selector.print_result(result)

    sys.exit(0)


if __name__ == '__main__':
    main()
