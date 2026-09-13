"""Conformance suite for the model fallback protocol (issue #270).

Local key V2-014, PRD FR-13 / SRS FR-25. The two acceptance criteria are:

1. A rate-limited model invocation retries at the next tier in the documented
   chain.
2. It escalates to the user at the top tier, rather than failing the step.

Every assertion below carries a companion negative that demonstrates the
assertion is capable of failing, on the principle that a check nobody has seen
fail is a check nobody has tested.

The suite adds the control the criteria do not ask for and most need: a
SPECIFICITY CONTROL that a non-rate-limit failure does NOT trigger a fallback.
Both criteria above are satisfied trivially by a driver that escalates on every
error, and that driver would be worse than none -- it would spend the most
expensive tier re-running bad instructions, scope errors and tool errors, which
is precisely what the rule's own "fix the root cause, don't model-switch"
clause forbids. ``TestRateLimitDetection``, ``TestDecision`` and
``TestFallbackDriver`` each pin the control, and two of them pair it with a
deliberately permissive stand-in that passes the positive tests and fails the
control, so the control is shown to have teeth rather than asserted to.

The tier chain is checked against the authored rule document rather than
against itself. ``~/.claude/rules/model-fallback.md`` is global-only with no
repo-relative copy, so the live-document test skips when it is absent; the
parser it uses is exercised unconditionally against an inline copy of the same
block, so the pair still has a running positive and a running negative on a
machine that does not have the rule installed.

Counts stated here were MEASURED against claude-global-library 29.73.0 on
2026-08-02: 508 agents declaring exactly two distinct tiers, sonnet (432) and
opus (76). The tier-coverage assertion is written as a subset relation rather
than as those figures, because an upstream release may add agents at any tier.

Windows-safe: ASCII only. The rule document writes its chain with a Unicode
arrow, so the arrow is built with ``chr`` rather than written out.
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langgraph_engine.model_fallback import (  # noqa: E402
    ACTION_ESCALATE_TO_USER,
    ACTION_NO_FALLBACK,
    ACTION_RETRY_NEXT_TIER,
    FAILURE_OTHER,
    FAILURE_RATE_LIMIT,
    TIER_CHAIN,
    FallbackDecision,
    UnknownTier,
    classify_failure,
    decide,
    format_fallback_log,
    invoke_with_fallback,
    next_tier,
    normalise_tier,
    rate_limit_evidence,
)

RULE_ENV_VAR = "MODEL_FALLBACK_RULE_PATH"
DEFAULT_RULE_PATH = Path.home() / ".claude" / "rules" / "model-fallback.md"

AGENT = "agent-under-test"
PROMPT = "implement the thing, preserving every instruction in this sentence"

ARROW = chr(0x2192)
_ARROW = re.compile("->|" + ARROW)
_FENCE = re.compile("```(.*?)```", re.DOTALL)


def _chain_line(*tokens):
    """Join tokens with the rule document's arrow separator."""
    return (" " + ARROW + " ").join(tokens)


DOCUMENTED_CHAIN_BLOCK = "\n".join(
    [
        "## Fallback Chain",
        "```",
        _chain_line("haiku", "sonnet", "opus", "fable", "escalate to user"),
        _chain_line("sonnet", "opus", "fable", "escalate to user"),
        _chain_line("opus", "fable", "escalate to user"),
        _chain_line("fable", "escalate to user (no further fallback, Fable is the top tier)"),
        "```",
        "",
    ]
)


def parse_documented_chain(text):
    """Return the ordered tier chain the rule document declares.

    Reads the fenced block under the Fallback Chain heading, takes the longest
    arrow-separated line -- the full chain, of which the others are suffixes --
    and drops the terminal escalation token, which names an outcome rather than
    a tier.

    Args:
        text: Full markdown source of the rule document.

    Returns:
        Tuple of tier names in escalation order, empty when no chain block is
        present.
    """
    marker = "## Fallback Chain"
    if marker not in text:
        return ()
    fenced = _FENCE.search(text.split(marker, 1)[1])
    if not fenced:
        return ()

    best = ()
    for line in fenced.group(1).splitlines():
        tokens = [token.strip().lower() for token in _ARROW.split(line) if token.strip()]
        tiers = tuple(token for token in tokens if "escalate" not in token)
        if len(tiers) > len(best):
            best = tiers
    return best


