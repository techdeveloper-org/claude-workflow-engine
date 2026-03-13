"""
DeepSeek Reasoning Service - Enhanced MCP and Skill Selection via Local DeepSeek Models.

Provides intelligent reasoning about:
- Which MCPs should be used for a given task
- Best skill/agent combination for task execution
- Task complexity and planning needs

Uses DeepSeek-R1 models locally via Ollama or NPU inference.
Falls back to Claude API if local inference unavailable.

Reasoning Flow:
1. Analyze task context (user message, complexity, patterns)
2. Consider available MCPs and their capabilities
3. Generate structured reasoning about optimal MCPs
4. Evaluate skill/agent fit
5. Return reasoning trace for Claude to use in final selection
"""

import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

try:
    from loguru import logger
except ImportError:
    class logger:
        @staticmethod
        def info(msg): print(f"[INFO] {msg}")
        @staticmethod
        def warning(msg): print(f"[WARNING] {msg}")
        @staticmethod
        def error(msg): print(f"[ERROR] {msg}")


@dataclass
class MCPReasoningResult:
    """Result of MCP reasoning analysis."""
    required_mcps: List[str]
    recommended_mcps: List[str]
    optional_mcps: List[str]
    reasoning: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "required_mcps": self.required_mcps,
            "recommended_mcps": self.recommended_mcps,
            "optional_mcps": self.optional_mcps,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
        }


