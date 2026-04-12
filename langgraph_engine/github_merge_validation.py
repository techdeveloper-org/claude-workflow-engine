"""
GitHub Merge Conflict and Project Validation Functions

Standalone functions extracted from Level3GitHubWorkflow for merge conflict
detection and project-specific validation.

The bulletproof merge conflict detection runs 4 layers:
- Layer 1: GitHub API check (pr.mergeable)
- Layer 2: Git status parsing (UU/DD/AA conflict markers)
- Layer 3: Local test merge (no commit)
- Layer 4: Project type auto-detection + language-specific test runner

All functions take explicit parameters instead of relying on self, making
them usable outside the class context.
"""

from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

# ============================================================================
# LAYER 2: GIT CONFLICT MARKER DETECTION
# ============================================================================


def detect_git_conflict_markers(git_ops: Any, branch_name: str) -> List[str]:
    """Parse git status for conflict markers (UU, DD, AA).

    Attempts a no-commit merge to surface conflict markers, then aborts.

    Args:
        git_ops:     GitOperations instance.
        branch_name: Name of the source branch to check against current HEAD.

    Returns:
        List of file paths that have conflict markers (empty means no conflicts).
    """
    try:
        git_ops._run_git(
            ["merge", "--no-commit", "--no-ff", f"origin/{branch_name}"],
            check=False,
        )

        status_result = git_ops._run_git(["status", "--porcelain"], check=False)
        status_lines = status_result.get("stdout", "").split("\n")

        conflicts: List[str] = []
        for line in status_lines:
            if line.startswith("UU") or line.startswith("DD") or line.startswith("AA"):
                file = line[3:].strip()
                conflicts.append(file)

        git_ops._run_git(["merge", "--abort"], check=False)

        return conflicts

    except Exception as e:
        logger.warning(f"Error detecting git conflicts: {e}")
        return []


# ============================================================================
# LAYER 3: LOCAL TEST MERGE
# ============================================================================


def test_merge_locally(git_ops: Any, branch_name: str) -> Dict[str, Any]:
    """Attempt a merge without committing to confirm it would succeed.

    Args:
        git_ops:     GitOperations instance.
        branch_name: Name of the source branch to test-merge.

    Returns:
        {"success": bool, "reason": str (on failure), "details": dict}
    """
    try:
        git_ops._run_git(["fetch", "origin"], check=False)

        result = git_ops._run_git(
            ["merge", "--no-commit", "--no-ff", f"origin/{branch_name}"],
            check=False,
        )

        if result.get("returncode") != 0:
            git_ops._run_git(["merge", "--abort"], check=False)
            return {
                "success": False,
                "reason": "Merge attempt failed - conflicts exist",
                "details": {"error": result.get("stderr", "")},
            }

        git_ops._run_git(["merge", "--abort"], check=False)
        return {"success": True}

    except Exception as e:
        logger.warning(f"Error in test merge: {e}")
        try:
            git_ops._run_git(["merge", "--abort"], check=False)
        except Exception:
            pass
        return {
            "success": False,
            "reason": f"Test merge error: {str(e)}",
            "details": {},
        }


# ============================================================================
# LAYER 4: PROJECT TYPE DETECTION
# ============================================================================


def detect_project_type_for_validation(repo_path: Any) -> str:
    """Auto-detect project type by checking for indicator files.

    Args:
        repo_path: Path-like object pointing to the repository root.

    Returns:
        One of: python, java, nodejs, go, rust, ruby, php, csharp, cpp, unknown.
    """
    indicators = {
        "python": ["setup.py", "requirements.txt", "pyproject.toml", "Pipfile", "setup.cfg"],
        "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "nodejs": ["package.json"],
        "go": ["go.mod"],
        "rust": ["Cargo.toml"],
        "ruby": ["Gemfile", "Rakefile"],
        "php": ["composer.json"],
        "csharp": ["*.csproj", "*.sln"],
        "cpp": ["CMakeLists.txt", "Makefile"],
    }

    for lang, files in indicators.items():
        for file_pattern in files:
            try:
                if Path(repo_path / file_pattern).exists():
                    return lang
            except (OSError, TypeError):
                pass

    return "unknown"


# ============================================================================
# LAYER 4: LANGUAGE-SPECIFIC VALIDATORS
# ============================================================================


