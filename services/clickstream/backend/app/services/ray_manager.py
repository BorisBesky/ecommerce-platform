"""Ray job orchestration helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict
from urllib.parse import urljoin

import httpx

from ..core.config import Settings
from ..models.ray import (
    RayJobInfo,
    RayJobStatus,
    RayJobStatusResponse,
    RayJobSubmission,
    RayJobType,
)

LOGGER = logging.getLogger(__name__)


DEFAULT_ENTRYPOINTS: dict[RayJobType, str] = {
    RayJobType.FULL_REFRESH: "python /apps/train_recommendation_model_k8s.py",
    RayJobType.INCREMENTAL_REFRESH: "python /apps/train_prio_aware_recommendation_model.py",
    RayJobType.BATCH_INFERENCE: "python /apps/serve_recommendations.py --mode batch",
}


@dataclass(slots=True)
class RayJobManager:
    """Submit and manage Ray jobs via the Ray Jobs REST API."""

    settings: Settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def submit(self, submission: RayJobSubmission) -> RayJobInfo:
        """Submit a Ray job and return job metadata."""

        payload = self._build_submission_payload(submission)
        LOGGER.info("Submitting Ray job type=%s entrypoint=%s", submission.job_type, payload["entrypoint"])

        response = httpx.post(self._jobs_endpoint(), json=payload, timeout=30.0)
        response.raise_for_status()
        data = response.json()

        job_id = data.get("job_id")
        status = self._normalize_status(data.get("status"))
        message = data.get("message")

        return RayJobInfo(
            job_id=job_id or "unknown",
            job_type=submission.job_type,
            status=status,
            submission_id=data.get("submission_id"),
            message=message,
            details=data,
        )

    def status(self, job_id: str, *, include_logs: bool = True, log_lines: int = 200) -> RayJobStatusResponse:
        """Fetch Ray job status (and optionally latest logs)."""

        LOGGER.debug("Fetching Ray job status for job_id=%s", job_id)

        response = httpx.get(self._job_detail_endpoint(job_id), timeout=15.0)
        if response.status_code == 404:
            raise ValueError(f"Ray job {job_id} not found")
        response.raise_for_status()
        data = response.json()

        status = self._normalize_status(data.get("status"))
        job_type = self._parse_job_type(data)

        job_info = RayJobInfo(
            job_id=job_id,
            job_type=job_type,
            status=status,
            submission_id=data.get("submission_id"),
            message=data.get("message"),
            details=data,
        )

        logs: list[str] | None = None
        if include_logs:
            logs = self._fetch_logs(job_id, limit=log_lines)

        return RayJobStatusResponse(
            job=job_info,
            logs=logs,
            dashboard_url=self.settings.ray_dashboard_url,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _jobs_endpoint(self) -> str:
        return urljoin(self._base_url(), "jobs/")

    def _job_detail_endpoint(self, job_id: str) -> str:
        return urljoin(self._base_url(), f"jobs/{job_id}")

    def _logs_endpoint(self, job_id: str) -> str:
        return urljoin(self._base_url(), f"jobs/{job_id}/logs")

    def _base_url(self) -> str:
        if not self.settings.ray_job_submission_url:
            raise ValueError("RAY_JOB_SUBMISSION_URL is not configured")
        return self.settings.ray_job_submission_url.rstrip("/") + "/"

    def _build_submission_payload(self, submission: RayJobSubmission) -> Dict[str, Any]:
        entrypoint = submission.entrypoint or DEFAULT_ENTRYPOINTS.get(submission.job_type)
        if not entrypoint:
            raise ValueError(f"No entrypoint configured for job type {submission.job_type}")

        runtime_env = self._merge_runtime_env(submission)
        metadata = submission.metadata or {}
        metadata.setdefault("job_type", submission.job_type.value)

        return {
            "entrypoint": entrypoint,
            "runtime_env": runtime_env,
            "metadata": metadata,
        }

    def _merge_runtime_env(self, submission: RayJobSubmission) -> dict[str, Any]:
        base_env = {
            "env_vars": {
                "RAY_ADDRESS": "auto",
                "RAY_NAMESPACE": self.settings.ray_namespace,
                "MINIO_ENDPOINT": self.settings.minio_endpoint,
                "MINIO_ACCESS_KEY": self.settings.minio_access_key,
                "MINIO_SECRET_KEY": self.settings.minio_secret_key,
                "CLICKSTREAM_S3_BUCKET": self.settings.minio_bucket,
                "CLICKSTREAM_S3_KEY": "data/clickstream/clickstream.jsonl",
                "MODEL_OUTPUT_KEY": "models/prio_aware_recommendation_model.pkl",
            },
            "pip": [
                "numpy<2",
                "pandas",
                "boto3",
                "s3fs",
                "pyarrow",
            ],
        }

        if submission.job_type == RayJobType.INCREMENTAL_REFRESH:
            base_env["env_vars"].update(
                {
                    "INCREMENTAL_MODE": "true",
                    "NEW_CLICKSTREAM_S3_KEY": "data/clickstream/latest.jsonl",
                }
            )
        else:
            base_env["env_vars"].update({"INCREMENTAL_MODE": "false"})

        if submission.runtime_env:
            runtime_env = submission.runtime_env.copy()
        else:
            runtime_env = {}

        # Merge env vars
        env_vars = runtime_env.get("env_vars", {})
        env_vars = {**base_env["env_vars"], **env_vars}
        runtime_env["env_vars"] = env_vars

        # Merge pip dependencies (ensure uniqueness while preserving order)
        pip_packages = list(dict.fromkeys(base_env.get("pip", []) + runtime_env.get("pip", [])))
        runtime_env["pip"] = pip_packages

        # Merge other top-level keys (e.g., working_dir, py_modules)
        for key, value in base_env.items():
            if key in {"env_vars", "pip"}:
                continue
            runtime_env.setdefault(key, value)

        return runtime_env

    def _normalize_status(self, status: str | None) -> RayJobStatus:
        if not status:
            return RayJobStatus.UNKNOWN
        try:
            return RayJobStatus(status.upper())
        except ValueError:
            LOGGER.debug("Encountered unknown Ray job status: %s", status)
            return RayJobStatus.UNKNOWN

    def _parse_job_type(self, payload: dict[str, Any]) -> RayJobType:
        metadata = payload.get("metadata") or {}
        job_type_value = metadata.get("job_type")
        if job_type_value:
            try:
                return RayJobType(job_type_value)
            except ValueError:
                LOGGER.debug("Unrecognized job type in metadata: %s", job_type_value)
        return RayJobType.FULL_REFRESH

    def _fetch_logs(self, job_id: str, *, limit: int) -> list[str] | None:
        params = {"line_limit": limit}
        response = httpx.get(self._logs_endpoint(job_id), params=params, timeout=10.0)
        if response.status_code != 200:
            LOGGER.debug("Failed to fetch logs for job %s: %s", job_id, response.text)
            return None
        try:
            content = response.json()
        except ValueError:
            return response.text.strip().splitlines()

        logs = content.get("logs")
        if isinstance(logs, str):
            return logs.strip().splitlines()
        if isinstance(logs, list):
            return logs
        return None