class DeepSeekReasoning:
    """Provides structured reasoning about MCP and skill selection."""

    def __init__(self):
        """Initialize DeepSeek reasoning service."""
        self.inference_router = None
        self.ollama_service = None
        self.claude_client = None

        self._init_services()

    def _init_services(self) -> None:
        """Initialize inference services."""
        # Try to load inference router for local models
        try:
            from .inference_router import InferenceRouter
            self.inference_router = InferenceRouter()
            logger.info("✓ Inference router initialized (DeepSeek local reasoning available)")
        except Exception as e:
            logger.warning(f"Inference router unavailable: {e}")
            self.inference_router = None

        # Try to load Ollama service
        try:
            from .ollama_service import OllamaService
            self.ollama_service = OllamaService()
            logger.info("✓ Ollama service initialized")
        except Exception as e:
            logger.warning(f"Ollama service unavailable: {e}")
            self.ollama_service = None

        # Try to load Claude API fallback
        try:
            from anthropic import Anthropic
            self.claude_client = Anthropic()
            logger.info("✓ Claude API fallback available")
        except Exception as e:
            logger.warning(f"Claude API unavailable: {e}")
            self.claude_client = None

    def analyze_mcp_requirements(
        self,
        user_message: str,
        task_type: str,
        complexity: int,
        available_mcps: List[Dict[str, Any]],
        validated_tasks: Optional[List[Dict]] = None,
        patterns: Optional[List[str]] = None,
    ) -> MCPReasoningResult:
        """Analyze task and determine which MCPs are needed.

        Args:
            user_message: User's task description
            task_type: Type of task (e.g., 'implementation', 'planning', 'analysis')
            complexity: Complexity score (1-10)
            available_mcps: List of available MCP metadata dicts
            validated_tasks: Breakdown of tasks (optional)
            patterns: Detected patterns in codebase (optional)

        Returns:
            MCPReasoningResult with recommended MCPs and reasoning
        """
        # Prepare reasoning prompt
        prompt = self._build_mcp_reasoning_prompt(
            user_message=user_message,
            task_type=task_type,
            complexity=complexity,
            available_mcps=available_mcps,
            validated_tasks=validated_tasks or [],
            patterns=patterns or [],
        )

        # Call reasoning service
        try:
            # Try local reasoning first (DeepSeek via Ollama/NPU)
            if self.ollama_service:
                reasoning_text = self._call_deepseek_reasoning(prompt)
            elif self.inference_router:
                reasoning_text = self._call_router_reasoning(prompt)
            else:
                # Fallback to Claude API
                reasoning_text = self._call_claude_reasoning(prompt)

            # Parse reasoning result
            result = self._parse_mcp_reasoning(reasoning_text)
            return result

        except Exception as e:
            logger.error(f"MCP reasoning failed: {e}")
            # Fallback: return reasonable defaults
            return MCPReasoningResult(
                required_mcps=[],
                recommended_mcps=["filesystem"] if any(m.get("short_name") == "filesystem" for m in available_mcps) else [],
                optional_mcps=[],
                reasoning=f"Reasoning unavailable ({str(e)}). Using defaults.",
                confidence=0.3,
            )

    def _build_mcp_reasoning_prompt(
        self,
        user_message: str,
        task_type: str,
        complexity: int,
        available_mcps: List[Dict],
        validated_tasks: List[Dict],
        patterns: List[str],
    ) -> str:
        """Build prompt for MCP reasoning."""
        mcp_descriptions = "\n".join([
            f"- {m.get('name', m.get('short_name'))}: {m.get('description', 'N/A')}"
            for m in available_mcps
        ])

        task_desc = "\n".join([
            f"- {t.get('description', t.get('name', 'Task'))}"
            for t in validated_tasks[:5]  # Limit to first 5 tasks
        ])

        return f"""Analyze this task and determine which MCP (Model Context Protocol) servers are needed.

USER TASK:
{user_message}

TASK ANALYSIS:
- Type: {task_type}
- Complexity: {complexity}/10
- Detected Patterns: {', '.join(patterns) if patterns else 'None'}

VALIDATED TASKS TO EXECUTE:
{task_desc if task_desc else 'None provided'}

AVAILABLE MCP SERVERS:
{mcp_descriptions}

YOUR ANALYSIS:
1. What are the file operations needed? (Read large files? Search large codebases? Explore directories?)
2. Would the Filesystem MCP be useful? Why or why not?
3. Are there other MCPs that would help?

RESPOND WITH STRUCTURED JSON:
{{
    "mcp_analysis": "Brief analysis of MCP needs",
    "filesystem_mcp_needed": true/false,
    "filesystem_reason": "Why filesystem MCP is needed or not",
    "other_mcps": ["mcp_name1", "mcp_name2"],
    "confidence": 0.0-1.0,
    "summary": "One sentence summary"
}}

RESPOND ONLY WITH THE JSON, NO MARKDOWN OR EXPLANATION."""

    def _call_deepseek_reasoning(self, prompt: str) -> str:
        """Call DeepSeek reasoning via Ollama."""
        try:
            response = self.ollama_service.call(
                prompt=prompt,
                model="qwen2.5:7b",  # Fallback model
                temperature=0.7,
                max_tokens=1000,
            )
            return response.get("response", "")
        except Exception as e:
            logger.error(f"Ollama reasoning failed: {e}")
            raise

    def _call_router_reasoning(self, prompt: str) -> str:
        """Call reasoning via inference router (smart GPU/NPU selection)."""
        try:
            backend = self.inference_router.choose_backend("reasoning", complexity=7)
            logger.info(f"Using {backend} for MCP reasoning")

            if backend == "gpu" and self.ollama_service:
                return self._call_deepseek_reasoning(prompt)
            elif backend == "npu":
                # Call NPU service
                # This would be implemented by npu_service
                # For now, fallback to Claude
                return self._call_claude_reasoning(prompt)
            else:
                return self._call_claude_reasoning(prompt)

        except Exception as e:
            logger.error(f"Router reasoning failed: {e}")
            raise

    def _call_claude_reasoning(self, prompt: str) -> str:
        """Call Claude API for reasoning (fallback)."""
        try:
            if not self.claude_client:
                raise RuntimeError("Claude client not initialized")

            response = self.claude_client.messages.create(
                model="claude-opus-4-1",
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )

            return response.content[0].text

        except Exception as e:
            logger.error(f"Claude reasoning failed: {e}")
            raise

    def _parse_mcp_reasoning(self, reasoning_text: str) -> MCPReasoningResult:
        """Parse reasoning response into structured result."""
        try:
            # Try to extract JSON from response
            import json
            import re

            # Find JSON block
            json_match = re.search(r'\{.*\}', reasoning_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(reasoning_text)

            return MCPReasoningResult(
                required_mcps=[],
                recommended_mcps=(
                    ["filesystem"]
                    if data.get("filesystem_mcp_needed", False)
                    else []
                ) + data.get("other_mcps", []),
                optional_mcps=[],
                reasoning=data.get("mcp_analysis", ""),
                confidence=data.get("confidence", 0.5),
            )

        except Exception as e:
            logger.warning(f"Failed to parse reasoning JSON: {e}")
            # Return partial result from text
            return MCPReasoningResult(
                required_mcps=[],
                recommended_mcps=[],
                optional_mcps=[],
                reasoning=reasoning_text[:500],
                confidence=0.3,
            )

    def evaluate_skill_agent_fit(
        self,
        user_message: str,
        candidate_skills: List[str],
        candidate_agents: List[str],
    ) -> Dict[str, Any]:
        """Evaluate which skill/agent combination best fits the task.

        Args:
            user_message: Task description
            candidate_skills: List of available skill names
            candidate_agents: List of available agent names

        Returns:
            Dict with recommendations and reasoning
        """
        prompt = f"""Given this task, which skill and/or agent is best suited?

TASK: {user_message}

AVAILABLE SKILLS:
{', '.join(candidate_skills[:10])}

AVAILABLE AGENTS:
{', '.join(candidate_agents[:10])}

Respond with JSON:
{{
    "recommended_skill": "skill_name_or_null",
    "recommended_agent": "agent_name_or_null",
    "reasoning": "Why this combination",
    "confidence": 0.0-1.0
}}"""

        try:
            if self.ollama_service:
                response = self.ollama_service.call(
                    prompt=prompt,
                    model="qwen2.5:7b",
                    temperature=0.7,
                    max_tokens=500,
                )
                response_text = response.get("response", "")
            else:
                response_text = self._call_claude_reasoning(prompt)

            import json
            import re

            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return json.loads(response_text)

        except Exception as e:
            logger.error(f"Skill/agent evaluation failed: {e}")
            return {
                "recommended_skill": candidate_skills[0] if candidate_skills else None,
                "recommended_agent": None,
                "reasoning": f"Evaluation unavailable: {e}",
                "confidence": 0.2,
            }


# Singleton instance
_deepseek_instance: Optional[DeepSeekReasoning] = None


def get_deepseek_reasoning() -> DeepSeekReasoning:
    """Get or create singleton DeepSeekReasoning instance."""
    global _deepseek_instance
    if _deepseek_instance is None:
        _deepseek_instance = DeepSeekReasoning()
    return _deepseek_instance


def reset_deepseek_reasoning() -> None:
    """Reset singleton (for testing)."""
    global _deepseek_instance
    _deepseek_instance = None