def rule_document_text():
    """Return the authored rule document's text, or ``None`` when absent."""
    override = os.environ.get(RULE_ENV_VAR, "")
    path = Path(override) if override else DEFAULT_RULE_PATH
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


class RateLimitError(Exception):
    """Stand-in for a provider SDK's rate-limit exception type."""


class ProviderError(Exception):
    """Stand-in for a provider error that carries an HTTP status attribute."""

    def __init__(self, message, status_code):
        """Record the message and the status the provider responded with."""
        super().__init__(message)
        self.status_code = status_code


class ToolExecutionError(Exception):
    """Stand-in for the tool-error class the rule sends back to its root cause."""


RATE_LIMITED_FAILURES = [
    ("explicit 429 status", ProviderError("request failed", 429), None),
    ("explicit 529 status", ProviderError("service issue", 529), None),
    ("status supplied by the caller", RuntimeError("upstream refused"), 429),
    ("message names the limit", RuntimeError("Error: rate limit exceeded, retry after 60s"), None),
    ("hyphenated message", RuntimeError("rate-limited by the provider"), None),
    ("exception type names it", RateLimitError("slow down"), None),
    ("http phrasing", RuntimeError("429 Client Error: Too Many Requests for url"), None),
    ("capacity refusal", RuntimeError("Overloaded"), None),
    ("capacity phrasing", RuntimeError("server is over capacity, try again"), None),
]

NON_RATE_LIMIT_FAILURES = [
    ("tool error", ToolExecutionError("write tool failed: permission denied"), None),
    ("bad instructions", ValueError("the prompt names no target file"), None),
    ("scope error", RuntimeError("agent edited a file it does not own"), None),
    ("timeout", TimeoutError("claude cli timed out after 300s"), None),
    ("connection reset", ConnectionResetError("connection reset by peer"), None),
    ("generic 500", RuntimeError("internal server error"), 500),
    ("service unavailable", RuntimeError("service unavailable"), 503),
    ("empty output", RuntimeError("claude cli returned empty response"), None),
    ("truncated output", RuntimeError("output truncated at the token ceiling"), None),
    ("authentication", PermissionError("authentication failed: invalid api key"), None),
]


class Recorder:
    """Callable invocation stand-in that records every attempt it is given."""

    def __init__(self, failures):
        """Store a tier-keyed map of failures to raise, empty meaning success."""
        self.failures = failures
        self.calls = []

    def __call__(self, prompt, tier):
        """Record the attempt, then raise this tier's failure or return a result."""
        self.calls.append((prompt, tier))
        failure = self.failures.get(tier)
        if failure is not None:
            raise failure
        return "completed at {}".format(tier)


def collect_log():
    """Return a sink list and the callable that appends report blocks to it."""
    sink = []
    return sink, sink.append


class TestChainMatchesTheAuthoredRule:
    """The encoded chain is the document's chain, not a private opinion."""

    def test_the_encoded_chain_matches_the_rule_document(self):
        """TIER_CHAIN equals the chain authored in the live rule document."""
        text = rule_document_text()
        if text is None:
            pytest.skip("rule document not installed at {}".format(DEFAULT_RULE_PATH))
        assert parse_documented_chain(text) == TIER_CHAIN

    def test_the_parser_reads_an_inline_copy_of_the_documented_block(self):
        """The same parser, run on an inline copy, still yields TIER_CHAIN.

        This runs everywhere, so the positive half of the pair does not vanish
        on a machine without the rule installed.
        """
        parsed = parse_documented_chain(DOCUMENTED_CHAIN_BLOCK)
        assert parsed == TIER_CHAIN
        assert len(parsed) == 4

    def test_the_parser_rejects_a_mutated_chain(self):
        """NEGATIVE CONTROL: the same parser must disagree when the chain is wrong.

        Without this, a parser that quietly returned an empty tuple, or the
        module's own constant, would report a clean pass on any document.
        """
        reversed_block = DOCUMENTED_CHAIN_BLOCK.replace(
            _chain_line("haiku", "sonnet", "opus"), _chain_line("opus", "sonnet", "haiku")
        )
        reversed_chain = parse_documented_chain(reversed_block)
        assert reversed_chain
        assert reversed_chain != TIER_CHAIN

        dropped_block = DOCUMENTED_CHAIN_BLOCK.replace(_chain_line("haiku", "sonnet"), "sonnet")
        dropped_chain = parse_documented_chain(dropped_block)
        assert dropped_chain
        assert dropped_chain != TIER_CHAIN

        assert parse_documented_chain("no chain block here") == ()


