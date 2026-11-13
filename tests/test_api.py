import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import fakeredis.aioredis
from fastapi.testclient import TestClient

from multi_agent_orchestrator.api.app import create_app
from multi_agent_orchestrator.api.repository import RedisJobRepository
from multi_agent_orchestrator.api.runtime import Runtime
from multi_agent_orchestrator.api.service import JobService
from multi_agent_orchestrator.config import Settings


class InterruptingGraph:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, graph_input: Any, config: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.01)
        self.calls += 1
        if self.calls == 1:
            return {
                "__interrupt__": [
                    SimpleNamespace(
                        value={
                            "kind": "critical_result_approval",
                            "priority": "P1",
                            "risk_score": 81.3,
                        }
                    )
                ]
            }
        return {
            "final_answer": "Resultado aprobado.",
            "analysis_result": {"priority": "P1", "risk_score": 81.3},
            "approval_status": "approved",
            "completed_agents": ["researcher", "analyst", "validator", "approval"],
        }


def test_api_enqueues_persists_and_resumes_job() -> None:
    graph = InterruptingGraph()

    @asynccontextmanager
    async def fake_runtime(settings: Settings) -> AsyncIterator[Runtime]:
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        repository = RedisJobRepository(client, ttl_seconds=300)
        service = JobService(repository, graph, queue_size=5, worker_count=1)
        await service.start()
        try:
            yield Runtime(repository=repository, service=service)
        finally:
            await service.stop()
            await client.aclose()

    settings = Settings(
        openai_api_key="test-key",
        phoenix_enabled=False,
        worker_count=1,
        job_queue_size=5,
    )
    app = create_app(settings=settings, runtime_factory=fake_runtime)

    with TestClient(app) as client:
        accepted = client.post(
            "/jobs",
            json={"request": "Investiga un incidente critico de checkout."},
        )
        assert accepted.status_code == 202, accepted.text
        job_id = accepted.json()["job_id"]

        waiting = _wait_for_status(client, job_id, "WAITING_APPROVAL")
        assert waiting["approval_request"]["priority"] == "P1"

        approval = client.post(
            f"/jobs/{job_id}/approval",
            json={"approved": True, "feedback": "Aprobado por operaciones."},
        )
        assert approval.status_code == 202

        completed = _wait_for_status(client, job_id, "COMPLETED")
        assert completed["result"]["final_answer"] == "Resultado aprobado."
        assert completed["result"]["approval_status"] == "approved"


def _wait_for_status(client: TestClient, job_id: str, expected: str) -> dict[str, Any]:
    for _ in range(100):
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] == expected:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"El trabajo no alcanzo el estado {expected}.")
