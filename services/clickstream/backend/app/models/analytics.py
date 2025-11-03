"""Models for analytics metrics responses."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import APIModel


class FraudMetric(APIModel):
    """Fraud detection aggregate metric."""

    name: str
    value: float
    delta: float | None = Field(None, description="Change relative to previous window")
    threshold: float | None = None


class FraudSummaryResponse(APIModel):
    """Collection of fraud metrics plus contextual metadata."""

    window_start: str
    window_end: str
    total_transactions: int
    suspicious_transactions: int
    metrics: list[FraudMetric]


class RecommendationAccuracy(APIModel):
    """Recommendation model accuracy breakdown."""

    model_version: str
    top_k: int
    precision_at_k: float
    recall_at_k: float
    map_at_k: float
    ndcg_at_k: float


class RecommendationAccuracyResponse(APIModel):
    """Response payload for recommendation accuracy analytics."""

    evaluation_id: str
    evaluation_type: Literal["full", "incremental"]
    sampled_users: int
    generated_at: str
    metrics: list[RecommendationAccuracy]

