# 🤖 Intelligent Model Selection Policy

**VERSION:** 3.0.0 (ENHANCED - Updated Model Tiers)
**CREATED:** 2026-02-16
**UPDATED:** 2026-02-28
**PRIORITY:** 🔴 CRITICAL - STEP 3 (After Plan Mode Decision)
**STATUS:** 🟢 ACTIVE

---

## 📋 POLICY OVERVIEW

**MANDATORY: After Steps 0, 1, 2 complete, intelligently select model based on:**

1. ✅ **Complexity Score** (from Step 1)
2. ✅ **Task Type** (from Step 0)
3. ✅ **Plan Mode Decision** (from Step 2)
4. ✅ **Phase Type** (if in phases)
5. ✅ **Token Efficiency** (cost optimization)

---

## 🚨 EXECUTION ORDER

```
Step 0: Prompt Generation ✅
Step 1: Task Breakdown ✅
    → Complexity: Known
Step 2: Plan Mode Suggestion ✅
    → Plan mode decision: Known
        ↓
🔴 STEP 3: INTELLIGENT MODEL SELECTION (THIS POLICY)
        ↓
    Analyze All Context:
    - Complexity score
    - Task type
    - Plan mode or direct execution?
    - Phase type (if applicable)
    - Expected duration
        ↓
    🎯 Decision Matrix:
    ┌──────────────────────────────────────┐
    │  PLAN MODE → OPUS                    │
    │  (Always use Opus for planning)      │
    ├──────────────────────────────────────┤
    │  VERY_COMPLEX + Execution → SONNET   │
    │  (Complex execution needs Sonnet)    │
    ├──────────────────────────────────────┤
    │  COMPLEX + Execution → SONNET        │
    │  (Standard for complex work)         │
    ├──────────────────────────────────────┤
    │  MODERATE + Code → SONNET            │
    │  MODERATE + Read/Search → HAIKU      │
    ├──────────────────────────────────────┤
    │  SIMPLE → HAIKU                      │
    │  (Fast and efficient)                │
    └──────────────────────────────────────┘
        ↓
Step 4: Context Check
Step 5: Execution (using selected model)
```

---

## 🎯 MODEL SELECTION DECISION MATRIX

### **PRIMARY RULE: Plan Mode Always Uses OPUS**

```python
if plan_mode_decision['auto_enter'] or user_chose_plan_mode:
    selected_model = 'OPUS'
    reasoning = 'Plan mode requires deep analysis and architectural thinking'
```

**Why OPUS for plan mode:**
- 🧠 Complex architectural reasoning
- 🔍 Deep codebase exploration
- 📋 Comprehensive planning
- 🎯 Critical decision making
- ⚠️ High stakes (wrong plan = wasted time)

---

### **EXECUTION MODE: Complexity-Based Selection**

```
┌─────────────────────────────────────────────────────────────┐
│                    COMPLEXITY MATRIX                         │
├──────────────┬─────────────┬────────────────────────────────┤
│ Complexity   │ Score       │ Model Selection                │
├──────────────┼─────────────┼────────────────────────────────┤
│ SIMPLE       │ 0-4         │ HAIKU                          │
│              │             │ - Fast execution               │
│              │             │ - Low cost                     │
│              │             │ - Simple patterns              │
├──────────────┼─────────────┼────────────────────────────────┤
│ MODERATE     │ 5-9         │ HAIKU or SONNET (task-based)   │
│              │             │ - Read/Search → HAIKU          │
│              │             │ - Implementation → SONNET      │
├──────────────┼─────────────┼────────────────────────────────┤
│ COMPLEX      │ 10-19       │ SONNET                         │
│              │             │ - Complex logic needed         │
│              │             │ - Multi-file coordination      │
│              │             │ - Business logic               │
├──────────────┼─────────────┼────────────────────────────────┤
│ VERY_COMPLEX │ 20+         │ SONNET (+ OPUS for planning)   │
│              │             │ - Execution: SONNET            │
│              │             │ - Planning: OPUS (if plan mode)│
└──────────────┴─────────────┴────────────────────────────────┘
```

