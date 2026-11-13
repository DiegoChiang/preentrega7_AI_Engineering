"""Construccion del grafo jerarquico."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from multi_agent_orchestrator.agents import AnalysisAgent, ResearchAgent
from multi_agent_orchestrator.approval import request_human_approval
from multi_agent_orchestrator.state import OrchestratorState, RouteTarget
from multi_agent_orchestrator.supervisor import Supervisor
from multi_agent_orchestrator.synthesis import Synthesizer
from multi_agent_orchestrator.validation import validate_result


def route_supervisor(state: OrchestratorState) -> RouteTarget:
    return state["next_agent"]


def build_graph(
    model: Any,
    *,
    max_steps: int = 8,
    checkpointer: Any | None = None,
) -> CompiledStateGraph:
    """Crea un supervisor central con especialistas de contexto aislado."""

    builder = StateGraph(OrchestratorState)
    builder.add_node("supervisor", Supervisor(model, max_steps=max_steps))
    builder.add_node("researcher", ResearchAgent(model))
    builder.add_node("analyst", AnalysisAgent(model))
    builder.add_node("validator", validate_result)
    builder.add_node("approval", request_human_approval)
    builder.add_node("synthesizer", Synthesizer(model))

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "researcher": "researcher",
            "analyst": "analyst",
            "validator": "validator",
            "approval": "approval",
            "synthesizer": "synthesizer",
        },
    )
    builder.add_edge("researcher", "supervisor")
    builder.add_edge("analyst", "supervisor")
    builder.add_edge("validator", "supervisor")
    builder.add_edge("synthesizer", END)
    return builder.compile(checkpointer=checkpointer)
