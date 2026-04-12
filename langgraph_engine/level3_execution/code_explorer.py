"""
Level 3 - Code Explorer

Standalone codebase exploration functions extracted from Level3RemainingSteps.
Provides tool-optimized file reading, grepping, and searching utilities.

WORKFLOW.md SPEC:
- Read: offset/limit (max 500 lines per file)
- Grep: head_limit (max 50 matches)
- Search: max_results optimization (max 10 results)
"""

from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

# Optional performance modules
try:
    from ..parallel_executor import run_parallel_step2_exploration

    _PERF_AVAILABLE = True
except ImportError:
    _PERF_AVAILABLE = False


def tool_read(
    file_path: str,
    offset: int = 0,
    limit: int = 500,
    base_path: Optional[Path] = None,
) -> str:
    """Simulate Claude's Read tool with offset/limit optimization.

    WORKFLOW.md SPEC: Read (with offset/limit for large files)

    Args:
        file_path: Path to file relative to base_path
        offset:    Starting line number (0-indexed)
        limit:     Maximum lines to read (max 500)
        base_path: Base directory for resolving relative paths.
                   Defaults to current working directory.

    Returns:
        File contents from offset to offset+limit
    """
    try:
        # Enforce limit (max 500 lines)
        if limit > 500:
            logger.warning(f"Read limit {limit} exceeds max 500, using 500")
            limit = 500

        root = base_path if base_path is not None else Path.cwd()
        full_path = root / file_path
        if not full_path.exists():
            return f"File not found: {file_path}"

        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        # Apply offset and limit
        start = min(offset, len(lines))
        end = min(start + limit, len(lines))
        selected_lines = lines[start:end]

        result = f"=== {file_path} (lines {start}-{end}) ===\n"
        result += "".join(selected_lines)
        return result

    except Exception as e:
        return f"Error reading {file_path}: {e}"


def tool_grep(
    pattern: str,
    glob_pattern: str = "**/*.py",
    head_limit: int = 20,
    base_path: Optional[Path] = None,
) -> str:
    """Simulate Claude's Grep tool with head_limit optimization.

    WORKFLOW.md SPEC: Grep (with head_limit)

    Args:
        pattern:      Regex pattern to search for
        glob_pattern: File glob pattern (e.g., "**/*.py")
        head_limit:   Maximum matches to return (max 50)
        base_path:    Base directory for the search.
                      Defaults to current working directory.

    Returns:
        List of matching files and lines
    """
    try:
        # Enforce head_limit (max 50)
        if head_limit > 50:
            logger.warning(f"Grep head_limit {head_limit} exceeds max 50, using 50")
            head_limit = 50

        root = base_path if base_path is not None else Path.cwd()
        matches: List[str] = []
        match_count = 0

        for file_path in root.glob(glob_pattern):
            if not file_path.is_file():
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if pattern.lower() in line.lower():
                            rel_path = file_path.relative_to(root)
                            matches.append(f"{rel_path}:{line_num}: {line.strip()}")
                            match_count += 1
                            if match_count >= head_limit:
                                break
            except Exception:
                pass

            if match_count >= head_limit:
                break

        result = f"=== Grep: {pattern} ({match_count} matches, limit {head_limit}) ===\n"
        result += "\n".join(matches[:head_limit])
        return result

    except Exception as e:
        return f"Error in grep: {e}"


def tool_search(
    query: str,
    max_results: int = 10,
    base_path: Optional[Path] = None,
) -> str:
    """Simulate Claude's Search tool with optimization.

    WORKFLOW.md SPEC: Search (with optimization)

    Args:
        query:       Search query
        max_results: Maximum results to return (capped at 10)
        base_path:   Base directory for the search.
                     Defaults to current working directory.

    Returns:
        List of relevant files and match counts
    """
    try:
        # Limit results
        max_results = min(max_results, 10)

        root = base_path if base_path is not None else Path.cwd()
        keywords = query.lower().split()[:5]  # Take first 5 keywords
        results: Dict[str, int] = {}

        # Search for files matching keywords
        for file_path in root.rglob("*.py"):
            if not file_path.is_file():
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Count keyword matches
                matches = sum(content.lower().count(kw) for kw in keywords)
                if matches > 0:
                    rel_path = file_path.relative_to(root)
                    results[str(rel_path)] = matches

            except Exception:
                pass

        # Sort by match count and return top results
        sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
        result = f"=== Search: {query} ({len(sorted_results)} matches) ===\n"
        result += "\n".join(f"{path}: {count} matches" for path, count in sorted_results[:max_results])
        return result

    except Exception as e:
        return f"Error in search: {e}"


