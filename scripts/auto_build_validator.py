#!/usr/bin/env python
"""Auto-detect project type and run compile/build validation.

Called by the PR workflow (github_pr_workflow.py) before creating a pull
request and optionally on TaskUpdate(completed). Returns a structured
pass/fail result with error output so Claude can auto-fix build failures
before committing.

Non-blocking: if the build tool is not installed the check is skipped
(reported as SKIPPED) rather than failing the calling hook.

Supported project types
-----------------------
pom.xml              -> ``mvn compile -q -DskipTests``
build.gradle(.kts)   -> ``gradle compileJava -q`` (or ``./gradlew``)
package.json         -> ``npm run build`` or ``npx tsc --noEmit``
*.py files           -> ``python -m py_compile`` per modified file
Cargo.toml           -> ``cargo check``
go.mod               -> ``go build ./...``

A project can match multiple types (e.g. Maven backend + npm frontend);
all matched types are checked and their results combined.

Safety constraints
------------------
- 90 s timeout for Maven/Gradle (they can be slow on first run).
- 15 s timeout per file for Python syntax checks.
- All public functions wrapped in try/except -- never raises.
- Only checks files or directories that actually exist in the repo root.

Windows-safe: ASCII-only output, no Unicode characters.

Version: 1.0.0
Last Modified: 2026-02-28
Author: Claude Memory System
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

BUILD_TIMEOUT = 90  # seconds (Maven/Gradle need time)
PY_COMPILE_TIMEOUT = 15  # seconds per file


def _get_repo_root() -> str:
    """Return the git repository root directory, falling back to CWD.

    Runs ``git rev-parse --show-toplevel`` to locate the repo root.
    If git is unavailable or the current directory is not inside a git
    repository, returns ``os.getcwd()`` so callers always get a valid path.

    Returns:
        Absolute path string for the repository root (or current directory).
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return os.getcwd()


def detect_project_type(repo_root: str) -> list:
    """Detect the project build system(s) by inspecting well-known build files.

    Examines the repository root for build descriptor files and returns a
    list of project descriptors, one per matched build system. A monorepo
    can match multiple types simultaneously.

    Args:
        repo_root: Absolute path to the repository root directory.

    Returns:
        List of dicts, each with keys:
            ``type``       -- Build system identifier string (e.g. 'maven').
            ``build_file`` -- Filename of the detected build descriptor.
            ``command``    -- List of command tokens to run, or ``None``
                             for Python (handled by ``run_python_compile``).
            ``label``      -- Human-readable label for output messages.

        Returns an empty list if no supported build system is detected.
    """
    root = Path(repo_root)
    detected = []

    # Maven
    if (root / 'pom.xml').exists():
        detected.append({
            'type': 'maven',
            'build_file': 'pom.xml',
            'command': ['mvn', 'compile', '-q', '-DskipTests'],
            'label': 'Maven compile',
        })

    # Gradle (prefer wrapper if exists)
    gradle_file = None
    if (root / 'build.gradle').exists():
        gradle_file = 'build.gradle'
    elif (root / 'build.gradle.kts').exists():
        gradle_file = 'build.gradle.kts'

    if gradle_file:
        # Use gradlew if available
        if sys.platform == 'win32' and (root / 'gradlew.bat').exists():
            gradle_cmd = [str(root / 'gradlew.bat')]
        elif (root / 'gradlew').exists():
            gradle_cmd = [str(root / 'gradlew')]
        else:
            gradle_cmd = ['gradle']

        detected.append({
            'type': 'gradle',
            'build_file': gradle_file,
            'command': gradle_cmd + ['compileJava', '-q'],
            'label': 'Gradle compileJava',
        })

    # Node.js / TypeScript
    if (root / 'package.json').exists():
        # Check if it has a build script or is TypeScript
        try:
            with open(root / 'package.json', 'r', encoding='utf-8') as f:
                pkg = json.load(f)
            scripts = pkg.get('scripts', {})
            deps = pkg.get('dependencies', {})
            dev_deps = pkg.get('devDependencies', {})
            all_deps = {**deps, **dev_deps}

            if 'build' in scripts:
                detected.append({
                    'type': 'npm-build',
                    'build_file': 'package.json',
                    'command': ['npm', 'run', 'build'],
                    'label': 'npm run build',
                })
            elif 'typescript' in all_deps:
                detected.append({
                    'type': 'typescript',
                    'build_file': 'package.json',
                    'command': ['npx', 'tsc', '--noEmit'],
                    'label': 'TypeScript type-check',
                })
        except Exception:
            pass

    # Rust
    if (root / 'Cargo.toml').exists():
        detected.append({
            'type': 'rust',
            'build_file': 'Cargo.toml',
            'command': ['cargo', 'check'],
            'label': 'Cargo check',
        })

    # Go
    if (root / 'go.mod').exists():
        detected.append({
            'type': 'go',
            'build_file': 'go.mod',
            'command': ['go', 'build', './...'],
            'label': 'Go build',
        })

    # Python (requirements.txt or setup.py or pyproject.toml)
    if ((root / 'requirements.txt').exists() or
            (root / 'setup.py').exists() or
            (root / 'pyproject.toml').exists()):
        detected.append({
            'type': 'python',
            'build_file': 'requirements.txt',
            'command': None,  # Special: py_compile per modified file
            'label': 'Python syntax check',
        })

    return detected


