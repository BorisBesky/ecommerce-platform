"""Clickstream simulation utilities."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import BackgroundTasks

from ..core.config import Settings
from ..models.simulation import SimulationMode, SimulationParameters, SimulationRun
from ..simulation import ClickstreamDataGenerator
from .storage import StorageService

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ClickstreamSimulator:
    """Encapsulates logic required to simulate clickstream data."""

    settings: Settings

    def create_run(
        self,
        params: SimulationParameters,
        storage: StorageService,
        *,
        request_id: str | None = None,
        background_tasks: BackgroundTasks | None = None,
    ) -> SimulationRun:
        """Persist a new simulation run and optionally execute it asynchronously."""

        run = SimulationRun(
            run_id=str(uuid4()),
            mode=params.mode,
            status="pending",
            batches=params.batches,
            batch_size=params.batch_size,
            user_count=params.user_count,
            product_count=params.product_count,
            event_count=0,
            request_id=request_id,
        )

        storage.save_run(run)

        if background_tasks:
            background_tasks.add_task(self._execute_run, run, params, storage)
        else:
            self._execute_run(run, params, storage)

        return run

    # ------------------------------------------------------------------
    # Internal execution pipeline
    # ------------------------------------------------------------------
    def _execute_run(self, run: SimulationRun, params: SimulationParameters, storage: StorageService) -> None:
        LOGGER.info(
            "Starting simulation run=%s mode=%s batches=%s batch_size=%s",
            run.run_id,
            params.mode,
            params.batches,
            params.batch_size,
        )

        storage.update_run_status(run, status="running")

        try:
            storage.ensure_namespace()
            existing_users: Optional[bytes] = None
            existing_products: Optional[bytes] = None
            if params.mode == SimulationMode.INCREMENTAL:
                existing_users = storage.fetch_dataset("users.csv")
                existing_products = storage.fetch_dataset("products.csv")

            generator = ClickstreamDataGenerator(
                params,
                seed=params.seed,
                existing_users_csv=existing_users,
                existing_products_csv=existing_products,
            )

            artifacts = generator.prepare()
            artifact_paths: dict[str, str] = {}

            if artifacts.users_csv is not None:
                artifact_paths["users_csv"] = storage.store_artifact(
                    run.run_id,
                    "users.csv",
                    artifacts.users_csv,
                    content_type="text/csv",
                )
                artifact_paths["canonical_users_csv"] = storage.store_canonical_dataset(
                    "users.csv",
                    artifacts.users_csv,
                    content_type="text/csv",
                )
            elif existing_users is not None:
                artifact_paths["canonical_users_csv"] = f"s3://{storage.bucket}/data/users.csv"

            if artifacts.products_csv is not None:
                artifact_paths["products_csv"] = storage.store_artifact(
                    run.run_id,
                    "products.csv",
                    artifacts.products_csv,
                    content_type="text/csv",
                )
                artifact_paths["canonical_products_csv"] = storage.store_canonical_dataset(
                    "products.csv",
                    artifacts.products_csv,
                    content_type="text/csv",
                )
            elif existing_products is not None:
                artifact_paths["canonical_products_csv"] = f"s3://{storage.bucket}/data/products.csv"

            combined_records: list[str] = []
            total_events = 0

            for batch in generator.iter_batches():
                key = storage.store_json_lines(
                    run.run_id,
                    f"clickstream-batch-{batch.index:04d}.jsonl",
                    batch.records,
                )
                artifact_paths[f"events_batch_{batch.index:04d}"] = key
                combined_records.extend(batch.records)
                total_events += batch.size

            if combined_records:
                combined_payload = "\n".join(combined_records).encode("utf-8")
                artifact_paths["canonical_clickstream_run"] = storage.store_canonical_dataset(
                    f"clickstream/{run.run_id}.jsonl",
                    combined_payload,
                    content_type="application/json",
                )
                artifact_paths["canonical_clickstream_latest"] = storage.store_canonical_dataset(
                    "clickstream/latest.jsonl",
                    combined_payload,
                    content_type="application/json",
                )

            metadata_key = storage.store_artifact(
                run.run_id,
                "metadata.json",
                json.dumps(artifacts.metadata, separators=(",", ":")).encode("utf-8"),
                content_type="application/json",
            )
            artifact_paths["metadata"] = metadata_key

            run.user_count = generator.user_count
            run.product_count = generator.product_count
            run.event_count = total_events

            storage.update_run_status(run, status="completed", artifact_paths=artifact_paths)

            LOGGER.info(
                "Completed simulation run=%s events=%s users=%s products=%s",
                run.run_id,
                total_events,
                run.user_count,
                run.product_count,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Simulation run %s failed: %s", run.run_id, exc)
            storage.update_run_status(run, status="failed", error_message=str(exc))

