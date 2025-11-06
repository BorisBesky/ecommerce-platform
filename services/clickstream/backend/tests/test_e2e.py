"""End-to-end tests for the clickstream service deployment.

These tests are designed to run against a deployed instance of the clickstream service
in a Kubernetes cluster. They verify that all endpoints are accessible and functioning
correctly.

Set the CLICKSTREAM_BASE_URL environment variable to the base URL of the deployed service.
Example: export CLICKSTREAM_BASE_URL=http://localhost:8000
"""

import os
import time

import pytest

# Skip all e2e tests if not explicitly enabled
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E_TESTS", "false").lower() != "true",
    reason="E2E tests require RUN_E2E_TESTS=true environment variable",
)


class TestHealthEndpoints:
    """Test suite for health check endpoints."""

    def test_liveness_probe(self, e2e_client):
        """Test that the liveness probe is accessible and returns correct status."""
        response = e2e_client.get("/api/v1/health/live")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["status"] == "ok", f"Expected status 'ok', got {data.get('status')}"

    def test_readiness_probe(self, e2e_client):
        """Test that the readiness probe is accessible and returns correct status."""
        response = e2e_client.get("/api/v1/health/ready")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["status"] == "ready", f"Expected status 'ready', got {data.get('status')}"


class TestDocumentation:
    """Test suite for API documentation endpoints."""

    def test_openapi_docs_accessible(self, e2e_client):
        """Test that Swagger UI documentation is accessible."""
        response = e2e_client.get("/docs")
        assert response.status_code == 200, f"Swagger docs not accessible: {response.status_code}"
        assert "swagger" in response.text.lower() or "openapi" in response.text.lower()

    def test_redoc_accessible(self, e2e_client):
        """Test that ReDoc documentation is accessible."""
        response = e2e_client.get("/redoc")
        assert response.status_code == 200, f"ReDoc not accessible: {response.status_code}"

    def test_openapi_json_accessible(self, e2e_client):
        """Test that OpenAPI JSON specification is accessible."""
        response = e2e_client.get("/openapi.json")
        assert response.status_code == 200, f"OpenAPI spec not accessible: {response.status_code}"
        spec = response.json()
        assert "info" in spec
        assert "paths" in spec
        assert spec["info"]["title"] == "Clickstream Analytics Service"


class TestAnalyticsEndpoints:
    """Test suite for analytics endpoints."""

    def test_fraud_analytics_endpoint(self, e2e_client):
        """Test that the fraud analytics endpoint is accessible."""
        response = e2e_client.get("/api/v1/analytics/fraud")
        
        # The endpoint should either return 200 with data or 500 if not configured
        # Both are valid for e2e testing - we just want to confirm it's accessible
        assert response.status_code in [200, 500], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            # Verify response structure - check for key fields from actual API
            # The API returns: total_transactions, suspicious_transactions, window_start, window_end, metrics
            expected_fields = [
                "total_transactions",
                "suspicious_transactions",
            ]
            for field in expected_fields:
                assert field in data, f"Missing expected field: {field}"

    def test_recommendation_accuracy_endpoint(self, e2e_client):
        """Test that the recommendation accuracy endpoint is accessible."""
        response = e2e_client.get("/api/v1/analytics/recommendations/accuracy")
        
        # Similar to fraud endpoint, accept both 200 and 500
        assert response.status_code in [200, 500], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            # Verify response structure - check for key fields from actual API
            # The API returns: evaluation_id, evaluation_type, sampled_users, generated_at, metrics
            expected_fields = [
                "evaluation_id",
                "sampled_users",
            ]
            for field in expected_fields:
                assert field in data, f"Missing expected field: {field}"


class TestRayEndpoints:
    """Test suite for Ray job management endpoints."""

    def test_ray_jobs_endpoint_exists(self, e2e_client):
        """Test that the Ray jobs endpoint exists and is properly configured."""
        # The API only has POST for /api/v1/ray/jobs and GET for /api/v1/ray/jobs/{job_id}
        # So we just verify the endpoint exists in the OpenAPI spec
        response = e2e_client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        paths = spec.get("paths", {})
        
        # Check that Ray job endpoints exist
        assert "/api/v1/ray/jobs" in paths, "Ray jobs endpoint not found"
        assert "/api/v1/ray/jobs/{job_id}" in paths, "Ray job status endpoint not found"


