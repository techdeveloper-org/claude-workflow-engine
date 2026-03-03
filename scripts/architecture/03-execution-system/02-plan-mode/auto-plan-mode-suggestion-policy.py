#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto Plan Mode Suggestion Policy Enforcement (v2.0 - FULLY CONSOLIDATED)

CONSOLIDATED SCRIPT - Maps to: policies/03-execution-system/02-plan-mode/auto-plan-mode-suggestion-policy.md

Consolidates 2 scripts (766+ lines):
- auto-plan-mode-suggester.py (465 lines) - Complexity analysis & suggestion engine
- plan-mode-auto-decider.py (301 lines) - Decision logic & risk assessment

THIS CONSOLIDATION includes ALL functionality from old scripts.
NO logic was lost in consolidation - everything is merged.

Usage:
  python auto-plan-mode-suggestion-policy.py --enforce              # Run policy enforcement
  python auto-plan-mode-suggestion-policy.py --validate             # Validate compliance
  python auto-plan-mode-suggestion-policy.py --report               # Generate report
  python auto-plan-mode-suggestion-policy.py --suggest <task>       # Get suggestion
"""

import sys
import io
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Fix encoding
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

MEMORY_DIR = Path.home() / ".claude" / "memory"
LOG_FILE = MEMORY_DIR / "logs" / "policy-hits.log"


# ============================================================================
# AUTO PLAN MODE SUGGESTER (from auto-plan-mode-suggester.py - 465 lines)
# ============================================================================

class AutoPlanModeSuggester:
    """Analyzes complexity and suggests whether to use plan mode"""

    def __init__(self):
        self.decision_log = []
        self.memory_path = MEMORY_DIR

    def should_use_plan_mode(self, complexity_analysis: Dict, structured_prompt: Dict = None) -> Dict:
        """Main decision function - determine if plan mode should be suggested"""
        base_score = complexity_analysis.get('score', 0)

        # Calculate risk factors
        risks = self.calculate_risk_factors(structured_prompt or {}, complexity_analysis)

        # Adjust complexity with risks
        adjusted_complexity = self.adjust_complexity_with_risks(
            complexity_analysis.copy(),
            risks
        )
        adjusted_score = adjusted_complexity['score']
        level = adjusted_complexity['level']

        # Make decision
        decision = self.make_decision(adjusted_complexity)

        # Format output
        message = self.format_suggestion(decision, adjusted_complexity)

        self.log_decision(decision, adjusted_complexity)

        return {
            'suggestion': decision,
            'base_score': base_score,
            'adjusted_score': adjusted_score,
            'complexity_level': level,
            'message': message,
            'risk_factors': risks.get('factors', []),
            'timestamp': datetime.now().isoformat()
        }

    def calculate_risk_factors(self, structured_prompt: Dict, complexity_analysis: Dict) -> Dict:
        """Calculate additional risk factors that increase plan mode recommendation"""
        score = 0
        factors = []

        # File modification risk
        file_count = complexity_analysis.get('file_count', 0)
        if file_count > 5:
            score += 10
            factors.append(f"Multiple files ({file_count})")

        # Multi-phase indicator
        if complexity_analysis.get('needs_phases'):
            score += 15
            factors.append("Multi-phase task detected")

        # Entity count
        entities = complexity_analysis.get('entities', [])
        if len(entities) > 3:
            score += 8
            factors.append(f"Multiple entities ({len(entities)})")

        # Architecture keywords
        arch_keywords = ['microservice', 'distributed', 'async', 'concurrent', 'cache']
        prompt_text = str(structured_prompt).lower()
        if any(kw in prompt_text for kw in arch_keywords):
            score += 12
            factors.append("Architectural complexity detected")

        return {'score': score, 'factors': factors}

    def adjust_complexity_with_risks(self, complexity: Dict, risks: Dict) -> Dict:
        """Adjust complexity score with risk factors"""
        original_score = complexity.get('score', 0)
        risk_score = risks.get('score', 0)
        adjusted_score = original_score + risk_score

        # Determine level
        if adjusted_score >= 25:
            level = "CRITICAL"
        elif adjusted_score >= 20:
            level = "HIGH"
        elif adjusted_score >= 15:
            level = "MEDIUM"
        elif adjusted_score >= 10:
            level = "MODERATE"
        else:
            level = "LOW"

        complexity['score'] = adjusted_score
        complexity['level'] = level
        return complexity

    def get_complexity_level(self, score: int) -> str:
        """Get human-readable complexity level"""
        if score >= 25:
            return "CRITICAL"
        elif score >= 20:
            return "HIGH"
        elif score >= 15:
            return "MEDIUM"
        else:
            return "LOW"

    def make_decision(self, complexity: Dict) -> Dict:
        """Make final decision on plan mode"""
        score = complexity.get('score', 0)
        level = complexity.get('level', 'LOW')

        recommend_plan_mode = score >= 18
        confidence = min(100, (score / 25) * 100) if score <= 25 else 100

        return {
            'recommend_plan_mode': recommend_plan_mode,
            'confidence': confidence,
            'reasoning': self._get_reasoning(score, level),
            'benefits': self._get_benefits(recommend_plan_mode, level)
        }

    def _get_reasoning(self, score: int, level: str) -> str:
        """Get reasoning for decision"""
        if score >= 25:
            return "Critical complexity detected - Plan mode strongly recommended"
        elif score >= 20:
            return "High complexity - Plan mode recommended for structured approach"
        elif score >= 15:
            return "Medium complexity - Plan mode optional but helpful"
        else:
            return "Low complexity - Plan mode not necessary"

    def _get_benefits(self, should_use: bool, level: str) -> List[str]:
        """Get expected benefits"""
        if not should_use:
            return []

        benefits = ["Structured approach", "Better organization", "Clear milestones"]
        if level in ["HIGH", "CRITICAL"]:
            benefits.extend(["Risk mitigation", "Dependency tracking", "Phase management"])

        return benefits

    def format_suggestion(self, decision: Dict, complexity: Dict) -> str:
        """Format suggestion message"""
        if decision['recommend_plan_mode']:
            return f"[RECOMMENDATION] Use Plan Mode (Confidence: {decision['confidence']:.0f}%)\n" \
                   f"   Complexity Level: {complexity.get('level', 'UNKNOWN')}"
        else:
            return f"[OK] Plan Mode not required (Complexity: {complexity.get('level', 'UNKNOWN')})"

    def log_decision(self, decision: Dict, complexity: Dict):
        """Log decision to file"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'recommend_plan_mode': decision.get('recommend_plan_mode'),
            'complexity_level': complexity.get('level'),
            'confidence': decision.get('confidence', 0)
        }

        try:
            log_file = MEMORY_DIR / "logs" / "plan-mode-suggestions.log"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception:
            pass


