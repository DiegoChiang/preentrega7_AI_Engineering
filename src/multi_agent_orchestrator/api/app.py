"""Aplicacion FastAPI que expone trabajos asincronos."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status

from multi_agent_orchestrator.api.repository import JobNotFoundError
from multi_agent_orchestrator.api.runtime import Runtime, production_runtime
from multi_agent_orchestrator.api.schemas import (
    ApprovalDecision,
    HealthResponse,
    JobAccepted,
    JobCreate,
    JobRecord,
)
from multi_agent_orchestrator.api.service import InvalidJobStateError
from multi_agent_orchestrator.config import Settings, get_settings

RuntimeFactory = Callable[[Settings], AbstractAsyncContextManager[Runtime]]


def create_app(
    *,
    settings: Settings | None = None,
    runtime_factory: RuntimeFactory = production_runtime,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        active_settings = settings or get_settings()
        async with runtime_factory(active_settings) as runtime:
            application.state.runtime = runtime
            yield

    application = FastAPI(
        title="Production Multi-Agent API",
        version="0.7.0",
        description=(
            "API asincrona con trabajos persistidos en Redis, checkpoints de LangGraph, "
            "trazabilidad Phoenix y aprobacion humana para resultados criticos."
        ),
        lifespan=lifespan,
    )

    def get_runtime(request: Request) -> Runtime:
        return request.app.state.runtime

    @application.get("/health", response_model=HealthResponse, tags=["operacion"])
    async def health(request: Request) -> HealthResponse:
        runtime = get_runtime(request)
        redis_ok = await runtime.repository.ping()
        return HealthResponse(
            status="ok" if redis_ok else "degraded",
            redis="ok" if redis_ok else "unavailable",
            queue_depth=runtime.service.queue_depth,
        )

    @application.post(
        "/jobs",
        response_model=JobAccepted,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["jobs"],
    )
    async def create_job(
        payload: JobCreate,
        request: Request,
    ) -> JobAccepted:
        runtime = get_runtime(request)
        try:
            record = await runtime.service.submit(payload.request)
        except asyncio.QueueFull as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="La cola de trabajos esta llena.",
            ) from exc
        return JobAccepted(
            job_id=record.job_id,
            status=record.status,
            status_url=f"/jobs/{record.job_id}",
        )

    @application.get("/jobs/{job_id}", response_model=JobRecord, tags=["jobs"])
    async def get_job(
        job_id: str,
        request: Request,
    ) -> JobRecord:
        runtime = get_runtime(request)
        try:
            return await runtime.repository.get(job_id)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Trabajo no encontrado.") from exc

    @application.post(
        "/jobs/{job_id}/approval",
        response_model=JobAccepted,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["human-in-the-loop"],
    )
    async def approve_job(
        job_id: str,
        decision: ApprovalDecision,
        request: Request,
    ) -> JobAccepted:
        runtime = get_runtime(request)
        try:
            record = await runtime.service.approve(job_id, decision)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Trabajo no encontrado.") from exc
        except InvalidJobStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except asyncio.QueueFull as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="La cola de trabajos esta llena.",
            ) from exc
        return JobAccepted(
            job_id=record.job_id,
            status=record.status,
            status_url=f"/jobs/{record.job_id}",
        )

    return application


app = create_app()
