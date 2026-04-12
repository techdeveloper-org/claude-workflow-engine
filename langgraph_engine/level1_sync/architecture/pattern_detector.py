# -*- coding: utf-8 -*-
"""
pattern_detector.py - Level 1 Sync System: Technology Pattern Detector

Detects technology patterns from project files (package.json, pom.xml,
requirements.txt, etc.) and returns a list of detected tech-stack patterns.

Policy Reference: policies/01-sync-system/pattern-detection/cross-project-patterns-policy.md

Usage:
    python pattern_detector.py                      # Detect patterns in current dir
    python pattern_detector.py <project_root>       # Detect patterns in given dir
    python pattern_detector.py --json               # Output as JSON
    python pattern_detector.py --all-projects       # Scan all projects

Import usage:
    from pattern_detector import detect_patterns
    patterns = detect_patterns(project_root)
    # patterns -> ["python", "flask", "pytest", "docker", ...]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# ============================================================================
# PATTERN DEFINITIONS
# Each entry: (pattern_name, category, marker_files, keyword_hints)
# marker_files: presence of any of these files confirms the pattern
# keyword_hints: strings searched inside marker files to confirm
# ============================================================================

PATTERN_RULES: List[Dict[str, Any]] = [
    # ---------- Languages ----------
    {
        "name": "python",
        "category": "language",
        "marker_files": [
            "requirements.txt",
            "requirements-dev.txt",
            "Pipfile",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "tox.ini",
        ],
        "keyword_hints": [],
        "file_extensions": [".py"],
    },
    {
        "name": "javascript",
        "category": "language",
        "marker_files": ["package.json"],
        "keyword_hints": [],
        "file_extensions": [".js", ".mjs"],
    },
    {
        "name": "typescript",
        "category": "language",
        "marker_files": ["tsconfig.json", "tsconfig.base.json"],
        "keyword_hints": ["typescript"],
        "file_extensions": [".ts", ".tsx"],
    },
    {
        "name": "java",
        "category": "language",
        "marker_files": ["pom.xml", "build.gradle", "build.gradle.kts", "gradlew"],
        "keyword_hints": [],
        "file_extensions": [".java"],
    },
    {
        "name": "kotlin",
        "category": "language",
        "marker_files": ["build.gradle.kts"],
        "keyword_hints": ["kotlin"],
        "file_extensions": [".kt", ".kts"],
    },
    {
        "name": "go",
        "category": "language",
        "marker_files": ["go.mod", "go.sum"],
        "keyword_hints": [],
        "file_extensions": [".go"],
    },
    {
        "name": "rust",
        "category": "language",
        "marker_files": ["Cargo.toml", "Cargo.lock"],
        "keyword_hints": [],
        "file_extensions": [".rs"],
    },
    {
        "name": "ruby",
        "category": "language",
        "marker_files": ["Gemfile", "Gemfile.lock", ".ruby-version"],
        "keyword_hints": [],
        "file_extensions": [".rb"],
    },
    {
        "name": "csharp",
        "category": "language",
        "marker_files": [],
        "keyword_hints": [],
        "file_extensions": [".cs", ".csproj", ".sln"],
    },
    # ---------- Python Frameworks ----------
    {
        "name": "flask",
        "category": "framework",
        "marker_files": [],
        "keyword_hints": ["flask", "Flask"],
        "search_in": ["requirements.txt", "requirements-dev.txt", "Pipfile", "pyproject.toml"],
        "file_extensions": [],
    },
    {
        "name": "django",
        "category": "framework",
        "marker_files": ["manage.py"],
        "keyword_hints": ["django", "Django"],
        "search_in": ["requirements.txt", "requirements-dev.txt", "Pipfile", "pyproject.toml"],
        "file_extensions": [],
    },
    {
        "name": "fastapi",
        "category": "framework",
        "marker_files": [],
        "keyword_hints": ["fastapi", "FastAPI"],
        "search_in": ["requirements.txt", "requirements-dev.txt", "Pipfile", "pyproject.toml"],
        "file_extensions": [],
    },
    {
        "name": "sqlalchemy",
        "category": "library",
        "marker_files": [],
        "keyword_hints": ["sqlalchemy", "SQLAlchemy"],
        "search_in": ["requirements.txt", "requirements-dev.txt", "Pipfile", "pyproject.toml"],
        "file_extensions": [],
    },
    {
        "name": "pytest",
        "category": "testing",
        "marker_files": ["pytest.ini", "conftest.py"],
        "keyword_hints": ["pytest"],
        "search_in": ["requirements.txt", "requirements-dev.txt", "pyproject.toml"],
        "file_extensions": [],
    },
    # ---------- JavaScript / TypeScript Frameworks ----------
    {
        "name": "react",
        "category": "framework",
        "marker_files": [],
        "keyword_hints": ['"react"', '"react-dom"'],
        "search_in": ["package.json"],
        "file_extensions": [".jsx", ".tsx"],
    },
    {
        "name": "angular",
        "category": "framework",
        "marker_files": ["angular.json"],
        "keyword_hints": ['"@angular/core"'],
        "search_in": ["package.json"],
        "file_extensions": [],
    },
    {
        "name": "vue",
        "category": "framework",
        "marker_files": [],
        "keyword_hints": ['"vue"'],
        "search_in": ["package.json"],
        "file_extensions": [".vue"],
    },
    {
        "name": "nextjs",
        "category": "framework",
        "marker_files": ["next.config.js", "next.config.ts", "next.config.mjs"],
        "keyword_hints": ['"next"'],
        "search_in": ["package.json"],
        "file_extensions": [],
    },
    {
        "name": "express",
        "category": "framework",
        "marker_files": [],
        "keyword_hints": ['"express"'],
        "search_in": ["package.json"],
        "file_extensions": [],
    },
    {
        "name": "nestjs",
        "category": "framework",
        "marker_files": [],
        "keyword_hints": ['"@nestjs/core"'],
        "search_in": ["package.json"],
        "file_extensions": [],
    },
    # ---------- Java Frameworks ----------
    {
        "name": "spring-boot",
        "category": "framework",
        "marker_files": [],
        "keyword_hints": ["spring-boot", "SpringBoot", "spring-boot-starter"],
        "search_in": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "file_extensions": [],
    },
    {
        "name": "maven",
        "category": "build",
        "marker_files": ["pom.xml"],
        "keyword_hints": [],
        "file_extensions": [],
    },
    {
        "name": "gradle",
        "category": "build",
        "marker_files": ["build.gradle", "build.gradle.kts", "gradlew"],
        "keyword_hints": [],
        "file_extensions": [],
    },
    # ---------- Databases ----------
    {
        "name": "postgresql",
        "category": "database",
        "marker_files": [],
        "keyword_hints": [
            "postgresql",
            "postgres",
            "psycopg2",
            "pg8000",
            "asyncpg",
            "jdbc:postgresql",
            '"pg"',
            "Npgsql",
        ],
        "search_in": [
            "requirements.txt",
            "requirements-dev.txt",
            "Pipfile",
            "pyproject.toml",
            "package.json",
            "pom.xml",
            "build.gradle",
        ],
        "file_extensions": [],
    },
    {
        "name": "mysql",
        "category": "database",
        "marker_files": [],
        "keyword_hints": ["mysqlclient", "PyMySQL", "mysql-connector", "jdbc:mysql", '"mysql2"', "MySqlConnector"],
        "search_in": [
            "requirements.txt",
            "requirements-dev.txt",
            "Pipfile",
            "pyproject.toml",
            "package.json",
            "pom.xml",
            "build.gradle",
        ],
        "file_extensions": [],
    },
    {
        "name": "mongodb",
        "category": "database",
        "marker_files": [],
        "keyword_hints": ["pymongo", "motor", "mongoose", "mongodb", '"mongodb"', "MongoClient", "spring-data-mongodb"],
        "search_in": [
            "requirements.txt",
            "requirements-dev.txt",
            "Pipfile",
            "pyproject.toml",
            "package.json",
            "pom.xml",
            "build.gradle",
        ],
        "file_extensions": [],
    },
    {
        "name": "redis",
        "category": "database",
        "marker_files": [],
        "keyword_hints": ["redis", "aioredis", "ioredis", "spring-data-redis"],
        "search_in": [
            "requirements.txt",
            "requirements-dev.txt",
            "Pipfile",
            "pyproject.toml",
            "package.json",
            "pom.xml",
            "build.gradle",
        ],
        "file_extensions": [],
    },
    {
        "name": "sqlite",
        "category": "database",
        "marker_files": [],
        "keyword_hints": ["sqlite3", "aiosqlite", "better-sqlite3", "sqlite-jdbc"],
        "search_in": [
            "requirements.txt",
            "requirements-dev.txt",
            "pyproject.toml",
            "package.json",
            "pom.xml",
        ],
        "file_extensions": [".db", ".sqlite", ".sqlite3"],
    },
    # ---------- Auth ----------
    {
        "name": "jwt",
        "category": "authentication",
        "marker_files": [],
        "keyword_hints": [
            "jwt",
            "jsonwebtoken",
            "PyJWT",
            "python-jose",
            "flask-jwt",
            "jjwt",
            "io.jsonwebtoken",
        ],
        "search_in": [
            "requirements.txt",
            "requirements-dev.txt",
            "pyproject.toml",
            "package.json",
            "pom.xml",
            "build.gradle",
        ],
        "file_extensions": [],
    },
    {
        "name": "oauth",
        "category": "authentication",
        "marker_files": [],
        "keyword_hints": ["oauth", "OAuth", "authlib", "passport-oauth"],
        "search_in": [
            "requirements.txt",
            "requirements-dev.txt",
            "pyproject.toml",
            "package.json",
            "pom.xml",
        ],
        "file_extensions": [],
    },
    # ---------- DevOps ----------
    {
        "name": "docker",
        "category": "devops",
        "marker_files": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"],
        "keyword_hints": [],
        "file_extensions": [],
    },
    {
        "name": "kubernetes",
        "category": "devops",
        "marker_files": ["k8s", "kubernetes"],
        "keyword_hints": ["apiVersion:", "kind: Deployment", "kind: Service"],
        "search_in": [],
        "file_extensions": [".yaml", ".yml"],
    },
    {
        "name": "github-actions",
        "category": "ci",
        "marker_files": [],
        "keyword_hints": [],
        "dir_markers": [".github/workflows"],
    },
    {
        "name": "jenkins",
        "category": "ci",
        "marker_files": ["Jenkinsfile"],
        "keyword_hints": [],
        "file_extensions": [],
    },
]


# ============================================================================
# CORE FUNCTION
# ============================================================================


def detect_patterns(project_root: Optional[Path] = None) -> List[str]:
    """Detect technology patterns from project files in project_root.

    Inspects marker files, file extensions, and keyword hints to determine
    which technologies are present. Returns a deduplicated, sorted list of
    pattern names.

    Args:
        project_root: Root directory of the project to analyse.
                      Defaults to the current working directory.

    Returns:
        Sorted list of detected pattern name strings,
        e.g. ["docker", "fastapi", "postgresql", "python", "pytest"].
    """
    if project_root is None:
        project_root = Path.cwd()
    project_root = Path(project_root)

    detected: Set[str] = set()

    # Pre-read small text files that are commonly used as hint sources
    file_cache: Dict[str, str] = {}
    for rule in PATTERN_RULES:
        search_in = rule.get("search_in", [])
        for fname in search_in + rule.get("marker_files", []):
            if fname in file_cache:
                continue
            fpath = project_root / fname
            if fpath.is_file() and fpath.stat().st_size < 512_000:
                try:
                    file_cache[fname] = fpath.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    file_cache[fname] = ""

    for rule in PATTERN_RULES:
        name = rule["name"]

        # 1. Directory markers (e.g. .github/workflows)
        for dir_marker in rule.get("dir_markers", []):
            if (project_root / dir_marker).is_dir():
                detected.add(name)
                break

        if name in detected:
            continue

        # 2. Marker file presence (existence is enough)
        for marker_file in rule.get("marker_files", []):
            # Could be a file or a directory name
            candidate = project_root / marker_file
            if candidate.exists():
                detected.add(name)
                break

        if name in detected:
            continue

        # 3. File extension scanning (top-level + one level deep)
        for ext in rule.get("file_extensions", []):
            if _has_extension(project_root, ext, max_depth=2):
                detected.add(name)
                break

        if name in detected:
            continue

        # 4. Keyword hints in search_in files
        hints = rule.get("keyword_hints", [])
        if hints:
            search_in = rule.get("search_in", [])
            for fname in search_in:
                content = file_cache.get(fname, "")
                if content and any(hint in content for hint in hints):
                    detected.add(name)
                    break

    return sorted(detected)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _has_extension(root: Path, ext: str, max_depth: int = 2) -> bool:
    """Return True if any file with the given extension exists within max_depth."""
    ext_lower = ext.lower()
    try:
        for item in root.iterdir():
            if item.is_file() and item.suffix.lower() == ext_lower:
                return True
            if item.is_dir() and max_depth > 1:
                if _has_extension(item, ext, max_depth - 1):
                    return True
    except PermissionError:
        pass
    return False


def detect_patterns_detailed(
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Like detect_patterns but returns full metadata per detected pattern.

    Returns:
        A dict with:
            - patterns (list): Sorted list of detected pattern names.
            - by_category (dict): {category: [pattern_names]}.
            - project_root (str): Directory analysed.
            - total_detected (int): Count of detected patterns.
    """
    if project_root is None:
        project_root = Path.cwd()

    patterns = detect_patterns(project_root)

    # Build category map
    category_map: Dict[str, List[str]] = {}
    rule_lookup = {r["name"]: r["category"] for r in PATTERN_RULES}
    for p in patterns:
        cat = rule_lookup.get(p, "other")
        category_map.setdefault(cat, []).append(p)

    return {
        "patterns": patterns,
        "by_category": category_map,
        "project_root": str(project_root),
        "total_detected": len(patterns),
    }