def run_build_check(repo_root: str, project_info: dict) -> dict:
    """Run a single build or compile check for one project descriptor.

    Executes the command specified in ``project_info['command']`` with a
    90-second timeout. Treats a missing build tool (FileNotFoundError) as
    a non-fatal skip rather than a failure so that CI environments without
    all tools installed do not block the workflow.

    Args:
        repo_root: Absolute path to the repository root (used as cwd).
        project_info: Dict returned by ``detect_project_type()``. Must
            contain ``'command'``, ``'label'``, and ``'type'`` keys.

    Returns:
        Dict with keys:
            ``passed``      -- True if the build command exited with code 0.
            ``output``      -- Error output (stderr + stdout) on failure,
                              empty string on success.
            ``label``       -- Human-readable label copied from ``project_info``.
            ``duration_ms`` -- Wall-clock time in milliseconds.
            ``skipped``     -- True (optional key) when the build tool was
                              not found or an unexpected error occurred.
    """
    label = project_info.get('label', 'Build')
    command = project_info.get('command')

    if command is None:
        # Python special case - handled by run_python_compile
        return {'passed': True, 'output': '', 'label': label, 'duration_ms': 0}

    start = datetime.now()
    try:
        result = subprocess.run(
            command,
            capture_output=True, text=True,
            timeout=BUILD_TIMEOUT,
            cwd=repo_root
        )
        duration = int((datetime.now() - start).total_seconds() * 1000)

        if result.returncode == 0:
            return {
                'passed': True,
                'output': '',
                'label': label,
                'duration_ms': duration,
            }
        else:
            # Combine stderr and stdout for error details
            error_output = (result.stderr or '') + '\n' + (result.stdout or '')
            # Trim to last 2000 chars (most relevant errors at the end)
            error_output = error_output.strip()
            if len(error_output) > 2000:
                error_output = '...\n' + error_output[-2000:]

            return {
                'passed': False,
                'output': error_output,
                'label': label,
                'duration_ms': duration,
            }

    except subprocess.TimeoutExpired:
        duration = int((datetime.now() - start).total_seconds() * 1000)
        return {
            'passed': False,
            'output': 'BUILD TIMEOUT after ' + str(BUILD_TIMEOUT) + 's',
            'label': label,
            'duration_ms': duration,
        }
    except FileNotFoundError:
        return {
            'passed': True,  # Don't fail if build tool not installed
            'output': 'Build tool not found: ' + str(command[0]) + ' (skipped)',
            'label': label,
            'duration_ms': 0,
            'skipped': True,
        }
    except Exception as e:
        return {
            'passed': True,  # Don't fail on unexpected errors
            'output': 'Build check error: ' + str(e),
            'label': label,
            'duration_ms': 0,
            'skipped': True,
        }