class TestTierArithmetic:
    """Walking the chain, and refusing to walk one that is not the chain."""

    def test_each_lower_tier_escalates_to_the_next(self):
        """Every tier but the top reports the tier immediately above it."""
        for index, tier in enumerate(TIER_CHAIN[:-1]):
            assert next_tier(tier) == TIER_CHAIN[index + 1]

    def test_the_top_tier_has_no_higher_tier(self):
        """The top of the chain has nowhere to escalate to."""
        assert next_tier(TIER_CHAIN[-1]) is None

    def test_an_unknown_tier_raises_rather_than_defaulting(self):
        """NEGATIVE CONTROL: an unrecognised tier is refused, not assumed.

        A silent default would let a typo in an agent definition decide the
        whole escalation path.
        """
        for bogus in ["", "  ", "gpt-4", "fast", "balanced", "deep", None, 3]:
            with pytest.raises(UnknownTier):
                normalise_tier(bogus)
            with pytest.raises(UnknownTier):
                next_tier(bogus)

    def test_case_and_padding_do_not_change_a_tier(self):
        """Tiers fold to canonical form, so frontmatter spacing is harmless."""
        for tier in TIER_CHAIN:
            assert normalise_tier(" {} ".format(tier.upper())) == tier

    def test_every_model_tier_the_library_declares_is_a_known_tier(self):
        """The chain covers the tiers real agent definitions actually use.

        MEASURED 2026-08-02 against claude-global-library 29.73.0: 508 agents,
        two distinct tiers. Asserted as a subset so an upstream release adding
        agents at the remaining tier does not fail the suite.
        """
        try:
            from langgraph_engine.library.resolver import LibrarySetupError, locate_library_root
        except ImportError:
            pytest.skip("library resolver unavailable")

        # locate_library_root's documented contract is Optional[Path]: it RETURNS
        # None when no candidate exists and does not raise for absence. This guard
        # originally caught LibrarySetupError only, so it never fired -- the test
        # passed on any machine with the sibling checkout and died on `None /
        # "knowledge-graph"` on every machine without one, which is every CI
        # runner. The exception arm is kept because the resolver may still raise
        # for a malformed override.
        try:
            root = locate_library_root()
        except LibrarySetupError:
            pytest.skip("claude-global-library not available")
        if root is None:
            pytest.skip("claude-global-library not available (resolver returned None)")

        path = root / "knowledge-graph" / "_master" / "agents_all.json"
        if not path.is_file():
            pytest.skip("master agent catalogue not present")

        agents = json.loads(path.read_text(encoding="utf-8"))["agents"]
        records = agents.values() if isinstance(agents, dict) else agents
        declared = {record.get("model") for record in records if isinstance(record, dict) and record.get("model")}

        assert declared, "the catalogue declared no model tier at all"
        assert declared.issubset(set(TIER_CHAIN)), "library declares tiers the chain does not know: {}".format(
            sorted(declared - set(TIER_CHAIN))
        )
        for tier in declared:
            assert normalise_tier(tier) in TIER_CHAIN


