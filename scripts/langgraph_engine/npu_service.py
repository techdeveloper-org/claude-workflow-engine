"""
Intel AI Boost NPU Service - Enhanced Multi-Model Support

Provides interface to Intel AI Boost NPU for fast local inference on:
- Step 1: Plan mode decision (super fast classification)
- Step 3: Task breakdown (lightweight reasoning)
- Step 5: Skill selection (pattern matching)

Supported Models (GGUF format):
- Gemma-2-2B: Ultra-fast (1.6GB) - classification, simple tasks
- Phi-3.5-Mini: Fast (2.4GB) - quick reasoning, fast analysis
- Llama-3.2-3B: Balanced (2.5GB) - good reasoning
- DeepSeek-R1-Distill-Qwen-1.5B: Very fast (1.4GB) - lightweight tasks
- Mistral-7B: High quality (4.3GB) - complex reasoning
- Qwen2.5-7B: Coding optimized (4.7GB) - agentic tasks, coding
- Llama-3.1-8B: Strong (5.2GB) - complex tasks, deep reasoning
- DeepSeek-R1-Distill-Qwen-7B: Powerful (4.4GB) - best quality

Configuration:
- Endpoint: C:\Users\techd\Downloads\intel-ai\npu\llama-cli-npu.exe
- Speed: 2-3x faster than GPU for simple tasks
- Latency: <500ms for classification tasks
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal
from loguru import logger


class NPUService:
    """Manages Intel AI Boost NPU inference with multiple models."""

    def __init__(self, npu_path: str = "C:/Users/techd/Downloads/intel-ai/npu"):
        """
        Initialize NPU service.

        Args:
            npu_path: Path to NPU executable directory
        """
        self.npu_path = Path(npu_path)
        self.cli_exe = self.npu_path / "llama-cli-npu.exe"
        self.models_path = self.npu_path.parent / "models" / "npu"

        # Validate NPU setup
        if not self.cli_exe.exists():
            raise RuntimeError(
                f"NPU CLI not found at {self.cli_exe}. "
                f"Install Intel AI Boost from C:\\Users\\techd\\Downloads\\intel-ai"
            )

        if not self.models_path.exists():
            raise RuntimeError(f"NPU models directory not found at {self.models_path}")

        # Model catalog - maps model type to filename patterns
        self.model_catalog = {
            # Ultra-fast models (2B)
            "ultra_fast": {
                "Gemma-2-2B-Q6_K.gguf": "Gemma 2 2B (ultra-fast, classification)",
                "DeepSeek-R1-Distill-Qwen-1.5B-Q6_K.gguf": "DeepSeek-R1 1.5B (fast, lightweight)",
            },
            # Fast models (3-4B)
            "fast": {
                "Phi-3.5-Mini-Q6_K.gguf": "Phi 3.5 Mini (fast, good quality)",
                "Llama-3.2-3B-Instruct-Q6_K.gguf": "Llama 3.2 3B (balanced, reasoning)",
            },
            # Medium models (7-8B)
            "medium": {
                "Mistral-7B-Instruct-v0.2-Q4_K_M.gguf": "Mistral 7B (quality reasoning)",
                "Qwen2.5-7B-Instruct-Q4_K_M.gguf": "Qwen 2.5 7B (coding, agentic)",
                "DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf": "DeepSeek-R1 7B (powerful, reasoning)",
            },
            # Large models (8B+)
            "large": {
                "Llama-3.1-8B-Instruct-Q4_K_M.gguf": "Llama 3.1 8B (strong reasoning, coding)",
            },
        }

        # Task-optimized routing
        self.task_models = {
            # Fast classification → ultra-fast models
            "classification": "ultra_fast",
            "plan_decision": "ultra_fast",
            "simple_analysis": "fast",
            "pattern_matching": "ultra_fast",

            # Task breakdown → fast models
            "task_breakdown": "fast",
            "simple_reasoning": "fast",

            # Complex tasks → medium models
            "reasoning": "medium",
            "agentic_coding": "medium",
            "skill_selection": "medium",
            "code_analysis": "medium",

            # Deep reasoning → large models
            "deep_reasoning": "large",
            "complex_architecture": "large",
            "synthesis": "large",
        }

        # Check available models
        self.available_models = self._check_available_models()
        self.available_categories = self._categorize_models()

        logger.info(f"✓ NPU service initialized at {self.npu_path}")
        logger.info(f"  Available models: {len(self.available_models)}")
        logger.info(f"  Categories: {list(self.available_categories.keys())}")

        for category, models in self.available_categories.items():
            if models:
                logger.debug(f"    [{category}] {len(models)} model(s)")
                for model in models:
                    logger.debug(f"       - {model.name}")

    def _check_available_models(self) -> List[Path]:
        """Check which GGUF models are available locally."""
        try:
            models = list(self.models_path.glob("*.gguf"))
            return sorted(models)
        except Exception as e:
            logger.error(f"Error checking NPU models: {e}")
            return []

    def _categorize_models(self) -> Dict[str, List[Path]]:
        """Categorize available models by size/capability."""
        categorized = {
            "ultra_fast": [],
            "fast": [],
            "medium": [],
            "large": [],
        }

        for model_path in self.available_models:
            model_name = model_path.name
            for category, patterns in self.model_catalog.items():
                for pattern in patterns.keys():
                    if pattern in model_name:
                        categorized[category].append(model_path)
                        break

        return categorized

    def select_model(
        self, task_type: str = "simple_analysis", complexity: int = 5
    ) -> Optional[Path]:
        """
        Intelligently select best model for task.

        Args:
            task_type: Type of task (see task_models dict)
            complexity: 1-10 complexity score

        Returns:
            Path to best available model, or None if none available
        """
        # Determine optimal category
        category = self.task_models.get(task_type, "fast")

        # Override based on complexity if not specified
        if task_type == "auto" or task_type not in self.task_models:
            if complexity <= 2:
                category = "ultra_fast"
            elif complexity <= 4:
                category = "fast"
            elif complexity <= 7:
                category = "medium"
            else:
                category = "large"

        # Get models in category
        models_in_category = self.available_categories.get(category, [])

        if models_in_category:
            # Prefer first available
            return models_in_category[0]

        # Fallback: find any available model
        if self.available_models:
            logger.warning(f"No models in {category} category, using {self.available_models[0].name}")
            return self.available_models[0]

        return None

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "fast_classification",
        task_type: str = "simple_analysis",
        complexity: int = 5,
        temperature: float = 0.3,
        max_tokens: int = 200,
    ) -> Dict[str, Any]:
        """
        Run inference on NPU using llama-cli.

        Args:
            messages: Chat messages (role, content)
            model: Legacy parameter (ignored, uses task_type instead)
            task_type: Type of task for smart model selection
            complexity: Task complexity 1-10
            temperature: Generation temperature (0-1)
            max_tokens: Max response tokens

        Returns:
            Dict with 'message' containing response content
        """
        try:
            # Build prompt from messages
            prompt = ""
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    prompt += f"System: {content}\n"
                elif role == "user":
                    prompt += f"User: {content}\n"
                elif role == "assistant":
                    prompt += f"Assistant: {content}\n"

            prompt += "Assistant:"

            # Select best model for task
            model_path = self.select_model(task_type, complexity)
            if not model_path:
                return {"error": "No models available"}

            logger.debug(f"NPU inference: {model_path.name} (task: {task_type}, complexity: {complexity}/10)")

            # Run NPU inference
            cmd = [
                str(self.cli_exe),
                "-m",
                str(model_path),
                "-n",
                str(max_tokens),
                "--temp",
                str(temperature),
                "--prompt",
                prompt,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # 2 min timeout
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode != 0:
                error_msg = f"NPU inference failed: {result.stderr}"
                logger.error(error_msg)
                return {"error": error_msg}

            # Parse output
            output = result.stdout.strip()
            response_text = output.split("Assistant:")[-1].strip() if "Assistant:" in output else output

            logger.debug(f"NPU response: {len(response_text)} chars from {model_path.name}")

            return {
                "message": {
                    "content": response_text,
                    "role": "assistant",
                },
                "model": model_path.name,
                "done": True,
                "source": "npu",
            }

        except subprocess.TimeoutExpired:
            logger.error("NPU inference timeout (120s)")
            return {"error": "NPU inference timeout"}
        except Exception as e:
            logger.error(f"NPU inference error: {e}")
            return {"error": str(e)}

    def step1_plan_mode_decision(self, toon: Dict[str, Any], user_requirement: str) -> Dict[str, Any]:
        """Fast plan decision on NPU (ultra-fast model)."""
        prompt = f"""Analyze project TOON and user requirement.
