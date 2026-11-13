"""Ciclo de vida de Redis, checkpointer y workers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from redis.asyncio import Redis

from multi_agent_orchestrator.api.repository import RedisJobRepository
from multi_agent_orchestrator.api.service import JobService
from multi_agent_orchestrator.config import Settings
from multi_agent_orchestrator.graph import build_graph
from multi_agent_orchestrator.model import build_model
from multi_agent_orchestrator.observability import configure_observability


@dataclass(slots=True)
class Runtime:
    repository: RedisJobRepository
    service: JobService


@asynccontextmanager
async def production_runtime(settings: Settings) -> AsyncIterator[Runtime]:
    configure_observability(settings)
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis_client.ping()

    async with AsyncRedisSaver.from_conn_string(settings.redis_url) as checkpointer:
        await checkpointer.asetup()
        graph = build_graph(
            build_model(settings),
            max_steps=settings.supervisor_max_steps,
            checkpointer=checkpointer,
        )
        repository = RedisJobRepository(
            redis_client,
            ttl_seconds=settings.job_ttl_seconds,
        )
        service = JobService(
            repository,
            graph,
            queue_size=settings.job_queue_size,
            worker_count=settings.worker_count,
            recursion_limit=settings.recursion_limit,
        )
        await service.start()
        try:
            yield Runtime(repository=repository, service=service)
        finally:
            await service.stop()
            await redis_client.aclose()