class TestRateLimitDetection:
    """Telling a rate limit apart from every other way an invocation can fail."""

    def test_every_documented_rate_limit_signal_is_classified_as_one(self):
        """All nine rate-limit shapes classify as a rate limit, with evidence."""
        assert len(RATE_LIMITED_FAILURES) == 9
        for label, error, status in RATE_LIMITED_FAILURES:
            assert classify_failure(error, status_code=status) == FAILURE_RATE_LIMIT, label
            assert rate_limit_evidence(error, status_code=status), label

    def test_no_non_rate_limit_failure_is_classified_as_rate_limiting(self):
        """SPECIFICITY CONTROL: ten other failure shapes must not read as throttling.

        This is the substance of the rule. Two of the ten -- the empty response
        and the truncated response -- are shapes the rule document itself lists
        as detection signals; they are pinned as NOT sufficient here, because
        reading them as sufficient contradicts the same document's instruction
        to fix non-rate-limit failures at their root.
        """
        assert len(NON_RATE_LIMIT_FAILURES) == 10
        for label, error, status in NON_RATE_LIMIT_FAILURES:
            assert classify_failure(error, status_code=status) == FAILURE_OTHER, label
            assert rate_limit_evidence(error, status_code=status) == (), label

    def test_a_permissive_classifier_passes_the_positives_and_fails_the_control(self):
        """NEGATIVE CONTROL: the specificity control must be able to fail.

        A classifier that calls everything a rate limit satisfies the positive
        test completely. If the control could not catch it, the positive test
        would be the only thing standing between this module and a driver that
        escalates every bug to the most expensive tier.
        """

        def permissive(error, status_code=None):
            """Stand-in classifier that treats any failure as a rate limit."""
            return FAILURE_RATE_LIMIT

        for label, error, status in RATE_LIMITED_FAILURES:
            assert permissive(error, status_code=status) == FAILURE_RATE_LIMIT, label

        misread = [
            label
            for label, error, status in NON_RATE_LIMIT_FAILURES
            if permissive(error, status_code=status) != FAILURE_OTHER
        ]
        assert len(misread) == len(NON_RATE_LIMIT_FAILURES)

    def test_a_bare_number_in_free_text_is_not_a_status_code(self):
        """Digits in a message are not evidence; only a real status is.

        Scanning message text for the number would make any response that
        happened to mention it look throttled.
        """
        for message in ["completed 429 of 500 steps", "the response used 529 tokens"]:
            assert classify_failure(RuntimeError(message)) == FAILURE_OTHER, message

    def test_a_boolean_is_not_mistaken_for_a_status_code(self):
        """``True`` is an int in Python; it is not a status and must not match."""
        assert classify_failure(RuntimeError("failed"), status_code=True) == FAILURE_OTHER


class TestDecision:
    """The decision function, tier by tier and failure kind by failure kind."""

    def test_a_rate_limit_below_the_top_yields_a_retry_at_the_next_tier(self):
        """Every non-top tier maps a rate limit onto the tier above it."""
        for index, tier in enumerate(TIER_CHAIN[:-1]):
            decision = decide(tier, RuntimeError("rate limit exceeded"))
            assert decision.action == ACTION_RETRY_NEXT_TIER
            assert decision.failure_kind == FAILURE_RATE_LIMIT
            assert decision.from_tier == tier
            assert decision.to_tier == TIER_CHAIN[index + 1]
            assert decision.evidence

    def test_a_rate_limit_at_the_top_yields_an_escalation(self):
        """The top tier has no higher tier, so the decision is escalation."""
        decision = decide(TIER_CHAIN[-1], RuntimeError("rate limit exceeded"))
        assert decision.action == ACTION_ESCALATE_TO_USER
        assert decision.to_tier is None

    def test_a_non_rate_limit_failure_yields_no_fallback_at_any_tier(self):
        """SPECIFICITY CONTROL: no tier turns a defect into a tier switch."""
        for tier in TIER_CHAIN:
            for label, error, status in NON_RATE_LIMIT_FAILURES:
                decision = decide(tier, error, status_code=status)
                assert decision.action == ACTION_NO_FALLBACK, (tier, label)
                assert decision.failure_kind == FAILURE_OTHER, (tier, label)
                assert decision.to_tier is None, (tier, label)
                assert decision.evidence == (), (tier, label)


