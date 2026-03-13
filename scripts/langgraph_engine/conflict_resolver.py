"""
Conflict Resolver - Detects and resolves conflicts in Level 3 pipeline.

Three conflict domains:
1. Skill Conflicts      - Incompatible skills/agents selected together (Step 5)
2. Standard Conflicts   - Conflicting Level 2 standards applied simultaneously
3. Branch Conflicts     - Git branch already exists or has uncommitted changes (Step 9)

Resolution Strategy:
- Priority-based: Higher priority wins when two skills/standards conflict
- Exclusive-first: Skills flagged exclusive=True block all others in same domain
- Branch: Auto-suffix with session ID when name collision detected
- All conflicts logged to JSON via save_conflict_log()

Usage:
    from .conflict_resolver import ConflictResolver

    resolver = ConflictResolver(session_dir="/tmp/session_123")

    # Skill conflicts
    resolution = resolver.resolve_skill_conflicts(selected_skills, task)

    # Standard conflicts
    resolution = resolver.resolve_standard_conflicts(active_standards)

    # Branch conflicts
    resolution = resolver.resolve_branch_conflict(desired_branch, repo_path=".")
"""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ---------------------------------------------------------------------------
# Priority tables
# ---------------------------------------------------------------------------

# Skill domain priority: higher number = higher priority when conflict arises
SKILL_DOMAIN_PRIORITY: Dict[str, int] = {
    "security":   10,
    "devops":     8,
    "backend":    7,
    "database":   7,
    "frontend":   6,
    "testing":    5,
    "monitoring": 4,
    "general":    1,
}

# Standard priority: higher = enforced first; lower is dropped on conflict
STANDARD_PRIORITY: Dict[str, int] = {
    "security":         10,
    "encoding":         9,
    "tool_optimization": 8,
    "error_handling":   7,
    "logging":          6,
    "performance":      5,
    "style":            3,
    "general":          1,
}

# Known mutually-exclusive skill name patterns (regex, case-insensitive)
_EXCLUSIVE_PATTERNS: List[Tuple[str, str]] = [
    (r"flask",     r"django"),
    (r"flask",     r"fastapi"),
    (r"django",    r"fastapi"),
    (r"sqlalchemy", r"django.orm"),
    (r"mysql",     r"postgresql"),
    (r"redis",     r"memcached"),
    (r"celery",    r"rq"),
    (r"jwt",       r"session.auth"),
]


# ---------------------------------------------------------------------------
# Data classes (plain dicts to stay JSON-serialisable)
# ---------------------------------------------------------------------------

