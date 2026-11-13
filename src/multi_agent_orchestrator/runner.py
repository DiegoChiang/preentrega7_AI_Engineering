"""Ejecucion y trazado legible de la delegacion."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

from multi_agent_orchestrator.config import Settings, get_settings
from multi_agent_orchestrator.graph import build_graph
from multi_agent_orchestrator.model import build_model


async def run_orchestrator(
    request: str,
    *,
    settings: Settings | None = None,
    model: Any | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Ejecuta el grafo y devuelve estado final junto con la secuencia de nodos."""

    if settings is None and model is None:
        settings = get_settings()
    active_model = model or build_model(settings)  # type: ignore[arg-type]
    max_steps = settings.supervisor_max_steps if settings else 8
    recursion_limit = settings.recursion_limit if settings else 30
    graph = build_graph(active_model, max_steps=max_steps)
    initial_state = {
        "messages": [HumanMessage(content=request)],
        "request": request,
        "next_agent": "researcher",
        "supervisor_instruction": "",
        "supervisor_reasoning": "",
        "supervisor_steps": 0,
        "research_findings": [],
        "analysis_result": None,
        "validation_feedback": [],
        "contributions": [],
        "completed_agents": [],
        "task_completed": False,
        "requires_approval": False,
        "approval_status": "not_required",
        "approval_request": None,
        "final_answer": "",
    }
    trace: list[dict[str, Any]] = []
    final_state: dict[str, Any] = initial_state
    async for mode, chunk in graph.astream(
        initial_state,
        config={"recursion_limit": recursion_limit},
        stream_mode=["updates", "values"],
    ):
        if mode == "values":
            final_state = chunk
        else:
            for node, values in chunk.items():
                trace.append(_trace_entry(node, values))
    return final_state, trace


def _trace_entry(node: str, values: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {"node": node}
    if node == "supervisor":
        entry.update(
            {
                "decision": values.get("next_agent"),
                "reasoning": values.get("supervisor_reasoning"),
                "instruction": values.get("supervisor_instruction"),
                "step": values.get("supervisor_steps"),
            }
        )
    elif node == "researcher":
        entry["sources"] = [
            item["source_id"] for item in values.get("research_findings", [])
        ]
    elif node == "analyst":
        entry["analysis"] = values.get("analysis_result")
    elif node == "validator":
        entry["task_completed"] = values.get("task_completed")
        entry["feedback"] = values.get("validation_feedback")
    elif node == "synthesizer":
        entry["final_answer"] = values.get("final_answer")
    return entry
