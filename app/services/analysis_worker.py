"""Isolated worker process that executes a validated analysis plan."""

from __future__ import annotations

import builtins
import json
import math
import socket
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet  # noqa: F401  # Load before network hardening to keep SSL imports intact.

from app.schemas.analysis import AnalysisPlan, FilterOperator
from app.services.analysis_columns import metric_output_name, time_bucket_output_name
from app.services.analysis_validator import output_column_types


class SandboxValidationError(Exception):
    """A plan could not be executed safely against the dataset."""


def _apply_resource_limits(cpu_seconds: int, memory_limit_mb: int) -> None:
    try:
        import resource

        requested_headroom = memory_limit_mb * 1024 * 1024
        current_vm = _current_vm_bytes()
        # Pandas/PyArrow reserve a large virtual address baseline before this
        # worker starts. RLIMIT_AS is absolute, so add the configured budget
        # on top of that baseline instead of incorrectly applying it to total
        # virtual memory. The container cgroup still enforces the hard RSS cap.
        limit = max(requested_headroom, current_vm + requested_headroom)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, OSError, ValueError):
        # Windows has no resource module. Process timeout and bounded output
        # still apply; containers additionally enforce their own limits.
        pass


def _current_vm_bytes() -> int:
    try:
        with open("/proc/self/status", encoding="utf-8") as status:
            for line in status:
                if line.startswith("VmSize:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return 0


def _disable_network() -> None:
    def blocked_connect(*_: object, **__: object) -> None:
        raise PermissionError("Network access is disabled in the analysis sandbox")

    def blocked_socket(*_: object, **__: object) -> None:
        raise PermissionError("Network access is disabled in the analysis sandbox")

    # Keep the socket class intact because some libraries subclass it (e.g.
    # ssl.SSLSocket). Only outbound connection entry points are blocked.
    socket.socket.connect = blocked_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = blocked_connect  # type: ignore[method-assign]
    socket.create_connection = blocked_socket  # type: ignore[assignment]
    socket.getaddrinfo = blocked_socket  # type: ignore[assignment]


def _disable_write_mode() -> None:
    original_open = builtins.open

    def read_only_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            raise PermissionError("File writes are disabled in the analysis sandbox")
        return original_open(file, mode, *args, **kwargs)

    builtins.open = read_only_open  # type: ignore[assignment]


def _execute(request: dict[str, Any]) -> dict[str, Any]:
    data_root = Path(request["data_root"]).resolve()
    dataset_path = Path(request["dataset_path"]).resolve()
    if dataset_path != data_root and not dataset_path.is_relative_to(data_root):
        raise SandboxValidationError("Dataset path is outside the managed data root")
    if not dataset_path.is_file():
        raise SandboxValidationError("Dataset file does not exist")

    plan = AnalysisPlan.model_validate(request["plan"])
    schema = request["schema"]
    max_rows = int(request["max_result_rows"])
    frame = pd.read_parquet(dataset_path)
    frame = _apply_filters(frame, plan)

    if frame.empty:
        return {
            "columns": [
                {"name": name, "dtype": dtype}
                for name, dtype in output_column_types(plan, schema).items()
            ],
            "rows": [],
            "row_count": 0,
            "truncated": False,
        }

    group_columns = list(plan.group_by)
    if plan.time_bucket is not None:
        time_alias = time_bucket_output_name(plan.time_bucket)
        period_codes = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}
        frame[time_alias] = (
            pd.to_datetime(frame[plan.time_bucket.column], errors="coerce")
            .dt.to_period(period_codes[plan.time_bucket.granularity.value])
            .dt.start_time
        )
        group_columns.append(time_alias)

    output = _aggregate(frame, plan, group_columns)
    output = _sort_output(output, plan, group_columns)
    total_rows = len(output)
    limited = output.head(min(plan.limit, max_rows)).copy()

    columns = _output_columns(limited, plan, schema)
    rows = [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in limited.to_dict(orient="records")
    ]
    return {
        "columns": columns,
        "rows": rows,
        "row_count": total_rows,
        "truncated": total_rows > len(rows),
    }


def _apply_filters(frame: pd.DataFrame, plan: AnalysisPlan) -> pd.DataFrame:
    filtered = frame
    for spec in plan.filters:
        if spec.column not in filtered.columns:
            raise SandboxValidationError(f"Unknown filter column: {spec.column}")
        series = filtered[spec.column]
        mask = _filter_mask(series, spec.operator, spec.value, spec.values)
        filtered = filtered.loc[mask]
    return filtered


def _filter_mask(
    series: pd.Series,
    operator: FilterOperator,
    value: Any,
    values: list[Any] | None,
) -> pd.Series:
    if operator == FilterOperator.IS_NULL:
        return series.isna()
    if operator == FilterOperator.NOT_NULL:
        return series.notna()
    if operator == FilterOperator.CONTAINS:
        return series.astype("string").str.contains(str(value), case=False, na=False, regex=False)

    converted = _convert_value(value, series)
    if operator == FilterOperator.EQ:
        return series.eq(converted).fillna(False)
    if operator == FilterOperator.NE:
        return series.ne(converted).fillna(True)
    if operator == FilterOperator.GT:
        return series.gt(converted).fillna(False)
    if operator == FilterOperator.GTE:
        return series.ge(converted).fillna(False)
    if operator == FilterOperator.LT:
        return series.lt(converted).fillna(False)
    if operator == FilterOperator.LTE:
        return series.le(converted).fillna(False)
    if operator in {FilterOperator.IN, FilterOperator.NOT_IN}:
        converted_values = [_convert_value(item, series) for item in (values or [])]
        mask = series.isin(converted_values)
        return mask if operator == FilterOperator.IN else ~mask
    if operator == FilterOperator.BETWEEN:
        converted_values = [_convert_value(item, series) for item in (values or [])]
        return series.between(converted_values[0], converted_values[1], inclusive="both").fillna(
            False
        )
    raise SandboxValidationError("Unsupported filter operator")


