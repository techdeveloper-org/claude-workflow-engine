"""
Inference Configuration - GPU vs NPU routing and model setup

Supports Intel AI setup with GPU (Ollama) and NPU (Intel AI Boost).

All paths are resolved via environment variables with cross-platform defaults.
See path_resolver.py for the path standard. Never hardcode absolute paths.

Environment variables for path overrides:
    INTEL_AI_PATH       -> Root (default: ~/intel-ai/)
    INTEL_AI_GPU_PATH   -> GPU dir (default: {INTEL_AI_PATH}/gpu/)
    INTEL_AI_NPU_PATH   -> NPU dir (default: {INTEL_AI_PATH}/npu/)
    INTEL_AI_MODELS_PATH -> Models dir (default: {INTEL_AI_PATH}/models/)
    INTEL_AI_GPU_EXE    -> GPU executable (default: {GPU_PATH}/ollama[.exe])
    INTEL_AI_NPU_EXE    -> NPU executable (default: {NPU_PATH}/llama-cli-npu[.exe])
    OLLAMA_ENDPOINT     -> GPU endpoint (default: http://127.0.0.1:11434)
"""

import os
import sys
from pathlib import Path
from typing import Literal


def _resolve_path(env_var, default_parts):
    """Resolve a path from env var or build from home + parts."""
    val = os.environ.get(env_var)
    if val:
        return Path(val)
    return Path.home().joinpath(*default_parts)


# Resolve Intel AI paths (cross-platform, no hardcoded usernames)
_INTEL_AI_ROOT = _resolve_path('INTEL_AI_PATH', ['intel-ai'])
_GPU_PATH = _resolve_path('INTEL_AI_GPU_PATH', ['intel-ai', 'gpu'])
_NPU_PATH = _resolve_path('INTEL_AI_NPU_PATH', ['intel-ai', 'npu'])
_MODELS_PATH = _resolve_path('INTEL_AI_MODELS_PATH', ['intel-ai', 'models'])

_EXE_SUFFIX = '.exe' if sys.platform == 'win32' else ''


