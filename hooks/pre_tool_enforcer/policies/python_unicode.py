# pre_tool_enforcer/policies/python_unicode.py
# Level 3.7: Detect Unicode characters that crash Python on Windows cp1252.
# Windows-safe: ASCII only, no Unicode characters.

# Unicode chars that CRASH Python on Windows (cp1252 encoding)
# Listed as escape sequences so THIS file stays ASCII-safe
UNICODE_DANGER = [
    "\u2705",
    "\u274c",
    "\u2728",
    "\U0001f4dd",
    "\u2192",
    "\u2193",
    "\u2191",
    "\u2713",
    "\u2717",
    "\u2022",
    "\u2605",
    "\U0001f680",
    "\u26a0",
    "\U0001f6a8",
    "\U0001f4ca",
    "\U0001f4cb",
    "\U0001f50d",
    "\u2b50",
    "\U0001f4c4",
    "\u270f",
    "\u2714",
    "\u2716",
    "\U0001f527",
    "\U0001f4a1",
    "\U0001f916",
    "\u2139",
    "\U0001f512",
    "\U0001f513",
    "\U0001f3af",
    "\u21d2",
    "\u2764",
    "\U0001f4a5",
    "\u2714",
    "\u25cf",
    "\u25cb",
    "\u25a0",
    "\u25a1",
    "\u2660",
    "\u2663",
    "\u2665",
    "\u2666",
    "\u00bb",
    "\u00ab",
    "\u2026",
    "\u2014",
    "\u2013",
    "\u201c",
    "\u201d",
    "\u2018",
    "\u2019",
    "\u00ae",
    "\u00a9",
    "\u2122",
    "\u00b7",
    "\u00b0",
    "\u00b1",
    "\u00d7",
    "\u00f7",
    "\u221e",
    "\u2248",
    "\u2260",
    "\u2264",
    "\u2265",
    "\u00bc",
    "\u00bd",
    "\u00be",
]


def _check_python_unicode_content(content):
    """Return block message if Unicode danger chars found in content.

    Args:
        content (str): String content of the Python file about to be written.

    Returns:
        str: Block message string, or empty string if no violations.
    """
    found_count = 0
    sample = []

    for char in UNICODE_DANGER:
        if char in content:
            found_count += 1
            if len(sample) < 5:
                sample.append(repr(char))

    if found_count > 0:
        return (
            "[PRE-TOOL L3.7] BLOCKED - Unicode chars in Python file!\n"
            "  Platform : Windows (cp1252 encoding)\n"
            "  Problem  : " + str(found_count) + " unicode char(s) will cause UnicodeEncodeError\n"
            "  Sample   : " + ", ".join(sample) + "\n"
            "  Fix      : Replace with ASCII: [OK] [ERROR] [WARN] [INFO] -> * #\n"
            "  Rule     : NEVER use Unicode in Python scripts on Windows!"
        )
    return ""


def check_python_unicode(tool_name, tool_input):
    """Level 3.7: Block Write/Edit to .py files that contain Windows-unsafe Unicode.

    Args:
        tool_name (str): Name of the tool being invoked.
        tool_input (dict): Tool parameters dict.

    Returns:
        tuple: (blocked: bool, message: str)
    """
    if tool_name not in ("Write", "Edit", "NotebookEdit"):
        return False, ""

    file_path = tool_input.get("file_path", "") or tool_input.get("notebook_path", "") or ""

    if not file_path.endswith(".py"):
        return False, ""

    content = (
        tool_input.get("content", "") or tool_input.get("new_string", "") or tool_input.get("new_source", "") or ""
    )

    if not content:
        return False, ""

    msg = _check_python_unicode_content(content)
    if msg:
        return True, msg
    return False, ""
