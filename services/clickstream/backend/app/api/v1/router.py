"""Root API router wiring all endpoint modules."""

from fastapi import APIRouter

from .endpoints import health, analytics, ray_jobs, data


api_router = APIRouter()

api_router.include_router(health.router, tags=["health"], prefix="/health")
api_router.include_router(analytics.router, tags=["analytics"], prefix="/analytics")
api_router.include_router(ray_jobs.router, tags=["ray"], prefix="/ray")
api_router.include_router(data.router, tags=["data"], prefix="/data")