def explore_codebase(
    user_requirement: str,
    project_root: str,
    base_path: Optional[Path] = None,
) -> str:
    """Explore codebase using tool-optimized methods (Read, Grep, Search).

    When parallel_executor is available, runs 3+ exploration tasks concurrently
    for ~50% speedup over sequential execution.

    WORKFLOW.md SPEC: Use exploration tools (Read, Grep, Search)
    - Read: offset/limit (max 500 lines per file)
    - Grep: head_limit (max 50 matches)
    - Search: max_results optimization

    Args:
        user_requirement: User's requirement to search for related code
        project_root:     Root directory to explore
        base_path:        Optional override for the search base path.

    Returns:
        String containing exploration results from tool calls
    """
    resolved_root = Path(project_root) if project_root else (base_path or Path.cwd())

    # Bind helpers with the resolved root so callers don't need to pass it
    def _read(fp: str, offset: int = 0, limit: int = 500) -> str:
        return tool_read(fp, offset=offset, limit=limit, base_path=resolved_root.parent)

    def _grep(pattern: str, glob_pattern: str = "**/*.py", head_limit: int = 20) -> str:
        return tool_grep(pattern, glob_pattern=glob_pattern, head_limit=head_limit, base_path=resolved_root)

    def _search(query: str, max_results: int = 10) -> str:
        return tool_search(query, max_results=max_results, base_path=resolved_root)

    # --- Parallel path (preferred) ---
    if _PERF_AVAILABLE:
        try:
            key_files = find_key_files(str(resolved_root))
            result = run_parallel_step2_exploration(
                user_requirement=user_requirement,
                project_root=str(resolved_root),
                search_fn=_search,
                grep_fn=_grep,
                read_fn=_read,
                key_files=key_files,
                max_workers=3,
            )
            structure = analyze_directory_structure(str(resolved_root))
            result += "\n\n=== PROJECT STRUCTURE ===\n" + structure
            logger.info("Codebase exploration completed (parallel mode)")
            return result
        except Exception as par_err:
            logger.warning(f"Parallel exploration failed ({par_err}), falling back to sequential")

    # --- Sequential fallback ---
    try:
        analysis_parts: List[str] = []

        # 1. Search for relevant files (TOOL: Search)
        logger.info("-> Searching for relevant files...")
        analysis_parts.append("=== SEARCH RESULTS ===")
        search_result = _search(user_requirement, max_results=10)
        analysis_parts.append(search_result)

        # 2. Grep for keyword matches (TOOL: Grep with head_limit)
        logger.info("-> Finding code patterns...")
        analysis_parts.append("\n=== CODE PATTERNS (Grep with head_limit=20) ===")
        keywords = user_requirement.lower().split()[:3]
        if keywords:
            for keyword in keywords:
                grep_result = _grep(keyword, glob_pattern="**/*.py", head_limit=20)
                analysis_parts.append(grep_result)
        else:
            analysis_parts.append("(No keywords to search)")

        # 3. Read key files (TOOL: Read with offset/limit)
        logger.info("-> Reading key file contents...")
        analysis_parts.append("\n=== KEY FILE CONTENTS (Read with limit=500) ===")
        key_files = find_key_files(str(resolved_root))
        for _file_type, files in key_files.items():
            if files:
                for file_path in files[:2]:  # Read first 2 key files
                    try:
                        read_result = _read(file_path, offset=0, limit=500)
                        analysis_parts.append(f"\n{read_result}")
                    except Exception as e:
                        logger.debug(f"Could not read {file_path}: {e}")

        # 4. Project structure (informational)
        analysis_parts.append("\n=== PROJECT STRUCTURE ===")
        structure = analyze_directory_structure(str(resolved_root))
        analysis_parts.append(structure)

        logger.info("Codebase exploration completed (sequential mode)")
        return "\n".join(analysis_parts)

    except Exception as e:
        logger.warning(f"Codebase exploration partial: {e}")
        return f"Could not fully explore codebase: {str(e)}"