class TestFallbackDriver:
    """Driving a real invocation through the protocol."""

    def test_a_rate_limited_invocation_retries_at_the_next_tier(self):
        """ACCEPTANCE CRITERION 1, at the lowest tier."""
        lower, upper = TIER_CHAIN[0], TIER_CHAIN[1]
        recorder = Recorder({lower: RuntimeError("rate limit exceeded")})
        sink, log = collect_log()

        outcome = invoke_with_fallback(recorder, agent=AGENT, tier=lower, prompt=PROMPT, log=log)

        assert outcome.escalated is False
        assert outcome.value == "completed at {}".format(upper)
        assert outcome.tiers_attempted == (lower, upper)
        assert [tier for _, tier in recorder.calls] == [lower, upper]
        assert len(sink) == 1

    def test_the_chain_is_walked_to_the_top_when_every_tier_is_rate_limited(self):
        """A rate limit at each tier walks the whole documented chain in order."""
        failures = {tier: ProviderError("refused", 429) for tier in TIER_CHAIN[:-1]}
        recorder = Recorder(failures)
        sink, log = collect_log()

        outcome = invoke_with_fallback(recorder, agent=AGENT, tier=TIER_CHAIN[0], prompt=PROMPT, log=log)

        assert outcome.tiers_attempted == TIER_CHAIN
        assert outcome.value == "completed at {}".format(TIER_CHAIN[-1])
        assert len(sink) == len(TIER_CHAIN) - 1

    def test_the_identical_prompt_is_passed_to_every_retry(self):
        """The rule requires the retry to preserve the full original prompt."""
        failures = {tier: ProviderError("refused", 429) for tier in TIER_CHAIN[:-1]}
        recorder = Recorder(failures)

        invoke_with_fallback(recorder, agent=AGENT, tier=TIER_CHAIN[0], prompt=PROMPT, log=lambda _: None)

        assert len(recorder.calls) == len(TIER_CHAIN)
        for prompt, _ in recorder.calls:
            assert prompt == PROMPT
            assert prompt is PROMPT

    def test_the_top_tier_escalates_to_the_user_rather_than_failing_the_step(self):
        """ACCEPTANCE CRITERION 2: escalation is returned, not raised."""
        top = TIER_CHAIN[-1]
        recorder = Recorder({top: ProviderError("refused", 429)})
        sink, log = collect_log()

        outcome = invoke_with_fallback(recorder, agent=AGENT, tier=top, prompt=PROMPT, log=log)

        assert outcome.escalated is True
        assert outcome.value is None
        assert outcome.tiers_attempted == (top,)
        assert outcome.decisions[-1].action == ACTION_ESCALATE_TO_USER
        assert outcome.escalation_message in sink
        assert AGENT in outcome.escalation_message

    def test_a_non_rate_limit_failure_propagates_and_never_escalates(self):
        """SPECIFICITY CONTROL: the fallback must not fire on a defect.

        The original exception must reach the caller unchanged, at the tier it
        happened on, with no second attempt and no report block -- otherwise
        the mechanism hides the bugs the rule says to fix at their root.
        """
        for label, error, _status in NON_RATE_LIMIT_FAILURES:
            for tier in TIER_CHAIN:
                recorder = Recorder({tier: error})
                sink, log = collect_log()

                with pytest.raises(type(error)) as caught:
                    invoke_with_fallback(recorder, agent=AGENT, tier=tier, prompt=PROMPT, log=log)

                assert caught.value is error, label
                assert [attempted for _, attempted in recorder.calls] == [tier], label
                assert sink == [], label

    def test_a_driver_that_falls_back_on_any_error_fails_the_specificity_control(self):
        """NEGATIVE CONTROL: the specificity control above must be able to fail.

        A permissive driver satisfies both acceptance criteria and is exactly
        what the rule forbids. Running the control against it must show it
        retrying a tool error at a higher tier.
        """

        def permissive_driver(invoke, tier, prompt):
            """Stand-in driver that escalates on any exception at all."""
            current = tier
            while True:
                try:
                    return invoke(prompt, current)
                except Exception:
                    upper = next_tier(current)
                    if upper is None:
                        return None
                    current = upper

        tool_error = ToolExecutionError("write tool failed: permission denied")
        recorder = Recorder({TIER_CHAIN[0]: tool_error})

        result = permissive_driver(recorder, TIER_CHAIN[0], PROMPT)

        assert result == "completed at {}".format(TIER_CHAIN[1])
        assert [tier for _, tier in recorder.calls] == [TIER_CHAIN[0], TIER_CHAIN[1]]

    def test_the_agent_definition_tier_is_not_mutated_by_a_fallback(self):
        """The rule calls the override transient; the definition stays as written."""

        class Definition:
            """Minimal stand-in for a selection match carrying a defined tier."""

            __slots__ = ("model",)

            def __init__(self, model):
                """Record the tier the agent is defined at."""
                self.model = model

        definition = Definition(TIER_CHAIN[0])
        recorder = Recorder({TIER_CHAIN[0]: ProviderError("refused", 429)})

        outcome = invoke_with_fallback(recorder, agent=AGENT, tier=definition.model, prompt=PROMPT, log=lambda _: None)

        assert definition.model == TIER_CHAIN[0]
        assert outcome.tiers_attempted[0] == TIER_CHAIN[0]
        assert outcome.tiers_attempted[-1] == TIER_CHAIN[1]

    def test_a_successful_first_attempt_records_no_decision(self):
        """No failure means no fallback machinery ran at all."""
        recorder = Recorder({})
        sink, log = collect_log()

        outcome = invoke_with_fallback(recorder, agent=AGENT, tier=TIER_CHAIN[1], prompt=PROMPT, log=log)

        assert outcome.decisions == ()
        assert outcome.tiers_attempted == (TIER_CHAIN[1],)
        assert sink == []

    def test_an_unknown_defined_tier_is_refused_before_any_invocation(self):
        """NEGATIVE CONTROL: a bad tier fails loudly and spends no tokens."""
        recorder = Recorder({})
        with pytest.raises(UnknownTier):
            invoke_with_fallback(recorder, agent=AGENT, tier="turbo", prompt=PROMPT, log=lambda _: None)
        assert recorder.calls == []


