"""Router inteligente que controla el ciclo de delegacion."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from multi_agent_orchestrator.state import OrchestratorState, RouteTarget


class RouteDecision(BaseModel):
    next_agent: RouteTarget
    reasoning: str = Field(min_length=5)
    instruction: str = Field(min_length=5)


class Supervisor:
    """Decide el siguiente nodo usando salida estructurada y guardas de seguridad."""

    def __init__(self, model: Any, max_steps: int = 8) -> None:
        self._router = model.with_structured_output(RouteDecision)
        self._max_steps = max_steps

    async def __call__(self, state: OrchestratorState) -> dict[str, Any]:
        step = state.get("supervisor_steps", 0) + 1
        if step > self._max_steps:
            raise RuntimeError(
                f"El supervisor alcanzo el limite de {self._max_steps} decisiones sin completar."
            )

        status = {
            "research_sources": [
                item["source_id"] for item in state.get("research_findings", [])
            ],
            "analysis_result": state.get("analysis_result"),
            "validation_feedback": state.get("validation_feedback", []),
            "task_completed": state.get("task_completed", False),
            "requires_approval": state.get("requires_approval", False),
            "approval_status": state.get("approval_status", "not_required"),
            "completed_agents": state.get("completed_agents", []),
        }
        try:
            decision = await self._router.ainvoke(
                [
                    SystemMessage(
                        content=(
                            "Eres el supervisor de un grafo jerarquico. Elige exactamente un nodo. "
                            "Usa researcher cuando falte evidencia o la validacion pida nuevas "
                            "fuentes; analyst cuando exista evidencia pero falte un calculo "
                            "consistente; validator cuando haya investigacion y analisis; "
                            "approval cuando el resultado validado sea critico y siga pendiente; "
                            "synthesizer solo con validacion y aprobacion completas."
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"Solicitud:\n{state['request']}\n\nEstado resumido:\n"
                            f"{json.dumps(status, ensure_ascii=False)}"
                        )
                    ),
                ]
            )
        except ValidationError:
            fallback = self._enforce_prerequisites("synthesizer", state)
            decision = RouteDecision(
                next_agent=fallback,
                reasoning="La salida estructurada fue invalida; se aplicaron las guardas.",
                instruction=self._fallback_instruction(fallback, state),
            )
        target = self._enforce_prerequisites(decision.next_agent, state)
        instruction = decision.instruction
        reasoning = decision.reasoning
        if target != decision.next_agent:
            instruction = self._fallback_instruction(target, state)
            reasoning = (
                f"La ruta {decision.next_agent} no cumplia sus prerrequisitos; "
                f"se aplico la guarda hacia {target}."
            )
        return {
            "next_agent": target,
            "supervisor_instruction": instruction,
            "supervisor_reasoning": reasoning,
            "supervisor_steps": step,
        }

    @staticmethod
    def _enforce_prerequisites(
        target: RouteTarget, state: OrchestratorState
    ) -> RouteTarget:
        findings = state.get("research_findings", [])
        analysis = state.get("analysis_result")
        validated = state.get("task_completed", False)
        requires_approval = state.get("requires_approval", False)
        approval_status = state.get("approval_status", "not_required")
        feedback = state.get("validation_feedback", [])

        if not findings:
            return "researcher"
        if feedback and any("fuente" in item.casefold() for item in feedback):
            return "researcher"
        if analysis is None:
            return "analyst"
        if feedback:
            return "analyst"
        if not validated:
            return "validator"
        if requires_approval and approval_status == "pending":
            return "approval"
        if target != "synthesizer":
            return "synthesizer"
        return target

    @staticmethod
    def _fallback_instruction(target: RouteTarget, state: OrchestratorState) -> str:
        if target == "researcher":
            return "Busca evidencia operativa relevante y conserva los identificadores de fuente."
        if target == "analyst":
            feedback = "; ".join(state.get("validation_feedback", []))
            suffix = f" Corrige: {feedback}" if feedback else ""
            return f"Calcula la prioridad usando exclusivamente la evidencia disponible.{suffix}"
        if target == "validator":
            return "Comprueba cobertura, trazabilidad y consistencia antes de autorizar el cierre."
        if target == "approval":
            return "Solicita aprobacion humana antes de continuar con el resultado critico."
        return "Sintetiza una respuesta accionable con referencias a la evidencia validada."
