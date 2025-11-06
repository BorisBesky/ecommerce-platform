# Manual Data Generation Test Implementation

## Overview

Implemented comprehensive manual tests for the data generation endpoint (`/api/v1/data/generate`). These tests are **intentionally slow** and **disabled by default** because they:

1. Actually trigger data generation (takes several minutes)
2. Generate and upload real data to MinIO
3. Require external service dependencies
4. Should only be run in test/dev environments

## Tests Implemented

### 1. `test_trigger_data_generation_streaming` ✅

**Status:** Already implemented, now working

**What it tests:**
- Triggers actual data generation via POST to `/api/v1/data/generate`
- Verifies streaming response works correctly
- Monitors output chunks and progress
- Validates response status and content type
- Ensures substantial output is received

**Duration:** ~2-5 minutes

### 2. `test_data_generation_creates_data` ✅ NEW

**Status:** Fully implemented

**What it tests:**
- Lists existing files in MinIO before generation
- Triggers data generation
- Waits for completion
- Verifies new files were created in MinIO
- Checks file sizes are reasonable (> 100 bytes each, > 1KB total)
- Handles cases where data already exists

**Key Features:**
- Uses boto3 to connect to MinIO
- Compares before/after file lists
- Provides detailed output showing created files
- Handles bucket creation gracefully

**Duration:** ~2-5 minutes + 2s for MinIO sync

### 3. `test_concurrent_data_generation_requests` ✅ NEW

**Status:** Fully implemented

**What it tests:**
- Sends 3 concurrent POST requests to the endpoint
- Verifies the service handles concurrency gracefully
- Tests for race conditions
- Validates error handling for concurrent requests

**Acceptable Behaviors:**
- All 3 succeed (parallel execution supported)
- 1+ succeeds, others timeout (sequential execution)
- All return appropriate error codes (409/503/429)

**What it validates:**
- No server crashes (no 5xx except 503)
- Proper error codes for resource conflicts
- System stability under concurrent load

**Duration:** ~10-30 seconds (uses short 10s timeout)

### 4. `test_data_generation_performance` ✅ NEW

**Status:** Fully implemented

**What it tests:**
- Measures time to first byte (TTFB)
- Tracks total generation time
- Calculates throughput and streaming rate
- Monitors chunk delay statistics

**Performance Thresholds:**
- Total time < 10 minutes (600s)
- Time to first byte < 5 seconds
- Minimum output > 1KB
- Average chunk delay < 1 second

**Metrics Reported:**
- Total time
- Bytes received (MB)
- Number of chunks
- Average throughput (KB/s)
- Average and max chunk delays

**Duration:** ~2-5 minutes

### 5. `test_data_generation_with_custom_parameters` ⏭️ SKIPPED