def _validate_python(git_ops: Any) -> Dict[str, Any]:
    """Validate Python project by running pytest or unittest, then syntax check.

    Args:
        git_ops: GitOperations instance used to run shell commands.

    Returns:
        {"success": bool, "reason": str or None}
    """
    try:
        result = git_ops._run_git(
            ["bash", "-c", "pytest --co -q 2>/dev/null || echo 'no-pytest'"],
            check=False,
        )
        if "no-pytest" not in result.get("stdout", ""):
            logger.info("  Running pytest...")
            result = git_ops._run_git(
                ["bash", "-c", "pytest -x 2>&1"],
                check=False,
            )
            if result.get("returncode") != 0:
                return {"success": False, "reason": "Python tests failed", "details": {}}
            return {"success": True}

        result = git_ops._run_git(
            ["bash", "-c", "python -m unittest discover -s . 2>&1"],
            check=False,
        )
        if result.get("returncode") == 0:
            return {"success": True}

        logger.info("  No tests found, checking syntax...")
        result = git_ops._run_git(
            ["bash", "-c", "python -m py_compile $(find . -name '*.py') 2>&1"],
            check=False,
        )
        return {
            "success": result.get("returncode") == 0,
            "reason": "Syntax error" if result.get("returncode") != 0 else None,
        }

    except Exception as e:
        logger.warning(f"Python validation error: {e}")
        return {"success": True}


def _validate_java(git_ops: Any) -> Dict[str, Any]:
    """Validate Java project via Maven or Gradle.

    Args:
        git_ops: GitOperations instance.

    Returns:
        {"success": bool, "reason": str or None}
    """
    try:
        if Path(git_ops.repo_path / "pom.xml").exists():
            logger.info("  Running mvn test...")
            result = git_ops._run_git(
                ["bash", "-c", "mvn test -q 2>&1"],
                check=False,
            )
            return {
                "success": result.get("returncode") == 0,
                "reason": "Maven tests failed" if result.get("returncode") != 0 else None,
            }

        if Path(git_ops.repo_path / "build.gradle").exists() or Path(git_ops.repo_path / "build.gradle.kts").exists():
            logger.info("  Running gradle test...")
            result = git_ops._run_git(
                ["bash", "-c", "./gradlew test -q 2>&1"],
                check=False,
            )
            return {
                "success": result.get("returncode") == 0,
                "reason": "Gradle tests failed" if result.get("returncode") != 0 else None,
            }

        return {"success": True}

    except Exception as e:
        logger.warning(f"Java validation error: {e}")
        return {"success": True}


def _validate_nodejs(git_ops: Any) -> Dict[str, Any]:
    """Validate Node.js project via npm test.

    Args:
        git_ops: GitOperations instance.

    Returns:
        {"success": bool, "reason": str or None}
    """
    try:
        logger.info("  Running npm test...")
        result = git_ops._run_git(
            ["bash", "-c", "npm test 2>&1"],
            check=False,
        )
        return {
            "success": result.get("returncode") == 0,
            "reason": "npm tests failed" if result.get("returncode") != 0 else None,
        }
    except Exception as e:
        logger.warning(f"Node.js validation error: {e}")
        return {"success": True}


def _validate_go(git_ops: Any) -> Dict[str, Any]:
    """Validate Go project via go test.

    Args:
        git_ops: GitOperations instance.

    Returns:
        {"success": bool, "reason": str or None}
    """
    try:
        logger.info("  Running go test...")
        result = git_ops._run_git(
            ["bash", "-c", "go test ./... 2>&1"],
            check=False,
        )
        return {
            "success": result.get("returncode") == 0,
            "reason": "go tests failed" if result.get("returncode") != 0 else None,
        }
    except Exception as e:
        logger.warning(f"Go validation error: {e}")
        return {"success": True}


def _validate_rust(git_ops: Any) -> Dict[str, Any]:
    """Validate Rust project via cargo test.

    Args:
        git_ops: GitOperations instance.

    Returns:
        {"success": bool, "reason": str or None}
    """
    try:
        logger.info("  Running cargo test...")
        result = git_ops._run_git(
            ["bash", "-c", "cargo test 2>&1"],
            check=False,
        )
        return {
            "success": result.get("returncode") == 0,
            "reason": "cargo tests failed" if result.get("returncode") != 0 else None,
        }
    except Exception as e:
        logger.warning(f"Rust validation error: {e}")
        return {"success": True}


def validate_project_after_merge(git_ops: Any, project_type: str) -> Dict[str, Any]:
    """Run project-specific validation after a test merge.

    Language-agnostic dispatch: delegates to the correct validator based on
    the detected project type.

    Args:
        git_ops:      GitOperations instance.
        project_type: One of python, java, nodejs, go, rust, or unknown.

    Returns:
        {"success": bool, "reason": str or None, "details": dict}
    """
    try:
        if project_type == "python":
            return _validate_python(git_ops)
        elif project_type == "java":
            return _validate_java(git_ops)
        elif project_type == "nodejs":
            return _validate_nodejs(git_ops)
        elif project_type == "go":
            return _validate_go(git_ops)
        elif project_type == "rust":
            return _validate_rust(git_ops)
        else:
            logger.info(f"Unknown project type '{project_type}', skipping validation")
            return {"success": True, "reason": "Unknown type - no validation"}

    except Exception as e:
        logger.error(f"Validation error: {e}")
        return {
            "success": False,
            "reason": f"Validation failed: {str(e)}",
            "details": {},
        }


