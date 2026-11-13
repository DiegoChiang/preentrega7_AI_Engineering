"""Punto de control Human-in-the-loop para resultados criticos."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END
from langgraph.types import Command, interrupt

from multi_agent_orchestrator.state import OrchestratorState


def request_human_approval(state: OrchestratorState) -> Command[Any]:
    """Pausa el grafo y reanuda solo con una decision externa."""

    analysis = state.get("analysis_result")
    payload = {
        "kind": "critical_result_approval",
        "priority": analysis["priority"] if analysis else None,
        "risk_score": analysis["risk_score"] if analysis else None,
        "recommendation": analysis["recommendation"] if analysis else None,
        "message": "El resultado critico requiere aprobacion humana para continuar.",
    }
    decision: dict[str, Any] = interrupt(payload)
    if not decision.get("approved", False):
        feedback = str(decision.get("feedback", "Rechazado por el revisor humano."))
        return Command(
            update={
                "approval_status": "rejected",
                "approval_request": payload,
                "final_answer": f"Ejecucion detenida por decision humana: {feedback}",
                "completed_agents": ["approval"],
            },
            goto=END,
        )
    return Command(
        update={
            "approval_status": "approved",
            "approval_request": payload,
            "contributions": [
                {
                    "agent": "approval",
                    "summary": "El resultado critico fue aprobado por un revisor humano.",
                    "evidence_ids": [],
                }
            ],
            "completed_agents": ["approval"],
        },
        goto="supervisor",
    )
