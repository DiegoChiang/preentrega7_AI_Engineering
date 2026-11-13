"""Prueba de cinco peticiones concurrentes contra la API."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from time import perf_counter
from typing import Any

import httpx

from multi_agent_orchestrator.api.schemas import TERMINAL_STATUSES, JobStatus

QUERY = (
    "Investiga el aumento de errores en checkout, calcula su prioridad y propone acciones "
    "inmediatas basadas en evidencia."
)


async def submit_and_wait(client: httpx.AsyncClient, index: int) -> dict[str, Any]:
    started = perf_counter()
    response = await client.post("/jobs", json={"request": f"Caso {index}: {QUERY}"})
    response.raise_for_status()
    job_id = response.json()["job_id"]
    approved = False

    while True:
        status_response = await get_with_retry(client, f"/jobs/{job_id}")
        status_response.raise_for_status()
        job = status_response.json()
        status = JobStatus(job["status"])
        if status == JobStatus.WAITING_APPROVAL and not approved:
            approval = await client.post(
                f"/jobs/{job_id}/approval",
                json={"approved": True, "feedback": "Aprobado durante la prueba de carga."},
            )
            approval.raise_for_status()
            approved = True
        elif status in TERMINAL_STATUSES:
            return {
                "job_id": job_id,
                "status": status,
                "latency_seconds": round(perf_counter() - started, 3),
                "approval_used": approved,
            }
        await asyncio.sleep(1)


async def get_with_retry(
    client: httpx.AsyncClient, path: str, attempts: int = 5
) -> httpx.Response:
    """Tolera cierres transitorios del transporte durante el sondeo."""

    for attempt in range(attempts):
        try:
            return await client.get(path)
        except httpx.TransportError:
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(0.2 * (attempt + 1))
    raise RuntimeError("Numero de intentos de transporte agotado")


async def run_load_test(base_url: str) -> dict[str, Any]:
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=0)
    async with httpx.AsyncClient(base_url=base_url, timeout=180, limits=limits) as client:
        results = await asyncio.gather(
            *(submit_and_wait(client, index) for index in range(1, 6))
        )
    latencies = sorted(float(result["latency_seconds"]) for result in results)
    p95_index = max(0, math.ceil(0.95 * len(latencies)) - 1)
    return {
        "request_count": len(results),
        "concurrency": 5,
        "p95_latency_seconds": latencies[p95_index],
        "all_completed": all(
            result["status"] == JobStatus.COMPLETED for result in results
        ),
        "jobs": results,
        "phoenix_dashboard": "http://localhost:6006",
    }


async def _async_main(base_url: str) -> None:
    result = await run_load_test(base_url)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Cinco peticiones concurrentes con HITL")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    asyncio.run(_async_main(args.base_url))


if __name__ == "__main__":
    main()
