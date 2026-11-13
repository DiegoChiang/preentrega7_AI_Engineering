"""Contratos Pydantic de la API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


TERMINAL_STATUSES = {JobStatus.COMPLETED, JobStatus.REJECTED, JobStatus.FAILED}


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: str = Field(min_length=10, max_length=4_000)


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    feedback: str = Field(default="", max_length=1_000)


class JobAccepted(BaseModel):
    job_id: str
    status: JobStatus
    status_url: str


class JobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    request: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    approval_request: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    redis: str
    queue_depth: int
