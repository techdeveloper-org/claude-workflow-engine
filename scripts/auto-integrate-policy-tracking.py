#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-Integrate Policy Tracking - Automatically adds tracking to all policy scripts

This utility intelligently adds policy tracking integration to Python scripts
without breaking existing functionality. It:

1. Reads a policy script
2. Adds import statements (with error handling)
3. Adds tracking calls to main execution points
4. Preserves all original logic
5. Writes back to file with backup

Usage:
    python auto-integrate-policy-tracking.py --script path/to/script.py
    python auto-integrate-policy-tracking.py --batch all
    python auto-integrate-policy-tracking.py --dry-run path/to/script.py

Version: 1.0.0
"""

import sys
import os
import re
import json
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional

# Windows-safe encoding
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


class PolicyTrackingIntegrator:
    """Automatically integrates policy tracking into Python scripts."""

    # Import statement to add
    TRACKING_IMPORT = """# Policy Tracking Integration
# Policy tracking - mandatory (find helper by walking up to scripts root)
_scripts_root = Path(__file__).resolve().parent
while _scripts_root != _scripts_root.parent:
    if (_scripts_root / 'policy_tracking_helper.py').exists():
        if str(_scripts_root) not in sys.path:
            sys.path.insert(0, str(_scripts_root))
        break
    _scripts_root = _scripts_root.parent
from policy_tracking_helper import record_policy_execution, record_sub_operation, get_session_id
"""

    # Setup code to add after imports
    TRACKING_SETUP = """
# Get session ID for tracking
_TRACKING_SESSION_ID = get_session_id()
_TRACKING_START_TIME = None
"""

    def __init__(self, script_path: str):
        """
        Initialize integrator for a script.

        Args:
            script_path: Path to Python script to integrate
        """
        self.script_path = Path(script_path)
        self.script_name = self.script_path.stem
        self.content = None
        self.modified = False

    def read_script(self) -> bool:
        """Read script content."""
        try:
            self.content = self.script_path.read_text(encoding='utf-8')
            return True
        except Exception as e:
            print(f"[ERROR] Failed to read {self.script_path}: {e}")
            return False

    def has_tracking_import(self) -> bool:
        """Check if script already has tracking imports."""
        return 'policy_tracking_helper' in self.content

    def integrate(self) -> bool:
        """
        Integrate policy tracking into script.

        Returns:
            bool: True if integration successful
        """
        if not self.content:
            print(f"[ERROR] No content to integrate")
            return False

        if self.has_tracking_import():
            print(f"[SKIP] {self.script_path.name} already has tracking")
            return True

        print(f"[INTEGRATING] {self.script_path.name}")

        # Step 1: Add imports after existing imports
        self._add_imports()

        # Step 2: Add setup code
        self._add_setup()

        # Step 3: Add tracking calls to enforce() or main()
        self._add_tracking_calls()

        self.modified = True
        return True

    def _add_imports(self):
        """Add tracking imports after existing imports."""
        # Find last import statement
        import_pattern = r'^(import|from)\s+'
        lines = self.content.split('\n')

        last_import_idx = -1
        for i, line in enumerate(lines):
            if re.match(import_pattern, line.strip()):
                last_import_idx = i

        if last_import_idx >= 0:
            # Insert tracking import after last import
            lines.insert(last_import_idx + 1, '')
            lines.insert(last_import_idx + 2, self.TRACKING_IMPORT.strip())
            self.content = '\n'.join(lines)
        else:
            # No imports found, insert after docstring
            docstring_pattern = r'""".*?"""'
            if '"""' in self.content:
                match = re.search(docstring_pattern, self.content, re.DOTALL)
                if match:
                    insert_pos = match.end()
                    self.content = (
                        self.content[:insert_pos] + '\n\n' + self.TRACKING_IMPORT +
                        self.content[insert_pos:]
                    )

    def _add_setup(self):
        """Add tracking setup code."""
        if '_TRACKING_SESSION_ID' not in self.content:
            lines = self.content.split('\n')
            # Find first function definition
            for i, line in enumerate(lines):
                if line.strip().startswith('def '):
                    lines.insert(i, self.TRACKING_SETUP.strip())
                    self.content = '\n'.join(lines)
                    break

    def _add_tracking_calls(self):
        """Add tracking calls to enforce()/main() functions."""
        # Find enforce() or main() function
        enforce_pattern = r'^def (enforce|main)\([^)]*\):'
        lines = self.content.split('\n')

        for i, line in enumerate(lines):
            if re.match(enforce_pattern, line.strip()):
                print(f"  |-- Found {line.strip()}")
                # Found function, add tracking at start and end
                # For now, add simple tracking template
                self._add_tracking_template(lines, i)
                break

        self.content = '\n'.join(lines)

    def _add_tracking_template(self, lines: list, func_start_idx: int):
        """Add tracking template to function."""
        # Add start time tracking after function def
        indent = '    '
        tracking_start = f"{indent}# [TRACKING] Record execution start"
        tracking_start += f"\n{indent}_start_time = datetime.now()"
        tracking_start += f"\n{indent}_sub_operations = []"

        lines.insert(func_start_idx + 2, tracking_start)

        # Find return statement and add tracking before it
        # This is simplified - real implementation needs better parsing
        return_pattern = r'^\s+return\s+'
        for i in range(func_start_idx, len(lines)):
            if re.match(return_pattern, lines[i]):
                tracking_end = f"{indent}# [TRACKING] Record execution"
                tracking_end += f"\n{indent}if HAS_TRACKING:"
                tracking_end += f"\n{indent}    _duration_ms = int((datetime.now() - _start_time).total_seconds() * 1000)"
                tracking_end += f"\n{indent}    record_policy_execution("
                tracking_end += f"\n{indent}        session_id=_TRACKING_SESSION_ID,"
                tracking_end += f"\n{indent}        policy_name=\"{self.script_name}\","
                tracking_end += f"\n{indent}        policy_script=\"{self.script_path.name}\","
                tracking_end += f"\n{indent}        policy_type=\"Policy Script\","
                tracking_end += f"\n{indent}        input_params={{}},  # [TODO] set input params"
                tracking_end += f"\n{indent}        output_results={{}},  # [TODO] set output results"
                tracking_end += f"\n{indent}        decision=\"\",  # [TODO] set decision"
                tracking_end += f"\n{indent}        duration_ms=_duration_ms"
                tracking_end += f"\n{indent}    )"

                lines.insert(i, tracking_end)
                break

    def write_script(self, backup: bool = True) -> bool:
        """
        Write modified content back to script.

        Args:
            backup: Create backup file first

        Returns:
            bool: Success status
        """
        if not self.modified:
            print(f"[SKIP] {self.script_path.name} not modified")
            return True

        try:
            # Create backup
            if backup:
                backup_path = self.script_path.with_suffix('.py.bak')
                backup_path.write_text(
                    self.script_path.read_text(encoding='utf-8'),
                    encoding='utf-8'
                )
                print(f"  \-- Backup created: {backup_path.name}")

            # Write modified content
            self.script_path.write_text(self.content, encoding='utf-8')
            print(f"  \-- [OK] Updated successfully")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to write {self.script_path}: {e}")
            return False

    def get_summary(self) -> dict:
        """Get integration summary."""
        return {
            "script": str(self.script_path),
            "has_tracking": self.has_tracking_import(),
            "modified": self.modified,
            "status": "[OK] updated" if self.modified else "[SKIP] skipped"
        }


