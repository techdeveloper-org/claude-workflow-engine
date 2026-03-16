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

import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Set
from loguru import logger


# ---------------------------------------------------------------------------
# Cross-session learning: RAG-based skill boost + pattern detection
# ---------------------------------------------------------------------------

# Cache for pattern data (loaded once per process)
_pattern_cache = None  # type: Optional[Dict]


def _load_cross_project_patterns():
    """Load cross-project patterns from detect-patterns output."""
    global _pattern_cache
    if _pattern_cache is not None:
        return _pattern_cache

    patterns_file = Path.home() / ".claude" / "memory" / "cross-project-patterns.json"
    try:
        if patterns_file.exists():
            _pattern_cache = json.loads(patterns_file.read_text(encoding="utf-8"))
        else:
            _pattern_cache = {"patterns": []}
    except Exception:
        _pattern_cache = {"patterns": []}
    return _pattern_cache


def _get_rag_skill_boost(task, skill):
    """Get RAG-based boost for a skill based on historical success patterns.

    Checks two sources:
    1. Vector DB: Search for past sessions where this skill was used for similar tasks
    2. Cross-project patterns: Boost if skill matches detected technology patterns

    Returns a bonus score between 0.0 and 0.15.
    """
    boost = 0.0
    skill_name = (skill.get("name") or "").lower()
    task_type = (task.get("task_type") or task.get("type") or "").lower()

    if not skill_name:
        return 0.0

    # Source 1: Vector DB RAG lookup (past skill selections)
    try:
        from .rag_integration import _get_vector_functions
        vf = _get_vector_functions()
        if vf.get("available"):
            query = f"step5 skill selection {skill_name} {task_type}"
            result_json = vf["search"](
                query=query,
                collection="node_decisions",
                limit=3,
                min_score=0.70,
                filter_field="step",
                filter_value="step5",
            )
            result = json.loads(result_json)
            matches = result.get("matches", [])
            if matches:
                # Found past successful use of this skill
                best_score = matches[0].get("score", 0)
                # Scale: 0.70-1.0 score -> 0.0-0.10 boost
                if best_score >= 0.70:
                    boost += min(0.10, (best_score - 0.70) * 0.33)
    except Exception:
        pass  # RAG lookup failure is non-fatal

    # Source 2: Cross-project pattern matching
    try:
        patterns_data = _load_cross_project_patterns()
        patterns = patterns_data.get("patterns", [])

        # Map skill names to technology keywords
        skill_keywords = set()
        skill_keywords.add(skill_name)
        # Extract keywords from skill name (e.g., "java-spring-boot" -> {"java", "spring", "boot"})
        for part in skill_name.replace("-", " ").replace("_", " ").split():
            skill_keywords.add(part.lower())

        # Check if any detected patterns match skill keywords
        matching_patterns = 0
        for pattern in patterns:
            pattern_name = (pattern.get("name") or "").lower()
            if pattern_name in skill_keywords:
                confidence = pattern.get("confidence", 0)
                if confidence >= 0.6:
                    matching_patterns += 1

        # Scale: 1+ pattern matches -> up to 0.05 boost
        if matching_patterns > 0:
            boost += min(0.05, matching_patterns * 0.025)
    except Exception:
        pass  # Pattern detection failure is non-fatal

    return min(boost, 0.15)


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

    logger.debug(
        f"[SkillSelectionCriteria] validate_skill PASS: '{skill_name}' covers {required_caps}"
    )
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
    name1 = (skill1.get("name") or "skill1")
    name2 = (skill2.get("name") or "skill2")

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
        for skill2 in selected_skills[i + 1:]:
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

    # Cross-session RAG boost (up to +0.15 bonus)
    # If this skill was successfully used for similar tasks in the past,
    # boost its score based on historical success patterns.
    rag_boost = _get_rag_skill_boost(task, skill)
    score += rag_boost

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
            logger.info(
                f"[SkillSelectionCriteria] Skipping '{skill.get('name')}' to avoid conflict"
            )

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
