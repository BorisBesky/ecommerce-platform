"""Health and readiness probes for the service."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/live", summary="Liveness probe")
async def live() -> dict[str, str]:
    """Return service liveness status."""

    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def ready() -> dict[str, str]:
    """Return readiness status. Further dependency checks will be added later."""

    return {"status": "ready"}