**Status:** Documented but skipped (endpoint doesn't support parameters yet)

**Why skipped:**
The current `/api/v1/data/generate` endpoint doesn't accept parameters.

**Future Implementation:**
When parameters are added to the endpoint, this test can be enabled to verify:
- Custom num_users, num_products, num_events
- Random seed for reproducibility
- Output format options
- Skip upload flag

**Documentation included:** 
- Clear skip message explaining why
- Example implementation (commented out)
- Instructions for enabling when parameters are added

## Running the Tests

### Run All Manual Tests

```bash
# Via Makefile (with confirmation prompt)
make test-clickstream-data-manual

# Direct via script
cd services/clickstream/backend
RUN_MANUAL_TESTS=true ./tests/run_e2e_tests.sh tests/test_data_generation_manual.py
```

### Run Specific Tests

```bash
cd services/clickstream/backend

# Just the streaming test
RUN_MANUAL_TESTS=true pytest tests/test_data_generation_manual.py::TestDataGenerationManual::test_trigger_data_generation_streaming -v

# Just the MinIO verification test
RUN_MANUAL_TESTS=true pytest tests/test_data_generation_manual.py::TestDataGenerationManual::test_data_generation_creates_data -v

# Just the concurrent test
RUN_MANUAL_TESTS=true pytest tests/test_data_generation_manual.py::TestDataGenerationManual::test_concurrent_data_generation_requests -v

# Just the performance test
RUN_MANUAL_TESTS=true pytest tests/test_data_generation_manual.py::test_data_generation_performance -v
```

## Requirements

### Environment Variables

These must be set (or service must be accessible):

```bash
MINIO_ENDPOINT=http://localhost:9000          # MinIO endpoint
MINIO_ACCESS_KEY=minioadmin                    # MinIO access key
MINIO_SECRET_KEY=minioadmin                    # MinIO secret key
MINIO_BUCKET=analytics                         # Target bucket
CLICKSTREAM_BASE_URL=http://localhost:8000     # Service URL
RUN_MANUAL_TESTS=true                          # Enable manual tests
```

### Dependencies

- `boto3` - For MinIO access (already in requirements.txt)
- `httpx` - For streaming requests (already in requirements.txt)
- Port forwarding to service (handled by `run_e2e_tests.sh`)

### External Services

1. **MinIO** - Must be accessible for data verification test
2. **Clickstream Service** - Must be deployed and running
3. **Port Forwarding** - Handled automatically by test script

## New Fixture

### `minio_client`

A pytest fixture that provides a configured boto3 S3 client for MinIO:

```python
@pytest.fixture
def minio_client() -> Generator[boto3.client, None, None]:
    """Create a MinIO client for verifying data upload."""
    # Configured from environment variables
    # Handles both k8s internal and localhost endpoints
```

Used by: `test_data_generation_creates_data`

## Test Markers

All tests use these pytest markers:

- `@pytest.mark.manual` - Indicates manual/long-running test
- `@pytest.mark.slow` - Indicates slow execution (minutes)

These markers are registered in `pytest.ini`:

```ini
markers =
    manual: Manual tests that require explicit enabling
    slow: Slow tests that take significant time to complete
```

## Success Criteria

### For `test_data_generation_creates_data`:
✅ At least 1 file created in MinIO  
✅ Total data size > 1KB  
✅ Files have reasonable sizes (> 100 bytes)  
✅ No MinIO access errors

### For `test_concurrent_data_generation_requests`:
✅ No server crashes (5xx errors except 503)  
✅ At least 1 request succeeds OR all return proper error codes  
✅ System remains stable under concurrent load

### For `test_data_generation_performance`:
✅ Total time < 10 minutes  
✅ Time to first byte < 5 seconds  
✅ Output > 1KB  
✅ Average chunk delay < 1 second

## Troubleshooting

### "Server disconnected without sending a response"

**Cause:** Port forwarding not set up  
**Solution:** Use `run_e2e_tests.sh` script or set up manual port forward

### "Error accessing MinIO: NoSuchBucket"

**Cause:** Bucket doesn't exist yet  
**Solution:** This is expected on first run; bucket will be created during generation

### Tests timeout in concurrent test

**Cause:** Expected behavior - service may serialize requests  
**Solution:** Not an error; test validates this behavior is handled gracefully

### Performance thresholds failing

**Cause:** System is slower than expected  
**Solution:** Adjust thresholds in test based on your environment's expected performance

## Future Enhancements

1. **Add parameter support to endpoint:**
   - Implement query/body parameters in `data.py`
   - Enable `test_data_generation_with_custom_parameters`

2. **Add data validation:**
   - Download generated files from MinIO
   - Verify CSV/Parquet format
   - Check data quality and completeness

3. **Add resource monitoring:**
   - Track pod CPU/memory during generation
   - Monitor MinIO storage growth
   - Measure network I/O

4. **Add cleanup tests:**
   - Test deleting generated data
   - Verify bucket cleanup
   - Test regeneration after cleanup

## Related Files

- `test_data_generation_manual.py` - The test file (this implementation)
- `test_data_generation.py` - Unit tests for the endpoint (mocked)
- `test_e2e.py` - E2E tests (fast, no actual data generation)
- `run_e2e_tests.sh` - Test execution script with port forwarding
- `conftest.py` - Shared fixtures
- `pytest.ini` - Pytest configuration and markers

---

**Last Updated:** 2025-11-06  
**Implemented By:** Automated test enhancement  
**Status:** ✅ Ready for use in test/dev environments

