"""
Error Messages - User-friendly error formatting with actionable recovery steps.

Converts raw technical exceptions and pipeline error codes into:
- Plain English descriptions (no stack traces exposed to the user)
- Numbered recovery steps the user can follow
- Troubleshooting links for common error categories
- Help command suggestions

Covers all common error categories in the Claude Workflow Engine pipeline:
- LLM inference errors (claude_cli, anthropic)
- GitHub API errors
- File system errors
- Skill/Agent load errors
- Validation errors
- Timeout errors
- Authentication errors

Usage:
    from .error_messages import ErrorMessages, format_error

    # Quick format
    msg = format_error("LLMConnectionError", detail="Connection refused")
    print(msg.user_message)
    print(msg.recovery_steps)

    # Full formatter
    formatter = ErrorMessages()
    msg = formatter.format(
        error_type="GitHubAuthError",
        detail="401 Unauthorized",
        context={"step": 8, "session_id": "abc-123"},
    )
    print(msg.full_text)
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# GitHub owner for help/troubleshooting links (configurable via env var)
_GITHUB_OWNER = os.environ.get("CLAUDE_GITHUB_OWNER", "techdeveloper-org")


# ---------------------------------------------------------------------------
# FormattedError dataclass
# ---------------------------------------------------------------------------


@dataclass
class FormattedError:
    """A fully formatted user-facing error message."""

    error_type: str  # Internal error category
    user_message: str  # Plain-language description
    recovery_steps: List[str] = field(default_factory=list)
    troubleshooting_links: List[str] = field(default_factory=list)
    help_commands: List[str] = field(default_factory=list)
    severity: str = "ERROR"  # INFO / WARNING / ERROR / CRITICAL
    is_recoverable: bool = True
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """Return the full formatted error message as a multi-line string."""
        lines = [
            "",
            f"[{self.severity}] {self.user_message}",
        ]

        if self.recovery_steps:
            lines.append("")
            lines.append("What you can do:")
            for i, step in enumerate(self.recovery_steps, 1):
                lines.append(f"  {i}. {step}")

        if self.troubleshooting_links:
            lines.append("")
            lines.append("Troubleshooting guides:")
            for link in self.troubleshooting_links:
                lines.append(f"  - {link}")

        if self.help_commands:
            lines.append("")
            lines.append("Useful commands:")
            for cmd in self.help_commands:
                lines.append(f"  $ {cmd}")

        if not self.is_recoverable:
            lines.append("")
            lines.append("Note: This error requires manual intervention before retrying.")

        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict (JSON-safe)."""
        return {
            "error_type": self.error_type,
            "user_message": self.user_message,
            "recovery_steps": self.recovery_steps,
            "troubleshooting_links": self.troubleshooting_links,
            "help_commands": self.help_commands,
            "severity": self.severity,
            "is_recoverable": self.is_recoverable,
            "context": self.context,
        }


# ---------------------------------------------------------------------------
# Error catalog - maps error_type -> template factory
# ---------------------------------------------------------------------------