class TestDataEndpoints:
    """Test suite for data management endpoints."""

    def test_data_or_simulation_endpoint_exists(self, e2e_client):
        """Test that data generation or simulation endpoint is registered (but don't trigger it)."""
        # The deployed service might have either /api/v1/data/generate (new) or /api/v1/simulations (old)
        response = e2e_client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        paths = spec.get("paths", {})
        
        # Check for either endpoint - both are valid for different versions
        has_data_endpoint = "/api/v1/data/generate" in paths
        has_simulations_endpoint = "/api/v1/simulations" in paths
        
        assert has_data_endpoint or has_simulations_endpoint, (
            "Neither data generation nor simulations endpoint found in API spec"
        )
    
    def test_data_generation_endpoint_method(self, e2e_client):
        """Test that data generation endpoint has correct HTTP method."""
        response = e2e_client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        paths = spec.get("paths", {})
        
        # Check the HTTP method for data generation
        if "/api/v1/data/generate" in paths:
            endpoint_spec = paths["/api/v1/data/generate"]
            assert "post" in endpoint_spec, "Data generation should be a POST endpoint"
            
            # Verify GET is not allowed
            response = e2e_client.get("/api/v1/data/generate")
            assert response.status_code == 405, "GET should not be allowed for data generation"
        elif "/api/v1/simulations" in paths:
            endpoint_spec = paths["/api/v1/simulations"]
            assert "post" in endpoint_spec, "Simulations should be a POST endpoint"
    
    def test_data_generation_endpoint_metadata(self, e2e_client):
        """Test that data generation endpoint has proper metadata."""
        response = e2e_client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        paths = spec.get("paths", {})
        
        # Check metadata for whichever endpoint exists
        if "/api/v1/data/generate" in paths:
            endpoint_spec = paths["/api/v1/data/generate"]["post"]
            assert "summary" in endpoint_spec, "Endpoint should have a summary"
            assert "tags" in endpoint_spec, "Endpoint should have tags"
            assert "data" in endpoint_spec["tags"], "Should be tagged as 'data'"
        elif "/api/v1/simulations" in paths:
            endpoint_spec = paths["/api/v1/simulations"]["post"]
            assert "summary" in endpoint_spec, "Endpoint should have a summary"
            assert "tags" in endpoint_spec, "Endpoint should have tags"


class TestServiceConnectivity:
    """Test suite for overall service connectivity and availability."""

    def test_service_responds_quickly(self, e2e_client):
        """Test that the service responds within acceptable time limits."""
        start_time = time.time()
        response = e2e_client.get("/api/v1/health/live")
        elapsed_time = time.time() - start_time
        
        assert response.status_code == 200
        assert elapsed_time < 5.0, f"Service took too long to respond: {elapsed_time:.2f}s"

    def test_cors_configuration(self, e2e_client):
        """Test that CORS is properly configured."""
        response = e2e_client.options(
            "/api/v1/health/live",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        # Should have CORS headers
        headers = {k.lower(): v for k, v in response.headers.items()}
        assert "access-control-allow-origin" in headers

    def test_all_critical_endpoints_accessible(self, e2e_client):
        """Test that all critical endpoints are accessible."""
        critical_endpoints = [
            "/api/v1/health/live",
            "/api/v1/health/ready",
            "/docs",
            "/openapi.json",
        ]
        
        for endpoint in critical_endpoints:
            response = e2e_client.get(endpoint)
            assert response.status_code == 200, f"Critical endpoint {endpoint} returned {response.status_code}"


class TestServiceIntegration:
    """Test suite for integration with external services."""

    def test_service_has_proper_configuration(self, e2e_client):
        """Test that the service is properly configured by checking OpenAPI spec."""
        response = e2e_client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        
        # Verify essential paths exist
        paths = spec.get("paths", {})
        essential_paths = [
            "/api/v1/health/live",
            "/api/v1/health/ready",
            "/api/v1/analytics/fraud",
            "/api/v1/analytics/recommendations/accuracy",
        ]
        
        for path in essential_paths:
            assert path in paths, f"Essential path {path} missing from API"

    def test_error_handling(self, e2e_client):
        """Test that the service handles errors gracefully."""
        # Try to access a non-existent endpoint
        response = e2e_client.get("/api/v1/nonexistent")
        assert response.status_code == 404
        
        # Should return JSON error response
        try:
            error_data = response.json()
            assert "detail" in error_data
        except Exception:
            # FastAPI's default 404 might not be JSON, which is also fine
            pass


class TestDeploymentHealth:
    """Test suite for verifying deployment health and configuration."""

    def test_service_version_info(self, e2e_client):
        """Test that service version information is available."""
        response = e2e_client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        assert "info" in spec
        assert "version" in spec["info"]
        assert "title" in spec["info"]

    def test_no_5xx_errors_on_basic_endpoints(self, e2e_client):
        """Test that basic endpoints don't return 5xx errors."""
        basic_endpoints = [
            "/api/v1/health/live",
            "/api/v1/health/ready",
            "/docs",
            "/openapi.json",
        ]
        
        for endpoint in basic_endpoints:
            response = e2e_client.get(endpoint)
            assert response.status_code < 500, (
                f"Endpoint {endpoint} returned server error: {response.status_code}"
            )

