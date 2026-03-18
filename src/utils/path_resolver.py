"""
Path Resolver for Claude Insight.

Single source of truth for ALL path resolution across the project.
No file should ever hardcode absolute paths - everything goes through here.

Path Standard:
    All paths are resolved via environment variable overrides with
    cross-platform defaults using Path.home(). Never hardcode usernames.

    | Path Type     | Env Override            | Default (all OS)            |
    |---------------|-------------------------|-----------------------------|
    | Claude Home   | CLAUDE_HOME             | ~/.claude/                  |
    | Scripts       | CLAUDE_SCRIPTS_DIR      | {CLAUDE_HOME}/scripts/      |
    | Policies      | CLAUDE_POLICIES_DIR     | {CLAUDE_HOME}/policies/     |
    | Settings      | CLAUDE_SETTINGS_FILE    | {CLAUDE_HOME}/settings.json |
    | Data/Memory   | CLAUDE_INSIGHT_DATA_DIR | {CLAUDE_HOME}/memory/       |
    | Intel AI Root | INTEL_AI_PATH           | ~/intel-ai/                 |
    | GPU Path      | INTEL_AI_GPU_PATH       | {INTEL_AI_PATH}/gpu/        |
    | NPU Path      | INTEL_AI_NPU_PATH       | {INTEL_AI_PATH}/npu/        |
    | Models Path   | INTEL_AI_MODELS_PATH    | {INTEL_AI_PATH}/models/     |

Priority chain for data directory:
    0. CLAUDE_INSIGHT_DATA_DIR environment variable (set by IDE launcher)
    1. ~/.claude/memory/ (present when Claude Memory System is installed)
    2. ./data/ within the project root (portable/standalone mode)

Module-level singletons:
    path_resolver (PathResolver): Global shared instance.

Convenience functions (all delegate to path_resolver):
    get_sessions_dir() -> Path
    get_logs_dir() -> Path
    get_config_dir() -> Path
    get_data_dir(subdir=None) -> Path
    get_file(*parts) -> Path
    is_global_mode() -> bool
    is_local_mode() -> bool
    get_mode_info() -> dict
    get_scripts_dir() -> Path
    get_policies_dir() -> Path
    get_session_logs_dir() -> Path
    get_claude_home() -> Path
    get_settings_file() -> Path
    get_intel_ai_path() -> Path
    get_gpu_path() -> Path
    get_npu_path() -> Path
    get_models_path() -> Path
    get_gpu_executable() -> Path
    get_npu_executable() -> Path

Classes:
    PathResolver: Data directory resolver with three-tier priority fallback.
"""

from pathlib import Path
import os
import sys


def _env_path(var_name, default):
    """Get path from environment variable or use default.

    Args:
        var_name: Environment variable name.
        default: Default Path object if env var not set.

    Returns:
        Path object from env var or default.
    """
    val = os.environ.get(var_name)
    if val:
        return Path(val)
    return default


