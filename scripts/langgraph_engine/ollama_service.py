"""
Ollama Service Layer - Local LLM integration for Level 3 execution.

Provides interface to local Ollama models for:
- Step 1: Plan mode decision (complexity analysis)
- Step 5: Skill and agent selection
- Step 7: Final prompt generation

Configuration:
- Primary endpoint: http://127.0.0.1:11434 (default Ollama)
- Models: qwen2.5:7b (fast), claude-opus (complex reasoning)
- Fallback: Not implemented yet (Ollama must be available)
"""

import json
import subprocess
import os
from typing import Dict, Any, Optional, List
from loguru import logger
from pathlib import Path


class OllamaService:
    """Manages communication with local Ollama LLM."""

    def __init__(self, endpoint: str = "http://127.0.0.1:11434"):
        self.endpoint = endpoint
        self.available_models = self._check_available_models()

        # Model routing
        self.models = {
            "fast_classification": "qwen2.5:7b",      # Fast, lightweight (7B params)
            "complex_reasoning": "qwen2.5:14b",       # Medium depth analysis
            "synthesis": "qwen2.5:14b"                # For prompt generation
        }

        logger.info(f"Ollama service initialized at {endpoint}")
        logger.info(f"Available models: {self.available_models}")

    def _check_available_models(self) -> List[str]:
        """Check which models are installed locally."""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logger.warning("Cannot list ollama models, assuming empty")
                return []

            # Parse ollama list output
            models = []
            for line in result.stdout.split('\n')[1:]:  # Skip header
                if line.strip():
                    model_name = line.split()[0]
                    models.append(model_name)
            return models
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
            "stream": False
        }

        if format:
            request_body["format"] = format

        if system_prompt:
            # Inject system prompt at beginning
            messages = [{"role": "system", "content": system_prompt}] + messages
            request_body["messages"] = messages

        try:
            logger.debug(f"Calling Ollama: {model_name} with {len(messages)} messages")

            result = subprocess.run(
                ["ollama", "chat"],
                input=json.dumps(request_body),
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout for complex reasoning
            )

            if result.returncode != 0:
                logger.error(f"Ollama error: {result.stderr}")
                return {"error": result.stderr}

            response = json.loads(result.stdout)
            logger.debug(f"Ollama response received ({len(response.get('message', {}).get('content', ''))} chars)")

            return response

        except subprocess.TimeoutExpired:
            logger.error(f"Ollama timeout for {model_name}")
            return {"error": "Ollama timeout (model too slow)"}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from Ollama: {e}")
            return {"error": f"Invalid JSON response: {str(e)}"}
        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            return {"error": str(e)}

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
        Select required skills and agents for task execution.

        Uses: qwen2.5:14b (medium depth analysis)

        Args:
            blueprint: ExecutionBlueprint with phases and tasks
            available_skills: List of available skill names
            available_agents: List of available agent names

        Returns:
            {
                "skill_mappings": [
                    {
                        "task_id": "Task-1",
                        "task_name": "...",
                        "required_skills": ["skill1", "skill2"],
                        "required_agents": ["agent1"],
                        "skill_confidence": {"skill1": 0.95}
                    }
                ],
                "final_skills_selected": ["skill1", "skill2"],
                "final_agents_selected": ["agent1"]
            }
        """
        # Format phases for LLM
        phases_text = ""
        for phase in blueprint.get("phases", []):
            phases_text += f"- Phase {phase.get('phase_number')}: {phase.get('title')}\n"
            for task in phase.get("tasks", []):
                phases_text += f"  * {task}\n"

        prompt = f"""Analyze the execution blueprint and select required skills and agents.

EXECUTION PLAN:
{blueprint.get('plan', 'No plan provided')}

PHASES:
{phases_text}

RISK LEVEL: {blueprint.get('risks', {}).get('risk_level', 'medium')}

AVAILABLE SKILLS (select relevant):
{json.dumps(available_skills, indent=2)}

AVAILABLE AGENTS (select 1-3):
{json.dumps(available_agents, indent=2)}

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
