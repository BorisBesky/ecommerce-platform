# Clickstream Service - Testing & Validation Guide

This document describes the testing and validation setup for the clickstream analytics service.

## Overview

The clickstream service includes comprehensive testing at multiple levels:

1. **Unit Tests** - Test individual components in isolation
2. **End-to-End (E2E) Tests** - Test the complete deployed service
3. **Deployment Validation** - Verify Kubernetes deployment health

## Quick Start

### Run All Validations

```bash
# From the project root
make validate-clickstream
```

This will:
- Check Kubernetes deployments and services
- Verify pod health
- Test service connectivity
- Run e2e tests against the deployed service

### Run Unit Tests Only

```bash
make test-clickstream-unit
```

### Run All Tests (Unit + E2E)

```bash
make test-clickstream
```

## Detailed Testing Guide

### 1. Unit Tests

Unit tests verify individual components without external dependencies.

**Location:** `services/clickstream/backend/tests/`

**Test Files:**
- `test_health.py` - Health endpoint tests
- `test_api.py` - API endpoint tests with mocked dependencies

**Run unit tests:**
```bash
cd services/clickstream/backend
pytest tests/test_health.py tests/test_api.py -v
```

**With coverage:**
```bash
cd services/clickstream/backend
pytest tests/ --cov=app --cov-report=html --cov-report=term
```

### 2. End-to-End Tests

E2E tests verify the complete service deployment in Kubernetes.

**Location:** `services/clickstream/backend/tests/test_e2e.py`

**Prerequisites:**
- Service must be deployed to Kubernetes
- kubectl must be configured
- Python and pytest installed

**Run e2e tests:**

Option 1: Using the automated script (recommended)
```bash
cd services/clickstream/backend/tests
./run_e2e_tests.sh
```

Option 2: Manual setup
```bash
# Terminal 1: Setup port forwarding
kubectl port-forward svc/clickstream-backend 8000:8000 -n ecommerce-platform

# Terminal 2: Run tests
cd services/clickstream/backend
export RUN_E2E_TESTS=true
export CLICKSTREAM_BASE_URL=http://localhost:8000
pytest tests/test_e2e.py -v
```

**Test Coverage:**

E2E tests verify:
- ✅ Health endpoints (liveness, readiness)
- ✅ API documentation (Swagger, ReDoc, OpenAPI spec)
- ✅ Analytics endpoints (fraud, recommendations)
- ✅ Ray job management endpoints
- ✅ Data generation endpoints
- ✅ Service connectivity and response times
- ✅ CORS configuration
- ✅ Error handling
- ✅ Deployment health

### 3. Deployment Validation

Validates the Kubernetes deployment of the clickstream service.

**Script:** `k8s/validate-clickstream.sh`

**What it checks:**
- Prerequisites (kubectl, cluster connectivity, namespace)
- Deployment status (backend, frontend)
- Service availability
- Pod health
- ConfigMaps and Secrets
- Service connectivity
- Runs e2e tests

**Run validation:**
```bash
# From project root
./k8s/validate-clickstream.sh

# Or via Makefile
make validate-clickstream
```

**Configuration:**
```bash
# Custom namespace
K8S_NAMESPACE=my-namespace ./k8s/validate-clickstream.sh

# Custom port for testing
LOCAL_PORT=8001 ./k8s/validate-clickstream.sh

# Skip e2e tests
RUN_E2E_TESTS=false ./k8s/validate-clickstream.sh
```

### 4. Integration with Main Validation

The clickstream validation is also integrated into the main platform validation script.

**Run full platform validation:**
```bash
./k8s/validate-deployment.sh
```

This checks all platform services including clickstream.

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Clickstream Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r services/clickstream/backend/requirements.txt
          pip install -r services/clickstream/backend/requirements-test.txt
      - name: Run unit tests
        run: make test-clickstream-unit

  e2e-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v3
      - name: Setup Kubernetes
        uses: engineerd/setup-kind@v0.5.0
      - name: Deploy service
        run: |
          make build-clickstream-images
          make deploy-all
      - name: Run e2e tests
        run: make validate-clickstream
