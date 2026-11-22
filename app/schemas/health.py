"""Health-check response models."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response returned when the API process is ready to accept requests."""

    status: Literal["ok"] = Field(default="ok", description="Service health status.")
    service: str = Field(description="Service identifier.")
    version: str = Field(description="Running application version.")