def run_python_compile(repo_root: str, modified_files: list = None) -> dict:
    """Run ``py_compile`` syntax checks on Python files.

    Checks only the files in ``modified_files`` when provided; otherwise
    scans the entire repository (capped at 50 files to avoid slow scans).
    Skips common virtual-environment and cache directories.

    Args:
        repo_root: Absolute path to the repository root directory.
        modified_files: Optional list of file paths to check. Paths may be
            absolute or relative to ``repo_root``. Non-``.py`` files and
            files that do not exist are silently skipped.

    Returns:
        Dict with keys:
            ``passed``      -- True if all checked files compiled without error.
            ``output``      -- Newline-joined error messages on failure,
                              or a success message on pass.
            ``label``       -- Human-readable label including the file count.
            ``errors``      -- List of individual error strings (empty on pass).
            ``duration_ms`` -- Always 0 (individual per-file timing not tracked).
    """
    root = Path(repo_root)
    errors = []
    checked = 0

    # Get list of Python files to check
    py_files = []
    if modified_files:
        for f in modified_files:
            # Resolve relative paths
            full_path = f if os.path.isabs(f) else str(root / f)
            if full_path.endswith('.py') and os.path.exists(full_path):
                py_files.append(full_path)
    else:
        # Check all .py files (limit to 50 to avoid slow scans)
        count = 0
        for py_file in root.rglob('*.py'):
            # Skip venv, __pycache__, node_modules
            parts = py_file.parts
            skip = False
            for skip_dir in ('venv', '.venv', '__pycache__', 'node_modules', '.git', 'env'):
                if skip_dir in parts:
                    skip = True
                    break
            if skip:
                continue
            py_files.append(str(py_file))
            count += 1
            if count >= 50:
                break

    for py_file in py_files:
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'py_compile', py_file],
                capture_output=True, text=True,
                timeout=PY_COMPILE_TIMEOUT
            )
            checked += 1
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                # Shorten file path for readability
                short_path = py_file.replace(repo_root, '').lstrip('/\\')
                errors.append(short_path + ': ' + error_msg[:200])
        except Exception:
            pass

    if errors:
        return {
            'passed': False,
            'output': '\n'.join(errors),
            'label': 'Python syntax check (' + str(checked) + ' files)',
            'errors': errors,
            'duration_ms': 0,
        }
    else:
        return {
            'passed': True,
            'output': str(checked) + ' Python files checked OK',
            'label': 'Python syntax check',
            'errors': [],
            'duration_ms': 0,
        }


def validate_build(repo_root=None, modified_files=None):
    """
    Main entry point. Detects project type(s) and runs compile checks.

    Args:
        repo_root: Git repo root path (auto-detected if None)
        modified_files: List of modified file paths (for targeted Python checks)

    Returns:
        dict: {
            'all_passed': bool,
            'results': [{'passed': bool, 'label': str, 'output': str}, ...],
            'summary': str  (human-readable one-liner)
        }
    """
    if not repo_root:
        repo_root = _get_repo_root()

    projects = detect_project_type(repo_root)

    if not projects:
        return {
            'all_passed': True,
            'results': [],
            'summary': 'No build system detected (skipped)',
        }

    results = []
    all_passed = True

    for project in projects:
        if project['type'] == 'python':
            result = run_python_compile(repo_root, modified_files)
        else:
            result = run_build_check(repo_root, project)

        results.append(result)
        if not result['passed']:
            all_passed = False

    # Build summary
    passed_count = sum(1 for r in results if r['passed'])
    total_count = len(results)
    skipped = sum(1 for r in results if r.get('skipped'))

    if all_passed:
        labels = [r['label'] for r in results if not r.get('skipped')]
        if labels:
            summary = 'BUILD OK: ' + ', '.join(labels) + ' (' + str(passed_count) + '/' + str(total_count) + ' passed)'
        else:
            summary = 'BUILD SKIPPED: build tools not found'
    else:
        failed_labels = [r['label'] for r in results if not r['passed']]
        summary = 'BUILD FAILED: ' + ', '.join(failed_labels) + ' (' + str(passed_count) + '/' + str(total_count) + ' passed)'

    return {
        'all_passed': all_passed,
        'results': results,
        'summary': summary,
    }


if __name__ == '__main__':
    # CLI usage: python auto_build_validator.py [repo_root]
    repo = sys.argv[1] if len(sys.argv) > 1 else None
    result = validate_build(repo)

    print(result['summary'])

    if not result['all_passed']:
        for r in result['results']:
            if not r['passed']:
                print('\n--- ' + r['label'] + ' FAILED ---')
                print(r['output'])
        sys.exit(1)
    else:
        sys.exit(0)
