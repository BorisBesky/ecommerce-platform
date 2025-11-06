"""Service factories exposed as FastAPI dependencies."""

from fastapi import Depends

from ..core.config import Settings, get_settings
from ..services import AnalyticsService, RayJobManager, StorageService


def get_storage_service(settings: Settings = Depends(get_settings)) -> StorageService:
    return StorageService(settings=settings)


def get_analytics_service(
    settings: Settings = Depends(get_settings),
    storage: StorageService = Depends(get_storage_service),
) -> AnalyticsService:
    return AnalyticsService(settings=settings, storage=storage)


def get_ray_manager(settings: Settings = Depends(get_settings)) -> RayJobManager:
    return RayJobManager(settings=settings)

