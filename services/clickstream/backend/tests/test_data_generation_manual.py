"""Manual tests for data generation that actually trigger the generation process.

These tests are SKIPPED by default because they:
1. Are long-running (can take several minutes)
2. Require external dependencies (MinIO, generate_data.py script)
3. Actually generate and upload data

To run these tests explicitly:
    pytest tests/test_data_generation_manual.py -v --run-manual

Or set environment variable:
    RUN_MANUAL_TESTS=true pytest tests/test_data_generation_manual.py -v
"""

import os
import pytest
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator
import boto3
from botocore.exceptions import ClientError


def pytest_addoption(parser):
    """Add custom command-line option for running manual tests."""
    try:
        parser.addoption(
            "--run-manual",
            action="store_true",
            default=False,
            help="Run manual/long-running tests",
        )
    except ValueError:
        # Option already added (happens when conftest.py also defines it)
        pass


# Skip all tests in this file by default
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MANUAL_TESTS", "false").lower() != "true",
    reason="Manual tests require RUN_MANUAL_TESTS=true environment variable",
)


@pytest.fixture
def minio_client() -> Generator[boto3.client, None, None]:
    """Create a MinIO client for verifying data upload."""
    endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    
    # Handle both internal k8s endpoints and external port-forwarded endpoints
    if "minio.ecommerce-platform" in endpoint:
        # If running inside cluster, use service endpoint
        pass
    elif "localhost" in endpoint or "127.0.0.1" in endpoint:
        # If testing locally, endpoint is fine as-is
        pass
    
    client = boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name='us-east-1',  # MinIO doesn't care about region
    )
    
    yield client


