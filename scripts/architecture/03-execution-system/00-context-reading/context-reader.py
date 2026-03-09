#!/usr/bin/env python3
"""
Context Reader Script - Step 3.0.0 (Pre-Flight)

Reads project context files (README, CHANGELOG, VERSION, SRS) before
prompt generation to provide Claude with project knowledge.

Features:
  - Detects project type (README exists = known project)
  - Gracefully skips new projects (no files found)
  - Reads files with encoding safety (UTF-8 + cp1252 fallback)
  - Extracts metadata (version, tech stack, recent changes)
  - Caches context in session JSON for reuse
  - Integrates with flow-trace.json for full traceability

Version: 1.0.0
Author: Claude Insight System
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Windows: ASCII-only output (no Unicode/emojis)
if sys.platform == 'win32':
    import io
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        elif hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass


def read_file_safe(file_path, max_lines=None, position='start'):
    """
    Read a file with encoding safety (UTF-8 fallback to cp1252).

    Args:
        file_path (Path): File to read
        max_lines (int, optional): Max lines to read (None = all)
        position (str): 'start' = read first N lines, 'end' = read last N lines

    Returns:
        str: File contents (or empty string on error)
    """
    try:
        # Try UTF-8 first
        try:
            content = file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            # Fallback to cp1252 for Windows-safe mixed encoding
            content = file_path.read_text(encoding='cp1252', errors='replace')

        # Limit lines if requested
        if max_lines is not None:
            lines = content.split('\n')
            if position == 'end':
                lines = lines[-max_lines:] if len(lines) > max_lines else lines
            else:  # start (default)
                lines = lines[:max_lines]
            content = '\n'.join(lines)

        return content
    except Exception as e:
        print(f"[WARN] Error reading {file_path.name}: {e}")
        return ''


class ContextReader:
    """Main context reading engine."""

    def __init__(self, hook_cwd):
        """Initialize with working directory from hook."""
        self.cwd = Path(hook_cwd) if hook_cwd else Path.cwd()
        self.files_to_find = {
            'readme': 'README.md',
            'changelog': 'CHANGELOG.md',
            'version': 'VERSION',
            'srs': 'SYSTEM_REQUIREMENTS_SPECIFICATION.md',
            'claude_md': 'CLAUDE.md'
        }
        # MANDATORY for enforcement: ALL 3 MUST EXIST
        # Policy: "Read README + SYSTEM_REQUIREMENTS_SPECIFICATION + CLAUDE.md before coding"
        self.required_for_enforcement = {'readme', 'srs', 'claude_md'}
        self.files_found = {}
        self.context = {}
        self.metadata = {}
        self.start_time = datetime.now()

    def detect_project(self):
        """Check if this is a known project (README exists)."""
        readme_path = self.cwd / self.files_to_find['readme']
        return readme_path.exists()

    def find_files(self):
        """Scan project directory for context files."""
        for key, filename_or_list in self.files_to_find.items():
            if isinstance(filename_or_list, list):
                # Try multiple filenames (SRS variants)
                for filename in filename_or_list:
                    path = self.cwd / filename
                    if path.exists():
                        self.files_found[key] = {
                            'exists': True,
                            'path': str(path),
                            'filename': filename
                        }
                        break
                else:
                    # None of the SRS variants found
                    self.files_found[key] = {'exists': False}
            else:
                # Single filename
                path = self.cwd / filename_or_list
                self.files_found[key] = {
                    'exists': path.exists(),
                    'path': str(path) if path.exists() else None,
                    'filename': filename_or_list
                }

    def read_readme(self):
        """Read README.md (first 500 lines)."""
        if not self.files_found['readme']['exists']:
            return

        path = Path(self.files_found['readme']['path'])
        content = read_file_safe(path, max_lines=500, position='start')

        self.context['readme_excerpt'] = content[:2000] if content else None
        self.files_found['readme']['size_bytes'] = path.stat().st_size if path.exists() else 0
        self.files_found['readme']['excerpt_lines'] = 500

    def read_changelog(self):
        """Read CHANGELOG.md (last 1000 lines for recent changes)."""
        if not self.files_found['changelog']['exists']:
            return

        path = Path(self.files_found['changelog']['path'])
        content = read_file_safe(path, max_lines=1000, position='end')

        self.context['changelog_excerpt'] = content[-3000:] if content else None
        self.files_found['changelog']['size_bytes'] = path.stat().st_size if path.exists() else 0
        self.files_found['changelog']['excerpt_lines'] = 1000

    def read_version(self):
        """Read VERSION file (complete)."""
        if not self.files_found['version']['exists']:
            return

        path = Path(self.files_found['version']['path'])
        content = read_file_safe(path).strip()

        self.context['version'] = content if content else None
        self.files_found['version']['size_bytes'] = path.stat().st_size if path.exists() else 0

    def read_srs(self):
        """Read SRS.md (first 1000 lines)."""
        if not self.files_found['srs']['exists']:
            return

        path = Path(self.files_found['srs']['path'])
        content = read_file_safe(path, max_lines=1000, position='start')

        self.context['srs_excerpt'] = content[:3000] if content else None
        self.files_found['srs']['size_bytes'] = path.stat().st_size if path.exists() else 0
        self.files_found['srs']['excerpt_lines'] = 1000

    def read_claude_md(self):
        """Read CLAUDE.md (relevant sections only)."""
        if not self.files_found['claude_md']['exists']:
            return

        path = Path(self.files_found['claude_md']['path'])
        content = read_file_safe(path, max_lines=200, position='start')

        self.context['claude_md_excerpt'] = content[:1500] if content else None
        self.files_found['claude_md']['size_bytes'] = path.stat().st_size if path.exists() else 0

    def extract_metadata(self):
        """Extract project metadata from context files.

        ENFORCEMENT LOGIC:
        - is_new_project = True if ANY of the 3 required files are MISSING
        - is_new_project = False only if ALL 3 required files EXIST
        - enforcement_applies = NOT is_new_project
        """
        # Check if ALL required files exist
        all_required_exist = all(
            self.files_found.get(key, {}).get('exists', False)
            for key in self.required_for_enforcement
        )

        self.metadata = {
            'tech_stack': [],
            'project_type': 'Unknown',
            'is_new_project': not all_required_exist  # True if any file missing
        }

        # Extract project name and type from README
        if self.context.get('readme_excerpt'):
            lines = self.context['readme_excerpt'].split('\n')
            for line in lines[:5]:
                if line.startswith('#'):
                    # Extract from first heading
                    self.metadata['project_name'] = line.replace('#', '').strip()
                    # Detect project type from heading
                    if 'Flask' in line or 'Django' in line:
                        self.metadata['project_type'] = 'Python Web Framework'
                    elif 'Spring' in line:
                        self.metadata['project_type'] = 'Java Spring Boot'
                    break

        # Extract version
        if self.context.get('version'):
            self.metadata['current_version'] = self.context['version']

        # Detect tech stack from README
        readme_text = (self.context.get('readme_excerpt') or '').lower()
        tech_keywords = {
            'python': 'Python',
            'flask': 'Flask',
            'django': 'Django',
            'fastapi': 'FastAPI',
            'java': 'Java',
            'spring': 'Spring Boot',
            'angular': 'Angular',
            'react': 'React',
            'docker': 'Docker',
            'kubernetes': 'Kubernetes',
            'postgresql': 'PostgreSQL',
            'mongodb': 'MongoDB',
            'sqlite': 'SQLite'
        }

        for keyword, tech_name in tech_keywords.items():
            if keyword in readme_text and tech_name not in self.metadata['tech_stack']:
                self.metadata['tech_stack'].append(tech_name)

    def build_enrichment_data(self):
        """Build data for prompt generation enrichment."""
        return {
            'project_name': self.metadata.get('project_name'),
            'project_overview': self.context.get('readme_excerpt', '')[:500],
            'current_version': self.context.get('version'),
            'tech_stack': self.metadata.get('tech_stack', []),
            'recent_context': self.context.get('changelog_excerpt', '')[:300],
            'requirements': self.context.get('srs_excerpt', '')[:300]
        }

    def cache_in_session(self, session_id):
        """Cache context in session for reuse."""
        try:
            memory_base = Path.home() / '.claude' / 'memory' / 'logs' / 'sessions' / session_id
            memory_base.mkdir(parents=True, exist_ok=True)

            cache_file = memory_base / 'context-cache.json'
            cache_data = {
                'version': '1.0.0',
                'context_read_at': self.start_time.isoformat(),
                'project_detected': self.detect_project(),
                'files_found': self.files_found,
                'metadata': self.metadata,
                'context': self.context,
                'enrichment_data': self.build_enrichment_data()
            }

            cache_file.write_text(json.dumps(cache_data, indent=2), encoding='utf-8')
            return True
        except Exception as e:
            print(f"[WARN] Error caching context: {e}")
            return False

    def build_trace_entry(self):
        """Build flow-trace.json entry."""
        duration = (datetime.now() - self.start_time).total_seconds() * 1000

        files_found_list = [
            key for key, val in self.files_found.items()
            if val.get('exists')
        ]

        return {
            'step': 'LEVEL_3_CONTEXT_READ',
            'name': 'Context Reading (Pre-Flight)',
            'level': 3,
            'order': 0,
            'is_blocking': False,
            'timestamp': self.start_time.isoformat(),
            'duration_ms': int(duration),
            'input': {
                'hook_cwd': str(self.cwd),
                'purpose': 'Detect and read project context before prompt generation'
            },
            'policy': {
                'script': 'context-reader.py',
                'version': '1.0.0',
                'rules_applied': [
                    'detect_project_from_readme',
                    'scan_context_files',
                    'read_with_encoding_safety',
                    'extract_metadata',
                    'cache_in_session',
                    'handle_missing_files_gracefully'
                ]
            },
            'policy_output': {
                'project_detected': self.detect_project(),
                'files_found': files_found_list,
                'project_name': self.metadata.get('project_name'),
                'version': self.context.get('version'),
                'tech_stack': self.metadata.get('tech_stack', []),
                'status': 'SUCCESS' if files_found_list else 'SKIPPED'
            },
            'decision': self._build_decision(),
            'passed_to_next': {
                'has_context': bool(files_found_list),
                'project_name': self.metadata.get('project_name'),
                'context_available': not self.metadata.get('is_new_project'),
                'enrichment_data': self.build_enrichment_data()
            }
        }

    def _build_decision(self):
        """Build decision statement for trace."""
        if self.detect_project():
            files = [k for k, v in self.files_found.items() if v.get('exists')]
            return f"Project detected. Found {len(files)} context file(s): {', '.join(files)}. Cached for session."
        else:
            return "No context files found. New project detected. Skipping context enrichment."

    def create_context_read_flag(self, session_id):
        """Create a flag file to signal that context has been read."""
        try:
            flag_dir = Path.home() / '.claude' / 'memory' / 'flags'
            flag_dir.mkdir(parents=True, exist_ok=True)

            pid = os.getpid()
            flag_file = flag_dir / f'.context-read-{session_id}-{pid}.json'

            is_new = self.metadata.get('is_new_project', True)
            flag_data = {
                'session_id': session_id,
                'pid': pid,
                'timestamp': datetime.now().isoformat(),
                'status': 'completed',
                'is_new_project': is_new,
                'project_detected': self.detect_project(),
                'files_found': list(k for k, v in self.files_found.items() if v.get('exists')),
                'enforcement_applies': not is_new
            }

            flag_file.write_text(json.dumps(flag_data, indent=2), encoding='utf-8')
            return True
        except Exception as e:
            print(f"[WARN] Failed to create context-read flag: {e}")
            return False

    def run(self):
        """Main execution."""
        print("[CONTEXT] Reading project context files...")

        # Step 1: Detect project
        self.find_files()

        if not self.detect_project():
            print("[CONTEXT] New project detected (no README). Skipping context reading.")
            return 0

        # Step 2: Read available files
        self.read_readme()
        self.read_changelog()
        self.read_version()
        self.read_srs()
        self.read_claude_md()

        # Step 3: Extract metadata
        self.extract_metadata()

        # Step 4: Output results
        print(f"[CONTEXT] Project: {self.metadata.get('project_name', 'Unknown')}")
        print(f"[CONTEXT] Version: {self.context.get('version', 'Unknown')}")
        print(f"[CONTEXT] Tech: {', '.join(self.metadata.get('tech_stack', []) or ['Unknown'])}")

        return 0


def main():
    """Entry point."""
    # Check for --check flag (used by LangGraph)
    check_mode = "--check" in sys.argv

    hook_cwd = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else os.getcwd()
    session_id = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else 'unknown'

    reader = ContextReader(hook_cwd)
    reader.find_files()
    reader.extract_metadata()

    if not check_mode:
        # Original full mode - read files and output trace entry
        exit_code = reader.run()
        reader.cache_in_session(session_id)
        reader.create_context_read_flag(session_id)
        trace_entry = reader.build_trace_entry()
        print(json.dumps(trace_entry))
        return exit_code

    # --check mode for LangGraph: simplified output
    is_new_project = reader.metadata.get('is_new_project', True)
    enforcement_applies = not is_new_project

    # Get list of files found
    files_found = [
        key for key, val in reader.files_found.items()
        if val.get('exists')
    ]

    # For existing projects, check if context has been read
    # For new projects, always allow (no enforcement)
    context_read = not is_new_project  # Assume read for existing projects

    # Build simplified output
    output = {
        "check_passed": context_read,
        "enforcement_applies": enforcement_applies,
        "is_new_project": is_new_project,
        "files_found": files_found,
        "context_read": context_read,
        "status": "OK"
    }

    print(json.dumps(output))
    return 0


if __name__ == '__main__':
    sys.exit(main())
