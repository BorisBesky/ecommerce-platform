"""FastAPI application entrypoint for the clickstream analytics service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1.router import api_router
from .core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""

    resolved_settings = settings or get_settings()

    app = FastAPI(
        title="Clickstream Analytics Service",
        version=resolved_settings.app_version,
        docs_url=resolved_settings.docs_url,
        redoc_url=resolved_settings.redoc_url,
        openapi_url=resolved_settings.openapi_url,
    )

    app.state.settings = resolved_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_allow_origins,
        allow_credentials=resolved_settings.cors_allow_credentials,
        allow_methods=resolved_settings.cors_allow_methods,
        allow_headers=resolved_settings.cors_allow_headers,
    )
    app.include_router(api_router, prefix=resolved_settings.api_v1_prefix)

    return app


app = create_app()

