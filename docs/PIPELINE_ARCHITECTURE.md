# Claude Workflow Engine — Pipeline Architecture

> Version 1.19.x · LangGraph 0.2.0+ · Python 3.10+

---

## 1. Top-Level Pipeline Flow

```mermaid
flowchart TD
    START(["User Task Input\npython scripts/3-level-flow.py --task ..."])

    subgraph LM1["Level -1 : Auto-Fix"]
        direction LR
        U["Unicode\nNormalize"]
        E["Encoding\nValidate\nUTF-8 / ASCII"]
        P["Path\nResolver\ncross-platform"]
        U --> E --> P
    end

    subgraph L1["Level 1 : Sync"]
        direction TB
        SS["Session\nSync"]
        subgraph PAR["Parallel Analysis"]
            direction LR
            CX["Simple\nComplexity\n1-10"]
            CTX["Context\nExtraction"]
        end
        MG["Merge and Score\ncombined_complexity_score\n1-25\nsimple x 0.3 + graph x 0.7"]
        SS --> PAR --> MG
    end

    subgraph L2["Level 2 : Standards NO-OP"]
        direction LR
        POL["policies/02-standards-system/\n.md files loaded from disk\nNo pipeline nodes"]
    end

    subgraph L3["Level 3 : Execution"]
        direction TB
        P0["Pre-0\nOrchestration\nPre-Analysis"]
        S0["Step 0\nTask Analysis v2\nPromptGen + Orchestrator\n~15s planning"]
        S8["Step 8\nGitHub + Jira\nIssue Creation"]
        S9["Step 9\nBranch Creation"]
        S10["Step 10\nImplementation\n+ Jira In Progress"]
        S11["Step 11\nPR + Code Review\n+ Jira In Review"]
        S12["Step 12\nIssue Closure\nGitHub + Jira Done"]
        S13["Step 13\nDocumentation\n+ UML Generation"]
        S14["Step 14\nFinal Summary"]
        P0 --> S0 --> S8 --> S9 --> S10 --> S11 --> S12 --> S13 --> S14
    end

    END(["Workflow Complete"])

    START --> LM1 --> L1 --> L2 --> L3 --> END

    style LM1 fill:#f3e8ff,stroke:#a855f7
    style L1  fill:#e0f2fe,stroke:#0284c7
    style L2  fill:#fef9c3,stroke:#ca8a04
    style L3  fill:#dcfce7,stroke:#16a34a
```

---

## 2. Level -1 : Auto-Fix Detail

```mermaid
flowchart LR
    IN(["Incoming\nFile / State"])

    subgraph C1["Check 1"]
        UC["Unicode\nNormalize\nnon-ASCII to ASCII\nequivalents"]
    end

    subgraph C2["Check 2"]
        EC["Encoding\nValidate\nUTF-8 / cp1252\nsafe guard"]
    end

    subgraph C3["Check 3"]
        PC["Path\nResolve\npath_resolver.py\nforward vs back slash"]
    end

    PASS{All 3\npassed?}
    FIX["Auto-fix\napplied\n+ state updated"]
    NEXT(["Level 1"])

    IN --> C1 --> C2 --> C3 --> PASS
    PASS -- yes --> NEXT
    PASS -- no  --> FIX --> NEXT

    style C1 fill:#f3e8ff,stroke:#a855f7
    style C2 fill:#f3e8ff,stroke:#a855f7
    style C3 fill:#f3e8ff,stroke:#a855f7
```

---

## 3. Level 1 : Sync Detail

```mermaid
flowchart TD
    IN(["State from\nLevel -1"])

    SS["Session Sync\nsession_id, metadata\nloaded from MCP session-mgr"]

    subgraph PAR["Parallel Workers"]
        direction LR
        CX["Simple Heuristic\nComplexity\ncomplexity_score\n1-10"]
        CTX["Context\nExtraction\ntask_description\nparsed + enriched"]
    end

    MG["Merge Node\nLinear-scale simple score to 1-25\ncombined_complexity_score\n= simple x 0.3 + graph x 0.7\nResult stored in state"]

    NEXT(["Level 2 NO-OP\nthen Level 3"])

    IN --> SS --> PAR --> MG --> NEXT

    style PAR fill:#e0f2fe,stroke:#0284c7
    style MG  fill:#bae6fd,stroke:#0284c7
```

---

## 4. Level 3 : Pre-0 + Step 0 Detail

