"""
LangGraph subgraphs - Backward compatibility bridge.

Canonical code has moved to level-based packages:
- level_minus1/  -> Level -1 Auto-Fix (fully migrated)
- level1_sync/   -> Level 1 Sync (fully migrated)
- level2_standards/ -> Level 2 Standards (fully migrated)
- level3_execution/ -> Level 3 Execution (bridge packages created)

This directory contains:
- level_minus1.py: shim -> langgraph_engine.level_minus1
- level1_sync/:    shim -> langgraph_engine.level1_sync
- level2_standards.py: shim -> langgraph_engine.level2_standards
- level3_execution/:   v1 steps (DEPRECATED, re-exported via level3_execution/steps/)
- level3_v2_nodes/:    v2 wrappers (re-exported via level3_execution/v2_nodes/)
- level3_execution_v2.py: v2 builder (re-exported via level3_execution/execution_v2.py)
"""
