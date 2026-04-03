"""Level 2 Standards System - Shared helpers and utility functions.

Canonical location: langgraph_engine/level2_standards/helpers.py
Windows-safe: ASCII only, no Unicode characters.
"""

import json
import subprocess
import sys
from pathlib import Path

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
    from utils.path_resolver import get_claude_home, get_policies_dir

    _LEVEL2_POLICIES_DIR = get_policies_dir()
    _LEVEL2_CLAUDE_HOME = get_claude_home()
except ImportError:
    _LEVEL2_POLICIES_DIR = Path.home() / ".claude" / "policies"
    _LEVEL2_CLAUDE_HOME = Path.home() / ".claude"

try:
    from langgraph.graph import END, START, StateGraph  # noqa: F401

    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

try:
    from ..flow_state import FlowState
except ImportError:
    FlowState = dict  # type: ignore[misc,assignment]

try:
    from ..step_logger import write_level_log
except ImportError:

    def write_level_log(*args, **kwargs):
        pass


# ============================================================================
# STANDARDS LOADING (from actual policies/)
# ============================================================================


def load_policies_from_directory():
    """Load all policies from ~/claude/policies/ directories.

    Returns:
        Dict with loaded policies by level
    """
    try:
        policies_dir = _LEVEL2_POLICIES_DIR

        if not policies_dir.exists():
            return {"level1": {}, "level2": {}, "level3": {}, "status": "NO_POLICIES_DIR"}

        result = {"level1": {}, "level2": {}, "level3": {}, "status": "LOADED"}

        # Load from each level directory
        for level_dir in ["01-sync-system", "02-standards-system", "03-execution-system"]:
            level_key = "level1" if "01" in level_dir else ("level2" if "02" in level_dir else "level3")
            level_path = policies_dir / level_dir

            if level_path.exists():
                for policy_file in level_path.glob("**/*.md"):
                    try:
                        content = policy_file.read_text(encoding="utf-8")
                        result[level_key][policy_file.stem] = {
                            "file": str(policy_file),
                            "size": len(content),
                            "path": policy_file.stem,
                        }
                    except Exception:
                        pass

        return result

    except Exception as e:
        return {"error": str(e), "status": "ERROR"}


def run_standards_loader_script():
    """Run standards-loader.py script."""
    try:
        scripts_dir = Path(__file__).parent.parent.parent
        script_path = scripts_dir / "architecture" / "02-standards-system" / "standards-loader.py"

        if not script_path.exists():
            return {"status": "SCRIPT_NOT_FOUND"}

        # Run script with UTF-8 encoding for Windows compatibility
        result = subprocess.run(
            [sys.executable, str(script_path), "--load-all"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            cwd=scripts_dir,
        )

        # Parse output
        try:
            return json.loads(result.stdout)
        except Exception:
            return {"status": "SUCCESS", "exit_code": result.returncode, "message": result.stdout[:500]}

    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "error": "standards-loader.py timed out"}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def detect_project_type(state):
    """Detect project type (Java, Python, etc.)."""
    try:
        project_root = Path(state.get("project_root", "."))

        # Java detection
        has_pom = (project_root / "pom.xml").exists()
        has_gradle = (project_root / "build.gradle").exists() or (project_root / "build.gradle.kts").exists()
        java_files = list(project_root.glob("**/*.java"))[:5]

        state["is_java_project"] = bool(has_pom or has_gradle or java_files)

    except Exception:
        state["is_java_project"] = False


# ============================================================================
# LINTER UTILITIES
# ============================================================================


def _run_linter(cmd, timeout=15):
    """Run a subprocess command and return the result, or None on any error."""
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except Exception:
        return None


def _detect_linter():
    """Detect the first available Python linter.

    Returns (linter_name, version_cmd) or (None, None) if none found.
    """
    # Try ruff first (modern, fast)
    result = _run_linter(["ruff", "--version"])
    if result is not None and result.returncode == 0:
        return "ruff", ["ruff"]

    # Fallback to flake8
    result = _run_linter(["flake8", "--version"])
    if result is not None and result.returncode == 0:
        return "flake8", ["flake8"]

    return None, None


def _run_ruff_check(project_root):
    """Run ruff on the project src/ directory and return up to 20 violations."""
    src_path = str(Path(project_root) / "src")
    if not Path(src_path).exists():
        src_path = project_root

    result = _run_linter(
        [
            "ruff",
            "check",
            src_path,
            "--output-format",
            "json",
            "--select",
            "E,W,F",
        ],
        timeout=15,
    )

    if result is None:
        return []

    try:
        violations_raw = json.loads(result.stdout or "[]")
    except (json.JSONDecodeError, ValueError):
        return []

    violations = []
    for item in violations_raw[:20]:
        violations.append(
            {
                "file": item.get("filename", ""),
                "line": item.get("location", {}).get("row", 0),
                "code": item.get("code", ""),
                "message": item.get("message", ""),
                "severity": "warning" if (item.get("code", "") or "").startswith("W") else "error",
            }
        )
    return violations


def _run_flake8_check(project_root):
    """Run flake8 on the project src/ directory and return up to 20 violations."""
    src_path = str(Path(project_root) / "src")
    if not Path(src_path).exists():
        src_path = project_root

    result = _run_linter(
        [
            "flake8",
            src_path,
            "--format",
            "%(path)s:%(row)d:%(col)d: %(code)s %(text)s",
            "--select",
            "E,W,F",
            "--max-line-length",
            "120",
        ],
        timeout=15,
    )

    if result is None:
        return []

    violations = []
    for line in (result.stdout or "").splitlines()[:20]:
        # Format: path:row:col: CODE message
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        try:
            rest = parts[3].strip()
            code_and_msg = rest.split(" ", 1)
            code = code_and_msg[0] if code_and_msg else ""
            message = code_and_msg[1] if len(code_and_msg) > 1 else rest
            violations.append(
                {
                    "file": parts[0],
                    "line": int(parts[1]),
                    "code": code,
                    "message": message,
                    "severity": "warning" if code.startswith("W") else "error",
                }
            )
        except (ValueError, IndexError):
            continue
    return violations