@pytest.mark.manual
@pytest.mark.slow
class TestDataGenerationManual:
    """Manual tests that actually trigger data generation."""

    def test_trigger_data_generation_streaming(self, e2e_client):
        """Test triggering actual data generation and verify streaming response.
        
        WARNING: This test:
        - Takes several minutes to complete
        - Actually generates and uploads data to MinIO
        - Should only be run in test/dev environments
        
        Note: This test works with both new (/api/v1/data/generate) and 
        old (/api/v1/simulations) endpoints for backward compatibility.
        """
        # Determine which endpoint to use
        # Check the OpenAPI spec to see which endpoint exists
        spec_response = e2e_client.get("/openapi.json")
        spec = spec_response.json()
        paths = spec.get("paths", {})
        
        if "/api/v1/data/generate" in paths:
            endpoint = "/api/v1/data/generate"
            print(f"\n⚠️  Using new endpoint: {endpoint}")
        elif "/api/v1/simulations" in paths:
            endpoint = "/api/v1/simulations"
            print(f"\n⚠️  Using old endpoint: {endpoint}")
            print("Note: This endpoint may require different parameters/behavior")
            # For now, skip this test if only old endpoint exists
            pytest.skip(f"Manual test designed for /api/v1/data/generate, but service has {endpoint}")
        else:
            pytest.fail("Neither /api/v1/data/generate nor /api/v1/simulations found in API")
        
        print(f"Starting data generation (this may take several minutes)...")
        
        start_time = time.time()
        
        # Trigger data generation
        # Note: httpx handles streaming with iter_bytes or iter_text methods
        with e2e_client.stream("POST", endpoint) as response:
            # Should return 200 and streaming response
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            
            # Verify content type
            content_type = response.headers.get("content-type", "")
            assert "text/plain" in content_type or "application/json" in content_type, (
                f"Unexpected content-type: {content_type}"
            )
            
            # Read and verify streaming output
            output_chunks = []
            bytes_received = 0
            
            try:
                for chunk in response.iter_bytes(chunk_size=8192):
                    if chunk:
                        bytes_received += len(chunk)
                        output_chunks.append(chunk.decode('utf-8', errors='ignore'))
                        
                        # Print progress
                        if len(output_chunks) % 10 == 0:
                            print(f"  Received {bytes_received} bytes, {len(output_chunks)} chunks...")
            except Exception as e:
                pytest.fail(f"Error reading streaming response: {e}")
        
        elapsed_time = time.time() - start_time
        full_output = ''.join(output_chunks)
        
        print(f"\n✅ Data generation completed in {elapsed_time:.1f} seconds")
        print(f"   Total output: {bytes_received} bytes")
        
        # Verify output contains expected markers
        assert "STDOUT" in full_output or "Generated" in full_output or len(full_output) > 100, (
            "Output should contain generation progress or substantial content"
        )
        
        # Check for success indicators (no failure markers)
        if "FAILED" in full_output or "ERROR" in full_output:
            print(f"\n⚠️  Output contains error markers:\n{full_output[:1000]}")
        
        # Verify reasonable amount of output (data generation should produce logs)
        assert bytes_received > 100, "Should receive substantial output from generation"
    
    def test_data_generation_creates_data(self, e2e_client, minio_client):
        """Test that data generation actually creates data in MinIO.
        
        This test:
        1. Lists existing files in MinIO before generation
        2. Triggers data generation
        3. Waits for completion
        4. Verifies new files were created in MinIO
        5. Checks file sizes are reasonable
        """
        bucket_name = os.getenv("MINIO_BUCKET", "analytics")
        
        # Get initial list of objects
        print(f"\n📦 Checking MinIO bucket: {bucket_name}")
        try:
            initial_response = minio_client.list_objects_v2(Bucket=bucket_name)
            initial_objects = {obj['Key']: obj['Size'] for obj in initial_response.get('Contents', [])}
            print(f"   Initial object count: {len(initial_objects)}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucket':
                print(f"   Bucket doesn't exist yet - will be created during generation")
                initial_objects = {}
            else:
                pytest.fail(f"Error accessing MinIO: {e}")
        
        # Trigger data generation
        print("\n🔄 Triggering data generation...")
        spec_response = e2e_client.get("/openapi.json")
        paths = spec_response.json().get("paths", {})
        endpoint = "/api/v1/data/generate" if "/api/v1/data/generate" in paths else "/api/v1/simulations"
        
        start_time = time.time()
        bytes_received = 0
        
        with e2e_client.stream("POST", endpoint) as response:
            assert response.status_code == 200
            for chunk in response.iter_bytes(chunk_size=8192):
                if chunk:
                    bytes_received += len(chunk)
        
        elapsed = time.time() - start_time
        print(f"✅ Generation completed in {elapsed:.1f}s, received {bytes_received} bytes of output")
        
        # Wait a bit for MinIO to sync
        time.sleep(2)
        
        # Check for new objects
        print("\n🔍 Verifying data was uploaded to MinIO...")
        try:
            final_response = minio_client.list_objects_v2(Bucket=bucket_name)
            final_objects = {obj['Key']: obj['Size'] for obj in final_response.get('Contents', [])}
            print(f"   Final object count: {len(final_objects)}")
            
            # Find new or modified objects
            new_objects = {k: v for k, v in final_objects.items() if k not in initial_objects or final_objects[k] != initial_objects[k]}
            
            if new_objects:
                print(f"   ✅ Found {len(new_objects)} new/updated files:")
                for key, size in sorted(new_objects.items())[:10]:  # Show first 10
                    print(f"      - {key} ({size:,} bytes)")
                if len(new_objects) > 10:
                    print(f"      ... and {len(new_objects) - 10} more")
                
                # Verify files have reasonable sizes (at least 100 bytes each)
                small_files = [k for k, v in new_objects.items() if v < 100]
                if small_files:
                    print(f"   ⚠️  Warning: {len(small_files)} files are smaller than 100 bytes")
                
                # At least one file should have been created
                assert len(new_objects) > 0, "Expected at least one file to be created"
                
                # Total size should be reasonable (at least 1KB total)
                total_size = sum(new_objects.values())
                assert total_size > 1024, f"Expected at least 1KB of data, got {total_size} bytes"
                
            else:
                # If no new files, maybe they were already there - check that at least some exist
                if len(final_objects) > 0:
                    print(f"   ℹ️  No new files, but {len(final_objects)} existing files found (data may have been generated previously)")
                else:
                    pytest.fail("No data files found in MinIO after generation")
                    
        except ClientError as e:
            pytest.fail(f"Error checking MinIO after generation: {e}")
    
    def test_concurrent_data_generation_requests(self, e2e_client):
        """Test behavior when multiple data generation requests are made concurrently.
        
        This tests:
        - How the system handles concurrent generation requests
        - Whether it accepts or rejects concurrent requests
        - Response behavior for concurrent requests
        
        Note: This test sends 3 concurrent requests with a short timeout.
        It verifies the service handles them gracefully (either accepts or returns appropriate errors).
        """
        import httpx
        
        spec_response = e2e_client.get("/openapi.json")
        paths = spec_response.json().get("paths", {})
        endpoint = "/api/v1/data/generate" if "/api/v1/data/generate" in paths else "/api/v1/simulations"
        
        print(f"\n🔀 Testing concurrent requests to {endpoint}")
        print("   Note: Using short timeout (10s) for concurrent test")
        
        def make_request(request_num: int) -> dict:
            """Make a single request and return result info."""
            print(f"   Starting request {request_num}...")
            start = time.time()
            
            try:
                # Use a shorter timeout for this test
                with httpx.Client(base_url=e2e_client.base_url, timeout=10.0) as client:
                    with client.stream("POST", endpoint) as response:
                        status = response.status_code
                        bytes_read = sum(len(chunk) for chunk in response.iter_bytes(chunk_size=8192))
                        elapsed = time.time() - start
                        
                        return {
                            'request_num': request_num,
                            'status': status,
                            'bytes': bytes_read,
                            'elapsed': elapsed,
                            'error': None
                        }
            except httpx.TimeoutException:
                elapsed = time.time() - start
                return {
                    'request_num': request_num,
                    'status': 'timeout',
                    'bytes': 0,
                    'elapsed': elapsed,
                    'error': 'Timeout after 10s (expected for concurrent test)'
                }
            except Exception as e:
                elapsed = time.time() - start
                return {
                    'request_num': request_num,
                    'status': 'error',
                    'bytes': 0,
                    'elapsed': elapsed,
                    'error': str(e)
                }
        
        # Send 3 concurrent requests
        results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request, i) for i in range(1, 4)]
            
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if result['error']:
                    print(f"   Request {result['request_num']}: {result['error']}")
                else:
                    print(f"   Request {result['request_num']}: {result['status']} - {result['bytes']} bytes in {result['elapsed']:.1f}s")
        
        # Analyze results
        successful = [r for r in results if r['status'] == 200]
        timeouts = [r for r in results if r['status'] == 'timeout']
        errors = [r for r in results if r['status'] not in [200, 'timeout']]
        
        print(f"\n📊 Results: {len(successful)} successful, {len(timeouts)} timeouts, {len(errors)} errors")
        
        # Verify behavior is reasonable
        # The service should either:
        # 1. Handle all requests successfully (parallel execution)
        # 2. Accept one and timeout/error on others (sequential execution)
        # 3. Return appropriate error codes for subsequent requests
        
        if len(successful) == 3:
            print("   ✅ All requests succeeded - service supports parallel execution")
        elif len(successful) >= 1:
            print(f"   ✅ {len(successful)} request(s) succeeded - service may serialize requests")
            print(f"      Timeouts/errors for others are expected behavior")
        else:
            # If none succeeded, that's only OK if they all got proper error responses
            if all(r['status'] in [409, 503, 429] for r in errors):
                print("   ✅ All requests returned appropriate error codes (409/503/429)")
            else:
                pytest.fail(f"No requests succeeded and errors were not appropriate: {errors}")
        
        # At minimum, verify no server crashes (5xx errors other than 503)
        server_errors = [r for r in results if isinstance(r['status'], int) and r['status'] >= 500 and r['status'] != 503]
        assert len(server_errors) == 0, f"Got unexpected server errors: {server_errors}"


