"""
Ollama Service Layer - GPU-based local LLM integration for Level 3 execution.

Provides interface to local Ollama GPU models for:
- Step 1: Plan mode decision (fast classification via qwen2.5:7b)
- Step 3: Task breakdown validation (reasoning via granite4:3b)
- Step 5: Skill and agent selection (pattern matching via qwen2.5:7b)
- Step 7: Final prompt generation (synthesis via qwen2.5:7b)

Configuration:
- Primary endpoint: http://127.0.0.1:11434 (default Ollama)
- Models: qwen2.5:7b (fast classification, synthesis), granite4:3b (reasoning)
- Fallback: Claude API via ANTHROPIC_KEY environment variable
"""

import json
import subprocess
import os
import requests
from typing import Dict, Any, Optional, List
from loguru import logger
from pathlib import Path


class OllamaService:
    """Manages communication with local Ollama LLM."""

    def __init__(self, endpoint: str = "http://127.0.0.1:11434"):
        self.endpoint = endpoint

        # VALIDATE OLLAMA SERVER IS RUNNING
        self._validate_ollama_server()

        self.available_models = self._check_available_models()

        # Model routing
        # Setup: run intel-ai/models/gpu/import-models.bat
        #
        # Strategy:
        #   14b steps (deep reasoning): qwen2.5:14b -> if GPU can't handle -> Claude CLI
        #   7b steps (classification):  qwen2.5:7b (7b is enough for yes/no)
        #   3b steps (breakdown):       llama3.2:3b (3b is enough for structured output)
        #
        # If 14b not available, HybridInferenceManager handles Claude CLI fallback
        self.models = {
            # 14B - deep reasoning (Steps 0, 2, 5, 7, 14)
            "deep_reasoning": "qwen2.5:14b",          # If GPU can't run -> Claude CLI fallback
            "prompt_synthesis": "qwen2.5:14b",         # If GPU can't run -> Claude CLI fallback
            # 7B - fast tasks (Steps 1, 8, 11)
            "fast_classification": "qwen2.5:7b",       # Step 1: plan yes/no
            "code_analysis": "qwen2.5:7b",             # Step 11: code review patterns
            # 3B - lightweight (Step 3)
            "task_breakdown": "llama3.2:3b",            # Step 3: structured task analysis
            # Backward compatibility keys
            "complex_reasoning": "qwen2.5:14b",        # Legacy key -> 14B
            "synthesis": "qwen2.5:14b",                # Legacy key -> 14B
            "pattern_matching": "qwen2.5:14b",         # Legacy key -> 14B
        }

        # Fallback to first available model if configured models not found
        if self.available_models:
            for key in self.models:
                if self.models[key] not in self.available_models:
                    self.models[key] = self.available_models[0]
                    logger.warning(f"Model {self.models[key]} not available, using {self.available_models[0]} instead")

        logger.info(f"Ollama service initialized at {endpoint}")
        logger.info(f"Available models: {self.available_models}")

        # Initialize Claude API client for fallback
        self.claude_client = None
        self._init_claude_fallback()

    def _validate_ollama_server(self):
        """Validate that Ollama server is running and accessible."""
        try:
            response = requests.get(f"{self.endpoint}/api/tags", timeout=3)
            if response.status_code == 200:
                logger.info(f"✓ Ollama server is running at {self.endpoint}")
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
            raise RuntimeError(
                f"Error validating Ollama server: {e}. "
                f"Start with: ollama serve"
            )

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
                logger.info(f"✓ Found {len(models)} models on Ollama server")
                return models
            else:
                logger.warning(f"Cannot list ollama models (status {response.status_code})")
                return []
        except Exception as e:
            logger.error(f"Error checking ollama models: {e}")
            return []

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "fast_classification",
        temperature: float = 0.7,
        format: Optional[str] = None,
        system_prompt: Optional[str] = None
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
        # Resolve model name
        model_name = self.models.get(model, model)

        # Check if model available
        if model_name not in self.available_models:
            logger.error(f"Model {model_name} not available. Available: {self.available_models}")
            return {"error": f"Model {model_name} not installed"}

        # Build request
        request_body = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
            "num_ctx": 8192  # CRITICAL: Increase context window from default 2048 to 8192
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
                f"{self.endpoint}/api/chat",
                json=request_body,
                timeout=120  # 2 minute timeout for complex reasoning
            )

            if response.status_code != 200:
                error_msg = f"Ollama error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return {"error": error_msg}

            result = response.json()
            logger.debug(f"Ollama response received ({len(result.get('message', {}).get('content', ''))} chars)")

            return result

        except (requests.Timeout, json.JSONDecodeError, Exception) as e:
            # Try Claude API fallback
            logger.warning(f"Ollama failed, attempting Claude API fallback: {e}")
            try:
                claude_response = self._chat_claude(
                    messages=messages,
                    model_type=model,
                    temperature=temperature
                )
                # Return in same format as Ollama
                return {
                    "message": {
                        "content": claude_response,
                        "role": "assistant"
                    },
                    "model": "claude-fallback",
                    "done": True
                }
            except Exception as fallback_error:
                logger.error(f"Claude fallback also failed: {fallback_error}")
                return {"error": f"Both Ollama and Claude failed: {str(e)} / {str(fallback_error)}"}


    def _init_claude_fallback(self):
        """Initialize Claude API client for fallback if available."""
        try:
            import anthropic
            api_key = os.getenv("ANTHROPIC_KEY")
            if api_key:
                self.claude_client = anthropic.Anthropic(api_key=api_key)
                logger.info("✓ Claude API fallback initialized (ANTHROPIC_KEY found)")
            else:
                logger.info("Claude API fallback not configured (set ANTHROPIC_KEY to enable)")
        except ImportError:
            logger.debug("anthropic SDK not installed, Claude fallback unavailable")
        except Exception as e:
            logger.debug(f"Could not initialize Claude fallback: {e}")

    def _chat_claude(
        self,
        messages: List[Dict[str, str]],
        model_type: str = "complex_reasoning",
        temperature: float = 0.7
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
            "synthesis": "claude-sonnet-4-6"
        }

        claude_model = model_map.get(model_type, "claude-opus-4-6")

        try:
            logger.warning(f"Using Claude API fallback ({claude_model})")

            response = self.claude_client.messages.create(
                model=claude_model,
                max_tokens=2000,
                temperature=temperature,
                messages=messages
            )

            content = response.content[0].text
            return content

        except Exception as e:
            logger.error(f"Claude API fallback failed: {e}")
            raise

    # ===== LEVEL 3 STEP 1: PLAN MODE DECISION =====

    def step1_plan_mode_decision(self, toon: Dict[str, Any], user_requirement: str) -> Dict[str, Any]:
        """
        Determine if plan mode is required based on TOON and user requirement.

        Uses: qwen2.5:7b (fast classification)

        Args:
            toon: ToonAnalysis object (complexity_score, files_loaded_count, context)
            user_requirement: User's original requirement text

        Returns:
            {
                "plan_required": bool,
                "reasoning": str,
                "risk_level": "low" | "medium" | "high"
            }
        """
        prompt = f"""Analyze the project TOON and user requirement.

PROJECT TOON:
- Complexity Score: {toon.get('complexity_score', 0)}/10
- Files Loaded: {toon.get('files_loaded_count', 0)}
- Has SRS: {toon.get('context', {}).get('srs', False)}
- Has README: {toon.get('context', {}).get('readme', False)}
- Has CLAUDE.md: {toon.get('context', {}).get('claude_md', False)}

USER REQUIREMENT:
{user_requirement}

Determine if PLAN MODE is required based on:
1. Complexity score (> 6 often needs planning)
2. Project architecture (multi-file changes)
3. Requirement complexity (bug vs feature vs refactor)
4. Risk assessment (data loss, breaking changes)

Return ONLY valid JSON (no markdown, no explanation):
{{
  "plan_required": true or false,
  "reasoning": "brief explanation",
  "risk_level": "low" or "medium" or "high"
}}"""

        response = self.chat(
            messages=[{"role": "user", "content": prompt}],
            model="fast_classification",
            format="json"
        )

        if "error" in response:
            logger.error(f"Step 1 plan decision failed: {response['error']}")
            # Fallback: assume plan needed for safety
            return {
                "plan_required": True,
                "reasoning": "Error in LLM evaluation, defaulting to plan mode",
                "risk_level": "medium"
            }

        try:
            content = response.get("message", {}).get("content", "{}")
            result = json.loads(content)

            # Validate response structure
            required_keys = {"plan_required", "reasoning", "risk_level"}
            if not required_keys.issubset(result.keys()):
                logger.warning(f"Incomplete response from Step 1: {result}")
                return {
                    "plan_required": True,
                    "reasoning": "Incomplete LLM response, defaulting to plan",
                    "risk_level": "medium"
                }

            logger.info(f"Step 1 decision: plan_required={result['plan_required']}, risk={result['risk_level']}")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Step 1 JSON parse error: {e}")
            return {
                "plan_required": True,
                "reasoning": "JSON parse error, defaulting to plan mode",
                "risk_level": "medium"
            }

    # ===== LEVEL 3 STEP 5: SKILL & AGENT SELECTION =====

    def step5_skill_agent_selection(
        self,
        blueprint: Dict[str, Any],
        available_skills: List[str],
        available_agents: List[str]
    ) -> Dict[str, Any]:
        """
        Select required skills and agents for task execution (WORKFLOW.md Compliant).

        CRITICAL: Uses full skill/agent definitions from blueprint if available.
        This allows LLM to understand what each skill/agent actually does.

        Uses: qwen2.5:14b (medium depth analysis)

        Args:
            blueprint: ExecutionBlueprint with:
              - phases and tasks
              - available_skills_full_definitions (if present - FULL skill content)
              - available_agents_full_definitions (if present - FULL agent content)
            available_skills: List of available skill names
            available_agents: List of available agent names

        Returns:
            {
                "skill_mappings": [...],
                "final_skills_selected": [...],
                "final_agents_selected": [...]
            }
        """
        # Format phases for LLM
        phases_text = ""
        for phase in blueprint.get("phases", []):
            phases_text += f"- Phase {phase.get('phase_number')}: {phase.get('title')}\n"
            for task in phase.get("tasks", []):
                phases_text += f"  * {task}\n"

        # FORMAT SKILL DEFINITIONS FOR LLM
        skills_section = "AVAILABLE SKILLS WITH DEFINITIONS:\n\n"
        skills_full_defs = blueprint.get("available_skills_full_definitions", [])

        if skills_full_defs:
            # Use FULL DEFINITIONS if available
            for skill in skills_full_defs:
                skill_name = skill.get("name", "unknown")
                skill_content = skill.get("content", "No description")  # FULL content (no truncation)
                skills_section += f"## {skill_name}\n{skill_content}\n\n"
            logger.info(f"Using FULL skill definitions ({len(skills_full_defs)} skills) for LLM")
        else:
            # Fallback to names only
            skills_section += json.dumps(available_skills, indent=2)
            logger.info(f"Using skill names only ({len(available_skills)} skills)")

        # FORMAT AGENT DEFINITIONS FOR LLM
        agents_section = "AVAILABLE AGENTS WITH DEFINITIONS:\n\n"
        agents_full_defs = blueprint.get("available_agents_full_definitions", [])

        if agents_full_defs:
            # Use FULL DEFINITIONS if available
            for agent in agents_full_defs:
                agent_name = agent.get("name", "unknown")
                agent_content = agent.get("content", "No description")  # FULL content (no truncation)
                agents_section += f"## {agent_name}\n{agent_content}\n\n"
            logger.info(f"Using FULL agent definitions ({len(agents_full_defs)} agents) for LLM")
        else:
            # Fallback to names only
            agents_section += json.dumps(available_agents, indent=2)
            logger.info(f"Using agent names only ({len(available_agents)} agents)")

        prompt = f"""Analyze the execution blueprint and select required skills and agents.

EXECUTION PLAN:
{blueprint.get('plan', 'No plan provided')}

PHASES:
{phases_text}

RISK LEVEL: {blueprint.get('risks', {}).get('risk_level', 'medium')}

{skills_section}

{agents_section}

For each major task/phase, identify:
1. Which skills are needed
2. Which agent(s) can execute this phase
3. Confidence level for each skill match (0-1)

Return ONLY valid JSON (no markdown):
{{
  "skill_mappings": [
    {{
      "task_id": "Task-1",
      "task_name": "description",
      "required_skills": ["skill1", "skill2"],
      "required_agents": ["agent1"],
      "skill_confidence": {{"skill1": 0.95, "skill2": 0.80}}
    }}
  ],
  "final_skills_selected": ["skill1", "skill2"],
  "final_agents_selected": ["agent1"]
}}"""

        response = self.chat(
            messages=[{"role": "user", "content": prompt}],
            model="complex_reasoning",
            format="json"
        )

        if "error" in response:
            logger.error(f"Step 5 skill selection failed: {response['error']}")
            # Fallback: empty selection
            return {
                "skill_mappings": [],
                "final_skills_selected": [],
                "final_agents_selected": []
            }

        try:
            content = response.get("message", {}).get("content", "{}")
            result = json.loads(content)
            logger.info(f"Step 5: Selected {len(result.get('final_skills_selected', []))} skills, "
                       f"{len(result.get('final_agents_selected', []))} agents")
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Step 5 JSON parse error: {e}")
            return {
                "skill_mappings": [],
                "final_skills_selected": [],
                "final_agents_selected": []
            }

    # ===== LEVEL 3 STEP 7: FINAL PROMPT GENERATION =====

    def step7_final_prompt_generation(self, toon_final: Dict[str, Any]) -> str:
        """
        Generate final execution prompt from merged TOON object.

        Uses: qwen2.5:14b (synthesis)

        Args:
            toon_final: Final merged TOON with all context, skills, agents

        Returns:
            Execution prompt text (plain, no markdown)
        """
        # Format TOON data for LLM
        phases_text = ""
        for phase in toon_final.get("phases", []):
            phases_text += f"\nPhase {phase.get('phase_number')}: {phase.get('title')}\n"
            phases_text += f"  Description: {phase.get('description')}\n"
            phases_text += f"  Tasks:\n"
            for task in phase.get("tasks", []):
                phases_text += f"    - {task}\n"
            phases_text += f"  Files affected: {', '.join(phase.get('files_affected', []))}\n"

        skills_text = ", ".join(toon_final.get("final_skills_selected", []))
        agents_text = ", ".join(toon_final.get("final_agents_selected", []))

        prompt = f"""Convert this execution blueprint into a clear, actionable execution prompt.

PROJECT CONTEXT:
Session ID: {toon_final.get('session_id')}
Complexity: {toon_final.get('complexity_score')}/10
Files affected: {len(toon_final.get('files_affected', []))} files

MASTER PLAN:
{toon_final.get('plan', 'No plan')}

EXECUTION PHASES:{phases_text}

RISK ASSESSMENT:
Level: {toon_final.get('risks', {}).get('risk_level', 'medium')}
Factors: {', '.join(toon_final.get('risks', {}).get('factors', []))}
Mitigation: {', '.join(toon_final.get('risks', {}).get('mitigation', []))}

SELECTED SKILLS: {skills_text}
SELECTED AGENTS: {agents_text}

Create a single, coherent execution prompt that:
1. Clearly states what needs to be implemented
2. Lists all files that will be modified
3. Provides step-by-step execution order
4. Includes verification steps
5. Warns about risks and mitigation

Format: Plain text, no markdown, practical instructions.
Start with "## EXECUTION PROMPT" and include all context needed for implementation."""

        response = self.chat(
            messages=[{"role": "user", "content": prompt}],
            model="synthesis",
            temperature=0.5  # Lower temperature for more consistent output
        )

        if "error" in response:
            logger.error(f"Step 7 prompt generation failed: {response['error']}")
            return f"## EXECUTION PROMPT\n\nError generating prompt: {response['error']}"

        content = response.get("message", {}).get("content", "")
        logger.info(f"Step 7: Generated execution prompt ({len(content)} chars)")
        return content


# Utility function for quick access
def get_ollama_service() -> OllamaService:
    """Get or create singleton Ollama service instance."""
    if not hasattr(get_ollama_service, '_instance'):
        get_ollama_service._instance = OllamaService()
    return get_ollama_service._instance
