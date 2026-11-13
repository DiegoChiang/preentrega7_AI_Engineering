"""Instrumentacion OpenTelemetry para Arize Phoenix."""

from __future__ import annotations

from opentelemetry import trace

from multi_agent_orchestrator.config import Settings

_configured = False


def configure_observability(settings: Settings) -> None:
    """Registra Phoenix y la autoinstrumentacion OpenInference una sola vez."""

    global _configured
    if _configured or not settings.phoenix_enabled:
        return

    from phoenix.otel import register

    register(
        endpoint=settings.phoenix_collector_endpoint,
        project_name=settings.phoenix_project_name,
        protocol="http/protobuf",
        auto_instrument=True,
        batch=True,
    )
    _configured = True


def get_tracer():
    return trace.get_tracer("multi_agent_orchestrator.jobs")
