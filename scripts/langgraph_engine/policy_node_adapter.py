"""
PolicyNodeAdapter - Wraps existing policy scripts as LangGraph nodes.

This adapter allows ALL 60+ existing policy scripts to work unchanged with
LangGraph by:
1. Reading input from FlowState using input_mapping
2. Running the script via subprocess
3. Parsing JSON output
4. Writing results back to FlowState using output_mapping

This enables gradual migration: existing scripts work as-is while new
components are built with LangGraph patterns.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Callable, Optional
from datetime import datetime
from .flow_state import FlowState


class PolicyNodeAdapter:
    """Adapter that wraps a policy script as a LangGraph node.

    Args:
        script_path: Relative or absolute path to policy script (e.g., "context-reader.py")
        input_mapping: Dict mapping FlowState keys -> script argument names
        output_mapping: Dict mapping script output keys -> FlowState keys
        description: Human-readable node description
        timeout_seconds: Max execution time (default 30s)
    """

    def __init__(
        self,
        script_path: str,
        input_mapping: Optional[Dict[str, str]] = None,
        output_mapping: Optional[Dict[str, str]] = None,
        description: str = "",
        timeout_seconds: int = 30,
    ):
        self.script_path = Path(script_path)
        self.input_mapping = input_mapping or {}
        self.output_mapping = output_mapping or {}
        self.description = description
        self.timeout_seconds = timeout_seconds
        self._script_full_path: Optional[Path] = None

    def _resolve_script_path(self) -> Path:
        """Resolve script path, checking multiple locations."""
        if self._script_full_path and self._script_full_path.exists():
            return self._script_full_path

        # Try absolute path first
        if self.script_path.is_absolute() and self.script_path.exists():
            self._script_full_path = self.script_path
            return self._script_full_path

        # Try relative to scripts/ directory
        scripts_dir = Path(__file__).parent.parent
        relative_path = scripts_dir / self.script_path
        if relative_path.exists():
            self._script_full_path = relative_path
            return self._script_full_path

        # Try relative to cwd
        cwd_path = Path.cwd() / self.script_path
        if cwd_path.exists():
            self._script_full_path = cwd_path
            return self._script_full_path

        raise FileNotFoundError(f"Policy script not found: {self.script_path}")

    def _build_command(self, state: FlowState) -> list:
        """Build subprocess command from state using input_mapping.

        Returns:
            List of command arguments [python, script_path, arg1, arg2, ...]
        """
        script = self._resolve_script_path()
        cmd = [sys.executable, str(script)]

        # Add arguments from input_mapping
        for state_key, arg_name in self.input_mapping.items():
            value = state.get(state_key)
            if value is not None:
                if isinstance(value, bool):
                    cmd.append(f"--{arg_name}={str(value).lower()}")
                elif isinstance(value, (list, dict)):
                    cmd.append(f"--{arg_name}={json.dumps(value)}")
                else:
                    cmd.append(f"--{arg_name}={value}")

        return cmd

    def _parse_output(self, output: str) -> Dict[str, Any]:
        """Parse script output as JSON.

        Scripts should output valid JSON to stdout.
        If output is not JSON, treat as error.

        Args:
            output: Script stdout

        Returns:
            Parsed JSON object, or empty dict if parsing fails
        """
        if not output or not output.strip():
            return {}

        try:
            return json.loads(output)
        except json.JSONDecodeError as e:
            # Log error but don't crash - graceful degradation
            return {
                "_parse_error": str(e),
                "_raw_output": output[:500],  # Cap at 500 chars
            }

    def _map_output_to_state(self, script_output: Dict[str, Any]) -> Dict[str, Any]:
        """Map script output keys to FlowState keys using output_mapping.

        Args:
            script_output: Parsed JSON from script

        Returns:
            Dict of state updates {state_key: value}
        """
        state_updates = {}

        for output_key, state_key in self.output_mapping.items():
            if output_key in script_output:
                state_updates[state_key] = script_output[output_key]

        # Always include top-level _parse_error if present
        if "_parse_error" in script_output:
            state_updates["_adapter_error"] = script_output["_parse_error"]

        return state_updates

    def __call__(self, state: FlowState) -> FlowState:
        """Execute policy script and update state.

        This is the main entry point when node is invoked in a graph.

        Args:
            state: Current FlowState

        Returns:
            Updated FlowState with script results
        """
        try:
            cmd = self._build_command(state)

            # Run script with subprocess
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,  # Don't raise on non-zero exit
            )

            # Parse output
            script_output = self._parse_output(result.stdout)

            # If script failed (non-zero exit), log it
            if result.returncode != 0:
                script_output["_exit_code"] = result.returncode
                if result.stderr:
                    script_output["_stderr"] = result.stderr[:500]

            # Map to state
            state_updates = self._map_output_to_state(script_output)

            # Update and return state
            updated_state = {**state, **state_updates}
            return updated_state

        except subprocess.TimeoutExpired:
            # Timeout - return state with error
            state["_adapter_error"] = f"Script timeout after {self.timeout_seconds}s"
            return state

        except Exception as e:
            # Any other error
            state["_adapter_error"] = f"Adapter error: {str(e)}"
            return state

    @staticmethod
    def create_batch(
        adapters: list,
    ) -> Callable[[FlowState], FlowState]:
        """Create a composite node that runs multiple adapters sequentially.

        Useful for grouping related policy scripts.

        Args:
            adapters: List of PolicyNodeAdapter instances

        Returns:
            Composite node function
        """

        def composite_node(state: FlowState) -> FlowState:
            for adapter in adapters:
                state = adapter(state)
            return state

        return composite_node


# Common input/output mapping patterns for reuse

CONTEXT_READER_MAPPING = {
    "input_mapping": {
        "session_id": "session-id",
        "project_root": "project-root",
    },
    "output_mapping": {
        "context_loaded": "context_loaded",
        "context_percentage": "context_percentage",
        "context_threshold_exceeded": "context_threshold_exceeded",
        "context_metadata": "context_metadata",
    },
}

SESSION_LOADER_MAPPING = {
    "input_mapping": {
        "session_id": "session-id",
    },
    "output_mapping": {
        "session_chain_loaded": "session_chain_loaded",
        "session_history": "session_history",
        "session_state_data": "session_state_data",
    },
}

PREFERENCE_LOADER_MAPPING = {
    "input_mapping": {},
    "output_mapping": {
        "preferences_loaded": "preferences_loaded",
        "preferences_data": "preferences_data",
    },
}

PATTERN_DETECTOR_MAPPING = {
    "input_mapping": {
        "project_root": "project-root",
    },
    "output_mapping": {
        "patterns_detected": "patterns_detected",
        "pattern_metadata": "pattern_metadata",
    },
}

STANDARDS_LOADER_MAPPING = {
    "input_mapping": {
        "is_java_project": "java-project",
    },
    "output_mapping": {
        "standards_loaded": "standards_loaded",
        "standards_count": "standards_count",
        "java_standards_loaded": "java_standards_loaded",
        "spring_boot_patterns": "spring_boot_patterns",
    },
}
