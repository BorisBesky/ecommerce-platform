"""Pytest configuration and fixtures for clickstream service tests."""

import os
from typing import Generator

import pytest

# Set required environment variables before importing the app
os.environ.setdefault("MINIO_ACCESS_KEY", "test-access-key")
os.environ.setdefault("MINIO_SECRET_KEY", "test-secret-key")
os.environ.setdefault("MINIO_ENDPOINT", "http://test-minio:9000")
os.environ.setdefault("MINIO_BUCKET", "test-bucket")
os.environ.setdefault("NESSIE_URI", "http://test-nessie:19120/api/v1")
os.environ.setdefault("RAY_ADDRESS", "ray://test-ray:10001")
os.environ.setdefault("RAY_JOB_SUBMISSION_URL", "http://test-ray:8265/api/jobs")

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings with mock values."""
    return Settings(
        MINIO_ACCESS_KEY="test-access-key",
        MINIO_SECRET_KEY="test-secret-key",
        minio_endpoint="http://test-minio:9000",
        minio_bucket="test-bucket",
        nessie_uri="http://test-nessie:19120/api/v1",
        ray_address="ray://test-ray:10001",
        ray_job_submission_url="http://test-ray:8265/api/jobs",
    )


@pytest.fixture
def app(test_settings: Settings):
    """Create a test FastAPI application instance."""
    return create_app(settings=test_settings)


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI application."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def e2e_base_url() -> str:
    """Get the base URL for e2e tests from environment or use default."""
    return os.getenv("CLICKSTREAM_BASE_URL", "http://localhost:8000")


@pytest.fixture
def e2e_client(e2e_base_url: str):
    """Create a client for e2e testing against a running service."""
    try:
        import httpx
        
        # Use httpx directly for e2e tests
        client = httpx.Client(base_url=e2e_base_url, timeout=30.0)
        yield client
        client.close()
    except ImportError:
        # Fall back to requests if httpx is not available
        import requests
        
        class RequestsAdapter:
            """Adapter to make requests look like httpx."""
            def __init__(self, base_url):
                self.base_url = base_url
                self.session = requests.Session()
            
            def get(self, path, **kwargs):
                return self.session.get(f"{self.base_url}{path}", **kwargs)
            
            def post(self, path, **kwargs):
                return self.session.post(f"{self.base_url}{path}", **kwargs)
            
            def options(self, path, **kwargs):
                return self.session.options(f"{self.base_url}{path}", **kwargs)
        
        client = RequestsAdapter(e2e_base_url)
        yield client

