# pre_tool_enforcer/policies/agent_persona.py
# PreToolUse policy: block general-purpose subagent spawns lacking a library persona,
# and block persona spawns that name the agent but never actually carry its skills.
# Windows-safe: ASCII only, no Unicode characters.

import json
import os
import re

_GENERIC_TYPES = ("general-purpose", "claude", "")
_PERSONA_MARKER = "---persona---"
_ESCAPE_HATCH = "[GENERIC-OK]"

# Auto-exempt pattern: dispatches whose prompt targets writing a brand-new
# skills/{name}/SKILL.md or agents/{name}/agent.md file. There is never a
# persona to inject for these -- the file being authored IS the persona/skill,
# and it does not exist yet. This is the single most common recurring
# generic-dispatch case in this library's domain-creation workflow (7-Phase
# Protocol Phase 2 "Skill Creation" / Phase 5 "Agent Creation"), so it is
# auto-exempted permanently instead of requiring a manual [GENERIC-OK] marker
# on every call. Scoped narrowly to this one path shape so it cannot be used
# to silently bypass the persona requirement for unrelated generic work.
_SKILL_OR_AGENT_AUTHOR_PATTERN = re.compile(
    r"skills[/\\][a-z0-9][a-z0-9\-]*[/\\]SKILL\.md|agents[/\\][a-z0-9][a-z0-9\-]*[/\\]agent\.md",
    re.IGNORECASE,
)

# Persona block body: everything between '---persona---' and the next line
# that is just dashes (the template's closing '---'). MULTILINE + '^-{3,}$'
# tolerates the small whitespace variations real dispatch prompts have,
# rather than requiring the exact spacing shown in ORCHESTRATION_TEMPLATE.md.
_PERSONA_BLOCK_RE = re.compile(r"---persona---(.*?)^-{3,}\s*$", re.DOTALL | re.MULTILINE)

# 'skills:' field value, captured up to the next top-level 'key:' line (or
# end of block). Works for both inline ('skills: [a, b]') and YAML-list
# ('skills:\n  - a\n  - b') forms used across real dispatch prompts.
_SKILLS_FIELD_RE = re.compile(r"skills\s*:\s*(.*?)(?:\n[ \t]*[A-Za-z_][\w-]*\s*:|\Z)", re.DOTALL | re.IGNORECASE)

# A skill slug: lowercase, hyphen-separated words with zero or more hyphens.
# Most real skills in this library are named like 'ai-agents-core' /
# 'system-design', but a few genuinely have no hyphen at all (e.g. 'docker',
# 'kubernetes') -- the quantifier below must be zero-or-more ('*'), not
# one-or-more ('+'), or those skills are silently dropped from the parsed
# declared-skills list even when present verbatim in the skills: field. This
# regex is only ever applied to the already-isolated skills: field capture
# (via _SKILLS_FIELD_RE), so broadening it does not risk matching stray
# words elsewhere in a dispatch prompt.
_SKILL_TOKEN_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")

# 'agent: <name>' line inside the persona block.
_AGENT_NAME_RE = re.compile(r"^\s*agent\s*:\s*([a-z0-9][a-z0-9\-]*)\s*$", re.IGNORECASE | re.MULTILINE)

# The mandated 'WORKING DIRECTORY & LIBRARY PATH: <path>. ...' line every
# dispatch prompt is supposed to start with (ORCHESTRATION_TEMPLATE.md GLOBAL
# LIBRARY PATH MANDATE). Captures the path up to the first '. ' sentence
# break -- real library paths never contain a literal '. ' sequence.
_LIBRARY_PATH_LINE_RE = re.compile(r"WORKING DIRECTORY\s*&\s*LIBRARY PATH\s*:\s*([^\n]+?)(?:\.\s|\n|$)", re.IGNORECASE)

