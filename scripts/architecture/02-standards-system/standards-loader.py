#!/usr/bin/env python3
"""
Coding Standards Loader - Level 2 Standards System Policy

Loads ALL coding standards and policies from ~/.claude/policies/
Makes them available for execution phase.

Invoked by: 3-level-flow.py (Level 2 Standards System)

Version: 3.0.0 - Real Policy Loading
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime


class StandardsLoader:
    """Load all coding standards from actual policy files."""

    def __init__(self):
        self.policies_dir = Path.home() / ".claude" / "policies"
        self.standards = {}
        self.loaded_files = []
        self.total_size_kb = 0

    def load_all_policies(self):
        """Load all .md policy files from ~/.claude/policies/"""
        try:
            if not self.policies_dir.exists():
                return {
                    "status": "NO_POLICIES_DIR",
                    "standards_loaded": 0,
                    "total_files": 0,
                    "message": "~/.claude/policies/ directory not found",
                    "loaded_standards": []
                }

            # Find all .md files (policies)
            policy_files = list(self.policies_dir.rglob("*.md"))

            # Filter out README files (they're metadata, not standards)
            policy_files = [f for f in policy_files if f.name != "README.md"]

            # Load each policy
            for policy_file in policy_files:
                try:
                    content = policy_file.read_text(encoding='utf-8')
                    size_kb = len(content) / 1024

                    # Extract policy name (use filename without .md)
                    policy_name = policy_file.stem

                    # Extract level from path (01-sync, 02-standards, 03-execution, etc)
                    relative_path = policy_file.relative_to(self.policies_dir)
                    parts = str(relative_path).split(os.sep)
                    level = parts[0] if parts else "unknown"

                    # Store policy metadata
                    self.standards[policy_name] = {
                        "name": policy_name,
                        "file": str(policy_file),
                        "size_kb": round(size_kb, 2),
                        "level": level,
                        "relative_path": str(relative_path),
                        "loaded_at": datetime.now().isoformat(),
                    }

                    self.loaded_files.append(policy_name)
                    self.total_size_kb += size_kb

                except Exception as e:
                    pass  # Skip files that can't be read

            return {
                "status": "SUCCESS",
                "standards_loaded": len(self.standards),
                "total_files": len(policy_files),
                "total_size_kb": round(self.total_size_kb, 2),
                "loaded_standards": self.loaded_files[:20],  # First 20 for reference
                "message": f"Loaded {len(self.standards)} standards from {len(policy_files)} policy files",
                "by_level": {
                    "sync_system": len([s for s in self.standards.values() if "01-sync" in s.get("level", "")]),
                    "standards_system": len([s for s in self.standards.values() if "02-standards" in s.get("level", "")]),
                    "execution_system": len([s for s in self.standards.values() if "03-execution" in s.get("level", "")]),
                    "other": len([s for s in self.standards.values() if not any(x in s.get("level", "") for x in ["01-sync", "02-standards", "03-execution"])]),
                },
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "standards_loaded": 0,
                "message": f"Failed to load standards: {str(e)[:100]}",
                "timestamp": datetime.now().isoformat(),
            }

    def run(self):
        """Main entry point for loading standards."""
        result = self.load_all_policies()
        return result


if __name__ == '__main__':
    # Parse arguments
    load_all = "--load-all" in sys.argv

    loader = StandardsLoader()
    result = loader.run()

    # Output as JSON for LangGraph
    print(json.dumps(result))
    sys.exit(0)
