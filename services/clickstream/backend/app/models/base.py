"""Shared Pydantic base models used across API payloads."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    """Canonical base model that enforces strict field definitions."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TimestampedModel(APIModel):
    """Common timestamp fields shared across responses."""

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

