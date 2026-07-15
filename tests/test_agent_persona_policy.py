"""
test_agent_persona_policy.py - Unit tests for
hooks/pre_tool_enforcer/policies/agent_persona.py

Covers check_agent_persona: blocks general-purpose (or unset) subagent_type
spawns that lack an injected library persona, allows named built-in
subagent types, allows the '---persona---' and '[GENERIC-OK]' escape
hatches, and never raises on malformed input.

Windows-safe: ASCII only, no Unicode characters.
"""

import importlib.util as _ilu
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = _REPO_ROOT / "hooks" / "pre_tool_enforcer" / "policies" / "agent_persona.py"

_spec = _ilu.spec_from_file_location("agent_persona", _MODULE_PATH)
agent_persona = _ilu.module_from_spec(_spec)
sys.modules["agent_persona"] = agent_persona
_spec.loader.exec_module(agent_persona)


class TestCheckAgentPersona:
    def test_blocks_general_purpose_without_persona(self):
        blocked, msg = agent_persona.check_agent_persona(
            "Agent",
            {"subagent_type": "general-purpose", "prompt": "go research X"},
        )
        assert blocked is True
        assert "PRE-TOOL BLOCKED" in msg

    def test_allows_when_persona_marker_present(self):
        blocked, msg = agent_persona.check_agent_persona(
            "Agent",
            {
                "subagent_type": "general-purpose",
                "prompt": "---persona---\nagent: deep-web-researcher\n---\nresearch X",
            },
        )
        assert blocked is False
        assert msg == ""

    def test_allows_when_generic_ok_escape_hatch_present(self):
        blocked, msg = agent_persona.check_agent_persona(
            "Agent",
            {"subagent_type": "general-purpose", "prompt": "[GENERIC-OK] one-off cleanup task"},
        )
        assert blocked is False
        assert msg == ""

    def test_allows_named_builtin_subagent_type(self):
        blocked, msg = agent_persona.check_agent_persona(
            "Agent",
            {"subagent_type": "Explore", "prompt": "find config loader"},
        )
        assert blocked is False
        assert msg == ""

    def test_ignores_non_agent_tool_names(self):
        blocked, msg = agent_persona.check_agent_persona(
            "Bash",
            {"subagent_type": "general-purpose", "prompt": "go research X"},
        )
        assert blocked is False
        assert msg == ""

    def test_blocks_task_tool_with_general_purpose(self):
        blocked, msg = agent_persona.check_agent_persona(
            "Task",
            {"subagent_type": "general-purpose", "prompt": "go research X"},
        )
        assert blocked is True
        assert "PRE-TOOL BLOCKED" in msg

    def test_blocks_when_subagent_type_missing_entirely(self):
        blocked, msg = agent_persona.check_agent_persona(
            "Agent",
            {"prompt": "go research X"},
        )
        assert blocked is True

    def test_uses_description_when_prompt_absent(self):
        blocked, msg = agent_persona.check_agent_persona(
            "Agent",
            {"subagent_type": "general-purpose", "description": "---persona---\nagent: x\n---\ndo it"},
        )
        assert blocked is False

    def test_none_tool_input_does_not_raise(self):
        blocked, msg = agent_persona.check_agent_persona("Agent", None)
        assert blocked is False
        assert msg == ""

    def test_malformed_subagent_type_does_not_raise(self):
        blocked, msg = agent_persona.check_agent_persona(
            "Agent",
            {"subagent_type": 12345, "prompt": None},
        )
        assert isinstance(blocked, bool)

    def test_empty_dict_tool_input_does_not_raise(self):
        blocked, msg = agent_persona.check_agent_persona("Agent", {})
        assert blocked is True

    def test_non_dict_tool_input_does_not_raise(self):
        blocked, msg = agent_persona.check_agent_persona("Agent", "not-a-dict")
        assert blocked is False
        assert msg == ""
