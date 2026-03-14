"""
TOON Object Models - Type-safe project understanding structures.

TOON = Tokenized Object-Oriented Notation
Lightweight schema-validated state objects for Level 3 execution.
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
import orjson


class ContextData(BaseModel):
    """Project context files (SRS, README, CLAUDE.md)."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    files: List[str] = Field(default_factory=list)
    srs: bool = False
    readme: bool = False
    claude_md: bool = False


class ToonAnalysis(BaseModel):
    """Level 1 Analysis TOON - Full project understanding."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str
    timestamp: datetime
    complexity_score: int = Field(ge=0, le=10)
    files_loaded_count: int
    context: ContextData
    project_type: Optional[str] = None


class RiskAssessment(BaseModel):
    """Risk analysis for the task."""

    risk_level: str = Field(pattern="^(low|medium|high)$")
    factors: List[str] = Field(default_factory=list)
    mitigation: List[str] = Field(default_factory=list)


class ExecutionPhase(BaseModel):
    """Single phase in the execution plan."""

    phase_number: int
    title: str
    description: str
    tasks: List[str]
    files_affected: List[str]
    dependencies: List[int] = Field(default_factory=list)
    estimated_complexity: int = Field(ge=0, le=10)


class ExecutionBlueprint(BaseModel):
    """Level 3 Refined TOON - Execution blueprint after planning.

    Enhanced with richer metadata for better planning and execution insights.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str
    timestamp: datetime
    complexity_score: int = Field(ge=0, le=10)
    plan: str
    files_affected: List[str]
    phases: List[ExecutionPhase]
    risks: RiskAssessment
    selected_skills: List[str] = Field(default_factory=list)
    selected_agents: List[str] = Field(default_factory=list)
    execution_strategy: str = "sequential"

    # Richer metadata fields
    project_type: Optional[str] = Field(
        default=None,
        description="Detected project type: Java, Python, Node, Go, Rust, etc."
    )
    detected_frameworks: List[str] = Field(
        default_factory=list,
        description="List of detected frameworks: Spring, Flask, React, Django, etc."
    )
    effort_estimate: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Effort estimate (1=minimal, 10=very high) based on scope and complexity"
    )


class SkillMapping(BaseModel):
    """Task to skill mapping."""

    task_id: str
    task_name: str
    required_skills: List[str]
    required_agents: List[str]
    skill_confidence: Dict[str, float] = Field(default_factory=dict)


class ToonWithSkills(ExecutionBlueprint):
    """TOON with skill mappings (after Step 5)."""

    skill_mappings: List[SkillMapping] = Field(default_factory=list)
    final_skills_selected: List[str] = Field(default_factory=list)
    final_agents_selected: List[str] = Field(default_factory=list)


class ExecutionLog(BaseModel):
    """Single execution log entry."""

    timestamp: datetime
    step: int
    step_name: str
    status: str = Field(pattern="^(running|success|failed|skipped)$")
    message: str
    duration_ms: Optional[float] = None
    error: Optional[str] = None


class SessionMetadata(BaseModel):
    """Session metadata for tracking."""

    session_id: str
    created_at: datetime
    user_message: str
    status: str = Field(default="active", pattern="^(active|completed|failed)$")
    execution_logs: List[ExecutionLog] = Field(default_factory=list)
    github_issue_id: Optional[int] = None
    github_pr_id: Optional[int] = None
    branch_name: Optional[str] = None


# Utility functions for TOON serialization

def serialize_toon(toon: BaseModel) -> str:
    """Serialize TOON to JSON string using orjson (fast)."""
    return orjson.dumps(toon.model_dump(mode='json')).decode('utf-8')


def deserialize_toon(json_str: str, model: type) -> BaseModel:
    """Deserialize JSON string to TOON model."""
    data = orjson.loads(json_str)
    return model(**data)
