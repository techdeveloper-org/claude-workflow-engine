"""
Ollama Service Layer - GPU-based local LLM integration for Level 3 execution.

Provides interface to local Ollama GPU models for:
- Step 8+: GitHub issue, branch, implementation, PR, docs, summary

Configuration:
- Primary endpoint: http://127.0.0.1:11434 (default Ollama)
- Models: qwen2.5:7b (fast classification, synthesis), granite4:3b (reasoning)
- Fallback: Claude API via ANTHROPIC_KEY environment variable

# v1.15.2: removed step1_plan_mode_decision, step5_skill_agent_selection,
#           step7_final_prompt_generation (Steps 1,5,7 removed in v1.13.0).
"""

import json
import os
import subprocess
from typing import Any, Dict, List, Optional

import requests
from loguru import logger


class OllamaService:
    """Manages communication with local Ollama LLM."""

    def __init__(self, endpoint: str = "http://127.0.0.1:11434"):
        self.endpoint = endpoint
        self.ollama_available = False
        self.available_models = []
        self.claude_client = None

        # Model routing config (used by both Ollama and Claude CLI fallback)
        self.models = {
            "deep_reasoning": "qwen2.5:14b",
            "prompt_synthesis": "qwen2.5:14b",
            "fast_classification": "qwen2.5:7b",
            "code_analysis": "qwen2.5:7b",
            "task_breakdown": "llama3.2:3b",
            "complex_reasoning": "qwen2.5:14b",
            "synthesis": "qwen2.5:14b",
            "pattern_matching": "qwen2.5:14b",
        }

        # Try Ollama - gracefully degrade if unavailable
        try:
            self._validate_ollama_server()
            self.ollama_available = True
            self.available_models = self._check_available_models()

            # Fallback to first available model if configured models not found
            if self.available_models:
                for key in self.models:
                    if self.models[key] not in self.available_models:
                        self.models[key] = self.available_models[0]

            logger.info(f"Ollama service initialized at {endpoint}")
            logger.info(f"Available models: {self.available_models}")
        except Exception as e:
            logger.warning(f"Ollama unavailable: {str(e)[:100]}")
            logger.info("Will use Claude CLI fallback for all LLM calls")

        # Initialize Claude API SDK fallback (if anthropic package installed)
        self._init_claude_fallback()

    def _validate_ollama_server(self):
        """Validate that Ollama server is running and accessible."""
        try:
            response = requests.get(f"{self.endpoint}/api/tags", timeout=3)
            if response.status_code == 200:
                logger.info(f"Ollama server is running at {self.endpoint}")
                return True
            else:
                raise RuntimeError(f"Ollama server returned status {response.status_code}")
        except requests.ConnectionError as e:
            error_msg = (
                f"\n{'='*70}\n"
                f"[ERROR] Cannot connect to Ollama server at {self.endpoint}\n"
                f"{'='*70}\n\n"
                f"Ollama is not running or not accessible.\n\n"
                f"HOW TO FIX:\n"
                f"1. Install Ollama (if not already installed):\n"
                f"   Download from: https://ollama.ai\n\n"
                f"2. Download required models:\n"
                f"   ollama pull qwen2.5:7b\n"
                f"   ollama pull qwen2.5:14b\n\n"
                f"3. Start the Ollama server:\n"
                f"   ollama serve\n\n"
                f"4. Keep Ollama running in background while using this pipeline\n"
                f"{'='*70}\n"
            )
            raise RuntimeError(error_msg) from e
        except requests.Timeout:
            raise RuntimeError(
                f"Ollama server at {self.endpoint} is not responding (timeout). "
                f"Make sure it's running: ollama serve"
            )
        except Exception as e:
            raise RuntimeError(f"Error validating Ollama server: {e}. " f"Start with: ollama serve")

    def _check_available_models(self) -> List[str]:
        """Check which models are installed locally via HTTP API."""
        try:
            # Use HTTP API instead of subprocess (ollama CLI might not be in PATH)
            response = requests.get(f"{self.endpoint}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = []
                for model_info in data.get("models", []):
                    model_name = model_info.get("name")
                    if model_name:
                        models.append(model_name)
                logger.info(f"Found {len(models)} models on Ollama server")
                return models
            else:
                logger.warning(f"Cannot list ollama models (status {response.status_code})")
                return []
        except Exception as e:
            logger.error(f"Error checking ollama models: {e}")
            return []

    # Optimal temperatures per model tier (research-backed)
    _MODEL_TEMPERATURES = {
        "fast_classification": 0.1,  # JSON, yes/no, classification
        "code_analysis": 0.1,  # Code review
        "task_breakdown": 0.1,  # Structured JSON output
        "deep_reasoning": 0.4,  # Planning, architecture
        "complex_reasoning": 0.4,  # Same as deep
        "prompt_synthesis": 0.2,  # Structured generation
        "synthesis": 0.2,  # Same
        "pattern_matching": 0.3,  # Balanced
    }

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "fast_classification",
        temperature: float = None,
        format: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send chat request to Ollama.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Key from self.models (fast_classification, complex_reasoning, synthesis)
            temperature: Creativity level (0-1)
            format: Response format ('json' for structured output)
            system_prompt: System context (prepends to messages if provided)

        Returns:
            Dict with 'message' containing response content
        """
        # Auto-select temperature based on model tier if not specified
        if temperature is None:
            temperature = self._MODEL_TEMPERATURES.get(model, 0.3)

        # If Ollama is down, go straight to fallbacks
        if not self.ollama_available:
            return self._fallback_chain(messages, model, temperature)

        # Resolve model name
        model_name = self.models.get(model, model)

        # Check if model available
        if model_name not in self.available_models:
            logger.warning(f"Model {model_name} not available, trying fallback")
            return self._fallback_chain(messages, model, temperature)

        # Build request
        request_body = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
            "options": {
                # Context window: maximize for quality (16GB RAM, 8GB shared GPU)
                # qwen2.5:7b supports 32K, 14b supports 32K, llama3.2:3b supports 128K
                # 16K is safe sweet spot for 16GB RAM with 7b models
                "num_ctx": 16384 if "7b" in model_name or "3b" in model_name else 8192,
                "num_predict": 2048,  # Allow longer responses
            },
        }

        if format:
            request_body["format"] = format

        if system_prompt:
            # Inject system prompt at beginning
            messages = [{"role": "system", "content": system_prompt}] + messages
            request_body["messages"] = messages

        try:
            logger.debug(f"Calling Ollama: {model_name} with {len(messages)} messages")

            # Use HTTP API instead of subprocess (ollama CLI might not be in PATH)
            response = requests.post(
                f"{self.endpoint}/api/chat", json=request_body, timeout=120  # 2 minute timeout for complex reasoning
            )

            if response.status_code != 200:
                error_msg = f"Ollama error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return {"error": error_msg}

            result = response.json()
            logger.debug(f"Ollama response received ({len(result.get('message', {}).get('content', ''))} chars)")

            return result

        except (requests.Timeout, json.JSONDecodeError, Exception) as e:
            logger.warning(f"Ollama failed: {e}")
            return self._fallback_chain(messages, model, temperature)

    def _fallback_chain(self, messages, model_type, temperature=0.7):
        """Try Claude API SDK then claude CLI when Ollama is unavailable."""
        # Fallback 1: Claude API SDK
        try:
            r = self._chat_claude(messages=messages, model_type=model_type, temperature=temperature)
            return {"message": {"content": r, "role": "assistant"}, "model": "claude-api", "done": True}
        except Exception as e:
            logger.debug(f"Claude API SDK fallback: {e}")
        # Fallback 2: claude CLI (user's Claude Code subscription)
        try:
            r = self._chat_claude_cli(messages=messages, model_type=model_type)
            if r:
                return {"message": {"content": r, "role": "assistant"}, "model": "claude-cli", "done": True}
        except Exception as e:
            logger.debug(f"Claude CLI fallback: {e}")
        return {"error": "All LLM backends failed (Ollama down, no Claude API key, claude CLI failed)"}

    def _init_claude_fallback(self):
        """Initialize Claude API client for fallback if available."""
        try:
            import anthropic

            api_key = os.getenv("ANTHROPIC_KEY")
            if api_key:
                self.claude_client = anthropic.Anthropic(api_key=api_key)
                logger.info("Claude API fallback initialized (ANTHROPIC_KEY found)")
            else:
                logger.info("Claude API fallback not configured (set ANTHROPIC_KEY to enable)")
        except ImportError:
            logger.debug("anthropic SDK not installed, Claude fallback unavailable")
        except Exception as e:
            logger.debug(f"Could not initialize Claude fallback: {e}")

    def _chat_claude(
        self, messages: List[Dict[str, str]], model_type: str = "complex_reasoning", temperature: float = 0.7
    ) -> str:
        """Fallback to Claude API when Ollama unavailable."""
        if not self.claude_client:
            raise RuntimeError(
                "Claude API not configured. "
                "Set ANTHROPIC_KEY environment variable to enable fallback. "
                "Or start Ollama with: ollama serve"
            )

        # Map model types to Claude models
        model_map = {
            "fast_classification": "claude-haiku-4-5-20251001",
            "complex_reasoning": "claude-opus-4-6",
            "synthesis": "claude-sonnet-4-6",
        }

        claude_model = model_map.get(model_type, "claude-opus-4-6")

        try:
            logger.warning(f"Using Claude API fallback ({claude_model})")

            response = self.claude_client.messages.create(
                model=claude_model, max_tokens=2000, temperature=temperature, messages=messages
            )

            content = response.content[0].text
            return content

        except Exception as e:
            logger.error(f"Claude API fallback failed: {e}")
            raise

    def _chat_claude_cli(
        self, messages: List[Dict[str, str]], model_type: str = "fast_classification"
    ) -> Optional[str]:
        """Fallback to claude CLI (user's Claude Code subscription).

        Model selection mirrors the Ollama model map:
          fast_classification -> haiku (cheap, fast)
          complex_reasoning  -> opus (best quality for planning/analysis)
          synthesis          -> sonnet (balanced for generation)
        """
        import shutil

        claude_path = shutil.which("claude")
        if not claude_path:
            return None
        # Same model selection logic as Claude API SDK (_chat_claude)
        cli_model = {
            "fast_classification": "haiku",
            "complex_reasoning": "opus",
            "synthesis": "sonnet",
        }.get(model_type, "haiku")
        parts = []
        for m in messages:
            if m.get("role") == "system":
                parts.append(f"SYSTEM: {m['content']}")
            else:
                parts.append(m.get("content", ""))
        prompt = "\n\n".join(parts)[:10000]
        env = os.environ.copy()
        env["CLAUDE_WORKFLOW_RUNNING"] = "1"
        try:
            result = subprocess.run(
                [claude_path, "-p", "--model", cli_model, prompt],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0 and result.stdout.strip():
                logger.info(f"Claude CLI fallback OK: {len(result.stdout)} chars")
                return result.stdout.strip()
        except Exception as e:
            logger.warning(f"Claude CLI failed: {e}")
        return None


# Utility function for quick access
def get_ollama_service() -> OllamaService:
    """Get or create singleton Ollama service instance."""
    if not hasattr(get_ollama_service, "_instance"):
        get_ollama_service._instance = OllamaService()
    return get_ollama_service._instance
