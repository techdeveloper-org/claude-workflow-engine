# Code Graph Analysis Policy - Step 3.0.1

**Version:** 1.0.0
**Step:** 3.0.1 (Pre-Flight, after Context Reading)
**Type:** Non-Blocking Pre-Flight
**Script:** `scripts/architecture/03-execution-system/00-code-graph-analysis/code-graph-analyzer.py`

---

## Purpose

Calculate **true structural complexity** of a codebase by building a dependency
graph from actual source code. This replaces keyword-only guessing with real
analysis of imports, call chains, coupling, and centrality.

**Problem with keyword-only complexity:**
- Keyword scoring is 10-20% accurate at best
- A message saying "add button" gets low score even if that button touches 40 files
- A message saying "refactor architecture" gets high score even for a 3-file project

**Solution - Graph-Based Complexity:**
- Parse actual source files to extract import/dependency relationships
- Build a directed dependency graph (DAG) using NetworkX
- Calculate real metrics: fan-out, coupling, centrality, depth, density
- Combine with keyword score: `FINAL = (keyword * 0.3) + (graph * 0.7)`

---

## Execution Order

```
Step 3.0.0  Context Reading   -> tech_stack, project_name (REQUIRED INPUT)
Step 3.0.1  Code Graph Analysis -> graph_complexity_score   (THIS STEP)
Step 3.0    Prompt Generation  -> uses BOTH keyword + graph complexity
```

**Why after 3.0.0?** Graph analyzer needs `tech_stack` from context reading to
know HOW to parse imports (Python `import` vs Java `import` vs JS `require`).

---

## Dependencies

| Library   | Purpose                              | Install            |
|-----------|--------------------------------------|--------------------|
| ast       | Python AST parsing (built-in)        | (standard library) |
| networkx  | Graph construction and algorithms    | pip install networkx |
| lizard    | Multi-language cyclomatic complexity | pip install lizard |

---

## Input

| Source              | Data                    | Used For                         |
|---------------------|-------------------------|----------------------------------|
| hook_cwd            | Project root directory  | File discovery                   |
| session_id          | Current session ID      | Cache results in session dir     |
| enrichment_data     | From Step 3.0.0         | tech_stack for language detection |

---

## Processing Phases

### Phase 1: File Discovery
- Walk project directory recursively
- Filter files by detected tech_stack languages
- Skip directories: `.git`, `node_modules`, `__pycache__`, `.venv`, `venv`,
  `dist`, `build`, `.tox`, `.eggs`, `*.egg-info`, `.mypy_cache`
- Limit: Max 500 files (performance safety)
- Skip files larger than 100KB (likely generated/vendor code)

### Phase 2: Import/Dependency Extraction

**Python (via `ast` module - full AST parsing):**
- `import X` -> edge from current_file to X
- `from X import Y` -> edge from current_file to X
- Function calls: `X.method()` -> call edge
- Class inheritance: `class A(B)` -> inheritance edge

**Java (regex-based):**
- `import com.example.Class;` -> edge to Class
- `extends ClassName` -> inheritance edge
- `implements InterfaceName` -> interface edge

**JavaScript/TypeScript (regex-based):**
- `import X from 'module'` -> edge to module
- `const X = require('module')` -> edge to module
- `import { X } from 'module'` -> edge to module

**Go (regex-based):**
- `import "package"` -> edge to package
- `import ( "pkg1" "pkg2" )` -> edges to each

**Other languages:** Fall back to generic import regex patterns.

### Phase 3: Graph Construction
- Create `networkx.DiGraph()`
- Nodes = source files (relative paths)
- Edges = dependency relationships
  - Type: `import`, `call`, `inheritance`, `interface`
  - Weight: 1 (import), 2 (call), 3 (inheritance)

### Phase 4: Metrics Calculation

| Metric                  | NetworkX Function            | What It Measures              |
|-------------------------|------------------------------|-------------------------------|
| Degree Centrality       | `degree_centrality()`        | How connected each file is    |
| Betweenness Centrality  | `betweenness_centrality()`   | Bottleneck detection          |
| PageRank                | `pagerank()`                 | Importance of each file       |
| Graph Density           | `density()`                  | How interconnected overall    |
| Clustering Coefficient  | `average_clustering()`       | Module cohesion               |
| Connected Components    | `weakly_connected_components()` | Independent subgraphs      |
| Longest Path            | `dag_longest_path_length()`  | Deepest dependency chain      |
| Average Fan-Out         | Mean out-degree              | Average deps per file         |

