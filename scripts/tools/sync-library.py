#!/usr/bin/env python3
"""Verify+pull wrapper for the claude-global-library sibling (ADR-2 / FR-2).

Thin C4 wrapper described in docs/phase-1-architecture/hld.md ADR-2. With the
ADR-1 local-path bridge in place, the engine reads skills/agents/KG files
directly from the sibling checkout at rolling disk state -- there is nothing
to "download". The only real operation left is freshness, so this wrapper
(1) verifies the sibling exists via the same locate_library_root() primitive
the resolver uses, and (2) optionally runs `git pull --ff-only` inside it.
It replaces the removed hook-downloader.py-based sync flow; no new
downloader is created.

Exit codes:
    0 - sibling verified (and, with --pull, fast-forwarded or already current)
    2 - sibling not found (same actionable LibrarySetupError message the
        ADR-1 resolver's terminal tier raises)
    3 - --pull failed (non-fast-forward or other git error); resolve manually
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional

_ENGINE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))

from langgraph_engine.library.resolver import ENV_LIBRARY_PATH, LibrarySetupError, locate_library_root  # noqa: E402

EXIT_OK = 0
EXIT_SIBLING_NOT_FOUND = 2
EXIT_PULL_FAILED = 3

RunnerFn = Callable[..., "subprocess.CompletedProcess[str]"]


def verify_and_pull(
    do_pull: bool,
    engine_root: Optional[Path] = None,
    runner: RunnerFn = subprocess.run,
) -> int:
    """Verify the claude-global-library sibling exists, optionally pulling it.

    Args:
        do_pull: If True, also run `git pull --ff-only` inside the sibling.
        engine_root: Root of this checkout, forwarded to
            locate_library_root(). Defaults to the real repo root.
        runner: Injection seam for subprocess.run (tests supply a fake).

    Returns:
        EXIT_OK, EXIT_SIBLING_NOT_FOUND, or EXIT_PULL_FAILED.
    """
    root = engine_root or _ENGINE_ROOT
    library_root = locate_library_root(root)

    if library_root is None:
        expected = root.parent / "claude-global-library"
        error = LibrarySetupError(expected, ENV_LIBRARY_PATH, detail="sync-library verify step")
        print(f"[ERROR] {error}", file=sys.stderr)
        return EXIT_SIBLING_NOT_FOUND

    print(f"[OK] claude-global-library found at {library_root}")

    if not do_pull:
        return EXIT_OK

    return _pull(library_root, runner)


def _pull(library_root: Path, runner: RunnerFn) -> int:
    """Run `git pull --ff-only` in library_root and map the result to an exit code.

    Raises:
        Nothing -- git/subprocess failures are captured and converted to
        EXIT_PULL_FAILED with an actionable message on stderr.
    """
    result = runner(
        ["git", "pull", "--ff-only"],
        cwd=str(library_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"[ERROR] git pull --ff-only failed in {library_root}", file=sys.stderr)
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        print(
            "[ERROR] Resolve manually (e.g. rebase/merge the sibling checkout) and retry.",
            file=sys.stderr,
        )
        return EXIT_PULL_FAILED

    print(result.stdout.strip() or "[OK] Already up to date.")
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the claude-global-library sibling and optionally fast-forward it (ADR-2).",
    )
    parser.add_argument(
        "--pull",
        action="store_true",
        help="After verifying the sibling exists, run 'git pull --ff-only' inside it.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point: parse args and delegate to verify_and_pull()."""
    args = _build_parser().parse_args(argv)
    return verify_and_pull(do_pull=args.pull)


if __name__ == "__main__":
    sys.exit(main())
