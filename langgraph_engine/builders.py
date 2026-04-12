"""
Builder Pattern implementations for pipeline-generated text objects.

Three builders for commonly constructed objects in the LangGraph pipeline:
  - CommitMessageBuilder  - builds semantic git commit messages
  - PRBodyBuilder         - builds GitHub pull request descriptions
  - IssueBodyBuilder      - builds GitHub issue descriptions

Design:
  - Fluent API (method chaining) for ergonomic call sites
  - Validation in build() raises ValueError for missing required fields
  - ASCII-safe output (cp1252 compatible for Windows)
  - Each builder is usable standalone - no pipeline dependencies

Usage examples:

    from langgraph_engine.builders import CommitMessageBuilder, PRBodyBuilder, IssueBodyBuilder

    # Commit message
    title = (
        CommitMessageBuilder()
        .type("fix")
        .scope("github")
        .subject("stash detection using stdout and stderr")
        .build()
    )
    # -> "fix(github): stash detection using stdout and stderr"

    # PR body
    body = (
        PRBodyBuilder()
        .resolves(42)
        .changes_summary("Replaced manual string concat with builder pattern")
        .change_type("Enhancement")
        .build()
    )

    # Issue body
    body = (
        IssueBodyBuilder()
        .description("Builders module missing from engine")
        .task_summary("Add Builder Pattern module to langgraph_engine")
        .implementation_plan("Create builders.py with 3 builder classes")
        .build()
    )
"""

from typing import List, Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ascii_safe(text: str) -> str:
    """Replace or remove non-ASCII characters to keep output cp1252-safe."""
    return text.encode("ascii", errors="replace").decode("ascii")


# ---------------------------------------------------------------------------
# CommitMessageBuilder
# ---------------------------------------------------------------------------


class CommitMessageBuilder:
    """Builds a semantic (Conventional Commits style) git commit message.

    Required fields:
        subject  - the short, imperative description

    Optional fields:
        type     - conventional commit type (feat, fix, refactor, chore, ...)
        scope    - component or module the change affects
        body     - longer description appended after a blank line
        footer   - issue/PR references, breaking-change notices

    The final message produced by build() is max 72 chars on the first line
    (title) to respect git log display standards.

    Example outputs:
        "fix(github): stash detection using stdout and stderr"
        "feat: add builder pattern module"
        "refactor(llm_call): extract provider selection into factory"
    """

    ALLOWED_TYPES = {
        "feat",
        "fix",
        "refactor",
        "chore",
        "docs",
        "style",
        "test",
        "perf",
        "ci",
        "build",
        "revert",
    }

    def __init__(self) -> None:
        self._type: Optional[str] = None
        self._scope: Optional[str] = None
        self._subject: Optional[str] = None
        self._body: Optional[str] = None
        self._footer: Optional[str] = None

    # --- fluent setters ---

    def type(self, commit_type: str) -> "CommitMessageBuilder":
        """Set the conventional commit type (feat, fix, chore, ...).

        The value is lowercased.  Unknown types are accepted (no enum
        restriction) so callers can use project-specific types.
        """
        self._type = commit_type.strip().lower()
        return self

    def scope(self, scope: str) -> "CommitMessageBuilder":
        """Set the optional scope component (e.g. 'github', 'llm_call')."""
        self._scope = scope.strip()
        return self

    def subject(self, subject: str) -> "CommitMessageBuilder":
        """Set the short, imperative description (required)."""
        self._subject = subject.strip()
        return self

    def body(self, body: str) -> "CommitMessageBuilder":
        """Set the optional multi-line body appended after a blank line."""
        self._body = body.strip()
        return self

    def footer(self, footer: str) -> "CommitMessageBuilder":
        """Set the optional footer (issue refs, breaking-change, co-authors)."""
        self._footer = footer.strip()
        return self

    # --- build ---

    def build(self) -> str:
        """Validate and assemble the commit message.

        Returns:
            ASCII-safe commit message string.

        Raises:
            ValueError: when subject is not provided.
        """
        if not self._subject:
            raise ValueError("CommitMessageBuilder: subject is required")

        # Assemble title
        if self._type:
            if self._scope:
                title = f"{self._type}({self._scope}): {self._subject}"
            else:
                title = f"{self._type}: {self._subject}"
        else:
            title = self._subject

        # Enforce 72-char title limit (same rule as generate_llm_commit_title)
        if len(title) > 72:
            title = title[:69] + "..."

        parts = [title]

        if self._body:
            parts.append("")
            parts.append(self._body)

        if self._footer:
            parts.append("")
            parts.append(self._footer)

        return _ascii_safe("\n".join(parts))


# ---------------------------------------------------------------------------
# PRBodyBuilder
# ---------------------------------------------------------------------------


