"""Storage and data access helpers for clickstream analytics."""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime
from typing import Any, Iterable

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from pyiceberg.catalog import load_catalog
from pyiceberg.catalog.catalog import Catalog
from pyiceberg.exceptions import NoSuchNamespaceError

from ..core.config import Settings
from ..models.simulation import SimulationRun

LOGGER = logging.getLogger(__name__)


class StorageService:
    """Facade for interacting with MinIO (S3) and Iceberg."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._s3_client: BaseClient | None = None
        self._catalog: Catalog | None = None
        self._bucket_checked: bool = False

    @property
    def s3_client(self) -> BaseClient:
        """Return a cached boto3 client."""

        if self._s3_client is None:
            LOGGER.info("Creating MinIO S3 client for endpoint %s", self._settings.minio_endpoint)
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=self._settings.minio_endpoint,
                aws_access_key_id=self._settings.minio_access_key,
                aws_secret_access_key=self._settings.minio_secret_key,
                region_name=self._settings.minio_region,
                use_ssl=self._settings.minio_secure,
            )

        return self._s3_client

    @property
    def bucket(self) -> str:
        """Return the target MinIO bucket name."""

        return self._settings.minio_bucket

    @property
    def catalog(self) -> Catalog:
        """Return an Iceberg catalog client."""

        if self._catalog is None:
            LOGGER.info("Loading Iceberg catalog (nessie) at %s", self._settings.nessie_uri)
            self._catalog = load_catalog(
                "nessie",
                uri=str(self._settings.nessie_uri),
                warehouse=self._settings.iceberg_warehouse,
                nessie_branch=self._settings.nessie_branch,
            )

        return self._catalog

    def ensure_bucket(self) -> None:
        """Ensure the configured S3 bucket exists."""

        if self._bucket_checked:
            return

        bucket = self._settings.minio_bucket
        try:
            self.s3_client.head_bucket(Bucket=bucket)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code not in {"404", "NoSuchBucket", None}:  # 404 means bucket missing
                LOGGER.debug("Head bucket failed with %s", error_code)
            LOGGER.info("Creating missing MinIO bucket: %s", bucket)
            self.s3_client.create_bucket(Bucket=bucket)

        self._bucket_checked = True

    def ensure_namespace(self) -> None:
        """Ensure the configured Iceberg namespace exists."""

        namespace = self._settings.iceberg_namespace
        try:
            self.catalog.load_namespace(namespace)
        except NoSuchNamespaceError:
            LOGGER.info("Creating missing Iceberg namespace: %s", namespace)
            self.catalog.create_namespace(namespace)

    # ------------------------------------------------------------------
    # Simulation run persistence helpers
    # ------------------------------------------------------------------
    def _run_metadata_key(self, run_id: str) -> str:
        return f"clickstream/runs/{run_id}/metadata.json"

    def _run_artifact_prefix(self, run_id: str) -> str:
        return f"clickstream/runs/{run_id}/artifacts"

    def save_run(self, run: SimulationRun) -> None:
        """Persist simulation run metadata."""

        self.ensure_bucket()
        payload = json.dumps(run.model_dump(mode="json"), separators=(",", ":")).encode("utf-8")
        self.s3_client.put_object(
            Bucket=self._settings.minio_bucket,
            Key=self._run_metadata_key(run.run_id),
            Body=payload,
            ContentType="application/json",
        )

    def load_run(self, run_id: str) -> SimulationRun | None:
        """Load simulation run metadata if it exists."""

        self.ensure_bucket()
        try:
            response = self.s3_client.get_object(
                Bucket=self._settings.minio_bucket,
                Key=self._run_metadata_key(run_id),
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
                return None
            raise

        payload = json.load(response["Body"])
        return SimulationRun.model_validate(payload)

    def store_artifact(self, run_id: str, name: str, body: bytes, content_type: str) -> str:
        """Store an artifact for a simulation run and return the object key."""

        self.ensure_bucket()
        key = f"{self._run_artifact_prefix(run_id)}/{name}"
        self.s3_client.put_object(
            Bucket=self._settings.minio_bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        return f"s3://{self._settings.minio_bucket}/{key}"

    def store_json_lines(self, run_id: str, name: str, records: Iterable[str]) -> str:
        """Store newline-delimited JSON records as an artifact."""

        buffer = io.BytesIO()
        for record in records:
            buffer.write(record.encode("utf-8"))
            if not record.endswith("\n"):
                buffer.write(b"\n")

        return self.store_artifact(run_id, name, buffer.getvalue(), content_type="application/json")

    def store_canonical_dataset(self, name: str, body: bytes, content_type: str) -> str:
        """Update the canonical dataset location used by Spark ETL jobs."""

        self.ensure_bucket()
        key = f"data/{name}"
        self.s3_client.put_object(
            Bucket=self._settings.minio_bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        return f"s3://{self._settings.minio_bucket}/{key}"

    def fetch_dataset(self, name: str) -> bytes | None:
        """Fetch a canonical dataset (users/products) if present."""

        self.ensure_bucket()
        key = f"data/{name}"
        try:
            response = self.s3_client.get_object(Bucket=self._settings.minio_bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
                return None
            raise

        return response["Body"].read()

    def update_run_status(
        self,
        run: SimulationRun,
        *,
        status: str,
        error_message: str | None = None,
        artifact_paths: dict[str, str] | None = None,
    ) -> SimulationRun:
        """Persist new status and optional metadata for a simulation run."""

        run.status = status
        run.updated_at = datetime.utcnow()
        run.error_message = error_message
        if status == "running" and run.started_at is None:
            run.started_at = run.updated_at
        if status == "completed":
            run.finished_at = run.updated_at
        if artifact_paths:
            run.artifact_paths = (run.artifact_paths or {}) | artifact_paths
        self.save_run(run)
        return run

    # Placeholder methods for later tasks.
    def fetch_fraud_metrics(self, window_minutes: int = 60) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def fetch_recommendation_accuracy(self) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