---

### **TASK TYPE OVERRIDES**

**Some task types ALWAYS need specific models regardless of complexity:**

```python
task_type_models = {
    # Architecture & Design → OPUS
    'Architecture Design': 'OPUS',
    'System Design': 'OPUS',
    'Migration Planning': 'OPUS',
    'Refactoring Strategy': 'OPUS',

    # Implementation → SONNET
    'API Creation': 'SONNET',
    'Service Implementation': 'SONNET',
    'Business Logic': 'SONNET',
    'Integration': 'SONNET',
    'Authentication': 'SONNET',
    'Authorization': 'SONNET',

    # Simple Operations → HAIKU
    'Bug Fix': 'HAIKU',  # Unless complex
    'Documentation': 'HAIKU',
    'Configuration': 'HAIKU',
    'Constant Addition': 'HAIKU',
    'Simple CRUD': 'HAIKU',  # Only if truly simple

    # Search & Analysis → HAIKU
    'Code Search': 'HAIKU',
    'File Reading': 'HAIKU',
    'Status Check': 'HAIKU',
    'Verification': 'HAIKU'
}
```

---

### **PHASE-BASED SELECTION**

**Different phases may need different models:**

```python
phase_model_mapping = {
    # Foundation phase
    'Foundation': {
        'default': 'HAIKU',  # Entity, Repository are simple
        'if_complex': 'SONNET'  # If custom logic needed
    },

    # Business Logic phase
    'Business Logic': {
        'default': 'SONNET',  # Always needs reasoning
        'if_simple': 'HAIKU'  # Only if trivial logic
    },

    # API Layer phase
    'API Layer': {
        'default': 'SONNET',  # REST endpoints need care
        'if_standard': 'HAIKU'  # If following exact pattern
    },

    # Configuration phase
    'Configuration': {
        'default': 'HAIKU',  # Config is usually simple
        'if_complex': 'SONNET'  # If custom config logic
    },

    # Testing & Validation phase
    'Testing': {
        'default': 'HAIKU',  # Running tests is simple
        'if_debugging': 'SONNET'  # If fixing test failures
    }
}
```

---

## 🧮 ENHANCED SELECTION ALGORITHM

