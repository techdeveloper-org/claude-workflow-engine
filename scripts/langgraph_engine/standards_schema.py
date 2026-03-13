"""
Standards Schema - Defines the required format for standard definition files.

Standard files are Markdown documents with a YAML front-matter block.
This module:
  - Defines the expected schema (REQUIRED_FIELDS, valid types, sub-structure)
  - Provides StandardsSchema.validate() for schema checking
  - Provides parse_standard_file() to read a .md file and extract the front-matter
  - Provides build_standard_dict() to create a standards dict programmatically

Expected .md front-matter format:

  ---
  version: "1.0.0"
  project_type: "python"
  framework: "flask"
  enforced: true
  deprecated: false
  rules:
    naming:
      functions: "snake_case"
      classes: "PascalCase"
      constants: "UPPER_SNAKE_CASE"
    code_style:
      max_line_length: 100
      imports: "sorted"
      docstrings: "google"
    testing:
      required: true
      framework: "pytest"
      min_coverage: 0.80
  ---
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# yaml is optional; we fall back to a lightweight regex parser if unavailable
try:
    import yaml  # type: ignore
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


# ============================================================================
# SCHEMA DEFINITION
# ============================================================================

VALID_PROJECT_TYPES = {"python", "java", "javascript", "typescript", "go", "rust", "csharp", "any"}
VALID_FRAMEWORKS = {
    "flask", "django", "fastapi", "pyramid",
    "spring", "spring-boot", "quarkus", "micronaut",
    "react", "angular", "vue", "nextjs", "express", "fastify", "nestjs",
    "any", "unknown",
}

RULES_SUBKEYS = {
    "naming": dict,
    "code_style": dict,
    "testing": dict,
    "structure": dict,
    "security": dict,
    "documentation": dict,
}


# ============================================================================
# STANDARDS SCHEMA CLASS
# ============================================================================

class StandardsSchema:
    """Validates a parsed standard dict against the required schema."""

    REQUIRED_FIELDS = ["version", "project_type", "enforced", "rules"]

    # Type map for top-level fields
    FIELD_TYPES: Dict[str, type] = {
        "version": str,
        "project_type": str,
        "framework": str,
        "enforced": bool,
        "deprecated": bool,
        "rules": dict,
    }

    def validate(self, standard_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate a standard dict against the schema.

        Checks:
          1. All REQUIRED_FIELDS are present.
          2. Each field has the expected type.
          3. ``project_type`` is one of the known values (or "any").
          4. ``framework`` (optional) is one of the known values.
          5. ``rules`` contains at least one recognised sub-key.
          6. ``version`` matches semver-like pattern X.Y.Z.

        Args:
            standard_dict: Parsed dict from a standard .md file.

        Returns:
            Tuple of (is_valid: bool, error_list: List[str]).
        """
        errors: List[str] = []

        if not isinstance(standard_dict, dict):
            return False, ["standard_dict must be a dict, got " + type(standard_dict).__name__]

        # 1. Required fields present
        for field in self.REQUIRED_FIELDS:
            if field not in standard_dict:
                errors.append(f"Missing required field: '{field}'")

        # 2. Type checks for present fields
        for field, expected_type in self.FIELD_TYPES.items():
            if field in standard_dict:
                value = standard_dict[field]
                if not isinstance(value, expected_type):
                    errors.append(
                        f"Field '{field}' must be {expected_type.__name__}, "
                        f"got {type(value).__name__}"
                    )

        # 3. project_type value check
        project_type = standard_dict.get("project_type")
        if isinstance(project_type, str) and project_type not in VALID_PROJECT_TYPES:
            errors.append(
                f"'project_type' must be one of {sorted(VALID_PROJECT_TYPES)}, "
                f"got '{project_type}'"
            )

        # 4. framework value check (optional field)
        framework = standard_dict.get("framework")
        if framework is not None and isinstance(framework, str) and framework not in VALID_FRAMEWORKS:
            # Non-fatal - just warn
            errors.append(
                f"'framework' value '{framework}' is not in the known list "
                f"{sorted(VALID_FRAMEWORKS)}. Add it to VALID_FRAMEWORKS if intentional."
            )

        # 5. rules sub-key check
        rules = standard_dict.get("rules")
        if isinstance(rules, dict):
            if len(rules) == 0:
                errors.append("'rules' dict must contain at least one rule sub-key")
            for sub_key, sub_value in rules.items():
                if sub_key in RULES_SUBKEYS:
                    expected = RULES_SUBKEYS[sub_key]
                    if not isinstance(sub_value, expected):
                        errors.append(
                            f"rules.{sub_key} must be {expected.__name__}, "
                            f"got {type(sub_value).__name__}"
                        )

        # 6. version semver check
        version = standard_dict.get("version")
        if isinstance(version, str):
            if not re.match(r"^\d+\.\d+\.\d+$", version):
                errors.append(
                    f"'version' should follow semver (X.Y.Z), got '{version}'"
                )

        is_valid = len(errors) == 0
        return is_valid, errors


# ============================================================================
# FRONT-MATTER PARSER
# ============================================================================

def _extract_front_matter(content: str) -> Tuple[Optional[str], str]:
    """Extract YAML front-matter block from a Markdown string.

    Looks for content between the first ``---`` and the second ``---``.

    Args:
        content: Full file content.

    Returns:
        Tuple of (yaml_block_str or None, remaining_markdown_str).
    """
    lines = content.splitlines()

    if not lines or lines[0].strip() != "---":
        return None, content

    end_index: Optional[int] = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = i
            break

    if end_index is None:
        return None, content

    yaml_block = "\n".join(lines[1:end_index])
    remaining = "\n".join(lines[end_index + 1:])
    return yaml_block, remaining


