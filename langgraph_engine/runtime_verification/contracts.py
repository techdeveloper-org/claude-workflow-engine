from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Union


@dataclass(frozen=True)
class PreconditionSpec:
    key: str
    expected_type: Any  # type or tuple of types
    required: bool
    min_val: Optional[Union[int, float]] = None  # for str: min length; for numeric: min value
    max_val: Optional[Union[int, float]] = None  # for numeric: max value


@dataclass(frozen=True)
class PostconditionSpec:
    key: str
    non_null: bool
    min_length: int = 0


@dataclass(frozen=True)
class InvariantSpec:
    description: str
    check_fn: Callable[[dict], bool]


@dataclass
class Violation:
    node_name: str
    check_type: str  # "precondition" | "postcondition" | "invariant" | "transition"
    key: str
    message: str
    severity: str  # "INFO" | "WARNING" | "ERROR" | "CRITICAL"


@dataclass
class NodeContract:
    node_name: str
    preconditions: List[PreconditionSpec] = field(default_factory=list)
    postconditions: List[PostconditionSpec] = field(default_factory=list)
    invariants: List[InvariantSpec] = field(default_factory=list)
