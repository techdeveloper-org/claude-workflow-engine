"""
Smoke-tests for TASK #4 modules.
Run: python scripts/langgraph_engine/test_task4_modules.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# ---- re-use relative imports by adjusting path ----
sys.path.insert(0, os.path.dirname(__file__) + '/..')

print('=' * 60)
print('TEST 1: plan_decision_rules')
print('=' * 60)
from langgraph_engine.plan_decision_rules import (
    should_plan, evaluate_from_toon, build_fallback_decision
)

# Rule 1: high complexity -> plan required
res, reason = should_plan(7, 'feature')
assert res is True, reason
print(f'  Rule 1 (complexity 7): {reason}')

# Rule 2: architecture always plans
res, reason = should_plan(2, 'architecture')
assert res is True, reason
print(f'  Rule 2 (architecture): {reason}')

# Rule 3: bug_fix + complexity >= 4
res, reason = should_plan(4, 'bug_fix')
assert res is True, reason
print(f'  Rule 3 (bug_fix c=4): {reason}')

# Default: no plan
res, reason = should_plan(3, 'feature')
assert res is False, reason
print(f'  Default (feature c=3): {reason}')

toon = {'complexity_score': 7}
ev = evaluate_from_toon(toon, 'feature')
assert ev['plan_required'] is True
assert ev['risk_level'] == 'high'
print('  evaluate_from_toon() passed')

fb = build_fallback_decision({'complexity_score': 3}, 'fix bug', 'bug_fix', 'ollama timeout')
assert fb['fallback'] is True
assert 'FALLBACK' in fb['reasoning']
print('  build_fallback_decision() passed')


print()
print('=' * 60)
print('TEST 2: plan_convergence')
print('=' * 60)
from langgraph_engine.plan_convergence import (
    assess_plan_quality, check_convergence, run_planning_loop, QUALITY_THRESHOLD
)

good_plan = {
    'plan': 'Implement authentication. 1. Create src/auth.py AuthService class. 2. Update src/routes.py routes.',
    'files_affected': ['src/auth.py', 'src/routes.py'],
    'phases': [{'phase_number': 1, 'title': 'Auth', 'description': 'x',
                'tasks': [], 'files_affected': []}],
    'risks': {'risk_level': 'low'}
}
q = assess_plan_quality(good_plan, 'authentication feature')
print(f'  Good plan quality: {q:.3f}')
assert q > 0.3, f'Expected quality > 0.3, got {q}'

converged, reason = check_convergence(0.90, 0, 3)
assert converged is True
print(f'  check_convergence(0.90): {reason}')

converged, reason = check_convergence(0.50, 2, 3)
assert converged is True
print(f'  check_convergence(max_iter): {reason}')

converged, reason = check_convergence(0.50, 0, 3)
assert converged is False
print(f'  check_convergence(0.50): {reason}')

call_count = [0]
def perfect_generator():
    call_count[0] += 1
    return good_plan

result = run_planning_loop(perfect_generator, 'auth feature', {})
assert result['iterations'] <= 3
print(f'  run_planning_loop() passed (iterations={result["iterations"]}, converged={result["converged"]})')


print()
print('=' * 60)
print('TEST 3: task_validator')
print('=' * 60)
from langgraph_engine.task_validator import validate_breakdown, has_cycle, cycle_detect, validate_feasibility

tasks = [
    {'id': 1, 'name': 'Setup database connection', 'dependencies': []},
    {'id': 2, 'name': 'Implement REST API endpoints', 'dependencies': [1]},
    {'id': 3, 'name': 'Write tests for all endpoints', 'dependencies': [2]},
]
valid, errors = validate_breakdown(tasks, 'setup database implement API tests')
print(f'  Valid tasks: valid={valid}, errors={errors}')
assert valid is True, f'Expected valid=True, got errors={errors}'

cyclic_tasks = [
    {'id': 1, 'name': 'A', 'dependencies': [3]},
    {'id': 2, 'name': 'B', 'dependencies': [1]},
    {'id': 3, 'name': 'C', 'dependencies': [2]},
]
valid, errors = validate_breakdown(cyclic_tasks)
assert valid is False
assert any('Circular' in e for e in errors)
print('  Cycle detection passed')

cycle_found, cycle_path = cycle_detect(cyclic_tasks)
assert cycle_found is True
assert len(cycle_path) >= 2
print(f'  cycle_detect() found path: {cycle_path}')

nameless_tasks = [{'id': 1, 'name': '', 'dependencies': []}]
valid, errors = validate_breakdown(nameless_tasks)
assert valid is False
print('  Feasibility check passed')

feasible, msg = validate_feasibility({'name': 'Setup DB', 'estimated_effort': 'small'}, 500)
assert feasible is True
print(f'  validate_feasibility(small/500): {msg}')

feasible, msg = validate_feasibility({'name': 'Refactor', 'estimated_tokens': 2000}, 500)
assert feasible is False
print(f'  validate_feasibility(2000/500): {msg}')


print()
print('=' * 60)
print('TEST 4: skill_selection_criteria')
print('=' * 60)
from langgraph_engine.skill_selection_criteria import (
    validate_skill, detect_conflicts, build_selection, score_skill
)

task = {'required_capabilities': ['orm', 'jwt']}
skill = {'name': 'flask-backend', 'capabilities': ['orm', 'jwt', 'rest_api']}
ok, msg = validate_skill(task, skill)
assert ok is True, msg
print(f'  validate_skill() PASS: {msg}')

skill_missing = {'name': 'minimal', 'capabilities': ['rest_api']}
ok, msg = validate_skill(task, skill_missing)
assert ok is False
assert 'Missing capability' in msg
print(f'  validate_skill() FAIL: {msg}')

skill1 = {'name': 'flask', 'exclusive': True}
skill2 = {'name': 'django', 'exclusive': True}
conflicts = detect_conflicts([skill1, skill2])
assert len(conflicts) == 1
print(f'  detect_conflicts() found: {conflicts[0]["reason"]}')

no_conflict = [
    {'name': 'flask', 'exclusive': False, 'capabilities': ['rest_api']},
    {'name': 'redis', 'exclusive': False, 'capabilities': ['caching']},
]
assert detect_conflicts(no_conflict) == []
print('  detect_conflicts() no conflict: passed')

candidates = [
    {'name': 'flask', 'capabilities': ['orm', 'jwt', 'rest_api'], 'exclusive': False},
    {'name': 'django', 'capabilities': ['orm', 'rest_api'], 'exclusive': False},
]
selection = build_selection(task, candidates)
assert len(selection['selected']) >= 1
print(f'  build_selection() selected: {[s["name"] for s in selection["selected"]]}')


print()
print('=' * 60)
print('TEST 5: step_validator')
print('=' * 60)
from langgraph_engine.step_validator import StepValidator
sv = StepValidator()

valid, errors = sv.validate_step_1_input({
    'level1_context_toon': {'complexity_score': 5, 'session_id': 'test'},
    'user_requirement': 'do something'
})
assert valid is True, errors
print('  Step 1 input PASS: ok')

valid, errors = sv.validate_step_1_input({})
assert valid is False
print(f'  Step 1 input FAIL: {errors}')

valid, errors = sv.validate_step_1_output({'plan_required': True, 'reasoning': 'complex task'})
assert valid is True, errors
print('  Step 1 output PASS: ok')

valid, errors = sv.validate_step_1_output({'plan_required': 'yes', 'reasoning': ''})
assert valid is False
print(f'  Step 1 output FAIL (type+empty): {errors}')

valid, errors = sv.validate_step_3_output([{'id': 1, 'name': 'Task A', 'dependencies': []}])
assert valid is True
print('  Step 3 output PASS: ok')

valid, errors = sv.validate_step_3_output([])
assert valid is False
print(f'  Step 3 output FAIL empty list: {errors}')

valid, errors = sv.validate_step_14_output({'step14_summary': {'text': 'done'}})
assert valid is True
print('  Step 14 output PASS: ok')

valid, errors = sv.validate_step_14_output({'step14_summary': {}})
assert valid is False
print(f'  Step 14 output FAIL empty: {errors}')

# Test all 14 steps exist
_toon = {'complexity_score': 5, 'session_id': 'test'}
methods = [
    ('validate_step_1_input', {'level1_context_toon': _toon, 'user_requirement': 'x'}),
    ('validate_step_2_input', {'level1_context_toon': _toon, 'user_requirement': 'x', 'step1_plan_required': True}),
    ('validate_step_3_input', {'user_requirement': 'x'}),
    ('validate_step_4_input', {'step3_tasks': [{'id': 1, 'name': 'x'}], 'level1_context_toon': _toon}),
    ('validate_step_5_input', {'step3_tasks': [{'id': 1, 'name': 'x'}]}),
    ('validate_step_6_input', {'step5_skills': ['python-backend']}),
    ('validate_step_7_input', {'user_requirement': 'x', 'step3_tasks': [{'id': 1}]}),
    ('validate_step_8_input', {'user_requirement': 'x'}),
    ('validate_step_9_input', {'step8_issue_id': 'GH-1'}),
    ('validate_step_10_input', {'step9_branch_name': 'feature/x', 'step3_tasks': [{'id': 1}]}),
    ('validate_step_11_input', {'step9_branch_name': 'feature/x', 'step8_issue_id': 'GH-1'}),
    ('validate_step_12_input', {'step8_issue_id': 'GH-1', 'step11_review_passed': True}),
    ('validate_step_13_input', {'step10_modified_files': ['src/a.py']}),
    ('validate_step_14_input', {'level3_status': 'OK'}),
]
for method_name, sample_state in methods:
    method = getattr(sv, method_name)
    valid, errors = method(sample_state)
    print(f'  {method_name}(): valid={valid}')

print()
print('=' * 60)
print('TEST 6: token_manager')
print('=' * 60)
from langgraph_engine.token_manager import TokenBudget, BudgetExceededError

budget = TokenBudget(total_budget=1000)
assert budget.get_remaining() == 1000
print('  Initial remaining=1000: ok')

budget.record_usage('step_1', 100)
assert budget.get_spent() == 100
assert budget.get_remaining() == 900
print('  record_usage(100): spent=100, remaining=900')

assert budget.can_proceed('step_2', 500) is True
assert budget.can_proceed('step_2', 10000) is False
print('  can_proceed() passed')

budget.check_or_raise('step_2', 500)
print('  check_or_raise(500) did not raise')

try:
    budget.check_or_raise('step_2', 50000)
    assert False, 'Should have raised BudgetExceededError'
except BudgetExceededError as e:
    print(f'  BudgetExceededError raised correctly: step={e.step}')

budget2 = TokenBudget(total_budget=50)
try:
    budget2.record_usage('step_1', 100)
    assert False, 'Should have raised'
except BudgetExceededError:
    print('  record_usage() over-budget raises correctly')

est = TokenBudget.estimate_tokens('hello world this is a test sentence')
assert est >= 1
print(f'  estimate_tokens() => {est}')

summary = budget.get_summary()
assert 'spent' in summary
assert 'per_step' in summary
assert 'utilization_pct' in summary
print(f'  get_summary() utilization={summary["utilization_pct"]}%')

budget.log_summary()

print()
print('ALL TESTS PASSED')
