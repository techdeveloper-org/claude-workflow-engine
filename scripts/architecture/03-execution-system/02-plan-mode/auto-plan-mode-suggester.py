#!/usr/bin/env python3
"""
Automatic Plan Mode Suggester
Analyzes complexity and suggests whether to use plan mode
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


import json
import yaml
from typing import Dict, List
from datetime import datetime


class AutoPlanModeSuggester:
    """Automatically suggests whether to use plan mode based on task complexity.

    Analyzes task complexity, risk factors, and prerequisite information to
    determine if plan mode should be enabled. Plan mode is recommended for
    complex tasks that require breaking down into smaller subtasks before
    execution.

    Attributes:
        decision_log (list): Log of all plan mode decisions made.
    """

    def __init__(self):
        """Initialize the AutoPlanModeSuggester.

        Sets up an empty decision log for tracking all plan mode decisions
        throughout the session.
        """
        self.decision_log = []

    def should_use_plan_mode(
        self,
        complexity_analysis: Dict,
        structured_prompt: Dict
    ) -> Dict:
        """Determine if plan mode should be used for the current task.

        Analyzes complexity score, risk factors, and task structure to decide
        whether plan mode would be beneficial. Plan mode is recommended for
        tasks with complexity score >= 6.

        Args:
            complexity_analysis (Dict): Analysis object containing complexity
                score, level, factors, and breakdown information.
            structured_prompt (Dict): Structured prompt containing task details,
                entities, operations, success criteria, and examples.

        Returns:
            Dict: Decision object containing:
                - recommended (bool): Whether plan mode is recommended.
                - confidence (float): Confidence level (0-1) for the decision.
                - complexity_score (int): Adjusted complexity score.
                - risk_factors (list): List of identified risk factors.
                - reasoning (str): Human-readable explanation.
                - action (str): Suggested action for the user.

        Examples:
            >>> suggester = AutoPlanModeSuggester()
            >>> result = suggester.should_use_plan_mode(analysis, prompt)
            >>> if result['recommended']:
            ...     print(f"Use plan mode: {result['reasoning']}")
        """
        print("=" * 80)
        print("[TARGET] AUTO PLAN MODE SUGGESTION")
        print("=" * 80)

        # Step 1: Get base complexity
        base_score = complexity_analysis.get('score', 0)
        print(f"\n[CHART] Base Complexity Score: {base_score}")

        # Step 2: Calculate additional risk factors
        risks = self.calculate_risk_factors(structured_prompt, complexity_analysis)
        print(f"\n[WARNING]️  Risk Adjustment: +{risks['score']}")
        if risks['factors']:
            print(f"   Risk Factors:")
            for factor in risks['factors']:
                print(f"   - {factor}")

        # Step 3: Adjust complexity
        adjusted_complexity = self.adjust_complexity_with_risks(
            complexity_analysis.copy(),
            risks
        )
        adjusted_score = adjusted_complexity['score']
        level = adjusted_complexity['level']

        print(f"\n[U+1F4C8] Adjusted Complexity: {adjusted_score} ({level})")

        # Step 4: Make decision
        decision = self.make_decision(adjusted_complexity)

        # Step 5: Format output
        message = self.format_suggestion(decision, adjusted_complexity)
        print(f"\n{message}")

        # Log decision
        self.log_decision(decision, adjusted_complexity)

        return decision

    def calculate_risk_factors(
        self,
        structured_prompt: Dict,
        complexity: Dict
    ) -> Dict:
        """
        Calculate additional risk factors beyond base complexity
        """
        risks = {
            'score': 0,
            'factors': []
        }

        prompt_str = str(structured_prompt).lower()

        # Factor 1: Multi-service impact
        if any(kw in prompt_str for kw in ['multiple services', 'all services', 'cross-service']):
            risks['score'] += 5
            risks['factors'].append('Multi-service impact detected')

        # Factor 2: Database changes
        if any(kw in prompt_str for kw in ['database', 'migration', 'schema', 'alter table']):
            risks['score'] += 5
            risks['factors'].append('Database changes involved')

        # Factor 3: Security/Auth
        if any(kw in prompt_str for kw in ['auth', 'security', 'jwt', 'permission', 'role']):
            risks['score'] += 3
            risks['factors'].append('Security-critical changes')

        # Factor 4: External integrations
        if any(kw in prompt_str for kw in ['integration', 'api call', 'external', 'third-party']):
            risks['score'] += 3
            risks['factors'].append('External integration complexity')

        # Factor 5: No similar examples found
        examples = structured_prompt.get('examples_from_codebase', [])
        if not examples or len(examples) == 0:
            risks['score'] += 4
            risks['factors'].append('No similar examples in codebase')

        # Factor 6: Uncertainties flagged
        metadata = structured_prompt.get('metadata', {})
        if metadata.get('uncertainties') or metadata.get('assumptions'):
            risks['score'] += 2
            risks['factors'].append('Uncertainties identified in requirements')

        # Factor 7: Performance critical
        if any(kw in prompt_str for kw in ['performance', 'optimize', 'scalability']):
            risks['score'] += 2
            risks['factors'].append('Performance-critical implementation')

        # Factor 8: Breaking changes
        if any(kw in prompt_str for kw in ['breaking', 'major change', 'refactor']):
            risks['score'] += 4
            risks['factors'].append('Potential breaking changes')

        # Factor 9: UI/Dashboard complexity
        if any(kw in prompt_str for kw in ['dashboard', 'admin panel', 'ui overlapping', 'layout', 'responsive']):
            risks['score'] += 3
            risks['factors'].append('UI/Dashboard complexity detected')

        # Factor 10: Frontend complexity
        if any(kw in prompt_str for kw in ['react', 'angular', 'vue', 'state management', 'components']):
            risks['score'] += 2
            risks['factors'].append('Frontend framework complexity')

        # Factor 11: Multiple UI fixes
        if any(kw in prompt_str for kw in ['multiple', 'several', 'many']) and any(kw in prompt_str for kw in ['fix', 'issue', 'problem']):
            risks['score'] += 2
            risks['factors'].append('Multiple issues to fix')

        return risks

    def adjust_complexity_with_risks(
        self,
        complexity: Dict,
        risks: Dict
    ) -> Dict:
        """
        Adjust complexity score based on risk factors
        """
        original_score = complexity['score']
        risk_score = risks['score']
        adjusted_score = original_score + risk_score

        complexity['original_score'] = original_score
        complexity['risk_adjustment'] = risk_score
        complexity['score'] = adjusted_score
        complexity['level'] = self.get_complexity_level(adjusted_score)
        complexity['risk_factors'] = risks['factors']

        return complexity

    def get_complexity_level(self, score: int) -> str:
        """Get complexity level from score"""
        if score < 5:
            return 'SIMPLE'
        elif score < 10:
            return 'MODERATE'
        elif score < 20:
            return 'COMPLEX'
        else:
            return 'VERY_COMPLEX'

    def make_decision(self, complexity: Dict) -> Dict:
        """
        Make plan mode decision based on complexity
        """
        score = complexity.get('score', 0)
        level = complexity.get('level', 'SIMPLE')

        decision = {
            'score': score,
            'level': level,
            'plan_mode_required': False,
            'plan_mode_recommended': False,
            'plan_mode_optional': False,
            'should_ask_user': False,
            'auto_enter': False,
            'reasoning': '',
            'benefits': [],
            'risks_without_planning': [],
            'recommendation': ''
        }

        if score < 5:
            # SIMPLE
            decision['recommendation'] = 'NO_PLAN_MODE'
            decision['reasoning'] = 'Task is straightforward, direct execution is efficient'

        elif score < 10:
            # MODERATE - RECOMMEND-THEN-ASK pattern
            # Analyze signals to form a recommendation, then ask user to confirm
            decision['plan_mode_optional'] = True
            decision['should_ask_user'] = True
            decision['recommendation'] = 'RECOMMEND_THEN_ASK'
            decision['recommend_plan'] = score >= 8  # 8-9 lean toward plan, 5-7 lean toward direct
            if score >= 8:
                decision['reasoning'] = 'Task leans complex (score 8-9). I recommend plan mode - multiple concerns detected.'
            elif score >= 6:
                decision['reasoning'] = 'Task is moderate (score 6-7). I recommend direct proceed - standard patterns apply.'
            else:
                decision['reasoning'] = 'Task is low-moderate (score 5). I recommend direct proceed - straightforward execution.'
            decision['benefits'] = [
                'Clearer implementation strategy',
                'Upfront identification of potential issues'
            ]
            decision['recommendation_text'] = (
                'I recommend plan mode' if score >= 8
                else 'I recommend proceeding directly'
            )

        elif score < 20:
            # COMPLEX
            decision['plan_mode_recommended'] = True
            decision['should_ask_user'] = True
            decision['recommendation'] = 'RECOMMENDED'
            decision['reasoning'] = 'Task complexity warrants upfront planning'
            decision['benefits'] = [
                'Design implementation strategy before coding',
                'Identify architectural issues early',
                'Ensure alignment with existing patterns',
                'Reduce risk of rework',
                'Better quality outcome'
            ]
            decision['risks_without_planning'] = [
                'May choose suboptimal approach',
                'Could miss important dependencies',
                'Higher chance of rework',
                'Potential architectural misalignment'
            ]

        else:
            # VERY COMPLEX
            decision['plan_mode_required'] = True
            decision['auto_enter'] = True
            decision['recommendation'] = 'REQUIRED'
            decision['reasoning'] = 'Task is too complex to execute safely without planning'
            decision['benefits'] = [
                'CRITICAL: Prevents incorrect architectural approach',
                'CRITICAL: Identifies all cross-service impacts',
                'CRITICAL: Ensures thorough dependency analysis',
                'CRITICAL: Significantly reduces rework risk'
            ]
            decision['risks_without_planning'] = [
                '[RED] HIGH: Wrong architectural decisions',
                '[RED] HIGH: Missed critical dependencies',
                '[RED] HIGH: Breaking changes to other services',
                '[RED] HIGH: Major rework required',
                '[RED] HIGH: Production issues'
            ]

        return decision

    def format_suggestion(self, decision: Dict, complexity: Dict) -> str:
        """
        Format the suggestion message
        """
        score = decision['score']
        level = decision['level']

        output = f"""
{'='*80}
[CHART] COMPLEXITY ANALYSIS COMPLETE
{'='*80}

