"""Especialista de analisis y computo."""

from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from multi_agent_orchestrator.state import AnalysisResult, OrchestratorState
from multi_agent_orchestrator.tools import calculate_incident_priority


class AnalysisNarrative(BaseModel):
    drivers: list[str] = Field(min_length=2, max_length=5)
    recommendation: str = Field(min_length=20)


class AnalysisAgent:
    """Calcula severidad con una formula reproducible y explica el resultado."""

    tools = (calculate_incident_priority,)

    def __init__(self, model: Any) -> None:
        self._writer = model.with_structured_output(AnalysisNarrative)

    async def __call__(self, state: OrchestratorState) -> dict[str, Any]:
        metrics = self._collect_metrics(state)
        tool_output = await calculate_incident_priority.ainvoke(metrics)
        calculation = json.loads(tool_output)
        narrative = await self._writer.ainvoke(
            [
                SystemMessage(
                    content=(
                        "Eres especialista en analisis de incidentes. Explica los factores del "
                        "puntaje y propone una accion concreta. Usa solo las metricas y fuentes "
                        "dadas."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Instruccion del supervisor: {state['supervisor_instruction']}\n"
                        f"Metricas: {json.dumps(metrics, ensure_ascii=False)}\n"
                        f"Calculo: {tool_output}\n"
                        f"Fuentes: {json.dumps(state['research_findings'], ensure_ascii=False)}"
                    )
                ),
            ]
        )
        result: AnalysisResult = {
            "priority": self._priority(calculation["priority"]),
            "risk_score": float(calculation["risk_score"]),
            "drivers": narrative.drivers,
            "recommendation": narrative.recommendation,
            "source_ids": [item["source_id"] for item in state["research_findings"]],
        }
        return {
            "analysis_result": result,
            "requires_approval": result["priority"] == "P1" or result["risk_score"] >= 75,
            "approval_status": (
                "pending"
                if result["priority"] == "P1" or result["risk_score"] >= 75
                else "not_required"
            ),
            "contributions": [
                {
                    "agent": "analyst",
                    "summary": (
                        f"Prioridad {result['priority']} con riesgo {result['risk_score']}/100. "
                        f"{result['recommendation']}"
                    ),
                    "evidence_ids": result["source_ids"],
                }
            ],
            "completed_agents": ["analyst"],
            "validation_feedback": [],
            "task_completed": False,
        }

    @staticmethod
    def _collect_metrics(state: OrchestratorState) -> dict[str, float | int]:
        combined: dict[str, float] = {}
        for finding in state["research_findings"]:
            combined.update(finding["metrics"])
        return {
            "error_rate_pct": combined.get("error_rate_pct", 0.0),
            "latency_p95_ms": combined.get("latency_p95_ms", 0.0),
            "affected_users": int(combined.get("affected_users", 0)),
            "duration_minutes": combined.get("duration_minutes", 0.0),
        }

    @staticmethod
    def _priority(value: str) -> Literal["P1", "P2", "P3", "P4"]:
        if value not in {"P1", "P2", "P3", "P4"}:
            raise ValueError(f"Prioridad inesperada: {value}")
        return value  # type: ignore[return-value]
