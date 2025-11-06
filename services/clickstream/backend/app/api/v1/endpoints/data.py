
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import asyncio
import subprocess
from ....core.config import Settings, get_settings

router = APIRouter()

async def run_generation_script(settings: Settings):
    """A generator function that runs the data generation script and yields its output."""
    process = await asyncio.create_subprocess_exec(
        'python', 'tools/generate_data.py', 'all', '--upload',
        '--minio-endpoint', settings.minio_endpoint,
        '--minio-access-key', settings.minio_access_key,
        '--minio-secret-key', settings.minio_secret_key,
        '--minio-bucket', settings.minio_bucket,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    async def stream_output(stream):
        while True:
            line = await stream.readline()
            if not line:
                break
            yield line
    
    yield b"--- STDOUT ---\n"
    async for line in stream_output(process.stdout):
        yield line
        
    yield b"\n--- STDERR ---\n"
    async for line in stream_output(process.stderr):
        yield line

    await process.wait()

    if process.returncode != 0:
        yield f"\n--- PROCESS FAILED WITH EXIT CODE {process.returncode} ---\n".encode('utf-8')


@router.post(
    "/generate",
    summary="Trigger a unified data generation and upload",
    status_code=status.HTTP_200_OK,
)
async def trigger_data_generation(
    settings: Settings = Depends(get_settings),
):
    """
    Triggers the unified data generation script, which generates users, products, and clickstream data,
    and uploads it to MinIO. The output of the script is streamed back to the client.
    """
    return StreamingResponse(run_generation_script(settings), media_type="text/plain")