def analyze_directory_structure(root: str, max_depth: int = 2) -> str:
    """Analyze directory structure.

    Args:
        root:      Root directory path as string
        max_depth: Maximum depth to traverse (currently depth-1 only)

    Returns:
        Formatted string listing directories and file counts
    """
    try:
        root_path = Path(root)
        if not root_path.exists():
            return f"Directory not found: {root}"

        lines: List[str] = []
        lines.append(f"Root: {root_path.name}/")

        # List key directories
        for item in sorted(root_path.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                lines.append(f"  {item.name}/")
                file_count = len(list(item.glob("*.*")))
                if file_count > 0:
                    lines.append(f"      ({file_count} files)")

        return "\n".join(lines[:20])  # Limit output
    except Exception as e:
        return f"Structure analysis failed: {e}"


def find_relevant_files(requirement: str, root: str) -> List[str]:
    """Find files related to the requirement using keyword matching.

    Args:
        requirement: User requirement string used for keyword extraction
        root:        Root directory path to search within

    Returns:
        List of relative file paths (up to 10) that match requirement keywords
    """
    try:
        root_path = Path(root)
        if not root_path.exists():
            return []

        relevant: List[str] = []
        keywords = requirement.lower().split()[:5]  # Get first 5 keywords

        # Search for source files with matching names or content
        for pattern in ["*.py", "*.java", "*.js", "*.ts", "*.go"]:
            for file_path in root_path.rglob(pattern):
                if file_path.is_file() and ".git" not in str(file_path):
                    filename_lower = file_path.name.lower()
                    for keyword in keywords:
                        if keyword in filename_lower and len(keyword) > 2:
                            relevant.append(str(file_path.relative_to(root_path)))
                            break

        return list(set(relevant))[:10]
    except Exception as e:
        logger.debug(f"File search failed: {e}")
        return []


def detect_project_patterns(root: str) -> str:
    """Detect programming language and architectural patterns.

    Args:
        root: Root directory path to inspect

    Returns:
        Formatted string describing detected patterns and languages
    """
    try:
        root_path = Path(root)
        patterns: List[str] = []

        # Check file extensions
        extensions: Dict[str, int] = {}
        for file_path in root_path.rglob("*.*"):
            if ".git" not in str(file_path):
                ext = file_path.suffix
                extensions[ext] = extensions.get(ext, 0) + 1

        # Identify primary language
        language_map = {
            ".py": "Python",
            ".java": "Java",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".go": "Go",
            ".rs": "Rust",
        }

        primary_lang = None
        max_count = 0
        for ext, lang in language_map.items():
            if extensions.get(ext, 0) > max_count:
                max_count = extensions[ext]
                primary_lang = lang

        if primary_lang:
            patterns.append(f"Primary Language: {primary_lang} ({max_count} files)")

        # Check for common frameworks/tools
        for name in ["requirements.txt", "package.json", "go.mod", "Cargo.toml", "pom.xml"]:
            if (root_path / name).exists():
                patterns.append(f"Found: {name} (dependency manifest)")

        for name in [".git", "docker-compose.yml", "Dockerfile", ".github"]:
            if (root_path / name).exists():
                patterns.append(f"Found: {name}")

        return "\n".join(patterns) if patterns else "No specific patterns detected"

    except Exception as e:
        return f"Pattern detection incomplete: {e}"


def find_key_files(root: str) -> Dict[str, List[str]]:
    """Find key architectural files (config, main, test, documentation).

    Args:
        root: Root directory path to inspect

    Returns:
        Dictionary mapping category names to lists of relative file paths
    """
    try:
        root_path = Path(root)
        key_files: Dict[str, List[str]] = {
            "Config": [],
            "Main/Entry": [],
            "Tests": [],
            "Documentation": [],
        }

        config_patterns = ["config.py", "settings.py", "requirements.txt", ".env"]
        main_patterns = ["main.py", "app.py", "index.py", "main.java", "app.js"]
        test_patterns = ["test_*.py", "*_test.py", "*.test.js", "*Test.java"]
        doc_patterns = ["README.md", "ARCHITECTURE.md", "DESIGN.md"]

        for pattern in config_patterns:
            files = list(root_path.rglob(pattern))
            key_files["Config"].extend([f.relative_to(root_path).as_posix() for f in files])

        for pattern in main_patterns:
            files = list(root_path.rglob(pattern))
            key_files["Main/Entry"].extend([f.relative_to(root_path).as_posix() for f in files])

        for pattern in test_patterns:
            files = list(root_path.rglob(pattern))
            key_files["Tests"].extend([f.relative_to(root_path).as_posix() for f in files])

        for pattern in doc_patterns:
            files = list(root_path.rglob(pattern))
            key_files["Documentation"].extend([f.relative_to(root_path).as_posix() for f in files])

        return key_files
    except Exception:
        return {k: [] for k in ["Config", "Main/Entry", "Tests", "Documentation"]}


def extract_code_snippets(
    file_paths: List[str],
    max_files: int = 3,
    base_path: Optional[Path] = None,
) -> str:
    """Extract relevant code snippets from files.

    Reads the first 15 lines (imports, class/function definitions) of each file
    to give the LLM quick context about the codebase structure.

    Args:
        file_paths: List of relative file paths to read
        max_files:  Maximum number of files to include
        base_path:  Base directory for resolving relative paths.
                    Defaults to current working directory.

    Returns:
        Concatenated code snippets as a formatted string
    """
    try:
        root = base_path if base_path is not None else Path.cwd()
        snippets: List[str] = []
        for file_path in file_paths[:max_files]:
            try:
                full_path = root / file_path
                if full_path.exists() and full_path.is_file():
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        # Get first 15 lines (imports, class/function defs)
                        snippet = "".join(lines[:15])
                        if len(snippet) > 200:
                            snippet = snippet[:200] + "..."
                        snippets.append(f"\n### {file_path}:\n{snippet}")
            except Exception:
                pass

        return "".join(snippets) if snippets else "(No code snippets available)"
    except Exception as e:
        return f"Code extraction failed: {e}"