# ============================================================================
# MULTI-PROJECT SCANNING
# ============================================================================


def scan_all_projects(
    projects_root: Optional[Path] = None,
) -> Dict[str, List[str]]:
    """Detect patterns across all projects under projects_root.

    Args:
        projects_root: Directory containing project subdirectories.
                       Defaults to current working directory's parent.

    Returns:
        Dict mapping project name -> list of detected patterns.
    """
    if projects_root is None:
        projects_root = Path.cwd().parent

    projects_root = Path(projects_root)
    results: Dict[str, List[str]] = {}

    if not projects_root.exists():
        return results

    for item in sorted(projects_root.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            try:
                patterns = detect_patterns(item)
                if patterns:
                    results[item.name] = patterns
            except Exception:
                pass

    return results


# ============================================================================
# CLI ENTRY POINT
# ============================================================================


def _print_human(detail: Dict[str, Any]) -> None:
    """Print a human-readable pattern detection report."""
    print("\nPattern Detection Report")
    print("=" * 50)
    print(f"  Project:   {detail['project_root']}")
    print(f"  Detected:  {detail['total_detected']} patterns\n")

    for category, names in sorted(detail["by_category"].items()):
        print(f"  [{category.upper()}]")
        for name in names:
            print(f"    - {name}")
    print()


def main() -> int:
    """CLI entry point for pattern_detector.py."""
    parser = argparse.ArgumentParser(description="Detect technology patterns from project files.")
    parser.add_argument(
        "project_root",
        nargs="?",
        default=None,
        help="Project root directory to analyse (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Scan all subdirectories of the given root as individual projects",
    )
    args = parser.parse_args()

    if args.all_projects:
        projects_root = Path(args.project_root) if args.project_root else Path.cwd()
        all_results = scan_all_projects(projects_root)
        if args.json:
            print(json.dumps(all_results, indent=2))
        else:
            print(f"\nPattern scan across projects in: {projects_root}")
            print("=" * 60)
            for project, patterns in sorted(all_results.items()):
                print(f"  {project}: {', '.join(patterns)}")
            print()
        return 0

    project_root = Path(args.project_root) if args.project_root else None
    detail = detect_patterns_detailed(project_root)

    if args.json:
        print(json.dumps(detail, indent=2))
    else:
        _print_human(detail)

    return 0


if __name__ == "__main__":
    sys.exit(main())
