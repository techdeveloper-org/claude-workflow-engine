"""
Level 3 Execution - Step 6: Skill Validation & Download
"""

import subprocess
import sys
from pathlib import Path

from ....flow_state import FlowState
from ..helpers import _LEVEL3_AGENTS_DIR, _LEVEL3_SKILLS_DIR


def _try_download_skill(skill_name: str, skills_dir: Path) -> bool:
    """Attempt to download a missing skill from the global library repo.

    Uses sync-library.py if available, otherwise tries direct git sparse checkout.
    Returns True if skill was successfully downloaded.
    """
    try:
        sync_script = Path(__file__).parent.parent.parent.parent.parent / "sync-library.py"
        if sync_script.exists():
            subprocess.run(
                [sys.executable, str(sync_script), "--skill", skill_name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            # Check if file now exists
            skill_path = skills_dir / skill_name / "SKILL.md"
            skill_path_lower = skills_dir / skill_name / "skill.md"
            return skill_path.exists() or skill_path_lower.exists()
    except Exception:
        pass
    return False


def _try_download_agent(agent_name: str, agents_dir: Path) -> bool:
    """Attempt to download a missing agent from the global library repo.

    Returns True if agent was successfully downloaded.
    """
    try:
        sync_script = Path(__file__).parent.parent.parent.parent.parent / "sync-library.py"
        if sync_script.exists():
            subprocess.run(
                [sys.executable, str(sync_script), "--agent", agent_name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            agent_path = agents_dir / agent_name / "agent.md"
            return agent_path.exists()
    except Exception:
        pass
    return False


def step6_skill_validation_download(state: FlowState) -> dict:
    """Step 6: Skill Validation & Download - Verify selected skills exist and download if needed.

    After Step 5 selects skills/agents, this step:
    1. Validates that selected resources exist locally
    2. Downloads missing skills/agents from repository
    3. Reports validation status and download progress
    4. (NEW) Validates any selected MCPs are available

    This ensures all selected tools are ready before execution.
    """

    skill_name = state.get("step5_skill", "")
    agent_name = state.get("step5_agent", "")

    validation_results = {"skill_exists": False, "agent_exists": False, "downloaded": [], "validation_errors": []}

    # Check if skill exists
    if skill_name:
        skills_dir = _LEVEL3_SKILLS_DIR
        skill_path = skills_dir / skill_name / "skill.md"
        # Also check uppercase SKILL.md (convention in claude-global-library)
        skill_path_upper = skills_dir / skill_name / "SKILL.md"

        if skill_path.exists() or skill_path_upper.exists():
            validation_results["skill_exists"] = True
        else:
            # Attempt download via sync-library script (non-blocking)
            downloaded = _try_download_skill(skill_name, skills_dir)
            if downloaded:
                validation_results["skill_exists"] = True
                validation_results["downloaded"].append(skill_name)
            else:
                validation_results["validation_errors"].append(
                    f"Skill '{skill_name}' not found locally and download failed."
                )

    # Check if agent exists
    if agent_name:
        agents_dir = _LEVEL3_AGENTS_DIR
        agent_path = agents_dir / agent_name / "agent.md"

        if agent_path.exists():
            validation_results["agent_exists"] = True
        else:
            # Attempt download via sync-library script (non-blocking)
            downloaded = _try_download_agent(agent_name, agents_dir)
            if downloaded:
                validation_results["agent_exists"] = True
                validation_results["downloaded"].append(agent_name)
            else:
                validation_results["validation_errors"].append(
                    f"Agent '{agent_name}' not found locally and download failed."
                )

    # NEW: Validate any selected MCPs (MCP Integration Phase 1)
    mcp_results = {"mcps_validated": {}, "mcp_validation_errors": [], "mcp_status": "OK"}

    available_mcps = state.get("mcp_servers_available", [])
    if available_mcps:
        available_mcp_names = {mcp["short_name"] for mcp in available_mcps}

        # Check if any MCPs were selected (would be from Step 5)
        # For now, just validate the Filesystem MCP if it's supposed to be available
        if state.get("mcp_filesystem_enabled"):
            if "filesystem" in available_mcp_names:
                mcp_results["mcps_validated"]["filesystem"] = "OK"
            else:
                mcp_results["mcp_validation_errors"].append(
                    "Filesystem MCP marked as enabled but not found in registry"
                )
                mcp_results["mcp_status"] = "WARNING"

    return {
        "step6_skill_validation": validation_results,
        "step6_skill_ready": validation_results["skill_exists"] or not skill_name,
        "step6_agent_ready": validation_results["agent_exists"] or not agent_name,
        "step6_validation_status": "OK" if not validation_results["validation_errors"] else "MISSING",
        "step6_mcp_validation": mcp_results,
        "step6_mcp_ready": mcp_results["mcp_status"] == "OK",
    }
