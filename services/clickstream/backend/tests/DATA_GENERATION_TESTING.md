# Data Generation Testing

This document describes the comprehensive testing infrastructure for the data generation functionality in the clickstream service.

## Overview

The clickstream service has a `/api/v1/data/generate` endpoint that triggers the generation and upload of test data (users, products, and clickstream events). Testing this functionality requires multiple approaches:

1. **Unit Tests** - Test endpoint structure with mocked execution
2. **E2E Tests** - Validate endpoint configuration without triggering
3. **Manual Tests** - Actually trigger data generation (optional, long-running)

## Test Files

### 1. `test_data_generation.py` - Unit Tests

**Purpose:** Test the data generation endpoint structure and behavior with mocked subprocess execution.

**What it tests:**
- ✅ Endpoint is registered in the API
- ✅ Endpoint is a POST endpoint
- ✅ Proper HTTP methods (POST allowed, GET rejected)
- ✅ Endpoint metadata (tags, summary, responses)
- ✅ Subprocess execution with mocked process
- ✅ Settings dependency injection

**Run it:**
```bash
pytest tests/test_data_generation.py -v
```

**Safe to run:** ✅ Yes - uses mocks, no actual data generation

### 2. `test_e2e.py::TestDataEndpoints` - E2E Tests

**Purpose:** Validate the data generation endpoint in a deployed service without actually triggering it.

**What it tests:**
- ✅ Endpoint exists (supports both `/api/v1/data/generate` and `/api/v1/simulations`)
- ✅ Correct HTTP method (POST)
- ✅ GET returns 405 Method Not Allowed
- ✅ Proper metadata and tags

**Run it:**
```bash
export RUN_E2E_TESTS=true
export CLICKSTREAM_BASE_URL=http://localhost:8000
pytest tests/test_e2e.py::TestDataEndpoints -v
```

**Safe to run:** ✅ Yes - only checks structure, doesn't trigger generation

### 3. `test_data_generation_manual.py` - Manual Tests

**Purpose:** Actually trigger data generation and verify the complete workflow.

**What it tests:**
- ⚠️ Actual data generation execution
- ⚠️ Streaming response handling
- ⚠️ Data upload to MinIO
- ⚠️ Process completion and output
- ⚠️ Performance characteristics

**Run it:**
```bash
# Option 1: Environment variable
export RUN_E2E_TESTS=true
export RUN_MANUAL_TESTS=true
pytest tests/test_data_generation_manual.py -v

# Option 2: Command-line flag
pytest tests/test_data_generation_manual.py -v --run-manual
```

**Safe to run:** ⚠️ **NO** - Takes minutes, generates real data, uploads to MinIO

## Data Generation Endpoint Details

### Endpoint: `POST /api/v1/data/generate`

**Function:** Triggers the unified data generation script (`tools/generate_data.py`)

**Behavior:**
- Runs data generation subprocess
- Streams output back to client in real-time
- Uploads generated data to MinIO
- Returns exit code information

**Request:**
```bash
POST /api/v1/data/generate
```

**Response:**
- Status: `200 OK`
- Content-Type: `text/plain`
- Body: Streaming output from generation script

**Example output:**
```
--- STDOUT ---
Generating users...
Generated 1000 users
Generating products...
Generated 500 products
Generating clickstream...
Generated 10000 events
Uploading to MinIO...
Upload complete

--- STDERR ---
```

## Test Coverage

### Current Coverage

**Unit Tests:** ✅ Complete
- Endpoint registration ✅
- HTTP methods ✅
- OpenAPI spec ✅
- Mocked execution ✅

**E2E Tests:** ✅ Complete
- Endpoint availability ✅
- Method validation ✅
- Metadata validation ✅
- Backward compatibility ✅

**Integration Tests:** ⚠️ Optional (Manual)
- Actual execution ⚠️
- Streaming response ⚠️
- Data validation ⚠️
- Performance ⚠️

## Running Tests

### Quick Test (Safe)

```bash
# Run all safe data generation tests
cd services/clickstream/backend
pytest tests/test_data_generation.py tests/test_e2e.py::TestDataEndpoints -v
```

