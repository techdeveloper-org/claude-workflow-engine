#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI-Based Task Type Detector using Local Ollama

Instead of fragile keyword matching, use local LLM via Ollama to intelligently
classify user prompts into task types.

REPLACES: Keyword-based detect_task_type() in prompt-generation-policy.py

Local Models (via Ollama):
- llama2, llama2-uncensored
- mistral, neural-chat
- dolphin-mixtral
- Any model available via: ollama pull <model>

Usage:
  python ai-task-type-detector.py --detect "user prompt here"
  python ai-task-type-detector.py --list-models

Requirements:
  1. Ollama installed: https://ollama.ai
  2. Model pulled: ollama pull mistral (or your preferred model)
  3. Ollama running on localhost:11434 (default port)
  4. Environment: OLLAMA_MODEL (optional, defaults to mistral)
"""

import sys
import json
import os
from pathlib import Path
from typing import Dict, Optional
import urllib.request
import urllib.error

# Task types we support
SUPPORTED_TASK_TYPES = [
    "Design",              # UI/UX, interface, layout, styling
    "API Creation",        # REST endpoints, microservices, CRUD
    "Authentication",      # Login, JWT, OAuth, security
    "Authorization",       # Roles, permissions, access control
    "Database",            # Tables, schemas, entities, queries
    "Configuration",       # Setup, settings, environment
    "Bug Fix",             # Errors, issues, patches
    "Refactoring",         # Code quality, improvements, optimization
    "Security",            # Encryption, vulnerabilities, hardening
    "Testing",             # Unit tests, integration tests, QA
    "Documentation",       # README, comments, guides
    "General Task"         # Default fallback
]


class AiTaskTypeDetector:
    """
    Intelligent task type detection using local Ollama.

    Uses locally-running LLM (no external API, no authentication needed).
    Analyzes user's prompt and classifies task type with confidence score.
    """

    def __init__(self, model: Optional[str] = None, ollama_host: str = "localhost:11434"):
        """Initialize with Ollama configuration.

        Args:
            model: Model name (e.g., 'mistral'). Defaults to env var OLLAMA_MODEL or 'mistral'
            ollama_host: Ollama server address. Defaults to localhost:11434
        """
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
        self.ollama_host = ollama_host
        self.api_endpoint = f"http://{ollama_host}/api/generate"

        # Verify Ollama is running
        if not self._check_ollama_available():
            raise ValueError(
                f"Ollama not available at {self.ollama_host}\n"
                "Please ensure:\n"
                "  1. Ollama is installed: https://ollama.ai\n"
                "  2. Ollama is running: ollama serve\n"
                "  3. A model is available: ollama pull mistral\n"
                f"  4. Ollama is listening on {self.ollama_host}"
            )

        # System prompt for classification
        self.system_prompt = """You are a task classifier. Analyze the user's request and determine the task type.

Return a JSON object with exactly these fields:
{
  "task_type": "one of: Design, API Creation, Authentication, Authorization, Database, Configuration, Bug Fix, Refactoring, Security, Testing, Documentation, General Task",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}

Be precise. Examples:
- "redesign the login form" → Design (high confidence)
- "create user endpoint" → API Creation
- "fix database timeout error" → Bug Fix
- "add encryption to passwords" → Security
- "what's the best practice?" → General Task

