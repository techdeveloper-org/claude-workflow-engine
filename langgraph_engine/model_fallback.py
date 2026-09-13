"""Conformance with the model fallback protocol (PRD FR-13 / SRS FR-25).

The protocol is authored at ``~/.claude/rules/model-fallback.md`` and is a
contract on whatever *calls* an agent, not on whatever *chooses* one. This
module encodes that contract as a decision function plus a driver, so that a
call site conforms by delegating rather than by re-deriving the rule.

Why this lives here and not under ``langgraph_engine/selection``
---------------------------------------------------------------
``selection`` answers "which agent, and what tier is it defined at" -- its
:class:`~langgraph_engine.selection.selector.Match` carries a ``model`` field
read from the agent's own definition. The tier an agent is *defined* at and the
tier a *particular invocation* ends up running at are different facts, and the
second only exists once something has tried to invoke and been refused. Putting
the retry policy inside ``selection`` would also put an invocation concern
inside a package whose asserted invariant is that it names no agent and whose
charter is retrieval. It is a sibling concern, so it is a sibling module.

The tier vocabulary is the agent-definition one -- the ``model:`` field in an
agent's frontmatter, surfaced by ``Match.model`` and by
``routing.kg_lookup.AgentRef.model``. It is deliberately NOT the ``fast /
balanced / deep`` tier vocabulary in ``llm_call``, nor the ``claude_cli ->
anthropic`` provider chain there. Those are provider-selection concerns; this
is agent-tier escalation, and conflating the two would make a provider outage
look like a rate limit.

How a rate limit is told apart from everything else
---------------------------------------------------
This is the whole substance of the rule, because the rule's final clause says
non-rate-limit failures -- bad instructions, scope errors, tool errors -- must
be fixed at the root and never model-switched. A detector that fired on any
failure would escalate past exactly the bugs the rule tells you to fix, and
would spend the more expensive tier doing it.

So classification is positive-evidence-only: an invocation is treated as rate
limited when, and only when, it carries one of the signals in
:data:`RATE_LIMIT_STATUS_CODES` or :data:`RATE_LIMIT_MARKERS`. Everything else
-- including a timeout, a connection reset, a generic 5xx, an authentication
failure, and an empty or truncated response with no rate-limit evidence -- is
:data:`FAILURE_OTHER`, and this module refuses to escalate it.

That is a deliberate narrowing of the rule's own detection list, which offers
"truncated output ... or agent returning incomplete/empty results" as rate-limit
signals. Those are consequences of a rate limit but are equally consequences of
a crash, a bad prompt, or a tool error, and reading them as sufficient would
contradict the same document's non-rate-limit clause. The narrow reading is the
only one under which both clauses hold. The gap is real and is recorded rather
than papered over: a caller that can genuinely distinguish "empty because
throttled" from "empty because broken" should pass that as ``status_code``
rather than rely on the shape of the output.

Generic 5xx is excluded for the same reason. A 500 or a 503 is not
distinguishable from a server bug, and ``sdlc_pipeline.llm_retry`` already
retries that class at the same tier with backoff, which is the correct response
to a transient server fault. Same-tier backoff and tier escalation are
complementary, not alternatives.

Scope
-----
Pure policy. Nothing here performs I/O, spawns a process, or mutates an agent
definition -- the rule calls the mechanism transient and says the definition's
declared model stays as written, so the tier override lives only in the
arguments passed to one invocation.

Windows-safe: ASCII only.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

_log = logging.getLogger(__name__)

TIER_CHAIN: Tuple[str, ...] = ("haiku", "sonnet", "opus", "fable")

RATE_LIMIT_STATUS_CODES: Tuple[int, ...] = (429, 529)

RATE_LIMIT_MARKERS: Tuple[str, ...] = (
    "rate limit",
    "ratelimit",
    "too many requests",
    "overloaded",
    "over capacity",
)

FAILURE_RATE_LIMIT = "rate_limit"
FAILURE_OTHER = "other"

ACTION_RETRY_NEXT_TIER = "retry_next_tier"
ACTION_ESCALATE_TO_USER = "escalate_to_user"
ACTION_NO_FALLBACK = "no_fallback"

_LABEL_WIDTH = 10


class UnknownTier(ValueError):
    """Raised when a tier is not one the documented chain knows.

    An unrecognised tier is a configuration defect: silently defaulting it to
    some assumed tier would decide the whole escalation path from a typo, so it
    is refused instead.
    """


def _fold(text: str) -> str:
    """Fold text for marker matching: lower case, separators to spaces.

    Hyphens and underscores become spaces so that ``rate-limit``,
    ``rate_limit`` and ``rate limit`` all reduce to one form, and runs of
    whitespace collapse so that a wrapped message matches the same markers as
    an unwrapped one.
    """
    lowered = text.lower().replace("-", " ").replace("_", " ")
    return " ".join(lowered.split())


def normalise_tier(raw: object) -> str:
    """Fold a tier name to its canonical form and verify the chain knows it.

    Args:
        raw: A tier as recorded on an agent definition or passed by a caller.

    Returns:
        The canonical tier name.

    Raises:
        UnknownTier: When ``raw`` is not a string naming a tier in
            :data:`TIER_CHAIN`.
    """
    if not isinstance(raw, str):
        raise UnknownTier("tier must be a string, got {}".format(type(raw).__name__))
    folded = raw.strip().lower()
    if folded not in TIER_CHAIN:
        raise UnknownTier("'{}' is not a tier in the documented chain {}".format(raw, list(TIER_CHAIN)))
    return folded


def next_tier(tier: object) -> Optional[str]:
    """Return the tier one step up the chain, or ``None`` at the top.

    Args:
        tier: The tier the refused invocation ran at.

    Returns:
        The next tier, or ``None`` when ``tier`` is the highest one, which is
        the point at which the rule says to escalate to the user.

    Raises:
        UnknownTier: When ``tier`` is not in the chain.
    """
    current = normalise_tier(tier)
    index = TIER_CHAIN.index(current)
    if index + 1 >= len(TIER_CHAIN):
        return None
    return TIER_CHAIN[index + 1]


def rate_limit_evidence(error: object, *, status_code: Optional[int] = None) -> Tuple[str, ...]:
    """Return the rate-limit signals present in a failure, in chain order.

    Args:
        error: The failure to inspect -- an exception, or any object whose text
            form carries the provider's message.
        status_code: HTTP status observed by the caller. Takes precedence over
            any ``status_code`` attribute on ``error``, because the caller saw
            the response and the exception may only be paraphrasing it.

    Returns:
        Every matched signal, empty when the failure carries no rate-limit
        evidence at all. Emptiness is the whole discriminator: this function
        never infers a rate limit from the absence of output.
    """
    found: List[str] = []

    code = status_code if status_code is not None else getattr(error, "status_code", None)
    if isinstance(code, int) and not isinstance(code, bool) and code in RATE_LIMIT_STATUS_CODES:
        found.append("status_code={}".format(code))

    parts = []
    if isinstance(error, BaseException):
        parts.append(type(error).__name__)
    parts.append("{}".format(error))
    haystack = _fold(" ".join(parts))

    for marker in RATE_LIMIT_MARKERS:
        if marker in haystack:
            found.append(marker)

    return tuple(found)


def classify_failure(error: object, *, status_code: Optional[int] = None) -> str:
    """Classify a failed invocation as rate limited or as something else.

    Args:
        error: The failure to classify.
        status_code: HTTP status observed by the caller, when known.

    Returns:
        :data:`FAILURE_RATE_LIMIT` when positive evidence is present, otherwise
        :data:`FAILURE_OTHER`.
    """
    return FAILURE_RATE_LIMIT if rate_limit_evidence(error, status_code=status_code) else FAILURE_OTHER


@dataclass(frozen=True)
class FallbackDecision:
    """What the protocol says to do about one failed invocation.

    Attributes:
        action: One of :data:`ACTION_RETRY_NEXT_TIER`,
            :data:`ACTION_ESCALATE_TO_USER`, :data:`ACTION_NO_FALLBACK`.
        failure_kind: :data:`FAILURE_RATE_LIMIT` or :data:`FAILURE_OTHER`.
        from_tier: Tier the refused invocation ran at.
        to_tier: Tier to retry at, populated only for a retry action.
        evidence: Rate-limit signals that were matched, empty for
            :data:`FAILURE_OTHER`. Recorded so a reader can audit why a tier
            switch happened rather than take it on trust.
    """

    action: str
    failure_kind: str
    from_tier: str
    to_tier: Optional[str]
    evidence: Tuple[str, ...]


def decide(tier: object, error: object, *, status_code: Optional[int] = None) -> FallbackDecision:
    """Apply the protocol to one failed invocation.

    Args:
        tier: Tier the invocation ran at.
        error: The failure it raised.
        status_code: HTTP status observed by the caller, when known.

    Returns:
        The :class:`FallbackDecision`. A non-rate-limit failure always yields
        :data:`ACTION_NO_FALLBACK` regardless of tier, because the rule sends
        that class of failure back to its root cause instead of up the chain.

    Raises:
        UnknownTier: When ``tier`` is not in the chain.
    """
    current = normalise_tier(tier)
    evidence = rate_limit_evidence(error, status_code=status_code)

    if not evidence:
        return FallbackDecision(
            action=ACTION_NO_FALLBACK,
            failure_kind=FAILURE_OTHER,
            from_tier=current,
            to_tier=None,
            evidence=(),
        )

    upper = next_tier(current)
    if upper is None:
        return FallbackDecision(
            action=ACTION_ESCALATE_TO_USER,
            failure_kind=FAILURE_RATE_LIMIT,
            from_tier=current,
            to_tier=None,
            evidence=evidence,
        )
    return FallbackDecision(
        action=ACTION_RETRY_NEXT_TIER,
        failure_kind=FAILURE_RATE_LIMIT,
        from_tier=current,
        to_tier=upper,
        evidence=evidence,
    )


def _block(agent: str, reason: str, action: str, status: str) -> str:
    """Render the four-field report block the rule prescribes."""
    lines = ["MODEL FALLBACK:"]
    for label, value in (("Agent", agent), ("Reason", reason), ("Action", action), ("Status", status)):
        lines.append("  {}{}".format((label + ":").ljust(_LABEL_WIDTH), value))
    return "\n".join(lines)


def format_fallback_log(decision: FallbackDecision, agent: str) -> str:
    """Render the report block the rule requires the caller to emit.

    The retry wording follows the template in the rule document, generalised
    across tiers rather than fixed to the one pair the template spells out. The
    escalation wording has no template in the document; it is written to the
    same four-field shape so that a reader who has seen one has seen both.

    Args:
        decision: The decision to report.
        agent: Name of the agent being invoked, supplied by the caller so that
            no agent name is written into this module.

    Returns:
        The multi-line block.

    Raises:
        ValueError: When ``decision`` is :data:`ACTION_NO_FALLBACK`, which is
            the outcome where no fallback occurred and so has nothing to report
            under this heading.
    """
    if decision.action == ACTION_NO_FALLBACK:
        raise ValueError("no fallback occurred for a {} failure; there is nothing to report".format(FAILURE_OTHER))

    reason = "{} rate limit reached".format(decision.from_tier.capitalize())
    if decision.action == ACTION_ESCALATE_TO_USER:
        return _block(
            agent=agent,
            reason=reason,
            action="Escalating to user -- {} is the top tier, no further fallback exists".format(decision.from_tier),
            status="Escalation required",
        )
    return _block(
        agent=agent,
        reason=reason,
        action="Retrying with {} model".format((decision.to_tier or "").capitalize()),
        status="Fallback in progress",
    )


@dataclass(frozen=True)
class InvocationOutcome:
    """Result of driving one invocation through the protocol.

    Attributes:
        value: Whatever the invocation returned on success, ``None`` when the
            run ended in escalation.
        escalated: True when the top tier was rate limited and the run stopped
            for the user rather than for a defect.
        tiers_attempted: Tiers actually invoked, in order. Its first entry is
            the tier the agent is defined at, which this module never rewrites.
        decisions: One decision per failed attempt, in order.
        escalation_message: The report block handed to the user, populated only
            when ``escalated`` is true.
    """

    value: Any
    escalated: bool
    tiers_attempted: Tuple[str, ...]
    decisions: Tuple[FallbackDecision, ...]
    escalation_message: Optional[str]


def invoke_with_fallback(
    invoke: Callable[[str, str], Any],
    *,
    agent: str,
    tier: object,
    prompt: str,
    log: Optional[Callable[[str], None]] = None,
) -> InvocationOutcome:
    """Invoke an agent, escalating tier on rate limits and only on rate limits.

    The identical ``prompt`` object is handed to every attempt, satisfying the
    rule's requirement that a retry preserve the full original prompt.

    A failure is whatever ``invoke`` raises. A provider that folds a rate limit
    into a sentinel return value cannot be driven correctly here, because the
    refusal never reaches this function -- such a provider has to surface the
    error before it can conform.

    Args:
        invoke: Called as ``invoke(prompt, tier)``. Returns the agent result,
            or raises to signal failure.
        agent: Agent name, used only for the report block.
        tier: Tier the agent is defined at. Not mutated.
        prompt: The task prompt, passed unchanged to every attempt.
        log: Sink for the report block. Defaults to this module's logger.

    Returns:
        An :class:`InvocationOutcome`. On escalation it is returned rather than
        raised, because the rule ends the top-tier case by telling the user,
        not by failing the step.

    Raises:
        UnknownTier: When ``tier`` is not in the chain.
        Exception: The original failure, unchanged, whenever it is not a rate
            limit. Re-raising is the point: that class of failure is a defect
            to fix at its root, and swallowing it would hide the defect behind
            a more expensive model.
    """
    emit = log if log is not None else _log.warning
    current = normalise_tier(tier)

    attempted: List[str] = []
    decisions: List[FallbackDecision] = []

    while True:
        attempted.append(current)
        try:
            value = invoke(prompt, current)
        except Exception as exc:
            decision = decide(current, exc)
            decisions.append(decision)

            if decision.action == ACTION_NO_FALLBACK:
                raise

            message = format_fallback_log(decision, agent)
            emit(message)

            if decision.action == ACTION_ESCALATE_TO_USER:
                return InvocationOutcome(
                    value=None,
                    escalated=True,
                    tiers_attempted=tuple(attempted),
                    decisions=tuple(decisions),
                    escalation_message=message,
                )

            current = decision.to_tier or current
            continue

        return InvocationOutcome(
            value=value,
            escalated=False,
            tiers_attempted=tuple(attempted),
            decisions=tuple(decisions),
            escalation_message=None,
        )
