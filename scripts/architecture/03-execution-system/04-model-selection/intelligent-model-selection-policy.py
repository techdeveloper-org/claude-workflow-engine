#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Intelligent Model Selection Policy (v3.0 - FULLY CONSOLIDATED)

CONSOLIDATED SCRIPT - Maps to:
  policies/03-execution-system/04-model-selection/intelligent-model-selection-policy.md

Consolidates 4 scripts (1422+ original lines) into one enterprise-grade policy:
  1. intelligent-model-selector.py    (375 lines) - Core selector, task-type mappings, complexity scoring
  2. model-auto-selector.py           (437 lines) - Auto-selector, risk factors, cost estimation, alternatives
  3. model-selection-enforcer.py      (299 lines) - Enforcement logic, keyword scoring, usage logging
  4. model-selection-monitor.py       (311 lines) - Monitoring, distribution tracking, trend analysis, alerts

ALL FUNCTIONALITY PRESERVED - zero logic loss in consolidation.

Classes:
  IntelligentModelSelector  - Core selection + auto-selection + task-type mapping
  ModelSelectionEnforcer    - Enforcement + keyword scoring + usage logging + recommendations
  ModelSelectionMonitor     - Monitoring + distribution + trend analysis + alert generation

Policy Interface:
  enforce()    - Initialize all systems, enforce model policy
  validate()   - Compliance check
  report()     - Generate statistics and model registry

CLI Modes:
  --enforce                       Run full policy enforcement
  --validate                      Validate compliance
  --report                        Generate statistics report
  --select TASK_JSON              Select model for a task (JSON input)
  --analyze MESSAGE               Analyze a request message and recommend model
  --monitor [--days N]            Show monitoring report
  --distribution [--days N]       Show model usage distribution
  --trend [--days N]              Show daily trend data
  --check-compliance [--days N]   Check distribution compliance
  --alert [--days N]              Alert if non-compliant
  --stats                         Show usage statistics from enforcer log
  --test                          Run built-in test suite

Usage Examples:
  python intelligent-model-selection-policy.py --enforce
  python intelligent-model-selection-policy.py --validate
  python intelligent-model-selection-policy.py --report
  python intelligent-model-selection-policy.py --select '{"task_type": "create", "multi_service": true}'
  python intelligent-model-selection-policy.py --analyze "Implement a JWT authentication service"
  python intelligent-model-selection-policy.py --monitor --days 14
  python intelligent-model-selection-policy.py --alert --days 7
  python intelligent-model-selection-policy.py --test