### Full Validation (Including Manual - SLOW)

```bash
# This will actually generate data!
cd services/clickstream/backend
export RUN_E2E_TESTS=true
export RUN_MANUAL_TESTS=true
pytest tests/test_data_generation*.py -v
```

### In CI/CD Pipeline

```yaml
# Safe tests only (recommended for CI)
- name: Test Data Generation
  run: |
    cd services/clickstream/backend
    pytest tests/test_data_generation.py -v

# Include e2e if service is deployed
- name: Test Data Generation E2E
  run: |
    export RUN_E2E_TESTS=true
    export CLICKSTREAM_BASE_URL=http://clickstream-backend:8000
    pytest tests/test_e2e.py::TestDataEndpoints -v
```

## Test Scenarios

### Scenario 1: Development Testing

**Goal:** Verify endpoint structure during development

**Run:**
```bash
pytest tests/test_data_generation.py -v
```

**Expected result:** All tests pass, no data generated

### Scenario 2: Deployment Validation

**Goal:** Verify deployed service has data generation capability

**Run:**
```bash
export RUN_E2E_TESTS=true
pytest tests/test_e2e.py::TestDataEndpoints -v
```

**Expected result:** All tests pass, endpoint accessible

### Scenario 3: Full Integration Test

**Goal:** Actually test data generation works end-to-end

**Run:**
```bash
export RUN_E2E_TESTS=true
export RUN_MANUAL_TESTS=true
pytest tests/test_data_generation_manual.py::TestDataGenerationManual::test_trigger_data_generation_streaming -v
```

**Expected result:** Data generated, uploaded to MinIO, streaming output received

**Duration:** 2-5 minutes depending on data size

## Troubleshooting

### Test fails: "Data generation endpoint not found"

**Cause:** Deployed service doesn't have the `/api/v1/data/generate` endpoint

**Solution:** Service might be using older `/api/v1/simulations` endpoint. Tests handle both versions automatically.

### Manual test fails: "Script not found"

**Cause:** `tools/generate_data.py` script not accessible from service

**Solution:** Ensure the script is in the correct location or deployed with the service

### Streaming response test fails

**Cause:** Client might not support streaming properly

**Solution:** Check `httpx` version and streaming configuration in conftest.py

### Data generation times out

**Cause:** Generation takes longer than expected

**Solution:** Increase timeout in manual tests or reduce data volume

## Best Practices

### 1. Run Unit Tests Frequently
```bash
# Fast, safe, no side effects
pytest tests/test_data_generation.py -v
```

### 2. Run E2E Tests After Deployment
```bash
# Validates deployed service
make validate-clickstream
```

### 3. Run Manual Tests Rarely
```bash
# Only when you need to verify actual generation
# In test/dev environment only
export RUN_MANUAL_TESTS=true
pytest tests/test_data_generation_manual.py -v
```

### 4. Never Run Manual Tests in Production
⚠️ Manual tests generate real data and can:
- Fill up storage
- Overwrite existing data
- Cause performance issues
- Trigger alerts/monitoring

## Future Enhancements

Potential improvements to data generation testing:

1. **Parameterized tests** - Test with different data volumes
2. **Cleanup verification** - Ensure data can be cleaned up after test
3. **Performance benchmarks** - Track generation speed over time
4. **Resource monitoring** - Track memory/CPU usage during generation
5. **Concurrent generation** - Test multiple simultaneous requests
6. **Custom parameters** - Test generation with custom configuration

## Summary

| Test Type | File | Safe | Fast | Coverage |
|-----------|------|------|------|----------|
| Unit | `test_data_generation.py` | ✅ Yes | ✅ Yes | Structure, mocked execution |
| E2E | `test_e2e.py` | ✅ Yes | ✅ Yes | Endpoint availability, methods |
| Manual | `test_data_generation_manual.py` | ⚠️ No | ❌ No | Actual execution, streaming |

**Recommendation:** Run unit and e2e tests regularly. Run manual tests only when needed in test environments.

