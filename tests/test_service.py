import asyncio
from typing import Any

import fakeredis.aioredis

from multi_agent_orchestrator.api.repository import RedisJobRepository
from multi_agent_orchestrator.api.schemas import JobStatus
from multi_agent_orchestrator.api.service import JobService


class FailingGraph:
    async def ainvoke(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("fallo controlado del modelo")


async def test_background_failure_is_persisted() -> None:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    repository = RedisJobRepository(client, ttl_seconds=300)
    service = JobService(
        graph=FailingGraph(),
        repository=repository,
        queue_size=5,
        worker_count=1,
    )
    await service.start()

    try:
        job = await service.submit("Ejecutar una tarea que falla")

        for _ in range(100):
            stored_job = await repository.get(job.job_id)
            if stored_job and stored_job.status is JobStatus.FAILED:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("El trabajo no llegó al estado FAILED")

        assert stored_job.error == "RuntimeError: fallo controlado del modelo"
        assert stored_job.completed_at is not None
    finally:
        await service.stop()
        await client.aclose()
