"""
runtime_verification -- non-invasive contract checking layer for LangGraph pipeline nodes.

Activate with: ENABLE_RUNTIME_VERIFICATION=1
Strict mode:   STRICT_RUNTIME_VERIFICATION=1
Zero overhead when disabled -- NullVerifier no-op path, original function returned unchanged.
"""

from langgraph_engine.runtime_verification.contracts import (
    InvariantSpec,
    NodeContract,
    PostconditionSpec,
    PreconditionSpec,
    Violation,
)
from langgraph_engine.runtime_verification.decorators import verify_node
from langgraph_engine.runtime_verification.invariants import LEVEL_TRANSITION_GUARDS, get_transition_guard
from langgraph_engine.runtime_verification.report import VerificationReport
from langgraph_engine.runtime_verification.schema_verifier import (
    verify_orchestration_prompt,
    verify_orchestrator_result,
)
from langgraph_engine.runtime_verification.verifier import NullVerifier, RuntimeVerifier

__all__ = [
    # Contracts
    "NodeContract",
    "PreconditionSpec",
    "PostconditionSpec",
    "InvariantSpec",
    "Violation",
    # Verifier
    "RuntimeVerifier",
    "NullVerifier",
    # Decorator
    "verify_node",
    # Report
    "VerificationReport",
    # Invariants / guards
    "LEVEL_TRANSITION_GUARDS",
    "get_transition_guard",
    # Schema validators
    "verify_orchestration_prompt",
    "verify_orchestrator_result",
]
