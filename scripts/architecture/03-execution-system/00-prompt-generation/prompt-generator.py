#!/usr/bin/env python3
"""
Level 3 Step 0 - Prompt Generator (Task Analyzer)

Analyzes user task to determine:
- Task type (REST API, refactoring, bug fix, new feature, testing, documentation, etc.)
- Project type (Java, Python, JavaScript, etc.)
- Complexity (1-10 scale)
- Suggested model (haiku/sonnet/opus)

Invoked by: level3_execution.py (Level 3 Step 0)
Input: Task description from state
Output: JSON with task_type, complexity, suggested_model, project_type, reasoning
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, Tuple


class TaskAnalyzer:
    """Analyze task characteristics and suggest execution parameters."""

    # Task type keywords and patterns
    TASK_PATTERNS = {
        "REST API": [
            r"api",
            r"endpoint",
            r"rest",
            r"http",
            r"crud",
            r"get|post|put|delete|patch",
            r"request|response",
        ],
        "refactoring": [
            r"refactor",
            r"clean up",
            r"reorganize",
            r"simplify",
            r"optimize",
            r"performance",
        ],
        "bug fix": [
            r"bug",
            r"fix",
            r"issue",
            r"error",
            r"failing",
            r"broken",
            r"incorrect",
        ],
        "new feature": [
            r"add",
            r"implement",
            r"create",
            r"build",
            r"feature",
            r"new",
        ],
        "testing": [
            r"test",
            r"unit test",
            r"integration test",
            r"test case",
            r"coverage",
        ],
        "documentation": [
            r"document",
            r"readme",
            r"comment",
            r"docstring",
            r"javadoc",
        ],
        "database": [
            r"database",
            r"sql",
            r"query",
            r"schema",
            r"migration",
            r"table",
        ],
        "security": [
            r"security",
            r"authentication",
            r"authorization",
            r"encrypt",
            r"jwt",
            r"oauth",
        ],
        "configuration": [
            r"config",
            r"setup",
            r"install",
            r"configure",
            r"environment",
        ],
    }

    # Project type detection
    PROJECT_FILES = {
        "Java": ["pom.xml", "build.gradle", "build.gradle.kts", "src/main/java"],
        "Python": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile"],
        "JavaScript": ["package.json", "tsconfig.json", "webpack.config.js"],
        "Go": ["go.mod", "go.sum"],
        "Rust": ["Cargo.toml"],
        ".NET": ["*.csproj", "*.sln"],
    }

    # Complexity indicators
    COMPLEXITY_KEYWORDS = {
        "simple": [
            "typo",
            "simple",
            "small",
            "one-line",
            "minor",
            "quick",
        ],
        "medium": [
            "update",
            "modify",
            "change",
            "add",
            "implement",
            "refactor",
        ],
        "complex": [
            "redesign",
            "architecture",
            "migrate",
            "major",
            "complete rewrite",
            "multi-step",
            "integration",
            "distributed",
        ],
    }

    def __init__(self):
        self.project_root = Path.cwd()

    def detect_task_type(self, task_description: str) -> str:
        """Detect task type from description."""
        task_lower = task_description.lower()

        # Score each task type based on keyword matches
        scores = {}
        for task_type, patterns in self.TASK_PATTERNS.items():
            score = sum(
                1
                for pattern in patterns
                if self._match_pattern(pattern, task_lower)
            )
            if score > 0:
                scores[task_type] = score

        if scores:
            return max(scores, key=scores.get)
        return "General Task"

    def detect_project_type(self) -> str:
        """Detect project type by looking for characteristic files."""
        for proj_type, files in self.PROJECT_FILES.items():
            for file_pattern in files:
                if "*" in file_pattern:
                    # Glob pattern
                    if list(self.project_root.glob(file_pattern)):
                        return proj_type
                else:
                    # Exact file or directory
                    if (self.project_root / file_pattern).exists():
                        return proj_type

        return "Unknown"

    def calculate_complexity(self, task_description: str, project_type: str) -> int:
        """Calculate task complexity (1-10)."""
        task_lower = task_description.lower()
        base_complexity = 5

        # Check simple indicators (-2 to -1)
        simple_hits = sum(
            1
            for keyword in self.COMPLEXITY_KEYWORDS["simple"]
            if keyword in task_lower
        )
        if simple_hits > 0:
            base_complexity = max(1, base_complexity - 2)

        # Check complex indicators (+2 to +3)
        complex_hits = sum(
            1
            for keyword in self.COMPLEXITY_KEYWORDS["complex"]
            if keyword in task_lower
        )
        if complex_hits > 0:
            base_complexity = min(10, base_complexity + 3)

        # Adjust by project type
        if project_type == "Java":
            # Java projects tend to be more complex due to framework integration
            base_complexity = min(10, base_complexity + 1)
        elif project_type == "Python":
            # Python is generally simpler
            base_complexity = max(1, base_complexity - 1)

        # Check task length as indicator
        word_count = len(task_description.split())
        if word_count > 100:
            base_complexity = min(10, base_complexity + 1)
        elif word_count < 10:
            base_complexity = max(1, base_complexity - 1)

        return max(1, min(10, base_complexity))

    def suggest_model(self, complexity: int) -> str:
        """Suggest Claude model based on complexity."""
        if complexity <= 3:
            return "haiku"
        elif complexity <= 7:
            return "sonnet"
        else:
            return "opus"

    def analyze(self, task_description: str = None) -> Dict:
        """Analyze task and return recommendations."""
        if not task_description:
            # Try to read from stdin or environment
            if not sys.stdin.isatty():
                task_description = sys.stdin.read().strip()
            else:
                task_description = os.environ.get("TASK_DESCRIPTION", "")

        if not task_description:
            # Default fallback
            task_description = "General task"

        task_type = self.detect_task_type(task_description)
        project_type = self.detect_project_type()
        complexity = self.calculate_complexity(task_description, project_type)
        suggested_model = self.suggest_model(complexity)

        return {
            "task_type": task_type,
            "project_type": project_type,
            "complexity": complexity,
            "suggested_model": suggested_model,
            "reasoning": f"Task type: {task_type} | Project: {project_type} | Complexity: {complexity}/10 → {suggested_model}",
        }

    @staticmethod
    def _match_pattern(pattern: str, text: str) -> bool:
        """Simple pattern matching (case-insensitive substring or regex)."""
        import re

        try:
            return bool(re.search(pattern, text, re.IGNORECASE))
        except Exception:
            return pattern.lower() in text


def main():
    """Main entry point."""
    analyzer = TaskAnalyzer()

    # Get task description from command line or stdin
    if len(sys.argv) > 1:
        task_description = " ".join(sys.argv[1:])
    else:
        task_description = None

    result = analyzer.analyze(task_description)

    # Output as JSON for LangGraph
    print(json.dumps(result))


if __name__ == "__main__":
    main()
