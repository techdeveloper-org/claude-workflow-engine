"""Acceptance suite for the no-match and low-confidence fallback (issue #269).

Local key V2-013, PRD FR-12 / SRS FR-24. The criterion has two clauses and each
is covered here with at least one companion negative demonstrating that the
assertion is capable of failing:

1. "A task description with no viable match returns the defined fallback
   outcome with a stated reason." Covered by ``TestNoMatchOutcome``,
   ``TestLowConfidenceOutcome`` and ``TestUnavailableOutcome`` -- one class per
   state, because the three are different answers to different questions and
   the requirement names more than one of them.
2. "Never an unexplained empty result and never a silent default pick."
   Covered by ``TestNeverUnexplainedNeverSilent``. Its companion negative feeds
   a deliberately blank outcome to the same predicate and requires it to fail,
   so a check that silently passed everything could not hide here.

Plus the specificity control, which the criterion does not ask for and should:
a fallback that fires on every task is exactly as useless as one that never
fires, and only one of those two failures is visible from the criterion as
written. ``TestSpecificityControl`` requires the fallback to stay silent across
all 37 sprint issue titles, and its companion negative raises the floor above
the measured maximum and requires the same 37 to flip to low confidence.

**Measured figures.** Top-1 confidence over the 37 sprint titles spans 0.685 to
0.863; over tasks the library plainly cannot serve it reaches 0.714 for those
that produce any candidate at all. The populations overlap, so the thresholds
below are written as bounds outside the measured range rather than as fitted
values, and the suite asserts the state machine rather than an accuracy figure
the retrieval stage cannot honestly promise.

Windows-safe: ASCII only.
"""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langgraph_engine.library.resolver import LibrarySetupError  # noqa: E402
from langgraph_engine.selection import (  # noqa: E402
    OUTCOME_LOW_CONFIDENCE,
    OUTCOME_NO_MATCH,
    OUTCOME_SELECTED,
    OUTCOME_UNAVAILABLE,
    REASON_OUTCOMES,
    ConfidenceFloorOutOfRange,
    Degraded,
    DomainKgAdapter,
    RiskSignal,
    UnmappedDegradedReason,
    load_catalogue,
    outcome_for,
    select_agents,
)
from langgraph_engine.selection import selector as selector_module  # noqa: E402
from langgraph_engine.selection.selector import (  # noqa: E402
    REASON_BELOW_THRESHOLD,
    REASON_KG_UNREADABLE,
    REASON_NO_DOMAIN_SIGNAL,
    REASON_NO_QUERY_TERMS,
    build_lexicon,
)

SPRINT_ISSUES = PROJECT_ROOT / "docs" / "phase-6-sprint" / "github_issues.json"

EXPECTED_SPRINT_TITLES = 37

MEASURED_REAL_MIN_CONFIDENCE = 0.685
MEASURED_REAL_MAX_CONFIDENCE = 0.865

FLOOR_ABOVE_EVERY_REAL_TASK = 0.95
FLOOR_BELOW_EVERY_CANDIDATE = 0.0

DECLARED_OUTCOMES = {
    OUTCOME_SELECTED,
    OUTCOME_LOW_CONFIDENCE,
    OUTCOME_NO_MATCH,
    OUTCOME_UNAVAILABLE,
}

UNSERVABLE_TASKS = (
    "zzqxwv jjplkm vvbnmq wwrtyu",
    "qqqq wwww eeee",
    "flarn blibbet wozzle",
    "xyzzy plugh frotz",
    "asdfgh qwerty zxcvbn",
)

try:
    _CATALOGUE_AVAILABLE = load_catalogue() is not None
except Exception:  # noqa: BLE001 - availability probe, the reason is reported by the skip
    _CATALOGUE_AVAILABLE = False

