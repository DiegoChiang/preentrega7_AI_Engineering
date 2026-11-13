"""Cola y workers asincronos para ejecutar el grafo fuera del endpoint."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from multi_agent_orchestrator.api.repository import RedisJobRepository
from multi_agent_orchestrator.api.schemas import ApprovalDecision, JobRecord, JobStatus
from multi_agent_orchestrator.observability import get_tracer


@dataclass(frozen=True, slots=True)
class WorkItem:
    job_id: str
    resume: dict[str, Any] | None = None


class InvalidJobStateError(RuntimeError):
    pass


class JobService:
    def __init__(
        self,
        repository: RedisJobRepository,
        graph: Any,
        *,
        queue_size: int = 100,
        worker_count: int = 2,
        recursion_limit: int = 30,
    ) -> None:
        self.repository = repository
        self._graph = graph
        self._queue: asyncio.Queue[WorkItem | None] = asyncio.Queue(maxsize=queue_size)
        self._worker_count = worker_count
        self._recursion_limit = recursion_limit
        self._workers: list[asyncio.Task[None]] = []

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    async def start(self) -> None:
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"agent-worker-{index}")
            for index in range(self._worker_count)
        ]

    async def stop(self) -> None:
        for _ in self._workers:
            await self._queue.put(None)
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def submit(self, request: str) -> JobRecord:
        job_id = str(uuid4())
        record = await self.repository.create(job_id, request)
        try:
            self._queue.put_nowait(WorkItem(job_id=job_id))
        except asyncio.QueueFull:
            await self.repository.update(
                job_id,
                status=JobStatus.FAILED,
                error="La cola de trabajos alcanzo su capacidad.",
                completed_at=datetime.now(UTC),
            )
            raise
        return record

    async def approve(self, job_id: str, decision: ApprovalDecision) -> JobRecord:
        record = await self.repository.get(job_id)
        if record.status != JobStatus.WAITING_APPROVAL:
            raise InvalidJobStateError(
                f"El trabajo {job_id} esta en {record.status}, no espera aprobacion."
            )
        await self.repository.update(job_id, status=JobStatus.QUEUED, error=None)
        try:
            self._queue.put_nowait(
                WorkItem(job_id=job_id, resume=decision.model_dump(mode="json"))
            )
        except asyncio.QueueFull:
            await self.repository.update(
                job_id,
                status=JobStatus.FAILED,
                error="La cola de trabajos alcanzo su capacidad al reanudar.",
                completed_at=datetime.now(UTC),
            )
            raise
        return await self.repository.get(job_id)

    async def _worker(self, worker_index: int) -> None:
        while True:
            item = await self._queue.get()
            try:
                if item is None:
                    return
                await self._execute(item, worker_index)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if item is not None:
                    await self.repository.update(
                        item.job_id,
                        status=JobStatus.FAILED,
                        error=f"{type(exc).__name__}: {exc}",
                        completed_at=datetime.now(UTC),
                    )
            finally:
                self._queue.task_done()

    async def _execute(self, item: WorkItem, worker_index: int) -> None:
        record = await self.repository.update(
            item.job_id,
            status=JobStatus.RUNNING,
            started_at=datetime.now(UTC),
            error=None,
        )
        config = {
            "configurable": {"thread_id": item.job_id},
            "recursion_limit": self._recursion_limit,
        }
        graph_input: Any
        if item.resume is None:
            graph_input = initial_state(record.request)
        else:
            graph_input = Command(resume=item.resume)

        tracer = get_tracer()
        with tracer.start_as_current_span("agent_job.execute") as span:
            span.set_attribute("job.id", item.job_id)
            span.set_attribute("worker.index", worker_index)
            span.set_attribute("job.resumed", item.resume is not None)
            result = await self._graph.ainvoke(graph_input, config=config)

        interrupts = result.get("__interrupt__", ())
        if interrupts:
            interrupt_value = getattr(interrupts[0], "value", interrupts[0])
            await self.repository.update(
                item.job_id,
                status=JobStatus.WAITING_APPROVAL,
                approval_request=interrupt_value,
            )
            return

        approval_status = result.get("approval_status", "not_required")
        status = (
            JobStatus.REJECTED if approval_status == "rejected" else JobStatus.COMPLETED
        )
        await self.repository.update(
            item.job_id,
            status=status,
            completed_at=datetime.now(UTC),
            approval_request=result.get("approval_request"),
            result={
                "final_answer": result.get("final_answer", ""),
                "analysis_result": result.get("analysis_result"),
                "approval_status": approval_status,
                "completed_agents": result.get("completed_agents", []),
            },
        )


def initial_state(request: str) -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content=request)],
        "request": request,
        "next_agent": "researcher",
        "supervisor_instruction": "",
        "supervisor_reasoning": "",
        "supervisor_steps": 0,
        "research_findings": [],
        "analysis_result": None,
        "validation_feedback": [],
        "contributions": [],
        "completed_agents": [],
        "task_completed": False,
        "requires_approval": False,
        "approval_status": "not_required",
        "approval_request": None,
        "final_answer": "",
    }
