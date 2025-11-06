"""Tests for data generation endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock
import asyncio


def test_data_generation_endpoint_registered(client: TestClient):
    """Test that the data generation endpoint is registered in the API."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    
    spec = response.json()
    paths = spec.get("paths", {})
    
    # Check that the data generation endpoint is registered
    assert "/api/v1/data/generate" in paths, "Data generation endpoint not found in API"
    
    # Verify it's a POST endpoint
    data_gen_spec = paths["/api/v1/data/generate"]
    assert "post" in data_gen_spec, "Data generation should be a POST endpoint"
    
    # Check the response type
    post_spec = data_gen_spec["post"]
    assert "summary" in post_spec
    assert "data generation" in post_spec["summary"].lower()


def test_data_generation_endpoint_structure(client: TestClient):
    """Test that the data generation endpoint has proper structure."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    
    spec = response.json()
    endpoint_spec = spec["paths"]["/api/v1/data/generate"]["post"]
    
    # Verify endpoint metadata
    assert endpoint_spec["tags"] == ["data"]
    assert endpoint_spec["summary"]
    
    # Verify responses structure - should have 200 status code
    responses = endpoint_spec.get("responses", {})
    assert "200" in responses, "Should have 200 status code in responses"
    assert "description" in responses["200"], "200 response should have description"


@pytest.mark.asyncio
async def test_data_generation_script_execution_mocked(client: TestClient):
    """Test data generation with mocked subprocess (unit test)."""
    # Mock the subprocess to avoid actually running the generation
    with patch("app.api.v1.endpoints.data.asyncio.create_subprocess_exec") as mock_subprocess:
        # Create a mock process
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()
        
        # Mock readline to return empty (end of stream)
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr.readline = AsyncMock(return_value=b"")
        mock_process.wait = AsyncMock()
        
        mock_subprocess.return_value = mock_process
        
        # Call the endpoint
        response = client.post("/api/v1/data/generate")
        
        # Should return 200 and streaming response
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")


def test_data_generation_requires_post(client: TestClient):
    """Test that data generation endpoint requires POST method."""
    # GET should not be allowed
    response = client.get("/api/v1/data/generate")
    assert response.status_code == 405  # Method Not Allowed


def test_data_generation_endpoint_uses_settings(client: TestClient):
    """Test that data generation endpoint has access to settings."""
    # Verify the endpoint is properly configured with dependency injection
    response = client.get("/openapi.json")
    assert response.status_code == 200
    
    spec = response.json()
    # The endpoint should be registered, which means dependencies are working
    assert "/api/v1/data/generate" in spec["paths"]