```python
def select_model(
    complexity: Dict,
    task_type: str,
    plan_mode_decision: Dict,
    current_phase: str = None,
    task_details: Dict = None
) -> Dict:
    """
    Intelligent model selection based on all available context
    """

    selection = {
        'model': None,
        'reasoning': [],
        'cost_estimate': None,
        'token_estimate': None,
        'alternative': None
    }

    # RULE 1: Plan mode ALWAYS uses OPUS
    if plan_mode_decision.get('auto_enter') or plan_mode_decision.get('in_plan_mode'):
        selection['model'] = 'OPUS'
        selection['reasoning'].append('Plan mode requires OPUS for deep analysis')
        return selection

    # RULE 2: Task type override
    if task_type in TASK_TYPE_MODELS:
        override_model = TASK_TYPE_MODELS[task_type]

        # Check if complexity justifies override
        complexity_score = complexity.get('score', 0)

        if override_model == 'OPUS':
            # Always use OPUS for architecture tasks
            selection['model'] = 'OPUS'
            selection['reasoning'].append(f'Task type "{task_type}" requires OPUS')
            return selection

        elif override_model == 'HAIKU':
            # Use HAIKU unless complexity is high
            if complexity_score < 10:
                selection['model'] = 'HAIKU'
                selection['reasoning'].append(f'Task type "{task_type}" + low complexity → HAIKU')
                return selection
            else:
                # Complexity overrides task type
                selection['reasoning'].append(f'Task type suggests HAIKU but complexity is high')
                # Fall through to complexity-based selection

    # RULE 3: Complexity-based selection
    complexity_score = complexity.get('score', 0)
    complexity_level = complexity.get('level', 'SIMPLE')

    if complexity_score < 5:
        # SIMPLE
        selection['model'] = 'HAIKU'
        selection['reasoning'].append(f'Low complexity ({complexity_score}) → HAIKU')

    elif complexity_score < 10:
        # MODERATE - depends on task type
        if task_type in ['API Creation', 'Business Logic', 'Integration']:
            selection['model'] = 'SONNET'
            selection['reasoning'].append(f'Moderate complexity + code task → SONNET')
        else:
            selection['model'] = 'HAIKU'
            selection['reasoning'].append(f'Moderate complexity + simple task → HAIKU')
            selection['alternative'] = {
                'model': 'SONNET',
                'reason': 'Use if task proves more complex than expected'
            }

    elif complexity_score < 20:
        # COMPLEX
        selection['model'] = 'SONNET'
        selection['reasoning'].append(f'High complexity ({complexity_score}) → SONNET')

    else:
        # VERY_COMPLEX
        selection['model'] = 'SONNET'
        selection['reasoning'].append(f'Very high complexity ({complexity_score}) → SONNET')
        selection['reasoning'].append('Consider OPUS for initial planning if not done')

    # RULE 4: Phase-specific adjustments
    if current_phase and current_phase in PHASE_MODEL_MAPPING:
        phase_config = PHASE_MODEL_MAPPING[current_phase]

        # Check if phase suggests different model
        phase_model = phase_config.get('default')

        if phase_model != selection['model']:
            selection['reasoning'].append(
                f'Phase "{current_phase}" typically uses {phase_model}'
            )
            # Keep current selection but note alternative

    # RULE 5: Risk-based adjustments
    risk_factors = complexity.get('risk_factors', [])

    if any('security' in str(factor).lower() for factor in risk_factors):
        if selection['model'] == 'HAIKU':
            selection['model'] = 'SONNET'
            selection['reasoning'].append('Security-critical: upgraded to SONNET')

    if any('multi-service' in str(factor).lower() for factor in risk_factors):
        if selection['model'] == 'HAIKU':
            selection['model'] = 'SONNET'
            selection['reasoning'].append('Multi-service impact: upgraded to SONNET')

    # Add cost and token estimates
    selection['cost_estimate'] = estimate_cost(
        selection['model'],
        complexity.get('estimated_tasks', 5)
    )
    selection['token_estimate'] = estimate_tokens(
        selection['model'],
        task_details
    )

    return selection


def estimate_cost(model: str, num_tasks: int) -> Dict:
    """
    Estimate cost based on model and task count
    """
    # Per million tokens (updated 2026-02-28)
    # Opus 4.6: $5 input / $25 output
    # Sonnet 4.6: $3 input / $15 output
    # Haiku 4.5: $1 input / $5 output
    costs = {
        'HAIKU': {'input': 1.00, 'output': 5.00},
        'SONNET': {'input': 3.00, 'output': 15.00},
        'OPUS': {'input': 5.00, 'output': 25.00}
    }

    # Estimate tokens per task
    tokens_per_task = {
        'HAIKU': 2000,    # Simple, fast
        'SONNET': 5000,   # Moderate reasoning
        'OPUS': 10000     # Deep analysis
    }

    model_cost = costs[model]
    model_tokens = tokens_per_task[model]

    total_tokens = model_tokens * num_tasks
    estimated_cost = (total_tokens / 1_000_000) * (
        model_cost['input'] + model_cost['output']
    )

    return {
        'model': model,
        'estimated_tokens': total_tokens,
        'estimated_cost_usd': round(estimated_cost, 4),
        'num_tasks': num_tasks
    }
```

---

## 📊 DECISION EXAMPLES

### **Example 1: Simple Bug Fix**