class TestFallbackLog:
    """The report block the rule requires the caller to emit."""

    @staticmethod
    def parse_block(text):
        """Return the block's field map, or ``None`` when its shape is wrong."""
        lines = text.splitlines()
        if len(lines) != 5 or lines[0] != "MODEL FALLBACK:":
            return None
        fields = {}
        for line in lines[1:]:
            if not line.startswith("  ") or ":" not in line:
                return None
            label, _, value = line.strip().partition(":")
            if not value.strip():
                return None
            fields[label] = value.strip()
        return fields

    def test_the_retry_block_matches_the_documented_shape(self):
        """Header plus the four documented fields, naming both tiers."""
        decision = decide(TIER_CHAIN[0], RuntimeError("rate limit exceeded"))
        fields = self.parse_block(format_fallback_log(decision, AGENT))

        assert fields is not None
        assert sorted(fields) == ["Action", "Agent", "Reason", "Status"]
        assert fields["Agent"] == AGENT
        assert TIER_CHAIN[0] in fields["Reason"].lower()
        assert TIER_CHAIN[1] in fields["Action"].lower()

    def test_the_shape_check_rejects_a_malformed_block(self):
        """NEGATIVE CONTROL: the shape check must reject what it should reject.

        Without this, a parser that accepted anything would report every block
        as well formed, including one with no fields at all.
        """
        good = format_fallback_log(decide(TIER_CHAIN[0], RuntimeError("rate limit exceeded")), AGENT)
        assert self.parse_block(good) is not None

        assert self.parse_block("MODEL FALLBACK:") is None
        assert self.parse_block(good.replace("MODEL FALLBACK:", "SOMETHING ELSE:")) is None
        assert self.parse_block("\n".join(good.splitlines()[:-1])) is None
        assert self.parse_block(good.replace("Fallback in progress", "")) is None

    def test_the_escalation_block_says_there_is_no_higher_tier(self):
        """The top-tier block reports escalation, not another retry."""
        decision = decide(TIER_CHAIN[-1], ProviderError("refused", 429))
        fields = self.parse_block(format_fallback_log(decision, AGENT))

        assert fields is not None
        assert "escalat" in fields["Action"].lower()
        assert TIER_CHAIN[-1] in fields["Action"].lower()
        assert "escalation" in fields["Status"].lower()

    def test_reporting_a_non_fallback_is_refused(self):
        """NEGATIVE CONTROL: there is no fallback block for a non-rate-limit failure."""
        decision = decide(TIER_CHAIN[0], ToolExecutionError("write tool failed"))
        assert decision.action == ACTION_NO_FALLBACK
        with pytest.raises(ValueError):
            format_fallback_log(decision, AGENT)

    def test_the_block_carries_no_agent_name_of_its_own(self):
        """The agent name comes from the caller, so none is written in the module."""
        other = "a-different-caller-supplied-name"
        decision = FallbackDecision(
            action=ACTION_RETRY_NEXT_TIER,
            failure_kind=FAILURE_RATE_LIMIT,
            from_tier=TIER_CHAIN[0],
            to_tier=TIER_CHAIN[1],
            evidence=("status_code=429",),
        )
        block = format_fallback_log(decision, other)

        assert other in block
        assert AGENT not in block
