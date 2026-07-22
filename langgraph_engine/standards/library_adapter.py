"""standards/library_adapter.py -- LibrarySkillStandardsAdapter (ADR-4, C12).

Sources framework-tier standards content from the sibling claude-global-library's
maintained skill files instead of hand-authored per-framework docs (HLD Section
5, ADR-4). Reuses the ADR-1 ``ResourceResolver`` (FR-1) for all file access; this
module contains no filesystem or network logic of its own.

Priority: 1.5 -- between framework=2 (an explicit bundled ``docs/{fw}-standards.md``
still wins) and language=1 (the floor when no library skill is mapped).

Also defines ``LibrarySkillLanguageAdapter`` -- the same pattern one tier down,
sourcing language-tier standards content from the sibling library's ``*-core``
skills at priority 0.5, one rung below the bundled ``docs/{lang}.md`` doc
(``PRIORITY_LANGUAGE=1``) so an explicit bundled language doc still wins a
conflict, mirroring how ``PRIORITY_FRAMEWORK=2`` outranks the framework
adapter's ``PRIORITY_LIBRARY_SKILL=1.5`` above.

Windows-safe: ASCII only (cp1252 compatible).
"""

import re
from typing import Any, Dict, List, Tuple

from langgraph_engine.core.logger_factory import get_logger
from langgraph_engine.library.resolver import LibrarySetupError, build_default_resolver

logger = get_logger(__name__)

PRIORITY_LIBRARY_SKILL = 1.5
PRIORITY_LIBRARY_LANGUAGE_SKILL = 0.5

# (project_type, framework) -> library skill name under skills/{name}/SKILL.md.
# Every entry below was verified against a real file in the sibling
# claude-global-library checkout before being added (see comment on each
# line). Frameworks with no matching library skill are intentionally
# omitted -- the adapter returns [] for them (ADR-4 accepted trade-off),
# which is a safe no-op that falls through to the language-level standard.
_FRAMEWORK_SKILL_MAP: Dict[Tuple[str, str], str] = {
    # verified: skills/fastapi-core/SKILL.md exists
    ("python", "fastapi"): "fastapi-core",
    # verified: skills/langgraph-core/SKILL.md exists
    ("python", "langgraph"): "langgraph-core",
    # verified: skills/langchain-core/SKILL.md exists
    ("python", "langchain"): "langchain-core",
    # verified: skills/java-spring-boot-microservices/SKILL.md exists
    ("java", "spring-boot"): "java-spring-boot-microservices",
    # verified: skills/react-core/SKILL.md exists
    ("javascript", "react"): "react-core",
    ("typescript", "react"): "react-core",
    # verified: skills/angular-core/SKILL.md exists
    ("javascript", "angular"): "angular-core",
    ("typescript", "angular"): "angular-core",
    # verified: skills/nextjs-core/SKILL.md exists
    ("javascript", "nextjs"): "nextjs-core",
    ("typescript", "nextjs"): "nextjs-core",
}

# Library skills follow a fixed section convention (rules/skill-format.md):
# a "## Mathematical Foundations" heading always precedes the applied/
# topic sections and always ends where the next top-level "## " heading
# begins. That section is deep-math derivation content, not coding
# standards, so it is stripped -- this is the ADR-4 "extract only
# standards-relevant headings" mitigation, implemented as a single
# heading-bounded strip rather than a per-framework parser.
_MATH_SECTION_RE = re.compile(r"^## Mathematical Foundations$.*?(?=^## |\Z)", re.DOTALL | re.MULTILINE)


def _extract_standards_content(raw_content: str) -> str:
    """Strip the math-derivation section, keep the rest of the skill as-is.

    Args:
        raw_content: Full ``SKILL.md`` text as read by the resolver.

    Returns:
        The skill content with its "## Mathematical Foundations" section
        removed. If the heading is absent, the content is returned unchanged.
    """
    return _MATH_SECTION_RE.sub("", raw_content, count=1)


