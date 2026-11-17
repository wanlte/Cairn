from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.auth.router import router as auth_router
from apps.api.config import get_settings
from apps.api.errors import register_error_handlers
from apps.api.health import router as health_router
from apps.api.logging import setup_logging
from apps.api.middleware import RequestIdMiddleware


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(title="Cairn API", version="0.1.0")
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
    register_error_handlers(app)
    return app
