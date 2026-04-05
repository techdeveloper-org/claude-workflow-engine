"""
Unified Inference Router - GPU-First model selection

Routes all tasks to GPU (Ollama) by default. NPU routing disabled as NPU is
slow and produces unreadable output. GPU models: qwen2.5:7b, granite4:3b.

Configuration via environment variables:
- INFERENCE_MODE: "auto" (default), "gpu_only", "npu_only"
- OLLAMA_ENDPOINT: GPU endpoint (default: http://127.0.0.1:11434)
- INTEL_AI_NPU_PATH: NPU path (default: ~/intel-ai/npu)

# v1.15.2: removed step1_plan_mode_decision() and step5_skill_agent_selection()
#           (Steps 1 and 5 removed from the pipeline in v1.13.0;
#            InferenceRouter is never imported by live graph nodes).
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Literal

from loguru import logger

try:
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
    from utils.path_resolver import get_gpu_path, get_npu_path

    _NPU_PATH_DEFAULT = str(get_npu_path())
    _GPU_PATH_DEFAULT = str(get_gpu_path())
except ImportError:
    _NPU_PATH_DEFAULT = str(Path.home() / "intel-ai" / "npu")
    _GPU_PATH_DEFAULT = str(Path.home() / "intel-ai" / "gpu")

from .npu_service import get_npu_service
from .ollama_service import OllamaService


class InferenceRouter:
    """Routes inference requests to GPU or NPU based on task and performance metrics."""

    def __init__(
        self,
        mode: str = "auto",
        ollama_endpoint: str = "http://127.0.0.1:11434",
        npu_path: str = None,
    ):
        """
        Initialize inference router.

        Args:
            mode: "auto" (smart routing), "gpu_only", "npu_only"
            ollama_endpoint: GPU Ollama endpoint
            npu_path: NPU executable path (default: ~/intel-ai/npu or INTEL_AI_NPU_PATH)
        """
        if npu_path is None:
            npu_path = str(Path(os.getenv("INTEL_AI_NPU_PATH", _NPU_PATH_DEFAULT)))
        self.mode = mode.lower()
        self.ollama_endpoint = ollama_endpoint
        self.npu_path = npu_path

        # Initialize services
        self.ollama = None
        self.npu = None
        self._init_services()

        logger.info(f"Inference router initialized (mode: {self.mode})")
        logger.info(f"  GPU: {'available' if self.ollama else 'unavailable'}")
        logger.info(f"  NPU: {'available' if self.npu else 'unavailable'}")

    def _init_services(self):
        """Initialize GPU and NPU services. GPU is initialized first as primary backend."""
        # Initialize GPU (Ollama) - primary backend
        if self.mode in ["auto", "gpu_only"]:
            try:
                self.ollama = OllamaService(endpoint=self.ollama_endpoint)
                logger.info("GPU (Ollama) initialized as primary backend")
            except Exception as e:
                logger.warning(f"GPU initialization failed: {e}")
                self.ollama = None

        # Initialize NPU - optional fallback only (known to be slow)
        if self.mode in ["npu_only"]:
            try:
                self.npu = get_npu_service(self.npu_path)
                if self.npu:
                    logger.info("NPU initialized (optional fallback, prefer GPU)")
            except Exception as e:
                logger.warning(f"NPU initialization failed: {e}")
                self.npu = None

        # Validate at least one is available
        if not self.ollama and not self.npu:
            gpu_exe = os.getenv(
                "INTEL_AI_GPU_EXE",
                str(Path(_GPU_PATH_DEFAULT) / "ollama"),
            )
            raise RuntimeError(
                "No inference backend available (GPU and NPU both failed). " "Start GPU with: %s serve" % gpu_exe
            )

    def choose_backend(self, task_type: str = "auto", complexity: int = 5) -> Literal["gpu", "npu"]:
        """
        Choose optimal backend for task.

        Args:
            task_type: "classification", "reasoning", "planning", "auto"
            complexity: 1-10 (task complexity)

        Returns:
            "gpu" or "npu"
        """
        if self.mode == "gpu_only":
            return "gpu"
        elif self.mode == "npu_only":
            return "npu"

        # Auto mode: smart routing
        # Fast tasks -> NPU, Complex tasks -> GPU
        if not self.npu:
            return "gpu"  # Only GPU available
        if not self.ollama:
            return "npu"  # Only NPU available

        # All tasks route to GPU - faster and better quality than NPU
        task_routing = {
            "classification": "gpu",  # Was npu, GPU is faster and better quality
            "simple_analysis": "gpu",
            "pattern_matching": "gpu",
            "reasoning": "gpu",
            "planning": "gpu",
            "synthesis": "gpu",
            "auto": "gpu",  # Default to GPU
        }

        return task_routing.get(task_type, "gpu")

    def chat(
        self,
        messages: List[Dict[str, str]],
        task_type: str = "auto",
        complexity: int = 5,
        model: str = "fast_classification",
        temperature: float = 0.3,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Send chat request to optimal backend.

        Args:
            messages: Chat messages
            task_type: Type of task (for backend selection)
            complexity: Task complexity 1-10
            model: Model/model-type selector
            temperature: Generation temperature
            **kwargs: Additional arguments

        Returns:
            Dict with 'message' containing response
        """
        backend = self.choose_backend(task_type, complexity)

        logger.debug(f"Routing to {backend}: {task_type} (complexity {complexity}/10)")

        try:
            if backend == "npu":
                if not self.npu:
                    logger.warning("NPU unavailable, falling back to GPU")
                    return self._fallback_to_gpu(messages, model, temperature, **kwargs)

                return self.npu.chat(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=kwargs.get("max_tokens", 200),
                )
            else:  # GPU
                if not self.ollama:
                    logger.warning("GPU unavailable, falling back to NPU")
                    return self._fallback_to_npu(messages, model, temperature, **kwargs)

                return self.ollama.chat(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    **kwargs,
                )

        except Exception as e:
            logger.error(f"{backend} inference failed: {e}")
            # Try fallback
            if backend == "npu":
                return self._fallback_to_gpu(messages, model, temperature, **kwargs)
            else:
                return self._fallback_to_npu(messages, model, temperature, **kwargs)

    def _fallback_to_gpu(
        self, messages: List[Dict[str, str]], model: str, temperature: float, **kwargs
    ) -> Dict[str, Any]:
        """Fallback to GPU if NPU fails."""
        if not self.ollama:
            return {"error": "GPU not available for fallback"}
        logger.warning("Falling back to GPU")
        return self.ollama.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            **kwargs,
        )

    def _fallback_to_npu(
        self, messages: List[Dict[str, str]], model: str, temperature: float, **kwargs
    ) -> Dict[str, Any]:
        """Fallback to NPU if GPU fails."""
        if not self.npu:
            return {"error": "NPU not available for fallback"}
        logger.warning("Falling back to NPU")
        return self.npu.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=kwargs.get("max_tokens", 200),
        )


def get_inference_router() -> InferenceRouter:
    """Get or create singleton inference router."""
    if not hasattr(get_inference_router, "_instance"):
        mode = os.getenv("INFERENCE_MODE", "auto")
        ollama_endpoint = os.getenv("OLLAMA_ENDPOINT", "http://127.0.0.1:11434")
        npu_path = os.getenv("INTEL_AI_NPU_PATH", _NPU_PATH_DEFAULT)

        get_inference_router._instance = InferenceRouter(mode=mode, ollama_endpoint=ollama_endpoint, npu_path=npu_path)

    return get_inference_router._instance
