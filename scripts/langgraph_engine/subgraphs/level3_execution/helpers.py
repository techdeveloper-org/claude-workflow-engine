"""
Level 3 Execution - Shared helpers, module-level constants, and script runner.
"""

import json
import subprocess
import sys
from pathlib import Path

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent / "src"))
    from utils.path_resolver import get_agents_dir, get_skills_dir

    _LEVEL3_SKILLS_DIR = get_skills_dir()
    _LEVEL3_AGENTS_DIR = get_agents_dir()
except ImportError:
    _LEVEL3_SKILLS_DIR = Path.home() / ".claude" / "skills"
    _LEVEL3_AGENTS_DIR = Path.home() / ".claude" / "agents"

try:
    from langgraph.graph import END, START, StateGraph  # noqa: F401

    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False


# ============================================================================
# SCRIPT EXECUTION HELPER
# ============================================================================


def call_execution_script(script_name: str, args: list = None, model_tier: str = None) -> dict:
    """Call a Level 3 execution script and return parsed output.

    Args:
        script_name: Name of the script (without .py) in architecture/03-execution-system/
        args: Command-line arguments to pass
        model_tier: Optional model tier ('fast', 'balanced', 'quality') passed via MODEL_TIER env var
    """
    import os

    DEBUG = os.getenv("CLAUDE_DEBUG") == "1"

    try:
        scripts_dir = Path(__file__).parent.parent.parent.parent
        # Try new level-based location first
        script_path = Path(__file__).parent.parent.parent / "level3_execution" / "architecture" / f"{script_name}.py"
        if not script_path.exists():
            # Fallback to legacy location
            script_path = scripts_dir / "architecture" / "03-execution-system" / f"{script_name}.py"

        if DEBUG:
            print(f"[L3-DEBUG] Finding script: {script_name}", file=sys.stderr)

        # Try variations if exact path not found
        if not script_path.exists():
            arch_dir = Path(__file__).parent.parent.parent / "level3_execution" / "architecture"
            found = list(arch_dir.glob(f"**/{script_name}*.py")) if arch_dir.exists() else []
            if not found:
                legacy_dir = scripts_dir / "architecture" / "03-execution-system"
                found = list(legacy_dir.glob(f"**/{script_name}*.py")) if legacy_dir.exists() else []
            if found:
                script_path = found[0]
            else:
                if DEBUG:
                    print(f"[L3-DEBUG] Script not found: {script_name}", file=sys.stderr)
                return {"status": "SCRIPT_NOT_FOUND", "script": script_name}

        # Run script
        cmd = [sys.executable, str(script_path)]
        if args:
            cmd.extend(args)

        if DEBUG:
            print(f"[L3-DEBUG] Running: {script_name}", file=sys.stderr)

        # Build env with optional MODEL_TIER
        env = os.environ.copy()
        if model_tier:
            env["MODEL_TIER"] = model_tier

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            cwd=scripts_dir,
            env=env,
        )

        if DEBUG:
            print(f"[L3-DEBUG] {script_name} returned: {result.returncode}", file=sys.stderr)

        # Parse output
        if result.stdout:
            try:
                return json.loads(result.stdout)
            except Exception:
                return {"status": "SUCCESS", "exit_code": result.returncode, "output": result.stdout[:300]}

        return {"status": "SUCCESS" if result.returncode == 0 else "FAILED", "exit_code": result.returncode}

    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT"}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


# ============================================================================
# SHARED CONTEXT DETECTION HELPERS
# ============================================================================


def _extract_modified_files(llm_response: str, project_root: str = ".") -> list:
    """Extract file paths mentioned in LLM response as modified/created.

    Parses the LLM output for file path patterns like:
    - File: src/main.py
    - Modified: src/config.py
    - Created: tests/test_new.py
    - ```python path/to/file.py
    - lines mentioning .py, .js, .ts, .java, .go, .rs extensions with path separators

    Args:
        llm_response: Full LLM response text
        project_root: Project root for validation

    Returns:
        List of unique file paths found (deduplicated, max 50)
    """
    import re

    if not llm_response:
        return []

    found = set()

    # Pattern 1: Explicit file mentions (File: X, Modified: X, Created: X, Updated: X)
    explicit_re = re.compile(
        r'(?:^|\n)\s*(?:File|Modified|Created|Updated|Edited|Changed|Wrote)\s*[:=]\s*[`"]?([^\s`"]+\.\w{1,5})[`"]?',
        re.IGNORECASE,
    )
    for m in explicit_re.finditer(llm_response):
        found.add(m.group(1))

    # Pattern 2: Code block headers (```lang path/to/file.ext)
    codeblock_re = re.compile(r"```\w*\s+([^\s`]+\.\w{1,5})")
    for m in codeblock_re.finditer(llm_response):
        found.add(m.group(1))

    # Pattern 3: Path-like strings with common extensions
    path_re = re.compile(
        r'(?:^|\s|[`"\'])(\S*?/\S+\.(?:py|js|ts|jsx|tsx|java|go|rs|cpp|c|h|md|json|yaml|yml|toml|cfg|html|css|scss))\b',
        re.IGNORECASE,
    )
    for m in path_re.finditer(llm_response):
        candidate = m.group(1).strip("`\"'()[]{}")
        if "/" in candidate and len(candidate) < 200:
            found.add(candidate)

    # Filter: remove obvious non-files (URLs, imports, etc.)
    filtered = []
    for f in found:
        if f.startswith("http") or f.startswith("//") or f.startswith("#"):
            continue
        if ".." in f and "/" not in f:
            continue
        # Normalize backslashes
        f = f.replace("\\", "/")
        filtered.append(f)

    # Deduplicate and limit
    return sorted(set(filtered))[:50]


