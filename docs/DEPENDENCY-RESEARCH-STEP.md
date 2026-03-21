# Dependency Research Step — Design Document

**Feature:** Automated Library & Dependency Research
**Proposed Step:** Between Step 1 (Plan Mode Decision) and Step 2 (Plan Execution)
**Flag:** `ENABLE_DEP_RESEARCH` (default: `0` — opt-in)
**Status:** Design Phase
**Last Updated:** 2026-03-21

---

## Table of Contents

1. [The Core Idea](#1-the-core-idea)
2. [Why This Matters](#2-why-this-matters)
3. [R&D Findings](#3-rd-findings)
4. [Architecture Design](#4-architecture-design)
5. [Pipeline Integration](#5-pipeline-integration)
6. [Confidence-Based Output Strategy](#6-confidence-based-output-strategy)
7. [Quality Scoring Model](#7-quality-scoring-model)
8. [Cross-Language Interoperability](#8-cross-language-interoperability)
9. [Implementation Plan](#9-implementation-plan)
10. [State Fields](#10-state-fields)
11. [Benefits & Impact](#11-benefits--impact)
12. [Risks & Mitigations](#12-risks--mitigations)
13. [Open Questions](#13-open-questions)

---

## 1. The Core Idea

> "Aaj ke time me mostly parts of any software kahi na kahi pade huye hain — kuch bhi aisa nahi jo net pe na ho. Bhale complete system nahi milega lekin system ko chalane wale parts zaroor mil jaenge."

Today, before writing any code, a senior engineer always asks:
- Does this problem already have a solution somewhere?
- Is there a library, SDK, native DLL, or REST API that handles this?
- Should I build this from scratch — or reuse and integrate?

This is the **Build vs Buy** decision. It is one of the most valuable engineering judgements but it is completely missing from automated pipelines today. Every existing AI coding pipeline jumps straight from "task description" to "code generation" — skipping the research phase entirely.

**This step adds that research phase to the pipeline.**

### What This Step Does

Given a task description, before any code planning begins, this step:

1. Understands what the task *actually needs* (functional intent extraction)
2. Searches multiple package registries and platforms in parallel
3. Evaluates candidates on quality signals (downloads, maintenance, security, license)
4. Presents findings to the user in Plan Mode with confidence levels
5. Injects approved dependencies into the plan for Step 2

### Key Design Philosophy

**Task-first, not language-first.**

A project written in Python might be best served by a C library with Python bindings. A Java project might call a Go microservice via gRPC. A Node.js app might use a Rust-compiled WASM module. The research is not constrained by the project's primary language — it covers the full ecosystem of solutions.

---

## 2. Why This Matters

### The Problem with Current Pipeline

```
Step 0: Task Analysis
Step 1: Plan Mode Decision
Step 2: Plan Execution  ←── HERE: LLM generates a plan and starts coding
                              with NO knowledge of what already exists
```

**Result:** The pipeline reinvents wheels. It writes custom HTTP clients when `httpx` exists. It builds retry logic when `tenacity` exists. It implements image processing from scratch when `libvips` (10x faster than Pillow) already has a Python wrapper.

### What a Senior Engineer Actually Does

```
Task arrives
    ↓
"What exactly does this need?" (intent extraction)
    ↓
"Does something already exist for this?" (research)
    ↓
"Which option is best? License OK? Maintained? Secure?" (evaluation)
    ↓
"OK, now I know what to build vs reuse" (informed planning)
    ↓
Implementation with real libraries, not reinvented ones
```

### The Gap in Existing Tools

| Tool | What It Does | Does It Suggest New Libraries? |
|------|-------------|-------------------------------|
| Dependabot / Renovate | Updates existing deps | No — only bumps versions you already use |
| GitHub Copilot | Inline code completion | Implicitly, during typing — no registry validation |
| Snyk Advisor | Security scoring | No — evaluates what you give it |
| libraries.io | Package discovery | Yes — but manual search, not task-driven |
| npms.io | npm scoring | Yes — but npm-only, manual search |

**No tool exists that does what this step proposes:** given a task description, proactively research and rank the best libraries across ecosystems before a single line of code is planned.

---

## 3. R&D Findings

### 3.1 Available Registry APIs (All Free, No Paid Subscription Needed)

| Registry | Search Endpoint | Auth | Notes |
|----------|----------------|------|-------|
| **PyPI** | `pypi.org/pypi/{name}/json` | None | No keyword search API; use libraries.io for discovery |
| **Maven Central** | `search.maven.org/solrsearch/select?q=...` | None | Solr-based, supports field queries |
| **npm** | `registry.npmjs.org/-/v1/search?text=...` | None | Includes composite quality score |
| **npms.io** | `api.npms.io/v2/search?q=...` | None | Richer quality/maintenance/popularity scores |
| **NuGet** | Dynamic URL from `api.nuget.org/v3/index.json` | None | Has totalDownloads inline |
| **crates.io** | `crates.io/api/v1/crates?q=...` | None (needs User-Agent) | Rich recent_downloads field |
| **GitHub** | `api.github.com/search/repositories?q=...` | Optional | Best for cross-language discovery |
| **libraries.io** | `libraries.io/api/:platform/:name` | Free API key | Covers **32 package managers** in one API |
| **deps.dev** | `api.deps.dev/v3alpha/` | None | Google's OSI — 7 ecosystems, license + CVEs + dep graph |
| **OSV.dev** | `api.osv.dev/v1/query` | None | Vulnerability data for 40+ ecosystems |
| **OpenSSF Scorecard** | `api.scorecard.dev/projects/github.com/{org}/{repo}` | None | 16-check security posture score |
| **pypistats.org** | `pypistats.org/api/packages/{pkg}/recent` | None | Python download counts |
| **bundlephobia** | `bundlephobia.com/api/size?package={name}@{ver}` | None | JS bundle size and tree-shaking info |

**Best strategy:** Use `deps.dev` as primary aggregator (7 ecosystems, no auth, returns license + CVEs + dependency graph + Scorecard in one call). Use `libraries.io` as secondary (32 ecosystems, free API key). Use ecosystem-specific APIs for download counts.

### 3.2 LLM + Library Research — Known Failure Modes (from arXiv Research)

These are documented problems in AI-suggested libraries that this step must solve:

| Failure Mode | Rate | Source | Our Mitigation |
|-------------|------|--------|----------------|
| Package hallucination (invented names) | ~4.6% | arXiv:2507.10818 | Verify every suggestion against registry API |
| Restrictive copyleft license not disclosed | 14.2% | arXiv:2408.05128 | Auto-fetch and flag license from registry |
| Import name ≠ install name | 4.6% | arXiv:2507.10818 | Fetch both names from registry metadata |
| Version staleness (training cutoff) | High | arXiv:2401.16340 | Always fetch current `latest_version` from API |
| No version pinning suggested | 91% of cases | arXiv:2401.16340 | Include exact version in output |
| No alternatives compared | Common | General observation | Structured pipeline forces multi-candidate ranking |

### 3.3 The "Build vs Buy" Decision Framework

Senior engineers use a multi-dimensional checklist. These are the signals that matter:

**Disqualifiers (auto-reject a library if any of these fail):**
- License is copyleft (GPL/AGPL) and project is commercial
- Known unpatched CVE at Critical or High severity
- Last commit > 2 years ago (for security-relevant libraries)
- Package does not exist in registry (hallucination check)
- Archived/deprecated status on GitHub

**Strong positive signals:**
- Weekly downloads: substantial relative to ecosystem
- GitHub stars: > 500 for niche, > 5,000 for general-purpose
- Version count > 10 (indicates iterative, active development)
- Issues: more closed than open (active maintenance)
- OpenSSF Scorecard > 7/10
- Presence of CI, tests, documentation

**Warning signals (show to user, don't auto-reject):**
- Single maintainer, no organization backing
- High transitive dependency count (attack surface)
- Dependencies themselves have security advisories
- No SECURITY.md disclosure policy

---

## 4. Architecture Design

### 4.1 Step Overview

```
┌─────────────────────────────────────────────────────────────────┐
│              STEP 1b: DEPENDENCY RESEARCH                        │
│              (Between Step 1 and Step 2)                         │
│              Controlled by: ENABLE_DEP_RESEARCH=1               │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
    ┌─────────▼──────┐  ┌─────▼──────┐  ┌────▼───────────┐
    │  Phase 1       │  │  Phase 2   │  │  Phase 3       │
    │  Intent        │  │  Registry  │  │  Quality       │
    │  Extraction    │  │  Search    │  │  Scoring &     │
    │  (LLM)         │  │  (APIs)    │  │  Ranking       │
    └────────────────┘  └────────────┘  └────────────────┘
              │               │               │
              └───────────────┼───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │         Phase 4               │
              │  Confidence Assessment &      │
              │  Plan Mode Presentation       │
              └───────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │                               │
    ┌─────────▼──────────┐       ┌────────────▼────────────┐
    │  HIGH CONFIDENCE   │       │  LOW CONFIDENCE          │
    │  Auto-inject into  │       │  Surface to user in     │
    │  Step 2 plan       │       │  Plan Mode with context  │
    │  + update dep files│       │  Engineer decides        │
    └────────────────────┘       └─────────────────────────┘
```

### 4.2 Phase 1 — Intent Extraction

**Input:** `user_message`, `step0_task_type`, `step0_complexity`, detected language/framework from Level 2 standards

**LLM Task:** Extract structured search intent:

```json
{
  "functional_domain": "image processing",
  "sub_requirements": ["resize", "compress", "format conversion"],
  "performance_sensitivity": "high",
  "primary_language": "python",
  "allow_cross_language": true,
  "constraint_hints": ["no GPL", "must support async"]
}
```

**Output:** Structured search queries per registry.

### 4.3 Phase 2 — Multi-Registry Parallel Search

**Parallel HTTP calls to:**

1. **deps.dev** — Primary aggregator. Returns license, CVEs, dependency graph, Scorecard score for 7 ecosystems
2. **GitHub search** — Language-agnostic discovery. Returns stars, forks, last commit, issues
3. **Ecosystem-specific APIs** — Based on detected language:
   - Python: PyPI JSON + pypistats.org
   - Java: Maven Central Solr
   - JS/TS: npms.io
   - .NET: NuGet search
   - Rust: crates.io
   - Any: libraries.io (covers 32 managers)
4. **OSV.dev** — Vulnerability lookup for shortlisted candidates

**Cross-language search:** Always run GitHub search regardless of primary language. If a C/Rust/Go library has Python/Java bindings, it may outperform pure-language alternatives.

### 4.4 Phase 3 — Quality Scoring

**Composite score formula:**

```
score = (0.30 × popularity_score)
      + (0.30 × maintenance_score)
      + (0.20 × security_score)
      + (0.20 × semantic_similarity)
```

**Popularity score** (normalized 0-1):
- Downloads per week (relative to ecosystem average)
- GitHub stars
- Dependent packages count

**Maintenance score** (normalized 0-1):
- Days since last commit (inverse)
- Open/closed issues ratio
- Version frequency
- Contributor count

**Security score** (normalized 0-1):
- CVE count (Critical=-1.0, High=-0.5, Medium=-0.2, Low=-0.1)
- OpenSSF Scorecard (0-10 → normalized)
- License in approved list (boolean)

**Semantic similarity** (0-1):
- Vector similarity between task intent embedding and package description embedding

### 4.5 Phase 4 — Confidence-Based Output

This is the key design insight: **LLM decisions are not always reliable, but user + LLM combined is**. Instead of making all decisions silently, show the user what was found and at what confidence level.

```
HIGH CONFIDENCE (score ≥ 0.80):
  → Auto-suggest in plan
  → Inject install command into requirements.txt / pom.xml / package.json
  → Show to user in Plan Mode as "Recommended (auto-added)"

MEDIUM CONFIDENCE (score 0.55–0.79):
  → Show to user in Plan Mode
  → Display reasoning: "Found X — good maintenance, 2M downloads/week,
    MIT license. Possible fit but verifying cross-language compatibility."
  → User approves/rejects/modifies before Step 2 proceeds

LOW CONFIDENCE (score < 0.55):
  → Show as "Research note" in Plan Mode
  → Do NOT auto-add to dependency files
  → "Found libvips (C library) with pyvips Python bridge.
    10x faster than Pillow for large images.
    Unsure if your deployment environment supports native libs.
    → Your call, engineer."

DISQUALIFIED:
  → Show as warning: "Considered X but rejected: GPL-3.0 license,
    last commit 3 years ago, 2 unpatched CVEs."
  → Transparency: user sees what was evaluated and why it was rejected
```

---

## 5. Pipeline Integration

### 5.1 Placement in Current Pipeline

```
Step 0:  Task Analysis
Step 1:  Plan Mode Decision
         │
         ├── [ENABLE_DEP_RESEARCH=1] ──► Step 1b: Dependency Research
         │                                          │
         │                               (injects dep_research_context
         │                                into state for Step 2)
         │                                          │
         └──────────────────────────────────────────┘
                                                    │
Step 2:  Plan Execution  ◄──────────────────────────┘
         (now aware of available libraries)
```

**When ENABLE_DEP_RESEARCH=0 (default):** Step 1 → Step 2 directly. No change to existing behavior.

**When ENABLE_DEP_RESEARCH=1:** Step 1 → Step 1b → Step 2. Step 2 receives `step1b_dep_research_context` with ranked library suggestions.

### 5.2 Effect on Downstream Steps

| Step | Impact When Dep Research Active |
|------|--------------------------------|
| **Step 2 (Plan)** | Plan is informed by what libraries exist — avoids reinventing wheels |
| **Step 3 (Breakdown)** | Task phases may be simpler (e.g., "integrate X" instead of "build X") |
| **Step 7 (Final Prompt)** | Prompt includes suggested libraries with install commands |
| **Step 10 (Implementation)** | Implementation uses real, validated libraries — not invented ones |
| **Step 13 (Docs)** | Dependencies section of docs auto-populated from research results |

### 5.3 Dependency File Auto-Update

For HIGH confidence suggestions:

| Language | File Updated | Format |
|----------|-------------|--------|
| Python | `requirements.txt` | `library-name==x.y.z` |
| Python (modern) | `pyproject.toml` | `[project.dependencies]` entry |
| Java (Maven) | `pom.xml` | `<dependency>` block |
| Java (Gradle) | `build.gradle` | `implementation '...'` |
| Node.js | `package.json` | `dependencies` or `devDependencies` |
| .NET | `.csproj` | `<PackageReference>` |
| Rust | `Cargo.toml` | `[dependencies]` entry |

For MEDIUM confidence: suggest the exact line to add but do not write to file automatically.

---

## 6. Confidence-Based Output Strategy

This is what makes the feature work for the cases where LLM alone cannot decide.

### 6.1 Plan Mode Display Format

When Plan Mode is active (Step 1 decides plan is needed), the dependency research findings appear in the plan review:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 DEPENDENCY RESEARCH RESULTS
 Task: "Add high-performance image compression to the API"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 AUTO-ADDED (High Confidence: 0.91)
 ✓ Pillow 10.3.0 — MIT license
   Python image processing. 1.2M downloads/week.
   Last commit: 12 days ago. 0 CVEs.
   → Added to requirements.txt

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 REVIEW NEEDED (Medium Confidence: 0.67) — your call:
 ? pyvips 2.2.1 — MIT license (wraps libvips C library)
   10-15x faster than Pillow for large images.
   90K downloads/week. Last commit: 45 days ago. 0 CVEs.
   Requires libvips native library on deployment server.
   → [APPROVE to add] [REJECT] [Engineer will decide]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 RESEARCH NOTE (Low Confidence: 0.41) — FYI:
 ℹ sharp (Node.js) — Apache 2.0
   Best-in-class performance. Your project is Python but
   could be called as a microservice via REST if performance
   is critical and pyvips is not an option.
   → NOT added. Engineer judgement required.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 REJECTED (with reason):
 ✗ imagepy — GPL-3.0 license (incompatible with commercial use)
 ✗ quick-image — Last commit: 3 years ago. No longer maintained.
 ✗ imgfastlib — Package not found in PyPI (hallucination check failed)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 6.2 Collaborative Intelligence Model

```
LLM Confidence High  + Engineer Reviews  =  Best outcome always
LLM Confidence Low   + Engineer Reviews  =  Human intelligence fills gap
LLM Wrong            + Engineer Reviews  =  Caught before implementation

The pipeline presents its reasoning → Engineer adds domain knowledge
→ Combined result beats either alone
```

This is the core principle: **do not silently make decisions with low confidence; make the reasoning visible and let the engineer decide**.

---

## 7. Quality Scoring Model

### 7.1 License Approval Matrix

Auto-approved (no flag, safe for commercial use):

```
MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC,
Unlicense, 0BSD, MPL-2.0, CC0-1.0
```

Auto-flagged (show warning, user decides):

```
LGPL-2.0, LGPL-2.1, LGPL-3.0 → Safe if dynamically linked; risky if statically linked
EPL-1.0, EPL-2.0             → Eclipse projects; generally OK with disclosure
CDDL-1.0                     → OK with disclosure
```

Auto-rejected (disqualifier for commercial projects):

```
GPL-2.0, GPL-3.0             → Derivative works must be open-sourced
AGPL-3.0                     → Network use triggers copyleft (SaaS = copyleft)
SSPL-1.0                     → MongoDB license; very restrictive
No license                   → Legally risky; no explicit permission
```

### 7.2 Maintenance Health Thresholds

| Metric | Green | Yellow | Red |
|--------|-------|--------|-----|
| Last commit | < 3 months | 3-12 months | > 12 months |
| Open/total issues ratio | < 30% | 30-60% | > 60% |
| Version count | > 10 | 3-10 | < 3 |
| Contributor count | > 5 | 2-5 | 1 (bus factor) |
| OpenSSF Scorecard | > 7 | 5-7 | < 5 |

### 7.3 Security Thresholds

| CVE Severity | Action |
|-------------|--------|
| Critical (CVSS ≥ 9.0) | Auto-reject; show in Rejected list |
| High (CVSS 7.0-8.9) | Auto-reject unless patch available for latest version |
| Medium (CVSS 4.0-6.9) | Yellow warning; show to user |
| Low (CVSS < 4.0) | Note only; no impact on score |
| No CVEs | Green signal; positive score boost |

---

## 8. Cross-Language Interoperability

A core design principle: **the research is not limited to the project's primary language**. When a better solution exists in another language, the pipeline surfaces it.

### 8.1 Common Interop Patterns

#### Python Using Native Libraries

| Bridge | When to Use | Example |
|--------|------------|---------|
| `ctypes` | Simple C APIs, system libs, no compilation needed | `libsodium` via ctypes |
| `cffi` | Complex C libs, PyPy/GraalPy compatible | `libssl` via cffi |
| `PyO3 + maturin` | Rust library with memory safety | `polars` (Rust → Python) |
| `Cython` | Performance inner loops, wrapping C++ | `lxml` (libxml2 → Python) |
| Direct wheel | Pre-compiled wheel includes native binary | `pyvips`, `Pillow-SIMD` |

#### Java Using Native Libraries

| Bridge | When to Use | Example |
|--------|------------|---------|
| `JNI` | Full native control, C/C++ | `OpenCV` Java bindings |
| `JNA` | Simpler FFI, no per-platform compilation | `libffi` via JNA |
| `Project Panama` | Modern Java (JDK 22+), safer JNI replacement | System call integration |

#### JavaScript/TypeScript

| Bridge | When to Use | Example |
|--------|------------|---------|
| `WASM` | Browser + Node.js, any language compiled | `ffmpeg.wasm` (C → WASM) |
| `N-API native addon` | Node.js only, tight C/C++ integration | `sharp` (libvips → Node) |

#### Any Language

| Bridge | When to Use |
|--------|------------|
| REST API call | Loose coupling, any language, deployed service |
| gRPC service | Typed cross-language RPC, high performance |
| Message queue | Async cross-language communication |
| Docker sidecar | Run a native process alongside the app |

### 8.2 How the Pipeline Handles Cross-Language Suggestions

When a cross-language library is found with a higher quality score than a native alternative:

1. Detect if a binding/wrapper exists for the project's primary language
2. If yes → treat as regular suggestion with note "wraps [language] library"
3. If no wrapper exists → show as "Low Confidence Research Note" with interop pattern suggestion
4. Let the engineer decide if the performance gain is worth the integration complexity

---

## 9. Implementation Plan

### 9.1 New Files to Create

```
scripts/langgraph_engine/
├── dependency_researcher.py          ← Core research logic (Phase 1-3)
├── dep_research_registry_client.py   ← HTTP clients for all registry APIs
└── dep_research_scorer.py            ← Quality scoring model

policies/03-execution-system/
└── 01b-dependency-research/
    └── dependency-research-policy.md ← Policy rules for this step

tests/
├── test_dependency_researcher.py
└── test_dep_research_registry_client.py
```

### 9.2 Files to Modify

```
scripts/langgraph_engine/state/state_definition.py     ← Add step1b_* fields
scripts/langgraph_engine/state/step_keys.py            ← Add STEP1B_* constants
scripts/langgraph_engine/subgraphs/level3_execution.py ← Add step1b core function
scripts/langgraph_engine/subgraphs/level3_execution_v2.py ← Add node wrapper
scripts/langgraph_engine/orchestrator.py               ← Register node + edges
.env.example                                            ← Add ENABLE_DEP_RESEARCH
docs/WORKFLOW.md                                        ← Update pipeline docs
```

### 9.3 Node Pattern (Following Existing Convention)

```python
# In level3_execution_v2.py
def step1b_dependency_research_node(state: FlowState) -> Dict[str, Any]:
    """Step 1b: Dependency Research — only runs if ENABLE_DEP_RESEARCH=1."""
    if os.environ.get("ENABLE_DEP_RESEARCH", "0") != "1":
        return {
            "step1b_skipped": True,
            "step1b_dep_candidates": [],
            "step1b_auto_approved": [],
        }
    return _run_step(
        "1b", "Dependency Research",
        step1b_dependency_research,
        state,
        fallback_result={
            "step1b_skipped": False,
            "step1b_dep_candidates": [],
            "step1b_auto_approved": [],
            "step1b_needs_review": [],
            "step1b_research_notes": [],
            "step1b_rejected": [],
            "step1b_error": "Dependency research failed — continuing without",
        },
    )
```

### 9.4 RAG Integration

This step produces decisions that are highly cacheable. If the same task type has been seen before (e.g., "HTTP client library for Python"), the RAG cache will serve the previous research result without new API calls.

- **Collection:** `node_decisions` (existing)
- **RAG threshold:** 0.82 (reuse previous research if similarity >= 0.82)
- **Cache TTL consideration:** Library data changes — RAG entries for this step should have a shorter effective lifetime (suggest: flag entries older than 30 days as "verify before use")

### 9.5 Environment Variables

```bash
# Enable dependency research step
ENABLE_DEP_RESEARCH=1

# Optional: libraries.io API key (covers 32 package managers)
LIBRARIES_IO_API_KEY=your_free_api_key

# Optional: GitHub token for higher rate limits on GitHub search
GITHUB_TOKEN=your_token  # already used by pipeline

# Optional: approved license list override (comma-separated SPDX IDs)
DEP_RESEARCH_APPROVED_LICENSES=MIT,Apache-2.0,BSD-2-Clause,BSD-3-Clause

# Optional: minimum quality score to auto-approve (default: 0.80)
DEP_RESEARCH_AUTO_APPROVE_THRESHOLD=0.80

# Optional: minimum score to show (below this = silent discard)
DEP_RESEARCH_MIN_SHOW_THRESHOLD=0.40
```

---

## 10. State Fields

New fields added to `FlowState` in `state/state_definition.py`:

```python
# ==================== STEP 1b: DEPENDENCY RESEARCH ====================
# (only populated when ENABLE_DEP_RESEARCH=1)

step1b_skipped: Optional[bool]               # True when flag is disabled
step1b_intent: Optional[Dict]                # Extracted search intent
step1b_search_queries: Optional[Dict]        # Queries sent to each registry
step1b_raw_results: Optional[Dict]           # Raw API responses (for debug)

step1b_dep_candidates: Optional[List[Dict]]  # All candidates found, scored
step1b_auto_approved: Optional[List[Dict]]   # HIGH confidence — auto-added
step1b_needs_review: Optional[List[Dict]]    # MEDIUM confidence — needs user input
step1b_research_notes: Optional[List[Dict]]  # LOW confidence — FYI only
step1b_rejected: Optional[List[Dict]]        # Disqualified (with reason)

step1b_dep_files_updated: Optional[List[str]] # Files modified (requirements.txt etc)
step1b_plan_summary: Optional[str]           # Formatted summary for Plan Mode display
step1b_execution_time_ms: Optional[float]    # Timing
step1b_error: Optional[str]                  # Non-blocking error message
```

New constants in `state/step_keys.py`:

```python
STEP1B_SKIPPED = "step1b_skipped"
STEP1B_INTENT = "step1b_intent"
STEP1B_DEP_CANDIDATES = "step1b_dep_candidates"
STEP1B_AUTO_APPROVED = "step1b_auto_approved"
STEP1B_NEEDS_REVIEW = "step1b_needs_review"
STEP1B_RESEARCH_NOTES = "step1b_research_notes"
STEP1B_REJECTED = "step1b_rejected"
STEP1B_DEP_FILES_UPDATED = "step1b_dep_files_updated"
STEP1B_PLAN_SUMMARY = "step1b_plan_summary"
STEP1B_ERROR = "step1b_error"
```

---

## 11. Benefits & Impact

### 11.1 Direct Benefits

| Benefit | Description |
|---------|-------------|
| **No reinvented wheels** | Pipeline knows what exists before planning — plans reuse, not rebuild |
| **Faster implementation** | Using a proven library is faster than writing equivalent code from scratch |
| **Higher code quality** | Battle-tested libraries have edge cases handled that custom code would miss |
| **Security by default** | CVE check prevents introducing vulnerable dependencies unknowingly |
| **License compliance** | Copyleft licenses are caught before they pollute the codebase |
| **Cross-language awareness** | Best-in-class solution is found regardless of primary language |

### 11.2 Confidence Model Benefits

| Scenario | Without This Feature | With This Feature |
|----------|---------------------|------------------|
| Obvious library exists | LLM may or may not suggest it; no verification | Auto-detected, verified, auto-added |
| Cross-language lib better | LLM stays in primary language | Surfaces alternative with interop path |
| LLM is uncertain | Silently makes wrong decision | Shows user the uncertainty, engineer decides |
| Library has CVE | No check | Auto-rejected with reason shown |
| Library is GPL | No check | Flagged before it enters codebase |
| LLM hallucinates package | Package added to plan; fails at install | Registry check catches it immediately |

### 11.3 Quantified Value (from R&D research)

Based on arXiv findings:
- 14.2% of LLM-suggested libraries have license issues → caught by license gate
- 4.6% of LLM-suggested packages don't exist → caught by registry verification
- 91% of LLM conversations skip version pinning → fixed by always including pinned version

Practical time savings: estimating 30-60 minutes of research time saved per task where a relevant library is found. For complex tasks with multiple dependencies, this compounds significantly.

---

## 12. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Registry API rate limiting | Medium | Low | Caching + exponential backoff + RAG reuse for similar tasks |
| Irrelevant suggestions for internal business logic tasks | High | Low | LLM intent extraction filters task types; skip if "internal domain logic" detected |
| Slow API calls blocking pipeline | Medium | Medium | Parallel HTTP calls + configurable timeout; fallback to LLM-only suggestion if APIs timeout |
| Wrong cross-language suggestion (no viable binding exists) | Medium | Low | Always verify binding exists before surfacing cross-language suggestion |
| RAG cache serving stale library data | Low | Medium | Timestamp-based cache freshness check; suggest re-verify if entry > 30 days old |
| User overwhelmed by too many suggestions | Medium | Low | Cap at 3 auto-approved + 3 review-needed + 3 research notes maximum |
| Network unavailable (offline environment) | Low | Medium | Graceful degradation — step skips with warning, pipeline continues |

---

## 13. Open Questions

These require engineering decisions before implementation:

1. **Step numbering:** Insert as "Step 1b" (keeping current 0-14 numbering) or renumber all steps to 0-15? Recommendation: use "Step 1b" to avoid breaking existing state field names.

2. **RAG cache TTL:** Library data changes — should dep research RAG entries expire faster than other node decisions? Recommendation: add `cache_valid_days` metadata to RAG entries for this step.

3. **Scope of auto-update:** Should HIGH confidence libraries be auto-added to dependency files without any user prompt, or always show in Plan Mode first even if confidence is high? Recommendation: always show in Plan Mode (pipeline runs with Plan Mode for complex tasks), auto-add only in non-plan mode.

4. **Cross-language threshold:** At what complexity/confidence level should a cross-language suggestion be surfaced? A C library suggestion for a Python project adds integration complexity. Recommendation: only surface if cross-language quality score > 0.75 and a Python binding with > 10K downloads exists.

5. **Hook Mode behavior:** In Hook Mode (Steps 0-9 only), should the dependency file updates be applied before the user implements (Step 10)? Recommendation: yes — dep research output should be available to the engineer before they begin implementation.

---

## Summary

This step fills the most critical gap in any AI development pipeline: **the research phase that every senior engineer does mentally but no tool automates**.

The design is practical because:
- It uses free, public APIs — no paid infrastructure needed
- It fails gracefully — network issues or wrong suggestions don't block the pipeline
- It is opt-in — existing workflows are unchanged (`ENABLE_DEP_RESEARCH=0` default)
- It uses the confidence model — LLM uncertainty is surfaced to the engineer, not hidden
- It is RAG-cached — same task types reuse previous research without new API calls
- It is language-agnostic — finds the best solution regardless of primary language

The "collaborative intelligence" model — where the LLM presents findings with confidence levels and the engineer fills the gaps — is what makes this reliable despite the documented limitations of LLMs in library recommendation tasks.

---

*Generated from R&D analysis on 2026-03-21. Next step: engineering review and implementation planning.*
