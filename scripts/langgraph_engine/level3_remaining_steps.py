"""
Level 3 - Remaining Steps: 2-7, 13-14

Implements:
- Step 2: Plan execution (if plan_required=True from Step 1)
- Step 3: Task breakdown
- Step 4: TOON refinement (compress after planning)
- Step 6: Skill/agent validation
- Step 7: Final prompt generation (intelligent routing: GPU or NPU)
- Step 13: Documentation update
- Step 14: Final summary and voice notification

Uses InferenceRouter for smart GPU/NPU backend selection based on task type.
Note: Step 10 (Implementation) is handled by Claude directly with tools
Note: Step 5 (Skill selection) is in ollama_service.py, wrapper here
"""

import time
import json
import subprocess
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, TypeVar
from datetime import datetime

from loguru import logger
from .toon_models import ExecutionBlueprint, ToonWithSkills
from .session_manager import SessionManager
from .inference_router import get_inference_router
from .plan_convergence import run_planning_loop, assess_plan_quality, DEFAULT_MAX_ITERATIONS
from .task_validator import validate_breakdown
from .token_manager import TokenBudget

# Focused sub-modules (extracted helpers)
from .level3_code_explorer import (
    tool_read,
    tool_grep,
    tool_search,
    explore_codebase,
    analyze_directory_structure,
    find_relevant_files,
    detect_project_patterns,
    find_key_files,
    extract_code_snippets,
)
from .level3_llm_retry import (
    is_llm_retryable,
    llm_call_with_retry,
    LLM_MAX_RETRIES,
    LLM_BACKOFF_DELAYS,
)

# Optional performance modules
try:
    from .parallel_executor import run_parallel_step2_exploration
    from .cache_system import get_pipeline_cache, cached_llm_call
    _PERF_AVAILABLE = True
except ImportError:
    _PERF_AVAILABLE = False


# ---------------------------------------------------------------------------
# Module-level aliases kept for any code that referenced the private names
# directly (e.g., tests or subgraphs that imported from this module).
# ---------------------------------------------------------------------------

T = TypeVar("T")

_LLM_BACKOFF_DELAYS: List[float] = LLM_BACKOFF_DELAYS
_LLM_MAX_RETRIES: int = LLM_MAX_RETRIES


def _is_llm_retryable(exc: Exception) -> bool:
    """Alias for :func:`level3_llm_retry.is_llm_retryable` (backward compat)."""
    return is_llm_retryable(exc)


def _llm_call_with_retry(
    call_fn: Callable[[], T],
    step_name: str,
    max_retries: int = LLM_MAX_RETRIES,
) -> T:
    """Alias for :func:`level3_llm_retry.llm_call_with_retry` (backward compat)."""
    return llm_call_with_retry(call_fn, step_name, max_retries=max_retries)


