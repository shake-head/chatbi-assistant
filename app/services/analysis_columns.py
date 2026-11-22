"""Shared output-column naming used by validation, charts, and the worker."""

from __future__ import annotations

from app.schemas.analysis import AnalysisPlan, MetricSpec, TimeBucketSpec


def metric_output_name(metric: MetricSpec) -> str:
    """Return the deterministic output column name for one metric."""

    if metric.alias:
        return metric.alias.strip()
    if metric.column:
        return f"{metric.aggregation}_{metric.column}"
    return "row_count"


def time_bucket_output_name(spec: TimeBucketSpec) -> str:
    """Return the deterministic output column name for a time bucket."""

    return f"{spec.column}_{spec.granularity}"


def plan_output_columns(plan: AnalysisPlan) -> list[str]:
    """Return all grouping and metric output names in execution order."""

    names = [*plan.group_by]
    if plan.time_bucket is not None:
        names.append(time_bucket_output_name(plan.time_bucket))
    names.extend(metric_output_name(metric) for metric in plan.metrics)
    return names
