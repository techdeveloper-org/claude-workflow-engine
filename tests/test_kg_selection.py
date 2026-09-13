"""Acceptance and conformance suite for KG-driven selection (issue #267).

Local key V2-011, PRD FR-10 / SRS FR-22. Three acceptance criteria, each with
at least one companion negative test that demonstrates the assertion is capable
of failing:

1. No agent or skill name appears as a string literal on the selection code
   path outside test fixtures. Asserted by parsing every module in
   ``langgraph_engine/selection`` and intersecting its string literals and
   comments against the live 528-agent / 1034-skill catalogue. The companion
   negative plants a real name into a temporary module and requires the same
   detector to flag it.
2. Ten sample task descriptions each return a ranked agent set in which every
   entry carries a non-empty knowledge-graph edge path. The sample is the every
   fourth sprint issue title, a deterministic slice rather than a chosen one.
   The companion negatives cover the empty task, the unmatchable task, and an
   agent that no edge mentions.
3. Runs are verified against a non-truncated call graph. The precondition is
   enforced in code, and a negative test sets the truncation override and
   requires selection to refuse.

Plus the specificity control the criteria do not ask for and should: a selector
that returns the same agents for every task has no collisions and no value.
``TestSpecificityControl`` measures inter-task result overlap and pins it, and
its negative substitutes a deliberately non-discriminating scorer and requires
the same measurement to fail.

Every count asserted here was measured against claude-global-library 29.97.4
(re-measured 2026-09-13; first measured against 29.73.0).
Where a figure could drift with an upstream library release the assertion says
so and is written as a bound rather than an equality.

Windows-safe: ASCII only.
"""

import ast
import io
import json
import re
import sys
import tokenize
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langgraph_engine.library.resolver import LibrarySetupError, locate_library_root  # noqa: E402
from langgraph_engine.selection import (  # noqa: E402
    DomainKgAdapter,
    Lexicon,
    LibraryCatalogue,
    Parsed,
    ParseError,
    RiskSignal,
    TruncatedRiskSignal,
)
from langgraph_engine.selection import kg_adapter as kg_adapter_module  # noqa: E402
from langgraph_engine.selection import load_catalogue, select_agents  # noqa: E402
from langgraph_engine.selection.catalogue import CatalogueUnavailable  # noqa: E402
from langgraph_engine.selection.ids import candidate_refs, normalise_ref  # noqa: E402
from langgraph_engine.selection.risk import ENV_MAX_FILES, ENV_MAX_PATHS, probe_builder_coverage  # noqa: E402
from langgraph_engine.selection.selector import REASON_NO_QUERY_TERMS, ComplexityOutOfRange, build_lexicon  # noqa: E402

SELECTION_PACKAGE = PROJECT_ROOT / "langgraph_engine" / "selection"
SPRINT_ISSUES = PROJECT_ROOT / "docs" / "phase-6-sprint" / "github_issues.json"
ROUTING_MAP = PROJECT_ROOT / "docs" / "phase-7-routing" / "routing_map.json"

SAMPLE_STRIDE = 4
SAMPLE_SIZE = 10

EXPECTED_DOMAIN_COUNT = 104
EXPECTED_TOTAL_EDGES = 7527
EXPECTED_AGENT_COUNT = 528
EXPECTED_SKILL_COUNT = 1034
NAIVE_READER_BLIND_SPOT_EDGES = 490
NAIVE_READER_BLIND_SPOT_DOMAINS = 7

MEASURED_CONTAINER_CENSUS = {
    ("bare", "type"): 62,
    ("edges", "type"): 23,
    ("bare", "edge_type"): 7,
    ("relationships", "type"): 7,
    ("edges", "edge_type"): 3,
    ("bare", "relationship_type"): 2,
}

SPECIFICITY_MAX_MEAN_OVERLAP = 0.35
SPECIFICITY_MIN_DISTINCT_AGENTS = 20

_SLUG_RUN = re.compile(r"[a-z0-9][a-z0-9-]*")

_LIBRARY_ROOT = locate_library_root(PROJECT_ROOT)

