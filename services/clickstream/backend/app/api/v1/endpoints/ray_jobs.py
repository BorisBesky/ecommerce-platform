"""Endpoints for orchestrating Ray jobs."""

from __future__ import annotations

from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ....dependencies.services import get_ray_manager
from ....models.ray import (
    RayJobStatusResponse,
    RayJobSubmission,
    RayJobSubmissionResponse,
)
from ....services.ray_manager import RayJobManager

router = APIRouter()


@router.post(
    "/jobs",
    response_model=RayJobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a Ray job",
)
async def submit_ray_job(
    payload: RayJobSubmission,
    manager: RayJobManager = Depends(get_ray_manager),
) -> RayJobSubmissionResponse:
    """Submit a Ray job to the configured Ray cluster."""

    try:
        job = manager.submit(payload)
    except httpx.HTTPError as exc:  # pragma: no cover - network edge cases
        raise HTTPException(status_code=502, detail=f"Ray job submission failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RayJobSubmissionResponse(job=job)


@router.get(
    "/jobs/{job_id}",
    response_model=RayJobStatusResponse,
    summary="Fetch Ray job status",
)
async def get_ray_job_status(
    job_id: str,
    include_logs: bool = Query(True, description="Include recent job logs"),
    log_lines: int = Query(200, ge=1, le=500, description="Number of log lines to retrieve"),
    manager: RayJobManager = Depends(get_ray_manager),
) -> RayJobStatusResponse:
    """Return the status for a submitted Ray job."""

    try:
        return manager.status(job_id, include_logs=include_logs, log_lines=log_lines)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except httpx.HTTPError as exc:  # pragma: no cover - network edge cases
        raise HTTPException(status_code=502, detail=f"Failed to query Ray job status: {exc}") from exc