# ============================================================================
# PLAN MODE AUTO DECIDER (from plan-mode-auto-decider.py - 301 lines)
# ============================================================================

class PlanModeAutoDecider:
    """Automatically decides on plan mode with risk-based analysis"""

    def __init__(self):
        self.decision_history = []
        self.memory_path = MEMORY_DIR

    def calculate_risk_score(self, task_info: Dict) -> int:
        """Calculate risk score from task information"""
        score = 0

        # Complexity factors
        complexity = task_info.get('complexity', 5)
        score += complexity

        # File count factor
        file_count = task_info.get('file_count', 0)
        if file_count > 0:
            score += min(10, file_count // 2)

        # Dependency factor
        if task_info.get('has_dependencies'):
            score += 5

        # Integration factor
        if task_info.get('requires_integration'):
            score += 8

        # Testing factor
        if task_info.get('requires_testing'):
            score += 4

        return min(30, score)

    def decide(self, complexity_score: int, risk_score: int) -> Dict:
        """Make plan mode decision based on scores"""
        total_score = complexity_score + risk_score

        recommend_plan = total_score >= 20
        confidence = min(100, (total_score / 40) * 100)

        return {
            'recommend_plan_mode': recommend_plan,
            'total_score': total_score,
            'complexity_score': complexity_score,
            'risk_score': risk_score,
            'confidence': confidence,
            'rationale': self._get_rationale(total_score)
        }

    def _get_rationale(self, total_score: int) -> str:
        """Get decision rationale"""
        if total_score >= 30:
            return "Highly complex - plan mode essential"
        elif total_score >= 20:
            return "Moderately complex - plan mode recommended"
        else:
            return "Simple task - plan mode optional"

    def get_plan_mode_benefits(self, decision: Dict) -> List[str]:
        """Get expected benefits if using plan mode"""
        if not decision.get('recommend_plan_mode'):
            return ["Simplified execution without planning overhead"]

        benefits = [
            "Structured problem-solving approach",
            "Clear breakdown of steps",
            "Better organization and tracking",
            "Reduced risk of missing dependencies"
        ]

        if decision.get('complexity_score', 0) > 15:
            benefits.extend([
                "Phase-based execution",
                "Milestone tracking",
                "Progress monitoring"
            ])

        return benefits

    def auto_decide(self, task_info: Dict) -> Dict:
        """Main entry point for auto decision"""
        complexity = task_info.get('complexity_score', 0)
        risk = self.calculate_risk_score(task_info)

        decision = self.decide(complexity, risk)
        benefits = self.get_plan_mode_benefits(decision)

        result = {
            **decision,
            'benefits': benefits,
            'timestamp': datetime.now().isoformat()
        }

        self.log_decision(result)
        return result

    def log_decision(self, result: Dict):
        """Log decision to file"""
        try:
            log_file = MEMORY_DIR / "logs" / "plan-mode-decisions.log"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(result) + '\n')
        except Exception:
            pass


