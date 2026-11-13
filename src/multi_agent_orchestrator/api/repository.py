"""Persistencia de trabajos en Redis."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from multi_agent_orchestrator.api.schemas import JobRecord, JobStatus


class JobNotFoundError(LookupError):
    pass


class RedisJobRepository:
    def __init__(self, client: Redis, *, ttl_seconds: int = 86_400) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(job_id: str) -> str:
        return f"agent-job:{job_id}"

    async def create(self, job_id: str, request: str) -> JobRecord:
        now = datetime.now(UTC)
        record = JobRecord(
            job_id=job_id,
            request=request,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
        key = self._key(job_id)
        await self._client.hset(key, mapping=self._encode(record.model_dump(mode="json")))
        await self._client.expire(key, self._ttl_seconds)
        return record

    async def get(self, job_id: str) -> JobRecord:
        data = await self._client.hgetall(self._key(job_id))
        if not data:
            raise JobNotFoundError(job_id)
        return JobRecord.model_validate(self._decode(data))

    async def update(self, job_id: str, **changes: Any) -> JobRecord:
        key = self._key(job_id)
        if not await self._client.exists(key):
            raise JobNotFoundError(job_id)
        changes["updated_at"] = datetime.now(UTC).isoformat()
        await self._client.hset(key, mapping=self._encode(changes))
        await self._client.expire(key, self._ttl_seconds)
        return await self.get(job_id)

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    @staticmethod
    def _encode(values: dict[str, Any]) -> dict[str, str]:
        return {
            key: json.dumps(value, ensure_ascii=False, default=str)
            for key, value in values.items()
        }

    @staticmethod
    def _decode(values: dict[Any, Any]) -> dict[str, Any]:
        decoded: dict[str, Any] = {}
        for raw_key, raw_value in values.items():
            key = raw_key.decode() if isinstance(raw_key, bytes) else str(raw_key)
            value = raw_value.decode() if isinstance(raw_value, bytes) else str(raw_value)
            decoded[key] = json.loads(value)
        return decoded