def _convert_value(value: Any, series: pd.Series) -> Any:
    if value is None:
        return None
    if pd.api.types.is_datetime64_any_dtype(series):
        converted = pd.to_datetime(value, errors="coerce")
        if pd.isna(converted):
            raise SandboxValidationError("Invalid datetime filter value")
        return converted
    if pd.api.types.is_numeric_dtype(series):
        try:
            return float(value) if isinstance(value, float) else int(value)
        except (TypeError, ValueError) as exc:
            raise SandboxValidationError("Invalid numeric filter value") from exc
    return value


def _aggregate(frame: pd.DataFrame, plan: AnalysisPlan, group_columns: list[str]) -> pd.DataFrame:
    if group_columns:
        grouped = frame.groupby(group_columns, dropna=False, sort=False, observed=True)
        output = grouped.size().reset_index(name="__rows").drop(columns="__rows")
        for metric in plan.metrics:
            name = metric_output_name(metric)
            aggregation = metric.aggregation.value
            if aggregation == "count" and metric.column is None:
                values = grouped.size().to_numpy()
            elif aggregation == "count":
                values = grouped[metric.column].count().to_numpy()
            elif aggregation == "count_distinct":
                values = grouped[metric.column].nunique(dropna=True).to_numpy()
            elif aggregation == "sum":
                values = grouped[metric.column].sum(min_count=1).to_numpy()
            elif aggregation == "mean":
                values = grouped[metric.column].mean().to_numpy()
            elif aggregation == "min":
                values = grouped[metric.column].min().to_numpy()
            elif aggregation == "max":
                values = grouped[metric.column].max().to_numpy()
            else:
                raise SandboxValidationError("Unsupported aggregation")
            output[name] = values
        return output

    output = pd.DataFrame(index=[0])
    for metric in plan.metrics:
        name = metric_output_name(metric)
        aggregation = metric.aggregation.value
        if aggregation == "count" and metric.column is None:
            value = len(frame)
        elif aggregation == "count":
            value = frame[metric.column].count()
        elif aggregation == "count_distinct":
            value = frame[metric.column].nunique(dropna=True)
        elif aggregation == "sum":
            value = frame[metric.column].sum(min_count=1)
        elif aggregation == "mean":
            value = frame[metric.column].mean()
        elif aggregation == "min":
            value = frame[metric.column].min()
        elif aggregation == "max":
            value = frame[metric.column].max()
        else:
            raise SandboxValidationError("Unsupported aggregation")
        output[name] = [value]
    return output


def _sort_output(
    output: pd.DataFrame,
    plan: AnalysisPlan,
    group_columns: list[str],
) -> pd.DataFrame:
    if output.empty:
        return output
    if plan.sort:
        output = output.sort_values(
            [spec.field for spec in plan.sort],
            ascending=[spec.direction == "asc" for spec in plan.sort],
            kind="mergesort",
            na_position="last",
        )
    elif plan.time_bucket is not None:
        output = output.sort_values(
            time_bucket_output_name(plan.time_bucket),
            ascending=True,
            kind="mergesort",
        )
    else:
        metric_name = metric_output_name(plan.metrics[0])
        output = output.sort_values(
            metric_name,
            ascending=False,
            kind="mergesort",
            na_position="last",
        )
    return output.reset_index(drop=True)


def _output_columns(
    output: pd.DataFrame,
    plan: AnalysisPlan,
    schema: dict[str, Any],
) -> list[dict[str, str]]:
    expected_types = output_column_types(plan, schema)
    return [
        {"name": str(column), "dtype": expected_types.get(str(column), "string")}
        for column in output.columns
    ]


def _json_value(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, str):
        return value[:1000]
    return value


def main() -> None:
    """Read one JSON request from stdin and emit one JSON response to stdout."""

    try:
        request = json.loads(sys.stdin.read())
        _apply_resource_limits(
            cpu_seconds=max(1, int(request.get("timeout_seconds", 15))),
            memory_limit_mb=int(request.get("memory_limit_mb", 1024)),
        )
        _disable_network()
        _disable_write_mode()
        result = _execute(request)
        sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except SandboxValidationError as exc:
        traceback.print_exc(file=sys.stderr)
        sys.stdout.write(
            json.dumps(
                {"error": {"code": "ANALYSIS_PLAN_INVALID", "message": str(exc)}},
                ensure_ascii=False,
            )
        )
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.stdout.write(
            json.dumps(
                {"error": {"code": "ANALYSIS_EXECUTION_FAILED", "message": "Execution failed"}},
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