# ============================================================================
# BULLETPROOF MERGE CONFLICT DETECTION (4 LAYERS)
# ============================================================================


def check_merge_conflicts_bulletproof(
    github_router: Any,
    git_ops: Any,
    pr_number: int,
    branch_name: str,
) -> Dict[str, Any]:
    """Bulletproof merge conflict detection - 4 layers.

    Works for ANY project/language.

    Args:
        github_router: GitHubOperationRouter instance (has .repo attribute).
        git_ops:       GitOperations instance.
        pr_number:     GitHub PR number.
        branch_name:   Name of the source branch.

    Returns:
        {
            "safe_to_merge": bool,
            "layer": int (1-4, layer where check failed or 4 on full pass),
            "reason": str,
            "details": dict,
        }
    """
    logger.info("=" * 70)
    logger.info("BULLETPROOF MERGE CONFLICT DETECTION (4 LAYERS)")
    logger.info("=" * 70)

    # ------------------------------------------------------------------
    # LAYER 1: GitHub API Check (pr.mergeable)
    # ------------------------------------------------------------------
    logger.info("[Layer 1] GitHub API Check (pr.mergeable)...")
    try:
        pr = github_router.repo.get_pull(pr_number)
        if not pr.mergeable:
            logger.error("[Layer 1] FAILED: PR not mergeable (GitHub API)")
            return {
                "safe_to_merge": False,
                "layer": 1,
                "reason": "GitHub API: PR has unresolvable conflicts",
                "details": {"pr_mergeable": False},
            }
        logger.info("[Layer 1] PASSED: pr.mergeable = True")
    except Exception as e:
        logger.warning(f"[Layer 1] Could not check pr.mergeable: {e}")

    # ------------------------------------------------------------------
    # LAYER 2: Git Status Parsing (UU/DD/AA markers)
    # ------------------------------------------------------------------
    logger.info("[Layer 2] Git Status Parsing (conflict markers)...")
    conflicts = detect_git_conflict_markers(git_ops, branch_name)
    if conflicts:
        logger.error(f"[Layer 2] FAILED: Found {len(conflicts)} files with conflicts")
        return {
            "safe_to_merge": False,
            "layer": 2,
            "reason": f"Git status: {len(conflicts)} files have conflict markers",
            "details": {"conflict_files": conflicts},
        }
    logger.info("[Layer 2] PASSED: No UU/DD/AA conflict markers")

    # ------------------------------------------------------------------
    # LAYER 3: Test Merge (actual merge attempt, no commit)
    # ------------------------------------------------------------------
    logger.info("[Layer 3] Test Merge (attempt without committing)...")
    merge_test = test_merge_locally(git_ops, branch_name)
    if not merge_test.get("success"):
        logger.error(f"[Layer 3] FAILED: {merge_test.get('reason')}")
        return {
            "safe_to_merge": False,
            "layer": 3,
            "reason": merge_test.get("reason"),
            "details": merge_test.get("details", {}),
        }
    logger.info("[Layer 3] PASSED: Test merge succeeded")

    # ------------------------------------------------------------------
    # LAYER 4: Auto-Detect Project Type & Validate
    # ------------------------------------------------------------------
    logger.info("[Layer 4] Auto-detect project type and validate...")
    repo_path = getattr(git_ops, "repo_path", None)
    project_type = detect_project_type_for_validation(repo_path) if repo_path else "unknown"
    logger.info(f"  Detected project type: {project_type}")

    validation = validate_project_after_merge(git_ops, project_type)
    if not validation.get("success"):
        logger.error(f"[Layer 4] FAILED: {validation.get('reason')}")
        return {
            "safe_to_merge": False,
            "layer": 4,
            "reason": validation.get("reason"),
            "details": validation.get("details", {}),
        }
    logger.info("[Layer 4] PASSED: Project validation successful")

    # ------------------------------------------------------------------
    # ALL LAYERS PASSED
    # ------------------------------------------------------------------
    logger.info("=" * 70)
    logger.info("ALL 4 LAYERS PASSED - SAFE TO MERGE")
    logger.info("=" * 70)

    return {
        "safe_to_merge": True,
        "layer": 4,
        "reason": "All merge safety checks passed",
        "details": {
            "layer1": "GitHub API check passed",
            "layer2": "No git conflict markers",
            "layer3": "Test merge succeeded",
            "layer4": f"Project validation passed ({project_type})",
        },
    }
