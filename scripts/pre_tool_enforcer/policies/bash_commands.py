# pre_tool_enforcer/policies/bash_commands.py
# Level 3.7: Detect and block Windows-only shell commands + branch protection.
# Windows-safe: ASCII only, no Unicode characters.

# Windows-only commands that fail in bash shell
# Format: (windows_cmd_prefix, bash_equivalent)
WINDOWS_CMDS = [
    ("del ", "rm"),
    ("del\t", "rm"),
    ("copy ", "cp"),
    ("xcopy ", "cp -r"),
    ("move ", "mv"),
    ("ren ", "mv"),
    ("md ", "mkdir"),
    ("rd ", "rmdir"),
    ("dir ", "ls"),
    ("dir\n", "ls"),
    ("type ", "cat"),
    ("attrib ", "chmod"),
    ("icacls ", "chmod"),
    ("taskkill", "kill"),
    ("tasklist", "ps aux"),
    ("where ", "which"),
    ("findstr ", "grep"),
    ("cls\n", "clear"),
    ("cls\r", "clear"),
    ("cls", "clear"),
    ("ipconfig", "ifconfig / ip addr"),
    ("netstat ", "netstat / ss"),
    ("systeminfo", "uname -a"),
    ("schtasks ", "cron"),
    ("sc ", "systemctl"),
    ("net ", "systemctl / id"),
    ("reg ", "No equivalent in bash"),
    ("regedit", "No equivalent in bash"),
    ("msiexec", "No equivalent in bash"),
]


def check_bash_commands(tool_name, tool_input):
    """Level 3.7: Detect and block Windows-only shell commands + branch protection.

    Scans the command string for Windows-only prefixes listed in WINDOWS_CMDS.
    Also enforces branch protection: blocks git push/commit to main/master
    when no issue branch has been created (GitHub workflow enforcement).

    Args:
        tool_name (str): Name of the tool (must be 'Bash' to trigger this check).
        tool_input (dict): Tool parameters dict with 'command' key.

    Returns:
        tuple: (blocked: bool, message: str)
    """
    if tool_name != "Bash":
        return False, ""

    command = tool_input.get("command", "")
    cmd_stripped = command.strip()
    cmd_lower = cmd_stripped.lower()

    # BRANCH PROTECTION: Block git push to main/master
    if "git push" in cmd_lower:
        push_to_protected = False
        for protected in ["main", "master"]:
            if ("push origin " + protected) in cmd_lower:
                push_to_protected = True
            elif cmd_lower.strip().endswith("push origin " + protected):
                push_to_protected = True

        if push_to_protected:
            try:
                import subprocess as _sp

                _branch_result = _sp.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5
                )
                current_branch = _branch_result.stdout.strip()
                if current_branch in ("main", "master"):
                    return True, (
                        "[PRE-TOOL BLOCKED] Direct push to " + current_branch + " is NOT allowed!\n"
                        "  Policy   : GitHub Branch Protection (github-branch-pr-policy)\n"
                        '  Current  : On branch "' + current_branch + '"\n'
                        "  Required : Create an issue branch first (e.g. fix/42, feature/123)\n"
                        "  Workflow : TaskCreate -> GitHub Issue -> Branch -> Work -> PR -> Merge\n"
                        "  Action   : Create a task with TaskCreate, then use the issue branch."
                    )
            except Exception:
                pass

    # WINDOWS COMMAND BLOCKING
    for win_cmd, bash_equiv in WINDOWS_CMDS:
        win_lower = win_cmd.lower()
        if (
            cmd_lower.startswith(win_lower)
            or ("\n" + win_lower) in cmd_lower
            or ("; " + win_lower) in cmd_lower
            or ("&& " + win_lower) in cmd_lower
        ):
            return True, (
                "[PRE-TOOL L3.7] BLOCKED - Windows command in bash shell!\n"
                "  Detected : " + win_cmd.strip() + "\n"
                "  Use instead: " + bash_equiv + "\n"
                "  Fix the command and retry."
            )

    return False, ""


def check_bash(command):
    """Backward-compat wrapper: original signature accepted a bare command string.

    Returns (hints: list, blocks: list) to match the old calling convention.
    """
    blocked, msg = check_bash_commands("Bash", {"command": command})
    if blocked:
        return [], [msg]
    return [], []