requires_library = pytest.mark.skipif(
    not _CATALOGUE_AVAILABLE,
    reason="sibling claude-global-library checkout is required for KG selection tests",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def catalogue():
    """Load the real master catalogue once for the module."""
    return load_catalogue()


@pytest.fixture(scope="module")
def lexicon(catalogue):
    """Build the term-weight model once for the module."""
    return build_lexicon(catalogue)


@pytest.fixture(scope="module")
def adapter(catalogue):
    """Adapter bound to the real library."""
    return DomainKgAdapter(catalogue)


@pytest.fixture(scope="module")
def uncapped_risk():
    """Return a coverage-complete risk signal, so coverage never masks a state."""
    return RiskSignal.unavailable()


@pytest.fixture(scope="module")
def sprint_titles():
    """Return every sprint issue title, not a sample.

    The whole set is used because the specificity control is a claim about the
    real task population, and a slice of it would let a bad threshold hide in
    the titles that were not looked at.
    """
    issues = json.loads(SPRINT_ISSUES.read_text(encoding="utf-8"))["issues"]
    titles = [issue["title"] for issue in issues]
    assert len(titles) == EXPECTED_SPRINT_TITLES, "expected {} sprint titles, found {}".format(
        EXPECTED_SPRINT_TITLES, len(titles)
    )
    return titles


def _select(task, catalogue, adapter, lexicon, risk, **kwargs):
    """Run one selection with the module fixtures bound."""
    return select_agents(
        task,
        catalogue=catalogue,
        adapter=adapter,
        risk=risk,
        lexicon=lexicon,
        complexity=kwargs.pop("complexity", 8),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# The predicate under test, shared by the positive check and its negative
# ---------------------------------------------------------------------------


def _unexplained_violations(result):
    """Return the ways ``result`` fails the "never unexplained, never silent" rule.

    Extracted so that the positive check and its companion negative run the
    identical code. A predicate that only ever ran against good input would
    prove nothing about its ability to reject bad input.

    Args:
        result: A selection result to inspect.

    Returns:
        A list of human-readable violation strings, empty when the result is
        well formed.
    """
    problems = []
    degraded = result.degraded
    if bool(result.matches) == (degraded is not None):
        problems.append("matches and degraded are not mutually exclusive")
    if result.outcome not in DECLARED_OUTCOMES:
        problems.append("outcome '{}' is not a declared state".format(result.outcome))
    if degraded is None:
        if result.outcome != OUTCOME_SELECTED:
            problems.append("no degraded outcome but state is '{}'".format(result.outcome))
        return problems
    if not (degraded.reason or "").strip():
        problems.append("degraded outcome carries no reason")
    if not (degraded.detail or "").strip():
        problems.append("degraded outcome carries no detail")
    if degraded.outcome == OUTCOME_SELECTED:
        problems.append("a degraded outcome reported itself as selected")
    if result.matches:
        problems.append("a degraded outcome also returned dispatchable matches")
    return problems


class _StubResolver:
    """Resolver returning canned content, used to force adapter failure."""

    def __init__(self, by_suffix):
        """Store a suffix-to-content mapping; unmatched reads fail like the real tiers."""
        self._by_suffix = by_suffix

    def fetch_kg_file(self, relpath):
        """Return canned content for a matching suffix, else raise."""
        for suffix, content in self._by_suffix.items():
            if relpath.endswith(suffix):
                return _StubResource(relpath, content)
        raise LibrarySetupError(Path(relpath))

    def fetch_skill(self, name):
        """Unused by these tests."""
        raise LibrarySetupError(Path(name))

    def fetch_agent(self, name):
        """Unused by these tests."""
        raise LibrarySetupError(Path(name))


class _StubResource:
    """Resolved-resource stand-in carrying only what the adapter reads."""

    def __init__(self, path_or_url, content):
        """Store the path and content."""
        self.path_or_url = path_or_url
        self.content = content


# ---------------------------------------------------------------------------
# The reason-to-state mapping is total and is not a silent default
# ---------------------------------------------------------------------------


class TestOutcomeMapping:
    """Every degraded reason names its state, and an unknown one is refused."""

    def test_every_declared_reason_maps_to_a_declared_outcome(self):
        """No reason can exist without an outcome state to report it under.

        Discovered by introspection rather than by listing the reasons here, so
        a reason added later without a state is caught by this test instead of
        by a caller receiving an outcome it cannot interpret.
        """
        reasons = {
            value
            for name, value in vars(selector_module).items()
            if name.startswith("REASON_") and isinstance(value, str)
        }
        assert reasons, "no reason constants found; this test has stopped testing anything"

        unmapped = sorted(reason for reason in reasons if reason not in REASON_OUTCOMES)
        assert unmapped == [], "degraded reasons with no outcome state: {}".format(unmapped)

        undeclared = sorted(state for state in REASON_OUTCOMES.values() if state not in DECLARED_OUTCOMES)
        assert undeclared == [], "reasons map to undeclared states: {}".format(undeclared)

    def test_both_disputed_states_are_actually_reachable_from_the_mapping(self):
        """The mapping distinguishes no-match from low-confidence, not just in name."""
        assert outcome_for(REASON_BELOW_THRESHOLD) == OUTCOME_LOW_CONFIDENCE
        assert outcome_for(REASON_NO_DOMAIN_SIGNAL) == OUTCOME_NO_MATCH
        assert outcome_for(REASON_NO_QUERY_TERMS) == OUTCOME_NO_MATCH
        assert outcome_for(REASON_KG_UNREADABLE) == OUTCOME_UNAVAILABLE
        assert OUTCOME_NO_MATCH != OUTCOME_LOW_CONFIDENCE

    def test_an_unmapped_reason_is_refused_rather_than_defaulted(self):
        """NEGATIVE CONTROL: an unknown reason must raise, not fall back to a state.

        Defaulting would make the state field untrustworthy in exactly the case
        it matters most -- a condition nobody has classified yet.
        """
        with pytest.raises(UnmappedDegradedReason):
            outcome_for("a_reason_nobody_declared")


# ---------------------------------------------------------------------------
# State 1 -- no match: the corpus offered nothing
# ---------------------------------------------------------------------------


@requires_library
class TestNoMatchOutcome:
    """A task the corpus cannot serve reports no-match, with a stated reason."""

    def test_a_task_with_no_corpus_overlap_reports_no_match(self, catalogue, adapter, lexicon, uncapped_risk):
        """Criterion clause 1: the defined outcome, and a reason for it."""
        for task in UNSERVABLE_TASKS:
            result = _select(task, catalogue, adapter, lexicon, uncapped_risk)
            assert result.outcome == OUTCOME_NO_MATCH, "task '{}' reported '{}'".format(task, result.outcome)
            assert result.degraded is not None
            assert result.degraded.reason == REASON_NO_DOMAIN_SIGNAL
            assert result.degraded.detail.strip()

    def test_an_empty_task_reports_no_match_with_its_own_reason(self, catalogue, adapter, lexicon, uncapped_risk):
        """An unscorable task is a no-match, distinguished by its reason."""
        result = _select("   ", catalogue, adapter, lexicon, uncapped_risk)
        assert result.outcome == OUTCOME_NO_MATCH
        assert result.degraded.reason == REASON_NO_QUERY_TERMS
        assert result.degraded.reason != REASON_NO_DOMAIN_SIGNAL

    def test_no_match_carries_no_near_misses(self, catalogue, adapter, lexicon, uncapped_risk):
        """The states differ in substance, not only in label.

        No-match means there was nothing to carry. If this ever starts carrying
        candidates then the two states have been collapsed again, whatever the
        outcome field says.
        """
        for task in UNSERVABLE_TASKS + ("   ",):
            result = _select(task, catalogue, adapter, lexicon, uncapped_risk)
            assert result.degraded.near_misses == (), "no-match carried candidates for '{}'".format(task)
            assert result.degraded.best_confidence == 0.0


# ---------------------------------------------------------------------------
# State 2 -- low confidence: something matched, badly
# ---------------------------------------------------------------------------


@requires_library
class TestLowConfidenceOutcome:
    """Candidates below the floor are reported, carried, and not dispatchable."""

    def test_a_floor_above_every_candidate_reports_low_confidence(
        self, sprint_titles, catalogue, adapter, lexicon, uncapped_risk
    ):
        """Criterion clause 1 for the other state."""
        result = _select(
            sprint_titles[0],
            catalogue,
            adapter,
            lexicon,
            uncapped_risk,
            confidence_floor=FLOOR_ABOVE_EVERY_REAL_TASK,
        )
        assert result.outcome == OUTCOME_LOW_CONFIDENCE
        assert result.degraded.reason == REASON_BELOW_THRESHOLD
        assert result.degraded.detail.strip()

    def test_low_confidence_carries_the_rejected_candidates_with_their_evidence(
        self, sprint_titles, catalogue, adapter, lexicon, uncapped_risk
    ):
        """A caller escalating or widening gets something concrete to act on.

        The rejected candidates keep the same explainability fields a selected
        match would carry, because an escalation that cannot say what was
        nearly chosen is not an escalation a human can adjudicate.
        """
        result = _select(
            sprint_titles[0],
            catalogue,
            adapter,
            lexicon,
            uncapped_risk,
            confidence_floor=FLOOR_ABOVE_EVERY_REAL_TASK,
        )
        near = result.degraded.near_misses
        assert near, "low confidence carried no candidates"
        for candidate in near:
            assert candidate.agent in catalogue.agents
            assert candidate.domain in catalogue.domains
            assert candidate.edge_path, "near miss {} carries no edge path".format(candidate.agent)
            assert candidate.persona_relpath
            assert candidate.confidence > 0.0
        confidences = [candidate.confidence for candidate in near]
        assert confidences == sorted(confidences, reverse=True), "near misses are not ranked"

    def test_low_confidence_never_offers_a_dispatchable_match(
        self, sprint_titles, catalogue, adapter, lexicon, uncapped_risk
    ):
        """Criterion clause 2: no silent default pick.

        A caller that ignores the outcome field and reads ``matches`` must come
        away with nothing, so a badly matched candidate cannot be dispatched by
        a caller that never learned to check.
        """
        for title in sprint_titles[:5]:
            result = _select(
                title,
                catalogue,
                adapter,
                lexicon,
                uncapped_risk,
                confidence_floor=FLOOR_ABOVE_EVERY_REAL_TASK,
            )
            assert result.outcome == OUTCOME_LOW_CONFIDENCE
            assert result.matches == (), "a low-confidence result offered a dispatchable match"

    def test_low_confidence_records_the_floor_it_was_judged_against(
        self, sprint_titles, catalogue, adapter, lexicon, uncapped_risk
    ):
        """The rejection is re-examinable without re-deriving the threshold."""
        result = _select(
            sprint_titles[0],
            catalogue,
            adapter,
            lexicon,
            uncapped_risk,
            confidence_floor=FLOOR_ABOVE_EVERY_REAL_TASK,
        )
        degraded = result.degraded
        assert degraded.applied_floor == pytest.approx(FLOOR_ABOVE_EVERY_REAL_TASK)
        assert degraded.best_confidence == pytest.approx(degraded.near_misses[0].confidence)
        assert degraded.best_confidence < degraded.applied_floor

    def test_a_floor_of_zero_never_reports_low_confidence(
        self, sprint_titles, catalogue, adapter, lexicon, uncapped_risk
    ):
        """NEGATIVE CONTROL: the state is floor-driven, not spontaneous.

        If low confidence were reported with the floor at zero, it would be
        coming from somewhere other than the threshold and the tests above
        would be measuring the wrong mechanism.
        """
        for title in sprint_titles[:5]:
            result = _select(
                title,
                catalogue,
                adapter,
                lexicon,
                uncapped_risk,
                confidence_floor=FLOOR_BELOW_EVERY_CANDIDATE,
            )
            assert result.outcome != OUTCOME_LOW_CONFIDENCE

    def test_a_floor_outside_zero_to_one_is_rejected(self, catalogue, adapter, lexicon, uncapped_risk):
        """NEGATIVE: a percentage passed as a floor is a unit error, not a value.

        Silently accepting 95 would reject every candidate and produce a
        perfectly plausible low-confidence outcome from a typo.
        """
        for bad in (-0.1, 1.1, 95.0):
            with pytest.raises(ConfidenceFloorOutOfRange):
                _select("anything at all", catalogue, adapter, lexicon, uncapped_risk, confidence_floor=bad)


# ---------------------------------------------------------------------------
# State 3 -- unavailable: nothing was read, so nothing was judged
# ---------------------------------------------------------------------------


@requires_library
class TestUnavailableOutcome:
    """An unreadable graph is a retryable failure, not a verdict on the library."""

    def test_unreadable_graphs_report_unavailable_rather_than_no_match(self, catalogue, lexicon, uncapped_risk):
        """Reporting this as no-match would tell a caller to widen or escalate.

        The correct action is to retry, because nothing was actually consulted.
        The two are different states for that reason.
        """
        broken = DomainKgAdapter(catalogue, resolver=_StubResolver({"relationships.json": "{ not json"}))
        result = select_agents(
            "fix call-graph discovery truncation so every package is analysed",
            catalogue=catalogue,
            adapter=broken,
            risk=uncapped_risk,
            lexicon=lexicon,
            complexity=8,
        )
        assert result.outcome == OUTCOME_UNAVAILABLE
        assert result.outcome != OUTCOME_NO_MATCH
        assert result.degraded.reason == REASON_KG_UNREADABLE
        assert result.degraded.detail.strip()
        assert result.parse_errors, "an unavailable outcome named no failing domain"
        assert result.degraded.near_misses == ()

    def test_the_same_task_succeeds_against_the_real_adapter(self, catalogue, adapter, lexicon, uncapped_risk):
        """NEGATIVE CONTROL: the unavailable state came from the broken reader.

        Without this, the test above would also pass if the task were simply
        unservable, and it would be proving nothing about the reader.
        """
        result = _select(
            "fix call-graph discovery truncation so every package is analysed",
            catalogue,
            adapter,
            lexicon,
            uncapped_risk,
        )
        assert result.outcome == OUTCOME_SELECTED
        assert result.matches


# ---------------------------------------------------------------------------
# Criterion clause 2 -- never unexplained, never a silent default
# ---------------------------------------------------------------------------


@requires_library
class TestNeverUnexplainedNeverSilent:
    """No probe produces an empty result without a stated, usable explanation."""

    def test_no_probe_produces_an_unexplained_or_silent_result(
        self, sprint_titles, catalogue, adapter, lexicon, uncapped_risk
    ):
        """Every state a probe can reach is explained and none is dispatchable by accident."""
        probes = list(sprint_titles) + list(UNSERVABLE_TASKS) + ["", "   ", "the", "the of a an to"]
        for task in probes:
            result = _select(task, catalogue, adapter, lexicon, uncapped_risk)
            assert _unexplained_violations(result) == [], "task '{}' produced {}".format(
                task, _unexplained_violations(result)
            )

    def test_the_low_confidence_path_is_included_in_that_sweep(
        self, sprint_titles, catalogue, adapter, lexicon, uncapped_risk
    ):
        """The sweep above must also cover the state a default floor rarely reaches."""
        for task in sprint_titles[:5]:
            result = _select(
                task,
                catalogue,
                adapter,
                lexicon,
                uncapped_risk,
                confidence_floor=FLOOR_ABOVE_EVERY_REAL_TASK,
            )
            assert result.outcome == OUTCOME_LOW_CONFIDENCE
            assert _unexplained_violations(result) == []

    def test_the_check_rejects_a_blank_reason_and_a_silent_pick(self, catalogue, adapter, lexicon, uncapped_risk):
        """NEGATIVE CONTROL: the predicate above must fail on malformed input.

        Two malformed results are fed to the identical predicate: one degraded
        outcome with no stated reason, and one that reports a degraded state
        while still offering a dispatchable match. A predicate that passed
        either of these would pass anything.
        """
        healthy = _select("fix call-graph discovery truncation", catalogue, adapter, lexicon, uncapped_risk)
        assert _unexplained_violations(healthy) == []

        blank = Degraded(reason="   ", detail="   ", outcome=OUTCOME_NO_MATCH)
        unexplained = selector_module.SelectionResult(
            task="anything",
            matches=(),
            degraded=blank,
            considered_domains=(),
            parse_errors=(),
            risk=uncapped_risk,
            library_version=catalogue.library_version,
        )
        problems = _unexplained_violations(unexplained)
        assert problems, "the predicate accepted a degraded outcome with no reason"

        silent = selector_module.SelectionResult(
            task="anything",
            matches=healthy.matches,
            degraded=Degraded(reason=REASON_BELOW_THRESHOLD, detail="stated", outcome=OUTCOME_LOW_CONFIDENCE),
            considered_domains=(),
            parse_errors=(),
            risk=uncapped_risk,
            library_version=catalogue.library_version,
        )
        assert _unexplained_violations(silent), "the predicate accepted a degraded result that still offered a pick"

    def test_the_serialised_payload_states_the_outcome_and_the_near_misses(
        self, sprint_titles, catalogue, adapter, lexicon, uncapped_risk
    ):
        """A caller reading only the serialised form can still tell the states apart."""
        low = _select(
            sprint_titles[0],
            catalogue,
            adapter,
            lexicon,
            uncapped_risk,
            confidence_floor=FLOOR_ABOVE_EVERY_REAL_TASK,
        ).to_dict()
        gone = _select(UNSERVABLE_TASKS[0], catalogue, adapter, lexicon, uncapped_risk).to_dict()

        json.dumps(low)
        json.dumps(gone)

        assert low["outcome"] == OUTCOME_LOW_CONFIDENCE
        assert gone["outcome"] == OUTCOME_NO_MATCH
        assert low["matches"] == []
        assert low["degraded"]["near_misses"], "serialised low confidence lost its candidates"
        assert gone["degraded"]["near_misses"] == []
        assert low["degraded"]["applied_floor"] == pytest.approx(FLOOR_ABOVE_EVERY_REAL_TASK)


# ---------------------------------------------------------------------------
# Specificity control -- the criterion does not require it and should
# ---------------------------------------------------------------------------


@requires_library
class TestSpecificityControl:
    """Proof the fallback discriminates rather than firing on everything."""

    def test_the_fallback_does_not_fire_on_any_real_task(
        self, sprint_titles, catalogue, adapter, lexicon, uncapped_risk
    ):
        """All 37 real sprint titles select cleanly under the default floor.

        A fallback that fired here would be worthless in the opposite
        direction: every real task would be handed to a human. The criterion as
        written cannot see that failure, which is why this control exists.
        """
        fired = []
        for title in sprint_titles:
            result = _select(title, catalogue, adapter, lexicon, uncapped_risk)
            if result.outcome != OUTCOME_SELECTED:
                fired.append((title, result.outcome, result.degraded.reason))
            else:
                assert result.matches
                assert result.degraded is None
        assert fired == [], "the fallback fired on real tasks: {}".format(fired)

    def test_real_task_confidence_stays_inside_the_measured_band(
        self, sprint_titles, catalogue, adapter, lexicon, uncapped_risk
    ):
        """The control's headroom is pinned, so silent drift is visible.

        Written as bounds rather than equalities because catalogue prose moves
        with upstream library releases. What must not change quietly is that
        real tasks sit well clear of the floor.
        """
        top = [
            _select(title, catalogue, adapter, lexicon, uncapped_risk).matches[0].confidence for title in sprint_titles
        ]
        assert len(top) == EXPECTED_SPRINT_TITLES
        assert min(top) >= MEASURED_REAL_MIN_CONFIDENCE, "real-task confidence fell to {:.3f}".format(min(top))
        assert max(top) <= MEASURED_REAL_MAX_CONFIDENCE, "real-task confidence rose to {:.3f}".format(max(top))
        assert min(top) > selector_module.BASE_CONFIDENCE_FLOOR

    def test_the_same_control_fails_when_the_floor_is_raised(
        self, sprint_titles, catalogue, adapter, lexicon, uncapped_risk
    ):
        """NEGATIVE CONTROL: the control above must be capable of failing.

        The floor is raised above the measured maximum and the same 37 titles
        are re-run. Every one must now report low confidence. If they did not,
        the control would be passing because the fallback is unreachable rather
        than because it is well targeted.
        """
        still_selected = []
        for title in sprint_titles:
            result = _select(
                title,
                catalogue,
                adapter,
                lexicon,
                uncapped_risk,
                confidence_floor=FLOOR_ABOVE_EVERY_REAL_TASK,
            )
            if result.outcome != OUTCOME_LOW_CONFIDENCE:
                still_selected.append((title, result.outcome))
        assert still_selected == [], "raising the floor did not reach these tasks: {}".format(still_selected)

    def test_the_two_degraded_states_never_describe_the_same_task_run(
        self, sprint_titles, catalogue, adapter, lexicon, uncapped_risk
    ):
        """A single run lands in exactly one state, and the states disagree.

        Run side by side: the same title under a raised floor is low
        confidence with candidates, while an unservable task is no-match with
        none. Reading either the label or the payload gives the same answer,
        which is what keeps the distinction from being cosmetic.
        """
        low = _select(
            sprint_titles[0],
            catalogue,
            adapter,
            lexicon,
            uncapped_risk,
            confidence_floor=FLOOR_ABOVE_EVERY_REAL_TASK,
        )
        gone = _select(UNSERVABLE_TASKS[0], catalogue, adapter, lexicon, uncapped_risk)

        assert low.outcome != gone.outcome
        assert low.degraded.reason != gone.degraded.reason
        assert bool(low.degraded.near_misses) != bool(gone.degraded.near_misses)
        assert low.degraded.best_confidence > gone.degraded.best_confidence
