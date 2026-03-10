#!/usr/bin/env python3
"""
Wrapper for 3-level-flow.py that sets environment variables on Windows.

On Windows, the hook syntax VAR=value python script.py doesn't work.
This wrapper handles env vars properly and passes stdin to the main script.
"""
import os
import sys
import subprocess

# Set environment variables
os.environ["OLLAMA_MODEL"] = "qwen2.5:7b"
os.environ["OLLAMA_ENDPOINT"] = "http://localhost:11434/api/generate"

# Get path to 3-level-flow.py
script_path = os.path.join(os.path.dirname(__file__), "3-level-flow.py")

try:
    # Run the main script, preserving stdin
    result = subprocess.run(
        [sys.executable, script_path],
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    sys.exit(result.returncode)
except Exception as e:
    print(f"[ERROR] 3-level-flow wrapper failed: {e}", file=sys.stderr)
    sys.exit(1)
