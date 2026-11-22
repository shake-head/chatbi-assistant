"""Service health and metrics endpoints."""

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import __version__
from app.core.constants import SERVICE_NAME
from app.schemas.health import HealthResponse

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check API health",
    description="Returns success when the API process is running.",
)
async def health_check() -> HealthResponse:
    """Report that the API process is healthy."""

    return HealthResponse(service=SERVICE_NAME, version=__version__)


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Expose Prometheus metrics for internal scraping."""

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