Windows UTF-8 compatible. All outputs are ASCII-safe.
"""

# ============================================================================
# ENCODING FIX - Windows UTF-8 compatibility (must be first)
# ============================================================================

import sys

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
else:
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


# ============================================================================
# STANDARD LIBRARY IMPORTS
# ============================================================================

import re
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Any, Tuple

# Optional: yaml support for output formatting
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# ============================================================================
# GLOBAL CONFIGURATION
# ============================================================================

MEMORY_DIR = Path.home() / ".claude" / "memory"
LOGS_DIR = MEMORY_DIR / "logs"
POLICY_LOG = LOGS_DIR / "policy-hits.log"
MODEL_SELECTION_LOG = LOGS_DIR / "model-selection.log"
MODEL_USAGE_LOG = LOGS_DIR / "model-usage.log"

# Configure module-level logger
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("intelligent-model-selection-policy")


# ============================================================================
# CLASS: IntelligentModelSelector
# Consolidates: intelligent-model-selector.py + model-auto-selector.py
# ============================================================================

class IntelligentModelSelector:
    """
    Core model selection engine.

    Combines the base selector (intelligent-model-selector.py) with the
    auto-selector (model-auto-selector.py) to provide:
      - Task-type to model mapping table
      - Multi-factor complexity scoring (0-30 scale)
      - Risk factor identification and scoring
      - Plan-mode detection and mandatory OPUS routing
      - Dynamic upgrade conditions
      - Cost estimation (input/output token split)
      - Alternative model suggestions with trade-offs
      - Selection logging to model-selection.log

    Model Tiers (2026 pricing, per million tokens):
      HAIKU  / claude-haiku-4-5-20251001 : $1 input / $5 output   - The Executor
      SONNET / claude-sonnet-4-6          : $3 input / $15 output  - The Workhorse
      OPUS   / claude-opus-4-6            : $5 input / $25 output  - The Strategist
    """

    # ------------------------------------------------------------------
    # Model registry
    # ------------------------------------------------------------------

    MODEL_INFO: Dict[str, Dict[str, Any]] = {
        'haiku': {
            'id': 'claude-haiku-4-5-20251001',
            'nickname': 'The Executor',
            'context': '200K',
            'input_cost': 1.0,
            'output_cost': 5.0,
            'tokens_per_task': 2000,
            'best_for': 'Fast searches, reads, simple status checks, cost-sensitive tasks'
        },
        'sonnet': {
            'id': 'claude-sonnet-4-6',
            'nickname': 'The Workhorse',
            'context': '200K (1M beta)',
            'input_cost': 3.0,
            'output_cost': 15.0,
            'tokens_per_task': 5000,
            'best_for': 'Implementation, editing, business logic, integrations, balanced reasoning'
        },
        'opus': {
            'id': 'claude-opus-4-6',
            'nickname': 'The Strategist',
            'context': '200K (1M beta)',
            'input_cost': 5.0,
            'output_cost': 25.0,
            'tokens_per_task': 10000,
            'best_for': 'Architecture, planning, complex reasoning, novel problems, strategic decisions'
        }
    }

    # ------------------------------------------------------------------
    # Task-type to model mapping table (from intelligent-model-selector.py)
    # ------------------------------------------------------------------

    TASK_TYPE_MODELS: Dict[str, str] = {
        # Architecture & Design -> OPUS
        'Architecture Design': 'opus',
        'System Design': 'opus',
        'Migration Planning': 'opus',
        'Refactoring Strategy': 'opus',

        # Implementation -> SONNET
        'API Creation': 'sonnet',
        'Service Implementation': 'sonnet',
        'Business Logic': 'sonnet',
        'Integration': 'sonnet',
        'Authentication': 'sonnet',
        'Authorization': 'sonnet',

        # UI/Frontend -> SONNET
        'Dashboard': 'sonnet',
        'UI/UX': 'sonnet',
        'Frontend': 'sonnet',

        # Simple Operations -> HAIKU
        'Bug Fix': 'haiku',
        'Documentation': 'haiku',
        'Configuration': 'haiku',
        'Constant Addition': 'haiku',

        # Search & Analysis -> HAIKU
        'Code Search': 'haiku',
        'File Reading': 'haiku',
        'Status Check': 'haiku'
    }

    # ------------------------------------------------------------------
    # Complexity score definitions (from model-auto-selector.py)
    # ------------------------------------------------------------------

    # Thresholds for model tier selection
    COMPLEXITY_THRESHOLDS: Dict[str, int] = {
        'haiku_max': 10,
        'sonnet_max': 20,
        'opus_min': 21
    }

    # Risk factors that trigger model upgrades
    OPUS_RISKS = {'architecture_change', 'novel_problem'}
    SECURITY_RISKS = {'security_critical'}
    SONNET_UPGRADE_RISKS = {'security_critical', 'novel_problem', 'multi_service', 'database_changes'}

    def __init__(self) -> None:
        """Initialize selector with log paths."""
        self.logs_path = LOGS_DIR
        self.model_log = MODEL_SELECTION_LOG

    # ------------------------------------------------------------------
    # Complexity scoring (merged from both scripts)
    # ------------------------------------------------------------------

    def calculate_complexity_score(self, task_info: Dict[str, Any]) -> int:
        """
        Calculate complexity score from task information (0-30 scale).

        Scoring sources (from model-auto-selector.py):
          - Task type base score (create/implement/build = 10, fix/debug = 7, etc.)
          - File count impact (>10 files = +8, >5 = +5, >2 = +3)
          - Service count for microservices (>3 = +7, >1 = +4)
          - Database changes (+5), security-critical (+6), no examples (+5)

        Additional modifiers (from intelligent-model-selector.py):
          - multi_service, requires_planning, requires_reasoning, requires_creativity

        Returns:
            int: Complexity score capped at 30
        """
        score = 0

        # Base score from task type string
        task_type = task_info.get('task_type', '').lower()
        if task_type in {'create', 'implement', 'build'}:
            score += 10
        elif task_type in {'fix', 'debug', 'refactor'}:
            score += 7
        elif task_type in {'update', 'modify'}:
            score += 5
        elif task_type in {'analyze', 'review', 'research'}:
            score += 3
        else:
            score += 2

        # File count complexity
        file_count = task_info.get('file_count', 0)
        if file_count > 10:
            score += 8
        elif file_count > 5:
            score += 5
        elif file_count > 2:
            score += 3

        # Service count (microservices context)
        service_count = task_info.get('service_count', 0)
        if service_count > 3:
            score += 7
        elif service_count > 1:
            score += 4

        # Boolean modifiers from model-auto-selector.py
        if task_info.get('database_changes', False):
            score += 5
        if task_info.get('security_critical', False):
            score += 6
        if task_info.get('no_examples', False):
            score += 5

        # Boolean modifiers from intelligent-model-selector.py
        if task_info.get('multi_service', False) and service_count <= 1:
            # Avoid double-counting if service_count already present
            score += 3
        if task_info.get('requires_planning', False):
            score += 5
        if task_info.get('requires_reasoning', False):
            score += 4
        if task_info.get('requires_creativity', False):
            score += 3

        return min(score, 30)

    def calculate_risk_factors(self, task_info: Dict[str, Any]) -> List[str]:
        """
        Identify risk factors that may require model upgrade.

        Risk factors (from model-auto-selector.py):
          security_critical, multi_service, database_changes,
          no_examples, architecture_change, novel_problem

        Returns:
            List[str]: List of active risk factor names
        """
        risks: List[str] = []

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

    def calculate_risk_score(self, task_info: Dict[str, Any]) -> int:
        """
        Calculate numeric risk score (from intelligent-model-selector.py).

        Risk weight table:
          security       = 5
          multi_service  = 3
          database       = 4
          external_api   = 2
          complex_logic  = 3

        Returns:
            int: Aggregate risk score
        """
        risk_weights = {
            'involves_security': 5,
            'involves_database': 4,
            'involves_external_api': 2,
            'multi_service': 3,
        }
        score = 0
        for key, weight in risk_weights.items():
            if task_info.get(key, False):
                score += weight
        return score

    # ------------------------------------------------------------------
    # Core selection logic
    # ------------------------------------------------------------------

    def select_model(
        self,
        task_info: Optional[Dict[str, Any]] = None,
        complexity: Optional[Dict[str, Any]] = None,
        task_type: Optional[str] = None,
        plan_mode_decision: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Main model selection method - supports two calling conventions:

        Convention A (from intelligent-model-selector.py):
          select_model(complexity=dict, task_type=str, plan_mode_decision=dict)
          Where complexity dict contains: score, level, risk_factors, estimated_tasks

        Convention B (from model-auto-selector.py via auto_select):
          select_model(task_info=dict)
          Where task_info contains raw task properties

        Returns:
            dict with keys:
              selected_model, model_id, nickname, reasoning, alternatives,
              cost_estimate, confidence, dynamic_upgrade, complexity_score, risk_score
        """
        # Normalize inputs to support both calling conventions
        if task_info is not None:
            # Convention B path - compute everything from task_info
            complexity_score = self.calculate_complexity_score(task_info)
            risk_factors = self.calculate_risk_factors(task_info)
            risk_score = self.calculate_risk_score(task_info)
            complexity_level = self._score_to_level(complexity_score)
            plan_mode = task_info.get('plan_mode', False)
            estimated_tasks = task_info.get('estimated_tasks', 5)
            task_type_str = task_info.get('task_type', 'Unknown')
        else:
            # Convention A path - complexity dict already provided
            if complexity is None:
                complexity = {}
            complexity_score = complexity.get('score', 0)
            complexity_level = complexity.get('level', 'SIMPLE')
            risk_factors = complexity.get('risk_factors', [])
            risk_score = len(risk_factors) * 2  # approximate from list
            estimated_tasks = complexity.get('estimated_tasks', 5)
            plan_mode = (
                (plan_mode_decision or {}).get('auto_enter', False) or
                (plan_mode_decision or {}).get('in_plan_mode', False)
            )
            task_type_str = task_type or 'Unknown'

        selection: Dict[str, Any] = {
            'selected_model': None,
            'reasoning': [],
            'alternatives': [],
            'cost_estimate': {},
            'confidence': 'high',
            'dynamic_upgrade': {
                'enabled': True,
                'conditions': [],
                'upgrade_to': None
            },
            'complexity_score': complexity_score,
            'risk_score': risk_score,
            'risk_factors': risk_factors
        }

        # RULE 1: Plan mode always requires OPUS
        if plan_mode:
            selection['selected_model'] = 'opus'
            selection['reasoning'].append(
                'Plan mode requires OPUS for deep analysis and architectural thinking'
            )
            selection['reasoning'].append(
                'Critical decisions need the highest capability model'
            )
            if complexity_score >= 10:
                selection['dynamic_upgrade']['upgrade_to'] = 'sonnet'
                selection['reasoning'].append(
                    'After plan approval, switch to SONNET for implementation execution'
                )

        # RULE 2: Explicit requires_opus flag
        elif task_info is not None and task_info.get('requires_opus', False):
            selection['selected_model'] = 'opus'
            selection['reasoning'].append('Task explicitly requires OPUS (strategic reasoning)')

        # RULE 3: Very high risk score (>= 8) escalates to OPUS
        elif risk_score >= 8:
            selection['selected_model'] = 'opus'
            selection['reasoning'].append(
                f'High aggregate risk score ({risk_score}) requires strategic OPUS model'
            )

        # RULE 4: Task-type table override (from intelligent-model-selector.py)
        elif task_type_str in self.TASK_TYPE_MODELS:
            suggested = self.TASK_TYPE_MODELS[task_type_str]

            if suggested == 'opus':
                selection['selected_model'] = 'opus'
                selection['reasoning'].append(
                    f'Task type "{task_type_str}" maps to OPUS in policy table'
                )
            elif suggested == 'haiku' and complexity_score >= 10:
                # Complexity overrides simple task-type suggestion
                selection['selected_model'] = 'sonnet'
                selection['reasoning'].append(
                    f'Task type suggests HAIKU but complexity ({complexity_score}) requires SONNET upgrade'
                )
            else:
                selection['selected_model'] = suggested
                selection['reasoning'].append(
                    f'Task type "{task_type_str}" matches {suggested.upper()} capabilities in policy table'
                )

        # RULE 5: Pure complexity-based selection (from intelligent-model-selector.py)
        else:
            if complexity_score > self.COMPLEXITY_THRESHOLDS['sonnet_max']:
                # Check for OPUS-level risk factors first
                if any(r in self.OPUS_RISKS for r in risk_factors):
                    selection['selected_model'] = 'opus'
                    selection['reasoning'].append(
                        f'Very high complexity ({complexity_score}) with critical risk factors {risk_factors} -> OPUS'
                    )
                else:
                    selection['selected_model'] = 'sonnet'
                    selection['reasoning'].append(
                        f'Very high complexity ({complexity_score}) requires SONNET reasoning'
                    )
                    selection['reasoning'].append(
                        'Escalate to OPUS if architectural decisions arise during execution'
                    )
                    selection['dynamic_upgrade']['upgrade_to'] = 'opus'
                    selection['dynamic_upgrade']['conditions'].append('Architectural issues discovered mid-task')

            elif complexity_score > self.COMPLEXITY_THRESHOLDS['haiku_max']:
                # Complex range (11-20) - check for OPUS-level risks
                if any(r in self.OPUS_RISKS for r in risk_factors):
                    selection['selected_model'] = 'opus'
                    selection['reasoning'].append(
                        f'Complex task ({complexity_score}) with critical risks {risk_factors} -> OPUS'
                    )
                else:
                    selection['selected_model'] = 'sonnet'
                    selection['reasoning'].append(
                        f'High complexity ({complexity_score}) requires SONNET reasoning'
                    )
                    selection['reasoning'].append(
                        'Multiple files and complex logic coordination needed'
                    )

            else:
                # Simple/moderate range (0-10)
                if complexity_score <= 4:
                    # Simple: check for critical risk overrides
                    if any(r in self.SECURITY_RISKS for r in risk_factors):
                        selection['selected_model'] = 'sonnet'
                        selection['reasoning'].append(
                            f'Simple complexity but security-critical risk -> SONNET upgrade'
                        )
                    else:
                        selection['selected_model'] = 'haiku'
                        selection['reasoning'].append(
                            f'Low complexity ({complexity_score}) -> HAIKU for speed and efficiency'
                        )
                else:
                    # Moderate (5-10): risk-based decision
                    if any(r in self.SONNET_UPGRADE_RISKS for r in risk_factors):
                        selection['selected_model'] = 'sonnet'
                        selection['reasoning'].append(
                            f'Moderate complexity with risks {risk_factors} -> SONNET upgrade'
                        )
                    elif task_type_str in {'API Creation', 'Business Logic', 'Integration'}:
                        selection['selected_model'] = 'sonnet'
                        selection['reasoning'].append(
                            f'Moderate complexity + code implementation task -> SONNET'
                        )
                    else:
                        selection['selected_model'] = 'haiku'
                        selection['reasoning'].append(
                            f'Moderate complexity ({complexity_score}) without elevated risks -> HAIKU'
                        )
                        selection['alternatives'].append({
                            'model': 'sonnet',
                            'reason': 'Use if task proves more complex than expected',
                            'risk': 'May need upgrade during execution',
                            'cost_increase': '~3x'
                        })

        # RULE 6: Security/multi-service post-selection risk adjustment
        if selection['selected_model'] == 'haiku' and risk_factors:
            if any(r in {'security_critical'} for r in risk_factors):
                selection['selected_model'] = 'sonnet'
                selection['reasoning'].append(
                    '[SECURITY] Security-critical flag detected -> upgraded HAIKU to SONNET'
                )
            elif any(r in {'multi_service'} for r in risk_factors):
                selection['selected_model'] = 'sonnet'
                selection['reasoning'].append(
                    '[MULTI-SERVICE] Multi-service coordination detected -> upgraded HAIKU to SONNET'
                )

        # RULE 7: Context pressure adjustment
        if task_info is not None:
            context_pct = task_info.get('context_percentage', 0)
            if context_pct > 85 and selection['selected_model'] == 'opus':
                selection['context_adjustment'] = (
                    f'Context high ({context_pct}%) - consider SONNET as fallback'
                )
                selection['recommended_fallback'] = 'sonnet'

        # Populate model metadata
        model_key = selection['selected_model']
        info = self.MODEL_INFO[model_key]
        selection['model_id'] = info['id']
        selection['nickname'] = info['nickname']
        selection['context_window'] = info['context']

        # Set standard dynamic upgrade conditions for non-OPUS selections
        if model_key != 'opus':
            selection['dynamic_upgrade']['conditions'].extend([
                'Build failures >= 3',
                'Test failures >= 3',
                'Security vulnerabilities found',
                'Performance issues detected'
            ])

        # Cost estimation
        selection['cost_estimate'] = self.estimate_cost(model_key, estimated_tasks)

        # Alternatives (if not already populated by HAIKU moderate path)
        if not selection['alternatives']:
            selection['alternatives'] = self.suggest_alternatives(model_key, complexity_score)

        return selection

    # ------------------------------------------------------------------
    # Auto-select entry point (from model-auto-selector.py)
    # ------------------------------------------------------------------

    def auto_select(
        self,
        task_info: Dict[str, Any],
        estimated_tokens: int = 10000,
        allow_override: bool = True
    ) -> Dict[str, Any]:
        """
        High-level auto-selection entry point (from model-auto-selector.py).

        Computes complexity + risks automatically from task_info dict, then
        delegates to select_model(). Logs result to model-selection.log and
        optionally marks completion in blocking-policy-enforcer.

        Args:
            task_info:        Dict with task properties (task_type, file_count, etc.)
            estimated_tokens: Estimated total token usage for cost estimation
            allow_override:   Flag for downstream tools to allow user override

        Returns:
            dict with selected_model, reason, confidence, complexity_score,
            risks, cost_estimate, alternatives, allow_override, timestamp
        """
        complexity_score = self.calculate_complexity_score(task_info)
        risk_factors = self.calculate_risk_factors(task_info)
        plan_mode = task_info.get('plan_mode', False)

        # Use the unified select_model logic
        selection_result = self.select_model(
            task_info=task_info,
            plan_mode_decision={'in_plan_mode': plan_mode}
        )

        model = selection_result['selected_model']
        cost = self.estimate_cost_from_tokens(model, estimated_tokens)

        result = {
            'selected_model': model,
            'reason': '; '.join(selection_result['reasoning']),
            'confidence': selection_result['confidence'],
            'complexity_score': complexity_score,
            'risks': risk_factors,
            'cost_estimate': cost,
            'alternatives': selection_result['alternatives'],
            'allow_override': allow_override,
            'timestamp': datetime.now().isoformat()
        }

        # Log selection
        self._log_selection(result)

        # Optionally notify blocking-policy-enforcer
        self._notify_blocking_enforcer()

        return result

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    def estimate_cost(self, model: str, num_tasks: int) -> Dict[str, Any]:
        """
        Estimate cost based on model token rates and estimated task count.
        Uses 60/40 input/output split. (from intelligent-model-selector.py)

        Args:
            model:     Model key ('haiku', 'sonnet', 'opus')
            num_tasks: Estimated number of tasks to complete

        Returns:
            dict with model, estimated_tokens, input_tokens, output_tokens,
            estimated_cost_usd, num_tasks
        """
        info = self.MODEL_INFO[model]
        tokens_per_task = info['tokens_per_task']
        total_tokens = tokens_per_task * num_tasks
        input_tokens = total_tokens * 0.6
        output_tokens = total_tokens * 0.4

        estimated_cost = (
            (input_tokens / 1_000_000) * info['input_cost'] +
            (output_tokens / 1_000_000) * info['output_cost']
        )

        return {
            'model': model,
            'estimated_tokens': int(total_tokens),
            'input_tokens': int(input_tokens),
            'output_tokens': int(output_tokens),
            'estimated_cost_usd': round(estimated_cost, 4),
            'num_tasks': num_tasks
        }

    def estimate_cost_from_tokens(self, model: str, estimated_tokens: int) -> Dict[str, Any]:
        """
        Estimate cost from a direct token count estimate. (from model-auto-selector.py)

        Args:
            model:             Model key
            estimated_tokens:  Total token estimate (input + output combined)

        Returns:
            dict with input_cost, output_cost, total_cost, estimated_tokens
        """
        info = self.MODEL_INFO[model]
        input_tokens = estimated_tokens * 0.6
        output_tokens = estimated_tokens * 0.4
        input_cost = (input_tokens / 1_000_000) * info['input_cost']
        output_cost = (output_tokens / 1_000_000) * info['output_cost']
        total_cost = input_cost + output_cost

        return {
            'input_cost': round(input_cost, 4),
            'output_cost': round(output_cost, 4),
            'total_cost': round(total_cost, 4),
            'estimated_tokens': estimated_tokens
        }

    # ------------------------------------------------------------------
    # Alternatives suggestion (from model-auto-selector.py)
    # ------------------------------------------------------------------

    def suggest_alternatives(
        self,
        selected_model: str,
        complexity_score: int
    ) -> List[Dict[str, str]]:
        """
        Suggest alternative models with trade-offs. (from model-auto-selector.py)

        Args:
            selected_model:   Currently selected model key
            complexity_score: Current complexity score

        Returns:
            List of alternative dicts with model, reason, cost_savings/cost_increase
        """
        alternatives: List[Dict[str, str]] = []

        if selected_model == 'sonnet':
            if complexity_score <= 10:
                alternatives.append({
                    'model': 'haiku',
                    'reason': 'Cheaper (~3x), fastest, near-frontier intelligence for simpler tasks',
                    'cost_savings': '67%'
                })
            if complexity_score >= 15:
                alternatives.append({
                    'model': 'opus',
                    'reason': 'Highest intelligence, catches subtle edge cases and architectural issues',
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
                'reason': 'May be sufficient for execution phase after planning is complete',
                'cost_savings': '40%'
            })

        return alternatives

    # ------------------------------------------------------------------
    # Batch operations and context-aware recommendation
    # ------------------------------------------------------------------

    def select_batch_models(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Select models for multiple tasks in a batch.

        Args:
            tasks: List of task_info dicts

        Returns:
            List of selection results
        """
        selections = []
        for task in tasks:
            selection = self.select_model(task_info=task)
            selections.append(selection)
        return selections

    def get_model_recommendation(
        self,
        task_info: Dict[str, Any],
        context_percentage: int = 0
    ) -> Dict[str, Any]:
        """
        Get comprehensive model recommendation with context pressure consideration.

        Args:
            task_info:          Task information dict
            context_percentage: Current context window usage (0-100)

        Returns:
            Selection dict with optional context_adjustment field
        """
        task_info['context_percentage'] = context_percentage
        return self.select_model(task_info=task_info)

    # ------------------------------------------------------------------
    # Formatted output (from intelligent-model-selector.py)
    # ------------------------------------------------------------------

    def print_selection(self, selection: Dict[str, Any]) -> None:
        """Print formatted model selection summary to stdout."""
        model = selection.get('selected_model', 'unknown')
        nickname = selection.get('nickname', '')
        print("=" * 80)
        print("[MODEL SELECTION] INTELLIGENT MODEL SELECTION")
        print("=" * 80)
        print(f"\n[SELECTED] {model.upper()} - {nickname}")
        print(f"\n[REASONING]")
        for reason in selection.get('reasoning', []):
            print(f"  - {reason}")

        cost = selection.get('cost_estimate', {})
        if cost:
            print(f"\n[COST ESTIMATE]")
            if 'estimated_cost_usd' in cost:
                print(f"  Tokens: {cost.get('estimated_tokens', 0):,}")
                print(f"  Cost:   ${cost.get('estimated_cost_usd', 0):.4f}")
                print(f"  Tasks:  {cost.get('num_tasks', 0)}")
            elif 'total_cost' in cost:
                print(f"  Tokens: {cost.get('estimated_tokens', 0):,}")
                print(f"  Input:  ${cost.get('input_cost', 0):.4f}")
                print(f"  Output: ${cost.get('output_cost', 0):.4f}")
                print(f"  Total:  ${cost.get('total_cost', 0):.4f}")

        alts = selection.get('alternatives', [])
        if alts:
            print(f"\n[ALTERNATIVES]")
            for alt in alts:
                savings = alt.get('cost_savings', alt.get('cost_increase', ''))
                savings_label = 'cost_savings' if 'cost_savings' in alt else 'cost_increase'
                print(f"  - {alt['model'].upper()}: {alt['reason']} ({savings_label}: {savings})")

        upgrade = selection.get('dynamic_upgrade', {})
        if upgrade.get('upgrade_to'):
            print(f"\n[DYNAMIC UPGRADE]")
            print(f"  Can upgrade to: {upgrade['upgrade_to'].upper()}")
            for cond in upgrade.get('conditions', []):
                print(f"  Condition: {cond}")

        print("=" * 80)

    def print_auto_select_result(self, result: Dict[str, Any]) -> None:
        """Print formatted auto-selection result to stdout. (from model-auto-selector.py)"""
        print(f"\n{'='*70}")
        print(f"[MODEL AUTO-SELECTOR]")
        print(f"{'='*70}\n")

        print(f"[ANALYSIS]")
        print(f"  Complexity Score: {result['complexity_score']}/30")
        risks = result.get('risks', [])
        if risks:
            print(f"  Risk Factors: {', '.join(risks)}")
        else:
            print(f"  Risk Factors: None")

        print(f"\n[SELECTED] {result['selected_model'].upper()}")
        print(f"  Reason: {result['reason']}")
        print(f"  Confidence: {result['confidence'].upper()}")

        cost = result.get('cost_estimate', {})
        if cost:
            tokens = cost.get('estimated_tokens', 0)
            print(f"\n[COST ESTIMATE] ({tokens:,} tokens)")
            print(f"  Input:  ${cost.get('input_cost', 0):.4f}")
            print(f"  Output: ${cost.get('output_cost', 0):.4f}")
            print(f"  Total:  ${cost.get('total_cost', 0):.4f}")

        alts = result.get('alternatives', [])
        if alts:
            print(f"\n[ALTERNATIVES]")
            for alt in alts:
                savings = alt.get('cost_savings', alt.get('cost_increase', ''))
                label = 'savings' if 'cost_savings' in alt else 'increase'
                print(f"  - {alt['model'].upper()}: {alt['reason']} (cost {label}: {savings})")

        if result.get('allow_override'):
            print(f"\n[NOTE] Override available if needed")

        print(f"\n{'='*70}\n")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_to_level(score: int) -> str:
        """Map numeric complexity score to level label."""
        if score < 5:
            return 'SIMPLE'
        elif score < 10:
            return 'MODERATE'
        elif score < 20:
            return 'COMPLEX'
        else:
            return 'VERY_COMPLEX'

    def _log_selection(self, result: Dict[str, Any]) -> None:
        """Log model selection result to model-selection.log. (from model-auto-selector.py)"""
        try:
            self.logs_path.mkdir(parents=True, exist_ok=True)
            log_entry = {
                'timestamp': result.get('timestamp', datetime.now().isoformat()),
                'model': result['selected_model'],
                'complexity': result.get('complexity_score', 0),
                'risks': result.get('risks', []),
                'confidence': result.get('confidence', 'unknown')
            }
            with open(self.model_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as exc:
            logger.warning("Could not write to model-selection.log: %s", exc)

    def _notify_blocking_enforcer(self) -> None:
        """
        Attempt to notify blocking-policy-enforcer of model selection.
        (from model-auto-selector.py - uses importlib with subprocess fallback)
        """
        try:
            import importlib.util
            enforcer_path = MEMORY_DIR / 'blocking-policy-enforcer.py'
            if enforcer_path.exists():
                spec = importlib.util.spec_from_file_location(
                    'blocking_policy_enforcer', enforcer_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, 'BlockingPolicyEnforcer'):
                    enforcer = module.BlockingPolicyEnforcer()
                    enforcer.mark_complete('model_selected')
        except Exception:
            # Silent fallback - blocking enforcer is optional
            pass


# ============================================================================
# CLASS: ModelSelectionEnforcer
# Consolidates: model-selection-enforcer.py
# ============================================================================

class ModelSelectionEnforcer:
    """
    Policy enforcement engine for model selection.

    Provides:
      - Keyword-based request analysis with pattern scoring
      - Enforcement (analyze + recommend against current model)
      - Usage logging to model-usage.log
      - Usage statistics retrieval
      - Built-in test suite for validation

    Keywords and Patterns:
      HAIKU:  search, find, grep, list, show, read, view, check, status, get
      SONNET: implement, create, write, edit, modify, update, fix, refactor, add, build
      OPUS:   design, architecture, plan, analyze, complex, system, strategy, approach

    Special case bonuses:
      +5 OPUS:   architecture, design system, plan implementation, design microservices
      +4 SONNET: implement, create function, write code, build feature, add functionality
      +3 HAIKU:  find file, search for, list all, show me, get list
    """

    # Keyword rules per model (from model-selection-enforcer.py)
    RULES: Dict[str, Dict[str, Any]] = {
        'haiku': {
            'keywords': [
                'search', 'find', 'grep', 'glob', 'list', 'show',
                'read', 'view', 'check', 'status', 'get'
            ],
            'patterns': [
                r'\b(search|find|grep|list|show)\b',
                r'\b(read|view|check|status)\b',
                r'\bget\s+\w+',
            ],
            'description': 'Quick searches, reads, status checks',
            'priority': 1
        },
        'sonnet': {
            'keywords': [
                'implement', 'create', 'write', 'edit', 'modify',
                'update', 'fix', 'refactor', 'add', 'build'
            ],
            'patterns': [
                r'\b(implement|create|write|build)\b',
                r'\b(edit|modify|update|fix)\b',
                r'\b(add|refactor|change)\b',
            ],
            'description': 'Implementation, editing, fixes',
            'priority': 2
        },
        'opus': {
            'keywords': [
                'design', 'architecture', 'plan', 'analyze', 'complex',
                'system', 'strategy', 'approach'
            ],
            'patterns': [
                r'\b(design|architect|plan)\b',
                r'\b(analyze|evaluate|assess)\b',
                r'\b(complex|system|strategy)\b',
            ],
            'description': 'Architecture, planning, complex analysis',
            'priority': 3
        }
    }

    # Special case phrase bonuses
    OPUS_BONUS_PHRASES = [
        'architecture', 'design system', 'plan implementation', 'design microservices'
    ]
    SONNET_BONUS_PHRASES = [
        'implement', 'create function', 'write code', 'build feature', 'add functionality'
    ]
    HAIKU_BONUS_PHRASES = [
        'find file', 'search for', 'list all', 'show me', 'get list'
    ]

    def __init__(self) -> None:
        """Initialize enforcer with log paths."""
        self.memory_dir = MEMORY_DIR
        self.usage_log = MODEL_USAGE_LOG
        self.usage_log.parent.mkdir(parents=True, exist_ok=True)

    def analyze_request(self, message: str) -> Dict[str, Any]:
        """
        Analyze a request message and recommend a model using keyword/pattern scoring.

        Scoring:
          +1 per matching keyword
          +2 per matching regex pattern
          +5 OPUS bonus for architecture phrases
          +4 SONNET bonus for implementation phrases
          +3 HAIKU bonus for search phrases

        Final decision rules:
          - 'analyz' present AND opus_score >= 2 -> OPUS
          - 'implement' present AND sonnet_score >= 2 -> SONNET
          - opus_score >= 5 -> OPUS
          - sonnet_score >= 2 -> SONNET
          - haiku_score >= 1 -> HAIKU
          - default -> SONNET (safest choice for ambiguous requests)

        Args:
            message: User request message string

        Returns:
            dict with message, recommended_model, scores, reasoning, confidence
        """
        message_lower = message.lower()

        scores: Dict[str, int] = {
            'haiku': 0,
            'sonnet': 0,
            'opus': 0
        }

        # Keyword scoring
        for model, rules in self.RULES.items():
            for keyword in rules['keywords']:
                if keyword in message_lower:
                    scores[model] += 1
            for pattern in rules['patterns']:
                if re.search(pattern, message_lower):
                    scores[model] += 2

        # Special phrase bonuses
        for phrase in self.OPUS_BONUS_PHRASES:
            if phrase in message_lower:
                scores['opus'] += 5
                break
        for phrase in self.SONNET_BONUS_PHRASES:
            if phrase in message_lower:
                scores['sonnet'] += 4
                break
        for phrase in self.HAIKU_BONUS_PHRASES:
            if phrase in message_lower:
                scores['haiku'] += 3
                break

        # Decision logic
        if re.search(r'\banalyz[e|ing]\b', message_lower) and scores['opus'] >= 2:
            recommended = 'opus'
        elif re.search(r'\bimplement(ation|ing|ed|s)?\b', message_lower) and scores['sonnet'] >= 2:
            recommended = 'sonnet'
        elif scores['opus'] >= 5:
            recommended = 'opus'
        elif scores['sonnet'] >= 2:
            recommended = 'sonnet'
        elif scores['haiku'] >= 1:
            recommended = 'haiku'
        else:
            recommended = 'sonnet'

        return {
            'message': message[:100],
            'recommended_model': recommended,
            'scores': scores,
            'reasoning': self._get_reasoning(recommended, scores),
            'confidence': self._calculate_confidence(scores, recommended)
        }

    def enforce(self, message: str, current_model: str = 'sonnet') -> Dict[str, Any]:
        """
        Enforce model selection for a given request.

        Analyzes the message, determines recommended model, and logs the enforcement.
        Returns whether the current model should be changed.

        Args:
            message:       User request message
            current_model: Currently selected model

        Returns:
            dict with current_model, recommended_model, should_change, analysis
        """
        analysis = self.analyze_request(message)
        recommended = analysis['recommended_model']

        result = {
            'current_model': current_model,
            'recommended_model': recommended,
            'should_change': current_model != recommended,
            'analysis': analysis
        }

        self.log_usage(
            recommended,
            'ENFORCEMENT',
            f"current={current_model}, confidence={analysis['confidence']}"
        )

        return result

    def log_usage(
        self,
        model: str,
        request_type: str,
        context: Optional[str] = None
    ) -> None:
        """
        Log model usage to model-usage.log.

        Format: [ISO_TIMESTAMP] MODEL_UPPER | REQUEST_TYPE | context

        Args:
            model:        Model key or name
            request_type: Type of usage (e.g., 'ENFORCEMENT', 'MANUAL')
            context:      Optional context string
        """
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {model.upper()} | {request_type}"
        if context:
            log_entry += f" | {context}"
        log_entry += "\n"

        try:
            with open(self.usage_log, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as exc:
            logger.warning("Could not write to model-usage.log: %s", exc)

    def get_usage_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        Get model usage statistics from model-usage.log.

        Args:
            days: Number of past days to include (unused currently - parses full file)

        Returns:
            dict with total_requests, by_model counts, percentage breakdown
        """
        if not self.usage_log.exists():
            return {'total_requests': 0, 'by_model': {}, 'percentage': {}}

        stats: Dict[str, int] = {'haiku': 0, 'sonnet': 0, 'opus': 0}

        try:
            with open(self.usage_log, 'r', encoding='utf-8') as f:
                for line in f:
                    for model in ('HAIKU', 'SONNET', 'OPUS'):
                        if model in line:
                            stats[model.lower()] += 1
                            break
        except Exception as exc:
            logger.warning("Could not read model-usage.log: %s", exc)

        total = sum(stats.values())
        result: Dict[str, Any] = {
            'total_requests': total,
            'by_model': stats,
            'percentage': {}
        }

        if total > 0:
            for model, count in stats.items():
                result['percentage'][model] = round((count / total) * 100, 1)

        return result

    def run_tests(self) -> Tuple[int, int]:
        """
        Run built-in test suite for model recommendation validation.

        Test cases are from model-selection-enforcer.py:
          find Python files -> haiku
          implement JWT authentication -> sonnet
          design microservices architecture -> opus
          read configuration file -> haiku
          fix bug in login function -> sonnet
          analyze performance bottlenecks -> opus

        Returns:
            Tuple of (passed_count, total_count)
        """
        test_cases = [
            ("Find all Python files in the src directory", "haiku"),
            ("Implement a user authentication system with JWT", "sonnet"),
            ("Design the microservices architecture for our application", "opus"),
            ("Read the configuration file", "haiku"),
            ("Fix the bug in the login function", "sonnet"),
            ("Analyze the performance bottlenecks and suggest improvements", "opus"),
        ]

        print("Running model selection test suite...")
        print("-" * 60)

        passed = 0
        for message, expected in test_cases:
            result = self.analyze_request(message)
            actual = result['recommended_model']
            status = "[OK]" if actual == expected else "[FAIL]"
            if actual == expected:
                passed += 1
            print(f"{status} '{message[:55]}' -> {actual} (expected {expected})")

        print("-" * 60)
        pct = (passed / len(test_cases)) * 100
        print(f"Results: {passed}/{len(test_cases)} correct ({pct:.0f}%)")

        if passed == len(test_cases):
            print("[OK] All tests passed!")
        else:
            print("[WARN] Some tests failed")

        return passed, len(test_cases)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_reasoning(model: str, scores: Dict[str, int]) -> str:
        """Return human-readable reasoning for model recommendation."""
        if model == 'haiku':
            return "Quick search/read operation - Haiku is fastest and most cost-effective"
        elif model == 'sonnet':
            return "Implementation/modification task - Sonnet provides good balance of capability and speed"
        elif model == 'opus':
            return "Complex planning/architecture task - Opus required for deep reasoning"
        return "Default selection - Sonnet chosen as safe default"

    @staticmethod
    def _calculate_confidence(scores: Dict[str, int], recommended: str) -> float:
        """
        Calculate confidence score in recommendation (0.0-1.0).

        Confidence = 0.5 + (score_gap * 0.1), capped at 1.0.
        If recommended score is the only non-zero score, confidence = 1.0.
        """
        max_score = scores.get(recommended, 0)
        other_scores = [s for m, s in scores.items() if m != recommended]

        if not other_scores or max(other_scores) == 0:
            return 1.0

        diff = max_score - max(other_scores)
        confidence = min(1.0, 0.5 + (diff * 0.1))
        return round(confidence, 2)


# ============================================================================
# CLASS: ModelSelectionMonitor
# Consolidates: model-selection-monitor.py
# ============================================================================

class ModelSelectionMonitor:
    """
    Monitoring engine for model usage distribution tracking.

    Reads from model-selection.log (JSON-lines format written by IntelligentModelSelector).
    Provides:
      - Usage data retrieval with time-range filtering
      - Distribution calculation (counts + percentages)
      - Compliance checking against expected policy ranges:
          HAIKU:  35-45%  (searches and status checks)
          SONNET: 50-60%  (implementation tasks)
          OPUS:   3-8%    (architecture and planning)
      - Daily trend analysis
      - Comprehensive usage reports
      - Non-compliance alerts with recommendations
      - Chart-ready trend output
    """

    # Expected distribution ranges (from model-selection-monitor.py)
    EXPECTED_RANGES: Dict[str, Tuple[int, int]] = {
        'haiku':  (35, 45),   # 35-45% for searches
        'sonnet': (50, 60),   # 50-60% for implementation
        'opus':   (3, 8)      # 3-8% for architecture
    }

    MIN_DATA_POINTS = 10  # Minimum entries for reliable analysis

    def __init__(self) -> None:
        """Initialize monitor with log path."""
        self.memory_dir = MEMORY_DIR
        self.usage_log = MODEL_SELECTION_LOG

    def parse_log_entry(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Parse a single log entry line.

        Supports JSON format:
          {"timestamp": "...", "model": "...", "complexity": N, "risks": [...]}

        Args:
            line: Raw log line string

        Returns:
            Parsed dict or None if parsing fails
        """
        try:
            data = json.loads(line.strip())
            return {
                'timestamp': datetime.fromisoformat(data['timestamp']),
                'model': data['model'].lower(),
                'complexity': data.get('complexity', 0),
                'risks': data.get('risks', []),
                'confidence': data.get('confidence', 'unknown')
            }
        except Exception:
            return None

    def get_usage_data(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Retrieve usage data from log within the specified time window.

        Args:
            days: Number of past days to include

        Returns:
            List of parsed log entry dicts, filtered to the time window
        """
        if not self.usage_log.exists():
            return []

        cutoff = datetime.now() - timedelta(days=days)
        usage_data: List[Dict[str, Any]] = []

        try:
            with open(self.usage_log, 'r', encoding='utf-8') as f:
                for line in f:
                    entry = self.parse_log_entry(line)
                    if entry and entry['timestamp'] >= cutoff:
                        usage_data.append(entry)
        except Exception as exc:
            logger.warning("Could not read model-selection.log: %s", exc)

        return usage_data

    def calculate_distribution(self, usage_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate model usage distribution from parsed log data.

        Args:
            usage_data: List of parsed log entry dicts

        Returns:
            dict with total_requests, counts (per model), percentages (per model)
        """
        counts: Dict[str, int] = defaultdict(int)
        for entry in usage_data:
            counts[entry['model']] += 1

        total = sum(counts.values())

        distribution: Dict[str, Any] = {
            'total_requests': total,
            'counts': dict(counts),
            'percentages': {}
        }

        if total > 0:
            for model, count in counts.items():
                distribution['percentages'][model] = round((count / total) * 100, 1)

        return distribution

    def check_distribution(self, distribution: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if the usage distribution complies with expected policy ranges.

        Flags issues for any model outside its expected [min, max] percentage range.
        Flags warnings if total data points < MIN_DATA_POINTS.

        Args:
            distribution: Output from calculate_distribution()

        Returns:
            dict with issues (list), warnings (list), compliant (bool)
        """
        issues: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []
        percentages = distribution['percentages']
        total = distribution['total_requests']

        if total < self.MIN_DATA_POINTS:
            warnings.append({
                'type': 'insufficient_data',
                'message': (
                    f'Only {total} requests logged, need at least '
                    f'{self.MIN_DATA_POINTS} for accurate analysis'
                )
            })

        for model, (min_pct, max_pct) in self.EXPECTED_RANGES.items():
            actual_pct = percentages.get(model, 0)

            if actual_pct < min_pct:
                issues.append({
                    'model': model,
                    'type': 'underused',
                    'expected': f'{min_pct}-{max_pct}%',
                    'actual': f'{actual_pct}%',
                    'message': (
                        f'{model.capitalize()} underused: {actual_pct}% '
                        f'(expected {min_pct}-{max_pct}%)'
                    )
                })
            elif actual_pct > max_pct:
                issues.append({
                    'model': model,
                    'type': 'overused',
                    'expected': f'{min_pct}-{max_pct}%',
                    'actual': f'{actual_pct}%',
                    'message': (
                        f'{model.capitalize()} overused: {actual_pct}% '
                        f'(expected {min_pct}-{max_pct}%)'
                    )
                })

        return {
            'issues': issues,
            'warnings': warnings,
            'compliant': len(issues) == 0
        }

    def get_usage_trends(self, usage_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Group usage data by day to calculate daily trends.

        Args:
            usage_data: List of parsed log entry dicts

        Returns:
            List of daily summary dicts sorted by date:
              [{'date': 'YYYY-MM-DD', 'total': N, 'by_model': {'haiku': N, ...}}, ...]
        """
        by_day: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for entry in usage_data:
            day = entry['timestamp'].date().isoformat()
            by_day[day][entry['model']] += 1

        trends: List[Dict[str, Any]] = []
        for day in sorted(by_day.keys()):
            day_total = sum(by_day[day].values())
            trends.append({
                'date': day,
                'total': day_total,
                'by_model': dict(by_day[day])
            })

        return trends

    def get_chart_data(self, days: int = 7) -> Dict[str, Any]:
        """
        Generate chart-ready trend data with labels and per-model arrays.
        (from model-selection-monitor.py --trend mode)

        Fills in zeros for days without data so arrays are always aligned.

        Args:
            days: Number of days for chart range

        Returns:
            dict with labels (date strings), haiku_data, sonnet_data, opus_data arrays
        """
        usage_data = self.get_usage_data(days)
        trends = self.get_usage_trends(usage_data)
        trends_dict = {t['date']: t['by_model'] for t in trends}

        today = datetime.now()
        labels: List[str] = []
        haiku_data: List[int] = []
        sonnet_data: List[int] = []
        opus_data: List[int] = []

        for i in range(days - 1, -1, -1):
            day = today - timedelta(days=i)
            day_str = day.date().isoformat()
            label = day.strftime('%m/%d')

            labels.append(label)
            day_models = trends_dict.get(day_str, {})
            haiku_data.append(day_models.get('haiku', 0))
            sonnet_data.append(day_models.get('sonnet', 0))
            opus_data.append(day_models.get('opus', 0))

        return {
            'labels': labels,
            'haiku_data': haiku_data,
            'sonnet_data': sonnet_data,
            'opus_data': opus_data
        }

    def generate_report(self, days: int = 7) -> Dict[str, Any]:
        """
        Generate a comprehensive monitoring report.

        Includes distribution, compliance check, trend analysis, and expected ranges.

        Args:
            days: Number of past days to analyze

        Returns:
            dict with period_days, generated_at, distribution, compliance,
            trends, expected_ranges
        """
        usage_data = self.get_usage_data(days)
        distribution = self.calculate_distribution(usage_data)
        compliance = self.check_distribution(distribution)
        trends = self.get_usage_trends(usage_data)

        return {
            'period_days': days,
            'generated_at': datetime.now().isoformat(),
            'distribution': distribution,
            'compliance': compliance,
            'trends': trends,
            'expected_ranges': {
                k: {'min': v[0], 'max': v[1]}
                for k, v in self.EXPECTED_RANGES.items()
            }
        }

    def alert_if_non_compliant(self, report: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate a structured alert if distribution is non-compliant.

        Args:
            report: Output from generate_report()

        Returns:
            Alert dict if non-compliant, None if compliant
        """
        if not report['compliance']['compliant']:
            return {
                'severity': 'WARNING',
                'message': 'Model usage distribution does not match policy',
                'issues': report['compliance']['issues'],
                'recommendations': self._get_recommendations(report['compliance']['issues'])
            }
        return None

    def _get_recommendations(self, issues: List[Dict[str, Any]]) -> List[str]:
        """
        Generate actionable recommendations from compliance issues.

        Args:
            issues: List of issue dicts from check_distribution()

        Returns:
            List of recommendation strings
        """
        recommendations: List[str] = []

        for issue in issues:
            model = issue['model']
            issue_type = issue['type']

            if issue_type == 'underused':
                if model == 'haiku':
                    recommendations.append(
                        "Use Haiku for more searches, reads, and status checks"
                    )
                elif model == 'sonnet':
                    recommendations.append(
                        "Use Sonnet for more implementation and coding tasks"
                    )
                elif model == 'opus':
                    recommendations.append(
                        "Use Opus for more architecture and planning tasks"
                    )

            elif issue_type == 'overused':
                if model == 'haiku':
                    recommendations.append(
                        "Reduce Haiku usage - may be using it for tasks needing Sonnet"
                    )
                elif model == 'sonnet':
                    recommendations.append(
                        "Review Sonnet usage - consider Haiku for simple tasks"
                    )
                elif model == 'opus':
                    recommendations.append(
                        "Reduce Opus usage - may be using it for simple implementation tasks"
                    )

        return recommendations


# ============================================================================
# POLICY SCRIPT INTERFACE FUNCTIONS
# ============================================================================

def log_policy_hit(action: str, context: str = "") -> None:
    """
    Log a policy execution event to policy-hits.log.

    Args:
        action:  Short action label (e.g., 'ENFORCE_START', 'VALIDATE_SUCCESS')
        context: Optional context string
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = (
        f"[{timestamp}] intelligent-model-selection-policy | {action} | {context}\n"
    )
    try:
        POLICY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(POLICY_LOG, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as exc:
        print(f"Warning: Could not write to policy log: {exc}", file=sys.stderr)


def enforce() -> Dict[str, Any]:
    """
    Main policy enforcement function.

    Initializes all three subsystems (Selector, Enforcer, Monitor),
    logs their initialization, and returns a success status dict.

    Returns:
        dict with status, models_available, models list
    """
    try:
        log_policy_hit("ENFORCE_START", "model-selection-enforcement")

        # Initialize all subsystems
        selector = IntelligentModelSelector()
        enforcer = ModelSelectionEnforcer()
        monitor = ModelSelectionMonitor()

        # Register available models
        models_available = list(selector.MODEL_INFO.keys())
        log_policy_hit("MODELS_REGISTERED", ", ".join(models_available))

        # Quick validation: enforcer rules loaded
        rule_count = sum(
            len(r['keywords']) for r in enforcer.RULES.values()
        )
        log_policy_hit("ENFORCER_READY", f"{rule_count} enforcement keywords loaded")

        # Quick validation: monitor configuration
        range_count = len(monitor.EXPECTED_RANGES)
        log_policy_hit("MONITOR_READY", f"{range_count} distribution ranges configured")

        log_policy_hit("ENFORCE_COMPLETE", "All subsystems initialized successfully")
        print(
            "[intelligent-model-selection-policy] Policy enforced - "
            f"{len(models_available)} models available: {', '.join(models_available)}"
        )

        return {
            "status": "success",
            "models_available": len(models_available),
            "models": models_available,
            "enforcer_keywords": rule_count,
            "monitor_ranges": range_count
        }

    except Exception as exc:
        log_policy_hit("ENFORCE_ERROR", str(exc))
        print(f"[intelligent-model-selection-policy] ERROR: {exc}", file=sys.stderr)
        return {"status": "error", "message": str(exc)}


def validate() -> bool:
    """
    Validate policy compliance.

    Checks that:
      - Log directory is accessible
      - All model info entries are present
      - Enforcer rules are configured

    Returns:
        True if valid, False otherwise
    """
    try:
        log_policy_hit("VALIDATE_START", "model-selection-validation")

        # Check log directory
        POLICY_LOG.parent.mkdir(parents=True, exist_ok=True)

        # Validate model info completeness
        selector = IntelligentModelSelector()
        required_models = {'haiku', 'sonnet', 'opus'}
        present_models = set(selector.MODEL_INFO.keys())
        if not required_models.issubset(present_models):
            missing = required_models - present_models
            log_policy_hit("VALIDATE_ERROR", f"Missing models: {missing}")
            return False

        # Validate enforcer rules
        enforcer = ModelSelectionEnforcer()
        for model in required_models:
            if model not in enforcer.RULES:
                log_policy_hit("VALIDATE_ERROR", f"Missing enforcer rules for: {model}")
                return False

        # Validate monitor ranges
        monitor = ModelSelectionMonitor()
        for model in required_models:
            if model not in monitor.EXPECTED_RANGES:
                log_policy_hit("VALIDATE_ERROR", f"Missing monitor range for: {model}")
                return False

        log_policy_hit("VALIDATE_SUCCESS", "model-selection-policy-validated")
        return True

    except Exception as exc:
        log_policy_hit("VALIDATE_ERROR", str(exc))
        return False


def report() -> Dict[str, Any]:
    """
    Generate a comprehensive policy compliance report.

    Includes model registry, enforcer configuration, monitor ranges,
    current usage distribution, and compliance status.

    Returns:
        dict with status, policy name, models, enforcer config,
        monitor config, usage_distribution, timestamp
    """
    try:
        selector = IntelligentModelSelector()
        enforcer = ModelSelectionEnforcer()
        monitor = ModelSelectionMonitor()

        # Usage distribution (last 7 days)
        usage_data = monitor.get_usage_data(days=7)
        distribution = monitor.calculate_distribution(usage_data)
        compliance = monitor.check_distribution(distribution)

        report_data = {
            "status": "success",
            "policy": "intelligent-model-selection-policy",
            "version": "3.0",
            "timestamp": datetime.now().isoformat(),
            "models": {
                name: {
                    'id': info['id'],
                    'nickname': info['nickname'],
                    'context': info['context'],
                    'best_for': info['best_for'],
                    'input_cost_per_million': info['input_cost'],
                    'output_cost_per_million': info['output_cost']
                }
                for name, info in selector.MODEL_INFO.items()
            },
            "enforcer": {
                'rules_count': {
                    model: len(rules['keywords'])
                    for model, rules in enforcer.RULES.items()
                },
                'total_keywords': sum(
                    len(r['keywords']) for r in enforcer.RULES.values()
                )
            },
            "monitor": {
                'expected_ranges': {
                    model: {'min_pct': mn, 'max_pct': mx}
                    for model, (mn, mx) in monitor.EXPECTED_RANGES.items()
                }
            },
            "usage_distribution": distribution,
            "compliance": compliance
        }

        log_policy_hit("REPORT_GENERATED", "model-selection-report")
        return report_data

    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ============================================================================
# CLI INTERFACE
# ============================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            'Intelligent Model Selection Policy v3.0 - '
            'Unified model selection, enforcement, and monitoring'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python intelligent-model-selection-policy.py --enforce
  python intelligent-model-selection-policy.py --validate
  python intelligent-model-selection-policy.py --report
  python intelligent-model-selection-policy.py --select '{"task_type": "create", "multi_service": true}'
  python intelligent-model-selection-policy.py --analyze "Design microservices architecture"
  python intelligent-model-selection-policy.py --monitor --days 14
  python intelligent-model-selection-policy.py --distribution --days 7
  python intelligent-model-selection-policy.py --trend --days 7
  python intelligent-model-selection-policy.py --check-compliance --days 30
  python intelligent-model-selection-policy.py --alert --days 7
  python intelligent-model-selection-policy.py --stats
  python intelligent-model-selection-policy.py --test
        """
    )

    # Policy interface
    parser.add_argument(
        '--enforce', action='store_true',
        help='Run full policy enforcement (initialize all subsystems)'
    )
    parser.add_argument(
        '--validate', action='store_true',
        help='Validate policy compliance'
    )
    parser.add_argument(
        '--report', action='store_true',
        help='Generate comprehensive policy report (JSON output)'
    )

    # Selection modes
    parser.add_argument(
        '--select', metavar='TASK_JSON',
        help='Select model for a task (JSON string with task properties)'
    )
    parser.add_argument(
        '--analyze', metavar='MESSAGE',
        help='Analyze a request message and recommend a model'
    )
    parser.add_argument(
        '--auto-select', metavar='TASK_JSON',
        help='Auto-select model using auto-selector logic (JSON string)'
    )

    # Monitoring modes
    parser.add_argument(
        '--monitor', action='store_true',
        help='Generate monitoring report'
    )
    parser.add_argument(
        '--distribution', action='store_true',
        help='Show model usage distribution'
    )
    parser.add_argument(
        '--trend', action='store_true',
        help='Show chart-ready daily trend data'
    )
    parser.add_argument(
        '--check-compliance', action='store_true',
        help='Check distribution compliance against policy ranges'
    )
    parser.add_argument(
        '--alert', action='store_true',
        help='Alert if usage distribution is non-compliant (exit 1 if non-compliant)'
    )

    # Enforcer modes
    parser.add_argument(
        '--stats', action='store_true',
        help='Show model usage statistics from enforcer log'
    )
    parser.add_argument(
        '--test', action='store_true',
        help='Run built-in test suite for model recommendation validation'
    )
    parser.add_argument(
        '--enforce-request', nargs=2, metavar=('MESSAGE', 'CURRENT_MODEL'),
        help='Enforce model selection for a specific request'
    )

    # Shared options
    parser.add_argument(
        '--days', type=int, default=7,
        help='Number of days for monitoring analysis (default: 7)'
    )
    parser.add_argument(
        '--estimated-tokens', type=int, default=10000,
        help='Estimated token usage for auto-select cost calculation (default: 10000)'
    )
    parser.add_argument(
        '--no-override', action='store_true',
        help='Disable user override option in auto-select mode'
    )
    parser.add_argument(
        '--json', action='store_true',
        help='Force JSON output format'
    )

    return parser


def main() -> int:
    """
    Main CLI entry point.

    Routes to the appropriate subsystem based on CLI arguments.
    Returns exit code: 0 = success, 1 = failure or non-compliance.
    """
    # Default: run enforcement when called without arguments
    if len(sys.argv) < 2:
        result = enforce()
        return 0 if result.get("status") == "success" else 1

    parser = build_arg_parser()
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Policy interface modes
    # ------------------------------------------------------------------

    if args.enforce:
        result = enforce()
        return 0 if result.get("status") == "success" else 1

    if args.validate:
        is_valid = validate()
        print("[OK] Policy valid" if is_valid else "[ERROR] Policy validation failed")
        return 0 if is_valid else 1

    if args.report:
        result = report()
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") == "success" else 1

    # ------------------------------------------------------------------
    # Selection modes
    # ------------------------------------------------------------------

    if args.select:
        try:
            task_info = json.loads(args.select)
            selector = IntelligentModelSelector()
            selection = selector.select_model(task_info=task_info)
            if args.json:
                print(json.dumps(selection, indent=2))
            else:
                selector.print_selection(selection)
            return 0
        except json.JSONDecodeError as exc:
            print(f"[ERROR] Invalid JSON task info: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"[ERROR] Selection failed: {exc}", file=sys.stderr)
            return 1

    if args.auto_select:
        try:
            task_info = json.loads(args.auto_select)
            selector = IntelligentModelSelector()
            result = selector.auto_select(
                task_info,
                estimated_tokens=args.estimated_tokens,
                allow_override=not args.no_override
            )
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                selector.print_auto_select_result(result)
            return 0
        except json.JSONDecodeError as exc:
            print(f"[ERROR] Invalid JSON task info: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"[ERROR] Auto-selection failed: {exc}", file=sys.stderr)
            return 1

    if args.analyze:
        enforcer = ModelSelectionEnforcer()
        result = enforcer.analyze_request(args.analyze)
        print(json.dumps(result, indent=2))
        return 0

    if args.enforce_request:
        message, current_model = args.enforce_request
        enforcer = ModelSelectionEnforcer()
        result = enforcer.enforce(message, current_model)
        print(json.dumps(result, indent=2))
        return 0

    # ------------------------------------------------------------------
    # Monitoring modes
    # ------------------------------------------------------------------

    if args.monitor:
        monitor = ModelSelectionMonitor()
        report_data = monitor.generate_report(args.days)
        print(json.dumps(report_data, indent=2))
        return 0

    if args.distribution:
        monitor = ModelSelectionMonitor()
        usage_data = monitor.get_usage_data(args.days)
        distribution = monitor.calculate_distribution(usage_data)
        print(json.dumps(distribution, indent=2))
        return 0

    if args.trend:
        monitor = ModelSelectionMonitor()
        chart_data = monitor.get_chart_data(args.days)
        print(json.dumps(chart_data, indent=2))
        return 0

    if args.check_compliance:
        monitor = ModelSelectionMonitor()
        usage_data = monitor.get_usage_data(args.days)
        distribution = monitor.calculate_distribution(usage_data)
        compliance = monitor.check_distribution(distribution)
        print(json.dumps(compliance, indent=2))
        return 0 if compliance['compliant'] else 1

    if args.alert:
        monitor = ModelSelectionMonitor()
        report_data = monitor.generate_report(args.days)
        alert = monitor.alert_if_non_compliant(report_data)
        if alert:
            print(json.dumps(alert, indent=2))
            return 1
        else:
            print(json.dumps({'status': 'OK', 'message': 'Model usage distribution is compliant'}))
            return 0

    # ------------------------------------------------------------------
    # Enforcer utility modes
    # ------------------------------------------------------------------

    if args.stats:
        enforcer = ModelSelectionEnforcer()
        stats = enforcer.get_usage_stats(args.days)
        print(json.dumps(stats, indent=2))
        return 0

    if args.test:
        enforcer = ModelSelectionEnforcer()
        passed, total = enforcer.run_tests()
        return 0 if passed == total else 1

    # No recognized argument - show help
    parser.print_help()
    return 1


# ============================================================================
# SCRIPT ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    sys.exit(main())
