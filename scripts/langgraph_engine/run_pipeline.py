"""
Pipeline CLI Entry Point

Supports starting new executions and resuming interrupted ones from checkpoints.

Usage:
    # Start a new execution
    python -m scripts.langgraph_engine.run_pipeline run \
        --message "Implement feature X" \
        --project .

    # Resume from the last checkpoint of a session
    python -m scripts.langgraph_engine.run_pipeline resume \
        --session flow-abc12345

    # Resume from a specific checkpoint
    python -m scripts.langgraph_engine.run_pipeline resume \
        --session flow-abc12345 \
        --checkpoint flow-abc12345:step-05

    # List checkpoints for a session
    python -m scripts.langgraph_engine.run_pipeline list \
        --session flow-abc12345

    # Short form: --resume flag (matches acceptance criteria)
    python -m scripts.langgraph_engine.run_pipeline --resume flow-abc12345:step-05

All code uses UTF-8 encoding and ASCII-safe practices.
"""

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path for standalone execution
# ---------------------------------------------------------------------------
_here = Path(__file__).parent
_project_root = _here.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def cmd_run(args: argparse.Namespace) -> int:
    """Start a new pipeline execution."""
    try:
        from scripts.langgraph_engine.orchestrator import invoke_flow

        session_id = args.session or ""
        project_root = args.project or "."
        user_message = args.message or ""

        if not user_message:
            print("Error: --message is required for 'run' command", file=sys.stderr)
            return 1

        print(f"Starting pipeline for session: {session_id or '(auto)'}", file=sys.stderr)
        print(f"Project root: {project_root}", file=sys.stderr)
        print(f"Message: {user_message[:80]}...", file=sys.stderr)

        result = invoke_flow(
            session_id=session_id,
            project_root=project_root,
            user_message=user_message,
        )

        final_status = result.get("final_status", "UNKNOWN") if result else "FAILED"
        session_out = result.get("session_id", "unknown") if result else "unknown"
        print(f"Pipeline completed. Status={final_status}, session={session_out}", file=sys.stderr)
        return 0 if final_status in ("OK", "PARTIAL") else 1

    except KeyboardInterrupt:
        print("\n[Interrupted] Pipeline stopped by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"[Error] Pipeline failed: {e}", file=sys.stderr)
        return 1


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume a pipeline from a checkpoint."""
    try:
        session_id = args.session or ""
        checkpoint_id = args.checkpoint or None

        if not session_id and not checkpoint_id:
            print(
                "Error: --session is required for 'resume' command "
                "(optionally --checkpoint)",
                file=sys.stderr
            )
            return 1

        # If checkpoint_id is provided but no session, extract session from checkpoint_id
        if not session_id and checkpoint_id and ":" in checkpoint_id:
            session_id = checkpoint_id.split(":")[0]
            print(f"[Resume] Extracted session_id from checkpoint: {session_id}", file=sys.stderr)

        from scripts.langgraph_engine.recovery_handler import resume_from_checkpoint

        print(f"[Resume] Session: {session_id}", file=sys.stderr)
        if checkpoint_id:
            print(f"[Resume] Checkpoint: {checkpoint_id}", file=sys.stderr)

        success = resume_from_checkpoint(
            session_id=session_id,
            step_executor=None,
            checkpoint_id=checkpoint_id,
        )

        if success:
            print("[Resume] Pipeline resumed and completed successfully.", file=sys.stderr)
            return 0
        else:
            print("[Resume] Pipeline resume failed or no checkpoint found.", file=sys.stderr)
            return 1

    except KeyboardInterrupt:
        print("\n[Interrupted] Resume stopped by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"[Error] Resume failed: {e}", file=sys.stderr)
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """List checkpoints for a session."""
    session_id = args.session or ""
    if not session_id:
        print("Error: --session is required for 'list' command", file=sys.stderr)
        return 1

    try:
        from scripts.langgraph_engine.checkpoint_manager import CheckpointManager

        mgr = CheckpointManager(session_id)
        checkpoints = mgr.list_checkpoints()

        if not checkpoints:
            print(f"No checkpoints found for session: {session_id}")
            return 0

        print(f"\nCheckpoints for session: {session_id}")
        print("-" * 72)
        for cp in checkpoints:
            status_str = "OK    " if cp.get("success_status", True) else "FAILED"
            err = cp.get("error_message") or ""
            err_suffix = f" | {err[:50]}" if err else ""
            print(
                f"  Step {cp['step']:02d}  {status_str}  "
                f"{cp['timestamp']}  id={cp['checkpoint_id']}{err_suffix}"
            )

        print()
        print(f"To resume from the last checkpoint:")
        print(f"  python -m scripts.langgraph_engine.run_pipeline resume --session {session_id}")
        if checkpoints:
            last = checkpoints[-1]
            print(f"To resume from a specific step:")
            print(
                f"  python -m scripts.langgraph_engine.run_pipeline resume "
                f"--session {session_id} --checkpoint {last['checkpoint_id']}"
            )
        return 0

    except Exception as e:
        print(f"[Error] Failed to list checkpoints: {e}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser supporting both subcommands and --resume flag."""
    parser = argparse.ArgumentParser(
        prog="run_pipeline",
        description="Claude Insight Level 3 Pipeline Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Top-level --resume flag for acceptance criteria compliance:
    # python run_pipeline.py --resume {checkpoint_id}
    parser.add_argument(
        "--resume",
        metavar="CHECKPOINT_ID",
        help="Resume execution from the specified checkpoint ID "
             "(e.g. flow-abc12345:step-05)",
    )

    subparsers = parser.add_subparsers(dest="command")

    # ---------- run subcommand ----------
    run_parser = subparsers.add_parser("run", help="Start a new pipeline execution")
    run_parser.add_argument(
        "--message", "-m",
        required=False,
        help="User task/request message",
    )
    run_parser.add_argument(
        "--project", "-p",
        default=".",
        help="Project root directory (default: current directory)",
    )
    run_parser.add_argument(
        "--session", "-s",
        default="",
        help="Session ID (auto-generated if not provided)",
    )

    # ---------- resume subcommand ----------
    resume_parser = subparsers.add_parser("resume", help="Resume from a checkpoint")
    resume_parser.add_argument(
        "--session", "-s",
        required=False,
        help="Session ID to resume",
    )
    resume_parser.add_argument(
        "--checkpoint", "-c",
        required=False,
        help="Specific checkpoint ID (e.g. flow-abc12345:step-05). "
             "Defaults to last checkpoint.",
    )

    # ---------- list subcommand ----------
    list_parser = subparsers.add_parser("list", help="List checkpoints for a session")
    list_parser.add_argument(
        "--session", "-s",
        required=True,
        help="Session ID",
    )

    return parser


def main() -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Handle --resume flag (top-level shorthand)
    if args.resume:
        checkpoint_id = args.resume
        # Extract session from checkpoint_id if possible
        if ":" in checkpoint_id:
            session_id = checkpoint_id.split(":")[0]
        else:
            session_id = checkpoint_id

        # Mimic resume subcommand
        args.session = session_id
        args.checkpoint = checkpoint_id if ":" in checkpoint_id else None
        return cmd_resume(args)

    # Handle subcommands
    if args.command == "run":
        return cmd_run(args)
    elif args.command == "resume":
        return cmd_resume(args)
    elif args.command == "list":
        return cmd_list(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
