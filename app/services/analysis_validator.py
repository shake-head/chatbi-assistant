"""Validate model-produced plans against the dataset's real schema."""

from __future__ import annotations

from typing import Any

from app.core.errors import AppException
from app.schemas.analysis import AnalysisPlan, FilterOperator
from app.services.analysis_columns import (
    metric_output_name,
    plan_output_columns,
    time_bucket_output_name,
)

NUMERIC_TYPES = {"integer", "number"}
GROUPABLE_TYPES = {"string", "boolean", "datetime"}


def validate_analysis_plan(
    plan: AnalysisPlan,
    schema: dict[str, Any],
    *,
    max_result_rows: int,
) -> AnalysisPlan:
    """Enforce column allow-lists, output bounds, and chart compatibility."""

    columns = {str(column["name"]): column for column in schema.get("columns", [])}
    issues: list[str] = []

    for name in plan.group_by:
        column = columns.get(name)
        if column is None:
            issues.append(f"Unknown group column: {name}")
        elif column["dtype"] not in GROUPABLE_TYPES:
            issues.append(f"Column cannot be grouped: {name}")

    if plan.time_bucket is not None:
        time_column = columns.get(plan.time_bucket.column)
        if time_column is None:
            issues.append(f"Unknown time column: {plan.time_bucket.column}")
        elif time_column["dtype"] != "datetime":
            issues.append(f"Time bucket column is not datetime: {plan.time_bucket.column}")
        if plan.time_bucket.column in plan.group_by:
            issues.append("Time bucket column must not also be in group_by")

    for metric in plan.metrics:
        if metric.column is None:
            continue
        column = columns.get(metric.column)
        if column is None:
            issues.append(f"Unknown metric column: {metric.column}")
        elif (
            metric.aggregation.value in {"sum", "mean", "min", "max"}
            and column["dtype"] not in NUMERIC_TYPES
        ):
            issues.append(f"Metric column is not numeric: {metric.column}")

    for filter_spec in plan.filters:
        column = columns.get(filter_spec.column)
        if column is None:
            issues.append(f"Unknown filter column: {filter_spec.column}")
            continue
        if filter_spec.operator == FilterOperator.CONTAINS and column["dtype"] != "string":
            issues.append("contains is only valid for string columns")

    output_names = plan_output_columns(plan)
    if len(output_names) != len(set(output_names)):
        issues.append("Output column names must be unique")

    dimension_count = len(plan.group_by) + (1 if plan.time_bucket is not None else 0)
    if dimension_count > 2:
        issues.append("At most two output dimensions are supported")

    for sort_spec in plan.sort:
        if sort_spec.field not in output_names:
            issues.append(f"Sort field is not an output column: {sort_spec.field}")

    if plan.chart_type == "pie":
        group_count = len(plan.group_by) + (1 if plan.time_bucket else 0)
        if group_count != 1 or len(plan.metrics) != 1:
            issues.append("Pie charts require exactly one dimension and one metric")

    if issues:
        raise AppException(
            code="ANALYSIS_PLAN_INVALID",
            message="The generated analysis plan is not valid for this dataset",
            status_code=422,
            detail=issues,
        )

    if plan.limit > max_result_rows:
        plan = plan.model_copy(update={"limit": max_result_rows})
    return plan


def output_column_types(plan: AnalysisPlan, schema: dict[str, Any]) -> dict[str, str]:
    """Return output names mapped to schema types for result serialization."""

    types = {str(column["name"]): str(column["dtype"]) for column in schema.get("columns", [])}
    output = {name: types.get(name, "string") for name in plan.group_by}
    if plan.time_bucket is not None:
        output[time_bucket_output_name(plan.time_bucket)] = "datetime"
    for metric in plan.metrics:
        output[metric_output_name(metric)] = (
            "integer" if metric.aggregation.value in {"count", "count_distinct"} else "number"
        )
    return output