```mermaid
flowchart TD
    IN(["combined_complexity_score\n+ session context\nenters Level 3"])

    subgraph P0["Pre-0 : Orchestration Pre-Analysis"]
        direction TB
        CG["CallGraph Scan\n578 classes · 3985 methods\nPython / Java / TS / Kotlin"]
        IA["analyze_impact_before_change\nrisk_level\ndanger_zones\naffected_methods\nhot_nodes\ncomplexity_boost"]
        TFP{Template\nFast-Path\ndetected?}
        FP["Skip Step 0\nJump to Step 8"]
        NP["Normal Path\nInject call-graph data into state"]
        CG --> IA --> TFP
        TFP -- yes --> FP
        TFP -- no  --> NP
    end

    subgraph S0["Step 0 : Task Analysis v2  ~15s"]
        direction TB
        C1["Call 1 : PromptGen Expert ~10s\nprompt_gen_expert_caller.py\nReads: orchestration_system_prompt.txt\nInjects: user_requirements\nruntime_context_json_block\ncomplexity_score_display\ncodebase_risk_level\ncodebase_danger_zones\ncodebase_hot_nodes\nOutputs: state orchestration_prompt"]
        C2["Call 2 : Orchestrator Agent ~30-90s\norchestrator_agent_caller.py\nReads: orchestration_prompt via temp file\nExecutes: solution-architect\nconsensus, squad agents, QA\nStreams live to terminal\nOutputs: state orchestrator_result"]
        C1 --> C2
    end

    NP  --> S0
    FP  --> STEP8
    S0  --> STEP8(["Step 8"])

    style P0  fill:#f0fdf4,stroke:#16a34a
    style S0  fill:#dcfce7,stroke:#16a34a
    style TFP fill:#fef9c3,stroke:#ca8a04
```

---

## 5. Level 3 : Steps 8-14 Execution Flow

```mermaid
flowchart TD
    IN(["orchestrator_result\nfrom Step 0"])

    S8["Step 8 : Issue Creation\nGitHub Issue created\nJira Issue created if ENABLE_JIRA\nCross-linked dual-tracked\nLabel + assignee applied"]

    S9["Step 9 : Branch Creation\nBranch from Jira key\nfeature/PROJ-123\nor from GitHub issue slug\nPushed to remote"]

    S10["Step 10 : Implementation\nCallGraph snapshot pre-change\ncall_graph_stale = True after writes\nJira → In Progress\nFigma → Implementation started\nSonarQube scan if ENABLE_SONARQUBE\nJenkins trigger if ENABLE_JENKINS"]

    S11["Step 11 : PR + Code Review\nPR opened on GitHub\nCallGraph diff: before vs after\nbreaking changes detected\norphaned methods flagged\nJira → In Review, PR linked\nFigma design fidelity checklist\nJenkins build validate\nQuality Gate: 4-gate merge check"]

    S12["Step 12 : Issue Closure\nGitHub Issue closed\nPR merged post-merge cleanup\nJira → Done\nFigma → Implementation complete"]

    S13["Step 13 : Documentation + UML\nCHANGELOG.md finalized\nVERSION bumped\nREADME.md updated\n13 UML diagrams regenerated\n13 draw.io diagrams regenerated"]

    S14["Step 14 : Final Summary\nSession metrics aggregated\nCLAUDE.md Latest Execution Insight updated\nAudit log entry written\nPrometheus metrics flushed"]

    END(["Workflow Complete"])

    IN --> S8 --> S9 --> S10 --> S11 --> S12 --> S13 --> S14 --> END

    style S8  fill:#eff6ff,stroke:#2563eb
    style S9  fill:#eff6ff,stroke:#2563eb
    style S10 fill:#fef3c7,stroke:#d97706
    style S11 fill:#fef3c7,stroke:#d97706
    style S12 fill:#f0fdf4,stroke:#16a34a
    style S13 fill:#f0fdf4,stroke:#16a34a
    style S14 fill:#f0fdf4,stroke:#16a34a
```

---

## 6. CallGraph Intelligence Flow

```mermaid
flowchart LR
    subgraph CGB["call_graph_builder.py : AST Parser"]
        direction TB
        PY["Python\nAST full"]
        JV["Java\nRegex"]
        TS["TypeScript\nRegex"]
        KT["Kotlin\nRegex"]
    end

    CGA["call_graph_analyzer.py\n578 classes\n3985 methods\nFQN call stack"]

    subgraph P0B["Pre-0"]
        IP["analyze_impact_before_change\nrisk_level · danger_zones\naffected_methods · hot_nodes"]
    end

    subgraph S10B["Step 10"]
        SN["snapshot_call_graph\npre-change state\nget_implementation_context\ncaller/callee awareness"]
        SF["call_graph_stale = True\nafter file writes"]
        SN --> SF
    end

    subgraph S11B["Step 11"]
        RC["review_change_impact\nbefore vs after diff\nbreaking changes\norphaned methods\nrisk delta"]
    end

    subgraph GUARD["Stale Graph Guard v1.6.1"]
        direction TB
        GC{stale\nflag?}
        RB["refresh_call_graph_if_stale\nsilent rebuild"]
        FB["Fallback priority\n1. fresh scan if stale\n2. step10_pre_change_graph\n3. step2_impact_analysis\n4. pre_analysis_result\n5. fresh scan"]
        GC -- yes --> RB --> FB
        GC -- no  --> FB
    end

    CGB --> CGA
    CGA --> P0B
    CGA --> S10B
    S10B --> GUARD
    GUARD --> S11B

    style CGB   fill:#f5f3ff,stroke:#7c3aed
    style CGA   fill:#ede9fe,stroke:#7c3aed
    style GUARD fill:#fef9c3,stroke:#ca8a04
```

---

## 7. Integration Lifecycles

