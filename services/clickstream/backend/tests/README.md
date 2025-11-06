# Clickstream Service Tests

This directory contains the test suite for the clickstream analytics service.

## Test Types

### Unit Tests
Unit tests verify individual components in isolation without external dependencies.

- `test_health.py` - Health endpoint tests
- `test_api.py` - API endpoint tests with mocked dependencies
- `test_data_generation.py` - Data generation endpoint tests (mocked)

### End-to-End Tests
E2E tests verify the complete service deployment in a Kubernetes environment.

- `test_e2e.py` - Comprehensive e2e tests for deployed service (includes data generation endpoint validation)

### Manual Tests
Optional tests that require explicit enabling and may be long-running.

- `test_data_generation_manual.py` - Manual tests that actually trigger data generation (skipped by default)

## Setup

### Install Test Dependencies

```bash
pip install -r requirements-test.txt
```

Or install the main requirements which include the app dependencies:

```bash
pip install -r ../requirements.txt
pip install -r requirements-test.txt
```

## Running Tests

### Unit Tests Only

Run unit tests without external dependencies:

```bash
cd /home/bb/Repo/ecommerce-platform/services/clickstream/backend
pytest tests/test_health.py tests/test_api.py -v
```

### E2E Tests

E2E tests require a running clickstream service. There are several ways to run them:

#### Option 1: Using the E2E Test Script (Recommended)

The script automatically sets up port forwarding and runs the tests:

```bash
cd /home/bb/Repo/ecommerce-platform/services/clickstream/backend/tests
./run_e2e_tests.sh
```

Configuration via environment variables:
```bash
K8S_NAMESPACE=ecommerce-platform \
LOCAL_PORT=8000 \
./run_e2e_tests.sh
```

#### Option 2: Manual Port Forwarding

1. Set up port forwarding to the service:
```bash
kubectl port-forward svc/clickstream-backend 8000:8000 -n ecommerce-platform
```

2. In another terminal, run the e2e tests:
```bash
cd /home/bb/Repo/ecommerce-platform/services/clickstream/backend
export RUN_E2E_TESTS=true
export CLICKSTREAM_BASE_URL=http://localhost:8000
pytest tests/test_e2e.py -v
```

#### Option 3: Against Remote Service

Test against a service with ingress or NodePort:

```bash
cd /home/bb/Repo/ecommerce-platform/services/clickstream/backend
export RUN_E2E_TESTS=true
export CLICKSTREAM_BASE_URL=http://clickstream.example.com
pytest tests/test_e2e.py -v
```

### All Tests

Run all tests (unit + e2e):

```bash
cd /home/bb/Repo/ecommerce-platform/services/clickstream/backend
export RUN_E2E_TESTS=true
export CLICKSTREAM_BASE_URL=http://localhost:8000
pytest tests/ -v
```

### Data Generation Tests

**Unit tests (mocked, safe to run):**
```bash
cd /home/bb/Repo/ecommerce-platform/services/clickstream/backend
pytest tests/test_data_generation.py -v
```

**E2E tests (validates endpoint structure, doesn't trigger):**
```bash
export RUN_E2E_TESTS=true
export CLICKSTREAM_BASE_URL=http://localhost:8000
pytest tests/test_e2e.py::TestDataEndpoints -v
```

**Manual tests (actually triggers data generation - SLOW):**
```bash
# These are skipped by default - run only when needed
export RUN_E2E_TESTS=true
export RUN_MANUAL_TESTS=true
pytest tests/test_data_generation_manual.py -v

# Or use the --run-manual flag
pytest tests/test_data_generation_manual.py -v --run-manual
```

⚠️ **Warning:** Manual data generation tests:
- Take several minutes to complete
- Actually generate and upload data to MinIO
- Should only be run in test/dev environments
- Require the data generation script to be available

## Test Coverage

Generate test coverage report (requires `pytest-cov` to be installed):

```bash
cd /home/bb/Repo/ecommerce-platform/services/clickstream/backend

# Install pytest-cov if not already installed
pip install pytest-cov

# Run tests with coverage
pytest tests/ --cov=app --cov-report=html --cov-report=term
```

View the HTML coverage report:
```bash
open htmlcov/index.html
```

**Note:** Coverage tools are optional. Tests will run without them.

## Configuration

### Environment Variables

- `RUN_E2E_TESTS` - Set to `true` to enable e2e tests (default: `false`)
- `CLICKSTREAM_BASE_URL` - Base URL of the service for e2e tests (default: `http://localhost:8000`)
- `K8S_NAMESPACE` - Kubernetes namespace where service is deployed (default: `ecommerce-platform`)

### Pytest Configuration

Test configuration is defined in `pytest.ini`:
- Test discovery patterns
- Coverage settings
- Logging configuration
- Test markers

## Continuous Integration

For CI/CD pipelines:

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-test.txt

# Run unit tests
pytest tests/test_health.py tests/test_api.py -v --junitxml=test-results.xml

# Run e2e tests (requires deployed service)
export RUN_E2E_TESTS=true
export CLICKSTREAM_BASE_URL=http://clickstream-backend:8000
pytest tests/test_e2e.py -v --junitxml=e2e-test-results.xml
```

## Test Structure

```
tests/
├── __init__.py              # Test package initialization
├── conftest.py              # Pytest fixtures and configuration
├── test_health.py           # Health endpoint tests
├── test_api.py              # API endpoint tests
├── test_e2e.py              # End-to-end tests
├── run_e2e_tests.sh         # E2E test runner script
└── README.md                # This file
```

## Writing New Tests

### Unit Test Example

```python
from fastapi.testclient import TestClient

def test_my_endpoint(client: TestClient):
    """Test description."""
    response = client.get("/api/v1/my-endpoint")
    assert response.status_code == 200
    assert response.json()["key"] == "value"
```

### E2E Test Example

```python
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E_TESTS", "false").lower() != "true",
    reason="E2E tests require RUN_E2E_TESTS=true",
)

def test_my_e2e_scenario(e2e_client):
    """Test description."""
    response = e2e_client.get("/api/v1/my-endpoint")
    assert response.status_code == 200
```

## Troubleshooting

### Port Already in Use
If port 8000 is already in use, specify a different port:
```bash
LOCAL_PORT=8001 ./run_e2e_tests.sh
```

### Service Not Found
Ensure the service is deployed:
```bash
kubectl get svc clickstream-backend -n ecommerce-platform
```

### Connection Refused
Check if port forwarding is working:
```bash
curl http://localhost:8000/api/v1/health/live
```

### Test Failures
Check service logs:
```bash
kubectl logs -l app=clickstream,component=backend -n ecommerce-platform
```

## CI/CD Integration Examples

### GitHub Actions

```yaml
- name: Run Unit Tests
  run: |
    pip install -r requirements.txt -r requirements-test.txt
    pytest tests/test_health.py tests/test_api.py -v

- name: Run E2E Tests
  run: |
    kubectl port-forward svc/clickstream-backend 8000:8000 &
    sleep 5
    export RUN_E2E_TESTS=true
    pytest tests/test_e2e.py -v
```

### GitLab CI

```yaml
test:unit:
  script:
    - pip install -r requirements.txt -r requirements-test.txt
    - pytest tests/test_health.py tests/test_api.py -v

test:e2e:
  script:
    - kubectl port-forward svc/clickstream-backend 8000:8000 &
    - sleep 5
    - export RUN_E2E_TESTS=true
    - pytest tests/test_e2e.py -v
```