def _detect_project_type_from_files(project_root: str) -> str:
    """Detect project type from marker files in project root.

    Checks for common framework markers to determine the actual project type
    instead of returning a generic "Python/Node/Other".
    """
    from pathlib import Path

    root = Path(project_root) if project_root else Path(".")
    if not root.exists():
        return "Unknown"

    # Check for framework markers (order: most specific first)
    markers = [
        (["angular.json", "angular.cli.json"], "Angular"),
        (["next.config.js", "next.config.mjs", "next.config.ts"], "Next.js"),
        (["nuxt.config.js", "nuxt.config.ts"], "Nuxt.js"),
        (["svelte.config.js"], "SvelteKit"),
        (["vite.config.ts", "vite.config.js"], "Vite"),
        (["package.json"], None),  # Check later for React/Vue
        (["pom.xml", "build.gradle", "build.gradle.kts"], "Java/Spring"),
        (["Cargo.toml"], "Rust"),
        (["go.mod"], "Go"),
        (["Gemfile"], "Ruby"),
        (["composer.json"], "PHP"),
        (["requirements.txt", "setup.py", "pyproject.toml"], None),  # Check later for Flask/Django
        (["Dockerfile", "docker-compose.yml"], None),  # Not primary type
    ]

    for files, framework in markers:
        for f in files:
            if (root / f).exists():
                if framework:
                    return framework
                # Special handling for package.json
                if f == "package.json":
                    try:
                        import json as _json

                        pkg = _json.loads((root / f).read_text(encoding="utf-8"))
                        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                        if "react" in deps:
                            return "React"
                        if "vue" in deps:
                            return "Vue.js"
                        if "svelte" in deps:
                            return "Svelte"
                        return "Node.js"
                    except Exception:
                        return "Node.js"
                # Special handling for Python
                if f in ("requirements.txt", "setup.py", "pyproject.toml"):
                    try:
                        req_text = ""
                        if (root / "requirements.txt").exists():
                            req_text = (root / "requirements.txt").read_text(encoding="utf-8").lower()
                        if "flask" in req_text:
                            return "Python/Flask"
                        if "django" in req_text:
                            return "Python/Django"
                        if "fastapi" in req_text:
                            return "Python/FastAPI"
                        if "langgraph" in req_text or "langchain" in req_text:
                            return "Python/LangGraph"
                        return "Python"
                    except Exception:
                        return "Python"

    return "Unknown"


def _read_project_context_snippets(project_root: str, max_chars: int = 1500) -> tuple:
    """Read README and SRS file snippets for project context.

    Returns (readme_snippet, srs_snippet) - each max_chars long.
    """
    from pathlib import Path

    root = Path(project_root) if project_root else Path(".")
    readme_snippet = ""
    srs_snippet = ""

    if not root.exists():
        return "", ""

    # Read README
    for readme_name in ["README.md", "readme.md", "README.txt", "README"]:
        readme_file = root / readme_name
        if readme_file.exists():
            try:
                content = readme_file.read_text(encoding="utf-8", errors="ignore")
                readme_snippet = content[:max_chars]
                if len(content) > max_chars:
                    readme_snippet += "\n... (truncated)"
            except Exception:
                pass
            break

    # Read SRS
    for srs_name in ["SRS.md", "srs.md", "SRS.txt", "SRS.doc"]:
        srs_file = root / srs_name
        if srs_file.exists():
            try:
                content = srs_file.read_text(encoding="utf-8", errors="ignore")
                srs_snippet = content[:max_chars]
                if len(content) > max_chars:
                    srs_snippet += "\n... (truncated)"
            except Exception:
                pass
            break

    return readme_snippet, srs_snippet
