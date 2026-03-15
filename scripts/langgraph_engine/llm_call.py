"""
Shared LLM Call Helper - Single entry point for all LLM calls in the pipeline.

Fallback chain: Ollama -> claude CLI (user's subscription)
All scripts should use this instead of direct urllib calls to Ollama.

Model tiers:
  fast     -> haiku  (classification, JSON, yes/no, titles)
  balanced -> sonnet (skill selection, code review, synthesis)
  deep     -> opus  (planning, complex reasoning, architecture)

Temperature guidelines (based on research):
  0.0-0.1: JSON output, classification, code review
  0.2-0.3: Skill selection, title generation, structured output
  0.4:     Planning, complex reasoning
  0.7+:    Creative tasks (not used in pipeline)

Usage:
    from langgraph_engine.llm_call import llm_call
    response = llm_call(prompt, model="fast", temperature=0.1)
"""

import os
import sys
import json
import subprocess
import shutil
from typing import Optional

# Ollama config
OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/api/generate")
OLLAMA_MODEL_FAST = os.getenv("OLLAMA_MODEL_FAST", os.getenv("OLLAMA_MODEL", "qwen2.5:7b"))
OLLAMA_MODEL_DEEP = os.getenv("OLLAMA_MODEL_DEEP", "qwen2.5:14b")

# Claude CLI model mapping
CLAUDE_MODEL_MAP = {
    "fast": "haiku",
    "balanced": "sonnet",
    "deep": "opus",
    # Legacy keys
    "fast_classification": "haiku",
    "complex_reasoning": "opus",
    "synthesis": "sonnet",
    "planning": "opus",
    "code_review": "sonnet",
}

# Default temperature per model tier (research-backed)
DEFAULT_TEMPERATURES = {
    "fast": 0.1,       # Classification, JSON, yes/no -> near-deterministic
    "balanced": 0.3,   # Skill selection, synthesis -> slight flexibility
    "deep": 0.4,       # Planning, complex reasoning -> quality exploration
    "fast_classification": 0.1,
    "complex_reasoning": 0.4,
    "synthesis": 0.2,
    "planning": 0.4,
    "code_review": 0.1,
}


def llm_call(
    prompt: str,
    model: str = "fast",
    temperature: Optional[float] = None,
    timeout: int = 120,
    json_mode: bool = False,
) -> Optional[str]:
    """Make an LLM call with automatic fallback chain.

    Args:
        prompt: The prompt text to send
        model: "fast" (haiku), "balanced" (sonnet), "deep" (opus)
        temperature: Override temp (default: auto per model tier)
        timeout: Max seconds to wait
        json_mode: If True, request JSON format from Ollama

    Returns:
        Response text string, or None if all backends failed.
    """
    # Auto-select temperature based on model tier if not specified
    if temperature is None:
        temperature = DEFAULT_TEMPERATURES.get(model, 0.3)

    # Try 1: Ollama (local, free)
    response = _call_ollama(prompt, model, temperature, timeout, json_mode)
    if response:
        return response

    # Try 2: claude CLI (user's subscription)
    response = _call_claude_cli(prompt, model, timeout)
    if response:
        return response

    return None


def _call_ollama(prompt, model, temperature, timeout, json_mode):
    """Try Ollama HTTP API."""
    import urllib.request
    import urllib.error

    ollama_model = OLLAMA_MODEL_DEEP if model in ("deep", "complex_reasoning", "planning") else OLLAMA_MODEL_FAST

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
            OLLAMA_ENDPOINT,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())
            text = result.get("response", "").strip()
            if text:
                return text
    except Exception:
        pass

    return None


def _call_claude_cli(prompt, model, timeout):
    """Try claude CLI with user's subscription."""
    claude_path = shutil.which("claude")
    if not claude_path:
        return None

    cli_model = CLAUDE_MODEL_MAP.get(model, "haiku")

    # Truncate to avoid pipe/arg issues
    if len(prompt) > 10000:
        prompt = prompt[:10000] + "\n[truncated]"

    env = os.environ.copy()
    env["CLAUDE_WORKFLOW_RUNNING"] = "1"

    try:
        result = subprocess.run(
            [claude_path, "-p", "--model", cli_model, prompt],
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
