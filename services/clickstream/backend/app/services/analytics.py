"""Analytics service for fraud detection and recommendation metrics."""

from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from ..core.config import Settings
from ..models.analytics import (
    FraudMetric,
    FraudSummaryResponse,
    RecommendationAccuracy,
    RecommendationAccuracyResponse,
)
from .storage import StorageService

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class AnalyticsService:
    """Provide aggregated analytics sourced from the data lake."""

    settings: Settings
    storage: StorageService

    def get_fraud_metrics(self, *, window_minutes: int = 60) -> FraudSummaryResponse:
        """Fetch fraud detection metrics from the latest clickstream dataset."""

        df = self._load_clickstream()
        if df.empty:
            return self._empty_fraud_summary()

        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"])
        if df.empty:
            return self._empty_fraud_summary()

        window_end = df["timestamp"].max()
        window_start = window_end - timedelta(minutes=window_minutes)
        window_mask = (df["timestamp"] >= window_start) & (df["timestamp"] <= window_end)
        window_df = df.loc[window_mask]

        if window_df.empty:
            window_df = df
            window_start = df["timestamp"].min()
            window_end = df["timestamp"].max()

        suspicious_mask = window_df["event_type"].isin(["payment_failed"]) | window_df.get("tags", pd.Series(dtype=object)).apply(
            lambda tags: isinstance(tags, list) and any(tag == "fraud_suspected" for tag in tags)
        )

        total_transactions = int(window_df.shape[0])
        suspicious_transactions = int(suspicious_mask.sum())

        grouped = window_df.groupby("user_id")["event_id"].count()
        avg_events_per_user = float(grouped.mean()) if not grouped.empty else 0.0
        rapid_click_users = int((grouped >= 50).sum())

        metrics = [
            FraudMetric(
                name="suspicion_rate",
                value=self._safe_divide(suspicious_transactions, total_transactions),
                delta=None,
                threshold=0.02,
            ),
            FraudMetric(
                name="payment_failure_rate",
                value=self._safe_divide(
                    window_df.loc[window_df["event_type"] == "payment_failed"].shape[0],
                    total_transactions,
                ),
                delta=None,
            ),
            FraudMetric(name="avg_events_per_user", value=avg_events_per_user),
            FraudMetric(name="rapid_click_users", value=float(rapid_click_users)),
        ]

        return FraudSummaryResponse(
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
            total_transactions=total_transactions,
            suspicious_transactions=suspicious_transactions,
            metrics=metrics,
        )

    def get_recommendation_accuracy(self, *, top_ks: tuple[int, ...] = (5, 10, 20)) -> RecommendationAccuracyResponse:
        """Estimate recommendation accuracy based on clickstream engagement."""

        df = self._load_clickstream()
        if df.empty:
            return self._empty_accuracy_response(top_ks)

        df_views = df[df["event_type"] == "view"]
        df_purchases = df[df["event_type"] == "purchase"]

        if df_purchases.empty:
            return self._empty_accuracy_response(top_ks)

        metrics: list[RecommendationAccuracy] = []
        sampled_users = 0
        purchase_users = df_purchases["user_id"].unique()

        for k in top_ks:
            precision_sum = 0.0
            recall_sum = 0.0
            map_sum = 0.0
            ndcg_sum = 0.0
            user_counter = 0

            for user_id in purchase_users:
                user_purchases = df_purchases.loc[df_purchases["user_id"] == user_id, "product_id"].unique()
                if user_purchases.size == 0:
                    continue

                user_views = df_views.loc[df_views["user_id"] == user_id]
                if user_views.empty:
                    continue

                view_counts = user_views.groupby("product_id")["event_id"].count().sort_values(ascending=False)
                top_products = list(view_counts.head(k).index)
                if not top_products:
                    continue

                hits = [1 if product in user_purchases else 0 for product in top_products]
                hit_count = sum(hits)

                precision = hit_count / k
                recall = hit_count / min(len(user_purchases), k)

                cumulative_hits = 0
                precision_accumulator = 0.0
                dcg = 0.0
                for rank, hit in enumerate(hits, start=1):
                    if hit:
                        cumulative_hits += 1
                        precision_accumulator += cumulative_hits / rank
                        dcg += 1 / math.log2(rank + 1)

                map_at_k = precision_accumulator / min(len(user_purchases), k) if user_purchases.size else 0.0
                ideal_hits = min(len(user_purchases), k)
                idcg = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1)) if ideal_hits else 0.0
                ndcg = (dcg / idcg) if idcg else 0.0

                precision_sum += precision
                recall_sum += recall
                map_sum += map_at_k
                ndcg_sum += ndcg
                user_counter += 1

            sampled_users = max(sampled_users, user_counter)

            metric = RecommendationAccuracy(
                model_version="latest",
                top_k=k,
                precision_at_k=self._safe_divide(precision_sum, user_counter),
                recall_at_k=self._safe_divide(recall_sum, user_counter),
                map_at_k=self._safe_divide(map_sum, user_counter),
                ndcg_at_k=self._safe_divide(ndcg_sum, user_counter),
            )
            metrics.append(metric)

        return RecommendationAccuracyResponse(
            evaluation_id=f"clickstream-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            evaluation_type="full",
            sampled_users=sampled_users,
            generated_at=datetime.utcnow().isoformat(),
            metrics=metrics,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_clickstream(self) -> pd.DataFrame:
        payload = self.storage.fetch_dataset("clickstream/latest.jsonl")
        if payload is None:
            return pd.DataFrame(columns=["event_id", "timestamp", "user_id", "product_id", "event_type", "tags"])
        try:
            return pd.read_json(io.BytesIO(payload), orient="records", lines=True)
        except ValueError:
            LOGGER.warning("Failed to parse clickstream JSON payload; returning empty frame")
            return pd.DataFrame(columns=["event_id", "timestamp", "user_id", "product_id", "event_type", "tags"])

    @staticmethod
    def _safe_divide(numerator: float, denominator: float) -> float:
        return float(numerator) / denominator if denominator else 0.0

    def _empty_fraud_summary(self) -> FraudSummaryResponse:
        now = datetime.utcnow().isoformat()
        return FraudSummaryResponse(
            window_start=now,
            window_end=now,
            total_transactions=0,
            suspicious_transactions=0,
            metrics=[
                FraudMetric(name="suspicion_rate", value=0.0, threshold=0.02),
                FraudMetric(name="payment_failure_rate", value=0.0),
                FraudMetric(name="avg_events_per_user", value=0.0),
            ],
        )

    def _empty_accuracy_response(self, top_ks: tuple[int, ...]) -> RecommendationAccuracyResponse:
        now = datetime.utcnow().isoformat()
        metrics = [
            RecommendationAccuracy(
                model_version="latest",
                top_k=k,
                precision_at_k=0.0,
                recall_at_k=0.0,
                map_at_k=0.0,
                ndcg_at_k=0.0,
            )
            for k in top_ks
        ]
        return RecommendationAccuracyResponse(
            evaluation_id="none",
            evaluation_type="full",
            sampled_users=0,
            generated_at=now,
            metrics=metrics,
        )