```mermaid
flowchart LR
    subgraph JL["Jira Lifecycle  ENABLE_JIRA=1"]
        direction TB
        J8["Step 8\nCREATE\nJira issue + GitHub link"]
        J9["Step 9\nBRANCH\nfeature/PROJ-123"]
        J10["Step 10\nUPDATE\nIn Progress"]
        J11["Step 11\nLINK\nPR linked\nIn Review"]
        J12["Step 12\nCLOSE\nDone"]
        J8 --> J9 --> J10 --> J11 --> J12
    end

    subgraph FL["Figma Lifecycle  ENABLE_FIGMA=1"]
        direction TB
        F0["Step 0\nEXTRACT + INJECT\nComponents + design tokens\ninto orchestration template"]
        F10["Step 10\nCOMMENT\nImplementation started\n+ component list"]
        F11["Step 11\nREVIEW\nDesign fidelity checklist"]
        F12["Step 12\nCOMMENT\nImplementation complete\n+ PR link"]
        F0 --> F10 --> F11 --> F12
    end

    style JL fill:#eff6ff,stroke:#2563eb
    style FL fill:#fdf4ff,stroke:#a855f7
```

---

## 8. Execution Modes

```mermaid
flowchart TD
    ENV{CLAUDE_HOOK_MODE}

    subgraph HM["Hook Mode  default = 1"]
        direction TB
        H1["Pre-0 : Orchestration Pre-Analysis"]
        H2["Step 0 : PromptGen + Orchestrator"]
        H3["Step 8 : GitHub Issue Creation"]
        H4["Step 9 : Branch Creation"]
        HSKIP["Steps 10-14\nSKIPPED\nUser implements manually\nthen runs Full Mode for PR/closure"]
        H1 --> H2 --> H3 --> H4 --> HSKIP
    end

    subgraph FM["Full Mode  = 0"]
        direction TB
        F1["Pre-0 : Orchestration Pre-Analysis"]
        F2["Step 0 : PromptGen + Orchestrator"]
        F3["Steps 8-9 : Issue + Branch"]
        F4["Step 10 : Implementation"]
        F5["Step 11 : PR + Code Review"]
        F6["Steps 12-14 : Close + Docs + Summary"]
        F1 --> F2 --> F3 --> F4 --> F5 --> F6
    end

    ENV -- "1 default" --> HM
    ENV -- "0"          --> FM

    style HM fill:#fef9c3,stroke:#ca8a04
    style FM fill:#dcfce7,stroke:#16a34a
```

---

## 9. MCP Server Architecture  13 servers · 295 tools

```mermaid
graph TD
    CWE["Claude Workflow Engine\nPipeline Core"]

    subgraph INFRA["Infrastructure Layer"]
        SM["session-mgr\n14 tools\nSession lifecycle"]
        GO["git-ops\n14 tools\nBranch / commit / push / pull"]
        GA["github-api\n12 tools\nPR / issue / merge"]
        PE["policy-enforcement\n11 tools\nCompliance + health"]
    end

    subgraph INTEL["Intelligence Layer"]
        TO["token-optimizer\n10 tools\n60-85% token reduction"]
        PTG["pre-tool-gate\n13 tools\n8 policy checks"]
        PTT["post-tool-tracker\n6 tools\nProgress + readiness"]
        SL["standards-loader\n7 tools\nProject detect + hot-reload"]
    end

    subgraph DIAG["Diagram Layer"]
        UML["uml-diagram\n15 tools\n13 UML types"]
        DIO["drawio-diagram\n5 tools\n12 draw.io types"]
    end

    subgraph THIRD["Third-Party Layer"]
        JR["jira-api\n10 tools\nCloud v3 + Server v2"]
        JK["jenkins-ci\n10 tools\nCI/CD trigger + poll"]
        FG["figma-api\n10 tools\nComponents + tokens"]
        AN["anthropic\n4 tools\nClaude API direct"]
    end

    CWE --> INFRA
    CWE --> INTEL
    CWE --> DIAG
    CWE --> THIRD

    style INFRA fill:#e0f2fe,stroke:#0284c7
    style INTEL fill:#f0fdf4,stroke:#16a34a
    style DIAG  fill:#fdf4ff,stroke:#a855f7
    style THIRD fill:#fef9c3,stroke:#ca8a04
```

---

## 10. Version History — Planning Evolution

```mermaid
timeline
    title Planning Phase Evolution
    v1.12.0 : 15 active steps : ~6 LLM calls : ~75s planning : Steps 0-7 each called LLM separately
    v1.13.0 : 9 active steps  : ~2 subprocess calls : ~30s planning : Steps 1,3,4,5,6,7 removed
    v1.14.0 : 8 active steps  : 2 subprocess calls : ~15s planning : Step 0 = template fill + orchestrator
    v1.15.0 : 8 active steps  : 2 subprocess calls : ~15s : TOON compression removed from Level 1
    v1.16.0 : 8 active steps  : 2 subprocess calls : ~15s : Level 2 script purge, policies on disk only
    v1.19.x : 8 active steps  : 2 subprocess calls : ~15s : Current stable release
```

---

*Rendered by GitHub / VS Code Markdown preview with Mermaid support*
