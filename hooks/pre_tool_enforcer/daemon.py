"""pre_tool_enforcer/daemon.py - optional warm daemon for PreToolUse policy evaluation.

Eliminates the dominant per-call cost of the direct path (Python interpreter
startup + ~15 dynamic importlib module loads of the policy files) by keeping
those modules loaded in a long-lived local process. The Claude Code hook
itself (pre-tool-enforcer.py) still runs as a normal synchronous hook
command - it just talks to this warm process over a localhost socket
instead of re-importing everything itself.

Fully opt-in (WORKFLOW_DAEMON_MODE=1) and fail-safe: any connection error,
timeout, or malformed response causes the caller to silently fall back to
the original in-process path (core.main()). The daemon calls the exact
same core._evaluate_tool_call() function the direct path uses, so results
can never drift between the two paths.

Windows-safe: ASCII only, no Unicode characters.
"""

import json
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

_DEFAULT_PORT = int(os.environ.get("WORKFLOW_DAEMON_PORT", "47291"))
_CONNECT_TIMEOUT_S = float(os.environ.get("WORKFLOW_DAEMON_CONNECT_TIMEOUT", "0.15"))
_LOCK_FILE = Path.home() / ".claude" / "memory" / ".pre-tool-daemon.lock"


def _send_framed(sock, obj):
    """Write one length-prefixed JSON message to a socket."""
    payload = json.dumps(obj).encode("utf-8")
    sock.sendall(struct.pack(">I", len(payload)) + payload)


def _recv_exact(sock, n):
    """Read exactly n bytes from a socket, raising on early close."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("daemon connection closed early")
        buf += chunk
    return buf


def _recv_framed(sock, timeout_s):
    """Read one length-prefixed JSON message from a socket."""
    sock.settimeout(timeout_s)
    header = _recv_exact(sock, 4)
    (length,) = struct.unpack(">I", header)
    body = _recv_exact(sock, length)
    return json.loads(body.decode("utf-8"))


# ---------------------------------------------------------------------------
# Client side (used by hooks/pre-tool-enforcer.py)
# ---------------------------------------------------------------------------


def try_daemon_fast_path(raw_stdin, port=None, timeout_s=None):
    """Attempt to get a policy verdict from the warm daemon.

    Returns {"hints": [...], "blocks": [...], "blocked_policy": str|None} on
    success, or None if the daemon is unreachable/unhealthy - callers must
    fall back to the direct in-process path (core.main()) on None.
    """
    port = port or _DEFAULT_PORT
    timeout_s = timeout_s if timeout_s is not None else _CONNECT_TIMEOUT_S
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout_s) as sock:
            _send_framed(sock, {"stdin": raw_stdin})
            result = _recv_framed(sock, timeout_s=timeout_s * 4)
        if "error" in result:
            return None
        return result
    except Exception:
        return None


def ensure_daemon_running(project_root, port=None):
    """Best-effort: spawn the daemon in the background if not already up.

    Never raises, never blocks the caller (fire-and-forget Popen). A short
    lock-file debounce prevents rapid-fire hook calls from spawning
    duplicate daemon processes while one is still starting.
    """
    port = port or _DEFAULT_PORT
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.05):
            return  # already running
    except Exception:
        pass

    try:
        _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _LOCK_FILE.exists():
            age = time.time() - _LOCK_FILE.stat().st_mtime
            if age < 5:
                return  # another hook call is already spawning it
        _LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")

        daemon_script = Path(__file__).resolve().parent / "daemon.py"
        env = os.environ.copy()
        env.pop("CLAUDE_WORKFLOW_RUNNING", None)
        env["WORKFLOW_DAEMON_PORT"] = str(port)

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

        subprocess.Popen(
            [sys.executable, str(daemon_script)],
            cwd=str(project_root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Server side
# ---------------------------------------------------------------------------


def _load_core_module():
    """Load pre_tool_enforcer/core.py once, resident for the daemon's life."""
    import importlib.util as _ilu

    core_path = Path(__file__).resolve().parent / "core.py"
    spec = _ilu.spec_from_file_location(
        "_pre_tool_enforcer_daemon_core",
        str(core_path),
        submodule_search_locations=[str(core_path.parent)],
    )
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_daemon(port=None, idle_timeout_s=1800):
    """Run the warm PreToolUse policy daemon until idle_timeout_s of inactivity.

    Auto-shuts-down after sitting idle so a forgotten daemon does not linger
    forever across machine restarts or long gaps between coding sessions.
    """
    port = port or _DEFAULT_PORT
    # core.py exits immediately at import time if this is "1" (recursion
    # guard for the pipeline itself) - force it off for the daemon process.
    os.environ["CLAUDE_WORKFLOW_RUNNING"] = "0"
    core = _load_core_module()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("127.0.0.1", port))
    except OSError:
        # Another daemon instance already owns this port - exit quietly.
        return
    server.listen(8)
    server.settimeout(idle_timeout_s)

    try:
        while True:
            try:
                conn, _addr = server.accept()
            except socket.timeout:
                break  # idle too long - shut down

            with conn:
                try:
                    request = _recv_framed(conn, timeout_s=5)
                    raw = request.get("stdin", "")
                    data = json.loads(raw) if raw and raw.strip() else {}
                    tool_name = data.get("tool_name", "")
                    tool_input = data.get("tool_input", {})
                    if not isinstance(tool_input, dict):
                        tool_input = {}
                    flow_ctx = core._load_flow_trace_context()
                    hints, blocks, blocked_policy = core._evaluate_tool_call(tool_name, tool_input, flow_ctx)
                    _send_framed(conn, {"hints": hints, "blocks": blocks, "blocked_policy": blocked_policy})
                except Exception as exc:
                    try:
                        _send_framed(conn, {"error": str(exc)[:200]})
                    except Exception:
                        pass
    finally:
        server.close()
        try:
            _LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    run_daemon()
