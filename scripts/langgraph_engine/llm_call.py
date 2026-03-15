"""
Shared LLM Call Module - Strategy Pattern with Provider Interface.

Design Patterns:
  - Strategy: LLMProvider ABC defines the interface, concrete classes implement it
  - Chain of Responsibility: Fallback chain tries providers in configured order
  - Singleton: Each provider instantiated once, reused across all calls
  - Factory: get_providers() builds the chain from configuration

Configuration (env vars):
  LLM_PROVIDER=ollama          # Primary provider: ollama, claude_cli, openai, auto (default)
  LLM_FALLBACK=claude_cli      # Fallback provider (comma-separated for chain)
  OLLAMA_ENDPOINT=http://localhost:11434/api/generate
  OLLAMA_MODEL_FAST=qwen2.5:7b
  OLLAMA_MODEL_DEEP=qwen2.5:14b
  OPENAI_API_KEY=sk-...
  OPENAI_MODEL_FAST=gpt-4o-mini
  OPENAI_MODEL_DEEP=gpt-4o

Model tiers (same across all providers):
  fast     -> classification, JSON, yes/no, titles
  balanced -> skill selection, code review, synthesis
  deep     -> planning, complex reasoning, architecture

Temperature guidelines (research-backed):
  0.0-0.1: JSON output, classification, code review
  0.2-0.3: Skill selection, title generation, structured output
  0.4:     Planning, complex reasoning
  0.7+:    Creative tasks (not used in pipeline)

Usage (unchanged - backward compatible):
    from langgraph_engine.llm_call import llm_call
    response = llm_call(prompt, model="fast", temperature=0.1)
"""

import os
import sys
import json
import subprocess
import shutil
from abc import ABC, abstractmethod
from typing import Optional, List


# =============================================================================
# INTERFACE: LLMProvider (Strategy Pattern)
# =============================================================================

