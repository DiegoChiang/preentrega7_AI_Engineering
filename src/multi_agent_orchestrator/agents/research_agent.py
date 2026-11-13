"""Especialista de investigacion documental."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from multi_agent_orchestrator.state import OrchestratorState, ResearchFinding
from multi_agent_orchestrator.tools import search_incident_knowledge


class ResearchNarrative(BaseModel):
    summary: str = Field(min_length=20)
    focus_areas: list[str] = Field(min_length=1, max_length=4)


class ResearchAgent:
    """Consulta solo la base documental y entrega evidencia estructurada."""

    tools = (search_incident_knowledge,)

    def __init__(self, model: Any) -> None:
        self._writer = model.with_structured_output(ResearchNarrative)

    async def __call__(self, state: OrchestratorState) -> dict[str, Any]:
        tool_output = await search_incident_knowledge.ainvoke(
            {"query": state["request"], "limit": 3}
        )
        findings: list[ResearchFinding] = json.loads(tool_output)
        try:
            narrative = await self._writer.ainvoke(
                [
                    SystemMessage(
                        content=(
                            "Eres especialista en investigacion operativa. Resume los hallazgos "
                            "sin inventar fuentes ni metricas. Identifica los focos que debe "
                            "revisar el analista."
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"Instruccion del supervisor: {state['supervisor_instruction']}\n"
                            f"Solicitud: {state['request']}\n"
                            "Evidencia de la herramienta: "
                            f"{json.dumps(findings, ensure_ascii=False)}"
                        )
                    ),
                ]
            )
        except ValidationError:
            narrative = ResearchNarrative(
                summary=(
                    f"Se recuperaron {len(findings)} fuentes documentales para analizar "
                    f"{state['request']}"
                ),
                focus_areas=list(
                    dict.fromkeys(tag for item in findings for tag in item["tags"])
                )[:4]
                or ["evidencia"],
            )
        source_ids = [item["source_id"] for item in findings]
        return {
            "research_findings": findings,
            "contributions": [
                {
                    "agent": "researcher",
                    "summary": narrative.summary,
                    "evidence_ids": source_ids,
                }
            ],
            "completed_agents": ["researcher"],
            "validation_feedback": [],
            "task_completed": False,
        }
