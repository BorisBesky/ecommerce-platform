"""Models for Ray job orchestration responses."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field

from .base import APIModel, TimestampedModel


class RayJobType(str, Enum):
    """Types of Ray jobs supported by the service."""

    FULL_REFRESH = "full_refresh"
    INCREMENTAL_REFRESH = "incremental_refresh"
    BATCH_INFERENCE = "batch_inference"


class RayJobStatus(str, Enum):
    """High-level Ray job status values returned by the Ray Jobs API."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class RayJobSubmission(APIModel):
    """Request payload for submitting a Ray job."""

    job_type: RayJobType
    entrypoint: str | None = None
    runtime_env: dict[str, object] | None = None
    metadata: dict[str, str] | None = None


class RayJobInfo(TimestampedModel):
    """Metadata describing a submitted Ray job."""

    job_id: str
    job_type: RayJobType
    status: RayJobStatus = RayJobStatus.PENDING
    submission_id: str | None = None
    message: str | None = None
    details: dict[str, object] | None = None


class RayJobSubmissionResponse(APIModel):
    """Response returned upon successful job submission."""

    job: RayJobInfo


class RayJobStatusResponse(APIModel):
    """Response containing the latest job status."""

    job: RayJobInfo
    logs: list[str] | None = Field(default=None, description="Optional tail of job logs")
    dashboard_url: str | None = None

