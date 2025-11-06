"""Unit tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch


def test_openapi_docs_accessible(client: TestClient):
    """Test that OpenAPI documentation is accessible."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_json_accessible(client: TestClient):
    """Test that OpenAPI JSON spec is accessible."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["info"]["title"] == "Clickstream Analytics Service"


def test_analytics_fraud_endpoint_structure(client: TestClient):
    """Test that the fraud analytics endpoint exists and has proper structure."""
    # Mock the analytics service to avoid external dependencies
    with patch("app.api.v1.endpoints.analytics.get_analytics_service") as mock_service:
        mock_analytics = Mock()
        mock_analytics.get_fraud_metrics.return_value = {
            "total_transactions": 1000,
            "fraudulent_transactions": 50,
            "fraud_rate": 0.05,
            "total_value": 100000.0,
            "fraudulent_value": 5000.0,
            "fraud_detection_accuracy": 0.95,
        }
        mock_service.return_value = mock_analytics
        
        response = client.get("/api/v1/analytics/fraud")
        assert response.status_code == 200
        data = response.json()
        assert "total_transactions" in data
        assert "fraudulent_transactions" in data
        assert "fraud_rate" in data


def test_analytics_recommendations_endpoint_structure(client: TestClient):
    """Test that the recommendation accuracy endpoint exists and has proper structure."""
    with patch("app.api.v1.endpoints.analytics.get_analytics_service") as mock_service:
        mock_analytics = Mock()
        mock_analytics.get_recommendation_accuracy.return_value = {
            "total_recommendations": 10000,
            "clicked_recommendations": 1500,
            "click_through_rate": 0.15,
            "total_conversions": 300,
            "conversion_rate": 0.03,
            "average_recommendation_quality": 0.82,
        }
        mock_service.return_value = mock_analytics
        
        response = client.get("/api/v1/analytics/recommendations/accuracy")
        assert response.status_code == 200
        data = response.json()
        assert "total_recommendations" in data
        assert "click_through_rate" in data


def test_cors_headers(client: TestClient):
    """Test that CORS headers are properly set."""
    response = client.options(
        "/api/v1/health/live",
        headers={"Origin": "http://example.com", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    # CORS headers should be present
    assert "access-control-allow-origin" in response.headers


def test_data_generation_endpoint_exists(client: TestClient):
    """Test that the data generation endpoint exists."""
    # We won't actually call it since it runs a subprocess
    # Just verify it's registered in the OpenAPI spec
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    paths = spec.get("paths", {})
    assert "/api/v1/data/generate" in paths