def _conflict_record(
    conflict_type: str,
    item_a: str,
    item_b: str,
    reason: str,
    resolution: str,
    winner: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a standardised conflict record dict."""
    return {
        "conflict_type": conflict_type,
        "item_a": item_a,
        "item_b": item_b,
        "reason": reason,
        "resolution": resolution,
        "winner": winner,
        "timestamp": datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# ConflictResolver
# ---------------------------------------------------------------------------

class ConflictResolver:
    """
    Detects and resolves conflicts across skills, standards, and git branches.

    All detected conflicts are stored in self.conflict_log and can be
    persisted to disk via save_conflict_log().
    """

    def __init__(self, session_dir: str):
        self.session_dir = Path(session_dir)
        self.conflict_log: List[Dict[str, Any]] = []

    # =========================================================================
    # PUBLIC: SKILL CONFLICTS
    # =========================================================================

    def resolve_skill_conflicts(
        self,
        selected_skills: List[Dict[str, Any]],
        task: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Detect and resolve conflicts in the list of selected skills/agents.

        Resolution order:
        1. Remove skills that explicitly list each other in `conflicts_with`.
        2. Remove skills that match _EXCLUSIVE_PATTERNS (framework exclusions).
        3. For domains with `exclusive=True` skills, drop all non-exclusive peers.
        4. When two skills compete for the same capability, prefer higher domain priority.

        Args:
            selected_skills: List of skill dicts from Step 5 output.
            task:            Optional task dict for context (not yet used in v1).

        Returns:
            {
                "resolved_skills": List[Dict],  # Conflict-free list
                "removed": List[str],           # Skill names removed
                "conflicts_detected": int,      # Number of conflicts found
                "conflict_details": List[Dict], # Per-conflict records
            }
        """
        logger.info("[ConflictResolver] Starting skill conflict resolution...")
        logger.info(f"[ConflictResolver] Input: {len(selected_skills)} skills")

        if not selected_skills:
            return self._skill_result([], [], 0)

        working = list(selected_skills)  # mutable copy
        removed_names: List[str] = []

        # Pass 1: explicit `conflicts_with` declarations
        working, pass1_removed = self._resolve_explicit_conflicts(working)
        removed_names.extend(pass1_removed)

        # Pass 2: pattern-based framework exclusions
        working, pass2_removed = self._resolve_pattern_conflicts(working)
        removed_names.extend(pass2_removed)

        # Pass 3: exclusive flag enforcement
        working, pass3_removed = self._resolve_exclusive_flags(working)
        removed_names.extend(pass3_removed)

        # Pass 4: domain capability de-duplication by priority
        working, pass4_removed = self._resolve_domain_priority(working)
        removed_names.extend(pass4_removed)

        total_conflicts = len(removed_names)
        details = [r for r in self.conflict_log if r["conflict_type"].startswith("skill")]

        logger.info(
            f"[ConflictResolver] Skill resolution complete: "
            f"{len(working)} kept, {total_conflicts} removed"
        )

        return self._skill_result(working, removed_names, total_conflicts, details)

    # =========================================================================
    # PUBLIC: STANDARD CONFLICTS
    # =========================================================================

    def resolve_standard_conflicts(
        self,
        active_standards: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Detect and resolve conflicts between active Level 2 standards.

        Two standards conflict when they define the same setting/key with
        incompatible values. Resolution: higher STANDARD_PRIORITY wins.
        When priority is equal, the first standard in the list wins.

        Args:
            active_standards: List of standard dicts, each with at least:
                {
                    "name": str,
                    "type": str,             # maps to STANDARD_PRIORITY keys
                    "settings": Dict[str, Any]  # key-value pairs this standard sets
                }

        Returns:
            {
                "resolved_standards": List[Dict],
                "overridden_settings": Dict,  # {setting_key: {winner, losers}}
                "conflicts_detected": int,
                "conflict_details": List[Dict],
            }
        """
        logger.info("[ConflictResolver] Starting standard conflict resolution...")

        if not active_standards:
            return {
                "resolved_standards": [],
                "overridden_settings": {},
                "conflicts_detected": 0,
                "conflict_details": [],
            }

        # Build map: setting_key -> list of (standard, value, priority)
        setting_owners: Dict[str, List[Tuple[Dict, Any, int]]] = {}

        for std in active_standards:
            std_type = std.get("type", "general")
            priority = STANDARD_PRIORITY.get(std_type, 1)
            settings = std.get("settings") or {}
            for key, value in settings.items():
                if key not in setting_owners:
                    setting_owners[key] = []
                setting_owners[key].append((std, value, priority))

        overridden: Dict[str, Any] = {}
        conflicted_std_names = set()

        # Detect keys claimed by more than one standard
        for key, owners in setting_owners.items():
            if len(owners) <= 1:
                continue

            # Sort by priority descending (first = highest = winner)
            owners_sorted = sorted(owners, key=lambda x: x[2], reverse=True)
            winner_std, winner_val, winner_pri = owners_sorted[0]
            losers = owners_sorted[1:]

            for loser_std, loser_val, loser_pri in losers:
                if loser_val != winner_val:
                    record = _conflict_record(
                        conflict_type="standard_setting",
                        item_a=winner_std.get("name", "unknown"),
                        item_b=loser_std.get("name", "unknown"),
                        reason=f"Both define '{key}': winner={winner_val!r}, loser={loser_val!r}",
                        resolution=f"Using value from '{winner_std.get('name')}' (priority={winner_pri})",
                        winner=winner_std.get("name"),
                    )
                    self.conflict_log.append(record)
                    conflicted_std_names.add(loser_std.get("name", ""))
                    logger.warning(
                        f"[ConflictResolver] Standard conflict on '{key}': "
                        f"{winner_std.get('name')} wins over {loser_std.get('name')}"
                    )
                    overridden[key] = {
                        "winner": winner_std.get("name"),
                        "winner_value": winner_val,
                        "losers": [l[0].get("name") for l in losers],
                    }

        total_conflicts = len([r for r in self.conflict_log if r["conflict_type"] == "standard_setting"])
        details = [r for r in self.conflict_log if r["conflict_type"] == "standard_setting"]

        logger.info(
            f"[ConflictResolver] Standard resolution complete: "
            f"{total_conflicts} setting conflicts resolved"
        )

        return {
            "resolved_standards": active_standards,  # Standards kept (only settings overridden)
            "overridden_settings": overridden,
            "conflicts_detected": total_conflicts,
            "conflict_details": details,
        }

    # =========================================================================
    # PUBLIC: BRANCH CONFLICTS
    # =========================================================================

    def resolve_branch_conflict(
        self,
        desired_branch: str,
        repo_path: str = ".",
        session_suffix: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Detect and resolve git branch naming conflicts.

        Checks:
        1. Does the branch already exist locally?
        2. Does the branch already exist on the remote?
        3. Are there uncommitted changes that would block checkout?

        Resolution:
        - Existing branch: append session_suffix (short hash) to create unique name
        - Uncommitted changes: log warning only (cannot auto-resolve without user intent)

        Args:
            desired_branch:  Intended branch name (e.g. "feature/issue-42-auth").
            repo_path:       Path to git repository root.
            session_suffix:  Short suffix to append on collision. Auto-generated if None.

        Returns:
            {
                "resolved_branch": str,  # Final branch name to use
                "original_branch": str,  # Requested branch name
                "conflict_detected": bool,
                "conflict_reason": str,
                "auto_resolved": bool,
                "uncommitted_changes": bool,
                "conflict_details": List[Dict],
            }
        """
        logger.info(f"[ConflictResolver] Checking branch conflict for: '{desired_branch}'")

        result = {
            "resolved_branch": desired_branch,
            "original_branch": desired_branch,
            "conflict_detected": False,
            "conflict_reason": "",
            "auto_resolved": False,
            "uncommitted_changes": False,
            "conflict_details": [],
        }

        # --- Check for uncommitted changes ---
        dirty = self._has_uncommitted_changes(repo_path)
        if dirty:
            result["uncommitted_changes"] = True
            logger.warning(
                "[ConflictResolver] Uncommitted changes detected in repo. "
                "Branch creation may fail - consider committing or stashing."
            )

        # --- Check if branch exists locally ---
        local_exists = self._branch_exists_local(desired_branch, repo_path)
        remote_exists = self._branch_exists_remote(desired_branch, repo_path)

        if local_exists or remote_exists:
            origin = "locally" if local_exists else "on remote"
            result["conflict_detected"] = True
            result["conflict_reason"] = f"Branch '{desired_branch}' already exists {origin}"

            # Auto-resolve: append suffix
            if session_suffix is None:
                session_suffix = datetime.now().strftime("%m%d%H%M")

            resolved_name = f"{desired_branch}-{session_suffix}"
            result["resolved_branch"] = resolved_name
            result["auto_resolved"] = True

            record = _conflict_record(
                conflict_type="branch_name",
                item_a=desired_branch,
                item_b=resolved_name,
                reason=f"Branch '{desired_branch}' exists {origin}",
                resolution=f"Using auto-suffixed name: '{resolved_name}'",
                winner=resolved_name,
            )
            self.conflict_log.append(record)
            result["conflict_details"].append(record)

            logger.warning(
                f"[ConflictResolver] Branch conflict resolved: "
                f"'{desired_branch}' -> '{resolved_name}'"
            )
        else:
            logger.info(f"[ConflictResolver] No branch conflict: '{desired_branch}' is available")

        return result

    # =========================================================================
    # PUBLIC: PERSIST LOG
    # =========================================================================

    def save_conflict_log(self, filename: Optional[str] = None) -> str:
        """
        Save all conflict records to a JSON file in the session directory.

        Args:
            filename: Optional filename override. Defaults to
                      'conflict_log_<timestamp>.json'.

        Returns:
            Absolute path to the written file.
        """
        if filename is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conflict_log_{ts}.json"

        output_path = self.session_dir / filename

        try:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "session_dir": str(self.session_dir),
                "generated_at": datetime.now().isoformat(),
                "total_conflicts": len(self.conflict_log),
                "conflicts": self.conflict_log,
            }
            with open(output_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=True)

            logger.info(f"[ConflictResolver] Conflict log saved: {output_path}")
            return str(output_path)

        except Exception as exc:
            logger.error(f"[ConflictResolver] Failed to save conflict log: {exc}")
            return ""

    # =========================================================================
    # PRIVATE: SKILL RESOLUTION PASSES
    # =========================================================================

    def _resolve_explicit_conflicts(
        self, skills: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Pass 1 - Remove skills that explicitly list another in conflicts_with."""
        removed: List[str] = []
        skill_names = {s.get("name", "").lower() for s in skills}

        to_keep = []
        for skill in skills:
            my_conflicts = [c.lower() for c in (skill.get("conflicts_with") or [])]
            overlapping = skill_names.intersection(set(my_conflicts)) - {skill.get("name", "").lower()}

            if overlapping:
                # Determine which to remove via domain priority
                for peer_name in overlapping:
                    peer = next((s for s in skills if s.get("name", "").lower() == peer_name), None)
                    if peer is None:
                        continue
                    my_prio = SKILL_DOMAIN_PRIORITY.get(skill.get("domain", "general"), 1)
                    peer_prio = SKILL_DOMAIN_PRIORITY.get(peer.get("domain", "general"), 1)

                    loser = skill if my_prio < peer_prio else peer
                    loser_name = loser.get("name", "unknown")

                    if loser_name not in removed:
                        removed.append(loser_name)
                        record = _conflict_record(
                            conflict_type="skill_explicit",
                            item_a=skill.get("name", "?"),
                            item_b=peer_name,
                            reason=f"Explicit conflicts_with declaration",
                            resolution=f"Removed '{loser_name}' (lower domain priority)",
                            winner=(skill if loser is peer else peer).get("name"),
                        )
                        self.conflict_log.append(record)
                        logger.warning(
                            f"[ConflictResolver] Explicit conflict: {skill.get('name')} "
                            f"vs {peer_name} -> removed '{loser_name}'"
                        )

        to_keep = [s for s in skills if s.get("name", "") not in removed]
        return to_keep, removed

    def _resolve_pattern_conflicts(
        self, skills: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Pass 2 - Remove skills that match known mutually-exclusive patterns."""
        removed: List[str] = []
        name_to_skill = {s.get("name", ""): s for s in skills}
        skill_names = list(name_to_skill.keys())

        for pat_a, pat_b in _EXCLUSIVE_PATTERNS:
            matches_a = [n for n in skill_names if re.search(pat_a, n, re.IGNORECASE)]
            matches_b = [n for n in skill_names if re.search(pat_b, n, re.IGNORECASE)]

            if matches_a and matches_b:
                # Both pattern groups present - resolve by domain priority
                skill_a = name_to_skill[matches_a[0]]
                skill_b = name_to_skill[matches_b[0]]
                prio_a = SKILL_DOMAIN_PRIORITY.get(skill_a.get("domain", "general"), 1)
                prio_b = SKILL_DOMAIN_PRIORITY.get(skill_b.get("domain", "general"), 1)

                # If equal priority, prefer first listed (a wins)
                loser = skill_b if prio_a >= prio_b else skill_a
                loser_name = loser.get("name", "unknown")

                if loser_name not in removed:
                    removed.append(loser_name)
                    record = _conflict_record(
                        conflict_type="skill_pattern",
                        item_a=matches_a[0],
                        item_b=matches_b[0],
                        reason=f"Mutually exclusive pattern: /{pat_a}/ vs /{pat_b}/",
                        resolution=f"Removed '{loser_name}' (pattern exclusion)",
                        winner=(skill_a if loser is skill_b else skill_b).get("name"),
                    )
                    self.conflict_log.append(record)
                    logger.warning(
                        f"[ConflictResolver] Pattern conflict: {matches_a[0]} vs {matches_b[0]} "
                        f"-> removed '{loser_name}'"
                    )

        to_keep = [s for s in skills if s.get("name", "") not in removed]
        return to_keep, removed

    def _resolve_exclusive_flags(
        self, skills: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Pass 3 - When an exclusive=True skill is present, drop domain peers."""
        removed: List[str] = []

        # Group by domain
        domain_map: Dict[str, List[Dict[str, Any]]] = {}
        for skill in skills:
            domain = skill.get("domain", "general")
            domain_map.setdefault(domain, []).append(skill)

        to_keep = []
        for domain, domain_skills in domain_map.items():
            exclusives = [s for s in domain_skills if s.get("exclusive", False)]
            if not exclusives:
                to_keep.extend(domain_skills)
                continue

            # Keep only the highest-priority exclusive skill
            winner = max(
                exclusives,
                key=lambda s: SKILL_DOMAIN_PRIORITY.get(s.get("domain", "general"), 1),
            )
            for skill in domain_skills:
                if skill is winner:
                    to_keep.append(skill)
                else:
                    removed.append(skill.get("name", "unknown"))
                    record = _conflict_record(
                        conflict_type="skill_exclusive",
                        item_a=winner.get("name", "?"),
                        item_b=skill.get("name", "?"),
                        reason=f"Exclusive skill '{winner.get('name')}' blocks peers in domain '{domain}'",
                        resolution=f"Removed '{skill.get('name')}'",
                        winner=winner.get("name"),
                    )
                    self.conflict_log.append(record)
                    logger.warning(
                        f"[ConflictResolver] Exclusive flag: domain='{domain}' "
                        f"winner='{winner.get('name')}' removed='{skill.get('name')}'"
                    )

        return to_keep, removed

    def _resolve_domain_priority(
        self, skills: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Pass 4 - When two skills claim the same unique capability, prefer higher domain priority."""
        removed: List[str] = []
        capability_owners: Dict[str, Dict[str, Any]] = {}

        for skill in skills:
            caps = skill.get("capabilities") or []
            for cap in caps:
                cap_key = cap.lower()
                if cap_key in capability_owners:
                    existing = capability_owners[cap_key]
                    existing_prio = SKILL_DOMAIN_PRIORITY.get(existing.get("domain", "general"), 1)
                    new_prio = SKILL_DOMAIN_PRIORITY.get(skill.get("domain", "general"), 1)

                    if new_prio > existing_prio:
                        # New skill wins - mark existing as removed
                        loser_name = existing.get("name", "?")
                        if loser_name not in removed:
                            removed.append(loser_name)
                            record = _conflict_record(
                                conflict_type="skill_capability_priority",
                                item_a=skill.get("name", "?"),
                                item_b=loser_name,
                                reason=f"Both provide capability '{cap_key}'",
                                resolution=f"'{skill.get('name')}' wins (higher domain priority)",
                                winner=skill.get("name"),
                            )
                            self.conflict_log.append(record)
                        capability_owners[cap_key] = skill
                    # else: existing wins, new skill may be removed later
                else:
                    capability_owners[cap_key] = skill

        to_keep = [s for s in skills if s.get("name", "") not in removed]
        return to_keep, removed

    # =========================================================================
    # PRIVATE: GIT HELPERS
    # =========================================================================

    def _run_git(self, args: List[str], cwd: str) -> Tuple[int, str, str]:
        """Run a git command, return (returncode, stdout, stderr)."""
        try:
            proc = subprocess.run(
                ["git"] + args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                timeout=15,
            )
            return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
        except Exception as exc:
            return -1, "", str(exc)

    def _branch_exists_local(self, branch: str, repo_path: str) -> bool:
        """Return True if branch exists locally."""
        code, stdout, _ = self._run_git(["branch", "--list", branch], repo_path)
        return code == 0 and branch in stdout

    def _branch_exists_remote(self, branch: str, repo_path: str) -> bool:
        """Return True if branch exists on origin remote."""
        code, stdout, _ = self._run_git(
            ["ls-remote", "--heads", "origin", branch], repo_path
        )
        return code == 0 and branch in stdout

    def _has_uncommitted_changes(self, repo_path: str) -> bool:
        """Return True if there are uncommitted changes in the working tree."""
        code, stdout, _ = self._run_git(["status", "--porcelain"], repo_path)
        return code == 0 and bool(stdout.strip())

    # =========================================================================
    # PRIVATE: RESULT BUILDERS
    # =========================================================================

    @staticmethod
    def _skill_result(
        kept: List[Dict],
        removed: List[str],
        conflicts: int,
        details: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        return {
            "resolved_skills": kept,
            "removed": removed,
            "conflicts_detected": conflicts,
            "conflict_details": details or [],
        }
