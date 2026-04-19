#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Task Auto-Analyzer (Phase 4)
Fully automatic task breakdown without user input

PHASE 4 AUTOMATION - FULL AUTO TASK BREAKDOWN
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Fix encoding for Windows console
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


class TaskAutoAnalyzer:
    """
    Automatically analyzes user messages and breaks them into tasks
    No user input needed - 100% automatic!
    """

    def __init__(self):
        self.memory_path = Path.home() / ".claude" / "memory"
        self.logs_path = self.memory_path / "logs"
        self.task_log = self.logs_path / "task-breakdown.log"

    def extract_entities(self, message):
        """Extract entities (services, features, etc.) from message"""
        entities = []

        # Common service patterns
        service_patterns = [r"(\w+)[-\s]service", r"service\s+for\s+(\w+)", r"(\w+)\s+microservice"]

        for pattern in service_patterns:
            matches = re.findall(pattern, message.lower())
            entities.extend(matches)

        # Feature patterns
        feature_patterns = [
            r"(\w+)\s+feature",
            r"feature\s+for\s+(\w+)",
            r"add\s+(\w+)",
            r"create\s+(\w+)",
            r"implement\s+(\w+)",
        ]

        for pattern in feature_patterns:
            matches = re.findall(pattern, message.lower())
            entities.extend(matches)

        return list(set(entities))  # Remove duplicates

    def estimate_file_count(self, message, entities):
        """Estimate number of files based on message analysis"""
        file_count = 0

        # Base count from entities
        file_count += len(entities) * 3  # Each entity typically needs ~3 files

        # Check for explicit mentions
        if "crud" in message.lower():
            file_count += 4  # Controller, Service, Repository, Entity

        if "api" in message.lower() or "endpoint" in message.lower():
            file_count += 2  # Controller + DTO

        if "database" in message.lower() or "entity" in message.lower():
            file_count += 2  # Entity + Repository

        if "config" in message.lower():
            file_count += 1

        if "test" in message.lower():
            file_count += 2

        # UI/Frontend files
        if "dashboard" in message.lower() or "admin panel" in message.lower():
            file_count += 3  # Template, CSS, JS

        if "ui" in message.lower() or "frontend" in message.lower():
            file_count += 2  # HTML, CSS

        if "component" in message.lower():
            file_count += 1  # Component file

        if "layout" in message.lower() or "template" in message.lower():
            file_count += 1  # Layout file

        return file_count

    def detect_phases(self, complexity_score, file_count):
        """
        Automatically detect if phases are needed
        Based on complexity and file count
        """
        needs_phases = False
        phase_list = []

        if complexity_score >= 15 or file_count >= 8:
            needs_phases = True
            phase_list = [
                {"name": "Foundation", "description": "Entities and repositories"},
                {"name": "Business Logic", "description": "Service layer implementation"},
                {"name": "API Layer", "description": "Controllers and DTOs"},
                {"name": "Configuration", "description": "Config files and properties"},
            ]
        elif complexity_score >= 10 or file_count >= 5:
            needs_phases = True
            phase_list = [
                {"name": "Core", "description": "Main implementation"},
                {"name": "Integration", "description": "Config and integration"},
            ]

        return needs_phases, phase_list

    def generate_tasks(self, message, entities, phases):
        """
        Automatically generate task list
        """
        tasks = []
        task_id = 1

        if phases:
            # Generate tasks per phase
            for phase in phases:
                phase_tasks = []

                if phase["name"] == "Foundation":
                    for entity in entities:
                        phase_tasks.append(
                            {
                                "id": task_id,
                                "title": f"Create {entity.capitalize()} entity",
                                "phase": phase["name"],
                                "type": "entity",
                            }
                        )
                        task_id += 1

                        phase_tasks.append(
                            {
                                "id": task_id,
                                "title": f"Create {entity.capitalize()} repository",
                                "phase": phase["name"],
                                "type": "repository",
                            }
                        )
                        task_id += 1

                elif phase["name"] == "Business Logic":
                    for entity in entities:
                        phase_tasks.append(
                            {
                                "id": task_id,
                                "title": f"Create {entity.capitalize()} service interface",
                                "phase": phase["name"],
                                "type": "service",
                            }
                        )
                        task_id += 1

                        phase_tasks.append(
                            {
                                "id": task_id,
                                "title": f"Implement {entity.capitalize()} service",
                                "phase": phase["name"],
                                "type": "service-impl",
                            }
                        )
                        task_id += 1

                elif phase["name"] == "API Layer" or phase["name"] == "Core":
                    for entity in entities:
                        phase_tasks.append(
                            {
                                "id": task_id,
                                "title": f"Create {entity.capitalize()} controller",
                                "phase": phase["name"],
                                "type": "controller",
                            }
                        )
                        task_id += 1

                        phase_tasks.append(
                            {
                                "id": task_id,
                                "title": f"Create {entity.capitalize()} DTOs",
                                "phase": phase["name"],
                                "type": "dto",
                            }
                        )
                        task_id += 1

                elif phase["name"] == "Configuration":
                    phase_tasks.append(
                        {
                            "id": task_id,
                            "title": "Update application properties",
                            "phase": phase["name"],
                            "type": "config",
                        }
                    )
                    task_id += 1

                tasks.extend(phase_tasks)

        else:
            # Generate flat task list
            for entity in entities:
                tasks.append({"id": task_id, "title": f"Implement {entity.capitalize()}", "type": "implementation"})
                task_id += 1

        return tasks

    def create_dependencies(self, tasks):
        """
        Automatically create task dependencies
        Entity -> Repository -> Service -> Controller
        """
        dependencies = {}

        # Group tasks by type
        task_map = {}
        for task in tasks:
            task_type = task.get("type", "")
            entity = task.get("title", "").split()[1] if len(task.get("title", "").split()) > 1 else ""

            if entity not in task_map:
                task_map[entity] = {}

            task_map[entity][task_type] = task["id"]

        # Create dependencies
        for entity, types in task_map.items():
            # Repository depends on Entity
            if "entity" in types and "repository" in types:
                dependencies[types["repository"]] = [types["entity"]]

            # Service depends on Repository
            if "repository" in types and "service" in types:
                dependencies[types["service"]] = [types["repository"]]

            # Service impl depends on Service
            if "service" in types and "service-impl" in types:
                dependencies[types["service-impl"]] = [types["service"]]

            # Controller depends on Service impl
            if "service-impl" in types and "controller" in types:
                dependencies[types["controller"]] = [types["service-impl"]]

            # DTO can be parallel with controller
            # No dependencies

        return dependencies

    def auto_analyze(self, user_message):
        """
        Main entry point - fully automatic analysis
        Returns complete task breakdown
        """
        # Extract entities
        entities = self.extract_entities(user_message)

        # If no entities found, create generic
        if not entities:
            entities = ["feature"]

        # Calculate complexity
        complexity_score = self.estimate_complexity(user_message, entities)

        # Estimate file count
        file_count = self.estimate_file_count(user_message, entities)

        # Detect phases
        needs_phases, phases = self.detect_phases(complexity_score, file_count)

        # Generate tasks
        tasks = self.generate_tasks(user_message, entities, phases)

        # Create dependencies
        dependencies = self.create_dependencies(tasks)

        result = {
            "user_message": user_message,
            "entities": entities,
            "complexity_score": complexity_score,
            "estimated_files": file_count,
            "needs_phases": needs_phases,
            "phases": phases,
            "tasks": tasks,
            "dependencies": dependencies,
            "total_tasks": len(tasks),
            "timestamp": datetime.now().isoformat(),
        }

        # Log analysis
        self.log_analysis(result)

        return result

    def estimate_complexity(self, message, entities):
        """Estimate complexity score"""
        score = 0

        # Base from entities
        score += len(entities) * 5

        # Keywords
        if "crud" in message.lower():
            score += 10

        if "security" in message.lower() or "auth" in message.lower():
            score += 8

        if "database" in message.lower():
            score += 5

        if "api" in message.lower():
            score += 3

        if "test" in message.lower():
            score += 5

        if "microservice" in message.lower():
            score += 7

        return min(score, 30)

    def log_analysis(self, result):
        """Log analysis result"""
        self.logs_path.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": result["timestamp"],
            "complexity": result["complexity_score"],
            "entities": len(result["entities"]),
            "tasks": result["total_tasks"],
            "phases": len(result["phases"]),
        }

        with open(self.task_log, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    def print_result(self, result):
        """Print formatted result"""
        print(f"\n{'='*70}")
        print("[CLIPBOARD] Task Auto-Analyzer (Phase 4 - Full Auto)")
        print(f"{'='*70}\n")

        print("[CHART] Analysis:")
        print(f"   Entities: {', '.join(result['entities'])}")
        print(f"   Complexity: {result['complexity_score']}/30")
        print(f"   Estimated Files: {result['estimated_files']}")
        print(f"   Total Tasks: {result['total_tasks']}")

        if result["needs_phases"]:
            print(f"\n[doc] Phases: {len(result['phases'])}")
            for i, phase in enumerate(result["phases"], 1):
                print(f"   {i}. {phase['name']}: {phase['description']}")

        print("\n[OK] Tasks Generated:")
        current_phase = None
        for task in result["tasks"]:
            if task.get("phase") != current_phase:
                current_phase = task.get("phase")
                if current_phase:
                    print(f"\n   Phase: {current_phase}")

            deps = result["dependencies"].get(task["id"], [])
            deps_str = f" (depends on: {deps})" if deps else ""
            print(f"   [{task['id']}] {task['title']}{deps_str}")

        print(f"\n{'='*70}\n")


def main():
    """CLI usage - outputs JSON for LangGraph"""
    # Import shared LLM call helper (claude_cli / anthropic)
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
        from langgraph_engine.llm_call import llm_call as _llm_call
    except ImportError:
        _llm_call = None

    if len(sys.argv) < 2:
        output = {
            "task_count": 1,
            "tasks": [
                {
                    "id": 1,
                    "name": "Execute task",
                    "description": "Execute the requested task",
                    "priority": "medium",
                    "depends_on": [],
                }
            ],
            "status": "minimal",
        }
        print(json.dumps(output))
        sys.exit(0)

    user_message = " ".join(sys.argv[1:])

    # Use LLM to break down tasks
    prompt = f"""Break down this task into sub-tasks. Respond ONLY with JSON (no markdown):

Task: {user_message}

JSON format (no markdown):
{{
  "task_count": number,
  "tasks": [
    {{"id": 1, "name": "task name", "description": "what to do", "priority": "high/medium/low"}},
    ...
  ]
}}

JSON only:"""

    try:
        # Use shared LLM call (claude_cli / anthropic fallback chain)
        llm_response = ""
        if _llm_call:
            llm_response = _llm_call(prompt, model="fast", temperature=0.3) or ""

        # Parse JSON from response
        if "{" in llm_response:
            json_start = llm_response.index("{")
            json_end = llm_response.rindex("}") + 1
            output = json.loads(llm_response[json_start:json_end])
        else:
            output = json.loads(llm_response)

        # Ensure required fields
        output["task_count"] = len(output.get("tasks", []))
        output["status"] = "OK"
        print(json.dumps(output))

    except Exception:
        # Fallback to simple task breakdown
        analyzer = TaskAutoAnalyzer()
        result = analyzer.auto_analyze(user_message)
        output = {
            "task_count": result.get("total_tasks", 1),
            "tasks": [
                {
                    "id": task.get("id"),
                    "name": task.get("title", "Unnamed task"),
                    "description": task.get("description", f"Phase: {task.get('phase', 'General')}"),
                    "priority": _estimate_priority(task, result),
                    "depends_on": result.get("dependencies", {}).get(task.get("id"), []),
                }
                for task in result.get("tasks", [])
            ],
            "status": "OK",
        }
        print(json.dumps(output))

    sys.exit(0)


def _estimate_priority(task, result):
    """Estimate task priority based on position and dependencies"""
    task_id = task.get("id", 1)
    total_tasks = result.get("total_tasks", 1)
    task.get("type", "")

    # Early tasks are higher priority
    position_ratio = task_id / total_tasks if total_tasks > 0 else 0.5

    if position_ratio < 0.3:
        return "high"
    elif position_ratio < 0.7:
        return "medium"
    else:
        return "low"


if __name__ == "__main__":
    main()
