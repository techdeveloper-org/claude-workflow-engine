"""
TOON Schema Definition - TypedDict + validation for Level 1 context sync.

TOON = Tokenized Object-Oriented Notation
Defines the canonical TOON structure produced by Level 1 and consumed by Level 3.

Usage:
    from toon_schema import TOONSchema, ContextType, validate_toon
    toon = TOONSchema(session_id="...", ...)
    is_valid, errors = validate_toon(toon)
"""

from typing import TypedDict, List, Optional, Dict, Any
from datetime import datetime


# ============================================================================
# CONTEXT SUB-TYPES
# ============================================================================

class ContextType(TypedDict, total=False):
    """Context data embedded inside a TOON object."""
    files: List[str]       # List of files loaded (e.g., ["SRS", "README", "CLAUDE.md"])
    srs: bool              # Whether SRS was loaded
    readme: bool           # Whether README was loaded
    claude_md: bool        # Whether CLAUDE.md was loaded
    raw_srs: Optional[str]
    raw_readme: Optional[str]
    raw_claude_md: Optional[str]


# ============================================================================
# MAIN TOON SCHEMA
# ============================================================================

class TOONSchema(TypedDict, total=False):
    """Canonical TOON object produced by Level 1 context sync.

    This is the minimal yet complete structure passed from Level 1 to Level 3.
    All required fields must be present for a valid TOON.
    """

    # Required fields
    session_id: str                  # Unique session identifier
    timestamp: str                   # ISO-8601 timestamp (set at Level 1 completion)
    version: str                     # Schema version, always "1.0.0"
    complexity_score: int            # Project complexity: 1-10
    files_loaded_count: int          # How many context files were loaded
    context: ContextType             # Which files loaded and minimal content flags

    # Optional enrichment fields
    model_preferences: dict          # e.g. {"prefer_fast": True, "prefer_complex": False}
    execution_constraints: dict      # e.g. {"timeout_total": 120, "max_retries": 3}
    caching_metadata: dict           # e.g. {"cache_hit": True, "cache_age_hours": 2}


# ============================================================================
# REQUIRED / OPTIONAL FIELD REGISTRIES
# ============================================================================

TOON_REQUIRED_FIELDS: List[str] = [
    "session_id",
    "timestamp",
    "version",
    "complexity_score",
    "files_loaded_count",
    "context",
]

TOON_OPTIONAL_FIELDS: List[str] = [
    "model_preferences",
    "execution_constraints",
    "caching_metadata",
]

TOON_VERSION = "1.0.0"


# ============================================================================
# VALIDATION FUNCTION
# ============================================================================

def validate_toon(toon: dict) -> tuple:
    """Validate a TOON dict against the schema.

    Args:
        toon: Dict to validate

    Returns:
        (is_valid, error_list) tuple.
        is_valid is True only when error_list is empty.

    Usage:
        is_valid, errors = validate_toon(toon_dict)
        if not is_valid:
            for err in errors:
                print(err)
    """
    errors: List[str] = []

    # 1. Must be a dict
    if not isinstance(toon, dict):
        return False, ["TOON must be a dict, got: " + type(toon).__name__]

    # 2. Check all required fields exist
    for field in TOON_REQUIRED_FIELDS:
        if field not in toon:
            errors.append("Missing required field: " + field)

    # 3. Validate individual field types and constraints

    # session_id: non-empty string
    if "session_id" in toon:
        if not isinstance(toon["session_id"], str) or not toon["session_id"].strip():
            errors.append("session_id must be a non-empty string")

    # timestamp: non-empty string (ISO format preferred but not enforced strictly)
    if "timestamp" in toon:
        if not isinstance(toon["timestamp"], str) or not toon["timestamp"].strip():
            errors.append("timestamp must be a non-empty string")
        else:
            # Try to parse as ISO timestamp
            try:
                datetime.fromisoformat(toon["timestamp"])
            except ValueError:
                errors.append(
                    "timestamp must be a valid ISO-8601 string, got: " + toon["timestamp"]
                )

    # version: must equal TOON_VERSION
    if "version" in toon:
        if not isinstance(toon["version"], str):
            errors.append("version must be a string")
        elif toon["version"] != TOON_VERSION:
            errors.append(
                "version must be '" + TOON_VERSION + "', got: " + str(toon["version"])
            )

    # complexity_score: int in range 1-10
    if "complexity_score" in toon:
        score = toon["complexity_score"]
        if not isinstance(score, int) or isinstance(score, bool):
            errors.append("complexity_score must be an int, got: " + type(score).__name__)
        elif not (1 <= score <= 10):
            errors.append(
                "complexity_score must be between 1 and 10, got: " + str(score)
            )

    # files_loaded_count: non-negative int
    if "files_loaded_count" in toon:
        count = toon["files_loaded_count"]
        if not isinstance(count, int) or isinstance(count, bool):
            errors.append(
                "files_loaded_count must be an int, got: " + type(count).__name__
            )
        elif count < 0:
            errors.append(
                "files_loaded_count must be >= 0, got: " + str(count)
            )

    # context: must be a dict
    if "context" in toon:
        ctx = toon["context"]
        if not isinstance(ctx, dict):
            errors.append("context must be a dict, got: " + type(ctx).__name__)
        else:
            # context.files must be a list
            if "files" in ctx and not isinstance(ctx["files"], list):
                errors.append("context.files must be a list")
            # boolean flags
            for flag in ("srs", "readme", "claude_md"):
                if flag in ctx and not isinstance(ctx[flag], bool):
                    errors.append("context." + flag + " must be a bool")

    # model_preferences: must be dict if present
    if "model_preferences" in toon and not isinstance(toon["model_preferences"], dict):
        errors.append("model_preferences must be a dict")

    # execution_constraints: must be dict if present
    if "execution_constraints" in toon and not isinstance(toon["execution_constraints"], dict):
        errors.append("execution_constraints must be a dict")

    # caching_metadata: must be dict if present
    if "caching_metadata" in toon and not isinstance(toon["caching_metadata"], dict):
        errors.append("caching_metadata must be a dict")

    return len(errors) == 0, errors


# ============================================================================
# FACTORY HELPER
# ============================================================================

def create_toon(
    session_id: str,
    complexity_score: int,
    files_loaded: List[str],
    has_srs: bool = False,
    has_readme: bool = False,
    has_claude_md: bool = False,
    model_preferences: Optional[Dict[str, Any]] = None,
    execution_constraints: Optional[Dict[str, Any]] = None,
    caching_metadata: Optional[Dict[str, Any]] = None,
) -> dict:
    """Create a valid TOON dict.

    Args:
        session_id: Unique session identifier
        complexity_score: 1-10 complexity score
        files_loaded: List of file labels loaded (e.g., ["SRS", "README"])
        has_srs: Whether SRS was loaded
        has_readme: Whether README was loaded
        has_claude_md: Whether CLAUDE.md was loaded
        model_preferences: Optional model preference overrides
        execution_constraints: Optional execution constraint overrides
        caching_metadata: Optional caching hints

    Returns:
        Valid TOONSchema-compliant dict
    """
    # Clamp complexity to valid range
    clamped_score = min(max(int(complexity_score), 1), 10)

    toon: dict = {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "version": TOON_VERSION,
        "complexity_score": clamped_score,
        "files_loaded_count": len(files_loaded),
        "context": {
            "files": list(files_loaded),
            "srs": has_srs,
            "readme": has_readme,
            "claude_md": has_claude_md,
        },
        "model_preferences": model_preferences or {},
        "execution_constraints": execution_constraints or {},
        "caching_metadata": caching_metadata or {},
    }
    return toon
