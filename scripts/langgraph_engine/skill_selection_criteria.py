"""
Skill Selection Criteria - Validation and conflict detection for Step 5.

Provides:
1. validate_skill()      - check a single skill covers required capabilities
2. detect_conflicts()    - find incompatible skill/agent pairs
3. rank_skills()         - score and rank candidates against task requirements
4. build_selection()     - orchestrate full selection from a candidate list

Skill / Agent dict schema (subset used here):
    {
        "name": str,
        "capabilities": List[str],      # what this skill can do
        "exclusive": bool,              # True if cannot be combined with others
        "conflicts_with": List[str],    # explicit conflict declarations (other skill names)
        "domain": str,                  # e.g. "backend", "frontend", "devops"
        "tags": List[str],              # freeform keyword tags
    }

Task dict schema (subset used here):
    {
        "required_capabilities": List[str],
        "preferred_capabilities": List[str],   # optional nice-to-haves
        "domain": str,                          # optional domain hint
    }
"""

from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from loguru import logger

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
    from utils.path_resolver import get_claude_home

    _SKILL_SELECTION_CLAUDE_HOME = get_claude_home()
except ImportError:
    _SKILL_SELECTION_CLAUDE_HOME = Path.home() / ".claude"


def _get_call_graph_node_bonus(task, skill):
    """Bonus based on call graph hot-node analysis (up to +0.10).

    If the task's call_graph_metrics (from orchestration_pre_analysis_node)
    shows hot nodes (5+ callers) in modules whose names overlap with this
    skill's name or domain, the skill receives a bonus.  Hot modules signal
    high-activity code areas where choosing the best skill matters most.

    Reads task.get("call_graph_metrics") set by pre-analysis.
    Returns 0.0 if call graph is unavailable or no match found.
    """
    try:
        graph_metrics = task.get("call_graph_metrics") or {}
        if not graph_metrics.get("call_graph_available"):
            return 0.0

        skill_name = (skill.get("name") or "").lower()
        skill_domain = (skill.get("domain") or "").lower()
        hot_nodes = graph_metrics.get("hot_nodes", [])
        affected_modules = graph_metrics.get("affected_modules", [])

        if not hot_nodes and not affected_modules:
            return 0.0

        # Keywords from skill name (e.g. "java-spring-boot" -> {"java","spring","boot"})
        skill_keywords: Set[str] = set()
        for part in skill_name.replace("-", " ").replace("_", " ").split():
            if len(part) > 2:
                skill_keywords.add(part)
        if skill_domain:
            skill_keywords.add(skill_domain)

        if not skill_keywords:
            return 0.0

        # Count how many hot node FQNs contain a skill keyword
        hot_matches = sum(1 for node in hot_nodes if any(kw in node.get("fqn", "").lower() for kw in skill_keywords))

        # Count how many affected module names contain a skill keyword
        module_matches = sum(1 for mod in affected_modules if any(kw in mod.lower() for kw in skill_keywords))

        # +0.02 per hot match (capped 0.10), +0.01 per module match (capped 0.05)
        bonus = min(0.10, hot_matches * 0.02) + min(0.05, module_matches * 0.01)
        return min(0.10, bonus)

    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Single-skill validation
# ---------------------------------------------------------------------------