class Level3RemainingSteps:
    """Implements steps 2-7, 13-14 for Level 3 execution with GPU/NPU routing."""

    def __init__(self, session_dir: str, token_budget: Optional[TokenBudget] = None):
        self.session_dir = Path(session_dir)
        self.session_manager = SessionManager(str(self.session_dir))
        # Use InferenceRouter for smart GPU/NPU backend selection
        self.inference = get_inference_router()
        # Keep reference to ollama for compatibility (routes through inference_router)
        self.ollama = self.inference.ollama
        # Optional token budget shared across the pipeline
        self.token_budget = token_budget

    # ===== INTELLIGENT MODEL SELECTION =====

    def _select_planning_model(self, toon: Dict[str, Any]) -> str:
        """Intelligently select planning model based on TOON factors.

        Maps complexity to available Ollama models via service.
        The OllamaService handles actual model routing based on availability.

        Available models (via OllamaService):
        - fast_classification: qwen2.5:7b (good for simple planning, complexity 1-5)
        - complex_reasoning: granite4:3b (for complex architecture, complexity 6-10)

        Args:
            toon: TOON object with complexity_score, files_affected, etc.

        Returns:
            Model type: "fast_classification" | "complex_reasoning"
        """
        complexity_score = toon.get("complexity_score", 5)
        files_affected = len(toon.get("files_affected", []))
        project_type = toon.get("project_type", "unknown")

        # Simple threshold-based selection (Ollama has fewer models than Claude)
        # Complexity 1-5: Use fast, efficient model
        # Complexity 6-10: Use more capable model for deep reasoning
        if complexity_score <= 5:
            selected_model = "fast_classification"
            reason = "Low-medium complexity, fast model sufficient"
        else:
            selected_model = "complex_reasoning"
            reason = "High complexity, deeper reasoning needed"

        logger.info(f"-> Selecting planning model based on TOON factors...")
        logger.info(f"   Complexity: {complexity_score}/10, Files: {files_affected}, Type: {project_type}")
        logger.info(f"✓ Selected model: {selected_model} ({reason})")

        return selected_model

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

        Uses Ollama models (fast_classification or complex_reasoning) selected
        based on complexity score via _select_planning_model().

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
                "selected_model": str,  # Model used (fast_classification/complex_reasoning)
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

            logger.info(f"→ Generating plan with {selected_model} model (convergence loop)...")

            # ---- CONVERGENCE LOOP via plan_convergence.run_planning_loop ----
            # Each iteration calls the LLM and checks quality; exits when
            # quality >= 0.85 OR max_iterations reached.

            def _generate_one_plan() -> Dict[str, Any]:
                """Single plan generation attempt with LLM caching + retry."""
                messages = [{"role": "user", "content": prompt}]

                def _call_inference() -> Dict[str, Any]:
                    # Try LLM response cache (1h TTL) before hitting inference backend
                    if _PERF_AVAILABLE:
                        try:
                            _cache = get_pipeline_cache()
                            _key = _cache.llm.make_llm_key(selected_model, messages)
                            _cached = _cache.llm.get(_key)
                            if _cached is not None:
                                logger.info("Step 2: LLM cache HIT (key={}...)".format(_key[:8]))
                                return _cached
                        except Exception:
                            pass  # Cache errors are non-fatal

                    resp = self.inference.chat(
                        messages=messages,
                        task_type="planning",
                        complexity=toon.get("complexity_score", 5),
                        model=selected_model,
                        temperature=0.5,
                    )
                    if "error" in resp:
                        raise RuntimeError(resp["error"])

                    # Persist successful response to cache
                    if _PERF_AVAILABLE:
                        try:
                            _cache = get_pipeline_cache()
                            _key = _cache.llm.make_llm_key(selected_model, messages)
                            _cache.llm.set(_key, resp)
                        except Exception:
                            pass

                    return resp

                # Use retry wrapper for transient LLM/network failures
                resp = _llm_call_with_retry(_call_inference, "Step 2 Plan Generation")
                plan_text_inner = resp.get("message", {}).get("content", "")
                return {
                    "plan": plan_text_inner,
                    "files_affected": self._extract_files(plan_text_inner),
                    "phases": self._extract_phases(plan_text_inner),
                    "risks": self._extract_risks(plan_text_inner),
                }

            convergence_result = run_planning_loop(
                generate_plan_fn=_generate_one_plan,
                requirement=user_requirement,
                toon=toon,
                max_iterations=DEFAULT_MAX_ITERATIONS,
            )

            best_plan_dict = convergence_result["plan"]
            plan_text = best_plan_dict.get("plan", "")
            files_affected = best_plan_dict.get("files_affected", [])
            phases = best_plan_dict.get("phases", [])
            risks = best_plan_dict.get("risks", {})

            logger.info(
                f"✓ Plan created: {len(files_affected)} files, {len(phases)} phases "
                f"(quality={convergence_result['quality']:.2f}, "
                f"iterations={convergence_result['iterations']}, "
                f"converged={convergence_result['converged']})"
            )

            # Token budget accounting for Step 2
            if self.token_budget is not None:
                estimated_tokens = TokenBudget.estimate_tokens(plan_text)
                try:
                    self.token_budget.record_usage("step_2", estimated_tokens)
                except Exception as budget_err:
                    logger.warning(f"[Step 2] Token budget error: {budget_err}")

            return {
                "success": True,
                "plan": plan_text,
                "files_affected": files_affected,
                "phases": phases,
                "risks": risks,
                "code_context": code_context,
                "selected_model": selected_model,
                "plan_quality": convergence_result["quality"],
                "plan_iterations": convergence_result["iterations"],
                "plan_converged": convergence_result["converged"],
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
    # The heavy logic lives in level3_code_explorer.py.
    # These thin wrappers bind the session_dir so call sites need no changes.

    def _tool_read(self, file_path: str, offset: int = 0, limit: int = 500) -> str:
        """Delegate to :func:`level3_code_explorer.tool_read`."""
        return tool_read(file_path, offset=offset, limit=limit, base_path=self.session_dir.parent)

    def _tool_grep(self, pattern: str, glob_pattern: str = "**/*.py", head_limit: int = 20) -> str:
        """Delegate to :func:`level3_code_explorer.tool_grep`."""
        return tool_grep(pattern, glob_pattern=glob_pattern, head_limit=head_limit, base_path=self.session_dir.parent)

    def _tool_search(self, query: str, max_results: int = 10) -> str:
        """Delegate to :func:`level3_code_explorer.tool_search`."""
        return tool_search(query, max_results=max_results, base_path=self.session_dir.parent)

    def _explore_codebase(self, user_requirement: str, project_root: Optional[str] = None) -> str:
        """Delegate to :func:`level3_code_explorer.explore_codebase`."""
        if project_root is None:
            project_root = str(self.session_dir)
        return explore_codebase(user_requirement, project_root, base_path=self.session_dir.parent)

    def _analyze_directory_structure(self, root: str, max_depth: int = 2) -> str:
        """Delegate to :func:`level3_code_explorer.analyze_directory_structure`."""
        return analyze_directory_structure(root, max_depth=max_depth)

    def _find_relevant_files(self, requirement: str, root: str) -> List[str]:
        """Delegate to :func:`level3_code_explorer.find_relevant_files`."""
        return find_relevant_files(requirement, root)

    def _detect_project_patterns(self, root: str) -> str:
        """Delegate to :func:`level3_code_explorer.detect_project_patterns`."""
        return detect_project_patterns(root)

    def _find_key_files(self, root: str) -> Dict[str, List[str]]:
        """Delegate to :func:`level3_code_explorer.find_key_files`."""
        return find_key_files(root)

    def _extract_code_snippets(self, file_paths: List[str], max_files: int = 3) -> str:
        """Delegate to :func:`level3_code_explorer.extract_code_snippets`."""
        return extract_code_snippets(file_paths, max_files=max_files, base_path=self.session_dir)

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

            # ---- TASK VALIDATION (task_validator.validate_breakdown) ----
            user_req = plan if isinstance(plan, str) else ""
            valid, validation_errors = validate_breakdown(tasks, requirement=user_req)
            if not valid:
                logger.warning(
                    f"[Step 3] Task breakdown validation found issues: {validation_errors}"
                )
            else:
                logger.info("[Step 3] Task breakdown validation passed")

            # Token budget accounting for Step 3
            if self.token_budget is not None:
                estimated_tokens = TokenBudget.estimate_tokens(str(tasks))
                try:
                    self.token_budget.record_usage("step_3", estimated_tokens)
                except Exception as budget_err:
                    logger.warning(f"[Step 3] Token budget error: {budget_err}")

            logger.info(f"✓ Task breakdown: {len(tasks)} tasks")

            return {
                "success": True,
                "tasks": tasks,
                "task_count": len(tasks),
                "dependencies": self._build_dependencies(tasks),
                "validation_passed": valid,
                "validation_errors": validation_errors,
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
        Refine TOON to ExecutionBlueprint with enriched metadata.

        Compresses after planning phase and detects:
        - Project type (Java, Python, Node, etc.)
        - Detected frameworks (Spring, Flask, React, etc.)
        - Effort estimate (1-10 scale)

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
            # Detect project metadata
            files_affected = plan.get("files_affected", [])
            project_type = self._detect_project_type(files_affected)
            detected_frameworks = self._detect_frameworks(files_affected)
            complexity_score = toon_analysis.get("complexity_score", 5)
            effort_estimate = self._calculate_effort_estimate(
                complexity_score=complexity_score,
                files_count=len(files_affected),
                framework_count=len(detected_frameworks)
            )

            logger.info(f"  Project type: {project_type}")
            logger.info(f"  Detected frameworks: {detected_frameworks}")
            logger.info(f"  Effort estimate: {effort_estimate}/10")

            # Ensure risks dict has all required fields
            risks_data = plan.get("risks", {})
            if not risks_data.get("risk_level"):
                risks_data["risk_level"] = "medium"
            if "factors" not in risks_data:
                risks_data["factors"] = []
            if "mitigation" not in risks_data:
                risks_data["mitigation"] = []

            # Ensure session_id has a fallback
            session_id = toon_analysis.get("session_id")
            if not session_id:
                from uuid import uuid4
                session_id = f"session-{uuid4().hex[:12]}"

            blueprint = {
                "session_id": session_id,
                "timestamp": datetime.now(),  # Use datetime object, not string
                "complexity_score": complexity_score,
                "plan": plan.get("plan", ""),
                "files_affected": files_affected,
                "phases": plan.get("phases", []),
                "risks": risks_data,
                "selected_skills": [],  # To be filled in Step 5
                "selected_agents": [],  # To be filled in Step 5
                "execution_strategy": "sequential",
                # New rich metadata fields
                "project_type": project_type,
                "detected_frameworks": detected_frameworks,
                "effort_estimate": effort_estimate
            }

            # Validate with Pydantic
            validated = ExecutionBlueprint(**blueprint)

            # Save to session
            self.session_manager.save_execution_blueprint(validated)

            logger.info("✓ TOON refined to ExecutionBlueprint with enriched metadata")

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

    def _detect_project_type(self, files_affected: List[str]) -> Optional[str]:
        """Detect project type from file extensions and root files.

        Returns: One of: Java, Python, Node, Go, Rust, C++, TypeScript, etc.
        """
        if not files_affected:
            return None

        # Count file type extensions
        py_count = sum(1 for f in files_affected if f.endswith('.py'))
        java_count = sum(1 for f in files_affected if f.endswith('.java'))
        js_count = sum(1 for f in files_affected if f.endswith('.js'))
        ts_count = sum(1 for f in files_affected if f.endswith('.ts'))
        go_count = sum(1 for f in files_affected if f.endswith('.go'))
        rs_count = sum(1 for f in files_affected if f.endswith('.rs'))
        cpp_count = sum(1 for f in files_affected if f.endswith(('.cpp', '.cc', '.h')))

        # Determine primary language
        type_scores = {
            'Python': py_count,
            'Java': java_count,
            'JavaScript': js_count,
            'TypeScript': ts_count,
            'Go': go_count,
            'Rust': rs_count,
            'C++': cpp_count,
        }

        detected = max(type_scores, key=type_scores.get) if max(type_scores.values()) > 0 else None
        if detected:
            logger.info(f"  Detected project type: {detected}")
        return detected

    def _detect_frameworks(self, files_affected: List[str]) -> List[str]:
        """Detect frameworks from file patterns and imports.

        Looks for common framework indicators in file paths and content.
        """
        frameworks = set()

        # Framework detection patterns
        patterns = {
            'Spring': ['spring-boot', 'pom.xml', '@SpringBootApplication'],
            'Flask': ['flask', 'requirements.txt'],
            'Django': ['django', 'manage.py'],
            'React': ['react', 'package.json', 'jsx', 'tsx'],
            'Angular': ['angular', '@angular/'],
            'Vue': ['vue', '.vue'],
            'FastAPI': ['fastapi', 'uvicorn'],
            'Express': ['express', 'node_modules'],
            'Rails': ['rails', 'Gemfile'],
            'Next.js': ['next', 'pages/', 'app/'],
            'Svelte': ['svelte', '.svelte'],
        }

        # Check file paths for framework indicators
        files_str = ' '.join(files_affected).lower()

        for framework, indicators in patterns.items():
            if any(indicator.lower() in files_str for indicator in indicators):
                frameworks.add(framework)

        if frameworks:
            logger.info(f"  Detected frameworks: {', '.join(sorted(frameworks))}")

        return sorted(list(frameworks))

    def _calculate_effort_estimate(
        self,
        complexity_score: int,
        files_count: int,
        framework_count: int
    ) -> int:
        """Calculate effort estimate (1-10) based on multiple factors.

        Formula:
        - Base: complexity_score (1-10)
        - File scale factor: +1 per 10 files (max +3)
        - Framework complexity: +1 per framework (max +2)
        - Clamped to 1-10 range

        Args:
            complexity_score: From Level 1 analysis (1-10)
            files_count: Number of files affected
            framework_count: Number of detected frameworks

        Returns:
            Effort estimate (1-10)
        """
        # Start with base complexity
        effort = float(complexity_score)

        # Add for file count (10 files = +1 effort)
        file_factor = min(files_count // 10, 3)
        effort += file_factor

        # Add for framework complexity
        framework_factor = min(framework_count, 2)
        effort += framework_factor

        # Clamp to 1-10 range
        effort = max(1, min(10, int(effort)))

        logger.debug(
            f"  Effort calculation: "
            f"base={complexity_score} + files({file_factor}) + frameworks({framework_factor}) = {effort}"
        )

        return effort

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
            # Try to download from GitHub skill library
            _gh_owner = os.environ.get("CLAUDE_GITHUB_OWNER", "techdeveloper-org")
            github_url = (
                f"https://raw.githubusercontent.com/{_gh_owner}/claude-global-library/main/"
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
*Completed by Claude Workflow Engine Level 3 Execution Pipeline*
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
                         f'[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null; [System.Windows.Forms.MessageBox]::Show("{msg}", "Claude Workflow Engine")'],
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
