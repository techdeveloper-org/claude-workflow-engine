"""
LLM Provider MCP Server - FastMCP-based LLM access for Claude Code.

Provides direct LLM access via MCP tools, wrapping the existing provider chain
from llm_call.py. Supports Ollama, Claude CLI, Anthropic API, and OpenAI.
Includes hybrid inference routing and model discovery.

Backend: Anthropic SDK + requests (Ollama) + Claude CLI
Transport: stdio

Tools (8):
  llm_generate, llm_list_models, llm_health_check, llm_git_commit_title,
  llm_discover_models, llm_select_model, llm_classify_step, llm_hybrid_generate
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

# Ensure src/mcp/ is in path for base package imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP
from base.response import to_json
from base.decorators import mcp_tool_handler

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


@mcp.tool()
@mcp_tool_handler
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
            return to_json({
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
                return to_json({
                    "success": False,
                    "error": f"Provider '{provider}' not available. Active: {[p.name for p in chain]}"
                })

            response = target.call(actual_prompt, model, temperature)
        else:
            # Use full chain with fallback
            response = llm_call(actual_prompt, model=model, temperature=temperature,
                               timeout=timeout)

        if response:
            return to_json({
                "success": True,
                "response": response,
                "model": model,
                "provider": provider,
                "temperature": temperature
            })
        else:
            return to_json({
                "success": False,
                "error": "All providers failed to generate a response",
                "active_providers": mod["get_active_providers"]()
            })

    except Exception as e:
        return to_json({"success": False, "error": str(e)})


@mcp.tool()
@mcp_tool_handler
def llm_list_models() -> str:
    """List all configured LLM providers and their available models."""
    try:
        mod = _get_llm_module()
        if "error" in mod:
            return to_json({
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

        return to_json({
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
        return to_json({"success": False, "error": str(e)})


# Health check cache (60s TTL)
_health_cache = {"timestamp": 0, "result": None}
_HEALTH_CACHE_TTL = 60


@mcp.tool()
@mcp_tool_handler
def llm_health_check(force_refresh: bool = False) -> str:
    """Check health and availability of all LLM providers concurrently.

    Runs parallel health probes to Ollama, Claude CLI, Anthropic API, and OpenAI.
    Results are cached for 60 seconds to avoid repeated slow checks.

    Args:
        force_refresh: If True, bypass cache and re-probe all providers
    """
    import time as _time

    # Return cached result if fresh
    if not force_refresh and _health_cache["result"]:
        age = _time.time() - _health_cache["timestamp"]
        if age < _HEALTH_CACHE_TTL:
            cached = json.loads(_health_cache["result"])
            cached["from_cache"] = True
            cached["cache_age_s"] = round(age, 1)
            return to_json(cached)

    try:
        import concurrent.futures

        results = {}

        def _probe_ollama():
            try:
                import urllib.request
                endpoint = os.getenv("OLLAMA_ENDPOINT", "http://127.0.0.1:11434")
                start = _time.time()
                req = urllib.request.Request(f"{endpoint}/api/tags", method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    latency = round((_time.time() - start) * 1000)
                    data = json.loads(resp.read().decode())
                    models = [m.get("name", "") for m in data.get("models", [])]
                    return {
                        "available": True, "status": "healthy",
                        "latency_ms": latency, "endpoint": endpoint,
                        "models": models, "model_count": len(models),
                    }
            except Exception as e:
                return {"available": False, "status": "unavailable", "error": str(e)[:80]}

        def _probe_claude_cli():
            try:
                import subprocess
                start = _time.time()
                result = subprocess.run(
                    ["claude", "--version"],
                    capture_output=True, text=True, timeout=5
                )
                latency = round((_time.time() - start) * 1000)
                if result.returncode == 0:
                    return {
                        "available": True, "status": "healthy",
                        "latency_ms": latency,
                        "version": result.stdout.strip()[:50],
                    }
                return {"available": False, "status": "error", "code": result.returncode}
            except FileNotFoundError:
                return {"available": False, "status": "not_installed"}
            except Exception as e:
                return {"available": False, "status": "error", "error": str(e)[:80]}

        def _probe_anthropic():
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not api_key:
                return {"available": False, "status": "no_api_key", "has_api_key": False}
            try:
                import urllib.request
                start = _time.time()
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps({
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "hi"}],
                    }).encode(),
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    latency = round((_time.time() - start) * 1000)
                    return {
                        "available": True, "status": "healthy",
                        "latency_ms": latency, "has_api_key": True,
                    }
            except Exception as e:
                err_str = str(e)[:80]
                # 401 = bad key, but connection works
                if "401" in err_str:
                    return {"available": False, "status": "invalid_key", "has_api_key": True}
                # Any HTTP error means API is reachable
                if "HTTP Error" in err_str:
                    return {"available": True, "status": "reachable", "has_api_key": True}
                return {"available": False, "status": "error", "error": err_str, "has_api_key": True}

        def _probe_openai():
            api_key = os.getenv("OPENAI_API_KEY", "")
            if not api_key:
                return {"available": False, "status": "no_api_key", "has_api_key": False}
            return {"available": True, "status": "configured", "has_api_key": True}

        # Run all probes concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(_probe_ollama): "ollama",
                executor.submit(_probe_claude_cli): "claude_cli",
                executor.submit(_probe_anthropic): "anthropic",
                executor.submit(_probe_openai): "openai",
            }
            for future in concurrent.futures.as_completed(futures, timeout=15):
                name = futures[future]
                try:
                    results[name] = future.result()
                except Exception as e:
                    results[name] = {"available": False, "status": "timeout", "error": str(e)[:80]}

        any_healthy = any(r.get("available") for r in results.values())

        # Also include module-level provider chain info
        mod = _get_llm_module()
        active_chain = []
        if "error" not in mod:
            active_chain = mod["get_active_providers"]()

        output = {
            "success": True,
            "healthy": any_healthy,
            "providers": results,
            "active_chain": active_chain,
            "from_cache": False,
            "checked_at": _time.time(),
        }

        # Cache the result
        _health_cache["timestamp"] = _time.time()
        _health_cache["result"] = to_json(output)

        return to_json(output)
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


@mcp.tool()
@mcp_tool_handler
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
            return to_json({
                "success": False,
                "error": f"LLM module not available: {mod['error']}"
            })

        # Try to use generate_llm_commit_title from llm_call module
        try:
            from langgraph_engine.llm_call import generate_llm_commit_title
            title = generate_llm_commit_title(commit_type=commit_type, cwd=cwd)
            if title:
                return to_json({
                    "success": True,
                    "title": title,
                    "commit_type": commit_type
                })
            return to_json({
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
                return to_json({"success": False, "error": "No staged changes found"})

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
                return to_json({"success": False, "error": "LLM call failed"})

            title = response.strip().splitlines()[0].strip().strip('"').strip("'")
            if commit_type and not title.lower().startswith(commit_type):
                title = f"{commit_type}: {title}"
            title = title[:69] + "..." if len(title) > 72 else title

            return to_json({
                "success": True,
                "title": title,
                "commit_type": commit_type
            })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


# =============================================================================
# HYBRID INFERENCE TOOLS (GPU-first routing + model discovery)
# =============================================================================

# Step classification mapping
_STEP_CLASSIFICATION = {
    "step0_prompt_generation": "complex_reasoning",
    "step1_plan_mode_decision": "classification",
    "step2_plan_execution": "complex_reasoning",
    "step3_task_analysis": "lightweight_analysis",
    "step4_model_selection": "complex_reasoning",
    "step5_skill_selection": "lightweight_analysis",
    "step6_tool_optimization": "no_llm",
    "step7_context_reading": "complex_reasoning",
    "step8_progress_tracking": "no_llm",
    "step9_git_commit": "no_llm",
    "step10_github_pr": "no_llm",
    "step11_github_issues": "no_llm",
    "step12_parallel_execution": "no_llm",
    "step13_failure_prevention": "no_llm",
}

# Model recommendations per step type
_MODEL_RECOMMENDATIONS = {
    "classification": {
        "gpu": "qwen2.5:7b",
        "description": "Fast classification - yes/no, type detection",
        "temperature": 0.1,
        "fallback": "fast",
    },
    "lightweight_analysis": {
        "gpu": "qwen2.5:7b",
        "description": "Quick analysis - skill selection, task classification",
        "temperature": 0.2,
        "fallback": "fast",
    },
    "deep_local": {
        "gpu": "qwen2.5:14b",
        "description": "Deep reasoning on local GPU (FREE)",
        "temperature": 0.3,
        "fallback": "balanced",
    },
    "complex_reasoning": {
        "gpu": None,
        "description": "Complex reasoning - requires Claude",
        "temperature": 0.4,
        "fallback": "deep",
    },
    "no_llm": {
        "gpu": None,
        "description": "No LLM needed - deterministic step",
        "temperature": 0,
        "fallback": None,
    },
}


@mcp.tool()
@mcp_tool_handler
def llm_classify_step(step_name: str) -> str:
    """Classify a pipeline step for optimal model routing.

    Returns the step type (classification/lightweight/deep/complex/no_llm)
    and recommended model.

    Args:
        step_name: Pipeline step name (e.g., 'step1_plan_mode_decision')
    """
    step_type = _STEP_CLASSIFICATION.get(step_name, "complex_reasoning")
    recommendation = _MODEL_RECOMMENDATIONS.get(step_type, _MODEL_RECOMMENDATIONS["complex_reasoning"])

    return to_json({
        "success": True,
        "step": step_name,
        "step_type": step_type,
        "recommended_gpu_model": recommendation["gpu"],
        "recommended_temperature": recommendation["temperature"],
        "fallback_tier": recommendation["fallback"],
        "description": recommendation["description"],
        "needs_llm": step_type != "no_llm",
    })


@mcp.tool()
@mcp_tool_handler
def llm_select_model(
    task_type: str = "",
    complexity: int = 5,
    step_name: str = ""
) -> str:
    """Intelligently select the best model for a task.

    Considers: task type, complexity score, step classification, and
    available providers.

    Args:
        task_type: Task type (e.g., 'Implementation', 'Bug Fix', 'Refactor')
        complexity: Complexity score (1-10)
        step_name: Optional pipeline step for step-aware routing
    """
    try:
        mod = _get_llm_module()
        providers = []
        if "error" not in mod:
            providers = mod["get_active_providers"]()

        # Step-based classification
        if step_name:
            step_type = _STEP_CLASSIFICATION.get(step_name, "complex_reasoning")
        else:
            # Complexity-based classification
            if complexity <= 3:
                step_type = "classification"
            elif complexity <= 6:
                step_type = "lightweight_analysis"
            elif complexity <= 8:
                step_type = "deep_local"
            else:
                step_type = "complex_reasoning"

        rec = _MODEL_RECOMMENDATIONS.get(step_type, _MODEL_RECOMMENDATIONS["complex_reasoning"])

        # Determine actual model
        if rec["gpu"] and "ollama" in providers:
            selected_model = rec["gpu"]
            selected_provider = "ollama"
            reason = f"GPU model ({rec['gpu']}) selected for {step_type} (local, fast, free)"
        elif rec["fallback"]:
            selected_model = rec["fallback"]
            selected_provider = "auto"
            reason = f"Cloud model tier '{rec['fallback']}' selected (GPU unavailable or complex task)"
        else:
            selected_model = None
            selected_provider = None
            reason = "No LLM needed for this step"

        return to_json({
            "success": True,
            "selected_model": selected_model,
            "selected_provider": selected_provider,
            "step_type": step_type,
            "temperature": rec["temperature"],
            "reason": reason,
            "task_type": task_type,
            "complexity": complexity,
            "active_providers": providers,
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


@mcp.tool()
@mcp_tool_handler
def llm_discover_models() -> str:
    """Discover all available local models (Ollama + local files).

    Queries Ollama API for installed models and checks local model directories.
    """
    try:
        models = []

        # Check Ollama models
        try:
            import urllib.request
            endpoint = os.getenv("OLLAMA_ENDPOINT", "http://127.0.0.1:11434")
            req = urllib.request.Request(f"{endpoint}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                for m in data.get("models", []):
                    models.append({
                        "name": m.get("name", ""),
                        "size": m.get("size", 0),
                        "size_gb": round(m.get("size", 0) / (1024**3), 1),
                        "platform": "gpu_ollama",
                        "modified": m.get("modified_at", ""),
                    })
        except Exception:
            pass

        # Check local model files
        local_dirs = [
            Path.home() / "Downloads" / "intel-ai" / "models",
            Path.home() / ".ollama" / "models",
        ]
        for model_dir in local_dirs:
            if model_dir.exists():
                for f in model_dir.rglob("*.gguf"):
                    models.append({
                        "name": f.stem,
                        "size_gb": round(f.stat().st_size / (1024**3), 1),
                        "platform": "local_gguf",
                        "path": str(f),
                    })

        return to_json({
            "success": True,
            "models": models,
            "total": len(models),
            "ollama_available": any(m["platform"] == "gpu_ollama" for m in models),
        })
    except Exception as e:
        return to_json({"success": False, "error": str(e)})


@mcp.tool()
@mcp_tool_handler
def llm_hybrid_generate(
    prompt: str,
    step_name: str = "",
    complexity: int = 5,
    temperature: Optional[float] = None
) -> str:
    """Generate text using hybrid GPU-first routing with Claude fallback.

    Routes to GPU (Ollama) for fast/lightweight steps, Claude for complex.
    Automatic fallback: GPU fail -> Claude CLI -> Anthropic API -> OpenAI.

    Args:
        prompt: The prompt text
        step_name: Pipeline step for step-aware routing
        complexity: Task complexity (1-10) for complexity-aware routing
        temperature: Override temperature
    """
    try:
        # Classify step
        if step_name:
            step_type = _STEP_CLASSIFICATION.get(step_name, "complex_reasoning")
        else:
            if complexity <= 3:
                step_type = "classification"
            elif complexity <= 6:
                step_type = "lightweight_analysis"
            else:
                step_type = "complex_reasoning"

        rec = _MODEL_RECOMMENDATIONS.get(step_type, _MODEL_RECOMMENDATIONS["complex_reasoning"])

        if step_type == "no_llm":
            return to_json({
                "success": True,
                "response": "",
                "step_type": step_type,
                "message": "No LLM needed for this step"
            })

        temp = temperature if temperature is not None else rec["temperature"]

        # Try GPU first if recommended
        if rec["gpu"]:
            try:
                import urllib.request
                endpoint = os.getenv("OLLAMA_ENDPOINT", "http://127.0.0.1:11434")
                payload = json.dumps({
                    "model": rec["gpu"],
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temp}
                }).encode()
                req = urllib.request.Request(
                    f"{endpoint}/api/generate",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read().decode())
                    response_text = result.get("response", "")
                    if response_text.strip():
                        return to_json({
                            "success": True,
                            "response": response_text,
                            "provider": "ollama",
                            "model": rec["gpu"],
                            "step_type": step_type,
                            "temperature": temp,
                            "routing": "gpu_primary"
                        })
            except Exception:
                pass  # Fall through to Claude

        # Fallback to provider chain
        mod = _get_llm_module()
        if "error" in mod:
            return to_json({"success": False, "error": f"LLM module unavailable: {mod['error']}"})

        tier = rec["fallback"] or "balanced"
        response = mod["llm_call"](prompt, model=tier, temperature=temp)

        if response:
            return to_json({
                "success": True,
                "response": response,
                "provider": "claude_fallback",
                "model": tier,
                "step_type": step_type,
                "temperature": temp,
                "routing": "cloud_fallback"
            })

        return to_json({"success": False, "error": "All providers failed"})

    except Exception as e:
        return to_json({"success": False, "error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
