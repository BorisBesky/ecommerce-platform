"""Unit tests for health endpoints."""

from fastapi.testclient import TestClient


def test_liveness_probe(client: TestClient):
    """Test that the liveness probe returns 200 OK."""
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_readiness_probe(client: TestClient):
    """Test that the readiness probe returns 200 OK."""
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"

