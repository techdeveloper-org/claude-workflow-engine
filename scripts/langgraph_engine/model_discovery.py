"""
Model Discovery System - Detect available inference models across GPU, NPU, and OpenVINO.

Scans local model directories and provides unified access to:
- NPU GGUF models (Ollama-compatible)
- OpenVINO optimized models (Intel NPU)
- GPU models (via Ollama)

Configuration:
- INTEL_AI_MODELS_PATH: Path to intel-ai/models directory
- Defaults to: C:\\Users\\techd\\Downloads\\intel-ai\\models\\
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Literal
from dataclasses import dataclass


@dataclass
class ModelInfo:
    """Metadata for a discovered model."""
    name: str
    path: str
    model_type: Literal["npu_gguf", "openvino", "gpu_ollama"]
    platform: Literal["npu", "gpu", "openvino"]
    size: str  # e.g., "1.5B", "7B"
    quantization: Optional[str]  # e.g., "Q4_K_M", "INT4"
    description: str
    recommended_for: List[str]  # e.g., ["reasoning", "planning"]

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "path": self.path,
            "type": self.model_type,
            "platform": self.platform,
            "size": self.size,
            "quantization": self.quantization,
            "description": self.description,
            "recommended_for": self.recommended_for,
        }


class ModelDiscovery:
    """Discovers and catalogs available inference models."""

    def __init__(
        self,
        models_path: Optional[str] = None,
    ):
        """Initialize model discovery.

        Args:
            models_path: Path to intel-ai/models directory.
                        Defaults to C:\\Users\\techd\\Downloads\\intel-ai\\models\\
        """
        if models_path is None:
            models_path = r"C:\Users\techd\Downloads\intel-ai\models"

        self.models_path = Path(models_path)
        self.models: Dict[str, ModelInfo] = {}

        # Discover all models
        self._discover_npu_models()
        self._discover_openvino_models()
        self._discover_gpu_models()

    def _discover_npu_models(self) -> None:
        """Discover NPU GGUF models."""
        npu_path = self.models_path / "npu"

        if not npu_path.exists():
            return

        for model_file in npu_path.glob("*.gguf"):
            name = model_file.stem
            info = self._parse_npu_model_name(name)

            self.models[name] = ModelInfo(
                name=name,
                path=str(model_file),
                model_type="npu_gguf",
                platform="npu",
                size=info["size"],
                quantization=info["quantization"],
                description=f"NPU GGUF model - {info['desc']}",
                recommended_for=info["recommended_for"],
            )

    def _parse_npu_model_name(self, name: str) -> Dict:
        """Parse NPU model filename to extract metadata."""
        if "DeepSeek-R1-Distill-Qwen-7B" in name:
            return {
                "size": "7B",
                "quantization": "Q4_K_M" if "Q4_K_M" in name else "Q6_K",
                "desc": "DeepSeek R1 Qwen Distill 7B",
                "recommended_for": ["reasoning", "planning", "complex_analysis"],
            }
        elif "DeepSeek-R1-Distill-Qwen-1.5B" in name:
            return {
                "size": "1.5B",
                "quantization": "Q6_K" if "Q6_K" in name else "Q4_K",
                "desc": "DeepSeek R1 Qwen Distill 1.5B",
                "recommended_for": ["reasoning", "fast_analysis"],
            }
        elif "Qwen2.5-7B" in name:
            return {
                "size": "7B",
                "quantization": "Q4_K_M" if "Q4_K_M" in name else "Q6_K",
                "desc": "Qwen 2.5 7B Instruct",
                "recommended_for": ["general_qa", "classification"],
            }
        elif "Llama-3.2-3B" in name:
            return {
                "size": "3B",
                "quantization": "Q6_K" if "Q6_K" in name else "Q4_K",
                "desc": "Llama 3.2 3B Instruct",
                "recommended_for": ["general_qa", "instruction_following"],
            }
        elif "gemma-2-2b" in name:
            return {
                "size": "2B",
                "quantization": "Q6_K",
                "desc": "Gemma 2 2B IT",
                "recommended_for": ["fast_classification", "lightweight"],
            }
        else:
            return {
                "size": "unknown",
                "quantization": None,
                "desc": name,
                "recommended_for": [],
            }

    def _discover_openvino_models(self) -> None:
        """Discover OpenVINO optimized models."""
        openvino_path = self.models_path / "openvino-npu"

        if not openvino_path.exists():
            return

        for model_dir in openvino_path.iterdir():
            if not model_dir.is_dir():
                continue

            name = model_dir.name
            info = self._parse_openvino_model_name(name)

            self.models[name] = ModelInfo(
                name=name,
                path=str(model_dir),
                model_type="openvino",
                platform="openvino",
                size=info["size"],
                quantization=info["quantization"],
                description=f"OpenVINO optimized - {info['desc']}",
                recommended_for=info["recommended_for"],
            )

    def _parse_openvino_model_name(self, name: str) -> Dict:
        """Parse OpenVINO model directory name to extract metadata."""
        if "DeepSeek-R1-1.5B" in name:
            return {
                "size": "1.5B",
                "quantization": name.split("-")[-1] if "-" in name else "HYBRID",
                "desc": "DeepSeek R1 1.5B OpenVINO Optimized",
                "recommended_for": ["reasoning", "fast_reasoning", "npu_optimized"],
            }
        elif "Qwen2.5-3B" in name:
            return {
                "size": "3B",
                "quantization": "INT4" if "INT4" in name else None,
                "desc": "Qwen 2.5 3B Instruct OpenVINO",
                "recommended_for": ["general_qa", "npu_optimized"],
            }
        else:
            return {
                "size": "unknown",
                "quantization": None,
                "desc": name,
                "recommended_for": ["npu_optimized"],
            }

    def _discover_gpu_models(self) -> None:
        """Discover GPU models (Ollama-compatible).

        Note: GPU models are managed by Ollama service, not discovered here.
        This is a placeholder for potential future GPU model discovery.
        """
        gpu_path = self.models_path / "gpu"

        if not gpu_path.exists():
            return

        # For now, just register that GPU models are available
        # Actual discovery is handled by ollama_service.py
        self.models["gpu_available"] = ModelInfo(
            name="GPU (Ollama)",
            path=str(gpu_path),
            model_type="gpu_ollama",
            platform="gpu",
            size="varies",
            quantization=None,
            description="GPU models managed by Ollama service",
            recommended_for=["complex_reasoning", "planning", "synthesis"],
        )

    def get_all_models(self) -> List[ModelInfo]:
        """Get all discovered models."""
        return list(self.models.values())

    def get_models_by_platform(
        self,
        platform: Literal["npu", "gpu", "openvino"],
    ) -> List[ModelInfo]:
        """Get models for specific platform."""
        return [m for m in self.models.values() if m.platform == platform]

    def get_models_for_task(self, task: str) -> List[ModelInfo]:
        """Get models recommended for a specific task.

        Args:
            task: Task type (e.g., 'reasoning', 'fast_analysis', 'general_qa')

        Returns:
            List of models recommended for this task, sorted by performance
        """
        matching = [m for m in self.models.values() if task in m.recommended_for]
        # Sort by platform priority (openvino > npu > gpu) and size (larger better)
        platform_priority = {"openvino": 3, "npu": 2, "gpu": 1}
        return sorted(
            matching,
            key=lambda m: (
                platform_priority.get(m.platform, 0),
                int(m.size.replace("B", "")) if m.size != "unknown" else 0,
            ),
            reverse=True,
        )

    def find_best_model(
        self,
        task: str = "reasoning",
        platform: Optional[str] = None,
    ) -> Optional[ModelInfo]:
        """Find best model for a task, optionally on specific platform.

        Args:
            task: Task type (e.g., 'reasoning')
            platform: Optional platform constraint ('npu', 'openvino', 'gpu')

        Returns:
            Best matching model, or None if not found
        """
        candidates = self.get_models_for_task(task)

        if platform:
            candidates = [m for m in candidates if m.platform == platform]

        return candidates[0] if candidates else None

    def to_dict(self) -> Dict:
        """Export all discovered models as dictionary."""
        return {
            "total": len(self.models),
            "by_platform": {
                "npu": len(self.get_models_by_platform("npu")),
                "openvino": len(self.get_models_by_platform("openvino")),
                "gpu": len(self.get_models_by_platform("gpu")),
            },
            "models": {
                name: model.to_dict() for name, model in self.models.items()
            },
        }


# Singleton instance
_discovery_instance: Optional[ModelDiscovery] = None


def get_model_discovery() -> ModelDiscovery:
    """Get or create the singleton ModelDiscovery instance."""
    global _discovery_instance
    if _discovery_instance is None:
        _discovery_instance = ModelDiscovery()
    return _discovery_instance


def reset_model_discovery() -> None:
    """Reset the singleton (for testing)."""
    global _discovery_instance
    _discovery_instance = None
