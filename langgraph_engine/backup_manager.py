"""
File Backup and Restore System

Provides safe backup/restore functionality with:
- Before/after file comparison
- Automatic rollback on failure
- Diff generation
- Transaction-like semantics
"""

import difflib
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class BackupManager:
    """Manages file backups and rollback operations."""

    def __init__(self, session_id: str, backup_base_dir: str = "~/.claude/logs"):
        """
        Initialize backup manager for a session.

        Args:
            session_id: Unique session identifier
            backup_base_dir: Base directory for backups
        """
        self.session_id = session_id
        self.backup_dir = Path(backup_base_dir).expanduser() / "sessions" / session_id / "backup"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.diff_dir = self.backup_dir / "diffs"
        self.diff_dir.mkdir(parents=True, exist_ok=True)

        self.metadata_file = self.backup_dir / "backup_metadata.json"
        self.metadata = self._load_metadata()

    def backup_file(self, file_path: str, step: str, description: str = "") -> bool:
        """
        Create backup of a file before modification.

        Args:
            file_path: Path to file to backup
            step: Step/phase name (e.g., "Level -1")
            description: Optional description of what's being done

        Returns:
            True if backup successful, False otherwise
        """
        file_path = Path(file_path)

        if not file_path.exists():
            print(f"[WARN]  File not found for backup: {file_path}")
            return False

        try:
            # Generate backup filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = file_path.name.replace(".", f"_{timestamp}.")
            backup_file = self.backup_dir / f"{step}_{safe_name}"

            # Create backup
            backup_file.write_bytes(file_path.read_bytes())

            # Track in metadata
            entry = {
                "timestamp": datetime.now().isoformat(),
                "original_path": str(file_path),
                "backup_path": str(backup_file),
                "step": step,
                "description": description,
                "file_size": file_path.stat().st_size,
            }

            self.metadata["backups"].append(entry)
            self._save_metadata()

            print(f"[OK] Backup created: {file_path} -> {backup_file}")
            return True

        except Exception as e:
            print(f"[FAIL] Backup failed for {file_path}: {e}")
            return False

    def restore_file(self, file_path: str, step: str) -> bool:
        """
        Restore file from backup.

        Args:
            file_path: Path to file to restore
            step: Step name to find corresponding backup

        Returns:
            True if restore successful, False otherwise
        """
        file_path = Path(file_path)

        try:
            # Find backup for this file and step
            backup_entries = [
                b for b in self.metadata["backups"] if b["original_path"] == str(file_path) and b["step"] == step
            ]

            if not backup_entries:
                print(f"[WARN]  No backup found for {file_path} in step {step}")
                return False

            # Use most recent backup
            latest_backup = max(backup_entries, key=lambda x: x["timestamp"])
            backup_file = Path(latest_backup["backup_path"])

            if not backup_file.exists():
                print(f"[FAIL] Backup file not found: {backup_file}")
                return False

            # Restore file
            file_path.write_bytes(backup_file.read_bytes())

            # Update metadata
            latest_backup["restored"] = True
            latest_backup["restore_timestamp"] = datetime.now().isoformat()
            self._save_metadata()

            print(f"[OK] Restored: {file_path} from {backup_file}")
            return True

        except Exception as e:
            print(f"[FAIL] Restore failed for {file_path}: {e}")
            return False

    def generate_diff(self, file_path: str, step: str, label: str = "") -> Optional[str]:
        """
        Generate unified diff between original and current file.

        Args:
            file_path: Path to file
            step: Step name
            label: Custom label for diff file

        Returns:
            Path to diff file, or None if error
        """
        file_path = Path(file_path)

        try:
            # Find backup for comparison
            backup_entries = [
                b for b in self.metadata["backups"] if b["original_path"] == str(file_path) and b["step"] == step
            ]

            if not backup_entries:
                print(f"[WARN]  No backup found for diff: {file_path}")
                return None

            latest_backup = max(backup_entries, key=lambda x: x["timestamp"])
            backup_file = Path(latest_backup["backup_path"])

            # Read both versions
            try:
                original_lines = backup_file.read_text(encoding="utf-8").splitlines(keepends=True)
            except Exception:
                original_lines = backup_file.read_bytes().decode("utf-8", errors="replace").splitlines(keepends=True)

            try:
                current_lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
            except Exception:
                current_lines = file_path.read_bytes().decode("utf-8", errors="replace").splitlines(keepends=True)

            # Generate unified diff
            diff_lines = difflib.unified_diff(
                original_lines,
                current_lines,
                fromfile=f"{file_path} (original)",
                tofile=f"{file_path} (current)",
                lineterm="",
            )

            diff_content = "\n".join(diff_lines)

            # Save diff file
            diff_label = label or file_path.stem
            diff_filename = f"{step}_{diff_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.diff"
            diff_file = self.diff_dir / diff_filename

            diff_file.write_text(diff_content, encoding="utf-8")

            print(f"[OK] Diff generated: {diff_file}")
            return str(diff_file)

        except Exception as e:
            print(f"[FAIL] Diff generation failed for {file_path}: {e}")
            return None

    def validate_file_integrity(self, file_path: str, step: str) -> bool:
        """
        Validate that file wasn't corrupted during modification.

        Args:
            file_path: Path to file to validate
            step: Step name

        Returns:
            True if file is valid, False otherwise
        """
        file_path = Path(file_path)

        if not file_path.exists():
            print(f"[FAIL] File not found for validation: {file_path}")
            return False

        try:
            # Try to read file as text
            content = file_path.read_text(encoding="utf-8")

            # Basic validation: non-empty file
            if not content.strip():
                print(f"[WARN]  File is empty after modification: {file_path}")
                return False

            # Specific validation for Python files
            if file_path.suffix == ".py":
                try:
                    compile(content, str(file_path), "exec")
                except SyntaxError as e:
                    print(f"[FAIL] Syntax error in {file_path}: {e}")
                    return False

            print(f"[OK] File validation passed: {file_path}")
            return True

        except Exception as e:
            print(f"[FAIL] File validation failed for {file_path}: {e}")
            return False

    def compare_files(self, file_path: str, step: str) -> Dict:
        """
        Get detailed comparison between original and current file.

        Args:
            file_path: Path to file
            step: Step name

        Returns:
            Dict with comparison details
        """
        file_path = Path(file_path)

        try:
            # Find backup
            backup_entries = [
                b for b in self.metadata["backups"] if b["original_path"] == str(file_path) and b["step"] == step
            ]

            if not backup_entries:
                return {"error": "No backup found", "file": str(file_path)}

            latest_backup = max(backup_entries, key=lambda x: x["timestamp"])
            backup_file = Path(latest_backup["backup_path"])

            original_content = backup_file.read_bytes()
            current_content = file_path.read_bytes()

            return {
                "file": str(file_path),
                "original_size": len(original_content),
                "current_size": len(current_content),
                "size_changed": len(original_content) != len(current_content),
                "content_identical": original_content == current_content,
                "backup_path": str(backup_file),
            }

        except Exception as e:
            return {"error": str(e), "file": str(file_path)}

    def get_backup_history(self, file_path: Optional[str] = None) -> List[Dict]:
        """
        Get backup history for a file or all files.

        Args:
            file_path: Optional file path to filter

        Returns:
            List of backup entries
        """
        backups = self.metadata["backups"]

        if file_path:
            backups = [b for b in backups if b["original_path"] == str(Path(file_path))]

        return sorted(backups, key=lambda x: x["timestamp"], reverse=True)

    # ========== Private methods ==========

    def _load_metadata(self) -> Dict:
        """Load or initialize metadata."""
        if self.metadata_file.exists():
            try:
                return json.loads(self.metadata_file.read_text())
            except Exception:
                pass

        return {"session_id": self.session_id, "created": datetime.now().isoformat(), "backups": []}

    def _save_metadata(self) -> None:
        """Save metadata to file."""
        try:
            self.metadata_file.write_text(json.dumps(self.metadata, indent=2))
        except Exception as e:
            print(f"[FAIL] Failed to save backup metadata: {e}")


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def create_backup_manager(session_id: str) -> BackupManager:
    """
    Create a new backup manager instance.

    Args:
        session_id: Unique session ID

    Returns:
        BackupManager instance
    """
    return BackupManager(session_id)


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    # Example usage
    manager = create_backup_manager("test-session-001")

    # Create a test file
    test_file = Path("test_file.py")
    test_file.write_text("print('original')\n")

    # Backup it
    manager.backup_file(str(test_file), "Level -1", "Before modification")

    # Modify it
    test_file.write_text("print('modified')\nprint('added line')\n")

    # Generate diff
    diff_path = manager.generate_diff(str(test_file), "Level -1")

    # Validate integrity
    is_valid = manager.validate_file_integrity(str(test_file), "Level -1")

    # Compare files
    comparison = manager.compare_files(str(test_file), "Level -1")
    print(f"\nComparison: {json.dumps(comparison, indent=2)}")

    # Restore if needed
    # manager.restore_file(str(test_file), "Level -1")

    # Cleanup
    test_file.unlink()
    print("\n[OK] Example completed")
