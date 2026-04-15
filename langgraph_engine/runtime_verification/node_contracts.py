"""NodeContract definitions for 3 core Level 3 LangGraph nodes.

Contracts declare which FlowState keys each node requires as preconditions
and guarantees as postconditions. The verifier (RuntimeVerifier) evaluates
these at node entry/exit when ENABLE_RUNTIME_VERIFICATION=1.

Key names are sourced directly from the node implementations:
  - orchestration_pre_analysis_node -> orchestration.py
  - step0_task_analysis_node (prompt_gen + orchestrator) -> step_wrappers_0to4.py
  - FlowState field names -> state/state_definition.py

Windows-safe: ASCII only.
"""

from __future__ import annotations

from langgraph_engine.runtime_verification.contracts import NodeContract, PostconditionSpec, PreconditionSpec

# ---------------------------------------------------------------------------
# orchestration_pre_analysis_node
#
# Reads:  user_message (primary task input), project_root (callgraph scan)
# Writes: pre_analysis_result, call_graph_metrics, template_fast_path
# Fail-open: any exception returns empty metrics -- never blocks pipeline
# ---------------------------------------------------------------------------
PRE_ANALYSIS_CONTRACT = NodeContract(
    node_name="orchestration_pre_analysis_node",
    preconditions=[
        PreconditionSpec(key="user_message", expected_type=str, required=True, min_val=1),
        PreconditionSpec(key="project_root", expected_type=str, required=False),
    ],
    postconditions=[
        PostconditionSpec(key="pre_analysis_result", non_null=True, min_length=0),
        PostconditionSpec(key="call_graph_metrics", non_null=True, min_length=0),
    ],
)

# ---------------------------------------------------------------------------
# prompt_gen_expert_caller (Step 0 Phase 1)
#
# Reads:  user_message (task input), combined_complexity_score (Level 1 1-25),
#         call_graph_metrics (from pre_analysis, optional)
# Writes: orchestration_prompt (min 200 chars for a useful prompt)
# ---------------------------------------------------------------------------
PROMPT_GEN_CONTRACT = NodeContract(
    node_name="prompt_gen_expert_caller",
    preconditions=[
        PreconditionSpec(key="user_message", expected_type=str, required=True, min_val=1),
        PreconditionSpec(key="combined_complexity_score", expected_type=int, required=False),
        PreconditionSpec(key="call_graph_metrics", expected_type=dict, required=False),
    ],
    postconditions=[
        PostconditionSpec(key="orchestration_prompt", non_null=True, min_length=200),
    ],
)

# ---------------------------------------------------------------------------
# orchestrator_agent_caller (Step 0 Phase 2)
#
# Reads:  orchestration_prompt (produced by prompt_gen phase, min 200 chars)
# Writes: orchestrator_result (dict with task breakdown + agent plan)
# ---------------------------------------------------------------------------
ORCHESTRATOR_CONTRACT = NodeContract(
    node_name="orchestrator_agent_caller",
    preconditions=[
        PreconditionSpec(key="orchestration_prompt", expected_type=str, required=True, min_val=200),
    ],
    postconditions=[
        PostconditionSpec(key="orchestrator_result", non_null=True, min_length=0),
    ],
)

# ---------------------------------------------------------------------------
# Registry -- maps node_name -> NodeContract for verifier lookup
# ---------------------------------------------------------------------------
NODE_CONTRACT_REGISTRY = {
    PRE_ANALYSIS_CONTRACT.node_name: PRE_ANALYSIS_CONTRACT,
    PROMPT_GEN_CONTRACT.node_name: PROMPT_GEN_CONTRACT,
    ORCHESTRATOR_CONTRACT.node_name: ORCHESTRATOR_CONTRACT,
}