def validate_skill(task: Dict[str, Any], skill: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate whether a skill satisfies all *required* capabilities of a task.

    Args:
        task: Task dict with optional 'required_capabilities' list.
        skill: Skill dict with optional 'capabilities' list.

    Returns:
        (valid: bool, message: str)
        message describes the first missing capability or "OK".

    Example:
        >>> task = {"required_capabilities": ["orm", "jwt"]}
        >>> skill = {"name": "flask-backend", "capabilities": ["orm", "jwt", "rest_api"]}
        >>> validate_skill(task, skill)
        (True, "OK")
    """
    required_caps: List[str] = task.get("required_capabilities") or []
    skill_caps: Set[str] = {c.lower() for c in (skill.get("capabilities") or [])}
    skill_name = skill.get("name", "<unnamed>")

    if not required_caps:
        # No requirements - any skill passes
        return True, "OK"

    for cap in required_caps:
        if cap.lower() not in skill_caps:
            msg = f"Missing capability: {cap} (skill '{skill_name}' does not provide it)"
            logger.debug(f"[SkillSelectionCriteria] validate_skill FAIL: {msg}")
            return False, msg

    logger.debug(f"[SkillSelectionCriteria] validate_skill PASS: '{skill_name}' covers {required_caps}")
    return True, "OK"


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def are_compatible(skill1: Dict[str, Any], skill2: Dict[str, Any]) -> bool:
    """
    Determine whether two skills can be used together.

    Incompatibility rules (first match wins):
    1. Either skill declares exclusive=True  -> incompatible
    2. skill1.conflicts_with contains skill2.name (or vice versa) -> incompatible
    3. Both have the same non-empty 'exclusive_domain' tag -> incompatible

    Returns:
        True if the two skills can coexist.
    """
    name1 = (skill1.get("name") or "").lower()
    name2 = (skill2.get("name") or "").lower()

    # Rule 1: exclusivity flag
    if skill1.get("exclusive") or skill2.get("exclusive"):
        return False

    # Rule 2: explicit conflict lists
    conflicts1 = [c.lower() for c in (skill1.get("conflicts_with") or [])]
    conflicts2 = [c.lower() for c in (skill2.get("conflicts_with") or [])]
    if name2 in conflicts1 or name1 in conflicts2:
        return False

    # Rule 3: exclusive domain overlap
    domain1 = (skill1.get("exclusive_domain") or "").lower()
    domain2 = (skill2.get("exclusive_domain") or "").lower()
    if domain1 and domain2 and domain1 == domain2:
        return False

    return True


def get_conflict_reason(skill1: Dict[str, Any], skill2: Dict[str, Any]) -> str:
    """
    Return a human-readable explanation for why two skills conflict.

    Assumes are_compatible() has already returned False for this pair.
    """
    name1 = skill1.get("name") or "skill1"
    name2 = skill2.get("name") or "skill2"

    if skill1.get("exclusive"):
        return f"'{name1}' is declared exclusive and cannot be combined"
    if skill2.get("exclusive"):
        return f"'{name2}' is declared exclusive and cannot be combined"

    conflicts1 = [c.lower() for c in (skill1.get("conflicts_with") or [])]
    if name2.lower() in conflicts1:
        return f"'{name1}' explicitly lists '{name2}' as a conflict"

    conflicts2 = [c.lower() for c in (skill2.get("conflicts_with") or [])]
    if name1.lower() in conflicts2:
        return f"'{name2}' explicitly lists '{name1}' as a conflict"

    domain1 = skill1.get("exclusive_domain", "")
    if domain1:
        return f"Both skills claim exclusive ownership of domain '{domain1}'"

    return "Incompatible by domain or tag overlap"


def detect_conflicts(selected_skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detect all incompatible pairs in a list of selected skills/agents.

    Args:
        selected_skills: List of skill/agent dicts already chosen.

    Returns:
        List of conflict dicts, each with:
            skill1 (str), skill2 (str), reason (str)
        Empty list if no conflicts found.

    Example:
        >>> skills = [
        ...     {"name": "flask", "exclusive": True},
        ...     {"name": "django", "exclusive": True},
        ... ]
        >>> detect_conflicts(skills)
        [{"skill1": "flask", "skill2": "django", "reason": "..."}]
    """
    conflicts: List[Dict[str, Any]] = []

    for i, skill1 in enumerate(selected_skills):
        for skill2 in selected_skills[i + 1 :]:
            if not are_compatible(skill1, skill2):
                conflict = {
                    "skill1": skill1.get("name", f"skill_{i}"),
                    "skill2": skill2.get("name", "unknown"),
                    "reason": get_conflict_reason(skill1, skill2),
                }
                conflicts.append(conflict)
                logger.warning(
                    f"[SkillSelectionCriteria] Conflict detected: "
                    f"'{conflict['skill1']}' vs '{conflict['skill2']}': {conflict['reason']}"
                )

    if not conflicts:
        logger.debug("[SkillSelectionCriteria] No conflicts in selected skills")

    return conflicts


# ---------------------------------------------------------------------------
# Skill ranking
# ---------------------------------------------------------------------------


def score_skill(task: Dict[str, Any], skill: Dict[str, Any]) -> float:
    """
    Compute a relevance score [0.0, 1.0] for a skill against a task.

    Scoring breakdown:
    - 0.60  required_capabilities coverage  (binary: all or none)
    - 0.20  preferred_capabilities coverage (partial credit)
    - 0.10  domain match bonus
    - 0.10  tag overlap bonus
    """
    score = 0.0
    skill_caps: Set[str] = {c.lower() for c in (skill.get("capabilities") or [])}
    skill_tags: Set[str] = {t.lower() for t in (skill.get("tags") or [])}

    # Required capabilities (60%)
    required = [c.lower() for c in (task.get("required_capabilities") or [])]
    if required:
        covered = sum(1 for c in required if c in skill_caps)
        req_ratio = covered / len(required)
        score += 0.60 * req_ratio
    else:
        score += 0.60  # No requirements - full points

    # Preferred capabilities (20%)
    preferred = [c.lower() for c in (task.get("preferred_capabilities") or [])]
    if preferred:
        covered_pref = sum(1 for c in preferred if c in skill_caps)
        pref_ratio = covered_pref / len(preferred)
        score += 0.20 * pref_ratio
    else:
        score += 0.20  # No preferences - full points

    # Domain match (10%)
    task_domain = (task.get("domain") or "").lower()
    skill_domain = (skill.get("domain") or "").lower()
    if task_domain and skill_domain and task_domain == skill_domain:
        score += 0.10

    # Tag overlap (10%)
    task_tags = {t.lower() for t in (task.get("tags") or [])}
    if task_tags and skill_tags:
        overlap = len(task_tags & skill_tags) / max(len(task_tags), 1)
        score += 0.10 * min(overlap, 1.0)

    # Call graph hot-node bonus (up to +0.10)
    # Skills whose domain matches hot nodes in the call graph score higher.
    cg_bonus = _get_call_graph_node_bonus(task, skill)
    score += cg_bonus

    return min(score, 1.0)


def rank_skills(
    task: Dict[str, Any],
    candidates: List[Dict[str, Any]],
) -> List[Tuple[float, Dict[str, Any]]]:
    """
    Rank candidate skills by relevance score for a task.

    Args:
        task: Task dict.
        candidates: List of skill dicts to evaluate.

    Returns:
        List of (score, skill) tuples sorted by score descending.
    """
    scored = [(score_skill(task, s), s) for s in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Selection orchestrator
# ---------------------------------------------------------------------------


def build_selection(
    task: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    max_skills: int = 3,
) -> Dict[str, Any]:
    """
    Select the best skills for a task, checking for validation and conflicts.

    Algorithm:
    1. Validate all candidates against required capabilities.
    2. Rank valid candidates by score.
    3. Greedily select top-scoring candidates, skipping those that create
       conflicts with already-selected skills.
    4. Stop after max_skills selected or when list exhausted.

    Args:
        task: Task dict with required_capabilities and optional domain/tags.
        candidates: Full list of available skills.
        max_skills: Maximum number of skills to select.

    Returns:
        Dict with:
            selected (List[Dict])   - chosen skills
            skipped_invalid (List)  - skills that failed capability check
            conflicts_found (List)  - conflicts in the final selection (should be [])
            scores (Dict[str, float]) - name -> score for all valid candidates
    """
    # Step 1: filter by required capability validation
    valid_candidates: List[Dict[str, Any]] = []
    skipped_invalid: List[Dict[str, str]] = []

    for skill in candidates:
        ok, reason = validate_skill(task, skill)
        if ok:
            valid_candidates.append(skill)
        else:
            skipped_invalid.append({"skill": skill.get("name", "?"), "reason": reason})

    # Step 2: rank valid candidates
    ranked = rank_skills(task, valid_candidates)
    scores = {skill.get("name", f"skill_{i}"): sc for i, (sc, skill) in enumerate(ranked)}

    # Step 3: greedy selection with conflict avoidance
    selected: List[Dict[str, Any]] = []
    for _, skill in ranked:
        if len(selected) >= max_skills:
            break
        trial = selected + [skill]
        if not detect_conflicts(trial):
            selected.append(skill)
        else:
            logger.info(f"[SkillSelectionCriteria] Skipping '{skill.get('name')}' to avoid conflict")

    # Step 4: sanity check final selection for any remaining conflicts
    final_conflicts = detect_conflicts(selected)

    logger.info(
        f"[SkillSelectionCriteria] Selection complete: {len(selected)} skills chosen, "
        f"{len(skipped_invalid)} invalid, {len(final_conflicts)} conflicts"
    )

    return {
        "selected": selected,
        "skipped_invalid": skipped_invalid,
        "conflicts_found": final_conflicts,
        "scores": scores,
    }