requires_library = pytest.mark.skipif(
    _LIBRARY_ROOT is None,
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
    """Adapter bound to the real library, with its per-domain cache warm."""
    return DomainKgAdapter(catalogue)


@pytest.fixture(scope="module")
def sample_tasks():
    """Return the ten sample task descriptions required by the criterion.

    Every fourth sprint issue title, taken in file order. A deterministic
    slice is used rather than a hand-picked set so the sample cannot have been
    chosen to flatter the selector.
    """
    issues = json.loads(SPRINT_ISSUES.read_text(encoding="utf-8"))["issues"]
    titles = [issues[index]["title"] for index in range(0, len(issues), SAMPLE_STRIDE)]
    assert len(titles) == SAMPLE_SIZE, "sample slice yielded {} titles, expected {}".format(len(titles), SAMPLE_SIZE)
    return titles


@pytest.fixture(scope="module")
def uncapped_risk():
    """Return a coverage-complete risk signal for use across selection tests."""
    complete, caps = probe_builder_coverage({})
    assert complete and not caps
    return RiskSignal.unavailable()


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
# Independent re-readers -- deliberately NOT importing the adapter's logic
# ---------------------------------------------------------------------------


def _raw_domain_payload(domain):
    """Read one domain's relationship file with an oracle written from scratch.

    This re-implements container unwrapping instead of importing it, so it is
    able to disagree with the adapter under test. An oracle built from the
    subject's own helpers can only ever agree and proves nothing.
    """
    path = _LIBRARY_ROOT / "knowledge-graph" / domain / "relationships.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _oracle_edges(domain):
    """Return the raw edge records for a domain, unwrapping all three forms."""
    payload = _raw_domain_payload(domain)
    if isinstance(payload, list):
        return payload
    for key in ("edges", "relationships"):
        if isinstance(payload.get(key), list):
            return payload[key]
    raise AssertionError("oracle could not unwrap domain {}".format(domain))


def _naive_edges_only_edges(domain):
    """Return what a reader that accepts only an ``edges`` container would see.

    This is the pre-ADR-015 behaviour that FR-10a exists to eliminate, kept as
    an executable control rather than a described one.
    """
    payload = _raw_domain_payload(domain)
    if isinstance(payload, list):
        return payload
    if isinstance(payload.get("edges"), list):
        return payload["edges"]
    return []


def _all_domains():
    """List the domain slugs declared by the master domain catalogue."""
    path = _LIBRARY_ROOT / "knowledge-graph" / "_master" / "domains_all.json"
    return [record["slug"] for record in json.loads(path.read_text(encoding="utf-8"))["domains"]]


def _declared_edge_counts():
    """Return the per-domain edge counts the master catalogue declares."""
    path = _LIBRARY_ROOT / "knowledge-graph" / "_master" / "domains_all.json"
    return {
        record["slug"]: record.get("edge_count") for record in json.loads(path.read_text(encoding="utf-8"))["domains"]
    }


# ---------------------------------------------------------------------------
# Criterion 1 -- zero agent or skill name literals on the selection path
# ---------------------------------------------------------------------------


def _literals_and_comments(path):
    """Yield every string literal and comment body in a Python source file.

    Both are scanned. A name hidden in a comment is not executable, but it is
    still the hardcoded knowledge the requirement removes, and the grep the
    acceptance criterion describes would find it.
    """
    source = path.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            yield token.string


def _name_literals_in(path, names):
    """Return the catalogue names that appear inside a source file's text.

    Every hyphenated slug-shaped run inside each literal is checked, so a name
    embedded in a longer sentence is caught, not only a literal equal to a
    name.
    """
    found = set()
    for text in _literals_and_comments(path):
        folded = normalise_ref(text)
        if folded in names:
            found.add(folded)
        for run in _SLUG_RUN.findall(folded):
            if run in names:
                found.add(run)
    return found


@requires_library
class TestNoHardcodedNames:
    """Acceptance criterion 1 and its companion negative."""

    def test_selection_path_contains_no_agent_or_skill_name_literal(self, catalogue):
        """No module under langgraph_engine/selection names an agent or skill."""
        names = set(catalogue.agents) | set(catalogue.skills)
        assert len(names) == EXPECTED_AGENT_COUNT + EXPECTED_SKILL_COUNT

        modules = sorted(SELECTION_PACKAGE.glob("*.py"))
        assert modules, "no modules found on the selection path"

        offenders = {}
        for module in modules:
            hits = _name_literals_in(module, names)
            if hits:
                offenders[module.name] = sorted(hits)
        assert offenders == {}, "agent or skill names appear as literals: {}".format(offenders)

    def test_the_detector_flags_a_planted_name(self, catalogue, tmp_path):
        """NEGATIVE CONTROL: the same detector must fail on a planted name.

        Without this, a detector that silently matched nothing would report a
        clean pass on any input at all.
        """
        names = set(catalogue.agents) | set(catalogue.skills)
        planted = sorted(catalogue.agents)[0]

        module = tmp_path / "planted.py"
        module.write_text(
            '"""Fixture module."""\n\nPREFERRED = "{}"\n'.format(planted),
            encoding="utf-8",
        )
        assert _name_literals_in(module, names) == {planted}

        embedded = tmp_path / "embedded.py"
        embedded.write_text(
            '"""Route this work to {} when the task is hard."""\n'.format(planted),
            encoding="utf-8",
        )
        assert planted in _name_literals_in(embedded, names)

        clean = tmp_path / "clean.py"
        clean.write_text('"""Nothing to see."""\n\nLIMIT = 5\n', encoding="utf-8")
        assert _name_literals_in(clean, names) == set()


# ---------------------------------------------------------------------------
# KG adapter conformance (FR-10a, ADR-015)
# ---------------------------------------------------------------------------


@requires_library
class TestKgAdapterConformance:
    """The adapter reads all six measured schema shapes and never empties out."""

    def test_every_domain_parses(self, adapter):
        """All 104 domain graphs parse; none degrades to an empty result."""
        domains = _all_domains()
        assert len(domains) == EXPECTED_DOMAIN_COUNT

        failures = []
        for domain in domains:
            result = adapter.read_domain(domain)
            if isinstance(result, ParseError):
                failures.append((domain, result.failure_kind, result.detail))
        assert failures == [], "domains failed to parse: {}".format(failures)

    def test_container_and_edge_type_census_matches_the_measured_shapes(self, adapter):
        """The six container/edge-type combinations occur at their measured counts.

        Counts are for library 29.97.4. An upstream release may legitimately
        move a domain between shapes; what must not change is that all six
        forms are handled and every domain lands in one of them.
        """
        census = {}
        for domain in _all_domains():
            result = adapter.read_domain(domain)
            assert isinstance(result, Parsed)
            key = (result.container_form, result.edge_type_key)
            census[key] = census.get(key, 0) + 1
        assert census == MEASURED_CONTAINER_CENSUS
        assert sum(census.values()) == EXPECTED_DOMAIN_COUNT

    def test_edge_totals_agree_with_the_master_catalogue_declaration(self, adapter):
        """Per-domain edge counts match what domains_all.json declares.

        This is the strongest available independent check on container
        resolution: the master catalogue counted the edges when the graphs were
        built, so a reader that drops a container form disagrees with it.
        """
        declared = _declared_edge_counts()
        mismatches = []
        total = 0
        for domain, expected in declared.items():
            result = adapter.read_domain(domain)
            assert isinstance(result, Parsed)
            total += len(result.edges)
            if expected is not None and len(result.edges) != expected:
                mismatches.append((domain, expected, len(result.edges)))
        assert mismatches == [], "edge-count disagreement with the master catalogue: {}".format(mismatches)
        assert total == EXPECTED_TOTAL_EDGES

    def test_the_naive_edges_only_reader_loses_edges_this_adapter_keeps(self, adapter):
        """NEGATIVE CONTROL: the pre-ADR-015 reader silently drops 490 edges.

        If this control ever passes -- if the naive reader loses nothing -- then
        the assertion above is no longer testing anything, because the corpus
        would have become schema-uniform.
        """
        lost_domains = []
        lost_edges = 0
        for domain in _all_domains():
            naive = len(_naive_edges_only_edges(domain))
            actual = len(_oracle_edges(domain))
            if naive < actual:
                lost_domains.append(domain)
                lost_edges += actual - naive
        assert len(lost_domains) == NAIVE_READER_BLIND_SPOT_DOMAINS
        assert lost_edges == NAIVE_READER_BLIND_SPOT_EDGES

        for domain in lost_domains:
            result = adapter.read_domain(domain)
            assert isinstance(result, Parsed)
            assert len(result.edges) == len(_oracle_edges(domain))
            assert result.container_form == kg_adapter_module.CONTAINER_RELATIONSHIPS

    def test_malformed_json_yields_a_typed_error_not_an_empty_list(self, catalogue):
        """NEGATIVE: a JSON decode failure is reported, never emptied out."""
        adapter = DomainKgAdapter(catalogue, resolver=_StubResolver({"relationships.json": "{ not json"}))
        result = adapter.read_domain(sorted(catalogue.domains)[0])
        assert isinstance(result, ParseError)
        assert result.failure_kind == kg_adapter_module.MALFORMED_JSON
        assert result.detail

    def test_unrecognised_container_yields_a_typed_error(self, catalogue):
        """NEGATIVE: an unknown container shape is reported, never emptied out."""
        payload = json.dumps({"links": [{"source": "a", "target": "b", "type": "USES"}]})
        adapter = DomainKgAdapter(catalogue, resolver=_StubResolver({"relationships.json": payload}))
        result = adapter.read_domain(sorted(catalogue.domains)[0])
        assert isinstance(result, ParseError)
        assert result.failure_kind == kg_adapter_module.UNRECOGNISED_CONTAINER

    def test_unrecognised_edge_type_key_yields_a_typed_error(self, catalogue):
        """NEGATIVE: an unknown edge-type key is reported, never emptied out."""
        payload = json.dumps([{"source": "a", "target": "b", "kind": "USES"}])
        adapter = DomainKgAdapter(catalogue, resolver=_StubResolver({"relationships.json": payload}))
        result = adapter.read_domain(sorted(catalogue.domains)[0])
        assert isinstance(result, ParseError)
        assert result.failure_kind == kg_adapter_module.UNRECOGNISED_EDGE_TYPE_KEY

    def test_a_successful_parse_can_never_be_empty(self, adapter):
        """Invariant S1/S2: Parsed always carries at least one edge."""
        for domain in _all_domains():
            result = adapter.read_domain(domain)
            if isinstance(result, Parsed):
                assert result.edges, "domain {} parsed successfully with no edges".format(domain)

    def test_names_beginning_with_a_type_word_are_not_truncated(self, catalogue, adapter):
        """A name that starts with a type word survives reference resolution.

        Three agents and nine skills in the library genuinely begin with a type
        word. Blind prefix stripping turns them into slugs matching nothing,
        which degrades to a silent no-match.
        """
        type_words = catalogue.type_words
        assert type_words, "type-word vocabulary was not derived from the corpus"

        at_risk_agents = [name for name in catalogue.agents if name.startswith(tuple(w + "-" for w in type_words))]
        at_risk_skills = [name for name in catalogue.skills if name.startswith(tuple(w + "-" for w in type_words))]
        assert at_risk_agents, "no at-risk agent names found; this test has stopped testing anything"
        assert at_risk_skills, "no at-risk skill names found; this test has stopped testing anything"

        for name in at_risk_agents + at_risk_skills:
            readings = candidate_refs(name, type_words)
            assert readings, "no reading offered for {}".format(name)
            resolved = [reading for reading in readings if catalogue.kind_of(reading) is not None]
            assert resolved == [
                name
            ], "bare reference {} resolved to {} instead of itself; a stripped reading won".format(name, resolved)

        reached = set()
        for domain in _all_domains():
            result = adapter.read_domain(domain)
            if isinstance(result, Parsed):
                for edge in result.edges:
                    if edge.source in at_risk_agents or edge.target in at_risk_agents:
                        reached.add(edge.source if edge.source in at_risk_agents else edge.target)
        assert reached == set(at_risk_agents), "type-word-prefixed agents lost during resolution: {}".format(
            sorted(set(at_risk_agents) - reached)
        )

    def test_blind_prefix_stripping_would_lose_those_names(self, catalogue):
        """NEGATIVE CONTROL: the naive normaliser breaks the same names."""
        broken = []
        for name in list(catalogue.agents) + list(catalogue.skills):
            for word in catalogue.type_words:
                marker = word + "-"
                if name.startswith(marker):
                    stripped = name[len(marker) :]
                    if catalogue.kind_of(stripped) is None:
                        broken.append(name)
                    break
        assert broken, "blind stripping broke nothing; the hazard this guards against is gone"

    def test_domain_local_aliases_make_every_agent_reachable(self, adapter, catalogue):
        """Every catalogue agent is named by at least one resolvable edge.

        Two domains identify their nodes only by opaque codes. Without the
        per-domain alias table, 12 of the 508 agents are named by no resolvable
        edge and could never be selected, because candidacy requires an edge.
        """
        reached = set()
        alias_using_domains = 0
        for domain in _all_domains():
            result = adapter.read_domain(domain)
            assert isinstance(result, Parsed)
            if result.alias_count:
                alias_using_domains += 1
            for edge in result.edges:
                if edge.source_kind == "agent":
                    reached.add(edge.source)
                if edge.target_kind == "agent":
                    reached.add(edge.target)
        assert alias_using_domains > 0, "no domain needed an alias; this test has stopped testing anything"
        missing = sorted(set(catalogue.agents) - reached)
        assert missing == [], "agents unreachable through any KG edge: {}".format(missing)

    def test_disabling_aliases_strands_agents(self, catalogue, monkeypatch):
        """NEGATIVE CONTROL: without aliases some agents become unreachable."""
        adapter = DomainKgAdapter(catalogue)
        monkeypatch.setattr(DomainKgAdapter, "_domain_aliases", lambda self, domain: {})
        reached = set()
        for domain in _all_domains():
            result = adapter.read_domain(domain)
            if isinstance(result, Parsed):
                for edge in result.edges:
                    if edge.source_kind == "agent":
                        reached.add(edge.source)
                    if edge.target_kind == "agent":
                        reached.add(edge.target)
        assert set(catalogue.agents) - reached, "alias resolution is no longer load-bearing"


class _StubResolver:
    """Minimal resolver returning canned content, for adapter failure tests."""

    def __init__(self, by_suffix):
        """Store a suffix-to-content mapping; unmatched reads raise."""
        self._by_suffix = by_suffix

    def fetch_kg_file(self, relpath):
        """Return canned content for a matching suffix, else fail like the real tiers."""
        for suffix, content in self._by_suffix.items():
            if relpath.endswith(suffix):
                return _StubResource(relpath, content)
        raise LibrarySetupError(Path(relpath))

    def fetch_skill(self, name):
        """Unused by the adapter tests."""
        raise LibrarySetupError(Path(name))

    def fetch_agent(self, name):
        """Unused by the adapter tests."""
        raise LibrarySetupError(Path(name))


class _StubResource:
    """Resolved-resource stand-in carrying only what the adapter reads."""

    def __init__(self, path_or_url, content):
        """Store the path and content."""
        self.path_or_url = path_or_url
        self.content = content


# ---------------------------------------------------------------------------
# Catalogue and the dispatch contract
# ---------------------------------------------------------------------------


@requires_library
class TestCatalogueAndDispatchContract:
    """The catalogue is the naming authority and yields executable personas."""

    def test_catalogue_sizes_match_the_library(self, catalogue):
        """The loaded catalogue matches the library's own declared counts."""
        assert len(catalogue.agents) == EXPECTED_AGENT_COUNT
        assert len(catalogue.skills) == EXPECTED_SKILL_COUNT
        assert len(catalogue.domains) == EXPECTED_DOMAIN_COUNT
        assert catalogue.library_version

    def test_the_three_name_spaces_are_disjoint(self, catalogue):
        """Kind resolution by membership is only sound if nothing overlaps."""
        agents, skills, domains = set(catalogue.agents), set(catalogue.skills), set(catalogue.domains)
        assert agents & skills == set()
        assert agents & domains == set()
        assert skills & domains == set()

    def test_every_persona_path_exists_on_disk(self, catalogue):
        """Every agent the selector could emit has a liftable persona block.

        A selection that names an agent without a resolvable persona path is
        not executable: library agents are not registered subagent types, so a
        run spawns a generic subagent with the persona injected from this file.
        """
        missing = [
            record.name
            for record in catalogue.agents.values()
            if not (_LIBRARY_ROOT / record.persona_relpath).is_file()
        ]
        assert missing == [], "agents with no persona file: {}".format(missing[:10])

    def test_an_unreadable_catalogue_raises_rather_than_emptying(self):
        """NEGATIVE: an unresolvable catalogue is an error, not an empty library."""
        with pytest.raises(CatalogueUnavailable):
            load_catalogue(resolver=_StubResolver({}))

    def test_a_malformed_catalogue_raises_rather_than_emptying(self):
        """NEGATIVE: malformed catalogue JSON is an error, not an empty library."""
        with pytest.raises(CatalogueUnavailable):
            load_catalogue(resolver=_StubResolver({"agents_all.json": "{ not json"}))


# ---------------------------------------------------------------------------
# Criterion 2 -- ten sample tasks, every entry with a non-empty edge path
# ---------------------------------------------------------------------------


@requires_library
class TestTenSampleTasks:
    """Acceptance criterion 2 and its companion negatives."""

    def test_every_sample_task_returns_matches_with_non_empty_edge_paths(
        self, sample_tasks, catalogue, adapter, lexicon, uncapped_risk
    ):
        """All ten sample tasks return a ranked set, each entry edge-backed."""
        for task in sample_tasks:
            result = _select(task, catalogue, adapter, lexicon, uncapped_risk)
            assert result.degraded is None, "task degraded unexpectedly: {} -> {}".format(task, result.degraded)
            assert result.matches, "task returned no matches: {}".format(task)
            for match in result.matches:
                assert match.edge_path, "empty edge path for {} on task {}".format(match.agent, task)
                assert len(match.edge_path) >= 1

    def test_matches_are_ranked_by_descending_confidence(
        self, sample_tasks, catalogue, adapter, lexicon, uncapped_risk
    ):
        """A ranked set must actually be ranked."""
        for task in sample_tasks:
            result = _select(task, catalogue, adapter, lexicon, uncapped_risk)
            confidences = [match.confidence for match in result.matches]
            assert confidences == sorted(confidences, reverse=True)

    def test_every_edge_path_step_exists_in_the_source_domain_graph(
        self, sample_tasks, catalogue, adapter, lexicon, uncapped_risk
    ):
        """Edge paths cite real edges, checked against an independent re-read.

        The oracle re-reads the domain file directly and compares raw endpoint
        text, so a fabricated or mis-attributed path is caught rather than
        confirmed by the same code that produced it.
        """
        for task in sample_tasks:
            result = _select(task, catalogue, adapter, lexicon, uncapped_risk)
            for match in result.matches:
                raw_types, raw_endpoints = _oracle_type_and_endpoint_vocabulary(match.domain)
                for step in match.edge_path:
                    assert step.domain == match.domain
                    assert step.edge_type in raw_types, "edge type {} absent from {}".format(
                        step.edge_type, match.domain
                    )
                    for slug in (step.source, step.target):
                        assert _endpoint_is_traceable(
                            slug, raw_endpoints, match.domain
                        ), "endpoint {} on the path for {} is not traceable in {}".format(
                            slug, match.agent, match.domain
                        )

    def test_all_five_explainability_fields_are_present_and_non_empty(
        self, sample_tasks, catalogue, adapter, lexicon, uncapped_risk
    ):
        """The SRS FR-23 five fields are populated on every emitted match.

        Emitting them is the next issue's job; carrying them is this one's, and
        a downstream emitter cannot invent a field the selector never produced.
        """
        for task in sample_tasks:
            payload = _select(task, catalogue, adapter, lexicon, uncapped_risk).to_dict()
            for entry in payload["matches"]:
                assert entry["agent"] in catalogue.agents
                assert entry["domain"] in catalogue.domains
                assert entry["matched_skills"], "matched_skills empty for {}".format(entry["agent"])
                assert entry["edge_path"], "edge_path empty for {}".format(entry["agent"])
                assert isinstance(entry["confidence"], float) and entry["confidence"] > 0.0

    def test_matched_skills_are_real_catalogue_skills(self, sample_tasks, catalogue, adapter, lexicon, uncapped_risk):
        """Skills are library skills, not slugs invented from edge text."""
        for task in sample_tasks:
            result = _select(task, catalogue, adapter, lexicon, uncapped_risk)
            for match in result.matches:
                for skill in match.matched_skills:
                    assert skill in catalogue.skills, "unknown skill {} for {}".format(skill, match.agent)

    def test_every_match_records_a_resolvable_persona_path(
        self, sample_tasks, catalogue, adapter, lexicon, uncapped_risk
    ):
        """Dispatch contract: a match names the file its persona is lifted from."""
        for task in sample_tasks:
            result = _select(task, catalogue, adapter, lexicon, uncapped_risk)
            for match in result.matches:
                assert match.persona_relpath.endswith("agent.md")
                assert (_LIBRARY_ROOT / match.persona_relpath).is_file()
                assert match.agent in match.persona_relpath

    def test_an_empty_task_degrades_with_a_reason(self, catalogue, adapter, lexicon, uncapped_risk):
        """NEGATIVE: no scorable terms yields an explicit degraded outcome."""
        result = _select("   ", catalogue, adapter, lexicon, uncapped_risk)
        assert result.matches == ()
        assert result.degraded is not None
        assert result.degraded.reason == REASON_NO_QUERY_TERMS

    def test_an_unmatchable_task_degrades_rather_than_guessing(self, catalogue, adapter, lexicon, uncapped_risk):
        """NEGATIVE: a task the library cannot serve returns no silent default."""
        result = _select("zzqxwv jjplkm vvbnmq wwrtyu", catalogue, adapter, lexicon, uncapped_risk)
        assert result.matches == ()
        assert result.degraded is not None
        assert result.degraded.detail

    def test_a_result_is_never_empty_without_a_reason(self, sample_tasks, catalogue, adapter, lexicon, uncapped_risk):
        """Exactly one of matches and degraded is populated, never neither."""
        probes = list(sample_tasks) + ["", "zzqxwv jjplkm", "the"]
        for task in probes:
            result = _select(task, catalogue, adapter, lexicon, uncapped_risk)
            assert bool(result.matches) != (result.degraded is not None)

    def test_an_agent_named_by_no_edge_is_never_selected(self, catalogue, adapter, lexicon, uncapped_risk):
        """NEGATIVE: catalogue membership alone does not make an agent selectable.

        A synthetic agent is added to the catalogue with prose engineered to
        outscore everything, but with no presence in any graph. It must not
        appear, because an entry with no edge path would violate criterion 2.
        """
        from langgraph_engine.selection.catalogue import AgentRecord

        marker = "qqzxjv"
        phantom = "zzz-phantom-probe-agent"
        augmented = dict(catalogue.agents)
        augmented[phantom] = AgentRecord(
            name=phantom,
            domain=sorted(catalogue.domains)[0],
            description=" ".join([marker] * 20),
            role=marker,
            model="sonnet",
            mandatory_skills=(),
            optional_skills=(),
            persona_relpath="agents/{}/agent.md".format(phantom),
        )
        spiked = LibraryCatalogue(
            agents=augmented,
            skills=catalogue.skills,
            domains=catalogue.domains,
            type_words=catalogue.type_words,
            library_version=catalogue.library_version,
            _agents_by_domain=dict(catalogue._agents_by_domain),
            _skills_by_domain=dict(catalogue._skills_by_domain),
        )
        spiked._agents_by_domain[sorted(catalogue.domains)[0]] = tuple(
            list(catalogue.agents_in(sorted(catalogue.domains)[0])) + [phantom]
        )

        result = select_agents(
            marker,
            catalogue=spiked,
            adapter=DomainKgAdapter(spiked),
            risk=uncapped_risk,
            complexity=8,
        )
        selected = {match.agent for match in result.matches}
        assert phantom not in selected, "an agent named by no edge was selected"
        assert bool(result.matches) != (result.degraded is not None)


def _oracle_type_and_endpoint_vocabulary(domain):
    """Return the raw edge-type values and endpoint strings a domain file holds.

    Read straight from the file with no help from the adapter, so the check
    below is capable of disagreeing with the code that produced the path.
    """
    raw_types = set()
    raw_endpoints = set()
    for record in _oracle_edges(domain):
        if not isinstance(record, dict):
            continue
        for key in ("type", "relationship_type", "edge_type"):
            if isinstance(record.get(key), str):
                raw_types.add(record[key].strip())
        for key in ("source", "target", "source_id", "target_id"):
            if isinstance(record.get(key), str):
                raw_endpoints.add(record[key].strip())
    return raw_types, raw_endpoints


def _endpoint_is_traceable(slug, raw_endpoints, domain):
    """Return whether a resolved slug traces back to a raw endpoint or an alias.

    A resolved slug matches a raw endpoint either directly once folded, or
    after a type word is removed. Two domains name their nodes by opaque codes
    with no textual relationship to the slug at all, so those resolve through
    the domain's own node files instead.
    """
    for raw in raw_endpoints:
        folded = normalise_ref(raw)
        if folded == slug or folded.endswith("-" + slug) or folded.endswith(":" + slug):
            return True
    return _alias_backed(domain, slug)


def _alias_backed(domain, slug):
    """Return whether ``slug`` is a domain-local alias target in ``domain``.

    Used only by the edge-path oracle: two domains name their nodes by opaque
    codes, so a resolved slug legitimately has no textual counterpart among the
    raw endpoints.
    """
    for filename, keys in (("agents.json", ("agents", "nodes")), ("skills.json", ("skills", "nodes"))):
        path = _LIBRARY_ROOT / "knowledge-graph" / domain / filename
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else None
        if records is None and isinstance(payload, dict):
            for key in keys:
                if isinstance(payload.get(key), list):
                    records = payload[key]
                    break
        for record in records or []:
            if isinstance(record, dict) and normalise_ref(record.get("name")) == slug:
                return True
    return False


# ---------------------------------------------------------------------------
# Specificity control -- the criteria do not require it and should
# ---------------------------------------------------------------------------


def _mean_pairwise_overlap(result_sets):
    """Return the mean Jaccard similarity across every pair of result sets."""
    scores = []
    for index, left in enumerate(result_sets):
        for right in result_sets[index + 1 :]:
            union = left | right
            scores.append(len(left & right) / len(union) if union else 1.0)
    return sum(scores) / len(scores) if scores else 1.0


class _FlatLexicon:
    """A scorer that rates every document identically.

    Stands in for the degenerate selector the specificity control exists to
    catch: one that discriminates nothing and therefore returns the same
    agents whatever it is asked.
    """

    document_count = 1
    vocabulary_size = 1
    _average_length = 1.0

    def weight(self, term):
        """Return a constant weight."""
        return 1.0

    def median_weight(self):
        """Return a constant reference scale."""
        return 1.0

    def score(self, query_terms, document_text):
        """Return a constant score regardless of query or document."""
        return 1.0

    def informative_terms(self, terms, quantile=0.0):
        """Return the terms unchanged."""
        return set(terms)


@requires_library
class TestSpecificityControl:
    """Proof that the selector discriminates rather than matching everything."""

    def test_the_selector_discriminates_between_tasks(self, sample_tasks, catalogue, adapter, lexicon, uncapped_risk):
        """Different tasks get materially different agent sets.

        A selector that returned the whole roster would have perfect recall,
        zero collisions and zero value. Two independent measurements pin that
        down: the number of distinct agents drawn across the ten tasks, and the
        mean pairwise overlap between their result sets.
        """
        result_sets = []
        for task in sample_tasks:
            result = _select(task, catalogue, adapter, lexicon, uncapped_risk)
            assert result.matches
            result_sets.append({match.agent for match in result.matches})

        distinct = set().union(*result_sets)
        assert (
            len(distinct) >= SPECIFICITY_MIN_DISTINCT_AGENTS
        ), "only {} distinct agents across {} tasks; the selector is not discriminating".format(
            len(distinct), len(sample_tasks)
        )
        assert len(distinct) < len(catalogue.agents) / 2, "the selector is returning an implausible share of the roster"

        overlap = _mean_pairwise_overlap(result_sets)
        assert overlap <= SPECIFICITY_MAX_MEAN_OVERLAP, "mean inter-task overlap {:.3f} is too high".format(overlap)

    def test_a_non_discriminating_scorer_fails_the_same_control(self, sample_tasks, catalogue, adapter, uncapped_risk):
        """NEGATIVE CONTROL: a flat scorer must fail the measurement above.

        Without this, the thresholds could be loose enough to pass anything and
        the control would be decorative.
        """
        result_sets = []
        for task in sample_tasks:
            result = select_agents(
                task,
                catalogue=catalogue,
                adapter=adapter,
                risk=uncapped_risk,
                lexicon=_FlatLexicon(),
                complexity=8,
            )
            result_sets.append({match.agent for match in result.matches})

        distinct = set().union(*result_sets)
        overlap = _mean_pairwise_overlap(result_sets)
        assert (
            len(distinct) < SPECIFICITY_MIN_DISTINCT_AGENTS or overlap > SPECIFICITY_MAX_MEAN_OVERLAP
        ), "the flat scorer passed the specificity control, so the control proves nothing"

    def test_confidence_is_absolute_not_a_within_pool_rank(self, catalogue, adapter, lexicon, uncapped_risk):
        """The best of a weak field scores low, rather than being handed 1.0.

        Pool normalisation would make the top candidate maximally confident on
        every query, including one the library cannot serve. That is the silent
        default the fallback requirement exists to forbid.
        """
        strong = _select(
            "kubernetes autoscaling service mesh observability deployment",
            catalogue,
            adapter,
            lexicon,
            uncapped_risk,
        )
        assert strong.matches
        assert strong.matches[0].confidence < 1.0
        weak = _select("the and for with", catalogue, adapter, lexicon, uncapped_risk)
        weak_top = weak.matches[0].confidence if weak.matches else 0.0
        assert weak_top < strong.matches[0].confidence


# ---------------------------------------------------------------------------
# Criterion 3 -- never the truncated builder
# ---------------------------------------------------------------------------


@requires_library
class TestCoveragePrecondition:
    """Acceptance criterion 3, enforced in code rather than at review."""

    def test_an_uncapped_environment_reports_coverage_complete(self):
        """No override set means nothing can truncate."""
        complete, caps = probe_builder_coverage({})
        assert complete is True
        assert caps == ()

    def test_a_file_cap_marks_coverage_incomplete(self):
        """NEGATIVE: the file-discovery override is detected."""
        complete, caps = probe_builder_coverage({ENV_MAX_FILES: "300"})
        assert complete is False
        assert caps == ((ENV_MAX_FILES, "300"),)

    def test_a_path_cap_marks_coverage_incomplete(self):
        """NEGATIVE: the path-traversal override is detected too.

        Fixing only the file cap leaves this one truncating every traversal,
        which is the half-fix the prerequisite issue explicitly forbade.
        """
        complete, caps = probe_builder_coverage({ENV_MAX_PATHS: "500"})
        assert complete is False
        assert caps == ((ENV_MAX_PATHS, "500"),)

    def test_an_unparseable_cap_is_not_treated_as_a_cap(self):
        """The builder ignores a malformed override, so the probe must too."""
        complete, caps = probe_builder_coverage({ENV_MAX_FILES: "not-a-number"})
        assert complete is True
        assert caps == ()

    def test_selection_refuses_a_truncated_risk_signal(self, catalogue, adapter, lexicon):
        """NEGATIVE: selection against a capped graph raises rather than ranking."""
        truncated = RiskSignal(
            risk_level="medium",
            danger_zone_count=3,
            coverage_complete=False,
            source="builder",
            caps_in_force=((ENV_MAX_FILES, "300"),),
        )
        with pytest.raises(TruncatedRiskSignal) as excinfo:
            _select("fix the call graph builder", catalogue, adapter, lexicon, truncated)
        assert ENV_MAX_FILES in str(excinfo.value)

    def test_explicit_acceptance_allows_a_truncated_signal_through(self, catalogue, adapter, lexicon):
        """Partial coverage is usable only when the caller says so in writing."""
        truncated = RiskSignal("medium", 3, False, "builder", ((ENV_MAX_FILES, "300"),))
        result = _select(
            "fix the call graph builder truncation",
            catalogue,
            adapter,
            lexicon,
            truncated,
            accept_partial_coverage=True,
        )
        assert result.matches or result.degraded

    def test_complexity_outside_the_one_to_twentyfive_band_is_rejected(
        self, catalogue, adapter, lexicon, uncapped_risk
    ):
        """NEGATIVE: a 1-10 score passed as complexity is a mis-scaling, not a value.

        combined_complexity_score is on a 1-25 scale. Silently clamping an
        out-of-band value would bias every threshold downstream.
        """
        for bad in (0, 26, -1, 100):
            with pytest.raises(ComplexityOutOfRange):
                _select("anything", catalogue, adapter, lexicon, uncapped_risk, complexity=bad)

    @pytest.mark.slow
    def test_selection_runs_against_a_freshly_built_uncapped_call_graph(self, catalogue, adapter, lexicon, monkeypatch):
        """End-to-end: build the real graph with the fixed builder and select on it.

        This is the criterion's "a rebuilt (FR-9a-fixed) call graph" branch
        exercised for real rather than simulated, so the selector is shown
        consuming a signal the shipping builder actually produced.
        """
        monkeypatch.delenv(ENV_MAX_FILES, raising=False)
        monkeypatch.delenv(ENV_MAX_PATHS, raising=False)

        from langgraph_engine.sdlc_pipeline.call_graph_analyzer import analyze_impact_before_change

        analysis = analyze_impact_before_change(
            str(PROJECT_ROOT), target_files=["langgraph_engine/selection/selector.py"]
        )
        assert analysis["call_graph_available"] is True

        risk = RiskSignal.from_impact_analysis(analysis)
        assert risk.coverage_complete is True
        assert risk.caps_in_force == ()

        result = _select(
            "fix call-graph discovery truncation so every package is analysed",
            catalogue,
            adapter,
            lexicon,
            risk,
        )
        assert result.matches
        for match in result.matches:
            assert match.edge_path


# ---------------------------------------------------------------------------
# Lexicon behaviour that the selection quality rests on
# ---------------------------------------------------------------------------


class TestLexicon:
    """Term weighting is measured from the corpus, not declared."""

    def test_a_term_in_every_document_carries_almost_no_weight(self):
        """The corpus supplies its own stopwords."""
        lex = Lexicon(["alpha common", "beta common", "gamma common", "delta common"])
        assert lex.weight("common") < lex.weight("alpha")

    def test_an_unseen_term_is_treated_as_maximally_rare(self):
        """An unusual word is a strong signal, not a weightless one."""
        lex = Lexicon(["alpha common", "beta common"])
        assert lex.weight("neverseen") >= lex.weight("alpha")

    def test_length_normalisation_stops_long_documents_from_winning(self):
        """NEGATIVE-BY-CONSTRUCTION: without it, verbosity beats relevance.

        Both documents match the query on exactly one term. The longer one adds
        nothing relevant, so it must not outscore the shorter one.
        """
        padding = " ".join("pad{}".format(index) for index in range(200))
        lex = Lexicon(["target alpha", "target " + padding, "unrelated beta"])
        short_score = lex.score({"target"}, "target alpha")
        long_score = lex.score({"target"}, "target " + padding)
        assert short_score > long_score

    def test_no_overlap_scores_zero(self):
        """No shared term is no evidence, not weak evidence."""
        lex = Lexicon(["alpha beta", "gamma delta"])
        assert lex.score({"omega"}, "alpha beta") == 0.0

    def test_an_empty_corpus_does_not_divide_by_zero(self):
        """Degenerate input yields uniform weights rather than an exception."""
        lex = Lexicon([])
        assert lex.weight("anything") == 1.0
        assert lex.median_weight() == 1.0
