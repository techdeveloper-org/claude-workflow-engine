"""
REMOVED (v1.15.0) -- Step 6: Skill Validation & Download

This module was removed as dead code. Skills and agents already exist in
~/.claude/skills/ and ~/.claude/agents/ -- no runtime download or validation
is needed. The Step 0 orchestration subprocess handles all skill selection.

If you see this file being imported, that import is stale and should be removed.
"""

raise ImportError(
    "step6_skill_validation_download is removed (v1.15.0). "
    "Skills are pre-installed in ~/.claude/skills/; no runtime validation needed."
)