Determine if PLAN MODE is required (complexity {toon.get('complexity_score', 0)}/10).

Respond with ONLY valid JSON:
{{"plan_required": true/false, "reasoning": "brief", "risk_level": "low/medium/high"}}"""

        response = self.chat(
            messages=[{"role": "user", "content": prompt}],
            task_type="classification",
            complexity=2,
            max_tokens=100,
        )

        if "error" in response:
            logger.error(f"Step 1 plan decision failed: {response['error']}")
            return {
                "plan_required": True,
                "reasoning": "NPU error, defaulting to plan mode",
                "risk_level": "medium",
            }

        try:
            content = response.get("message", {}).get("content", "{}")
            result = json.loads(content)
            return result
        except json.JSONDecodeError:
            logger.warning(f"Step 1 JSON parse error: {content}")
            return {
                "plan_required": True,
                "reasoning": "JSON parse error, defaulting to plan mode",
                "risk_level": "medium",
            }

    def step3_task_breakdown(self, plan: str, complexity: int) -> Dict[str, Any]:
        """Break plan into tasks on NPU."""
        prompt = f"""Break this plan into structured tasks (complexity {complexity}/10):
{plan[:500]}

Return tasks as JSON array: [{{"id": "Task-1", "description": "...", "files": [...]}}, ...]"""

        response = self.chat(
            messages=[{"role": "user", "content": prompt}],
            task_type="task_breakdown",
            complexity=complexity,
            max_tokens=300,
        )

        if "error" in response:
            return {"success": False, "error": response["error"]}

        try:
            content = response.get("message", {}).get("content", "[]")
            tasks = json.loads(content)
            return {"success": True, "tasks": tasks}
        except json.JSONDecodeError:
            return {"success": False, "error": "Failed to parse task breakdown"}

    def list_models(self) -> Dict[str, List[str]]:
        """List all available models by category."""
        result = {}
        for category, models in self.available_categories.items():
            result[category] = [m.name for m in models]
        return result


def get_npu_service(npu_path: str = "C:/Users/techd/Downloads/intel-ai/npu") -> Optional[NPUService]:
    """Get or create singleton NPU service instance."""
    try:
        if not hasattr(get_npu_service, "_instance"):
            get_npu_service._instance = NPUService(npu_path)
        return get_npu_service._instance
    except Exception as e:
        logger.warning(f"NPU service not available: {e}")
        return None