```

### GitLab CI Example

```yaml
unit-tests:
  stage: test
  script:
    - pip install -r services/clickstream/backend/requirements.txt
    - pip install -r services/clickstream/backend/requirements-test.txt
    - make test-clickstream-unit

e2e-tests:
  stage: test
  dependencies:
    - unit-tests
  script:
    - kubectl config use-context $KUBE_CONTEXT
    - make validate-clickstream
```

## Test Configuration

### Environment Variables

**For E2E Tests:**
- `RUN_E2E_TESTS` - Set to `true` to enable e2e tests (default: `false`)
- `CLICKSTREAM_BASE_URL` - Base URL of the service (default: `http://localhost:8000`)
- `K8S_NAMESPACE` - Kubernetes namespace (default: `ecommerce-platform`)
- `LOCAL_PORT` - Local port for port forwarding (default: `8000`)

**For Unit Tests:**
- Standard pytest environment variables

### Pytest Configuration

Configuration is defined in `services/clickstream/backend/pytest.ini`:

```ini
[pytest]
testpaths = tests
markers =
    unit: Unit tests
    e2e: End-to-end tests
    integration: Integration tests
```

## Troubleshooting

### Port Already in Use

```bash
# Use a different port
LOCAL_PORT=8001 make validate-clickstream
```

### Service Not Responding

```bash
# Check service status
kubectl get svc clickstream-backend -n ecommerce-platform

# Check pod logs
kubectl logs -l app=clickstream,component=backend -n ecommerce-platform

# Check pod status
kubectl get pods -l app=clickstream -n ecommerce-platform
```

### E2E Tests Timing Out

```bash
# Check if port forwarding is working
curl http://localhost:8000/api/v1/health/live

# Restart port forwarding
kubectl port-forward svc/clickstream-backend 8000:8000 -n ecommerce-platform
```

### pytest Not Found

```bash
# Install test dependencies
pip install -r services/clickstream/backend/requirements-test.txt
```

### Import Errors

```bash
# Make sure you're in the correct directory
cd services/clickstream/backend

# Install app dependencies
pip install -r requirements.txt
```

## Best Practices

### Writing New Tests

1. **Unit tests** should:
   - Be fast (< 100ms per test)
   - Not require external services
   - Mock external dependencies
   - Test single units of functionality

2. **E2E tests** should:
   - Test complete user workflows
   - Verify integration points
   - Be marked with `@pytest.mark.skipif` to run conditionally
   - Have clear assertions with helpful error messages

### Test Organization

```
tests/
├── __init__.py              # Package initialization
├── conftest.py              # Fixtures and configuration
├── test_health.py           # Health endpoint tests
├── test_api.py              # API tests with mocks
├── test_e2e.py              # End-to-end tests
├── run_e2e_tests.sh         # E2E test runner
└── README.md                # Test documentation
```

### Continuous Testing

Run tests frequently during development:

```bash
# Watch mode (requires pytest-watch)
cd services/clickstream/backend
ptw tests/

# Or use a file watcher
find services/clickstream/backend/app -name "*.py" | entr -c pytest tests/test_health.py -v
```

## Makefile Targets Summary

| Target | Description |
|--------|-------------|
| `make validate-clickstream` | Run full validation (deployment + e2e tests) |
| `make test-clickstream-unit` | Run unit tests only |
| `make test-clickstream` | Run all tests (unit + e2e) |
| `make clickstream-portforward` | Setup port forwarding for manual testing |

## Additional Resources

- [Test README](services/clickstream/backend/tests/README.md) - Detailed test documentation
- [Service README](services/clickstream/backend/README.md) - Service overview
- [Deployment README](k8s/clickstream-service/README.md) - Deployment instructions

## Summary

The clickstream service has comprehensive testing at multiple levels:

- ✅ **Unit tests** verify individual components
- ✅ **E2E tests** verify complete service functionality
- ✅ **Deployment validation** verifies Kubernetes health
- ✅ **Automated scripts** simplify testing workflow
- ✅ **Makefile targets** provide convenient commands
- ✅ **CI/CD ready** with examples for popular platforms

Run `make validate-clickstream` to validate your deployment!

