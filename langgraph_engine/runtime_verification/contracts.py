"""Runtime-verification contract specifications.

Frozen/plain dataclasses describing the preconditions, postconditions, invariants,
and per-node contract that RuntimeVerifier checks against the pipeline state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Union


@dataclass(frozen=True)
class PreconditionSpec:
    """A precondition on a single state key, checked before a node executes.

    Verifies presence (when ``required``), type, and optional bounds. ``min_val``/
    ``max_val`` are numeric bounds for numbers and length bounds for str/list/dict.
    """

    key: str
    expected_type: Any  # type or tuple of types
    required: bool
    min_val: Optional[Union[int, float]] = None  # for str: min length; for numeric: min value
    max_val: Optional[Union[int, float]] = None  # for numeric: max value


@dataclass(frozen=True)
class PostconditionSpec:
    """A postcondition on a single state key, checked after a node executes.

    ``non_null`` asserts the key is present and not None; ``min_length`` asserts a
    minimum ``len()`` for str/list/dict values.
    """

    key: str
    non_null: bool
    min_length: int = 0


@dataclass(frozen=True)
class InvariantSpec:
    """A named boolean invariant over the whole state dict (``check_fn(state) -> bool``)."""

    description: str
    check_fn: Callable[[dict], bool]


@dataclass
class Violation:
    """One recorded contract violation: node, check type, offending key, message, severity."""

    node_name: str
    check_type: str  # "precondition" | "postcondition" | "invariant" | "transition"
    key: str
    message: str
    severity: str  # "INFO" | "WARNING" | "ERROR" | "CRITICAL"


@dataclass
class NodeContract:
    """The full set of preconditions, postconditions, and invariants for one node."""

    node_name: str
    preconditions: List[PreconditionSpec] = field(default_factory=list)
    postconditions: List[PostconditionSpec] = field(default_factory=list)
    invariants: List[InvariantSpec] = field(default_factory=list)