class PathResolver:
    """Resolve data storage paths for Claude Insight with a three-tier priority chain.

    Single source of truth for ALL paths. No hardcoded absolute paths anywhere.
    Every path is resolved via env var override -> cross-platform default.

    Chooses the base data directory according to the following priority:
    0. CLAUDE_INSIGHT_DATA_DIR env var (IDE launcher override)
    1. ~/.claude/memory/ if it exists (Claude Memory System installed)
    2. <project_root>/data/ (portable standalone mode)

    Attributes:
        project_root (Path): Absolute path to the project root (parent of src/).
        claude_home (Path): Claude home directory (~/.claude/ or CLAUDE_HOME).
        base_dir (Path): The resolved data root directory for this instance.
        mode (str): Operating mode string - 'IDE', 'GLOBAL', or 'LOCAL'.
        has_global_memory (bool): True when using the global memory directory.
    """

    def __init__(self):
        """Initialize PathResolver and resolve the operating mode and base_dir."""
        self.project_root = Path(__file__).parent.parent.parent

        # ---- Claude Home (base for all Claude paths) ----
        self.claude_home = _env_path(
            'CLAUDE_HOME', Path.home() / '.claude'
        )
        self.global_memory = self.claude_home / 'memory'

        # ---- Intel AI paths (GPU/NPU/Models) ----
        self.intel_ai_root = _env_path(
            'INTEL_AI_PATH', Path.home() / 'intel-ai'
        )

        # Priority 0: Environment variable (set by IDE)
        env_data_dir = os.environ.get('CLAUDE_INSIGHT_DATA_DIR')
        if env_data_dir:
            self.base_dir = Path(env_data_dir)
            self.mode = "IDE"
            self.has_global_memory = False
            self._ensure_local_structure()
        # Priority 1: Global ~/.claude/memory
        elif self.global_memory.exists():
            self.base_dir = self.global_memory
            self.mode = "GLOBAL"
            self.has_global_memory = True
        # Priority 2: Local ./data/
        else:
            self.base_dir = self.project_root / 'data'
            self.mode = "LOCAL"
            self.has_global_memory = False
            self._ensure_local_structure()

    def _ensure_local_structure(self):
        """Create the required local data directory structure under base_dir.

        Creates the following subdirectories (parents=True, exist_ok=True):
        sessions/, logs/, config/, anomalies/, forecasts/, performance/.

        Returns:
            None
        """
        dirs = [
            self.base_dir / 'sessions',
            self.base_dir / 'logs',
            self.base_dir / 'config',
            self.base_dir / 'anomalies',
            self.base_dir / 'forecasts',
            self.base_dir / 'performance',
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    # ---- Data directories ----

    def get_sessions_dir(self):
        """Get sessions directory."""
        return self.base_dir / 'sessions'

    def get_logs_dir(self):
        """Get logs directory."""
        return self.base_dir / 'logs'

    def get_session_logs_dir(self):
        """Get per-session logs directory (flow-trace.json, etc.)."""
        return self.base_dir / 'logs' / 'sessions'

    def get_config_dir(self):
        """Get config directory."""
        return self.base_dir / 'config'

    def get_data_dir(self, subdir=None):
        """Get data directory (optionally with subdirectory)."""
        if subdir:
            return self.base_dir / subdir
        return self.base_dir

    def get_file(self, *parts):
        """Get file path within data directory."""
        return self.base_dir.joinpath(*parts)

    # ---- Claude directories ----

    def get_claude_home(self):
        """Get Claude home directory (~/.claude/ or CLAUDE_HOME)."""
        return self.claude_home

    def get_scripts_dir(self):
        """Get scripts directory (hooks live here).

        Override: CLAUDE_SCRIPTS_DIR env var.
        Default: {CLAUDE_HOME}/scripts/
        """
        return _env_path('CLAUDE_SCRIPTS_DIR', self.claude_home / 'scripts')

    def get_policies_dir(self):
        """Get policies directory.

        Override: CLAUDE_POLICIES_DIR env var.
        Default: {CLAUDE_HOME}/policies/
        """
        return _env_path('CLAUDE_POLICIES_DIR', self.claude_home / 'policies')

    def get_settings_file(self):
        """Get settings.json file path.

        Override: CLAUDE_SETTINGS_FILE env var.
        Default: {CLAUDE_HOME}/settings.json
        """
        return _env_path('CLAUDE_SETTINGS_FILE', self.claude_home / 'settings.json')

    # ---- Intel AI directories ----

    def get_intel_ai_path(self):
        """Get Intel AI root directory.

        Override: INTEL_AI_PATH env var.
        Default: ~/intel-ai/
        """
        return self.intel_ai_root

    def get_gpu_path(self):
        """Get GPU (Ollama) directory.

        Override: INTEL_AI_GPU_PATH env var.
        Default: {INTEL_AI_PATH}/gpu/
        """
        return _env_path('INTEL_AI_GPU_PATH', self.intel_ai_root / 'gpu')

    def get_npu_path(self):
        """Get NPU directory.

        Override: INTEL_AI_NPU_PATH env var.
        Default: {INTEL_AI_PATH}/npu/
        """
        return _env_path('INTEL_AI_NPU_PATH', self.intel_ai_root / 'npu')

    def get_models_path(self):
        """Get models directory.

        Override: INTEL_AI_MODELS_PATH env var.
        Default: {INTEL_AI_PATH}/models/
        """
        return _env_path('INTEL_AI_MODELS_PATH', self.intel_ai_root / 'models')

    def get_gpu_executable(self):
        """Get GPU executable path (ollama or ollama.exe).

        Override: INTEL_AI_GPU_EXE env var.
        Default: {GPU_PATH}/ollama.exe (Windows) or {GPU_PATH}/ollama (Linux/Mac)
        """
        env_exe = os.environ.get('INTEL_AI_GPU_EXE')
        if env_exe:
            return Path(env_exe)
        gpu_dir = self.get_gpu_path()
        if sys.platform == 'win32':
            return gpu_dir / 'ollama.exe'
        return gpu_dir / 'ollama'

    def get_npu_executable(self):
        """Get NPU executable path (llama-cli-npu).

        Override: INTEL_AI_NPU_EXE env var.
        Default: {NPU_PATH}/llama-cli-npu.exe (Windows) or {NPU_PATH}/llama-cli-npu
        """
        env_exe = os.environ.get('INTEL_AI_NPU_EXE')
        if env_exe:
            return Path(env_exe)
        npu_dir = self.get_npu_path()
        if sys.platform == 'win32':
            return npu_dir / 'llama-cli-npu.exe'
        return npu_dir / 'llama-cli-npu'

    # ---- Mode info ----

    def is_global_mode(self):
        """Check if using global ~/.claude/memory."""
        return self.mode == "GLOBAL"

    def is_local_mode(self):
        """Check if using local ./data/."""
        return self.mode == "LOCAL"

    def get_mode_info(self):
        """Get current mode information."""
        return {
            'mode': self.mode,
            'base_dir': str(self.base_dir),
            'claude_home': str(self.claude_home),
            'intel_ai_path': str(self.intel_ai_root),
            'has_global_memory': self.has_global_memory,
        }


# Global instance
path_resolver = PathResolver()


# Convenience functions

def get_sessions_dir():
    """Return the sessions directory path from the global PathResolver instance.

    Returns:
        Path: Absolute path to the sessions directory.
    """
    return path_resolver.get_sessions_dir()


def get_logs_dir():
    """Return the logs directory path from the global PathResolver instance.

    Returns:
        Path: Absolute path to the logs directory.
    """
    return path_resolver.get_logs_dir()


def get_config_dir():
    """Return the config directory path from the global PathResolver instance.

    Returns:
        Path: Absolute path to the config directory.
    """
    return path_resolver.get_config_dir()


def get_data_dir(subdir=None):
    """Return the data root (optionally with a subdirectory appended).

    Args:
        subdir (str or None): Optional subdirectory name to append to the
            base data directory.

    Returns:
        Path: Absolute path to the data directory (or subdirectory).
    """
    return path_resolver.get_data_dir(subdir)


def get_file(*parts):
    """Return a file path constructed from the data root and the given parts.

    Args:
        *parts: Path components to join after the base data directory.

    Returns:
        Path: Absolute file path under the data directory.
    """
    return path_resolver.get_file(*parts)


def is_global_mode():
    """Return True when the global ~/.claude/memory directory is in use.

    Returns:
        bool: True if mode is 'GLOBAL', False otherwise.
    """
    return path_resolver.is_global_mode()


def is_local_mode():
    """Return True when the local ./data/ directory is in use.

    Returns:
        bool: True if mode is 'LOCAL', False otherwise.
    """
    return path_resolver.is_local_mode()


def get_mode_info():
    """Return a dictionary describing the current path resolver mode.

    Returns:
        dict: With keys:
            mode (str): 'IDE', 'GLOBAL', or 'LOCAL'.
            base_dir (str): String representation of the base directory.
            has_global_memory (bool): Whether global memory is available.
    """
    return path_resolver.get_mode_info()


def get_scripts_dir():
    """Return the scripts directory path from the global PathResolver instance.

    Returns:
        Path: Absolute path to ~/.claude/scripts/.
    """
    return path_resolver.get_scripts_dir()


def get_policies_dir():
    """Return the policies directory path from the global PathResolver instance.

    Returns:
        Path: Absolute path to ~/.claude/policies/.
    """
    return path_resolver.get_policies_dir()


def get_session_logs_dir():
    """Return the per-session logs directory path from the global PathResolver.

    Returns:
        Path: Absolute path to the session logs directory (logs/sessions/).
    """
    return path_resolver.get_session_logs_dir()


def get_claude_home():
    """Return the Claude home directory (~/.claude/ or CLAUDE_HOME).

    Returns:
        Path: Absolute path to the Claude home directory.
    """
    return path_resolver.get_claude_home()


def get_settings_file():
    """Return the settings.json file path.

    Returns:
        Path: Absolute path to settings.json.
    """
    return path_resolver.get_settings_file()


def get_intel_ai_path():
    """Return the Intel AI root directory.

    Returns:
        Path: Absolute path to Intel AI root (~/intel-ai/ or INTEL_AI_PATH).
    """
    return path_resolver.get_intel_ai_path()


def get_gpu_path():
    """Return the GPU directory path.

    Returns:
        Path: Absolute path to GPU directory.
    """
    return path_resolver.get_gpu_path()


def get_npu_path():
    """Return the NPU directory path.

    Returns:
        Path: Absolute path to NPU directory.
    """
    return path_resolver.get_npu_path()


def get_models_path():
    """Return the models directory path.

    Returns:
        Path: Absolute path to models directory.
    """
    return path_resolver.get_models_path()


def get_gpu_executable():
    """Return the GPU executable path.

    Returns:
        Path: Absolute path to ollama executable.
    """
    return path_resolver.get_gpu_executable()


def get_npu_executable():
    """Return the NPU executable path.

    Returns:
        Path: Absolute path to llama-cli-npu executable.
    """
    return path_resolver.get_npu_executable()
