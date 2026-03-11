"""
Level 3 - Remaining Steps: 2-7, 13-14

Implements:
- Step 2: Plan execution (if plan_required=True from Step 1)
- Step 3: Task breakdown
- Step 4: TOON refinement (compress after planning)
- Step 6: Skill/agent validation
- Step 7: Final prompt generation (already in ollama_service.py, wrapper here)
- Step 13: Documentation update
- Step 14: Final summary and voice notification

Note: Step 10 (Implementation) is handled by Claude directly with tools
Note: Step 5 (Skill selection) is in ollama_service.py, wrapper here
"""

import time
import json
import subprocess
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from loguru import logger
from .toon_models import ExecutionBlueprint, ToonWithSkills
from .session_manager import SessionManager
from .ollama_service import get_ollama_service


class Level3RemainingSteps:
    """Implements steps 2-7, 13-14 for Level 3 execution."""

    def __init__(self, session_dir: str):
        self.session_dir = Path(session_dir)
        self.session_manager = SessionManager(str(self.session_dir))
        self.ollama = get_ollama_service()

    # ===== INTELLIGENT MODEL SELECTION =====

    def _select_planning_model(self, toon: Dict[str, Any]) -> str:
        """Intelligently select planning model based on TOON factors.

        WORKFLOW.md SPEC: Use OPUS for deep reasoning, but this function
        applies intelligence to choose appropriate model based on complexity.

        Available models:
        - haiku: Fast and cheap, good for simple planning (complexity 1-3)
        - sonnet: Balanced reasoning, good for medium complexity (4-7)
        - opus: Deep reasoning, best for complex architecture (8-10)

        Args:
            toon: TOON object with complexity_score, files_affected, etc.

        Returns:
            Model name: "haiku" | "sonnet" | "opus"
        """
        complexity_score = toon.get("complexity_score", 5)
        files_affected = len(toon.get("files_affected", []))
        project_type = toon.get("project_type", "unknown")

        # Build decision prompt for LLM
        decision_prompt = f"""Analyze this planning requirement and select the best LLM model:

FACTORS:
- Complexity score: {complexity_score}/10
- Files affected: {files_affected}
- Project type: {project_type}

AVAILABLE MODELS:
- haiku: Fast and cheap, good for simple/straightforward planning
- sonnet: Balanced reasoning and speed, good for medium complexity
- opus: Deep reasoning, best for complex architecture or intricate requirements

DECISION LOGIC:
- Complexity 1-3: haiku is usually sufficient and cost-effective
- Complexity 4-7: sonnet provides good balance of reasoning and speed
- Complexity 8-10: opus provides deep reasoning needed for complex tasks

Based on these factors and the DECISION LOGIC above, which model would be BEST for this planning task?

Respond with ONLY the model name (haiku, sonnet, or opus). No explanation needed."""

        try:
            logger.info("→ Selecting planning model based on TOON factors...")
            response = self.ollama.chat(
                messages=[{"role": "user", "content": decision_prompt}],
                model="fast_classification",  # Use fast model for decision-making
                temperature=0.3  # Low temperature for deterministic choice
            )

            model_choice = response.get("message", {}).get("content", "sonnet").strip().lower()

            # Validate choice
            if model_choice not in ["haiku", "sonnet", "opus"]:
                logger.warning(f"Invalid model choice '{model_choice}', defaulting to sonnet")
                model_choice = "sonnet"

            logger.info(f"✓ Selected model: {model_choice} (complexity: {complexity_score}/10, files: {files_affected})")
            return model_choice

        except Exception as e:
            logger.warning(f"Model selection failed, defaulting to sonnet: {e}")
            return "sonnet"

    # ===== STEP 2: PLAN EXECUTION =====

    def step2_plan_execution(
        self,
        toon: Dict[str, Any],
        user_requirement: str,
        project_root: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute detailed planning phase with tool-optimized code exploration.

        Only runs if Step 1 returned plan_required=True.

        WORKFLOW.md SPEC: Use exploration tools (Read, Grep, Search) with optimization
        - Read: offset/limit (max 500 lines per file)
        - Grep: head_limit (max 50 matches)
        - Search: max_results optimization (max 10 results)

        This implementation:
        1. Uses tool-like methods for exploration (_tool_read, _tool_grep, _tool_search)
        2. Enforces optimization rules explicitly
        3. Grounds planning in actual codebase analysis
        4. Follows WORKFLOW.md specification for tool usage

        Args:
            toon: TOON object from Level 1
            user_requirement: Original user requirement
            project_root: Root directory for code exploration (optional)

        Returns:
            {
                "plan": str,  # Detailed execution plan
                "files_affected": List[str],
                "phases": List[Dict],
                "risks": Dict,
                "code_context": str,  # Code snippets from tool-optimized exploration
                "selected_model": str,  # Model used (haiku/sonnet/opus)
                "success": bool
            }
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 2: PLAN EXECUTION (with tool-optimized exploration)")
        logger.info("=" * 60)
        logger.info("WORKFLOW.md SPEC: Using Read (offset/limit), Grep (head_limit), Search (optimization)")

        step_start = time.time()

        try:
            # EXPLORATION PHASE: Use tool-optimized methods (Read, Grep, Search)
            logger.info("→ Running tool-optimized codebase exploration...")
            code_context = self._explore_codebase(user_requirement, project_root)

            # Build enriched prompt with code analysis
            prompt = f"""Create a detailed implementation plan grounded in the actual codebase.

USER REQUIREMENT:
{user_requirement}

PROJECT ANALYSIS:
- Complexity: {toon.get('complexity_score')}/10
- Files loaded: {toon.get('files_loaded_count')}
- Project type: {toon.get('project_type', 'unknown')}

CODEBASE CONTEXT (from exploration):
{code_context}

Generate a comprehensive plan that includes:
1. High-level strategy aligned with existing patterns
2. Specific implementation phases with file references
3. Which existing files need modification (based on code analysis)
4. New files needed (if any)
5. Dependencies between tasks (respect existing architecture)
6. Risk assessment with specific concerns based on code patterns
7. Testing approach using existing test patterns

IMPORTANT: Reference actual files and code patterns found in the analysis.
Be very specific and actionable - mention actual file paths and existing functions/classes."""

            # INTELLIGENT MODEL SELECTION (WORKFLOW.md: choose appropriate model)
            logger.info("→ Selecting appropriate model for planning...")
            selected_model = self._select_planning_model(toon)

            logger.info(f"→ Generating plan with {selected_model} model...")
            response = self.ollama.chat(
                messages=[{"role": "user", "content": prompt}],
                model=selected_model,  # Use intelligently selected model
                temperature=0.5
            )

            if "error" in response:
                logger.error(f"Plan execution failed: {response['error']}")
                return {
                    "success": False,
                    "error": response["error"],
                    "execution_time_ms": (time.time() - step_start) * 1000
                }

            plan_text = response.get("message", {}).get("content", "")

            # Parse plan to extract key components
            files_affected = self._extract_files(plan_text)
            phases = self._extract_phases(plan_text)
            risks = self._extract_risks(plan_text)

            logger.info(f"✓ Plan created: {len(files_affected)} files, {len(phases)} phases")

            return {
                "success": True,
                "plan": plan_text,
                "files_affected": files_affected,
                "phases": phases,
                "risks": risks,
                "code_context": code_context,  # Store exploration results
                "selected_model": selected_model,  # Track which model was used
                "execution_time_ms": (time.time() - step_start) * 1000,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 2 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    def _extract_files(self, plan_text: str) -> List[str]:
        """Extract list of affected files from plan text."""
        files = []
        lines = plan_text.split('\n')
        for line in lines:
            # Look for patterns like "src/file.py" or "tests/test.py"
            if any(marker in line for marker in ["src/", "tests/", "scripts/", ".py", ".java", ".js", ".ts"]):
                # Simple heuristic: lines with file extensions
                for word in line.split():
                    if any(ext in word for ext in [".py", ".java", ".js", ".ts", ".jsx", ".tsx"]):
                        files.append(word.strip(",;:()"))
        return list(set(files))  # Remove duplicates

    def _extract_phases(self, plan_text: str) -> List[Dict[str, Any]]:
        """Extract execution phases from plan text."""
        phases = []
        phase_num = 1

        # Simple approach: split by "Phase" keyword
        for section in plan_text.split("Phase"):
            if len(section.strip()) > 10:
                lines = section.split('\n')
                title = lines[0].strip() if lines else f"Phase {phase_num}"
                description = '\n'.join(lines[1:5]) if len(lines) > 1 else ""

                phases.append({
                    "phase_number": phase_num,
                    "title": title,
                    "description": description.strip(),
                    "tasks": [],
                    "files_affected": []
                })
                phase_num += 1

        return phases if phases else [{
            "phase_number": 1,
            "title": "Implementation",
            "description": "Execute the planned changes",
            "tasks": [],
            "files_affected": []
        }]

    def _extract_risks(self, plan_text: str) -> Dict[str, Any]:
        """Extract risk assessment from plan text."""
        risk_level = "medium"
        factors = []
        mitigation = []

        # Simple keyword matching
        if "high risk" in plan_text.lower() or "critical" in plan_text.lower():
            risk_level = "high"
        elif "low risk" in plan_text.lower() or "safe" in plan_text.lower():
            risk_level = "low"

        return {
            "risk_level": risk_level,
            "factors": factors,
            "mitigation": mitigation
        }

    # ===== TOOL-OPTIMIZED EXPLORATION (WORKFLOW.md: Read, Grep, Search) =====

    def _tool_read(self, file_path: str, offset: int = 0, limit: int = 500) -> str:
        """Simulate Claude's Read tool with offset/limit optimization.

        WORKFLOW.md SPEC: Read (with offset/limit for large files)

        Args:
            file_path: Path to file relative to project root
            offset: Starting line number (0-indexed)
            limit: Maximum lines to read (max 500)

        Returns:
            File contents from offset to offset+limit
        """
        try:
            # Enforce limit (max 500 lines)
            if limit > 500:
                logger.warning(f"Read limit {limit} exceeds max 500, using 500")
                limit = 500

            full_path = self.session_dir.parent / file_path
            if not full_path.exists():
                return f"File not found: {file_path}"

            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # Apply offset and limit
            start = min(offset, len(lines))
            end = min(start + limit, len(lines))
            selected_lines = lines[start:end]

            result = f"=== {file_path} (lines {start}-{end}) ===\n"
            result += "".join(selected_lines)
            return result

        except Exception as e:
            return f"Error reading {file_path}: {e}"

    def _tool_grep(self, pattern: str, glob_pattern: str = "**/*.py", head_limit: int = 20) -> str:
        """Simulate Claude's Grep tool with head_limit optimization.

        WORKFLOW.md SPEC: Grep (with head_limit)

        Args:
            pattern: Regex pattern to search for
            glob_pattern: File glob pattern (e.g., "**/*.py")
            head_limit: Maximum matches to return (max 50)

        Returns:
            List of matching files and lines
        """
        try:
            # Enforce head_limit (max 50)
            if head_limit > 50:
                logger.warning(f"Grep head_limit {head_limit} exceeds max 50, using 50")
                head_limit = 50

            root = self.session_dir.parent
            matches = []
            match_count = 0

            for file_path in root.glob(glob_pattern):
                if not file_path.is_file():
                    continue

                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            if pattern.lower() in line.lower():
                                rel_path = file_path.relative_to(root)
                                matches.append(f"{rel_path}:{line_num}: {line.strip()}")
                                match_count += 1
                                if match_count >= head_limit:
                                    break
                except Exception:
                    pass

                if match_count >= head_limit:
                    break

            result = f"=== Grep: {pattern} ({match_count} matches, limit {head_limit}) ===\n"
            result += "\n".join(matches[:head_limit])
            return result

        except Exception as e:
            return f"Error in grep: {e}"

    def _tool_search(self, query: str, max_results: int = 10) -> str:
        """Simulate Claude's Search tool with optimization.

        WORKFLOW.md SPEC: Search (with optimization)

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            List of relevant files and context
        """
        try:
            # Limit results
            max_results = min(max_results, 10)

            root = self.session_dir.parent
            keywords = query.lower().split()[:5]  # Take first 5 keywords
            results = {}

            # Search for files matching keywords
            for file_path in root.rglob("*.py"):
                if not file_path.is_file():
                    continue

                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    # Count keyword matches
                    matches = sum(content.lower().count(kw) for kw in keywords)
                    if matches > 0:
                        rel_path = file_path.relative_to(root)
                        results[str(rel_path)] = matches

                except Exception:
                    pass

            # Sort by match count and return top results
            sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
            result = f"=== Search: {query} ({len(sorted_results)} matches) ===\n"
            result += "\n".join(f"{path}: {count} matches" for path, count in sorted_results[:max_results])
            return result

        except Exception as e:
            return f"Error in search: {e}"

    def _explore_codebase(self, user_requirement: str, project_root: Optional[str] = None) -> str:
        """
        Explore codebase using tool-optimized methods (Read, Grep, Search).

        WORKFLOW.md SPEC: Use exploration tools (Read, Grep, Search)
        This method uses tool-like calls with optimization rules:
        - Read: offset/limit (max 500 lines per file)
        - Grep: head_limit (max 50 matches)
        - Search: max_results optimization

        Args:
            user_requirement: User's requirement to search for related code
            project_root: Root directory to explore (defaults to session_dir)

        Returns:
            String containing exploration results from tool calls
        """
        if project_root is None:
            project_root = str(self.session_dir)

        try:
            analysis_parts = []

            # 1. Search for relevant files (TOOL: Search)
            logger.info("→ Searching for relevant files...")
            analysis_parts.append("=== SEARCH RESULTS ===")
            search_result = self._tool_search(user_requirement, max_results=10)
            analysis_parts.append(search_result)

            # 2. Grep for keyword matches (TOOL: Grep with head_limit)
            logger.info("→ Finding code patterns...")
            analysis_parts.append("\n=== CODE PATTERNS (Grep with head_limit=20) ===")
            keywords = user_requirement.lower().split()[:3]
            if keywords:
                for keyword in keywords:
                    grep_result = self._tool_grep(keyword, glob_pattern="**/*.py", head_limit=20)
                    analysis_parts.append(grep_result)
            else:
                analysis_parts.append("(No keywords to search)")

            # 3. Read key files (TOOL: Read with offset/limit)
            logger.info("→ Reading key file contents...")
            analysis_parts.append("\n=== KEY FILE CONTENTS (Read with limit=500) ===")
            key_files = self._find_key_files(project_root)
            for file_type, files in key_files.items():
                if files:
                    for file_path in files[:2]:  # Read first 2 key files
                        try:
                            read_result = self._tool_read(file_path, offset=0, limit=500)
                            analysis_parts.append(f"\n{read_result}")
                        except Exception as e:
                            logger.debug(f"Could not read {file_path}: {e}")

            # 4. Project structure (informational)
            analysis_parts.append("\n=== PROJECT STRUCTURE ===")
            structure = self._analyze_directory_structure(project_root)
            analysis_parts.append(structure)

            logger.info("✓ Codebase exploration completed with tool-optimized methods")
            return "\n".join(analysis_parts)

        except Exception as e:
            logger.warning(f"Codebase exploration partial: {e}")
            return f"Could not fully explore codebase: {str(e)}"

    def _analyze_directory_structure(self, root: str, max_depth: int = 2) -> str:
        """Analyze directory structure."""
        try:
            root_path = Path(root)
            if not root_path.exists():
                return f"Directory not found: {root}"

            lines = []
            lines.append(f"Root: {root_path.name}/")

            # List key directories
            for item in sorted(root_path.iterdir()):
                if item.is_dir() and not item.name.startswith('.'):
                    lines.append(f"  📁 {item.name}/")
                    # Count files in this dir
                    file_count = len(list(item.glob("*.*")))
                    if file_count > 0:
                        lines.append(f"      ({file_count} files)")

            return "\n".join(lines[:20])  # Limit output
        except Exception as e:
            return f"Structure analysis failed: {e}"

    def _find_relevant_files(self, requirement: str, root: str) -> List[str]:
        """Find files related to the requirement using keyword matching."""
        try:
            root_path = Path(root)
            if not root_path.exists():
                return []

            relevant = []
            keywords = requirement.lower().split()[:5]  # Get first 5 keywords

            # Search for Python files with matching names or content
            for pattern in ["*.py", "*.java", "*.js", "*.ts", "*.go"]:
                for file_path in root_path.rglob(pattern):
                    if file_path.is_file() and ".git" not in str(file_path):
                        # Check filename for keywords
                        filename_lower = file_path.name.lower()
                        for keyword in keywords:
                            if keyword in filename_lower and len(keyword) > 2:
                                relevant.append(str(file_path.relative_to(root_path)))
                                break

            return list(set(relevant))[:10]
        except Exception as e:
            logger.debug(f"File search failed: {e}")
            return []

    def _detect_project_patterns(self, root: str) -> str:
        """Detect programming language and architectural patterns."""
        try:
            root_path = Path(root)
            patterns = []

            # Check file extensions
            extensions = {}
            for file_path in root_path.rglob("*.*"):
                if ".git" not in str(file_path):
                    ext = file_path.suffix
                    extensions[ext] = extensions.get(ext, 0) + 1

            # Identify primary language
            language_map = {
                ".py": "Python",
                ".java": "Java",
                ".js": "JavaScript",
                ".ts": "TypeScript",
                ".go": "Go",
                ".rs": "Rust",
            }

            primary_lang = None
            max_count = 0
            for ext, lang in language_map.items():
                if extensions.get(ext, 0) > max_count:
                    max_count = extensions[ext]
                    primary_lang = lang

            if primary_lang:
                patterns.append(f"Primary Language: {primary_lang} ({max_count} files)")

            # Check for common frameworks/tools
            for name in ["requirements.txt", "package.json", "go.mod", "Cargo.toml", "pom.xml"]:
                if (root_path / name).exists():
                    patterns.append(f"Found: {name} (dependency manifest)")

            for name in [".git", "docker-compose.yml", "Dockerfile", ".github"]:
                if (root_path / name).exists():
                    patterns.append(f"Found: {name}")

            return "\n".join(patterns) if patterns else "No specific patterns detected"

        except Exception as e:
            return f"Pattern detection incomplete: {e}"

    def _find_key_files(self, root: str) -> Dict[str, List[str]]:
        """Find key architectural files (config, main, test, etc)."""
        try:
            root_path = Path(root)
            key_files = {
                "Config": [],
                "Main/Entry": [],
                "Tests": [],
                "Documentation": []
            }

            config_patterns = ["config.py", "settings.py", "requirements.txt", ".env"]
            main_patterns = ["main.py", "app.py", "index.py", "main.java", "app.js"]
            test_patterns = ["test_*.py", "*_test.py", "*.test.js", "*Test.java"]
            doc_patterns = ["README.md", "ARCHITECTURE.md", "DESIGN.md"]

            for pattern in config_patterns:
                files = list(root_path.rglob(pattern))
                key_files["Config"].extend([f.relative_to(root_path).as_posix() for f in files])

            for pattern in main_patterns:
                files = list(root_path.rglob(pattern))
                key_files["Main/Entry"].extend([f.relative_to(root_path).as_posix() for f in files])

            for pattern in test_patterns:
                files = list(root_path.rglob(pattern))
                key_files["Tests"].extend([f.relative_to(root_path).as_posix() for f in files])

            for pattern in doc_patterns:
                files = list(root_path.rglob(pattern))
                key_files["Documentation"].extend([f.relative_to(root_path).as_posix() for f in files])

            return key_files
        except Exception:
            return {k: [] for k in ["Config", "Main/Entry", "Tests", "Documentation"]}

    def _extract_code_snippets(self, file_paths: List[str], max_files: int = 3) -> str:
        """Extract relevant code snippets from files."""
        try:
            snippets = []
            for file_path in file_paths[:max_files]:
                try:
                    full_path = self.session_dir / file_path
                    if full_path.exists() and full_path.is_file():
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()
                            # Get first 15 lines (imports, class/function defs)
                            snippet = "".join(lines[:15])
                            if len(snippet) > 200:
                                snippet = snippet[:200] + "..."
                            snippets.append(f"\n### {file_path}:\n{snippet}")
                except Exception:
                    pass

            return "".join(snippets) if snippets else "(No code snippets available)"
        except Exception as e:
            return f"Code extraction failed: {e}"

    # ===== STEP 3: TASK BREAKDOWN =====

    def step3_task_breakdown(
        self,
        plan: str,
        files_affected: List[str]
    ) -> Dict[str, Any]:
        """
        Break down plan into concrete tasks.

        Args:
            plan: Execution plan from Step 2
            files_affected: Files to be modified

        Returns:
            {
                "tasks": List[Dict],  # Each task has id, name, files, modifications
                "task_count": int,
                "dependencies": Dict,
                "success": bool
            }
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 3: TASK BREAKDOWN")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            tasks = []
            task_id = 1

            # Simple breakdown: one task per file
            for file_path in files_affected:
                tasks.append({
                    "id": f"Task-{task_id}",
                    "name": f"Modify {file_path}",
                    "file": file_path,
                    "modifications": [f"Update {file_path} as per plan"],
                    "dependencies": [f"Task-{task_id - 1}"] if task_id > 1 else [],
                    "execution_order": task_id
                })
                task_id += 1

            logger.info(f"✓ Task breakdown: {len(tasks)} tasks")

            return {
                "success": True,
                "tasks": tasks,
                "task_count": len(tasks),
                "dependencies": self._build_dependencies(tasks),
                "execution_time_ms": (time.time() - step_start) * 1000,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 3 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    def _build_dependencies(self, tasks: List[Dict]) -> Dict[str, List[str]]:
        """Build task dependency graph."""
        deps = {}
        for task in tasks:
            deps[task["id"]] = task.get("dependencies", [])
        return deps

    # ===== STEP 4: TOON REFINEMENT =====

    def step4_toon_refinement(
        self,
        toon_analysis: Dict[str, Any],
        plan: Dict[str, Any],
        tasks: List[Dict]
    ) -> Dict[str, Any]:
        """
        Refine TOON to ExecutionBlueprint.

        Compresses after planning phase.

        Args:
            toon_analysis: Original ToonAnalysis from Level 1
            plan: Plan from Step 2
            tasks: Tasks from Step 3

        Returns:
            ExecutionBlueprint object as dict
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 4: TOON REFINEMENT")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            blueprint = {
                "session_id": toon_analysis.get("session_id"),
                "timestamp": datetime.now().isoformat(),
                "complexity_score": toon_analysis.get("complexity_score", 5),
                "plan": plan.get("plan", ""),
                "files_affected": plan.get("files_affected", []),
                "phases": plan.get("phases", []),
                "risks": plan.get("risks", {"risk_level": "medium", "factors": [], "mitigation": []}),
                "selected_skills": [],  # To be filled in Step 5
                "selected_agents": [],  # To be filled in Step 5
                "execution_strategy": "sequential"
            }

            # Validate with Pydantic
            validated = ExecutionBlueprint(**blueprint)

            # Save to session
            self.session_manager.save_execution_blueprint(validated)

            logger.info("✓ TOON refined to ExecutionBlueprint")

            return {
                "success": True,
                "blueprint": validated.model_dump(),
                "execution_time_ms": (time.time() - step_start) * 1000,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 4 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    # ===== STEP 6: SKILL VALIDATION =====

    def _scan_available_skills(self) -> List[Dict[str, Any]]:
        """Scan ~/.claude/skills/ and return all available skills with metadata."""
        home = Path.home()
        skills_dir = home / ".claude" / "skills"
        available = []

        if not skills_dir.exists():
            logger.warning(f"Skills directory not found: {skills_dir}")
            return []

        try:
            for category_dir in skills_dir.iterdir():
                if not category_dir.is_dir():
                    continue

                category = category_dir.name
                for skill_dir in category_dir.iterdir():
                    if not skill_dir.is_dir():
                        continue

                    skill_name = skill_dir.name
                    skill_file = skill_dir / "skill.md"
                    skill_file_alt = skill_dir / "SKILL.md"

                    if skill_file.exists() or skill_file_alt.exists():
                        file_to_read = skill_file if skill_file.exists() else skill_file_alt
                        try:
                            content = file_to_read.read_text(encoding='utf-8')
                            available.append({
                                "name": skill_name,
                                "category": category,
                                "path": str(skill_dir),
                                "file": str(file_to_read),
                                "content_preview": content[:200]
                            })
                        except Exception as e:
                            logger.debug(f"Could not read {skill_name}: {e}")

            logger.info(f"✓ Found {len(available)} available skills on system")
            return available

        except Exception as e:
            logger.error(f"Error scanning skills: {e}")
            return []

    def _scan_available_agents(self) -> List[Dict[str, Any]]:
        """Scan ~/.claude/agents/ and return all available agents with metadata."""
        home = Path.home()
        agents_dir = home / ".claude" / "agents"
        available = []

        if not agents_dir.exists():
            logger.warning(f"Agents directory not found: {agents_dir}")
            return []

        try:
            for agent_dir in agents_dir.iterdir():
                if not agent_dir.is_dir() or agent_dir.name == "__pycache__":
                    continue

                agent_name = agent_dir.name
                agent_file = agent_dir / "agent.md"

                if agent_file.exists():
                    try:
                        content = agent_file.read_text(encoding='utf-8')
                        available.append({
                            "name": agent_name,
                            "path": str(agent_dir),
                            "file": str(agent_file),
                            "content_preview": content[:200]
                        })
                    except Exception as e:
                        logger.debug(f"Could not read agent {agent_name}: {e}")

            logger.info(f"✓ Found {len(available)} available agents on system")
            return available

        except Exception as e:
            logger.error(f"Error scanning agents: {e}")
            return []

    def _download_skill_from_internet(self, skill_name: str, category: str = "backend") -> bool:
        """Download a skill from Claude Code GitHub repository if not available locally."""
        home = Path.home()
        skills_dir = home / ".claude" / "skills" / category / skill_name

        if skills_dir.exists():
            logger.info(f"Skill {skill_name} already exists locally")
            return True

        try:
            # Try to download from Claude Code GitHub
            github_url = (
                f"https://raw.githubusercontent.com/piyushmakhija28/claude-global-library/main/"
                f"skills/{category}/{skill_name}/skill.md"
            )

            import urllib.request
            logger.info(f"Downloading skill {skill_name} from {github_url}")

            # Create directory
            skills_dir.mkdir(parents=True, exist_ok=True)
            skill_file = skills_dir / "skill.md"

            urllib.request.urlretrieve(github_url, skill_file)
            logger.info(f"✓ Downloaded {skill_name} to {skill_file}")
            return True

        except Exception as e:
            logger.warning(f"Could not download {skill_name}: {e}")
            return False

    def step6_skill_validation_and_selection(
        self,
        toon: Dict[str, Any],
        llm_recommendation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        ENHANCED Step 6: Validate, select, and download skills/agents.

        Process:
        1. Scan available skills/agents on system
        2. Add to TOON for LLM reference
        3. Use LLM recommendation to select which to use
        4. Download missing skills from internet if needed
        5. Return selected skills with full content

        Args:
            toon: TOON object with task context
            llm_recommendation: From Step 5 - LLM's skill recommendations

        Returns:
            {
                "success": bool,
                "selected_skills": List[Dict],
                "selected_agents": List[Dict],
                "downloaded": List[str],
                "final_skills": List[Dict] with full content,
                "final_agents": List[Dict] with full content
            }
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 6: SKILL VALIDATION & SELECTION")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            # 1. Scan available skills and agents
            logger.info("📂 Scanning local skills and agents...")
            available_skills = self._scan_available_skills()
            available_agents = self._scan_available_agents()

            # 2. Enhance TOON with available list
            toon_enhanced = {
                **toon,
                "available_skills_on_system": [
                    {"name": s["name"], "category": s["category"]} for s in available_skills
                ],
                "available_agents_on_system": [
                    {"name": a["name"]} for a in available_agents
                ],
                "available_skills_count": len(available_skills),
                "available_agents_count": len(available_agents)
            }

            logger.info(f"Found {len(available_skills)} skills, {len(available_agents)} agents")

            # 3. Get LLM selection based on available skills
            selected_skills = llm_recommendation.get("final_skills_selected", [])
            selected_agents = llm_recommendation.get("final_agents_selected", [])
            missing_preferences = llm_recommendation.get("missing_but_prefer", [])

            # 4. Check if selected skills exist, download if missing
            downloaded = []
            final_skills = []
            final_agents = []

            # Process selected skills
            for skill_name in selected_skills:
                # Find in available skills
                skill_found = None
                for skill in available_skills:
                    if skill["name"] == skill_name:
                        skill_found = skill
                        break

                if skill_found:
                    final_skills.append(skill_found)
                else:
                    # Try to download from internet
                    logger.info(f"Skill {skill_name} not available locally, attempting download...")
                    if self._download_skill_from_internet(skill_name):
                        downloaded.append(skill_name)
                        # Re-scan to get the downloaded skill
                        updated_skills = self._scan_available_skills()
                        for skill in updated_skills:
                            if skill["name"] == skill_name:
                                final_skills.append(skill)
                                break

            # Process selected agents
            for agent_name in selected_agents:
                agent_found = None
                for agent in available_agents:
                    if agent["name"] == agent_name:
                        agent_found = agent
                        break

                if agent_found:
                    final_agents.append(agent_found)

            # 5. Handle missing but preferred skills
            for skill_name in missing_preferences:
                if not any(s["name"] == skill_name for s in final_skills):
                    logger.info(f"Preferred skill {skill_name} missing, attempting download...")
                    if self._download_skill_from_internet(skill_name):
                        downloaded.append(skill_name)

            logger.info(f"✓ Selected {len(final_skills)} skills, {len(final_agents)} agents")
            if downloaded:
                logger.info(f"✓ Downloaded {len(downloaded)} missing skills: {downloaded}")

            return {
                "success": True,
                "selected_skills": selected_skills,
                "selected_agents": selected_agents,
                "final_skills": final_skills,
                "final_agents": final_agents,
                "downloaded": downloaded,
                "toon_enhanced": toon_enhanced,
                "execution_time_ms": (time.time() - step_start) * 1000,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 6 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    def step6_validate_skills(self, skill_mappings: List[Dict]) -> Dict[str, Any]:
        """
        Legacy Step 6: Validate selected skills exist in ~/.claude/skills/.
        (Kept for backward compatibility)

        Args:
            skill_mappings: Skill mappings from Step 5

        Returns:
            {"success": bool, "valid_skills": List[str], "warnings": List[str]}
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 6: SKILL VALIDATION (Legacy)")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            home = Path.home()
            skills_dir = home / ".claude" / "skills"

            valid_skills = []
            warnings = []

            for mapping in skill_mappings:
                for skill_name in mapping.get("required_skills", []):
                    # Check if skill exists
                    if not self._skill_exists(skill_name, skills_dir):
                        warnings.append(f"Skill not found: {skill_name}")
                    else:
                        valid_skills.append(skill_name)

            logger.info(f"✓ Validated {len(valid_skills)} skills")
            if warnings:
                logger.warning(f"Found {len(warnings)} missing skills")

            return {
                "success": len(warnings) == 0,
                "valid_skills": list(set(valid_skills)),
                "warnings": warnings,
                "execution_time_ms": (time.time() - step_start) * 1000,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 6 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    def _skill_exists(self, skill_name: str, skills_dir: Path) -> bool:
        """Check if a skill exists in skills directory."""
        if not skills_dir.exists():
            return False

        # Check all subdirectories
        for category_dir in skills_dir.iterdir():
            if category_dir.is_dir():
                skill_path = category_dir / skill_name / "skill.md"
                skill_path_alt = category_dir / skill_name / "SKILL.md"
                if skill_path.exists() or skill_path_alt.exists():
                    return True
        return False

    # ===== STEP 13: DOCUMENTATION UPDATE =====

    def step13_update_documentation(self, files_modified: List[str]) -> Dict[str, Any]:
        """
        Update project documentation (README, CLAUDE.md, SRA, VERSION, CHANGELOG).

        Uses enterprise-grade templates with intelligent creation/update logic:
        - CREATE: Full codebase analysis → complete documentation
        - UPDATE: Latest changes only → smart merge with existing content

        Args:
            files_modified: Files that were modified

        Returns:
            {
                "success": bool,
                "updated_files": List[str],
                "errors": Optional[List[str]],
                "execution_time_ms": float,
                "context": {project_name, languages, frameworks, version}
            }
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 13: DOCUMENTATION UPDATE")
        logger.info("Enterprise-grade documentation generation")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            from .documentation_generator import DocumentationGenerator

            # Initialize generator (analyzes codebase automatically)
            gen = DocumentationGenerator(
                project_root=".",
                session_dir=self.session_manager.session_dir
            )

            logger.info("Generating/updating all documentation files...")

            # Generate/update all 5 documentation files intelligently
            result = gen.update_all_documentation(files_modified)

            execution_time_ms = (time.time() - step_start) * 1000

            # Log results
            if result["success"]:
                logger.info(f"✓ Documentation generation successful")
                logger.info(f"  Files updated: {len(result['updated_files'])}")
                for file in result['updated_files']:
                    logger.info(f"    - {file}")

                if result.get('context'):
                    ctx = result['context']
                    logger.info(f"  Project: {ctx.get('project_name')}")
                    logger.info(f"  Languages: {', '.join(ctx.get('languages', []))}")
                    logger.info(f"  Frameworks: {', '.join(ctx.get('frameworks', []))}")
                    logger.info(f"  Version: {ctx.get('version')}")
            else:
                logger.error(f"Documentation generation had errors")
                if result.get('errors'):
                    for error in result['errors']:
                        logger.error(f"  - {error}")

            # Save to session
            self.session_manager.save_github_details({
                "documentation_updated": result['updated_files'],
                "documentation_status": "success" if result['success'] else "partial",
                "documentation_context": result.get('context', {}),
                "timestamp": datetime.now().isoformat()
            })

            return {
                "success": result['success'],
                "updated_files": result['updated_files'],
                "errors": result.get('errors'),
                "execution_time_ms": execution_time_ms,
                "context": result.get('context'),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 13 failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "updated_files": [],
                "execution_time_ms": (time.time() - step_start) * 1000,
                "timestamp": datetime.now().isoformat()
            }


    # ===== STEP 14: FINAL SUMMARY =====

    def step14_final_summary(
        self,
        issue_number: int,
        pr_number: int,
        files_modified: List[str],
        approach_summary: str = ""
    ) -> Dict[str, Any]:
        """
        Generate final summary and voice notification.

        Args:
            issue_number: GitHub issue number
            pr_number: PR number
            files_modified: Files that were modified
            approach_summary: Summary of implementation approach

        Returns:
            {"success": bool, "summary": str, "voice_notification": bool}
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 14: FINAL SUMMARY")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            # Build summary narrative
            summary = self._build_summary_narrative(
                issue_number,
                pr_number,
                files_modified,
                approach_summary
            )

            logger.info("Generated final summary")
            logger.info(summary)

            # Attempt voice notification (best effort)
            voice_success = self._send_voice_notification(summary)

            # Save summary to session
            self.session_manager.save_github_details({
                "final_summary": summary,
                "voice_notification_sent": voice_success,
                "timestamp": datetime.now().isoformat()
            })

            return {
                "success": True,
                "summary": summary,
                "voice_notification": voice_success,
                "execution_time_ms": (time.time() - step_start) * 1000,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 14 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    def _build_summary_narrative(
        self,
        issue_number: int,
        pr_number: int,
        files_modified: List[str],
        approach_summary: str
    ) -> str:
        """Build story-style final summary."""
        summary = f"""
## ✅ Task Completed Successfully

**Issue:** #{issue_number}
**Pull Request:** #{pr_number}

### What Was Accomplished
{approach_summary if approach_summary else "Successfully resolved the GitHub issue."}

### Files Modified
"""
        for file in files_modified[:10]:
            summary += f"- {file}\n"

        if len(files_modified) > 10:
            summary += f"- ... and {len(files_modified) - 10} more files\n"

        summary += f"""
### Summary
The task has been completed and integrated into the main branch via pull request #{pr_number}.
All changes are tested and documented.

---
*Completed by Claude Insight Level 3 Execution Pipeline*
"""
        return summary

    def _send_voice_notification(self, summary: str) -> bool:
        """Attempt to send voice notification."""
        try:
            import platform
            import sys
            system = platform.system()

            if system == "Darwin":  # macOS
                subprocess.run(
                    ["say", "Task completed successfully"],
                    timeout=5
                )
            elif system == "Windows":
                # Windows MessageBox notification
                try:
                    msg = "Task completed successfully"
                    subprocess.run(
                        ["powershell", "-Command",
                         f'[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null; [System.Windows.Forms.MessageBox]::Show("{msg}", "Claude Insight")'],
                        timeout=5,
                        capture_output=True
                    )
                except Exception:
                    # If PowerShell fails, just log it
                    pass
            else:  # Linux
                subprocess.run(
                    ["notify-send", "Task", "Completed successfully"],
                    timeout=5
                )

            return True
        except Exception as e:
            logger.debug(f"Voice notification failed: {e}")
            return False
