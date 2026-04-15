"""Step 12/13/14 implementation functions.

Facade module: wraps Level3GitHubWorkflow (Step 12 issue closure),
Level3DocumentationManager (Step 13 docs update), and Step 14 summary
generation behind thin, state-dict-first functions that the step wrappers
in step_wrappers_12_14.py invoke.

Restored 2026-04-14 during v1.16.x restoration cycle (issue #213),
adapted for:
  - v1.11 physical layout (nodes/ package)
  - loguru-with-stdlib-fallback logger import pattern (matches sibling nodes)
  - UML_OUTPUT_DIR / DRAWIO_OUTPUT_DIR env vars (v1.16.1)

Design patterns:
  - Facade: thin wrapper over Level3GitHubWorkflow + Level3DocumentationManager
  - Null Object: returns well-formed ERROR-status dict on failure (never None, never raises)
  - Defensive Import: every external import wrapped in try/except

Windows-safe: ASCII only.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

try:
    from ...flow_state import FlowState
except ImportError:
    FlowState = dict  # type: ignore[misc,assignment]

try:
    from ..steps8to12_github import Level3GitHubWorkflow
except ImportError:  # pragma: no cover
    Level3GitHubWorkflow = None  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Step 12: Issue Closure
# ---------------------------------------------------------------------------


def step12_issue_closure(state: FlowState) -> Dict[str, Any]:
    """Step 12: Close GitHub issue after implementation.

    Skips when no issue was created (issue_id == 0).  Falls back gracefully
    when GitHub API is unreachable.  Post-merge branch cleanup is attempted
    best-effort after a successful close.

    Returns step12_* keys including issue_closed, closing_comment, and status.
    """
    try:
        # Skip if no real issue exists
        if not state.get("step8_issue_created", False) or state.get("step8_issue_id", "0") == "0":
            logger.info("Step 12: Skipping issue closure -- no issue was created")
            return {
                "step12_issue_closed": False,
                "step12_closing_comment": "",
                "step12_status": "SKIPPED",
            }

        issue_id = state.get("step8_issue_id", "0")
        pr_id = state.get("step11_pr_id", "0")
        pr_url = state.get("step11_pr_url", "")
        review_passed = state.get("step11_review_passed", False)
        modified_files = state.get("step10_modified_files", [])
        session_path = state.get("session_dir") or os.environ.get("CLAUDE_SESSION_PATH", ".")
        project_root = state.get("project_root", ".")

        task_type = state.get("step0_task_type", "Task")
        skill = state.get("step5_skill", "")
        approach = "%s execution" % task_type
        if skill:
            approach += " using %s" % skill

        if Level3GitHubWorkflow is not None:
            try:
                workflow = Level3GitHubWorkflow(session_dir=session_path, repo_path=project_root)
                result = workflow.step12_close_issue(
                    issue_number=int(issue_id) if issue_id.isdigit() else 0,
                    pr_number=int(pr_id) if pr_id.isdigit() else 0,
                    files_modified=modified_files,
                    approach_taken=approach,
                    verification_steps=[
                        "Code review passed" if review_passed else "Code review pending",
                        ("PR: %s" % pr_url) if pr_url else "PR not created",
                    ],
                )
                if result.get("success"):
                    # Post-merge cleanup (best-effort)
                    branch_name = state.get("step9_branch_name", "")
                    if branch_name and state.get("step11_merged", False):
                        try:
                            cleanup = workflow.git.post_merge_cleanup(branch_name)
                            if cleanup.get("success"):
                                logger.info("Post-merge cleanup: %s", cleanup.get("message"))
                            else:
                                logger.warning("Post-merge cleanup issue: %s", cleanup.get("error"))
                        except Exception as cleanup_err:
                            logger.warning("Post-merge cleanup skipped: %s", cleanup_err)

                    return {
                        "step12_issue_closed": True,
                        "step12_closing_comment": "Issue #%s closed via PR #%s" % (issue_id, pr_id),
                        "step12_status": "OK",
                    }
                else:
                    logger.warning("Issue closure failed: %s. Using fallback.", result.get("error"))
            except Exception as gh_err:
                logger.warning("Level3GitHubWorkflow unavailable for closure: %s. Using fallback.", gh_err)

        # Fallback
        closing_comment = (
            "## Implementation Complete\n\n"
            "PR: %s\n"
            "Status: %s\n\n"
            "See PR for details." % (pr_url, "Passed" if review_passed else "Needs Work")
        )
        return {
            "step12_issue_closed": False,
            "step12_closing_comment": closing_comment,
            "step12_status": "FALLBACK",
        }

    except Exception as e:
        return {"step12_issue_closed": False, "step12_status": "ERROR", "step12_error": str(e)}


# ---------------------------------------------------------------------------
# Step 13: Project Documentation Update
# ---------------------------------------------------------------------------


def step13_project_documentation_update(state: FlowState) -> Dict[str, Any]:
    """Step 13: Create or update project documentation.

    Circular SDLC cycle: Step 0 reads docs, Step 13 writes/updates them.
    - Fresh projects: creates SRS, README, CLAUDE.md, CHANGELOG via
      Level3DocumentationManager.create_all_docs()
    - Existing projects: smart per-file updates via update_existing_docs()
    - UML diagram generation is best-effort (non-blocking).

    Returns step13_* keys including updates_prepared, updated_files, and status.
    """
    try:
        from ..documentation_manager import Level3DocumentationManager

        manager = Level3DocumentationManager(
            project_root=state.get("project_root", "."),
            session_dir=state.get("session_dir", "") or state.get("session_path", ""),
        )

        is_fresh = state.get("is_fresh_project", False)

        if is_fresh:
            result = manager.create_all_docs(dict(state))
        else:
            result = manager.update_existing_docs(dict(state))

        # UML diagram generation (best-effort, non-blocking)
        uml_diagrams_generated = []
        try:
            from ...uml_generators import UmlGenerators

            # Respect UML_OUTPUT_DIR env var (v1.16.1)
            uml_output_dir = os.environ.get(
                "UML_OUTPUT_DIR",
                str(Path(state.get("project_root", ".")) / "uml"),
            )
            uml_gen = UmlGenerators(
                project_root=state.get("project_root", "."),
                output_dir=uml_output_dir,
            )
            for diagram_type in ["class", "component", "sequence"]:
                try:
                    uml_gen.generate(diagram_type)
                    uml_diagrams_generated.append(diagram_type)
                except Exception:
                    pass  # Individual diagram failures are non-blocking
        except ImportError:
            pass
        except Exception:
            pass

        # Write session-dir audit file (non-critical)
        session_path = state.get("session_dir") or state.get("session_path", "")
        if session_path:
            try:
                import datetime as _dt

                doc_file = Path(session_path) / "execution-docs.md"
                task_type = state.get("step0_task_type", "Unknown")
                complexity = state.get("step0_complexity", 5)
                content = (
                    "# Execution Documentation\n\n"
                    "**Generated**: %s\n\n"
                    "- Task Type: %s\n"
                    "- Complexity: %d/10\n"
                    "- Documentation Status: %s\n"
                    "- Files Updated: %s\n"
                    % (
                        _dt.datetime.now().isoformat(),
                        task_type,
                        complexity,
                        result.get("step13_documentation_status", "OK"),
                        ", ".join(result.get("step13_updated_files", [])),
                    )
                )
                doc_file.write_text(content, encoding="utf-8")
            except Exception:
                pass

        return {
            "step13_updates_prepared": True,
            "step13_update_count": len(result.get("step13_updated_files", [])),
            "step13_updated_files": result.get("step13_updated_files", []),
            "step13_documentation_status": result.get("step13_documentation_status", "OK"),
            "step13_docs_created": result.get("step13_docs_created", []),
            "step13_uml_diagrams": uml_diagrams_generated,
        }

    except Exception as e:
        return {
            "step13_updates_prepared": False,
            "step13_documentation_status": "ERROR",
            "step13_error": str(e),
        }


# ---------------------------------------------------------------------------
# Step 14: Final Summary Generation
# ---------------------------------------------------------------------------


def _build_summary_text(summary: dict, state: FlowState) -> str:
    """Build human-readable summary text for saving to the session directory."""
    import datetime as _dt

    lines = [
        "=" * 60,
        "  PIPELINE EXECUTION SUMMARY",
        "=" * 60,
        "  Date:       %s" % _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "  Session:    %s" % state.get("session_id", "unknown"),
        "  Project:    %s" % state.get("project_root", "."),
        "  Framework:  %s" % state.get("detected_framework", "unknown"),
        "",
        "  Task Type:  %s" % summary.get("task_type", "Unknown"),
        "  Complexity: %s/10" % summary.get("complexity", "?"),
        "  Plan Used:  %s" % ("Yes" if summary.get("plan_used") else "No"),
        "",
    ]

    skill = summary.get("skill_selected", "")
    agent = summary.get("agent_selected", "")
    if skill or agent:
        lines.append("  Resources:")
        if skill:
            lines.append("    Skill: %s" % skill)
        if agent:
            lines.append("    Agent: %s" % agent)
        lines.append("")

    if summary.get("issue_created"):
        lines.append("  Issue:  %s" % summary.get("issue_url", "created"))
    if summary.get("pr_url"):
        lines.append("  PR:     %s" % summary.get("pr_url"))
        lines.append("  Merged: %s" % ("Yes" if summary.get("pr_merged") else "No"))
    lines.append("")

    modified = summary.get("modified_files_list", [])
    if modified:
        lines.append("  Files Modified (%d):" % len(modified))
        for f in modified[:10]:
            lines.append("    - %s" % f)
        if len(modified) > 10:
            lines.append("    ... and %d more" % (len(modified) - 10))
    else:
        lines.append("  Files Modified: 0")

    lines += ["", "  Status: %s" % summary.get("status", "UNKNOWN"), "=" * 60]
    return "\n".join(lines)


def step14_final_summary_generation(state: FlowState) -> Dict[str, Any]:
    """Step 14: Generate and persist the pipeline execution summary.

    1. Builds a summary dict from all prior step state keys.
    2. Saves execution-summary.txt to the session directory (always).
    3. Attempts voice notification via voice-notifier.py (best-effort).

    Returns step14_* keys including summary, summary_saved, voice_sent, and status.
    """
    import datetime as _dt
    import subprocess

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
            "timestamp": _dt.datetime.now().isoformat(),
        }

        # Save summary to session directory (always)
        session_dir = state.get("session_dir") or state.get("session_path", "")
        summary_text = _build_summary_text(summary, state)
        summary_saved = False

        if session_dir:
            try:
                summary_file = Path(session_dir) / "execution-summary.txt"
                summary_file.write_text(summary_text, encoding="utf-8")
                summary_saved = True
                logger.info("Summary saved to %s", summary_file)
            except Exception as save_err:
                logger.warning("Could not save summary: %s", save_err)

        # Voice notification (best-effort)
        voice_sent = False
        voice_msg = "Pipeline complete. %s task, complexity %d." % (task_type, complexity)
        if skill:
            voice_msg += " Using %s." % skill
        if issue_created:
            voice_msg += " Issue created."
        if pr_merged:
            voice_msg += " PR merged."
        if modified_files:
            voice_msg += " %d files modified." % len(modified_files)

        try:
            # voice-notifier.py lives in scripts/tools/ relative to project root
            voice_script = (
                Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "tools" / "voice-notifier.py"
            )
            if voice_script.exists():
                result = subprocess.run(
                    [sys.executable, str(voice_script), voice_msg],
                    timeout=60,
                    capture_output=True,
                )
                voice_sent = result.returncode == 0
                if not voice_sent:
                    logger.debug("Voice exited with code %d", result.returncode)
        except subprocess.TimeoutExpired:
            logger.debug("Voice notification timed out (60s)")
        except Exception as voice_err:
            logger.debug("Voice notification skipped: %s", voice_err)

        # Runtime verification report (non-blocking, best-effort)
        verification_report = None
        verification_violations = []
        if os.getenv("ENABLE_RUNTIME_VERIFICATION", "0") == "1":
            try:
                from ....runtime_verification.verifier import RuntimeVerifier

                verifier = RuntimeVerifier.get_instance()
                report = verifier.build_report()
                if report is not None:
                    verification_report = report.to_dict()
                    verification_violations = [v["message"] for v in report.violations]
                    logger.info("[RuntimeVerifier] Report built: %d violations", len(verification_violations))
            except Exception as rv_err:
                logger.warning("[RuntimeVerifier] build_report skipped: %s", rv_err)

        result = {
            "step14_summary": summary,
            "step14_summary_saved": summary_saved,
            "step14_voice_sent": voice_sent,
            "step14_status": "OK",
        }
        if verification_report is not None:
            result["verification_report"] = verification_report
            result["verification_violations"] = verification_violations
        return result

    except Exception as e:
        return {"step14_status": "ERROR", "step14_error": str(e)}