class LibrarySkillStandardsAdapter:
    """Adapter (HLD Section 6.2) translating a library ``SKILL.md`` into a
    standards-tier entry at priority 1.5. Implements the Section 7.4 contract.
    """

    def load(self, project_type: str, framework: str) -> List[Dict[str, Any]]:
        """Load framework standards content sourced from a library skill.

        Args:
            project_type: Language string from ``detect_project_type()``.
            framework: Framework string from ``detect_framework()``.

        Returns:
            A single-item list with keys ``id``, ``source``, ``file``,
            ``content``, ``priority``, or ``[]`` when no mapping exists,
            the sibling library is unavailable, or the mapped skill cannot
            be resolved. Never raises (Section 7.4 MUST NOT).
        """
        skill_name = _FRAMEWORK_SKILL_MAP.get((project_type, framework))
        if not skill_name:
            return []

        try:
            resolver = build_default_resolver()
            resource = resolver.fetch_skill(skill_name)
        except LibrarySetupError as exc:
            logger.debug(f"[library_adapter] skill '{skill_name}' unavailable: {exc}")
            return []

        content = _extract_standards_content(resource.content)

        return [
            {
                "id": "library_skill_{}".format(framework),
                "source": "library_skill_standards",
                "file": resource.path_or_url,
                "content": content,
                "priority": PRIORITY_LIBRARY_SKILL,
            }
        ]


# project_type -> library skill name under skills/{name}/SKILL.md, for the
# language tier. Every entry below was verified against a real file in the
# sibling claude-global-library checkout before being added (see comment on
# each line). A csharp-core-equivalent skill does not exist in the sibling
# library at the time this map was built, so "csharp" is intentionally
# omitted -- the adapter returns [] for it (same ADR-4 accepted trade-off as
# the framework map above), a safe no-op that leaves the language tier to
# whatever bundled docs/{lang}.md already provides.
_LANGUAGE_SKILL_MAP: Dict[str, str] = {
    # verified: skills/python-core/SKILL.md exists
    "python": "python-core",
    # verified: skills/typescript-core/SKILL.md exists
    "typescript": "typescript-core",
    # verified: skills/javascript-core/SKILL.md exists
    "javascript": "javascript-core",
    # verified: skills/go-runtime-internals-core/SKILL.md exists
    "go": "go-runtime-internals-core",
    # verified: skills/rust-ownership-formal-core/SKILL.md exists
    "rust": "rust-ownership-formal-core",
    # verified: skills/java-design-patterns-core/SKILL.md exists
    "java": "java-design-patterns-core",
}


class LibrarySkillLanguageAdapter:
    """Adapter (HLD Section 6.2 pattern, one tier down) translating a library
    ``SKILL.md`` into a language-tier standards entry at priority 0.5.

    Sits one rung below the bundled ``docs/{lang}.md`` doc (``PRIORITY_LANGUAGE
    = 1``) rather than sharing its priority slot: both sources are loaded
    unconditionally when a mapping exists (same additive-then-rank-by-priority
    design as the framework tier above), so an explicit bundled language doc
    always wins a conflicting rule, while the library-sourced skill still
    contributes non-conflicting content and still outranks having nothing at
    all for languages with no bundled doc.
    """

    def load(self, project_type: str) -> List[Dict[str, Any]]:
        """Load language standards content sourced from a library skill.

        Args:
            project_type: Language string from ``detect_project_type()``.

        Returns:
            A single-item list with keys ``id``, ``source``, ``file``,
            ``content``, ``priority``, or ``[]`` when no mapping exists,
            the sibling library is unavailable, or the mapped skill cannot
            be resolved. Never raises (same Section 7.4 MUST NOT contract as
            ``LibrarySkillStandardsAdapter``).
        """
        skill_name = _LANGUAGE_SKILL_MAP.get(project_type)
        if not skill_name:
            return []

        try:
            resolver = build_default_resolver()
            resource = resolver.fetch_skill(skill_name)
        except LibrarySetupError as exc:
            logger.debug(f"[library_adapter] language skill '{skill_name}' unavailable: {exc}")
            return []

        content = _extract_standards_content(resource.content)

        return [
            {
                "id": "library_language_{}".format(project_type),
                "source": "library_language_standards",
                "file": resource.path_or_url,
                "content": content,
                "priority": PRIORITY_LIBRARY_LANGUAGE_SKILL,
            }
        ]
