"""Dobles de prueba para ejecutar el grafo sin red."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage


class ScriptedStructuredModel:
    def __init__(self, schema: type[Any]) -> None:
        self.schema = schema

    async def ainvoke(self, messages: list[Any]) -> Any:
        schema_name = self.schema.__name__
        if schema_name == "RouteDecision":
            status = messages[-1].content
            if '"research_sources": []' in status:
                target = "researcher"
            elif '"analysis_result": null' in status:
                target = "analyst"
            elif '"task_completed": false' in status:
                target = "validator"
            else:
                target = "synthesizer"
            return self.schema(
                next_agent=target,
                reasoning=f"El estado requiere {target}.",
                instruction=f"Ejecuta la responsabilidad de {target} con los datos disponibles.",
            )
        if schema_name == "ResearchNarrative":
            return self.schema(
                summary=(
                    "La evidencia vincula errores sostenidos, alta latencia y afectacion de "
                    "usuarios."
                ),
                focus_areas=["errores", "latencia", "usuarios afectados"],
            )
        if schema_name == "AnalysisNarrative":
            return self.schema(
                drivers=["Tasa de errores sostenida", "Latencia p95 elevada"],
                recommendation=(
                    "Escalar al equipo de pagos, limitar reintentos y vigilar la recuperacion."
                ),
            )
        raise AssertionError(f"Esquema no programado: {schema_name}")


class ScriptedModel:
    def with_structured_output(self, schema: type[Any]) -> ScriptedStructuredModel:
        return ScriptedStructuredModel(schema)

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        return AIMessage(
            content=(
                "Prioridad P1 (81.3/100). Escalar al equipo de pagos, limitar reintentos y "
                "monitorear la recuperacion [runbook-checkout-01] "
                "[telemetry-checkout-02] [postmortem-payments-03]."
            )
        )


class MalformedStructuredModel(ScriptedModel):
    def with_structured_output(self, schema: type[Any]) -> Any:
        class InvalidResponse:
            async def ainvoke(self, _messages: list[Any]) -> Any:
                return schema.model_validate({})

        return InvalidResponse()
