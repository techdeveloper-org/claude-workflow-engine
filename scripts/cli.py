"""
Claude Workflow Engine CLI.

Usage:
  cwe run "fix the login bug"              # Run the pipeline on a task
  cwe run --task "add feature" --mode full  # Full mode (all 15 steps)
  cwe setup                                 # Interactive first-time setup
  cwe status                                # Show current pipeline state
  cwe health                                # Check all dependencies and MCP servers
  cwe version                              # Show version
  cwe doctor                               # Diagnose common issues

Version: 1.4.1
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def get_version():
    """Read version from VERSION file."""
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return "unknown"


def cmd_run(args):
    """Run the pipeline on a task.

    Delegates to 3-level-flow.py with proper environment setup.
    The existing script accepts --message=MSG for the task text.
    """
    task = args.task or (" ".join(args.task_words) if args.task_words else "")
    if not task:
        print('Error: No task provided. Usage: cwe run "fix the bug"')
        sys.exit(1)

    mode = "0" if args.mode == "full" else "1"

    env = os.environ.copy()
    env["CLAUDE_HOOK_MODE"] = mode
    if args.debug:
        env["CLAUDE_DEBUG"] = "1"
    if args.dry_run:
        env["CLAUDE_DRY_RUN"] = "1"

    flow_script = Path(__file__).resolve().parent / "3-level-flow.py"
    if not flow_script.exists():
        print(f"Error: Pipeline script not found at {flow_script}")
        print("Ensure you are running from the claude-workflow-engine directory.")
        sys.exit(1)

    # Build command: 3-level-flow.py uses --message=MSG format
    cmd = [sys.executable, str(flow_script), f"--message={task}"]
    if args.summary:
        cmd.append("--summary")
    if args.dry_run:
        cmd.append("--dry-run")

    print(f"Running pipeline ({args.mode} mode): {task[:80]}...")
    result = subprocess.run(cmd, env=env)
    sys.exit(result.returncode)


def cmd_status(args):
    """Show current pipeline status.

    Reads the latest session and flow-trace to show state.
    """
    logs_dir = Path.home() / ".claude" / "logs" / "sessions"
    if not logs_dir.exists():
        print("No pipeline sessions found.")
        return

    sessions = sorted(
        (p for p in logs_dir.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not sessions:
        print("No sessions found.")
        return

    latest = sessions[0]
    print(f"Latest session: {latest.name}")

    flow_trace = latest / "flow-trace.json"
    if flow_trace.exists():
        try:
            data = json.loads(flow_trace.read_text(encoding="utf-8"))
            print(f"  Steps completed: {len(data.get('steps', []))}")
            print(f"  Status: {data.get('status', 'unknown')}")
            if data.get("task_type"):
                print(f"  Task type: {data['task_type']}")
        except Exception:
            print("  (flow-trace unreadable)")

    session_file = latest / "session.json"
    if session_file.exists():
        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
            _meta = data.get("metadata", {})
            print(f"  Session ID: {_meta.get('session_id', data.get('session_id', 'unknown'))}")
            print(f"  Created: {_meta.get('created_at', data.get('created_at', 'unknown'))}")
        except Exception:
            pass


def cmd_health(args):
    """Check all dependencies and services.

    Verifies: Python version, required packages, GitHub CLI,
    LLM provider configuration, and required environment variables.
    """
    print("Claude Workflow Engine - Health Check")
    print("=" * 50)

    checks = []

    # Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 8)
    checks.append(("Python >= 3.8", py_ver, ok))

    # Required packages
    for pkg in ["langgraph", "langchain_core", "mcp"]:
        try:
            __import__(pkg)
            checks.append((f"Package: {pkg}", "installed", True))
        except ImportError:
            checks.append((f"Package: {pkg}", "missing", False))

    # GitHub CLI
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ver = result.stdout.strip().split("\n")[0] if result.returncode == 0 else "not found"
        checks.append(("GitHub CLI (gh)", ver, result.returncode == 0))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        checks.append(("GitHub CLI (gh)", "not installed", False))

    # LLM provider: claude CLI
    import shutil

    claude_path = shutil.which("claude")
    if claude_path:
        checks.append(("LLM: claude_cli", f"found ({claude_path})", True))
    else:
        checks.append(("LLM: claude_cli", "not on PATH (optional)", False))

    # Environment variables
    for var, required in [
        ("GITHUB_TOKEN", True),
        ("ANTHROPIC_API_KEY", True),
        ("JIRA_URL", False),
        ("JENKINS_URL", False),
    ]:
        val = os.environ.get(var, "")
        if val:
            masked = val[:4] + "..." + val[-4:] if len(val) > 10 else "set"
            checks.append((f"Env: {var}", masked, True))
        else:
            suffix = " (required)" if required else " (optional)"
            checks.append((f"Env: {var}", "not set" + suffix, not required))

    # .env file
    env_file = Path(__file__).resolve().parent.parent / ".env"
    checks.append(
        (
            ".env file",
            "exists" if env_file.exists() else "missing (copy from .env.example)",
            env_file.exists(),
        )
    )

    # Print results
    passed = 0
    failed = 0
    for name, value, ok in checks:
        status = "[OK]" if ok else "[!!]"
        print(f"  {status} {name}: {value}")
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n  {passed} passed, {failed} issues")
    if failed > 0:
        print("  Run 'cwe setup' to fix configuration issues.")


def cmd_version(args):
    """Show version information."""
    ver = get_version()
    print(f"Claude Workflow Engine v{ver}")
    print(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print(f"Platform: {sys.platform}")


def cmd_doctor(args):
    """Diagnose common issues.

    Checks for: MCP server registrations, stale sessions, and
    non-ASCII characters in Python source files (Windows cp1252 risk).
    """
    print("Claude Workflow Engine - Doctor")
    print("=" * 50)

    issues = []

    # Check settings.json for MCP registrations
    settings_file = Path.home() / ".claude" / "settings.json"
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            mcp_servers = settings.get("mcpServers", {})
            registered = len(mcp_servers)
            print(f"  MCP servers registered: {registered}")
            if registered < 12:
                issues.append(
                    f"Only {registered} MCP servers registered (expected 12+). " "Run 'cwe setup' to register all."
                )
        except Exception as exc:
            issues.append(f"Cannot read settings.json: {exc}")
    else:
        issues.append("~/.claude/settings.json not found. Run 'cwe setup'.")

    # Check for stale sessions (older than 7 days)
    sessions_dir = Path.home() / ".claude" / "logs" / "sessions"
    if sessions_dir.exists():
        import time

        stale_count = 0
        total_count = 0
        for s in sessions_dir.iterdir():
            if s.is_dir():
                total_count += 1
                if (time.time() - s.stat().st_mtime) > 7 * 86400:
                    stale_count += 1
        if stale_count > 50:
            issues.append(f"{stale_count} stale sessions (>7 days). Consider archiving.")
        print(f"  Sessions: {total_count} total, {stale_count} stale (>7d)")

    # Check for non-ASCII characters in langgraph_engine Python files
    scripts_dir = Path(__file__).resolve().parent / "langgraph_engine"
    if scripts_dir.exists():
        non_ascii = 0
        for py_file in scripts_dir.glob("*.py"):
            try:
                content = py_file.read_bytes()
                if any(b > 127 for b in content):
                    non_ascii += 1
            except Exception:
                pass
        if non_ascii > 0:
            issues.append(f"{non_ascii} Python files contain non-ASCII characters " "(Windows cp1252 risk).")
        print(f"  Encoding check: {non_ascii} files with non-ASCII chars")
    else:
        print("  Encoding check: langgraph_engine directory not found")

    # Summary
    if issues:
        print(f"\n  Found {len(issues)} issue(s):")
        for i, issue in enumerate(issues, 1):
            print(f"    {i}. {issue}")
    else:
        print("\n  No issues found. Everything looks healthy!")


def cmd_setup(args):
    """Run the interactive setup wizard."""
    setup_script = Path(__file__).resolve().parent / "setup" / "setup_wizard.py"
    if setup_script.exists():
        subprocess.run([sys.executable, str(setup_script)])
    else:
        print("Setup wizard not found. Manual setup steps:")
        print("  1. cp .env.example .env")
        print("  2. Edit .env with your API keys (ANTHROPIC_API_KEY, GITHUB_TOKEN)")
        print("  3. pip install -r requirements.txt")
        print("  4. Register MCP servers in ~/.claude/settings.json")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="cwe",
        description="Claude Workflow Engine - Full SDLC Automation",
        epilog="Run 'cwe <command> --help' for command-specific help.",
    )
    parser.add_argument("--version", "-v", action="store_true", help="Show version")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # cwe run
    run_parser = subparsers.add_parser("run", help="Run the pipeline on a task")
    run_parser.add_argument("task_words", nargs="*", help="Task description (positional)")
    run_parser.add_argument("--task", "-t", type=str, help="Task description (flag)")
    run_parser.add_argument(
        "--mode",
        "-m",
        choices=["hook", "full"],
        default="hook",
        help="Execution mode: hook (Steps 0-9) or full (Steps 0-14)",
    )
    run_parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run (Steps 0-7 only, skip GitHub/implementation)",
    )
    run_parser.add_argument("--summary", "-s", action="store_true", help="Show execution summary")
    run_parser.set_defaults(func=cmd_run)

    # cwe setup
    setup_parser = subparsers.add_parser("setup", help="Interactive first-time setup")
    setup_parser.set_defaults(func=cmd_setup)

    # cwe status
    status_parser = subparsers.add_parser("status", help="Show pipeline status")
    status_parser.set_defaults(func=cmd_status)

    # cwe health
    health_parser = subparsers.add_parser("health", help="Check dependencies and services")
    health_parser.set_defaults(func=cmd_health)

    # cwe version
    version_parser = subparsers.add_parser("version", help="Show version info")
    version_parser.set_defaults(func=cmd_version)

    # cwe doctor
    doctor_parser = subparsers.add_parser("doctor", help="Diagnose common issues")
    doctor_parser.set_defaults(func=cmd_doctor)

    args = parser.parse_args()

    if args.version:
        cmd_version(args)
        return

    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
