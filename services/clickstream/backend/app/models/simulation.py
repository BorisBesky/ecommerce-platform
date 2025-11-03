"""Models for clickstream simulation API contracts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field

from .base import APIModel, TimestampedModel


class SimulationMode(str, Enum):
    """Supported clickstream simulation modes."""

    FULL = "full"
    INCREMENTAL = "incremental"


class SimulationParameters(APIModel):
    """Parameters controlling a clickstream simulation run."""

    mode: SimulationMode = SimulationMode.FULL
    batches: int = Field(1, ge=1, description="Number of batches to generate")
    batch_size: int = Field(1000, ge=1, description="Events per batch")
    user_count: int = Field(100, ge=1, description="Unique users to simulate")
    product_count: int = Field(500, ge=1, description="Distinct products to reference")
    seed: int | None = Field(None, description="Optional RNG seed for reproducibility")


class SimulationRun(TimestampedModel):
    """Metadata describing a simulation run persisted in storage."""

    run_id: str = Field(..., description="Unique identifier for the simulation run")
    mode: SimulationMode
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    batches: int
    batch_size: int
    user_count: int
    product_count: int
    event_count: int = 0
    request_id: str | None = Field(None, description="Optional request tracing identifier")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    artifact_paths: dict[str, str] | None = Field(
        default=None,
        description="Mapping of artifact names to their MinIO object paths",
    )


class SimulationTriggerResponse(APIModel):
    """Response returned when a new simulation run is enqueued."""

    run_id: str
    status: str


class SimulationStatusResponse(APIModel):
    """Current status of a simulation run."""

    run: SimulationRun