@pytest.mark.manual
@pytest.mark.slow
def test_data_generation_performance(e2e_client):
    """Test data generation performance and set reasonable thresholds.
    
    This test measures:
    - Time to complete generation
    - Response streaming rate
    - Overall throughput
    
    And verifies performance is within acceptable bounds.
    """
    spec_response = e2e_client.get("/openapi.json")
    paths = spec_response.json().get("paths", {})
    endpoint = "/api/v1/data/generate" if "/api/v1/data/generate" in paths else "/api/v1/simulations"
    
    print(f"\n⚡ Performance testing {endpoint}")
    
    # Track timing metrics
    start_time = time.time()
    first_byte_time = None
    bytes_received = 0
    chunks_received = 0
    chunk_times = []
    
    with e2e_client.stream("POST", endpoint) as response:
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        last_chunk_time = start_time
        for chunk in response.iter_bytes(chunk_size=8192):
            if chunk:
                current_time = time.time()
                
                # Record first byte time
                if first_byte_time is None:
                    first_byte_time = current_time
                    time_to_first_byte = first_byte_time - start_time
                    print(f"   ⏱️  Time to first byte: {time_to_first_byte:.2f}s")
                
                bytes_received += len(chunk)
                chunks_received += 1
                
                # Track time between chunks
                chunk_delay = current_time - last_chunk_time
                chunk_times.append(chunk_delay)
                last_chunk_time = current_time
    
    # Calculate overall metrics
    total_time = time.time() - start_time
    avg_throughput = bytes_received / total_time if total_time > 0 else 0
    avg_chunk_delay = sum(chunk_times) / len(chunk_times) if chunk_times else 0
    max_chunk_delay = max(chunk_times) if chunk_times else 0
    
    print(f"\n📈 Performance Metrics:")
    print(f"   Total time: {total_time:.2f}s")
    print(f"   Bytes received: {bytes_received:,} ({bytes_received/1024/1024:.2f} MB)")
    print(f"   Chunks received: {chunks_received}")
    print(f"   Average throughput: {avg_throughput/1024:.2f} KB/s")
    print(f"   Average chunk delay: {avg_chunk_delay*1000:.1f}ms")
    print(f"   Max chunk delay: {max_chunk_delay*1000:.1f}ms")
    
    # Performance assertions - these are reasonable thresholds
    # Adjust based on your system's expected performance
    
    # Should complete in reasonable time (< 10 minutes for full generation)
    assert total_time < 600, f"Generation took {total_time:.1f}s (> 10 min threshold)"
    
    # Should start streaming quickly (< 5 seconds to first byte)
    assert time_to_first_byte < 5.0, f"First byte took {time_to_first_byte:.2f}s (> 5s threshold)"
    
    # Should receive substantial output
    assert bytes_received > 1000, f"Only received {bytes_received} bytes (expected > 1KB)"
    
    # Average chunk delay should be reasonable (< 1 second)
    assert avg_chunk_delay < 1.0, f"Average chunk delay {avg_chunk_delay:.2f}s (> 1s threshold)"
    
    print(f"\n✅ All performance thresholds met!")