```python
Input:
    complexity = {
        'score': 2,
        'level': 'SIMPLE',
        'estimated_tasks': 1
    }
    task_type = 'Bug Fix'
    plan_mode_decision = {'auto_enter': False}

Output:
    ✅ SELECTED MODEL: HAIKU

    Reasoning:
    - Low complexity (2) → HAIKU
    - Task type "Bug Fix" → HAIKU
    - No plan mode needed

    Cost Estimate:
    - Tokens: ~2,000
    - Cost: ~$0.0035
    - Duration: ~2 minutes
```

---

### **Example 2: Product API Creation**

```python
Input:
    complexity = {
        'score': 18,
        'level': 'COMPLEX',
        'estimated_tasks': 13
    }
    task_type = 'API Creation'
    plan_mode_decision = {'auto_enter': False}

Output:
    ✅ SELECTED MODEL: SONNET

    Reasoning:
    - High complexity (18) → SONNET
    - Task type "API Creation" → SONNET
    - Multiple files requiring coordination
    - Business logic implementation

    Cost Estimate:
    - Tokens: ~65,000
    - Cost: ~$1.17
    - Duration: ~15 minutes
```

---

### **Example 3: JWT Auth Across Services**

```python
Input:
    complexity = {
        'score': 34,
        'level': 'VERY_COMPLEX',
        'estimated_tasks': 25,
        'risk_factors': [
            'Multi-service impact',
            'Security-critical'
        ]
    }
    task_type = 'Authentication'
    plan_mode_decision = {
        'auto_enter': True,
        'recommendation': 'REQUIRED'
    }

Output:
    ✅ SELECTED MODEL: OPUS (for planning)

    Reasoning:
    - Plan mode required → OPUS
    - Very high complexity (34)
    - Security-critical task
    - Multi-service coordination needed
    - Architectural decisions required

    After Planning (Execution):
    ✅ SWITCH TO: SONNET

    Reasoning:
    - Plan approved, now implementing
    - Complex execution requires SONNET
    - Following approved plan

    Cost Estimate (Planning):
    - Tokens: ~250,000
    - Cost: ~$22.50
    - Duration: ~30 minutes (planning)

    Cost Estimate (Execution):
    - Tokens: ~125,000
    - Cost: ~$2.25
    - Duration: ~45 minutes (implementation)
```

---

### **Example 4: Moderate Config Task**

```python
Input:
    complexity = {
        'score': 7,
        'level': 'MODERATE',
        'estimated_tasks': 3
    }
    task_type = 'Configuration'
    plan_mode_decision = {'auto_enter': False}

Output:
    ✅ SELECTED MODEL: HAIKU

    Reasoning:
    - Moderate complexity (7)
    - Task type "Configuration" → HAIKU
    - Standard config patterns available
    - Low risk task

    Alternative:
    ⚠️  SONNET if configuration proves complex

    Cost Estimate:
    - Tokens: ~6,000
    - Cost: ~$0.01
    - Duration: ~3 minutes
```

---

## 🔄 DYNAMIC MODEL SWITCHING

**During execution, model can be upgraded if needed:**

```python
def should_upgrade_model(
    current_model: str,
    encountered_complexity: str,
    errors_count: int
) -> Dict:
    """
    Determine if model should be upgraded during execution
    """

    if current_model == 'HAIKU':
        # Upgrade from HAIKU to SONNET
        if encountered_complexity in ['HIGH', 'VERY_HIGH']:
            return {
                'upgrade': True,
                'new_model': 'SONNET',
                'reason': 'Task proved more complex than estimated'
            }

        if errors_count >= 3:
            return {
                'upgrade': True,
                'new_model': 'SONNET',
                'reason': 'Multiple errors indicate need for better reasoning'
            }

    elif current_model == 'SONNET':
        # Upgrade from SONNET to OPUS (rare)
        if encountered_complexity == 'ARCHITECTURAL':
            return {
                'upgrade': True,
                'new_model': 'OPUS',
                'reason': 'Architectural decisions required'
            }

    return {'upgrade': False}
```

**Upgrade Triggers:**
- ✅ Build fails 3+ times → Upgrade
- ✅ Tests fail repeatedly → Upgrade
- ✅ Architectural issues discovered → Upgrade to OPUS
- ✅ Security vulnerabilities found → Upgrade
- ✅ Performance issues → Upgrade

