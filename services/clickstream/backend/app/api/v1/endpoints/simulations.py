"""Endpoints for managing clickstream simulation runs."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status

from ....core.config import Settings, get_settings
from ....dependencies.services import get_simulator, get_storage_service
from ....models.simulation import (
    SimulationMode,
    SimulationParameters,
    SimulationStatusResponse,
    SimulationTriggerResponse,
)
from ....services.simulator import ClickstreamSimulator
from ....services.storage import StorageService

router = APIRouter()


def get_default_parameters(settings: Settings = Depends(get_settings)) -> SimulationParameters:
    """Construct default simulation parameters from configuration."""

    return SimulationParameters(
        mode=SimulationMode.FULL,
        batches=1,
        batch_size=settings.default_simulation_batch_size,
        user_count=settings.default_simulation_users,
    )


@router.post(
    "",
    response_model=SimulationTriggerResponse,
    summary="Trigger a clickstream simulation run",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_simulation(
    background_tasks: BackgroundTasks,
    params: SimulationParameters | None = Body(default=None),
    simulator: ClickstreamSimulator = Depends(get_simulator),
    storage: StorageService = Depends(get_storage_service),
    settings: Settings = Depends(get_settings),
) -> SimulationTriggerResponse:
    """Enqueue a clickstream simulation run using background execution."""

    effective_params = params or SimulationParameters(
        mode=SimulationMode.FULL,
        batches=1,
        batch_size=settings.default_simulation_batch_size,
        user_count=settings.default_simulation_users,
    )

    run = simulator.create_run(effective_params, storage, background_tasks=background_tasks)

    return SimulationTriggerResponse(run_id=run.run_id, status=run.status)


@router.get(
    "/{run_id}",
    response_model=SimulationStatusResponse,
    summary="Fetch status for a simulation run",
)
async def get_simulation_status(
    run_id: str,
    storage: StorageService = Depends(get_storage_service),
) -> SimulationStatusResponse:
    """Return the status of a clickstream simulation run."""

    run = storage.load_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    return SimulationStatusResponse(run=run)