Score: {score} ({level})
Tasks: {complexity.get('estimated_tasks', 'Unknown')}
Files: {complexity.get('file_count', 'Unknown')}
Phases: {len(complexity.get('phases', []))}
"""

        if complexity.get('risk_factors'):
            output += f"\nRisk Factors:"
            for factor in complexity['risk_factors']:
                output += f"\n  [WARNING]️  {factor}"

        output += "\n"

        if decision['auto_enter']:
            # VERY COMPLEX
            output += f"""
{'='*80}
[RED] PLAN MODE: REQUIRED (MANDATORY)
{'='*80}

{decision['reasoning']}

Why this is mandatory:
"""
            for risk in decision['risks_without_planning']:
                output += f"{risk}\n"

            output += """
I will now enter plan mode to create a detailed implementation plan.
This will ensure we approach this correctly and avoid costly mistakes.

[CHECK] ACTION: Entering plan mode automatically...
"""

        elif decision['plan_mode_recommended']:
            # COMPLEX
            output += f"""
{'='*80}
[CHECK] PLAN MODE: STRONGLY RECOMMENDED
{'='*80}

{decision['reasoning']}

Benefits of planning:
"""
            for benefit in decision['benefits']:
                output += f"[CHECK] {benefit}\n"

            output += "\nRisks without planning:"
            for risk in decision['risks_without_planning']:
                output += f"[WARNING]️  {risk}\n"

            output += """