class PRBodyBuilder:
    """Builds a GitHub pull request description.

    Required fields:
        issue_number  - the GitHub issue this PR resolves

    Optional fields:
        changes_summary   - human-readable summary of what was changed
        change_types      - list of selected change categories (see CHANGE_TYPES)
        testing_notes     - extra testing notes appended to the Testing section
        footer_note       - override the default footer attribution line

    Example output:
        ## Resolves #42
        ...
    """

    CHANGE_TYPES = [
        "Bug fix",
        "New feature",
        "Enhancement",
        "Documentation update",
        "Refactoring",
        "Performance improvement",
        "CI/CD change",
    ]

    def __init__(self) -> None:
        self._issue_number: Optional[int] = None
        self._changes_summary: Optional[str] = None
        self._change_types: List[str] = []
        self._testing_notes: Optional[str] = None
        self._footer_note: Optional[str] = None

    # --- fluent setters ---

    def resolves(self, issue_number: int) -> "PRBodyBuilder":
        """Set the GitHub issue number this PR resolves (required)."""
        self._issue_number = issue_number
        return self

    def changes_summary(self, summary: str) -> "PRBodyBuilder":
        """Set the human-readable summary of what was changed."""
        self._changes_summary = summary.strip()
        return self

    def change_type(self, label: str) -> "PRBodyBuilder":
        """Mark a single change type as selected (checked in the checklist).

        Call multiple times to mark several types.
        Accepts any string value; known values from CHANGE_TYPES receive a
        checked checkbox, unknown values are appended as new checked items.
        """
        label = label.strip()
        if label and label not in self._change_types:
            self._change_types.append(label)
        return self

    def testing_notes(self, notes: str) -> "PRBodyBuilder":
        """Append additional testing notes below the standard testing bullets."""
        self._testing_notes = notes.strip()
        return self

    def footer_note(self, note: str) -> "PRBodyBuilder":
        """Override the default 'Automated by ...' footer line."""
        self._footer_note = note.strip()
        return self

    # --- build ---

    def build(self) -> str:
        """Validate and assemble the PR description.

        Returns:
            ASCII-safe PR body markdown string.

        Raises:
            ValueError: when issue_number is not provided.
        """
        if self._issue_number is None:
            raise ValueError("PRBodyBuilder: issue_number is required (call .resolves(n))")

        parts: List[str] = []

        # Resolves section
        parts.append(f"## Resolves #{self._issue_number}")
        parts.append("")

        # Changes Made
        parts.append("## Changes Made")
        if self._changes_summary:
            parts.append(self._changes_summary)
        else:
            parts.append("See issue for details.")

        # Type of Change checklist
        parts.append("")
        parts.append("## Type of Change")

        all_types = list(self.CHANGE_TYPES)
        # Append any extra types the caller added that are not in the defaults
        for ct in self._change_types:
            if ct not in all_types:
                all_types.append(ct)

        for ct in all_types:
            checkbox = "[x]" if ct in self._change_types else "[ ]"
            parts.append(f"- {checkbox} {ct}")

        # Testing section
        parts.append("")
        parts.append("## Testing")
        parts.append("- Changes have been tested locally")
        parts.append("- No breaking changes introduced")
        if self._testing_notes:
            parts.append(self._testing_notes)

        # Footer
        parts.append("")
        footer = self._footer_note or "Automated by Claude Workflow Engine"
        parts.append(footer)

        return _ascii_safe("\n".join(parts))


# ---------------------------------------------------------------------------
# IssueBodyBuilder
# ---------------------------------------------------------------------------


class IssueBodyBuilder:
    """Builds a GitHub issue description.

    Required fields:
        description  - the main body text describing the issue

    Optional fields:
        task_summary          - one-line summary shown above the description
        implementation_plan   - step-by-step plan appended as its own section
        acceptance_criteria   - list of acceptance criteria items
        footer_note           - override the default 'Automated by ...' line

    Example output:
        ## Task Summary
        Add builder pattern module to langgraph_engine
        ...
    """

    def __init__(self) -> None:
        self._description: Optional[str] = None
        self._task_summary: Optional[str] = None
        self._implementation_plan: Optional[str] = None
        self._acceptance_criteria: List[str] = []
        self._footer_note: Optional[str] = None

    # --- fluent setters ---

    def description(self, description: str) -> "IssueBodyBuilder":
        """Set the main issue description text (required)."""
        self._description = description.strip()
        return self

    def task_summary(self, summary: str) -> "IssueBodyBuilder":
        """Set the short task summary shown at the top of the issue."""
        self._task_summary = summary.strip()
        return self

    def implementation_plan(self, plan: str) -> "IssueBodyBuilder":
        """Set an implementation plan appended as its own section."""
        self._implementation_plan = plan.strip()
        return self

    def acceptance_criterion(self, criterion: str) -> "IssueBodyBuilder":
        """Add a single acceptance criterion.  Call multiple times for a list."""
        criterion = criterion.strip()
        if criterion:
            self._acceptance_criteria.append(criterion)
        return self

    def footer_note(self, note: str) -> "IssueBodyBuilder":
        """Override the default 'Automated by ...' footer line."""
        self._footer_note = note.strip()
        return self

    # --- build ---

    def build(self) -> str:
        """Validate and assemble the issue body.

        Returns:
            ASCII-safe issue body markdown string.

        Raises:
            ValueError: when description is not provided.
        """
        if not self._description:
            raise ValueError("IssueBodyBuilder: description is required")

        parts: List[str] = []

        # Task Summary section
        parts.append("## Task Summary")
        parts.append(self._task_summary or "See description for details.")

        # Description section
        parts.append("")
        parts.append("## Description")
        parts.append(self._description)

        # Implementation Plan section (optional)
        if self._implementation_plan:
            parts.append("")
            parts.append("## Implementation Plan")
            parts.append(self._implementation_plan)

        # Acceptance Criteria section (optional)
        if self._acceptance_criteria:
            parts.append("")
            parts.append("## Acceptance Criteria")
            for criterion in self._acceptance_criteria:
                parts.append(f"- [ ] {criterion}")

        # Footer
        parts.append("")
        parts.append("## Automated by")
        footer = self._footer_note or "Generated by Claude Workflow Engine execution pipeline"
        parts.append(footer)

        return _ascii_safe("\n".join(parts))
