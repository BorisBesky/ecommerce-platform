"""Endpoints exposing fraud detection and recommendation analytics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ....dependencies.services import get_analytics_service
from ....models.analytics import FraudSummaryResponse, RecommendationAccuracyResponse
from ....services.analytics import AnalyticsService

router = APIRouter()


@router.get(
    "/fraud",
    response_model=FraudSummaryResponse,
    summary="Fraud detection overview",
)
async def fraud_summary(
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> FraudSummaryResponse:
    """Return aggregated fraud detection metrics sourced from the data lake."""

    try:
        return analytics_service.get_fraud_metrics()
    except Exception as exc:  # pragma: no cover - defensive barrier
        raise HTTPException(status_code=500, detail=f"Failed to compute fraud metrics: {exc}") from exc


@router.get(
    "/recommendations/accuracy",
    response_model=RecommendationAccuracyResponse,
    summary="Recommendation accuracy metrics",
)
async def recommendation_accuracy(
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> RecommendationAccuracyResponse:
    """Return recommendation accuracy metrics derived from clickstream engagement."""

    try:
        return analytics_service.get_recommendation_accuracy()
    except Exception as exc:  # pragma: no cover - defensive barrier
        raise HTTPException(status_code=500, detail=f"Failed to compute recommendation metrics: {exc}") from exc