class _ErrorCatalog:
    """
    Central registry of error templates.

    Each entry is a function that receives (detail, context) and returns
    a FormattedError. This avoids storing state and makes each template
    fully parametric.
    """

    def __init__(self):
        self._templates: Dict[str, Any] = {}
        self._register_all()

    def get(self, error_type: str):
        """Return template function for the given error_type, or generic fallback."""
        # Exact match first
        if error_type in self._templates:
            return self._templates[error_type]
        # Prefix/keyword match for flexible lookup
        upper = error_type.upper()
        for key, fn in self._templates.items():
            if key.upper() in upper or upper in key.upper():
                return fn
        return self._templates["GENERIC"]

    # -----------------------------------------------------------------------
    # Registration helpers
    # -----------------------------------------------------------------------

    def _register(self, *names: str):
        """Decorator: register a template under one or more error type names."""

        def decorator(fn):
            for name in names:
                self._templates[name.upper()] = fn
            return fn

        return decorator

    def _register_all(self):
        """Register all error templates."""

        # --- LLM inference errors ---

        @self._register("LLMConnectionError", "LLMUnavailable")
        def _llm_connection(detail: str, context: dict) -> FormattedError:
            return FormattedError(
                error_type="LLMConnectionError",
                user_message=(
                    "The LLM provider is unavailable. "
                    "The pipeline requires at least one configured LLM provider "
                    "(claude_cli or anthropic) to be reachable."
                ),
                recovery_steps=[
                    "Check LLM_PROVIDER env var: set to 'claude_cli' or 'anthropic'",
                    "For claude_cli: ensure the 'claude' CLI is installed and on your PATH",
                    "For anthropic: ensure ANTHROPIC_API_KEY is set and valid",
                    "Run 'cwe health' to check provider status",
                ],
                troubleshooting_links=[
                    "https://docs.anthropic.com/claude/reference/getting-started-with-the-api",
                ],
                help_commands=[
                    "echo $ANTHROPIC_API_KEY",
                    "claude --version",
                ],
                severity="ERROR",
                is_recoverable=True,
                context=context,
            )

        @self._register("ModelNotFound")
        def _llm_model(detail: str, context: dict) -> FormattedError:
            model = _extract_model(detail) or "unknown"
            return FormattedError(
                error_type="ModelNotFound",
                user_message=(
                    f"The requested AI model '{model}' is not available. "
                    "The pipeline needs a valid model to process requests."
                ),
                recovery_steps=[
                    "Check the model name in your LLM_PROVIDER configuration",
                    "For anthropic: verify ANTHROPIC_MODEL_FAST / ANTHROPIC_MODEL_DEEP are valid",
                    "Retry with the default model by unsetting model override env vars",
                ],
                severity="ERROR",
                is_recoverable=True,
                context=context,
            )

        @self._register("LLMTimeoutError", "InferenceTimeout", "RequestTimeout")
        def _llm_timeout(detail: str, context: dict) -> FormattedError:
            step = context.get("step", "")
            step_info = f" (Step {step})" if step else ""
            return FormattedError(
                error_type="LLMTimeoutError",
                user_message=(
                    f"The AI inference request timed out{step_info}. "
                    "This can happen when the LLM provider is under load "
                    "or the task is very complex."
                ),
                recovery_steps=[
                    "Wait a few seconds and retry - the provider may be processing other requests",
                    "For large tasks, consider breaking the request into smaller parts",
                    "Check your ANTHROPIC_API_KEY rate limits",
                    "Try switching LLM_PROVIDER to another available provider",
                    "Reduce parallel tasks if multiple pipelines are running simultaneously",
                ],
                severity="WARNING",
                is_recoverable=True,
                context=context,
            )

        # --- GitHub / Git errors ---

        @self._register("GitHubAuthError", "GitHubUnauthorized", "GitHubTokenError")
        def _github_auth(detail: str, context: dict) -> FormattedError:
            return FormattedError(
                error_type="GitHubAuthError",
                user_message=(
                    "GitHub authentication failed. The pipeline needs a valid "
                    "GitHub token to create issues, branches, and pull requests."
                ),
                recovery_steps=[
                    "Check that the GITHUB_TOKEN environment variable is set",
                    "Verify the token has 'repo' scope: visit GitHub Settings > Developer Settings > Tokens",
                    "Generate a new token if the existing one has expired",
                    "Set the token: export GITHUB_TOKEN=your_token_here",
                    "Confirm the token works: 'gh auth status' (if GitHub CLI is installed)",
                ],
                troubleshooting_links=[
                    "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token",
                    "https://cli.github.com/manual/gh_auth_login - GitHub CLI authentication",
                ],
                help_commands=[
                    "gh auth status",
                    "gh auth login",
                    "echo $GITHUB_TOKEN",
                ],
                severity="ERROR",
                is_recoverable=True,
                context=context,
            )

        @self._register("GitHubRepoNotFound", "RepositoryNotFound")
        def _github_repo(detail: str, context: dict) -> FormattedError:
            return FormattedError(
                error_type="GitHubRepoNotFound",
                user_message=(
                    "The target GitHub repository was not found. "
                    "Either the repository does not exist, is private, "
                    "or your token does not have access to it."
                ),
                recovery_steps=[
                    "Verify the repository URL in your project configuration",
                    "Confirm the repository exists on GitHub",
                    "If the repository is private, ensure the token has 'repo' scope",
                    "Check that your GitHub username or organization name is correct",
                    "Update the remote URL: 'git remote set-url origin <correct-url>'",
                ],
                help_commands=[
                    "git remote -v",
                    "gh repo view",
                ],
                severity="ERROR",
                is_recoverable=True,
                context=context,
            )

        @self._register("GitBranchError", "BranchCreationFailed", "BranchConflict")
        def _git_branch(detail: str, context: dict) -> FormattedError:
            return FormattedError(
                error_type="GitBranchError",
                user_message=(
                    "Failed to create a new Git branch. "
                    "A branch with the same name may already exist, "
                    "or the working directory has uncommitted changes."
                ),
                recovery_steps=[
                    "Check for existing branches: 'git branch -a'",
                    "If a branch with the same name exists, delete it: 'git branch -D branch-name'",
                    "Commit or stash uncommitted changes before creating a new branch",
                    "Ensure you are on the main/master branch before starting",
                    "Pull latest changes from origin: 'git pull origin main'",
                ],
                help_commands=[
                    "git branch -a",
                    "git status",
                    "git stash",
                    "git pull origin main",
                ],
                severity="ERROR",
                is_recoverable=True,
                context=context,
            )

        # --- File system errors ---

        @self._register("FileNotFoundError", "FileReadError", "PathNotFound")
        def _file_not_found(detail: str, context: dict) -> FormattedError:
            path = _extract_path(detail)
            path_info = f" '{path}'" if path else ""
            return FormattedError(
                error_type="FileNotFoundError",
                user_message=(
                    f"A required file{path_info} could not be found. "
                    "The pipeline expected this file to exist before proceeding."
                ),
                recovery_steps=[
                    f"Verify the file exists: 'ls {path}'" if path else "Verify the expected file path exists",
                    "Check that the project root directory is correctly configured",
                    "If the file was recently deleted, restore it from version control: 'git checkout -- <file>'",
                    "Ensure you are running the pipeline from the correct working directory",
                    "Check file permissions - the process needs read access",
                ],
                help_commands=[
                    f"ls -la {path}" if path else "ls -la .",
                    "pwd",
                    "git status",
                ],
                severity="ERROR",
                is_recoverable=True,
                context=context,
            )

        @self._register("PermissionError", "FileWriteError", "AccessDenied")
        def _permission(detail: str, context: dict) -> FormattedError:
            return FormattedError(
                error_type="PermissionError",
                user_message=(
                    "The pipeline does not have permission to read or write a file. "
                    "This is a file system permissions issue."
                ),
                recovery_steps=[
                    "Check the file or directory permissions: 'ls -la <path>'",
                    "On Windows, verify the file is not marked as read-only",
                    "If the file is locked by another process, close that process first",
                    "Run the pipeline with appropriate user permissions",
                    "Check antivirus or security software is not blocking file access",
                ],
                help_commands=[
                    "ls -la .",
                    "icacls . /t /q",
                ],
                severity="ERROR",
                is_recoverable=False,
                context=context,
            )

        # --- Skill / Agent errors ---

        @self._register("SkillNotFound", "SkillLoadError", "AgentNotFound")
        def _skill_not_found(detail: str, context: dict) -> FormattedError:
            skill = _extract_skill(detail)
            skill_info = f" '{skill}'" if skill else ""
            return FormattedError(
                error_type="SkillNotFound",
                user_message=(
                    f"The required skill{skill_info} could not be loaded. "
                    "Skills are Markdown definitions that guide the AI on how to "
                    "handle specific task types."
                ),
                recovery_steps=[
                    (
                        f"Check if the skill file exists: 'ls ~/.claude/skills/**/{skill}*'"
                        if skill
                        else "Check the skills directory: 'ls ~/.claude/skills/'"
                    ),
                    "Download missing skills from the claude-global-library repository",
                    "If the skill was recently added, run: 'python auto_task_launcher.sh' to sync",
                    "Verify the skills directory structure: skills should be at ~/.claude/skills/<domain>/<skill-name>/skill.md",
                    "The pipeline will continue using general capabilities if the skill is unavailable",
                ],
                troubleshooting_links=[
                    f"https://github.com/{_GITHUB_OWNER}/claude-global-library - Skill definitions repository",
                ],
                help_commands=[
                    "ls ~/.claude/skills/",
                    "ls ~/.claude/agents/",
                ],
                severity="WARNING",
                is_recoverable=True,
                context=context,
            )

        @self._register("SkillValidationError", "SkillIncompatible")
        def _skill_validation(detail: str, context: dict) -> FormattedError:
            return FormattedError(
                error_type="SkillValidationError",
                user_message=(
                    "The selected skill does not fully cover all requirements for this task. "
                    "The pipeline will proceed with the best available skill and supplement "
                    "with general capabilities."
                ),
                recovery_steps=[
                    "Review the skill definition to understand its coverage",
                    "Check if a more suitable skill exists in the registry",
                    "Add missing capabilities to the skill file if you have write access",
                    "The pipeline will attempt to handle uncovered areas using baseline knowledge",
                    "Report the gap to the claude-global-library team if this is a common use case",
                ],
                troubleshooting_links=[
                    f"https://github.com/{_GITHUB_OWNER}/claude-global-library/issues - Report skill gaps",
                ],
                severity="WARNING",
                is_recoverable=True,
                context=context,
            )

        # --- Validation errors ---

        @self._register("InputValidationError", "InvalidInput", "ValidationError")
        def _validation(detail: str, context: dict) -> FormattedError:
            return FormattedError(
                error_type="InputValidationError",
                user_message=(
                    "The input provided to the pipeline did not pass validation. "
                    + (f"Specific issue: {_truncate(detail, 100)}" if detail else "")
                ),
                recovery_steps=[
                    "Review your request and check for typos or missing information",
                    "Ensure the task description is clear and complete",
                    "Avoid special characters that may interfere with JSON parsing",
                    "For code-related tasks, include relevant context (language, framework, file paths)",
                    "Retry with a simplified request to isolate the issue",
                ],
                severity="ERROR",
                is_recoverable=True,
                context=context,
            )

        @self._register("JSONParseError", "JSONDecodeError")
        def _json_parse(detail: str, context: dict) -> FormattedError:
            return FormattedError(
                error_type="JSONParseError",
                user_message=(
                    "A script returned output that could not be parsed as JSON. "
                    "This is usually a temporary issue caused by unexpected output "
                    "from a subprocess."
                ),
                recovery_steps=[
                    "Retry the operation - transient script output errors usually resolve themselves",
                    "Check if any background processes are writing to stdout unexpectedly",
                    "Verify all required Python packages are installed: 'pip install -r requirements.txt'",
                    "Enable debug mode to see raw script output: set CLAUDE_DEBUG=1",
                    "Check the error logs for the raw output that failed to parse",
                ],
                help_commands=[
                    "pip install -r requirements.txt",
                    "set CLAUDE_DEBUG=1",
                ],
                severity="WARNING",
                is_recoverable=True,
                context=context,
            )

        # --- Network errors ---

        @self._register("NetworkError", "ConnectionError", "SSLError")
        def _network(detail: str, context: dict) -> FormattedError:
            return FormattedError(
                error_type="NetworkError",
                user_message=(
                    "A network request failed. This could be a temporary connectivity "
                    "issue or a problem with the target service."
                ),
                recovery_steps=[
                    "Check your internet connection",
                    "Verify the target service is operational (check status pages)",
                    "Try again in a few minutes - transient network issues often resolve",
                    "If behind a corporate proxy, ensure proxy settings are configured",
                    "Disable VPN temporarily to test if it is causing the issue",
                ],
                severity="WARNING",
                is_recoverable=True,
                context=context,
            )

        # --- Context / Memory errors ---

        @self._register("ContextOverflowError", "ContextLimitExceeded")
        def _context_overflow(detail: str, context: dict) -> FormattedError:
            return FormattedError(
                error_type="ContextOverflowError",
                user_message=(
                    "The AI context window is almost full. "
                    "Loading more context might cause important information to be dropped."
                ),
                recovery_steps=[
                    "Break the task into smaller, focused sub-tasks",
                    "Start a new session for each major component of the work",
                    "Archive or summarise old session data to free context space",
                    "Use the --no-history flag to start fresh without session history",
                    "Focus on one file or feature at a time rather than the whole codebase",
                ],
                severity="WARNING",
                is_recoverable=True,
                context=context,
            )

        # --- Generic fallback ---

        @self._register("GENERIC")
        def _generic(detail: str, context: dict) -> FormattedError:
            step = context.get("step", "")
            step_info = f" at Step {step}" if step else ""
            detail_info = f": {_truncate(detail, 120)}" if detail else ""
            return FormattedError(
                error_type="PipelineError",
                user_message=(
                    f"An unexpected error occurred{step_info}{detail_info}. "
                    "The pipeline will attempt to continue where possible."
                ),
                recovery_steps=[
                    "Review the error details in the session log",
                    "Retry the operation - some errors are transient",
                    "If the error repeats, check the troubleshooting guide",
                    "Enable debug mode for more details: set CLAUDE_DEBUG=1",
                    "Report persistent errors with your session ID to the project maintainer",
                ],
                troubleshooting_links=[
                    f"https://github.com/{_GITHUB_OWNER}/claude-workflow-engine/issues - Report issues",
                ],
                help_commands=[
                    "set CLAUDE_DEBUG=1",
                ],
                severity="ERROR",
                is_recoverable=True,
                context=context,
            )


