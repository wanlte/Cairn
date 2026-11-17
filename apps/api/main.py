from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.auth.router import router as auth_router
from apps.api.config import get_settings
from apps.api.credentials.router import router as credentials_router
from apps.api.errors import register_error_handlers
from apps.api.evaluation.router import router as evaluation_router
from apps.api.extraction.router import router as extraction_router
from apps.api.gateway.router import router as gateway_router
from apps.api.health import router as health_router
from apps.api.ingestion.router import router as ingestion_router
from apps.api.logging import setup_logging
from apps.api.middleware import RequestIdMiddleware
from apps.api.profile.router import router as profile_router
from apps.api.retrieval.router import router as retrieval_router
from apps.api.review.router import router as review_router
from apps.api.usage.router import router as usage_router


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(title="Cairn API", version="0.2.0")
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(credentials_router)
    app.include_router(gateway_router)
    app.include_router(ingestion_router)
    app.include_router(extraction_router)
    app.include_router(review_router)
    app.include_router(profile_router)
    app.include_router(retrieval_router)
    app.include_router(evaluation_router)
    app.include_router(usage_router)
    register_error_handlers(app)
    return app
