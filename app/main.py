"""FastAPI application entry point."""

import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.error_handlers import register_exception_handlers
from app.api.middleware import RequestObservabilityMiddleware
from app.api.routes import account, analysis, auth, datasets, health
from app.core.config import get_settings
from app.core.logging import configure_logging

APP_TITLE = "AI Data Analysis Assistant API"
APP_DESCRIPTION = (
    "Backend API for uploading datasets and asking natural-language analysis questions."
)
STATIC_DIR = Path(__file__).resolve().parent / "static"
# Ensure ES module scripts are served with the correct MIME type on every platform
# (Windows otherwise guesses text/plain, which browsers refuse to execute).
mimetypes.add_type("text/javascript", ".mjs")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Prepare runtime directories before accepting requests."""

    get_settings().ensure_data_dir()
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""

    settings = get_settings()
    configure_logging(settings.log_level)
    application = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
    )
    application.add_middleware(RequestObservabilityMiddleware)
    register_exception_handlers(application)
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(datasets.router)
    application.include_router(analysis.router)
    application.include_router(account.router)

    # Serve the Chinese operations console after API, /docs, and /openapi.json routes
    # so those endpoints keep their existing behaviour.
    application.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
    return application


app = create_app()
