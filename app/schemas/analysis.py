"""Structured analysis plans and end-to-end chat response schemas."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

JsonValue = str | int | float | bool | None


class FilterOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    BETWEEN = "between"
    IS_NULL = "is_null"
    NOT_NULL = "not_null"


class Aggregation(StrEnum):
    SUM = "sum"
    MEAN = "mean"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"


class TimeGranularity(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class FilterSpec(BaseModel):
    """A validated filter expression; values are never interpolated into code."""

    column: str = Field(min_length=1, max_length=128)
    operator: FilterOperator
    value: JsonValue = None
    values: list[JsonValue] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_operands(self) -> FilterSpec:
        if self.operator == FilterOperator.BETWEEN:
            if self.values is None or len(self.values) != 2:
                raise ValueError("between requires exactly two values")
        elif self.operator in {FilterOperator.IN, FilterOperator.NOT_IN}:
            if not self.values:
                raise ValueError("in/not_in requires at least one value")
        elif self.operator == FilterOperator.CONTAINS:
            if not isinstance(self.value, str):
                raise ValueError("contains requires a string value")
        elif self.operator in {FilterOperator.IS_NULL, FilterOperator.NOT_NULL}:
            if self.value is not None or self.values is not None:
                raise ValueError("null checks do not accept operands")
        elif self.value is None:
            raise ValueError("operator requires a value")
        return self


class MetricSpec(BaseModel):
    """One aggregate output column."""

    aggregation: Aggregation
    column: str | None = Field(default=None, max_length=128)
    alias: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_column(self) -> MetricSpec:
        if self.aggregation == Aggregation.COUNT and self.column is None:
            return self
        if self.column is None:
            raise ValueError("aggregation requires a column")
        if self.alias is not None and not self.alias.strip():
            raise ValueError("metric alias must not be blank")
        return self


class SortSpec(BaseModel):
    field: str = Field(min_length=1, max_length=128)
    direction: Literal["asc", "desc"] = "desc"


class TimeBucketSpec(BaseModel):
    column: str = Field(min_length=1, max_length=128)
    granularity: TimeGranularity = TimeGranularity.MONTH


class AnalysisPlan(BaseModel):
    """A bounded, schema-validated instruction set produced by the model."""

    title: str = Field(min_length=1, max_length=200)
    metrics: list[MetricSpec] = Field(min_length=1, max_length=6)
    group_by: list[str] = Field(default_factory=list, max_length=2)
    filters: list[FilterSpec] = Field(default_factory=list, max_length=20)
    time_bucket: TimeBucketSpec | None = None
    sort: list[SortSpec] = Field(default_factory=list, max_length=3)
    limit: int = Field(default=100, ge=1, le=1000)
    chart_type: Literal["auto", "bar", "line", "pie", "table"] = "auto"

    @model_validator(mode="after")
    def validate_plan_shape(self) -> AnalysisPlan:
        if len(set(self.group_by)) != len(self.group_by):
            raise ValueError("group_by columns must be unique")
        return self


class ChatRequest(BaseModel):
    """A natural-language question for a dataset."""

    question: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = Field(default=None, ge=1)


class ChartSeries(BaseModel):
    name: str
    data: list[JsonValue]


class PieDatum(BaseModel):
    name: str
    value: float | int


class ChartSpec(BaseModel):
    """ECharts-ready chart specification returned to the frontend."""

    type: Literal["bar", "line", "pie", "table"]
    title: str
    x_axis: str | None = None
    x_data: list[JsonValue] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)
    data: list[PieDatum] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """The complete answer for one analysis question."""

    conversation_id: int
    message_id: int
    question: str
    conclusion: str
    chart_spec: ChartSpec
    result_table: list[dict[str, Any]]
    row_count: int
