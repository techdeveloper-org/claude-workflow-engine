"""
Version Selector - Skill version compatibility checking and selection.

Provides:
1. parse_version()            - Parse semantic version string to comparable tuple
2. check_compatibility()      - Validate a version against a requirement specifier
3. select_best_version()      - Pick the best available version for a requirement
4. build_compatibility_matrix()- Build a compatibility matrix for multiple skills
5. handle_deprecated()        - Detect and handle deprecated skill versions
6. validate_version_set()     - Validate that a set of skills have compatible versions

Version specifiers supported:
    *          any version (wildcard)
    1.2.3      exact version
    >=1.0.0    minimum version
    <=2.0.0    maximum version
    >1.0.0     strictly greater
    <2.0.0     strictly less
    ~=1.2.0    compatible release (== 1.2.x)
    !=1.5.0    exclusion

Multiple specifiers can be joined with commas: ">=1.0.0,<2.0.0"
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# ---------------------------------------------------------------------------
# Version parsing
# ---------------------------------------------------------------------------

_VERSION_PATTERN = re.compile(
    r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[._-]?(alpha|beta|rc|dev|post)\.?(\d*))?",
    re.IGNORECASE,
)

# Deprecation markers expected in skill markdown
_DEPRECATION_MARKERS = [
    "deprecated",
    "legacy",
    "end-of-life",
    "eol",
    "replaced by",
    "superseded",
    "do not use",
]


class Version:
    """Comparable semantic version object.

    Supports comparison operators (<, <=, >, >=, ==, !=) for use in filtering
    and sorting version lists.
    """

    # Pre-release labels ranked lowest to highest relative to release
    _PRE_RANK: Dict[str, int] = {"dev": 0, "alpha": 1, "beta": 2, "rc": 3, "": 4, "post": 5}

    def __init__(self, major: int = 0, minor: int = 0, patch: int = 0, pre: str = "", pre_num: int = 0):
        self.major = major
        self.minor = minor
        self.patch = patch
        self.pre = pre.lower() if pre else ""
        self.pre_num = pre_num

    @classmethod
    def parse(cls, version_str: str) -> "Version":
        """Parse a version string into a Version object.

        Args:
            version_str: Version string like "1.2.3", "2.0.0-beta.1", "1.0"

        Returns:
            Version object. Returns Version(0,0,0) if parsing fails.
        """
        if not version_str or version_str.strip() in ("*", "any", ""):
            return cls(0, 0, 0, "", 0)

        cleaned = version_str.strip().lstrip("vV")
        match = _VERSION_PATTERN.match(cleaned)

        if not match:
            logger.debug(f"[VersionSelector] Could not parse version '{version_str}', using 0.0.0")
            return cls(0, 0, 0, "", 0)

        major = int(match.group(1) or 0)
        minor = int(match.group(2) or 0)
        patch = int(match.group(3) or 0)
        pre = (match.group(4) or "").lower()
        pre_num = int(match.group(5) or 0) if match.group(5) else 0

        return cls(major, minor, patch, pre, pre_num)

    def _sort_key(self) -> Tuple:
        pre_rank = self._PRE_RANK.get(self.pre, 4)
        return (self.major, self.minor, self.patch, pre_rank, self.pre_num)

    def __lt__(self, other: "Version") -> bool:
        return self._sort_key() < other._sort_key()

    def __le__(self, other: "Version") -> bool:
        return self._sort_key() <= other._sort_key()

    def __gt__(self, other: "Version") -> bool:
        return self._sort_key() > other._sort_key()

    def __ge__(self, other: "Version") -> bool:
        return self._sort_key() >= other._sort_key()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._sort_key() == other._sort_key()

    def __repr__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre:
            base += f"-{self.pre}"
            if self.pre_num:
                base += f".{self.pre_num}"
        return base

    def is_compatible_release(self, other: "Version") -> bool:
        """~= compatible release: same major.minor, any patch."""
        return self.major == other.major and self.minor == other.minor


def parse_version(version_str: str) -> Version:
    """Parse a version string to a comparable Version object.

    Args:
        version_str: Version string like "1.2.3", ">=2.0.0", "~=1.5.0"
            (operator prefix is stripped automatically)

    Returns:
        Version object.
    """
    # Strip any operator prefix for raw version parsing
    cleaned = re.sub(r"^[><=!~]+\s*", "", version_str.strip())
    return Version.parse(cleaned)


# ---------------------------------------------------------------------------
# Compatibility checking
# ---------------------------------------------------------------------------


def check_compatibility(
    version_str: str,
    requirement: str,
) -> Tuple[bool, str]:
    """Check if a version satisfies a requirement specifier.

    Args:
        version_str: The version to test (e.g., "1.5.2").
        requirement: The specifier to test against (e.g., ">=1.0.0,<2.0.0").
            Use "*" or "" for any version.

    Returns:
        Tuple (compatible: bool, reason: str).

    Examples:
        >>> check_compatibility("1.5.2", ">=1.0.0,<2.0.0")
        (True, "1.5.2 satisfies >=1.0.0,<2.0.0")
        >>> check_compatibility("2.1.0", ">=1.0.0,<2.0.0")
        (False, "2.1.0 fails <2.0.0")
        >>> check_compatibility("1.5.2", "*")
        (True, "Wildcard requirement - any version accepted")
    """
    req = (requirement or "").strip()

    # Wildcard - always compatible
    if req in ("*", "", "any"):
        return True, "Wildcard requirement - any version accepted"

    version = Version.parse(version_str.strip())

    # Split multi-specifier requirements like ">=1.0.0,<2.0.0"
    specifiers = [s.strip() for s in req.split(",") if s.strip()]

    for spec in specifiers:
        ok, reason = _check_single_specifier(version, spec)
        if not ok:
            return False, f"{version_str} fails {spec} (requirement: {requirement})"

    return True, f"{version_str} satisfies {requirement}"


def _check_single_specifier(version: Version, specifier: str) -> Tuple[bool, str]:
    """Check a single specifier clause like >=1.0.0 or ~=1.5.0."""
    specifier = specifier.strip()

    if specifier.startswith("~="):
        req_ver = Version.parse(specifier[2:])
        ok = version.is_compatible_release(req_ver) and version >= req_ver
        return ok, "~= compatible release"

    if specifier.startswith("!="):
        req_ver = Version.parse(specifier[2:])
        return version != req_ver, "!= exclusion"

    if specifier.startswith(">="):
        req_ver = Version.parse(specifier[2:])
        return version >= req_ver, ">= minimum"

    if specifier.startswith("<="):
        req_ver = Version.parse(specifier[2:])
        return version <= req_ver, "<= maximum"

    if specifier.startswith(">"):
        req_ver = Version.parse(specifier[1:])
        return version > req_ver, "> strict minimum"

    if specifier.startswith("<"):
        req_ver = Version.parse(specifier[1:])
        return version < req_ver, "< strict maximum"

    if specifier.startswith("=="):
        req_ver = Version.parse(specifier[2:])
        return version == req_ver, "== exact match"

    # Plain version string - treat as exact match
    req_ver = Version.parse(specifier)
    return version == req_ver, "exact match"


# ---------------------------------------------------------------------------
# Best version selection
# ---------------------------------------------------------------------------


def select_best_version(
    skill_name: str,
    available_versions: List[str],
    requirement: str = "*",
    prefer_stable: bool = True,
) -> Dict[str, Any]:
    """Select the best available version of a skill for a given requirement.

    Strategy:
    1. Filter available versions that satisfy the requirement.
    2. If prefer_stable=True, prefer non-pre-release versions.
    3. Among remaining candidates, select the highest version.

    Args:
        skill_name: Name of the skill (for logging).
        available_versions: All versions available for download/use.
        requirement: Version requirement specifier (e.g., ">=1.0.0", "*").
        prefer_stable: If True, prefer release versions over pre-releases.

    Returns:
        Dict with:
            selected (Optional[str])  - selected version string, None if none qualify
            compatible (List[str])    - all compatible versions
            incompatible (List[str])  - versions that failed the requirement
            reason (str)              - human-readable explanation
            is_stable (bool)          - whether selected version is a stable release

    Example:
        >>> select_best_version("my-skill", ["1.0.0", "1.5.0", "2.0.0-beta"], ">=1.0.0,<2.0.0")
        {"selected": "1.5.0", "compatible": ["1.0.0", "1.5.0"], ...}
    """
    compatible: List[str] = []
    incompatible: List[str] = []

    for ver in available_versions:
        ok, _ = check_compatibility(ver, requirement)
        if ok:
            compatible.append(ver)
        else:
            incompatible.append(ver)

    if not compatible:
        logger.warning(
            f"[VersionSelector] No compatible versions for '{skill_name}' "
            f"matching '{requirement}'. Available: {available_versions}"
        )
        return {
            "selected": None,
            "compatible": [],
            "incompatible": incompatible,
            "reason": f"No versions satisfy requirement '{requirement}'",
            "is_stable": False,
        }

    # Sort compatible versions descending (newest first)
    sorted_compatible = sorted(
        compatible,
        key=lambda v: Version.parse(v),
        reverse=True,
    )

    selected = None
    is_stable = False

    if prefer_stable:
        # Try to find a stable (non-pre-release) version first
        for ver_str in sorted_compatible:
            v = Version.parse(ver_str)
            if v.pre == "":
                selected = ver_str
                is_stable = True
                break

    # Fallback to highest available (including pre-releases)
    if selected is None:
        selected = sorted_compatible[0]
        is_stable = Version.parse(selected).pre == ""

    logger.info(
        f"[VersionSelector] '{skill_name}': selected={selected} "
        f"(from {len(compatible)} compatible), stable={is_stable}"
    )

    return {
        "selected": selected,
        "compatible": sorted_compatible,
        "incompatible": incompatible,
        "reason": f"Selected {selected} (best match for '{requirement}')",
        "is_stable": is_stable,
    }


# ---------------------------------------------------------------------------
# Compatibility matrix
# ---------------------------------------------------------------------------


def build_compatibility_matrix(
    skills: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a compatibility matrix for a collection of skills.

    Checks pairwise version compatibility between skills based on their
    declared version requirements for each other.

    Args:
        skills: List of skill dicts, each with:
            name (str)                 - skill name
            version (str)              - installed/selected version
            version_requirements (Dict[str, str]) - {dep_name: version_req}

    Returns:
        Dict with:
            matrix (Dict[str, Dict[str, bool]])  - [skill_a][skill_b] = compatible
            conflicts (List[Dict])               - [{skill, dep, has_version, requires}]
            all_compatible (bool)                - True if no conflicts found
            summary (str)                        - human-readable summary

    Example:
        >>> skills = [
        ...   {"name": "a", "version": "1.5.0", "version_requirements": {"b": ">=1.0.0"}},
        ...   {"name": "b", "version": "0.9.0", "version_requirements": {}},
        ... ]
        >>> result = build_compatibility_matrix(skills)
        >>> result["all_compatible"]
        False
    """
    matrix: Dict[str, Dict[str, bool]] = {}
    conflicts: List[Dict[str, str]] = []

    skill_versions: Dict[str, str] = {s["name"]: s.get("version", "*") for s in skills}

    for skill in skills:
        skill_name = skill["name"]
        matrix[skill_name] = {}
        version_reqs: Dict[str, str] = skill.get("version_requirements", {})

        for dep_name, req in version_reqs.items():
            dep_version = skill_versions.get(dep_name)
            if dep_version is None:
                # Dependency not in provided skill set - assume compatible
                matrix[skill_name][dep_name] = True
                continue

            ok, reason = check_compatibility(dep_version, req)
            matrix[skill_name][dep_name] = ok

            if not ok:
                conflict = {
                    "skill": skill_name,
                    "dep": dep_name,
                    "has_version": dep_version,
                    "requires": req,
                    "reason": reason,
                }
                conflicts.append(conflict)
                logger.warning(
                    f"[VersionSelector] Version conflict: '{skill_name}' requires "
                    f"'{dep_name}' {req} but found {dep_version}"
                )

    all_compatible = len(conflicts) == 0

    if all_compatible:
        summary = f"All {len(skills)} skills are version-compatible"
    else:
        summary = f"{len(conflicts)} version conflict(s) found among {len(skills)} skills: " + ", ".join(
            f"{c['skill']}->{c['dep']}" for c in conflicts
        )

    logger.info(f"[VersionSelector] Compatibility matrix: {summary}")

    return {
        "matrix": matrix,
        "conflicts": conflicts,
        "all_compatible": all_compatible,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Deprecation handling
# ---------------------------------------------------------------------------


def handle_deprecated(
    skill_name: str,
    skill_content: str,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    """Detect and handle deprecated skill definitions.

    Scans skill content for deprecation markers and returns structured
    information about the deprecation status and any recommended replacements.

    Args:
        skill_name: Name of the skill being checked.
        skill_content: Full skill markdown content.
        version: Optional version string being evaluated.

    Returns:
        Dict with:
            is_deprecated (bool)         - True if deprecation detected
            deprecation_reason (str)     - Why it is deprecated
            replacement (Optional[str])  - Recommended replacement skill name
            severity (str)               - "warning" | "error" | "none"
            message (str)                - Human-readable deprecation message

    Example:
        >>> content = "# my-skill\\n**Deprecated:** Use new-skill instead."
        >>> result = handle_deprecated("my-skill", content)
        >>> result["is_deprecated"]
        True
        >>> result["replacement"]
        'new-skill'
    """
    if not skill_content:
        return {
            "is_deprecated": False,
            "deprecation_reason": "",
            "replacement": None,
            "severity": "none",
            "message": f"Skill '{skill_name}' has no content to analyze",
        }

    content_lower = skill_content.lower()
    is_deprecated = False
    deprecation_reason = ""
    severity = "none"

    for marker in _DEPRECATION_MARKERS:
        if marker in content_lower:
            is_deprecated = True
            deprecation_reason = marker
            # Distinguish severity: "deprecated" / "legacy" = warning, "eol" = error
            if marker in ("end-of-life", "eol", "do not use"):
                severity = "error"
            else:
                severity = "warning"
            break

    # Try to extract replacement skill name
    replacement: Optional[str] = None
    if is_deprecated:
        # Look for "replaced by X", "use X instead", "superseded by X" patterns
        replacement_patterns = [
            r"replaced\s+by\s+[`'\"]?([a-zA-Z][a-zA-Z0-9_-]+)[`'\"]?",
            r"use\s+[`'\"]?([a-zA-Z][a-zA-Z0-9_-]+)[`'\"]?\s+instead",
            r"superseded\s+by\s+[`'\"]?([a-zA-Z][a-zA-Z0-9_-]+)[`'\"]?",
            r"migrate\s+to\s+[`'\"]?([a-zA-Z][a-zA-Z0-9_-]+)[`'\"]?",
        ]
        for pattern in replacement_patterns:
            match = re.search(pattern, skill_content, re.IGNORECASE)
            if match:
                replacement = match.group(1).strip()
                break

        if severity == "error":
            logger.error(
                f"[VersionSelector] Skill '{skill_name}' is end-of-life/deprecated (EOL). "
                f"Replacement: {replacement or 'none specified'}"
            )
        else:
            logger.warning(
                f"[VersionSelector] Skill '{skill_name}' is deprecated "
                f"(reason: '{deprecation_reason}'). "
                f"Replacement: {replacement or 'none specified'}"
            )

    version_note = f" (version {version})" if version else ""

    if is_deprecated:
        message = f"Skill '{skill_name}'{version_note} is deprecated " f"[{deprecation_reason}]"
        if replacement:
            message += f". Recommended replacement: '{replacement}'"
    else:
        message = f"Skill '{skill_name}'{version_note} is current and supported"

    return {
        "is_deprecated": is_deprecated,
        "deprecation_reason": deprecation_reason,
        "replacement": replacement,
        "severity": severity,
        "message": message,
    }


# ---------------------------------------------------------------------------
# Version set validation
# ---------------------------------------------------------------------------


def validate_version_set(
    skill_versions: Dict[str, str],
    requirements: Dict[str, Dict[str, str]],
) -> Dict[str, Any]:
    """Validate that a complete set of versioned skills satisfies all requirements.

    Args:
        skill_versions: Map of {skill_name: version_string} for all installed skills.
        requirements: Map of {skill_name: {dep_name: version_req}} for all dependencies.

    Returns:
        Dict with:
            valid (bool)               - True if all requirements satisfied
            violations (List[Dict])    - Each violation {skill, dep, has, requires}
            satisfied (List[str])      - List of satisfied requirement pairs as strings
            report (str)               - Summary report string

    Example:
        >>> versions = {"a": "1.5.0", "b": "2.0.0"}
        >>> reqs = {"a": {"b": ">=1.0.0"}}
        >>> validate_version_set(versions, reqs)
        {"valid": True, "violations": [], ...}
    """
    violations: List[Dict[str, str]] = []
    satisfied: List[str] = []

    for skill_name, deps in requirements.items():
        for dep_name, req in deps.items():
            dep_version = skill_versions.get(dep_name)

            if dep_version is None:
                violations.append(
                    {
                        "skill": skill_name,
                        "dep": dep_name,
                        "has": "NOT INSTALLED",
                        "requires": req,
                        "reason": f"Dependency '{dep_name}' is not installed",
                    }
                )
                logger.warning(f"[VersionSelector] '{skill_name}' requires '{dep_name}' " f"but it is not installed")
                continue

            ok, reason = check_compatibility(dep_version, req)
            pair_str = f"{skill_name}->{dep_name}@{dep_version} (req: {req})"

            if ok:
                satisfied.append(pair_str)
                logger.debug(f"[VersionSelector] Satisfied: {pair_str}")
            else:
                violations.append(
                    {
                        "skill": skill_name,
                        "dep": dep_name,
                        "has": dep_version,
                        "requires": req,
                        "reason": reason,
                    }
                )
                logger.warning(f"[VersionSelector] Violation: {pair_str} - {reason}")

    is_valid = len(violations) == 0

    if is_valid:
        report = f"All {len(satisfied)} version requirements satisfied"
    else:
        report = (
            f"{len(violations)} violation(s) out of "
            f"{len(satisfied) + len(violations)} requirements. "
            f"Violations: "
            + "; ".join(f"{v['skill']}->{v['dep']} (has {v['has']}, needs {v['requires']})" for v in violations)
        )

    logger.info(f"[VersionSelector] Validation: {report}")

    return {
        "valid": is_valid,
        "violations": violations,
        "satisfied": satisfied,
        "report": report,
    }