# ---------------------------------------------------------------------------
# Singleton catalog
# ---------------------------------------------------------------------------

_CATALOG = _ErrorCatalog()


# ---------------------------------------------------------------------------
# ErrorMessages - public formatter class
# ---------------------------------------------------------------------------


class ErrorMessages:
    """Formats raw pipeline errors into user-friendly messages.

    Wraps the error catalog with additional context enrichment and
    session-aware help suggestions.
    """

    def format(
        self,
        error_type: str,
        detail: str = "",
        context: Optional[Dict[str, Any]] = None,
        severity_override: Optional[str] = None,
    ) -> FormattedError:
        """
        Format an error into a user-friendly message.

        Args:
            error_type:        Error category string (e.g. "LLMConnectionError").
            detail:            Raw error detail or exception message.
            context:           Optional pipeline context (step, session_id, etc.).
            severity_override: Override the template severity if needed.

        Returns:
            FormattedError with user message, recovery steps, and help.
        """
        ctx = context or {}
        template_fn = _CATALOG.get(error_type)
        msg = template_fn(detail, ctx)

        # Enrich context
        msg.context.update(ctx)
        if "raw_detail" not in msg.context:
            msg.context["raw_detail"] = detail

        if severity_override:
            msg.severity = severity_override

        return msg

    def format_from_exception(
        self,
        exc: Exception,
        step: Optional[int] = None,
        session_id: str = "",
    ) -> FormattedError:
        """
        Format a Python exception into a user-friendly message.

        Args:
            exc:        The caught exception.
            step:       Pipeline step number where the exception occurred.
            session_id: Session identifier for log correlation.

        Returns:
            FormattedError derived from the exception type.
        """
        error_type = type(exc).__name__
        detail = str(exc)
        context: Dict[str, Any] = {}
        if step is not None:
            context["step"] = step
        if session_id:
            context["session_id"] = session_id

        return self.format(error_type, detail=detail, context=context)

    def format_help(self, topic: str = "") -> str:
        """
        Return a help text string for a given topic or a general overview.

        Args:
            topic: Optional topic keyword (llm / github / skills / etc.)

        Returns:
            Multi-line help string.
        """
        topic_lower = topic.lower() if topic else ""

        if "llm" in topic_lower or "provider" in topic_lower or "anthropic" in topic_lower:
            return _LLM_HELP
        if "github" in topic_lower or "git" in topic_lower:
            return _GITHUB_HELP
        if "skill" in topic_lower:
            return _SKILLS_HELP
        return _GENERAL_HELP


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------