Return ONLY the JSON object, no other text."""

    def detect(self, user_message: str) -> Dict:
        """
        Detect task type using local Ollama LLM.

        Args:
            user_message: User's prompt/request

        Returns:
            Dict with keys: task_type, confidence, reasoning

        Raises:
            Exception: If Ollama is unavailable or request fails
        """
        response = self._call_ollama(user_message)
        result = self._parse_response(response)
        return result

    def _check_ollama_available(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            request = urllib.request.Request(
                f"http://{self.ollama_host}/api/tags",
                method='GET'
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status == 200
        except Exception:
            return False

    def _call_ollama(self, user_message: str) -> str:
        """Call local Ollama API and return response."""

        # Request payload for Ollama
        payload = {
            "model": self.model,
            "prompt": f"{self.system_prompt}\n\nUser request: {user_message}",
            "stream": False,  # Wait for complete response
            "temperature": 0.2  # Low temp for consistent classification
        }

        request = urllib.request.Request(
            self.api_endpoint,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json"},
            method='POST'
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode('utf-8')
                return body
        except urllib.error.HTTPError as e:
            raise Exception(f"Ollama HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise Exception(f"Ollama connection failed: {e.reason}")
        except Exception as e:
            raise Exception(f"Ollama request failed: {str(e)}")

    def _parse_response(self, response_text: str) -> Dict:
        """Parse Ollama API response."""
        try:
            response_json = json.loads(response_text)

            # Ollama returns: {"response": "...", "model": "...", ...}
            response_text = response_json.get("response", "").strip()

            if not response_text:
                raise ValueError("Empty response from Ollama")

            # Try to extract JSON from response
            # Sometimes LLM wraps it in markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            response_text = response_text.strip()

            # Parse JSON
            classification = json.loads(response_text)

            # Validate task type
            task_type = classification.get("task_type", "General Task")
            if task_type not in SUPPORTED_TASK_TYPES:
                task_type = "General Task"

            return {
                "task_type": task_type,
                "confidence": float(classification.get("confidence", 0.5)),
                "reasoning": classification.get("reasoning", "")
            }
        except (json.JSONDecodeError, KeyError, ValueError, IndexError, TypeError) as e:
            raise ValueError(f"Failed to parse Ollama response: {str(e)}")

    @staticmethod
    def is_available() -> bool:
        """Check if Ollama is available."""
        try:
            detector = AiTaskTypeDetector()
            return True
        except Exception:
            return False

    @staticmethod
    def list_models(ollama_host: str = "localhost:11434") -> list:
        """List available models in Ollama."""
        try:
            request = urllib.request.Request(
                f"http://{ollama_host}/api/tags",
                method='GET'
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                return [model.get("name", "unknown") for model in data.get("models", [])]
        except Exception:
            return []


def main():
    """CLI interface for testing."""
    import argparse

    parser = argparse.ArgumentParser(description="AI Task Type Detector (Local Ollama)")
    parser.add_argument("--detect", type=str, help="Detect task type for prompt")
    parser.add_argument("--model", type=str, help="Ollama model to use (default: mistral)")
    parser.add_argument("--ollama-host", type=str, default="localhost:11434", help="Ollama server address")
    parser.add_argument("--test", action="store_true", help="Run test cases")
    parser.add_argument("--list-models", action="store_true", help="List available Ollama models")

    args = parser.parse_args()

    # List models
    if args.list_models:
        models = AiTaskTypeDetector.list_models(args.ollama_host)
        if models:
            print("Available Ollama models:")
            for model in models:
                print(f"  - {model}")
        else:
            print("No models found. Pull a model: ollama pull mistral")
        return

    # Initialize detector
    try:
        detector = AiTaskTypeDetector(model=args.model, ollama_host=args.ollama_host)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Test cases
    if args.test:
        test_prompts = [
            "redesign the login page",
            "create a REST API for users",
            "fix the database timeout issue",
            "add JWT authentication",
            "improve code performance",
            "write unit tests for auth service",
            "what's the best way to learn Python?"
        ]

        print("=" * 80)
        print("AI TASK TYPE DETECTOR - TEST CASES (Local Ollama)")
        print(f"Model: {detector.model}")
        print("=" * 80)

        for prompt in test_prompts:
            try:
                result = detector.detect(prompt)
                print(f"\nPrompt: {prompt}")
                print(f"  Task Type: {result['task_type']}")
                print(f"  Confidence: {result['confidence']:.1%}")
                print(f"  Reasoning: {result['reasoning']}")
            except Exception as e:
                print(f"\nPrompt: {prompt}")
                print(f"  ERROR: {str(e)[:100]}")

    elif args.detect:
        try:
            result = detector.detect(args.detect)
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