def _parse_yaml_block(yaml_str: str) -> Dict[str, Any]:
    """Parse a YAML string into a dict.

    Uses the ``yaml`` library when available. Falls back to a minimal
    key: value regex parser for simple flat structures.

    Args:
        yaml_str: YAML text.

    Returns:
        Parsed dict (best-effort on fallback).
    """
    if _YAML_AVAILABLE:
        try:
            result = yaml.safe_load(yaml_str)
            return result if isinstance(result, dict) else {}
        except Exception:
            pass

    # Minimal fallback: handle simple key: value and key: "quoted"
    result: Dict[str, Any] = {}
    current_key: Optional[str] = None
    current_dict: Optional[Dict[str, Any]] = None

    for line in yaml_str.splitlines():
        stripped = line.rstrip()

        # Top-level keys (no leading spaces)
        top_match = re.match(r"^(\w+):\s*(.*)?$", stripped)
        if top_match and not stripped.startswith(" "):
            key = top_match.group(1)
            raw_val = top_match.group(2).strip() if top_match.group(2) else ""

            if raw_val == "" or raw_val == "{}":
                result[key] = {}
                current_key = key
                current_dict = result[key]
            elif raw_val.lower() == "true":
                result[key] = True
                current_key = None
                current_dict = None
            elif raw_val.lower() == "false":
                result[key] = False
                current_key = None
                current_dict = None
            else:
                # Strip surrounding quotes
                val = raw_val.strip('"').strip("'")
                result[key] = val
                current_key = key
                current_dict = None
            continue

        # Nested keys (2+ leading spaces)
        nested_match = re.match(r"^(\s+)(\w+):\s*(.*)?$", stripped)
        if nested_match and current_key:
            if current_dict is None:
                result[current_key] = {}
                current_dict = result[current_key]
            nested_key = nested_match.group(2)
            raw_val = nested_match.group(3).strip() if nested_match.group(3) else ""
            if raw_val.lower() == "true":
                current_dict[nested_key] = True
            elif raw_val.lower() == "false":
                current_dict[nested_key] = False
            else:
                try:
                    current_dict[nested_key] = float(raw_val) if "." in raw_val else int(raw_val)
                except ValueError:
                    current_dict[nested_key] = raw_val.strip('"').strip("'")

    return result


def parse_standard_file(file_path: str) -> Tuple[Dict[str, Any], List[str]]:
    """Read a standard .md file and extract its YAML front-matter.

    Args:
        file_path: Absolute path to the standard file.

    Returns:
        Tuple of:
          - parsed_dict: The front-matter as a Python dict (may be empty on failure)
          - errors: List of parse/validation error strings
    """
    path = Path(file_path)
    errors: List[str] = []

    if not path.exists():
        return {}, [f"File not found: {file_path}"]

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {}, [f"Could not read file: {exc}"]

    yaml_str, _ = _extract_front_matter(content)
    if yaml_str is None:
        errors.append("No YAML front-matter block found (file must start with ---)")
        return {}, errors

    parsed = _parse_yaml_block(yaml_str)
    if not parsed:
        errors.append("Front-matter block parsed to empty dict")
        return {}, errors

    # Run schema validation
    schema = StandardsSchema()
    is_valid, validation_errors = schema.validate(parsed)
    if not is_valid:
        errors.extend(validation_errors)

    return parsed, errors


# ============================================================================
# PROGRAMMATIC BUILDER
# ============================================================================

def build_standard_dict(
    version: str,
    project_type: str,
    rules: Dict[str, Any],
    framework: str = "any",
    enforced: bool = True,
    deprecated: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a standards dict programmatically (no file required).

    Args:
        version: Semver string, e.g. "1.0.0".
        project_type: One of VALID_PROJECT_TYPES.
        rules: Rules dict with sub-keys (naming, code_style, testing, etc.).
        framework: Framework name (default "any").
        enforced: Whether this standard is enforced (default True).
        deprecated: Whether this standard is deprecated (default False).
        extra: Any additional top-level fields to include.

    Returns:
        Standards dict ready for StandardsSchema.validate().
    """
    standard: Dict[str, Any] = {
        "version": version,
        "project_type": project_type,
        "framework": framework,
        "enforced": enforced,
        "deprecated": deprecated,
        "rules": rules,
    }

    if extra:
        standard.update(extra)

    return standard


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    # --- Example 1: validate a programmatically built standard ---
    sample = build_standard_dict(
        version="1.0.0",
        project_type="python",
        framework="flask",
        enforced=True,
        rules={
            "naming": {
                "functions": "snake_case",
                "classes": "PascalCase",
                "constants": "UPPER_SNAKE_CASE",
            },
            "code_style": {
                "max_line_length": 100,
                "imports": "sorted",
                "docstrings": "google",
            },
            "testing": {
                "required": True,
                "framework": "pytest",
                "min_coverage": 0.80,
            },
        },
    )

    schema = StandardsSchema()
    is_valid, errs = schema.validate(sample)
    print(f"Valid: {is_valid}")
    if errs:
        for e in errs:
            print(f"  ERROR: {e}")

    # --- Example 2: validation failure ---
    bad = {
        "version": "bad_version",
        "project_type": "cobol",
        "enforced": "yes",   # should be bool
        "rules": {},          # empty rules
    }

    is_valid2, errs2 = schema.validate(bad)
    print(f"\nBad standard valid: {is_valid2}")
    for e in errs2:
        print(f"  ERROR: {e}")