def format_error(
    error_type: str,
    detail: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> FormattedError:
    """Quick format shortcut - creates a formatter and formats immediately."""
    return ErrorMessages().format(error_type, detail=detail, context=context)


def format_exception(
    exc: Exception,
    step: Optional[int] = None,
    session_id: str = "",
) -> FormattedError:
    """Quick format shortcut for exceptions."""
    return ErrorMessages().format_from_exception(exc, step=step, session_id=session_id)


# ---------------------------------------------------------------------------
# Help text blocks
# ---------------------------------------------------------------------------

_GENERAL_HELP = """
Claude Workflow Engine Pipeline - Help

The pipeline runs in 8 active steps to process your request:
  Pre-0, Step 0: Pre-analysis and orchestration
  Steps  8-12:  GitHub workflow (issue, branch, implementation, PR, closure)
  Steps 13-14:  Documentation and summary

Common issues:
  - LLM provider unavailable -> check LLM_PROVIDER or ANTHROPIC_API_KEY
  - GitHub auth failed       -> set GITHUB_TOKEN environment variable
  - Skills missing           -> check ~/.claude/skills/ directory

Enable debug output:
  set CLAUDE_DEBUG=1    (Windows)
  export CLAUDE_DEBUG=1 (Linux/Mac)

For more help on a specific topic:
  help llm       - LLM provider setup (claude_cli, anthropic)
  help github    - GitHub authentication
  help skills    - Skill management
"""

_LLM_HELP = """
LLM Provider Setup Help

The pipeline supports two LLM providers (in auto-fallback order):
  1. claude_cli  - Claude Code CLI (uses your Anthropic subscription)
  2. anthropic   - Anthropic API direct (needs ANTHROPIC_API_KEY)

Configuration:
  LLM_PROVIDER=auto          # auto-detect available providers (default)
  LLM_PROVIDER=claude_cli    # use only claude CLI
  LLM_PROVIDER=anthropic     # use only Anthropic API
  LLM_FALLBACK=anthropic     # fallback provider chain (comma-separated)

For claude_cli:
  1. Install Claude Code CLI: npm install -g @anthropic-ai/claude-code
  2. Verify: claude --version

For anthropic:
  1. Get API key: https://console.anthropic.com/
  2. Set: export ANTHROPIC_API_KEY=sk-ant-...
"""

_GITHUB_HELP = """
GitHub Authentication Help

The pipeline uses GitHub to create issues, branches, and pull requests.

1. Create a Personal Access Token:
   - Visit: https://github.com/settings/tokens/new
   - Select scopes: repo (full access)
   - Copy the generated token

2. Set the token:
   Windows:  set GITHUB_TOKEN=your_token_here
   Linux/Mac: export GITHUB_TOKEN=your_token_here

3. Verify authentication:
   gh auth status   (requires GitHub CLI)

4. If using GitHub CLI:
   gh auth login

Common problems:
   - Token expired: regenerate at github.com/settings/tokens
   - Wrong scope: ensure 'repo' scope is selected
   - Organization repo: ensure token has org read/write permission
"""

_SKILLS_HELP = f"""
Skills Management Help

Skills are Markdown files that teach the AI how to handle specific task types.

Skill directory structure:
   ~/.claude/skills/<domain>/<skill-name>/skill.md

List available skills:
   ls ~/.claude/skills/

Download skills from the global library:
   Visit: https://github.com/{_GITHUB_OWNER}/claude-global-library

To add a new skill manually:
   1. Create directory: mkdir -p ~/.claude/skills/backend/my-skill
   2. Create skill.md with capabilities, patterns, and tools
   3. The pipeline will auto-discover it on next run

Agents work the same way:
   ~/.claude/agents/<agent-name>/agent.md
"""

# ---------------------------------------------------------------------------
# Helper extraction functions
# ---------------------------------------------------------------------------


def _extract_port(text: str) -> Optional[str]:
    """Try to extract a port number from an error message."""
    import re

    match = re.search(r":(\d{4,5})", text)
    return match.group(1) if match else None


def _extract_model(text: str) -> Optional[str]:
    """Try to extract a model name from an error message."""
    import re

    match = re.search(r"model[:\s'\"]+([a-zA-Z0-9_\-.:]+)", text, re.IGNORECASE)
    return match.group(1) if match else None


def _extract_path(text: str) -> Optional[str]:
    """Try to extract a file path from an error message."""
    import re

    match = re.search(r"['\"]([/\\][^'\"]+)['\"]", text)
    if match:
        return match.group(1)
    match = re.search(r"((?:[A-Za-z]:)?[/\\][^\s:\"']+)", text)
    return match.group(1) if match else None


def _extract_skill(text: str) -> Optional[str]:
    """Try to extract a skill name from an error message."""
    import re

    match = re.search(r"skill[:\s'\"]+([a-zA-Z0-9_\-]+)", text, re.IGNORECASE)
    return match.group(1) if match else None


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len characters, appending '...' if truncated."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


# Make Optional importable without re-importing from typing at call sites
from typing import Optional  # noqa: E402 (placed here to avoid circular-import appearance)