### Phase 5: Cyclomatic Complexity (via Lizard)
- Run `lizard` on discovered source files
- Extract per-function cyclomatic complexity
- Calculate average and max cyclomatic complexity
- Supports: Python, Java, JavaScript, C/C++, Go, TypeScript, Rust

### Phase 6: Complexity Score Calculation

```
graph_score = 0 (accumulate 1-25)

Factor 1: Graph Size (0-5)
  >100 files: +5, >50: +4, >20: +3, >10: +2, >5: +1

Factor 2: Dependency Density (0-5)
  density = edges / max_possible_edges
  >0.20: +5, >0.15: +4, >0.10: +3, >0.05: +2, >0.02: +1

Factor 3: Max Betweenness Centrality (0-5)
  Highest bottleneck score in graph
  >0.5: +5, >0.3: +4, >0.2: +3, >0.1: +2, >0.05: +1

Factor 4: Average Fan-Out / Coupling (0-5)
  Mean outgoing edges per node
  >10: +5, >7: +4, >5: +3, >3: +2, >1: +1

Factor 5: Longest Dependency Chain (0-5)
  DAG longest path (falls back to 0 if cycles exist)
  >10: +5, >7: +4, >5: +3, >3: +2, >1: +1
```

### Combined Score Formula

```
FINAL_COMPLEXITY = round((keyword_complexity * 0.3) + (graph_complexity * 0.7))
FINAL_COMPLEXITY = clamp(FINAL_COMPLEXITY, 1, 25)
```

---

## Output

### Saved to Session
File: `~/.claude/memory/logs/sessions/{SESSION_ID}/graph-analysis.json`

```json
{
  "version": "1.0.0",
  "session_id": "SESSION-xxx",
  "analyzed_at": "2026-03-07T...",
  "project_dir": "/path/to/project",
  "tech_stack": ["Python", "Flask"],
  "files_analyzed": 87,
  "graph_metrics": {
    "total_nodes": 87,
    "total_edges": 234,
    "density": 0.031,
    "max_betweenness": 0.23,
    "max_pagerank": 0.045,
    "avg_fan_out": 2.69,
    "longest_path": 6,
    "connected_components": 3,
    "avg_clustering": 0.12,
    "avg_cyclomatic": 4.2,
    "max_cyclomatic": 18
  },
  "graph_complexity_score": 14,
  "top_bottleneck_files": [
    "src/app.py",
    "src/services/monitoring/metrics_collector.py"
  ]
}
```

### Passed to Next Step
```json
{
  "graph_complexity_score": 14,
  "graph_metrics_summary": "87 files, 234 deps, density=0.031, bottleneck=src/app.py",
  "top_bottleneck_files": ["src/app.py", "..."],
  "analysis_available": true
}
```

---

## Error Handling

| Scenario                  | Behavior                           |
|---------------------------|------------------------------------|
| No source files found     | Return score=1, skip graph build   |
| networkx not installed    | Return score=0, log warning        |
| lizard not installed      | Skip cyclomatic, use graph-only    |
| AST parse error           | Skip that file, continue           |
| Timeout (>10s)            | Return partial results             |
| Cyclic graph              | Skip longest_path, use other metrics |
| New project (0 files)     | Return score=1                     |

---

## Integration with Downstream Steps

| Step              | How It Uses Graph Complexity                    |
|-------------------|-------------------------------------------------|
| 3.0 Prompt Gen    | FINAL = (keyword*0.3) + (graph*0.7)            |
| 3.1 Task Breakdown| Phase count based on FINAL complexity           |
| 3.2 Plan Mode     | Plan required/recommended based on FINAL        |
| 3.4 Model Select  | HAIKU/SONNET/OPUS threshold based on FINAL      |

---

## Performance Budget

- **Target:** < 5 seconds for projects up to 500 files
- **File limit:** 500 files max (skip rest with warning)
- **File size limit:** 100KB per file (skip larger)
- **Timeout:** 10 seconds hard limit
- **Caching:** Results cached in session, reused within same session

---

## Version History

| Version | Date       | Changes                                    |
|---------|------------|--------------------------------------------|
| 1.0.0   | 2026-03-07 | Initial implementation with networkx+lizard |