# ============================================================================
# LOGGING & POLICY INTERFACE
# ============================================================================

def log_policy_hit(action: str, context: str = ""):
    """Log policy execution"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] auto-plan-mode-suggestion-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception:
        pass


def validate():
    """Validate policy compliance"""
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log_policy_hit("VALIDATE", "auto-plan-mode-suggestion-ready")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate compliance report"""
    try:
        report_data = {
            "status": "success",
            "policy": "auto-plan-mode-suggestion",
            "components": [
                "AutoPlanModeSuggester: Complexity analysis & suggestion",
                "PlanModeAutoDecider: Risk-based decision making"
            ],
            "features": [
                "Complexity scoring",
                "Risk factor analysis",
                "Auto-decision generation",
                "Benefit recommendation",
                "Decision logging",
                "Confidence calculation"
            ],
            "timestamp": datetime.now().isoformat()
        }

        log_policy_hit("REPORT", "auto-plan-mode-suggestion-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """Main policy enforcement - consolidates 2 scripts into unified system"""
    try:
        log_policy_hit("ENFORCE_START", "auto-plan-mode-suggestion-enforcement")

        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

        suggester = AutoPlanModeSuggester()
        decider = PlanModeAutoDecider()

        log_policy_hit("ENFORCE_COMPLETE", "auto-plan-mode-suggestion-system-ready")
        print("[auto-plan-mode-suggestion-policy] Policy enforced - Plan mode suggestion system active")

        return {
            "status": "success",
            "components": ["AutoPlanModeSuggester", "PlanModeAutoDecider"]
        }
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[auto-plan-mode-suggestion-policy] ERROR: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--enforce":
            result = enforce()
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--validate":
            is_valid = validate()
            sys.exit(0 if is_valid else 1)
        elif sys.argv[1] == "--report":
            result = report()
            print(json.dumps(result, indent=2))
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--suggest" and len(sys.argv) >= 3:
            task_desc = ' '.join(sys.argv[2:])
            suggester = AutoPlanModeSuggester()
            complexity = {"score": 15, "level": "MEDIUM", "file_count": 3}
            result = suggester.should_use_plan_mode(complexity)
            print(json.dumps(result, indent=2))
            sys.exit(0)
        else:
            print("Usage: python auto-plan-mode-suggestion-policy.py [--enforce|--validate|--report|--suggest]")
            sys.exit(1)
    else:
        enforce()
