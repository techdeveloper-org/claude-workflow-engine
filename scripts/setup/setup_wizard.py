"""
Claude Workflow Engine - Interactive Setup Wizard.

Walks first-time users through configuration:
1. System checks (Python, OS, dependencies)
2. Core setup (.env file creation)
3. GitHub authentication
4. Optional integrations (Jira, Jenkins, SonarQube)
5. MCP server registration
6. Connectivity verification

Usage:
  python scripts/setup_wizard.py
  cwe setup

Version: 1.4.1
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ASCII-only banner
BANNER = """
============================================================
  Claude Workflow Engine - Setup Wizard
  Version: {version}
============================================================
"""


def get_version():
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return "1.4.1"


def prompt_user(question, default="", required=False, secret=False):
    """Prompt user for input with default value."""
    if default:
        display = "{0} [{1}]: ".format(question, default)
    else:
        display = "{0}: ".format(question)

    while True:
        try:
            value = input(display).strip()
        except EOFError:
            value = ""
        if not value:
            value = default
        if required and not value:
            print("  This field is required.")
            continue
        return value


def prompt_yes_no(question, default=True):
    """Prompt yes/no question."""
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input("{0} {1}: ".format(question, suffix)).strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in ("y", "yes")


def check_system():
    """Step 1: Check system requirements."""
    print("\n--- Step 1: System Checks ---\n")

    all_ok = True

    # Python version
    py_ver = "{0}.{1}".format(sys.version_info.major, sys.version_info.minor)
    ok = sys.version_info >= (3, 8)
    status = "[OK]" if ok else "[!!]"
    suffix = "" if ok else " (>= 3.8 required)"
    print("  {0} Python {1}{2}".format(status, py_ver, suffix))
    all_ok = all_ok and ok

    # pip
    try:
        subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, timeout=5)
        print("  [OK] pip available")
    except Exception:
        print("  [!!] pip not available")
        all_ok = False

    # git
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
        print("  [OK] {0}".format(result.stdout.strip()))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  [!!] git not installed")
        all_ok = False

    # GitHub CLI
    try:
        result = subprocess.run(["gh", "--version"], capture_output=True, text=True, timeout=5)
        ver = result.stdout.strip().split("\n")[0]
        print("  [OK] {0}".format(ver))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  [!!] GitHub CLI (gh) not installed")
        print("       Install: https://cli.github.com/")
        all_ok = False

    # Platform
    print("  [OK] Platform: {0}".format(sys.platform))

    return all_ok


def install_dependencies():
    """Step 2: Install Python dependencies."""
    print("\n--- Step 2: Install Dependencies ---\n")

    req_file = Path(__file__).resolve().parent.parent / "requirements.txt"
    if not req_file.exists():
        print("  [!!] requirements.txt not found")
        return False

    if prompt_yes_no("  Install/update dependencies from requirements.txt?"):
        print("  Installing... (this may take a minute)")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print("  [OK] Dependencies installed")
            return True
        else:
            print("  [!!] Installation failed: {0}".format(result.stderr[:200]))
            return False
    else:
        print("  Skipped dependency installation")
        return True


def setup_env():
    """Step 3: Create .env file from .env.example."""
    print("\n--- Step 3: Environment Configuration ---\n")

    project_root = Path(__file__).resolve().parent.parent
    env_file = project_root / ".env"
    env_example = project_root / ".env.example"

    if env_file.exists():
        if not prompt_yes_no("  .env already exists. Overwrite?", default=False):
            print("  Keeping existing .env")
            return True

    if not env_example.exists():
        print("  [!!] .env.example not found")
        return False

    config = {}

    # Core settings
    print("\n  -- Core Settings --")
    config["CLAUDE_HOOK_MODE"] = prompt_user("  Pipeline mode (1=hook Steps 0-9, 0=full Steps 0-14)", default="1")
    config["CLAUDE_DEBUG"] = prompt_user("  Debug mode (0=off, 1=on)", default="0")

    # LLM Provider
    print("\n  -- LLM Provider --")
    config["LLM_PROVIDER"] = prompt_user("  LLM provider (auto/claude_cli/anthropic)", default="auto")

    anthropic_key = prompt_user("  Anthropic API key (leave empty to skip)", default="")
    if anthropic_key:
        config["ANTHROPIC_API_KEY"] = anthropic_key

    # GitHub
    print("\n  -- GitHub --")
    gh_token = prompt_user("  GitHub token (leave empty to use 'gh auth token')", default="")
    if gh_token:
        config["GITHUB_TOKEN"] = gh_token

    # Optional integrations
    print("\n  -- Optional Integrations --")

    # Jira
    if prompt_yes_no("  Enable Jira integration?", default=False):
        config["ENABLE_JIRA"] = "1"
        config["JIRA_URL"] = prompt_user("  Jira URL", required=True)
        config["JIRA_USER"] = prompt_user("  Jira user (email for Cloud)", required=True)
        config["JIRA_API_TOKEN"] = prompt_user("  Jira API token", required=True)
        config["JIRA_API_VERSION"] = prompt_user("  Jira API version (3=Cloud, 2=Server)", default="3")
        config["JIRA_DEFAULT_PROJECT"] = prompt_user("  Default Jira project key", default="")

    # Jenkins
    if prompt_yes_no("  Enable Jenkins integration?", default=False):
        config["ENABLE_JENKINS"] = "1"
        config["JENKINS_URL"] = prompt_user("  Jenkins URL", required=True)
        config["JENKINS_USER"] = prompt_user("  Jenkins username", required=True)
        config["JENKINS_API_TOKEN"] = prompt_user("  Jenkins API token", required=True)

    # SonarQube
    if prompt_yes_no("  Enable SonarQube integration?", default=False):
        config["ENABLE_SONARQUBE"] = "1"
        config["SONAR_HOST_URL"] = prompt_user("  SonarQube URL", default="http://localhost:9000")
        config["SONAR_TOKEN"] = prompt_user("  SonarQube token", default="")

    # Copy .env.example as base, then overlay user values
    shutil.copy2(str(env_example), str(env_file))
    content = env_file.read_text(encoding="utf-8")

    for key, value in config.items():
        # Match commented or uncommented version of the key
        pattern = r"^#?\s*" + re.escape(key) + r"=.*$"
        replacement = "{0}={1}".format(key, value)
        new_content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)
        if count > 0:
            content = new_content
        else:
            # Append if not found in the example file
            content += "\n{0}={1}".format(key, value)

    env_file.write_text(content, encoding="utf-8")
    print("\n  [OK] .env file created at {0}".format(env_file))
    return True


def register_mcp_servers():
    """Step 4: Register MCP servers in ~/.claude/settings.json."""
    print("\n--- Step 4: MCP Server Registration ---\n")

    if not prompt_yes_no("  Register MCP servers in ~/.claude/settings.json?", default=True):
        print("  Skipped MCP registration")
        return True

    settings_path = Path.home() / ".claude" / "settings.json"
    project_root = Path(__file__).resolve().parent.parent
    mcp_dir = project_root / "src" / "mcp"

    if not mcp_dir.exists():
        print("  [!!] MCP directory not found at {0}".format(mcp_dir))
        return False

    # Discover MCP server files
    mcp_files = list(mcp_dir.glob("*_mcp_server.py"))
    if not mcp_files:
        print("  [!!] No MCP server files found in {0}".format(mcp_dir))
        return False

    print("  Found {0} MCP server(s) in {1}".format(len(mcp_files), mcp_dir))

    # Load existing settings or create skeleton
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print("  [!!] Could not read settings.json: {0}".format(exc))
            return False
    else:
        settings_path.parent.mkdir(parents=True, exist_ok=True)

    if "mcpServers" not in settings:
        settings["mcpServers"] = {}

    registered = 0
    skipped = 0
    for mcp_file in sorted(mcp_files):
        # Derive server name from filename: git_mcp_server.py -> git-ops (use stem)
        stem = mcp_file.stem  # e.g. git_mcp_server
        server_name = stem.replace("_mcp_server", "").replace("_", "-")

        if server_name in settings["mcpServers"]:
            skipped += 1
            continue

        settings["mcpServers"][server_name] = {"command": sys.executable, "args": [str(mcp_file)], "env": {}}
        registered += 1

    try:
        settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        print(
            "  [OK] Registered {0} server(s), skipped {1} already-registered " "server(s)".format(registered, skipped)
        )
        print("  [OK] Settings saved to {0}".format(settings_path))
    except OSError as exc:
        print("  [!!] Could not write settings.json: {0}".format(exc))
        return False

    return True


def verify_connectivity():
    """Step 5: Verify service connectivity."""
    print("\n--- Step 5: Connectivity Check ---\n")

    # Load .env if exists
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    checks = []

    # GitHub CLI auth
    try:
        result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=5)
        checks.append(("GitHub CLI auth", result.returncode == 0))
    except Exception:
        checks.append(("GitHub CLI auth", False))

    # Jira
    if os.environ.get("ENABLE_JIRA") == "1":
        jira_url = os.environ.get("JIRA_URL", "")
        if jira_url:
            try:
                import urllib.request

                with urllib.request.urlopen(jira_url, timeout=5):
                    checks.append(("Jira", True))
            except Exception:
                checks.append(("Jira", False))

    # Jenkins
    if os.environ.get("ENABLE_JENKINS") == "1":
        jenkins_url = os.environ.get("JENKINS_URL", "")
        if jenkins_url:
            try:
                import urllib.request

                with urllib.request.urlopen(jenkins_url, timeout=5):
                    checks.append(("Jenkins", True))
            except Exception:
                checks.append(("Jenkins", False))

    # SonarQube
    if os.environ.get("ENABLE_SONARQUBE") == "1":
        sonar_url = os.environ.get("SONAR_HOST_URL", "http://localhost:9000")
        try:
            import urllib.request

            with urllib.request.urlopen(sonar_url, timeout=5):
                checks.append(("SonarQube", True))
        except Exception:
            checks.append(("SonarQube", False))

    for name, ok in checks:
        status = "[OK]" if ok else "[!!]"
        state = "connected" if ok else "not reachable"
        print("  {0} {1}: {2}".format(status, name, state))

    if not checks:
        print("  (No connectivity checks configured)")

    return True


def print_next_steps():
    """Show what to do next."""
    print("\n--- Setup Complete! ---\n")
    print("  Next steps:")
    print('    1. Run the pipeline:  cwe run "fix the login bug"')
    print("    2. Check health:      cwe health")
    print("    3. View status:       cwe status")
    print('    4. Full mode:         cwe run --mode full "add user profile"')
    print('    5. Debug mode:        cwe run --debug "investigate crash"')
    print("\n  Documentation:")
    print("    - Getting started:    docs/00_START_HERE.md")
    print("    - Full README:        README.md")
    print("    - Architecture:       docs/ARCHITECTURE_REVIEW.md")
    print()


def main():
    """Run the interactive setup wizard."""
    print(BANNER.format(version=get_version()))

    # Step 1: System checks
    if not check_system():
        if not prompt_yes_no("\n  Some checks failed. Continue anyway?"):
            print("  Setup cancelled.")
            sys.exit(1)

    # Step 2: Install dependencies
    install_dependencies()

    # Step 3: Environment configuration
    setup_env()

    # Step 4: MCP server registration
    register_mcp_servers()

    # Step 5: Verify connectivity
    verify_connectivity()

    # Done
    print_next_steps()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Setup interrupted by user.")
        sys.exit(0)