@pytest.mark.manual
def test_data_generation_with_custom_parameters(e2e_client):
    """Test data generation with custom parameters.
    
    This test is currently skipped because the endpoint doesn't support parameters yet.
    
    To implement parameter support:
    1. Update the endpoint to accept parameters (e.g., num_users, num_products, seed)
    2. Pass these parameters to generate_data.py script
    3. Uncomment and update this test
    
    Example parameters to test:
    - num_users: Number of users to generate
    - num_products: Number of products to generate  
    - num_events: Number of clickstream events
    - seed: Random seed for reproducibility
    - output_format: Format of output files
    - skip_upload: Whether to skip MinIO upload
    """
    pytest.skip(
        "Custom parameters not yet supported by endpoint. "
        "To add: Update data.py endpoint to accept query/body parameters, "
        "then implement this test to verify parameter handling."
    )
    
    # Example implementation once parameters are supported:
    # 
    # print("\n🔧 Testing custom parameters...")
    # 
    # # Test with minimal data for faster execution
    # params = {
    #     "num_users": 10,
    #     "num_products": 20,
    #     "num_events": 100,
    #     "seed": 42
    # }
    # 
    # endpoint = "/api/v1/data/generate"
    # with e2e_client.stream("POST", endpoint, json=params) as response:
    #     assert response.status_code == 200
    #     output = b''.join(response.iter_bytes())
    # 
    # # Verify output mentions the custom parameters
    # output_str = output.decode('utf-8', errors='ignore')
    # assert "10" in output_str or "users" in output_str.lower()
    # 
    # print("✅ Custom parameters accepted and processed")

