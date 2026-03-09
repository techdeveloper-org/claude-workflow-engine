#!/usr/bin/env python3
"""Restart Claude Insight Dashboard after updates.

This script runs after claude-insight repository updates.
It detects if the Flask dashboard is running, kills the process,
and restarts it to load the latest code changes.

Purpose: Ensure latest dashboard code is loaded after updates.
"""

import os
import subprocess
import sys
import time
from pathlib import Path


def find_dashboard_port():
    """Find which port the Flask dashboard is running on.

    Returns:
        int: Port number if found, None otherwise
    """
    try:
        # Check for common Flask ports
        for port in [5000, 5001, 8000, 8080, 3000]:
            result = subprocess.run(
                f'netstat -ano | findstr ":{port}"',
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout:
                # Extract PID from netstat output
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    parts = line.split()
                    if parts:
                        pid = parts[-1]
                        if pid.isdigit():
                            return port, int(pid)
        return None, None
    except Exception as e:
        print(f"[WARN]    Error checking ports: {e}")
        return None, None


def kill_process(pid):
    """Kill a process by PID.

    Args:
        pid (int): Process ID to kill

    Returns:
        bool: True if killed successfully, False otherwise
    """
    try:
        subprocess.run(f'taskkill /PID {pid} /F', shell=True, timeout=10)
        print(f"[KILL]    Process {pid} terminated")
        time.sleep(2)  # Wait for port to be released
        return True
    except Exception as e:
        print(f"[ERROR]   Failed to kill process {pid}: {e}")
        return False


def restart_dashboard():
    """Restart the Flask dashboard.

    Returns:
        bool: True if restart succeeded, False otherwise
    """
    try:
        # Find run.py
        insight_dir = Path(__file__).parent.parent
        run_py = insight_dir / 'run.py'

        if not run_py.exists():
            print(f"[WARN]    run.py not found at {run_py}")
            return False

        print(f"[START]   Starting Flask dashboard from {run_py}...")

        # Start dashboard in background
        subprocess.Popen(
            [sys.executable, str(run_py)],
            cwd=str(insight_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        time.sleep(3)  # Wait for app to start
        print(f"[SUCCESS] Dashboard restarted")
        return True

    except Exception as e:
        print(f"[ERROR]   Failed to restart dashboard: {e}")
        return False


def main():
    """Check if dashboard is running and restart if necessary."""
    print("[RESTART] Claude Insight Dashboard Restart Handler")
    print("[CHECK]   Detecting dashboard process...")

    port, pid = find_dashboard_port()

    if port is None:
        print(f"[INFO]    Dashboard not running, skipping restart")
        return 0

    print(f"[FOUND]   Dashboard running on port {port} (PID: {pid})")
    print(f"[STOP]    Stopping old dashboard...")

    if kill_process(pid):
        if restart_dashboard():
            print(f"[OK]      Dashboard restarted with latest code")
            return 0
        else:
            print(f"[WARN]    Failed to restart dashboard (non-blocking)")
            return 0  # Non-blocking
    else:
        print(f"[WARN]    Could not stop dashboard (non-blocking)")
        return 0  # Non-blocking


if __name__ == '__main__':
    sys.exit(main())
