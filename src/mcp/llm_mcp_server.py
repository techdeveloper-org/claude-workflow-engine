"""
LLM Provider MCP Server - FastMCP-based LLM access for Claude Code.

Provides direct LLM access via MCP tools, wrapping the existing provider chain
from llm_call.py. Supports Ollama, Claude CLI, Anthropic API, and OpenAI.
Backend: Anthropic SDK + requests (Ollama) + Claude CLI
Transport: stdio

Tools (4):
  llm_generate, llm_list_models, llm_health_check, llm_git_commit_title
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

# Add project paths for imports
_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

mcp = FastMCP("llm-provider", instructions="LLM provider access (Ollama, Claude, Anthropic, OpenAI)")

# Lazy import of llm_call module (heavy imports)
_llm_module = None


def _get_llm_module():
    """Lazy-load the llm_call module to avoid import overhead at startup."""
    global _llm_module
    if _llm_module is None:
        try:
            from langgraph_engine.llm_call import (
                llm_call,
                get_active_providers,
                _provider_chain,
                DEFAULT_TEMPERATURES,
            )
            _llm_module = {
                "llm_call": llm_call,
                "get_active_providers": get_active_providers,
                "provider_chain": _provider_chain,
                "default_temps": DEFAULT_TEMPERATURES,
            }
        except ImportError as e:
            _llm_module = {"error": str(e)}
    return _llm_module


def _json(data: dict) -> str:
    """Return compact JSON string."""
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
def llm_generate(
    prompt: str,
    model: str = "fast",
    provider: str = "auto",
    temperature: Optional[float] = None,
    json_mode: bool = False,
    timeout: int = 120
) -> str:
    """Generate text using configured LLM providers.

    Uses the provider chain with automatic fallback. Tries each configured
    provider in order until one succeeds.

    Args:
        prompt: The prompt text to send
        model: Tier - 'fast' (haiku/mini), 'balanced' (sonnet/4o), 'deep' (opus/4o)
        provider: 'auto' (use chain), or specific: 'ollama', 'claude_cli', 'anthropic', 'openai'
        temperature: Override temperature (default: auto per model tier).
            Guidelines: 0.0-0.1 for JSON/classification, 0.2-0.3 for structured, 0.4 for planning
        json_mode: If True, instruct the LLM to return valid JSON
        timeout: Timeout in seconds (default: 120)
    """
    try:
        mod = _get_llm_module()
        if "error" in mod:
            return _json({
                "success": False,
                "error": f"LLM module not available: {mod['error']}"
            })

        llm_call = mod["llm_call"]
        default_temps = mod["default_temps"]

        if temperature is None:
            temperature = default_temps.get(model, 0.3)

        # Append JSON instruction if json_mode is enabled
        actual_prompt = prompt
        if json_mode:
            actual_prompt = prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No explanation or markdown."

        if provider != "auto":
            # Direct provider call
            chain = mod["provider_chain"]
            target = None
            for p in chain:
                if p.name == provider:
                    target = p
                    break

            if not target:
                return _json({
                    "success": False,
                    "error": f"Provider '{provider}' not available. Active: {[p.name for p in chain]}"
                })

            response = target.call(actual_prompt, model, temperature)
        else:
            # Use full chain with fallback
            response = llm_call(actual_prompt, model=model, temperature=temperature,
                               timeout=timeout)

        if response:
            return _json({
                "success": True,
                "response": response,
                "model": model,
                "provider": provider,
                "temperature": temperature
            })
        else:
            return _json({
                "success": False,
                "error": "All providers failed to generate a response",
                "active_providers": mod["get_active_providers"]()
            })

    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def llm_list_models() -> str:
    """List all configured LLM providers and their available models."""
    try:
        mod = _get_llm_module()
        if "error" in mod:
            return _json({
                "success": False,
                "error": f"LLM module not available: {mod['error']}"
            })

        providers = []
        for p in mod["provider_chain"]:
            info = {"name": p.name, "available": p.is_available()}

            # Extract model info per provider type
            if hasattr(p, "_model_fast"):
                info["model_fast"] = p._model_fast
            if hasattr(p, "_model_deep"):
                info["model_deep"] = p._model_deep
            if hasattr(p, "_model_balanced"):
                info["model_balanced"] = p._model_balanced
            if hasattr(p, "MODEL_MAP"):
                info["model_map"] = p.MODEL_MAP

            providers.append(info)

        return _json({
            "success": True,
            "providers": providers,
            "active_count": len([p for p in providers if p["available"]]),
            "model_tiers": {
                "fast": "Classification, JSON, yes/no, titles (temp 0.1)",
                "balanced": "Skill selection, code review, synthesis (temp 0.3)",
                "deep": "Planning, complex reasoning, architecture (temp 0.4)"
            }
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def llm_health_check() -> str:
    """Check health and availability of all configured LLM providers."""
    try:
        mod = _get_llm_module()
        if "error" in mod:
            return _json({
                "success": False,
                "error": f"LLM module not available: {mod['error']}"
            })

        results = {}
        for p in mod["provider_chain"]:
            available = p.is_available()
            results[p.name] = {
                "available": available,
                "status": "healthy" if available else "unavailable"
            }

            # Provider-specific health info
            if p.name == "ollama" and hasattr(p, "_endpoint"):
                results[p.name]["endpoint"] = p._endpoint
            elif p.name == "claude_cli" and hasattr(p, "_claude_path"):
                results[p.name]["cli_path"] = p._claude_path
            elif p.name == "anthropic":
                results[p.name]["has_api_key"] = bool(os.getenv("ANTHROPIC_API_KEY"))
            elif p.name == "openai":
                results[p.name]["has_api_key"] = bool(os.getenv("OPENAI_API_KEY"))

        any_healthy = any(r["available"] for r in results.values())

        return _json({
            "success": True,
            "healthy": any_healthy,
            "providers": results,
            "active_chain": mod["get_active_providers"]()
        })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


@mcp.tool()
def llm_git_commit_title(
    commit_type: Optional[str] = None,
    cwd: Optional[str] = None
) -> str:
    """Generate a meaningful git commit title using LLM from staged diff.

    Reads the staged diff, sends it to the LLM, and returns a conventional
    commit title (max 72 chars).

    Args:
        commit_type: Optional semantic type (feat, fix, refactor, docs, etc.)
        cwd: Working directory for git commands (default: current dir)
    """
    try:
        mod = _get_llm_module()
        if "error" in mod:
            return _json({
                "success": False,
                "error": f"LLM module not available: {mod['error']}"
            })

        # Try to use generate_llm_commit_title from llm_call module
        try:
            from langgraph_engine.llm_call import generate_llm_commit_title
            title = generate_llm_commit_title(commit_type=commit_type, cwd=cwd)
            if title:
                return _json({
                    "success": True,
                    "title": title,
                    "commit_type": commit_type
                })
            return _json({
                "success": False,
                "error": "No staged changes found or LLM unavailable"
            })
        except ImportError:
            # Fallback: manual implementation
            import subprocess
            stat_result = subprocess.run(
                ["git", "diff", "--cached", "--stat"],
                capture_output=True, text=True, timeout=5, cwd=cwd
            )
            diff_result = subprocess.run(
                ["git", "diff", "--cached"],
                capture_output=True, text=True, timeout=5, cwd=cwd
            )
            stat_text = stat_result.stdout.strip() if stat_result.returncode == 0 else ""
            diff_text = diff_result.stdout[:3000] if diff_result.returncode == 0 else ""

            if not stat_text and not diff_text:
                return _json({"success": False, "error": "No staged changes found"})

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
                f"- Be specific\n"
                f"- No quotes, no explanation, just the commit title line\n"
            )

            llm_call = mod["llm_call"]
            response = llm_call(prompt, model="fast", temperature=0.1, timeout=15)
            if not response:
                return _json({"success": False, "error": "LLM call failed"})

            title = response.strip().splitlines()[0].strip().strip('"').strip("'")
            if commit_type and not title.lower().startswith(commit_type):
                title = f"{commit_type}: {title}"
            title = title[:69] + "..." if len(title) > 72 else title

            return _json({
                "success": True,
                "title": title,
                "commit_type": commit_type
            })
    except Exception as e:
        return _json({"success": False, "error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
