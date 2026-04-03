"""
Level 3 Execution - Step 14: Final Summary Generation
"""

import sys
from pathlib import Path

from loguru import logger

from ....flow_state import FlowState


def _build_summary_text(summary: dict, state) -> str:
    """Build human-readable summary text for saving to file."""
    from datetime import datetime

    lines = []
    lines.append("=" * 60)
    lines.append("  PIPELINE EXECUTION SUMMARY")
    lines.append("=" * 60)
    lines.append(f"  Date:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"  Session:    {state.get('session_id', 'unknown')}")
    lines.append(f"  Project:    {state.get('project_root', '.')}")
    lines.append(f"  Framework:  {state.get('detected_framework', 'unknown')}")
    lines.append("")
    lines.append(f"  Task Type:  {summary.get('task_type', 'Unknown')}")
    lines.append(f"  Complexity: {summary.get('complexity', '?')}/10")
    lines.append(f"  Plan Used:  {'Yes' if summary.get('plan_used') else 'No'}")
    lines.append("")

    skill = summary.get("skill_selected", "")
    agent = summary.get("agent_selected", "")
    if skill or agent:
        lines.append("  Resources:")
        if skill:
            lines.append(f"    Skill: {skill}")
        if agent:
            lines.append(f"    Agent: {agent}")
        lines.append("")

    if summary.get("issue_created"):
        lines.append(f"  Issue:  {summary.get('issue_url', 'created')}")
    if summary.get("pr_url"):
        lines.append(f"  PR:     {summary.get('pr_url')}")
        lines.append(f"  Merged: {'Yes' if summary.get('pr_merged') else 'No'}")
    lines.append("")

    modified = summary.get("modified_files_list", [])
    if modified:
        lines.append(f"  Files Modified ({len(modified)}):")
        for f in modified[:10]:
            lines.append(f"    - {f}")
        if len(modified) > 10:
            lines.append(f"    ... and {len(modified) - 10} more")
    else:
        lines.append("  Files Modified: 0")

    lines.append("")
    lines.append(f"  Status: {summary.get('status', 'UNKNOWN')}")
    lines.append("=" * 60)

    return "\n".join(lines)


def step14_final_summary_generation(state: FlowState) -> dict:
    """Step 14: Final Summary Generation - Generate execution summary.

    1. Build summary dict from all steps
    2. ALWAYS save summary to session folder (execution-summary.txt)
    3. Attempt voice notification (best-effort, never blocks)
    """
    from datetime import datetime

    try:
        task_type = state.get("step0_task_type", "Unknown")
        complexity = state.get("step0_complexity", 5)
        skill = state.get("step5_skill", "")
        agent = state.get("step5_agent", "")
        issue_created = state.get("step8_issue_created", False)
        issue_url = state.get("step8_issue_url", "")
        pr_url = state.get("step11_pr_url", "")
        pr_merged = state.get("step11_merged", False)
        modified_files = state.get("step10_modified_files", [])
        plan_used = state.get("step1_plan_required", False)

        summary = {
            "task_type": task_type,
            "complexity": complexity,
            "plan_used": plan_used,
            "skill_selected": skill,
            "agent_selected": agent,
            "issue_created": issue_created,
            "issue_url": issue_url,
            "pr_url": pr_url,
            "pr_merged": pr_merged,
            "files_modified": len(modified_files),
            "modified_files_list": modified_files[:20],
            "status": "COMPLETED",
            "timestamp": datetime.now().isoformat(),
        }

        # ================================================================
        # ALWAYS save summary to session folder (even if voice fails)
        # ================================================================
        session_dir = state.get("session_dir") or state.get("session_path", "")
        summary_text = _build_summary_text(summary, state)
        summary_saved = False

        if session_dir:
            try:
                summary_file = Path(session_dir) / "execution-summary.txt"
                summary_file.write_text(summary_text, encoding="utf-8")
                summary_saved = True
                logger.info(f"Summary saved to {summary_file}")
            except Exception as save_err:
                logger.warning(f"Could not save summary: {save_err}")

        # ================================================================
        # Voice notification (best-effort, generous timeout)
        # ================================================================
        import subprocess

        voice_sent = False
        voice_msg = f"Pipeline complete. {task_type} task, complexity {complexity}."
        if skill:
            voice_msg += f" Using {skill}."
        if issue_created:
            voice_msg += " Issue created."
        if pr_merged:
            voice_msg += " PR merged."
        if modified_files:
            voice_msg += f" {len(modified_files)} files modified."

        try:
            voice_script = Path(__file__).parent.parent.parent.parent.parent / "voice-notifier.py"
            if voice_script.exists():
                result = subprocess.run(
                    [sys.executable, str(voice_script), voice_msg],
                    timeout=60,  # generous: Coqui TTS needs time for model load + generation
                    capture_output=True,
                )
                voice_sent = result.returncode == 0
                if not voice_sent:
                    logger.debug(f"Voice exited with code {result.returncode}")
        except subprocess.TimeoutExpired:
            logger.debug("Voice notification timed out (60s)")
        except Exception as voice_err:
            logger.debug(f"Voice notification skipped: {voice_err}")

        return {
            "step14_summary": summary,
            "step14_summary_saved": summary_saved,
            "step14_voice_sent": voice_sent,
            "step14_status": "OK",
        }

    except Exception as e:
        return {"step14_status": "ERROR", "step14_error": str(e)}