_BLOCK_MSG_NO_PERSONA = (
    "[PRE-TOOL BLOCKED] Generic subagent spawned without a library persona!\n"
    "  Tool       : Agent/Task spawn with subagent_type=general-purpose (or unset)\n"
    "  Problem    : No agents/{name}/agent.md persona was injected into the prompt.\n"
    "  Required   : Route to a library agent, read its Skill Dependencies, then\n"
    "               inject its persona as a '---persona---' YAML block at the top\n"
    "               of the prompt (see ORCHESTRATION_TEMPLATE.md STEP 0.05,\n"
    "               Subagent Dispatch Contract).\n"
    "  Escape hatch: prefix the prompt/description with [GENERIC-OK] for a\n"
    "               genuinely generic one-off task with no matching persona,\n"
    "               OR a recurring task with no persona to inject because the\n"
    "               persona/skill IS what the task produces (e.g. authoring a\n"
    "               new SKILL.md / agent.md for a library that doesn't have\n"
    "               that persona yet).\n"
    "  Note       : Local code exploration should use the built-in 'Explore'\n"
    "               subagent_type instead -- it is not gated by this policy.\n"
    "  Action     : Add subagent_type of a named library agent, or inject the\n"
    "               '---persona---' block, or prefix with [GENERIC-OK]."
)

_BLOCK_MSG_HOLLOW_PERSONA = (
    "[PRE-TOOL BLOCKED] Persona injected but its skills were not actually carried!\n"
    "  Tool       : Agent/Task spawn with subagent_type=general-purpose (or unset)\n"
    "  Problem    : {detail}\n"
    "  Required   : Per ORCHESTRATION_TEMPLATE.md STEP 0.05, the persona block's\n"
    "               'skills:' field must list the agent's full skill set (mandatory\n"
    "               AGENT_USES_SKILL edges + OPTIONAL_SKILL edges), and the prompt\n"
    "               body must instruct the subagent to READ each one at its real\n"
    "               'skills/<name>/SKILL.md' path before doing anything else. A\n"
    "               persona name alone is a hollow dispatch -- the subagent never\n"
    "               receives the skill knowledge it is supposed to apply.\n"
    "  Escape hatch: prefix the prompt/description with [GENERIC-OK] only if this\n"
    "               agent genuinely has zero skill dependencies (rare -- check its\n"
    "               agent.md Skill Dependencies section first)."
)

_BLOCK_MSG_INCOMPLETE_SKILLS = (
    "[PRE-TOOL BLOCKED] Persona's declared skills do not match its real mandatory set!\n"
    "  Tool       : Agent/Task spawn with subagent_type=general-purpose (or unset)\n"
    "  Agent      : {agent_name}\n"
    "  Problem    : knowledge-graph/_master/agents_all.json lists this agent's mandatory\n"
    "               skills as: {mandatory}\n"
    "               but the persona block's 'skills:' field is missing: {missing}\n"
    "  Required   : The 'skills:' field must include EVERY mandatory skill for this\n"
    "               agent (plus any task-relevant optional ones) -- a self-consistent\n"
    "               but incomplete or wrong skill list is still a hollow dispatch, just\n"
    "               one that passes a naive format check. Copy the mandatory list above\n"
    "               into 'skills:' and add a matching 'skills/<name>/SKILL.md' read\n"
    "               instruction for each.\n"
    "  Escape hatch: prefix the prompt/description with [GENERIC-OK] only if this is a\n"
    "               deliberate, reduced-scope dispatch that genuinely does not need the\n"
    "               full mandatory set for this specific subtask."
)


