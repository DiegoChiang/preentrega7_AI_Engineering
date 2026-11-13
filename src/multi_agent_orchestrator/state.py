"""Estado compartido y contratos de datos del grafo."""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal, NotRequired, TypedDict

from langgraph.graph import MessagesState

AgentName = Literal["researcher", "analyst", "validator", "approval", "synthesizer"]
RouteTarget = Literal["researcher", "analyst", "validator", "approval", "synthesizer"]
ApprovalStatus = Literal["not_required", "pending", "approved", "rejected"]


class ResearchFinding(TypedDict):
    source_id: str
    title: str
    summary: str
    metrics: dict[str, float]
    tags: list[str]


class AnalysisResult(TypedDict):
    priority: Literal["P1", "P2", "P3", "P4"]
    risk_score: float
    drivers: list[str]
    recommendation: str
    source_ids: list[str]


class Contribution(TypedDict):
    agent: AgentName
    summary: str
    evidence_ids: list[str]


class OrchestratorState(MessagesState):
    """Memoria acotada que intercambian los nodos."""

    request: str
    next_agent: RouteTarget
    supervisor_instruction: str
    supervisor_reasoning: str
    supervisor_steps: int
    research_findings: list[ResearchFinding]
    analysis_result: AnalysisResult | None
    validation_feedback: list[str]
    contributions: Annotated[list[Contribution], add]
    completed_agents: Annotated[list[AgentName], add]
    task_completed: bool
    requires_approval: bool
    approval_status: ApprovalStatus
    approval_request: dict[str, object] | None
    final_answer: str
    last_error: NotRequired[str]
