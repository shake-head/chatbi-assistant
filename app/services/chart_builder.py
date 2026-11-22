"""Build ECharts-ready chart specifications from trusted result data."""

from __future__ import annotations

from typing import Any

from app.schemas.analysis import (
    AnalysisPlan,
    ChartSeries,
    ChartSpec,
    PieDatum,
)
from app.services.analysis_columns import metric_output_name, time_bucket_output_name
from app.services.sandbox_runner import ExecutionResult


def build_chart_spec(plan: AnalysisPlan, result: ExecutionResult) -> ChartSpec:
    """Select an appropriate chart and map result rows into series."""

    metric_names = [metric_output_name(metric) for metric in plan.metrics]
    dimensions = list(plan.group_by)
    time_name = time_bucket_output_name(plan.time_bucket) if plan.time_bucket else None
    if time_name is not None:
        dimensions.append(time_name)

    chart_type = _chart_type(plan, dimensions)
    if chart_type == "table" or not result.rows:
        return ChartSpec(type="table", title=plan.title)

    if chart_type == "pie":
        dimension = dimensions[0]
        metric = metric_names[0]
        points = [
            PieDatum(name=str(row[dimension]), value=row[metric])
            for row in result.rows
            if row.get(dimension) is not None and isinstance(row.get(metric), (int, float))
        ]
        return ChartSpec(type="pie", title=plan.title, data=points)

    x_field = time_name if time_name is not None else dimensions[0]
    series_dimensions = [name for name in dimensions if name != x_field]
    series_field = series_dimensions[0] if series_dimensions else None
    x_data = _unique_values(result.rows, x_field)
    data_lookup = {(row.get(series_field), row.get(x_field)): row for row in result.rows}

    series: list[ChartSeries] = []
    if series_field is None:
        x_lookup = {row[x_field]: row for row in result.rows}
        for metric in metric_names:
            series.append(
                ChartSeries(
                    name=metric,
                    data=[x_lookup.get(x_value, {}).get(metric) for x_value in x_data],
                )
            )
    else:
        series_values = _unique_values(result.rows, series_field)
        for series_value in series_values:
            for metric in metric_names:
                series_name = (
                    str(series_value) if len(metric_names) == 1 else f"{series_value} - {metric}"
                )
                series.append(
                    ChartSeries(
                        name=series_name,
                        data=[
                            data_lookup.get((series_value, x_value), {}).get(metric)
                            for x_value in x_data
                        ],
                    )
                )

    return ChartSpec(
        type=chart_type,
        title=plan.title,
        x_axis=x_field,
        x_data=x_data,
        series=series,
    )


def _chart_type(plan: AnalysisPlan, dimensions: list[str]) -> str:
    if plan.chart_type == "table" or not dimensions:
        return "table"
    if plan.chart_type in {"bar", "line", "pie"}:
        return plan.chart_type
    if plan.time_bucket is not None:
        return "line"
    if len(dimensions) == 1:
        return "bar"
    return "table"


def _unique_values(rows: list[dict[str, Any]], field: str) -> list[Any]:
    values: list[Any] = []
    seen: set[Any] = set()
    for row in rows:
        value = row.get(field)
        if value not in seen:
            seen.add(value)
            values.append(value)
    return values
