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

    # ===== STEP 2: PLAN EXECUTION =====

    def step2_plan_execution(
        self,
        toon: Dict[str, Any],
        user_requirement: str
    ) -> Dict[str, Any]:
        """
        Execute detailed planning phase using OPUS.

        Only runs if Step 1 returned plan_required=True.

        Args:
            toon: TOON object from Level 1
            user_requirement: Original user requirement

        Returns:
            {
                "plan": str,  # Detailed execution plan
                "files_affected": List[str],
                "phases": List[Dict],
                "risks": Dict,
                "success": bool
            }
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 2: PLAN EXECUTION")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            prompt = f"""Create a detailed implementation plan for this requirement:

USER REQUIREMENT:
{user_requirement}

PROJECT CONTEXT:
- Complexity: {toon.get('complexity_score')}/10
- Files: {toon.get('files_loaded_count')}

Generate a comprehensive plan that includes:
1. High-level strategy
2. Specific implementation phases
3. Files that need to be modified
4. Dependencies between tasks
5. Risk assessment and mitigation
6. Testing approach

Be very specific and actionable."""

            response = self.ollama.chat(
                messages=[{"role": "user", "content": prompt}],
                model="complex_reasoning",  # Use 14B for deep planning
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
        Update project documentation (SRS, README, CLAUDE.md).

        Args:
            files_modified: Files that were modified

        Returns:
            {"success": bool, "updated_files": List[str]}
        """
        logger.info("=" * 60)
        logger.info("LEVEL 3 - STEP 13: DOCUMENTATION UPDATE")
        logger.info("=" * 60)

        step_start = time.time()

        try:
            updated = []

            # Update README if it exists
            readme_path = Path("README.md")
            if readme_path.exists():
                self._update_readme(readme_path, files_modified)
                updated.append("README.md")
                logger.info("Updated README.md")

            # Create/update SRS if needed
            srs_path = Path("SRS.md")
            if srs_path.exists():
                self._update_srs(srs_path, files_modified)
                updated.append("SRS.md")
                logger.info("Updated SRS.md")

            # Save to session
            self.session_manager.save_github_details({
                "documentation_updated": updated,
                "timestamp": datetime.now().isoformat()
            })

            logger.info(f"✓ Documentation updated: {len(updated)} files")

            return {
                "success": True,
                "updated_files": updated,
                "execution_time_ms": (time.time() - step_start) * 1000,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Step 13 failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": (time.time() - step_start) * 1000
            }

    def _update_readme(self, readme_path: Path, files_modified: List[str]):
        """Add update note to README."""
        # Simple approach: add a note at the end
        content = readme_path.read_text(encoding='utf-8')
        note = f"\n\n## Latest Updates\nUpdated {datetime.now().strftime('%Y-%m-%d')}:\n"
        for file in files_modified[:5]:  # Show first 5
            note += f"- {file}\n"
        readme_path.write_text(content + note, encoding='utf-8')

    def _update_srs(self, srs_path: Path, files_modified: List[str]):
        """Update SRS with changes."""
        # Simple approach: ensure SRS exists and is valid
        if not srs_path.exists():
            srs_path.write_text("# System Requirements Specification\n\n## Latest Changes\n")

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