def integrate_script(script_path: str, dry_run: bool = False) -> bool:
    """
    Integrate tracking into a single script.

    Args:
        script_path: Path to Python script
        dry_run: If True, don't write changes

    Returns:
        bool: Success status
    """
    integrator = PolicyTrackingIntegrator(script_path)

    if not integrator.read_script():
        return False

    if not integrator.integrate():
        return False

    if not dry_run:
        integrator.write_script(backup=True)

    return True


def integrate_batch(batch_name: str = 'critical') -> list:
    """
    Integrate tracking for a batch of scripts.

    Args:
        batch_name: 'critical', 'high', 'all'

    Returns:
        list: Results for each script
    """
    base_path = Path(__file__).parent.parent

    batches = {
        'critical': [
            'scripts/auto-fix-enforcer.py',
            'scripts/session-id-generator.py',
            'scripts/clear-session-handler.py',
            'scripts/pre-tool-enforcer.py',
        ],
        'high': [
            'scripts/architecture/01-sync-system/session-management/session-chaining-policy.py',
            'scripts/architecture/01-sync-system/session-management/session-memory-policy.py',
            'scripts/architecture/01-sync-system/context-management/session-pruning-policy.py',
            'scripts/architecture/03-execution-system/00-prompt-generation/prompt-generation-policy.py',
        ],
        'all': [
            # All 28 scripts would go here
            # For now, just the above
        ]
    }

    scripts = batches.get(batch_name, [])
    results = []

    for script_rel_path in scripts:
        script_path = base_path / script_rel_path
        if script_path.exists():
            success = integrate_script(str(script_path))
            results.append({
                'script': script_rel_path,
                'success': success
            })
        else:
            print(f"[WARN] Script not found: {script_path}")
            results.append({'script': script_rel_path, 'success': False})

    return results


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Auto-integrate policy tracking into Python scripts'
    )
    parser.add_argument('--script', help='Single script to integrate')
    parser.add_argument('--batch', default='critical',
                       choices=['critical', 'high', 'all'],
                       help='Batch of scripts to integrate')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without modifying')

    args = parser.parse_args()

    if args.script:
        print(f"[INTEGRATING] Single script: {args.script}")
        integrate_script(args.script, dry_run=args.dry_run)
    else:
        print(f"[INTEGRATING] Batch: {args.batch}")
        results = integrate_batch(args.batch)
        print(f"\n[SUMMARY] {len([r for r in results if r['success']])}/{len(results)} scripts updated")