class LLMProvider(ABC):
    """Abstract interface for LLM providers.

    All providers must implement call() and is_available().
    Same input/output contract regardless of backend.
    """

    @abstractmethod
    def call(
        self,
        prompt: str,
        model: str = "fast",
        temperature: float = 0.3,
        timeout: int = 120,
        json_mode: bool = False,
    ) -> Optional[str]:
        """Send prompt to LLM and return response text.

        Args:
            prompt: The prompt text to send.
            model: Tier - "fast", "balanced", or "deep".
            temperature: Sampling temperature (0.0-1.0).
            timeout: Max seconds to wait for response.
            json_mode: If True, request JSON-formatted output.

        Returns:
            Response text string, or None on failure.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and reachable.

        Called ONCE at init time. Result is cached.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        ...


# =============================================================================
# IMPLEMENTATION: OllamaProvider
# =============================================================================

class OllamaProvider(LLMProvider):
    """Local Ollama LLM provider (free, no API key needed)."""

    def __init__(self):
        self._endpoint = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/api/generate")
        self._model_fast = os.getenv("OLLAMA_MODEL_FAST", os.getenv("OLLAMA_MODEL", "qwen2.5:7b"))
        self._model_deep = os.getenv("OLLAMA_MODEL_DEEP", "qwen2.5:14b")
        self._available = self._check_health()

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        return self._available

    def _check_health(self) -> bool:
        """Check Ollama server health (3s timeout)."""
        try:
            import urllib.request
            from urllib.parse import urlparse
            parsed = urlparse(self._endpoint)
            health_url = f"{parsed.scheme}://{parsed.netloc}/api/tags"
            with urllib.request.urlopen(urllib.request.Request(health_url), timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def call(self, prompt, model="fast", temperature=0.3, timeout=120, json_mode=False):
        if not self._available:
            return None

        import urllib.request

        ollama_model = self._model_deep if model in ("deep", "complex_reasoning", "planning") else self._model_fast

        try:
            payload = {
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "temperature": temperature,
                "options": {"num_ctx": 16384, "num_predict": 2048},
            }
            if json_mode:
                payload["format"] = "json"

            req = urllib.request.Request(
                self._endpoint,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=min(timeout, 30)) as resp:
                result = json.loads(resp.read().decode())
                text = result.get("response", "").strip()
                if text:
                    return text
        except Exception:
            pass
        return None


# =============================================================================
# IMPLEMENTATION: ClaudeCLIProvider
# =============================================================================

class ClaudeCLIProvider(LLMProvider):
    """Claude Code CLI provider (uses user's Anthropic subscription)."""

    MODEL_MAP = {
        "fast": "haiku",
        "balanced": "sonnet",
        "deep": "opus",
        "fast_classification": "haiku",
        "complex_reasoning": "opus",
        "synthesis": "sonnet",
        "planning": "opus",
        "code_review": "sonnet",
    }

    def __init__(self):
        self._claude_path = shutil.which("claude")
        self._available = self._claude_path is not None

    @property
    def name(self) -> str:
        return "claude_cli"

    def is_available(self) -> bool:
        return self._available

    def call(self, prompt, model="fast", temperature=0.3, timeout=120, json_mode=False):
        if not self._available:
            return None

        cli_model = self.MODEL_MAP.get(model, "haiku")

        if len(prompt) > 10000:
            prompt = prompt[:10000] + "\n[truncated]"

        env = os.environ.copy()
        env["CLAUDE_WORKFLOW_RUNNING"] = "1"

        try:
            result = subprocess.run(
                [self._claude_path, "-p", "--model", cli_model, prompt],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None


# =============================================================================
# IMPLEMENTATION: OpenAIProvider
# =============================================================================

class OpenAIProvider(LLMProvider):
    """OpenAI API provider (requires OPENAI_API_KEY)."""

    MODEL_MAP = {
        "fast": "gpt-4o-mini",
        "balanced": "gpt-4o",
        "deep": "gpt-4o",
        "fast_classification": "gpt-4o-mini",
        "complex_reasoning": "gpt-4o",
        "synthesis": "gpt-4o",
        "planning": "gpt-4o",
        "code_review": "gpt-4o",
    }

    def __init__(self):
        self._api_key = os.getenv("OPENAI_API_KEY", "")
        self._base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")
        # Allow model override via env
        self._model_fast = os.getenv("OPENAI_MODEL_FAST", self.MODEL_MAP["fast"])
        self._model_deep = os.getenv("OPENAI_MODEL_DEEP", self.MODEL_MAP["deep"])
        self._available = bool(self._api_key)

    @property
    def name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        return self._available

    def call(self, prompt, model="fast", temperature=0.3, timeout=120, json_mode=False):
        if not self._available:
            return None

        import urllib.request

        openai_model = self._model_deep if model in ("deep", "complex_reasoning", "planning") else self._model_fast

        try:
            payload = {
                "model": openai_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": 2048,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            req = urllib.request.Request(
                self._base_url,
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=min(timeout, 60)) as resp:
                result = json.loads(resp.read().decode())
                text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if text:
                    return text
        except Exception:
            pass
        return None


# =============================================================================
# PROVIDER CHAIN (Chain of Responsibility + Factory)
# =============================================================================

# Default temperature per model tier (research-backed)
DEFAULT_TEMPERATURES = {
    "fast": 0.1,
    "balanced": 0.3,
    "deep": 0.4,
    "fast_classification": 0.1,
    "complex_reasoning": 0.4,
    "synthesis": 0.2,
    "planning": 0.4,
    "code_review": 0.1,
}

# Provider registry (Singleton instances)
_PROVIDER_REGISTRY = {
    "ollama": OllamaProvider,
    "claude_cli": ClaudeCLIProvider,
    "openai": OpenAIProvider,
}

_provider_chain: List[LLMProvider] = []


def _build_provider_chain() -> List[LLMProvider]:
    """Build the provider chain from configuration (Factory Pattern).

    Configuration via env vars:
      LLM_PROVIDER=auto       -> try all available providers (default)
      LLM_PROVIDER=ollama     -> use only Ollama
      LLM_PROVIDER=claude_cli -> use only Claude CLI
      LLM_PROVIDER=openai     -> use only OpenAI
      LLM_FALLBACK=claude_cli,openai -> fallback chain (comma-separated)

    Returns:
        List of instantiated, available providers in priority order.
    """
    primary = os.getenv("LLM_PROVIDER", "auto").strip().lower()
    fallback_str = os.getenv("LLM_FALLBACK", "").strip()

    chain = []

    if primary == "auto":
        # Auto mode: try Ollama -> Claude CLI -> OpenAI
        order = ["ollama", "claude_cli", "openai"]
    else:
        order = [primary]
        if fallback_str:
            order.extend(f.strip() for f in fallback_str.split(",") if f.strip())

    for provider_name in order:
        cls = _PROVIDER_REGISTRY.get(provider_name)
        if cls:
            instance = cls()
            if instance.is_available():
                chain.append(instance)

    return chain


# Build chain once at import time (Singleton)
_provider_chain = _build_provider_chain()


# =============================================================================
# PUBLIC API (Backward Compatible)
# =============================================================================

def llm_call(
    prompt: str,
    model: str = "fast",
    temperature: Optional[float] = None,
    timeout: int = 120,
    json_mode: bool = False,
) -> Optional[str]:
    """Make an LLM call with automatic fallback chain.

    Tries each configured provider in order until one succeeds.
    Fully backward compatible - same signature as before.

    Args:
        prompt: The prompt text to send.
        model: "fast" (haiku/mini), "balanced" (sonnet/4o), "deep" (opus/4o).
        temperature: Override temp (default: auto per model tier).
        timeout: Max seconds to wait.
        json_mode: If True, request JSON format.

    Returns:
        Response text string, or None if all providers failed.
    """
    if temperature is None:
        temperature = DEFAULT_TEMPERATURES.get(model, 0.3)

    for provider in _provider_chain:
        response = provider.call(prompt, model, temperature, timeout, json_mode)
        if response:
            return response

    return None


def get_active_providers() -> List[str]:
    """Return names of currently active providers in chain order."""
    return [p.name for p in _provider_chain]


def generate_llm_commit_title(commit_type: str = None, cwd: str = None) -> Optional[str]:
    """Generate a meaningful commit title using LLM with staged diff context.

    Single source of truth for LLM-powered commit messages. Used by both
    git-auto-commit-policy.py and github_pr_workflow.py.

    Args:
        commit_type: Optional semantic type (feat, fix, refactor, etc.)
        cwd: Working directory for git commands (default: current dir)

    Returns:
        Commit title string (max 72 chars), or None if LLM unavailable.
    """
    try:
        stat_result = subprocess.run(
            ['git', 'diff', '--cached', '--stat'],
            capture_output=True, text=True, timeout=5, cwd=cwd
        )
        stat_text = stat_result.stdout.strip() if stat_result.returncode == 0 else ""

        diff_result = subprocess.run(
            ['git', 'diff', '--cached'],
            capture_output=True, text=True, timeout=5, cwd=cwd
        )
        diff_text = diff_result.stdout[:3000] if diff_result.returncode == 0 else ""

        if not stat_text and not diff_text:
            return None

        type_hint = f"Commit type: {commit_type}\n" if commit_type else ""
        type_rule = (f"- Start with type prefix: {commit_type}:\n" if commit_type
                     else "- Use conventional commit format: type: description\n")

        prompt = (
            f"Generate a git commit message for these changes.\n"
            f"{type_hint}\n"
            f"Changed files:\n{stat_text}\n\n"
            f"Diff (truncated):\n{diff_text}\n\n"
            f"Rules:\n"
            f"- Return ONLY the commit title (one line, under 72 chars)\n"
            f"{type_rule}"
            f"- Focus on WHAT changed and WHY, not just file names\n"
            f"- Be specific: 'fix stash detection using stdout+stderr' not 'fix issues'\n"
            f"- No quotes, no explanation, just the commit title line\n"
        )

        response = llm_call(prompt, model="fast", temperature=0.1, timeout=15)
        if not response:
            return None

        title = response.strip().splitlines()[0].strip().strip('"').strip("'")
        if commit_type and not title.lower().startswith(commit_type):
            title = f"{commit_type}: {title}"
        return title[:69] + "..." if len(title) > 72 else title

    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None
