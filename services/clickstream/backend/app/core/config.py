"""Application configuration and settings management."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Pydantic-backed application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")

    # App metadata
    app_name: str = "clickstream-analytics"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    docs_url: str | None = "/docs"
    redoc_url: str | None = "/redoc"
    openapi_url: str = "/openapi.json"

    # MinIO / S3 configuration
    minio_endpoint: str = Field("http://minio.ecommerce-platform.svc.cluster.local:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(..., alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(..., alias="MINIO_SECRET_KEY")
    minio_region: str | None = Field(None, alias="MINIO_REGION")
    minio_secure: bool = Field(False, alias="MINIO_SECURE")
    minio_bucket: str = Field("warehouse", alias="MINIO_BUCKET")

    # Iceberg configuration
    iceberg_namespace: str = Field("analytics", alias="ICEBERG_NAMESPACE")
    iceberg_warehouse: str = Field("s3a://warehouse", alias="ICEBERG_WAREHOUSE")
    nessie_uri: Annotated[str, AnyUrl] = Field(
        "http://nessie.ecommerce-platform.svc.cluster.local:19120/api/v1",
        alias="NESSIE_URI",
    )
    nessie_branch: str = Field("main", alias="NESSIE_BRANCH")

    # Ray configuration
    ray_dashboard_url: str | None = Field(None, alias="RAY_DASHBOARD_URL")
    ray_address: str = Field("ray://ray-head.ecommerce-platform.svc.cluster.local:10001", alias="RAY_ADDRESS")
    ray_namespace: str = Field("clickstream", alias="RAY_NAMESPACE")
    ray_job_submission_url: str | None = Field(
        "http://ray-head.ecommerce-platform.svc.cluster.local:8265/api/jobs",
        alias="RAY_JOB_SUBMISSION_URL",
    )

    # Feature flags / simulation defaults
    default_simulation_batch_size: int = Field(1000, alias="DEFAULT_SIMULATION_BATCH_SIZE")
    default_simulation_users: int = Field(100, alias="DEFAULT_SIMULATION_USERS")

    # Security / CORS
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()