def _resolve_agents_registry(prompt):
    """Best-effort locate and parse knowledge-graph/_master/agents_all.json.

    Tries the GLOBAL_LIBRARY_PATH environment variable first, then the
    'WORKING DIRECTORY & LIBRARY PATH: <path>' line ORCHESTRATION_TEMPLATE.md
    mandates at the top of every dispatch prompt. Returns the parsed list of
    agent records, or None if no candidate path resolves to a readable,
    parseable registry.

    This hook runs globally across every project, not just projects that use
    claude-global-library -- callers MUST treat None as fail-open (skip the
    ground-truth check entirely), never as a reason to block. A project that
    does not use this library, or whose library copy is unreachable for some
    incidental reason, must not have its dispatches blocked by an
    infrastructure lookup failure.
    """
    candidates = []
    env_path = os.environ.get("GLOBAL_LIBRARY_PATH")
    if env_path:
        candidates.append(env_path)
    path_match = _LIBRARY_PATH_LINE_RE.search(prompt)
    if path_match:
        candidates.append(path_match.group(1).strip().strip('"').strip("'"))

    for base in candidates:
        try:
            registry_path = os.path.join(base, "knowledge-graph", "_master", "agents_all.json")
            if not os.path.isfile(registry_path):
                continue
            with open(registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        agents = data.get("agents") if isinstance(data, dict) else data
        if isinstance(agents, list) and agents:
            return agents
    return None


def _find_agent_record(agents, name):
    """Return the agent record whose 'name' field matches (case-insensitive),
    or None if not found. `agents` is the list _resolve_agents_registry returns.
    """
    lowered = name.strip().lower()
    for record in agents:
        if isinstance(record, dict) and str(record.get("name", "")).strip().lower() == lowered:
            return record
    return None


def _extract_agent_name(persona_block_text):
    """Return the 'agent: <name>' value from a persona block, or None."""
    match = _AGENT_NAME_RE.search(persona_block_text)
    return match.group(1).strip().lower() if match else None


def _extract_declared_skills(persona_block_text):
    """Return the deduped, lowercased skill slugs listed in a persona block's
    'skills:' field. Empty list if the field is missing, empty, or unparseable.
    """
    field_match = _SKILLS_FIELD_RE.search(persona_block_text)
    if not field_match:
        return []
    tokens = _SKILL_TOKEN_RE.findall(field_match.group(1))
    declared = []
    for token in tokens:
        lowered = token.lower()
        if lowered not in declared:
            declared.append(lowered)
    return declared


def _skill_read_path_present(prompt, skill):
    """True if the prompt instructs reading skill's real SKILL.md path."""
    pattern = re.compile(r"skills[/\\]" + re.escape(skill) + r"[/\\]SKILL\.md", re.IGNORECASE)
    return bool(pattern.search(prompt))


def check_agent_persona(tool_name, tool_input):
    """PreToolUse policy: block general-purpose subagent spawns lacking a
    real, skill-carrying persona.

    SIBLING IMPLEMENTATION NOTICE: this function is not reachable from any
    live hook (ADR-006, Hook-Free Execution Model -- PreToolUse was
    deregistered 2026-08-04) and is kept only for its own equivalence tests.
    The reachable backstop is the ported `validate_agent_dispatch` MCP tool
    in mcp-pre-tool-gate/server.py (github.com/techdeveloper-org/mcp-pre-tool-gate).
    If you change the semantics here, check whether that port needs the same
    change (and vice versa), or the two copies will silently diverge.

    A general-purpose (or unset) subagent_type must carry a library agent
    persona injected as a '---persona---' YAML block at the top of its
    prompt, per the Subagent Dispatch Contract -- and that block must
    actually carry the agent's skills, not just its name. Three failure
    modes are gated:
      1. No '---persona---' block at all (the original check).
      2. A '---persona---' block present but hollow -- no 'skills:' field,
         an empty one, or skills declared with no matching
         'skills/<name>/SKILL.md' read instruction in the prompt body. A
         persona shell without its skill knowledge defeats the whole point
         of persona injection: the subagent never actually reads the
         domain skill it is supposed to apply.
      3. A '---persona---' block that is internally self-consistent (every
         declared skill has a matching read path) but still WRONG -- it
         names a real library agent yet omits one or more of that agent's
         actual mandatory skills per knowledge-graph/_master/agents_all.json.
         Checks 1-2 only prove the block is well-formed; this check proves
         the skill list is the agent's real one, not just a plausible-looking
         one. This check is fail-open: if the agents_all.json registry
         cannot be located for the current project (see
         _resolve_agents_registry), or the named agent is not found in it
         (e.g. a legitimate project-local custom persona this library does
         not track), the dispatch is allowed through on checks 1-2 alone --
         this hook runs globally across every project, not just ones that
         use claude-global-library, and a registry-lookup failure must never
         become a false-positive block.

    Named built-in subagent types (e.g. Explore, Plan) are never gated. An
    explicit '[GENERIC-OK]' marker in the prompt/description is an escape
    hatch for genuinely generic one-off tasks, or for the rare agent with
    zero real skill dependencies. Dispatches that target writing a new
    skills/{name}/SKILL.md or agents/{name}/agent.md file are auto-exempt
    permanently (no marker needed) via _SKILL_OR_AGENT_AUTHOR_PATTERN,
    since there is never a persona to inject there -- the file being
    authored IS the persona/skill and does not exist yet.

    Args:
        tool_name (str): Name of the tool (must be 'Agent' or 'Task' to trigger).
        tool_input (dict): Tool parameters dict with 'subagent_type' and
            'prompt' (or 'description') keys. Any non-dict value (None,
            malformed payload) is treated as fail-open, never as a block.

    Returns:
        tuple: (blocked: bool, message: str)
    """
    if tool_name not in ("Agent", "Task"):
        return False, ""

    if not isinstance(tool_input, dict):
        return False, ""

    subagent_type = str(tool_input.get("subagent_type") or "").strip().lower()
    if subagent_type not in _GENERIC_TYPES:
        return False, ""

    prompt = str(tool_input.get("prompt") or tool_input.get("description") or "")

    if _ESCAPE_HATCH in prompt:
        return False, ""

    if _PERSONA_MARKER not in prompt:
        # The skill/agent-authoring exemption only applies to prompts with no
        # persona block: its premise is "the target agent.md/SKILL.md doesn't
        # exist yet, so there is nothing to inject". Once a '---persona---'
        # block is present, that premise no longer holds -- the dispatch IS a
        # routed persona call, and a 'skills/<name>/SKILL.md' substring inside
        # it is far more likely to be a legitimate READ instruction than an
        # authoring target, so it must go through full hollow-persona
        # validation below rather than short-circuit past it.
        if _SKILL_OR_AGENT_AUTHOR_PATTERN.search(prompt):
            return False, ""
        return True, _BLOCK_MSG_NO_PERSONA

    block_match = _PERSONA_BLOCK_RE.search(prompt)
    if not block_match:
        return True, _BLOCK_MSG_HOLLOW_PERSONA.format(
            detail="'---persona---' marker found but the block never closes with "
            "a matching '---' line, so no skills: field could be parsed."
        )

    declared_skills = _extract_declared_skills(block_match.group(1))
    if not declared_skills:
        return True, _BLOCK_MSG_HOLLOW_PERSONA.format(
            detail="the persona block has no 'skills:' field (or it is empty) -- "
            "no skill knowledge is being injected into the subagent."
        )

    missing = [s for s in declared_skills if not _skill_read_path_present(prompt, s)]
    if missing:
        return True, _BLOCK_MSG_HOLLOW_PERSONA.format(
            detail="skills declared in the persona block have no matching "
            "'skills/<name>/SKILL.md' read instruction in the prompt: " + ", ".join(missing)
        )

    agents = _resolve_agents_registry(prompt)
    if agents is not None:
        agent_name = _extract_agent_name(block_match.group(1))
        if agent_name is not None:
            record = _find_agent_record(agents, agent_name)
            if record is not None:
                # In-domain mandatory skills live in "mandatory_skills"; a skill whose
                # SKILL.md sits in a different domain's KG (no local graph edge to draw)
                # is instead recorded under "cross_domain_mandatory_skills" -- both are
                # equally mandatory and must both be enforced here, or a persona can
                # silently omit a cross-domain skill its own agent.md requires.
                in_domain = record.get("mandatory_skills")
                cross_domain = record.get("cross_domain_mandatory_skills")
                mandatory = list(in_domain or [])
                for skill in cross_domain or []:
                    if skill not in mandatory:
                        mandatory.append(skill)
                if isinstance(mandatory, list) and mandatory:
                    declared_set = set(declared_skills)
                    missing_mandatory = [s for s in mandatory if s.lower() not in declared_set]
                    if missing_mandatory:
                        return True, _BLOCK_MSG_INCOMPLETE_SKILLS.format(
                            agent_name=agent_name,
                            mandatory=", ".join(mandatory),
                            missing=", ".join(missing_mandatory),
                        )

    return False, ""