class InferenceConfig:
    """Configuration for inference backends.

    All paths use environment variable overrides with cross-platform defaults.
    """

    # ============================================================================
    # INFERENCE MODE - Choose between GPU, NPU, or Auto routing
    # ============================================================================

    # Mode options: "auto" | "gpu_only" | "npu_only"
    # - "auto": Smart routing (fast tasks->NPU, complex tasks->GPU)
    # - "gpu_only": Use only Ollama GPU
    # - "npu_only": Use only Intel AI Boost NPU
    INFERENCE_MODE: Literal["auto", "gpu_only", "npu_only"] = os.getenv(
        "INFERENCE_MODE", "auto"
    )

    # ============================================================================
    # GPU SETUP (Ollama with Intel Arc)
    # ============================================================================

    GPU_ENABLED = True
    GPU_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://127.0.0.1:11434")
    GPU_MODELS_PATH = str(_MODELS_PATH / "gpu")
    GPU_EXECUTABLE = str(
        _resolve_path('INTEL_AI_GPU_EXE', ['intel-ai', 'gpu', 'ollama' + _EXE_SUFFIX])
    )

    # GPU startup command (platform-aware)
    @staticmethod
    def get_gpu_startup_command():
        """Build GPU startup command for current platform."""
        gpu_dir = str(_GPU_PATH)
        if sys.platform == 'win32':
            return (
                'start "Ollama GPU Server" cmd /k '
                '"cd /d %s && '
                "set OLLAMA_NUM_GPU=33 && "
                "set ZES_ENABLE_SYSMAN=1 && "
                "set SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS=1 && "
                "set SYCL_CACHE_PERSISTENT=1 && "
                "set ONEAPI_DEVICE_SELECTOR=level_zero:0 && "
                "set OLLAMA_KEEP_ALIVE=10m && "
                "set OLLAMA_NUM_PARALLEL=1 && "
                "set OLLAMA_HOST=127.0.0.1:11434 && "
                'ollama%s serve"'
            ) % (gpu_dir, _EXE_SUFFIX)
        else:
            return (
                "cd %s && "
                "OLLAMA_NUM_GPU=33 "
                "ZES_ENABLE_SYSMAN=1 "
                "OLLAMA_KEEP_ALIVE=10m "
                "OLLAMA_HOST=127.0.0.1:11434 "
                "./ollama serve &"
            ) % gpu_dir

    # Available GPU models (from GPU mode)
    GPU_MODELS = {
        "fast_classification": "qwen2.5:7b",  # For fast tasks
        "complex_reasoning": "granite4:3b",   # For complex reasoning
        "synthesis": "qwen2.5:7b",            # For prompt generation
    }

    # ============================================================================
    # NPU SETUP (Intel AI Boost - llama-cli-npu)
    # ============================================================================

    NPU_ENABLED = True
    NPU_PATH = str(_NPU_PATH)
    NPU_CLI_EXE = str(
        _resolve_path('INTEL_AI_NPU_EXE', ['intel-ai', 'npu', 'llama-cli-npu' + _EXE_SUFFIX])
    )
    NPU_MODELS_PATH = str(_MODELS_PATH / "npu")

    # Available NPU models (GGUF format)
    NPU_MODELS = {
        "fast_classification": "DeepSeek-R1-Distill-Qwen-1.5B-Q6_K.gguf",  # 1.46GB, fastest
        "medium_reasoning": "Llama-3.2-3B-Instruct-Q6_K.gguf",             # 2.64GB
        "deep_reasoning": "DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",       # 4.68GB, best quality
    }

    # ============================================================================
    # ROUTING STRATEGY - Which tasks go to which backend
    # ============================================================================

    TASK_ROUTING = {
        # Fast tasks → NPU (2-3x faster)
        "classification": "npu",
        "plan_decision": "npu",
        "simple_analysis": "npu",
        "pattern_matching": "npu",
        "task_breakdown": "npu",

        # Complex tasks → GPU (better quality)
        "reasoning": "gpu",
        "planning": "gpu",
        "synthesis": "gpu",
        "skill_selection": "gpu",
        "code_generation": "gpu",

        # Complexity-based routing
        "auto": "npu_if_complexity_<=5_else_gpu",
    }

    # ============================================================================
    # PERFORMANCE TARGETS
    # ============================================================================

    # NPU performance expectations
    NPU_TARGET_LATENCY_MS = 500  # NPU should respond in <500ms
    NPU_TARGET_THROUGHPUT = 50   # Tokens per second

    # GPU performance expectations
    GPU_TARGET_LATENCY_MS = 1000  # GPU slightly slower but better quality
    GPU_TARGET_THROUGHPUT = 30    # Tokens per second

    # ============================================================================
    # FALLBACK STRATEGY
    # ============================================================================

    # If NPU fails, fallback to GPU
    # If GPU fails, fallback to NPU
    # If both fail, use Claude API (if configured via ANTHROPIC_KEY)
    AUTO_FALLBACK = True

    # ============================================================================
    # STARTUP HELPERS
    # ============================================================================

    @staticmethod
    def get_gpu_startup_instruction() -> str:
        """Get instruction for starting GPU."""
        gpu_dir = str(_GPU_PATH)
        return (
            "GPU (Ollama with Intel Arc) not running.\n"
            "To start:\n"
            "  1. Open terminal\n"
            "  2. cd %s\n"
            "  3. Set environment variables:\n"
            "     OLLAMA_NUM_GPU=33\n"
            "     ZES_ENABLE_SYSMAN=1\n"
            "     OLLAMA_KEEP_ALIVE=10m\n"
            "     OLLAMA_HOST=127.0.0.1:11434\n"
            "  4. ollama serve\n"
            "\n"
            "  Or set INTEL_AI_GPU_PATH env var to your GPU directory.\n"
        ) % gpu_dir

    @staticmethod
    def get_npu_startup_instruction() -> str:
        """Get instruction for starting NPU."""
        npu_exe = str(_NPU_PATH / ('llama-cli-npu' + _EXE_SUFFIX))
        models_dir = str(_MODELS_PATH / 'npu')
        return (
            "NPU (Intel AI Boost) not available.\n"
            "Required files:\n"
            "  - %s\n"
            "  - Models in %s\n"
            "\n"
            "Set INTEL_AI_NPU_PATH env var to customize location.\n"
            "Download Intel AI setup from:\n"
            "  https://github.com/intel-analytics/ipex-llm/releases\n"
        ) % (npu_exe, models_dir)

    @staticmethod
    def validate_setup() -> dict:
        """Validate GPU and NPU setup."""
        results = {
            "gpu_ready": False,
            "npu_ready": False,
            "errors": [],
        }

        # Check GPU
        gpu_exe = Path(InferenceConfig.GPU_EXECUTABLE)
        gpu_models = Path(InferenceConfig.GPU_MODELS_PATH)

        if gpu_exe.exists() and gpu_models.exists():
            results["gpu_ready"] = True
        else:
            if not gpu_exe.exists():
                results["errors"].append(f"GPU exe not found: {gpu_exe}")
            if not gpu_models.exists():
                results["errors"].append(f"GPU models not found: {gpu_models}")

        # Check NPU
        npu_cli = Path(InferenceConfig.NPU_CLI_EXE)
        npu_models = Path(InferenceConfig.NPU_MODELS_PATH)

        if npu_cli.exists() and npu_models.exists():
            results["npu_ready"] = True
        else:
            if not npu_cli.exists():
                results["errors"].append(f"NPU CLI not found: {npu_cli}")
            if not npu_models.exists():
                results["errors"].append(f"NPU models not found: {npu_models}")

        return results