---

## 📊 MODEL CHARACTERISTICS

### **HAIKU 4.5 - "The Executor" (claude-haiku-4-5-20251001)**

| Attribute | Value |
|-----------|-------|
| Intelligence | Near-Frontier |
| Speed | Fastest (Instant) |
| Cost (Input/Output) | $1 / $5 per MTok |
| Context Window | 200K tokens |

**Best For:**
- Real-time customer support and chatbot tasks
- Bulk data classification and labeling
- Simple code generation and boilerplate
- Sub-agent tasks (where a larger model plans and Haiku executes)
- File reading and searching
- Status checks and verification
- Simple bug fixes
- Standard CRUD (when truly simple)
- Configuration (standard patterns)

**Characteristics:**
- ⚡ Fastest response time (instant)
- 💰 Lowest cost (~5x cheaper than Sonnet)
- 🎯 Near-frontier intelligence for simple patterns
- ⚠️ Limited complex reasoning

**When NOT to use:**
- Complex business logic
- Architectural decisions
- Security-critical code
- Multi-service coordination
- Novel problem solving

---

### **SONNET 4.6 - "The Workhorse" (claude-sonnet-4-6)**

| Attribute | Value |
|-----------|-------|
| Intelligence | Balanced (Strong) |
| Speed | Fast |
| Cost (Input/Output) | $3 / $15 per MTok |
| Context Window | 200K tokens (1M beta) |

**Best For:**
- Standard coding (feature building, unit tests)
- Content creation and technical documentation
- Data analysis and processing
- API implementation and business logic
- Service layer code and controller logic
- Integration work and complex CRUD
- Validation logic and error handling
- Testing implementation
- Computer-use tasks

**Characteristics:**
- ⚖️ Best balanced choice for daily assistant use
- 💰 Moderate cost
- 🧠 Strong reasoning ability
- 🎯 Best for most coding tasks (the default for most users)
- 📄 1M token context window (in beta)

**When to use:**
- Any implementation work
- Complex logic needed
- Multi-file coordination
- Standard to complex tasks

**Pro Tip:** Use Sonnet for your main development and only switch to Opus when you hit a logic wall or need a high-level architectural review.

---

### **OPUS 4.6 - "The Strategist" (claude-opus-4-6)**

| Attribute | Value |
|-----------|-------|
| Intelligence | Highest (Frontier) |
| Speed | Moderate |
| Cost (Input/Output) | $5 / $25 per MTok |
| Context Window | 200K tokens (1M beta) |

**Best For:**
- Professional software engineering (multi-file refactoring)
- High-level strategic planning
- Complex financial analysis and legal research
- Architectural design and system planning
- Migration planning and complex refactoring strategy
- Security architecture
- Performance optimization strategy
- **Plan mode (ALWAYS)**

**Characteristics:**
- 🧠 Most "human-like" and nuanced understanding
- 🔍 Catches subtle edge cases that smaller models miss
- 💰 Highest cost (but only ~1.67x Sonnet, not 5x like before)
- ⏱️ Moderate speed (not as slow as previous Opus)

**When to use:**
- Plan mode (mandatory)
- Architecture decisions
- Complex system design
- High-stakes decisions
- Novel problem solving

---

### **COMPARISON SUMMARY TABLE**

| Feature | Opus 4.6 | Sonnet 4.6 | Haiku 4.5 |
|---------|----------|------------|-----------|
| Intelligence | Highest (Frontier) | Balanced (Strong) | Near-Frontier |
| Speed | Moderate | Fast | Fastest (Instant) |
| Cost (Input/Output) | $5 / $25 per MTok | $3 / $15 per MTok | $1 / $5 per MTok |
| Context Window | 200K (1M beta) | 200K (1M beta) | 200K tokens |
| Nickname | "The Strategist" | "The Workhorse" | "The Executor" |
| Best For | Architecture, planning | Daily coding, features | Searches, sub-agents |