[WARNING]️  RECOMMENDATION: Enter plan mode (STRONGLY SUGGESTED)

Would you like me to enter plan mode?
- Yes: I'll create a detailed plan for your approval (Recommended)
- No: I'll proceed directly (higher risk, not recommended)
"""

        elif decision['plan_mode_optional']:
            # MODERATE
            output += f"""
{'='*80}
[WARNING]️  PLAN MODE: OPTIONAL
{'='*80}

{decision['reasoning']}

Option 1 (Recommended): Proceed directly
- Can execute using standard patterns
- Estimated time: Faster
- Risk: Low

Option 2: Enter plan mode
- Create detailed implementation plan
- Review approach first
- Estimated time: +5-10 minutes for planning

[BULB] RECOMMENDATION: Option 1 (Proceed directly)
"""

        else:
            # SIMPLE
            output += f"""
{'='*80}
[CHECK] NO PLAN MODE NEEDED
{'='*80}

{decision['reasoning']}

[CHECK] ACTION: Proceeding directly to execution...
"""

        output += f"{'='*80}\n"

        return output

    def log_decision(self, decision: Dict, complexity: Dict):
        """
        Log decision for future learning
        """
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'score': decision['score'],
            'level': decision['level'],
            'recommendation': decision['recommendation'],
            'complexity_details': complexity
        }

        self.decision_log.append(log_entry)


def main():
    """CLI interface - outputs JSON for LangGraph"""
    # Check for --analyze flag (used by LangGraph)
    analyze_mode = "--analyze" in sys.argv

    if analyze_mode:
        # Simplified mode for LangGraph - uses default complexity
        # In real flow, this would read from flow-trace.json
        complexity = {
            'score': 5,  # Default to moderate
            'level': 'MODERATE',
            'estimated_tasks': 2,
            'requires_phases': False
        }
        structured_prompt = {
            'metadata': {'original_request': 'Task'},
            'task_type': 'Unknown',
            'analysis': {}
        }
    elif len(sys.argv) < 2:
        # No arguments - return default
        output = {
            "plan_required": False,
            "reasoning": "Task analysis complete",
            "factors": []
        }
        print(json.dumps(output))
        sys.exit(0)
    else:
        # Load complexity analysis (can be number or JSON file)
        complexity_arg = sys.argv[1]
        try:
            # Try as a number first
            complexity_score = int(complexity_arg)
            complexity = {
                'score': complexity_score,
                'level': 'SIMPLE' if complexity_score < 5 else 'MODERATE' if complexity_score < 10 else 'COMPLEX' if complexity_score < 15 else 'VERY_COMPLEX',
                'estimated_tasks': max(1, complexity_score // 2),
                'requires_phases': complexity_score >= 10
            }
        except ValueError:
            # It's a file path
            try:
                with open(complexity_arg, 'r') as f:
                    complexity = json.load(f)
            except Exception:
                complexity = {
                    'score': 5,
                    'level': 'MODERATE',
                    'estimated_tasks': 2,
                    'requires_phases': False
                }

        # Load structured prompt (can be string or YAML file)
        if len(sys.argv) >= 3:
            prompt_arg = sys.argv[2]
            try:
                # Try to load as file
                with open(prompt_arg, 'r') as f:
                    structured_prompt = yaml.safe_load(f)
            except (FileNotFoundError, OSError, ValueError):
                # It's a string description
                structured_prompt = {
                    'metadata': {'original_request': prompt_arg},
                    'task_type': 'Unknown',
                    'analysis': {}
                }
        else:
            # No prompt provided, use minimal
            structured_prompt = {
                'metadata': {'original_request': 'Task'},
                'task_type': 'Unknown',
                'analysis': {}
            }

    # Get score and task count
    score = complexity.get('score', 5)
    estimated_tasks = complexity.get('estimated_tasks', 1)

    # Determine if plan is required
    plan_required = (score >= 6) or (estimated_tasks > 2)

    # Build factors list
    factors = []
    if score >= 6:
        factors.append(f"complexity >= 6 (score: {score})")
    if estimated_tasks > 2:
        factors.append(f"multiple sub-tasks ({estimated_tasks} tasks)")

    # Reasoning
    if plan_required:
        if score >= 6 and estimated_tasks > 2:
            reasoning = f"Complex task with multiple sub-tasks (complexity: {score}, tasks: {estimated_tasks}) requires planning"
        elif score >= 6:
            reasoning = f"High complexity score ({score}) warrants planning before execution"
        else:
            reasoning = f"Multiple sub-tasks ({estimated_tasks}) require coordinated planning"
    else:
        reasoning = "Task complexity allows direct execution"

    # Build output
    output = {
        "plan_required": plan_required,
        "reasoning": reasoning,
        "factors": factors,
        "complexity_score": score,
        "estimated_tasks": estimated_tasks
    }

    # Output as JSON only (no human-readable output in analyze mode)
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
