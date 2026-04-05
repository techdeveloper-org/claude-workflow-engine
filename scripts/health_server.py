"""
health_server.py - Lightweight HTTP health and readiness server.

Provides two endpoints used by Docker HEALTHCHECK and Kubernetes probes:
  GET /health    - Liveness check. Returns 200 with version and timestamp.
  GET /readiness - Readiness check. Verifies that ANTHROPIC_API_KEY is set.
                   Returns 200 only when ready.

The server runs in a daemon thread so it does not block the main pipeline.
It is activated only when the environment variable ENABLE_HEALTH_SERVER=1.

This module intentionally has zero imports from langgraph_engine so it can
start before the pipeline initialises (fail-fast startup visibility).

Python 3.8+ compatible. ASCII-only string literals (cp1252 safe).
"""

import json
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------
_VERSION = "1.15.1"
_SERVICE_NAME = "workflow-engine"


# ---------------------------------------------------------------------------
# Health check helpers
# ---------------------------------------------------------------------------


def _check_anthropic_key():
    # type: () -> bool
    """Return True when ANTHROPIC_API_KEY is set to a non-empty value."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return bool(key)


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------


class _HealthHandler(BaseHTTPRequestHandler):
    """Handles GET /health and GET /readiness."""

    def log_message(self, fmt, *args):
        # Suppress default access log to keep stdout clean.
        pass

    def _send_json(self, status_code, payload):
        # type: (int, dict) -> None
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/readiness":
            self._handle_readiness()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_health(self):
        payload = {
            "status": "ok",
            "version": _VERSION,
            "service": _SERVICE_NAME,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self._send_json(200, payload)

    def _handle_readiness(self):
        anthropic_key_ok = _check_anthropic_key()
        ready = anthropic_key_ok
        payload = {
            "ready": ready,
            "checks": {
                "anthropic_key": anthropic_key_ok,
            },
        }
        status_code = 200 if ready else 503
        self._send_json(status_code, payload)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start_health_server(port=8080):
    # type: (int) -> None
    """Start the health server in a background daemon thread.

    The server only starts when the environment variable
    ENABLE_HEALTH_SERVER is set to exactly "1". When the variable is absent
    or set to any other value this function returns immediately without
    binding any port.

    Args:
        port: TCP port to bind. Defaults to 8080.
    """
    if os.environ.get("ENABLE_HEALTH_SERVER", "0") != "1":
        return

    server = HTTPServer(("0.0.0.0", port), _HealthHandler)

    def _serve():
        server.serve_forever()

    thread = threading.Thread(target=_serve, name="health-server", daemon=True)
    thread.start()
    # Print to stderr so it does not pollute pipeline stdout
    import sys

    print(
        "[INFO] Health server listening on port {}".format(port),
        file=sys.stderr,
    )
