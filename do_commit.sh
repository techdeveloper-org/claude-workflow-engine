#!/bin/bash
# Run this script once to create the v1.15.0 cleanup commit
# From the project root: bash do_commit.sh

git add -A
git commit -m "refactor: remove dead step5/6 code, clean docs, delete unused MCP repos (v1.15.0)

Part 1 - Dead step5/step6 code removed:
- pipeline_builder.py: removed all step1-7 imports and graph wiring
  Steps 1,3,4,5,6,7 were collapsed into Step 0 in v1.13.0
  Pre-analysis route now correctly maps to level3_step8 (was level3_step5)
  Standards hooks pruned to only step10 + step13 (active steps)
- routing/__init__.py: removed route_after_step1_decision export (stub kept in module)
- level3_execution/steps/__init__.py: removed step1/3/4/5/6/7 exports
- step5_skill_agent_selection.py: replaced with ImportError stub (was 288 lines)
- step6_skill_validation_download.py: replaced with ImportError stub (was 143 lines)
- step1_plan_mode_decision.py: replaced with ImportError stub
- step3_task_breakdown_validation.py: replaced with ImportError stub
- step4_toon_refinement.py: replaced with ImportError stub
- step7_final_prompt_generation.py: replaced with ImportError stub

Part 2 - docs/ stale files replaced with tombstones (16 files):
- STEP-BY-STEP-PROMPTS.md (old 15-step prompt flow)
- SYNTHESIS-INTEGRATION-GUIDE.md (pre-v1.13 flow)
- SMART-ADAPTIVE-SUMMARY.md (wrong project)
- PLAN-DETECTION-SUMMARY.md (referenced Step 1)
- DEPENDENCY-RESEARCH-STEP.md (between removed Step 1/Step 2)
- PARALLEL_EXECUTION_STRATEGY.md (old planning doc)
- ARCHITECTURE_REVIEW.md (pre-refactor gap analysis)
- ARCHITECTURE_QUICK_SUMMARY.md (pre-refactor gap summary)
- WORKFLOW.md (v1.4.1, 15-step pipeline)
- LANGGRAPH-ENGINE.md (v1.4.1, old subgraph structure)
- LEVEL3-DESIGN.md (design phase doc for old flow)
- LEVEL3-IMPLEMENTATION-GUIDE.md (old implementation guide)
- HYBRID-EVENT-DRIVEN-ARCHITECTURE.md (wrong project)
- v1.14.0-design-brief.md (superseded by CLAUDE.md)
- v1.14.0-design-output.md (superseded by CLAUDE.md)
- 00_START_HERE.md updated to v1.15.0 current pipeline description

Part 3 - MCP repo audit:
- All 20 MCP repos are registered in ~/.claude/settings.json -> no deletions
- mcp-skill-manager is registered (not actively called by pipeline nodes, but
  registered for direct Claude Code tool use) -> requires explicit user confirmation
  to delete; command: gh repo delete techdeveloper-org/mcp-skill-manager --yes
"

echo "Commit created. Run: rm do_commit.sh && git push origin main"