---

## 🎯 FINAL SELECTION SUMMARY

```
┌─────────────────────────────────────────────────────────┐
│              MODEL SELECTION FLOWCHART                   │
└─────────────────────────────────────────────────────────┘

Plan Mode?
    │
    ├─ YES → OPUS (mandatory)
    │
    └─ NO → Check Complexity
            │
            ├─ Score 0-4 (SIMPLE)
            │   └─ HAIKU
            │
            ├─ Score 5-9 (MODERATE)
            │   ├─ Code task? → SONNET
            │   └─ Read/Search? → HAIKU
            │
            ├─ Score 10-19 (COMPLEX)
            │   └─ SONNET
            │
            └─ Score 20+ (VERY_COMPLEX)
                ├─ Planning needed? → OPUS
                └─ Execution? → SONNET

Override Checks:
    ├─ Security-critical? → Upgrade to SONNET minimum
    ├─ Multi-service? → Upgrade to SONNET minimum
    ├─ Architecture? → OPUS
    └─ Novel problem? → Upgrade one level
```

---

## 📝 OUTPUT FORMAT

```yaml
model_selection:
  selected_model: "SONNET"
  reasoning:
    - "High complexity (18) requires sophisticated reasoning"
    - "API Creation task type matches SONNET capabilities"
    - "Multiple files require coordination"
    - "Business logic implementation needed"

  alternatives:
    - model: "HAIKU"
      reason: "Could be used if patterns are very standard"
      risk: "May struggle with complex validation logic"

  cost_estimate:
    model: "SONNET"
    estimated_tokens: 65000
    estimated_cost_usd: 1.17
    num_tasks: 13

  confidence: "HIGH"

  dynamic_upgrade:
    enabled: true
    conditions:
      - "Build failures >= 3"
      - "Architectural issues discovered"
      - "Security vulnerabilities found"
    upgrade_to: "OPUS"
```

---

## 🔧 IMPLEMENTATION SCRIPT

**File:** `~/.claude/memory/intelligent-model-selector.py`

```python
#!/usr/bin/env python3
"""
Intelligent Model Selection
Based on complexity, task type, plan mode decision
"""

import json
import yaml
from typing import Dict


class IntelligentModelSelector:
    def __init__(self):
        self.task_type_models = {
            'Architecture Design': 'OPUS',
            'System Design': 'OPUS',
            'Migration Planning': 'OPUS',
            'API Creation': 'SONNET',
            'Authentication': 'SONNET',
            'Business Logic': 'SONNET',
            'Bug Fix': 'HAIKU',
            'Configuration': 'HAIKU',
            'Documentation': 'HAIKU'
        }

    def select_model(
        self,
        complexity: Dict,
        task_type: str,
        plan_mode_decision: Dict
    ) -> Dict:
        """
        Main selection logic
        """
        # Implementation of algorithm above
        pass


def main():
    """CLI interface"""
    import sys

    if len(sys.argv) < 4:
        print("Usage: python intelligent-model-selector.py complexity.json task_type plan_decision.json")
        sys.exit(1)

    # Load inputs
    with open(sys.argv[1], 'r') as f:
        complexity = json.load(f)

    task_type = sys.argv[2]

    with open(sys.argv[3], 'r') as f:
        plan_mode = json.load(f)

    # Select model
    selector = IntelligentModelSelector()
    selection = selector.select_model(complexity, task_type, plan_mode)

    # Output
    print(yaml.dump(selection, default_flow_style=False))


if __name__ == "__main__":
    main()
```

---

**VERSION:** 3.0.0 (ENHANCED - Updated Model Tiers)
**CREATED:** 2026-02-16
**UPDATED:** 2026-02-28
**LOCATION:** `policies/03-execution-system/04-model-selection/intelligent-model-selection-policy.md`
**SCRIPT:** `scripts/architecture/03-execution-system/04-model-selection/intelligent-model-selector.py`
