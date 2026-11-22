"""Dataset metadata and parsed schema schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import JsonValue

ColumnType = Literal["integer", "number", "boolean", "datetime", "string"]
DatasetStatus = Literal["uploading", "parsing", "ready", "failed"]


class ColumnSchema(BaseModel):
    name: str
    dtype: ColumnType
    nullable: bool
    unique_count: int
    sample_values: list[JsonValue] = Field(default_factory=list)
    minimum: JsonValue = None
    maximum: JsonValue = None


class DatasetSchema(BaseModel):
    columns: list[ColumnSchema]
    row_count: int
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


class DatasetSummary(BaseModel):
    id: int
    name: str
    status: DatasetStatus
    row_count: int
    error_message: str | None = None
    created_at: datetime


class DatasetRead(DatasetSummary):
    model_config = ConfigDict(populate_by_name=True)

    schema_payload: DatasetSchema | None = Field(
        default=None,
        alias="schema",
        serialization_alias="schema",
    )


class DatasetList(BaseModel):
    items: list[DatasetSummary]
    total: int
