#!/usr/bin/env python3
"""
Level 3 Step 0 - Prompt Generator (Uses Local Ollama LLM)

Uses local LLM to intelligently analyze task and determine:
- Task type (from LLM analysis, not keywords)
- Complexity (1-10 scale from LLM)
- Suggested model (haiku/sonnet/opus based on complexity)

Invoked by: level3_execution.py (Level 3 Step 0)
Input: Task description from state
Output: JSON with task_type, complexity, suggested_model, reasoning
"""

import json
import sys
import os
from pathlib import Path
import urllib.request
import urllib.error

OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")


class OllamaTaskAnalyzer:
    """Use local Ollama LLM for intelligent task analysis."""

    def __init__(self):
        self.endpoint = OLLAMA_ENDPOINT
        self.model = OLLAMA_MODEL
        self.project_root = Path.cwd()

    def call_ollama(self, prompt: str) -> str:
        """Call local Ollama LLM with prompt."""
        try:
            num_ctx = 8192 if "14b" in self.model else 16384
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.3,  # Lower temp for consistency
                "options": {"num_ctx": num_ctx, "num_predict": 2048}
            }

            req = urllib.request.Request(
                self.endpoint,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode())
                return result.get("response", "").strip()
        except Exception as e:
            # Fallback if Ollama not available
            return f"Error calling Ollama: {str(e)}"

    def detect_project_type(self) -> str:
        """Detect project type by looking for files."""
        if (self.project_root / "pom.xml").exists() or (self.project_root / "build.gradle").exists():
            return "Java"
        elif (self.project_root / "package.json").exists():
            return "JavaScript"
        elif (self.project_root / "requirements.txt").exists() or (self.project_root / "pyproject.toml").exists():
            return "Python"
        return "Unknown"

    def analyze(self, task_description: str = None, context_data: dict = None) -> dict:
        """Analyze task using Ollama LLM with full context from Level 1."""
        if not task_description:
            if not sys.stdin.isatty():
                task_description = sys.stdin.read().strip()
            else:
                task_description = os.environ.get("TASK_DESCRIPTION", "General task")

        if not task_description or task_description == "General task":
            # Minimal fallback
            return {
                "task_type": "General Task",
                "complexity": 5,
                "suggested_model": "sonnet",
                "project_type": "Unknown",
                "reasoning": "No task description provided"
            }

        project_type = self.detect_project_type()

        # Build context section for the prompt
        context_section = ""
        if context_data:
            context_info = []

            # Add context loading info
            context_pct = context_data.get("loaded_context", {}).get("context_percentage", 0)
            if context_pct > 0:
                context_info.append(f"- Already loaded {context_pct}% of project context ({context_data.get('loaded_context', {}).get('files_loaded', 0)} files)")

            # Add project info
            if context_data.get("project", {}).get("is_java_project"):
                context_info.append("- This is a JAVA/Spring Boot project")

            # Add patterns if found
            patterns = context_data.get("patterns", {}).get("patterns_detected", [])
            if patterns:
                context_info.append(f"- Detected patterns: {', '.join(patterns)}")

            # Add session info
            if context_data.get("session_info", {}).get("previous_sessions", 0) > 0:
                prev_sessions = context_data["session_info"]["previous_sessions"]
                context_info.append(f"- Previous sessions: {prev_sessions}")

            if context_info:
                context_section = "Context Information:\n" + "\n".join(context_info) + "\n\n"

        # Prompt for LLM to analyze task WITH CONTEXT
        analysis_prompt = f"""Analyze this task and respond with ONLY a JSON object (no markdown, no extra text):

{context_section}Task: {task_description}
Project Type: {project_type}

Respond ONLY with JSON:
{{
  "task_type": "one of: API Creation, Bug Fix, Refactoring, New Feature, Testing, Documentation, Database, Security, Configuration, or Design",
  "complexity": integer from 1 to 10,
  "reasoning": "brief explanation"
}}

JSON only, no markdown:"""

        llm_response = self.call_ollama(analysis_prompt)

        # Parse LLM response
        try:
            # Try to extract JSON from response
            if "{" in llm_response:
                json_start = llm_response.index("{")
                json_end = llm_response.rindex("}") + 1
                analysis = json.loads(llm_response[json_start:json_end])
            else:
                analysis = json.loads(llm_response)
        except Exception:
            # Fallback if parsing fails
            analysis = {
                "task_type": "General Task",
                "complexity": 5,
                "reasoning": "LLM analysis parsing failed"
            }

        # Get complexity and suggest model
        complexity = analysis.get("complexity", 5)
        if isinstance(complexity, str):
            try:
                complexity = int(complexity)
            except ValueError:
                complexity = 5

        if complexity <= 3:
            suggested_model = "haiku"
        elif complexity <= 7:
            suggested_model = "sonnet"
        else:
            suggested_model = "opus"

        return {
            "task_type": analysis.get("task_type", "General Task"),
            "complexity": complexity,
            "suggested_model": suggested_model,
            "project_type": project_type,
            "reasoning": analysis.get("reasoning", "Analyzed by Ollama LLM")
        }


def main():
    """Main entry point."""
    analyzer = OllamaTaskAnalyzer()

    # Parse arguments
    task_description = None
    context_data = None

    for arg in sys.argv[1:]:
        if arg.startswith("--context="):
            # Extract context JSON
            context_json = arg.replace("--context=", "")
            try:
                context_data = json.loads(context_json)
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse context JSON: {e}", file=sys.stderr)
        else:
            # Regular argument is task description
            if task_description:
                task_description += " " + arg
            else:
                task_description = arg

    result = analyzer.analyze(task_description, context_data)

    # Output as JSON for LangGraph
    print(json.dumps(result))


if __name__ == "__main__":
    main()
