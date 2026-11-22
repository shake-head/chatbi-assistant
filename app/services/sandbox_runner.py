"""Parent-side runner and output validator for the analysis sandbox."""

from __future__ import annotations

import json
import logging
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.errors import AppException
from app.schemas.analysis import AnalysisPlan
from app.services.dataset_service import resolve_stored_path

logger = logging.getLogger(__name__)
MAX_RESULT_COLUMNS = 50
MAX_ABS_NUMERIC_VALUE = 1_000_000_000_000_000


@dataclass(frozen=True)
class ExecutionResult:
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool


def execute_analysis_plan(
    settings: Settings,
    dataset_relative_path: str,
    plan: AnalysisPlan,
    schema: dict[str, Any],
) -> ExecutionResult:
    """Run the plan in a separate process and validate all returned data."""

    dataset_path = resolve_stored_path(settings.data_dir, dataset_relative_path)
    request = {
        "dataset_path": str(dataset_path),
        "data_root": str((settings.data_dir / "datasets").resolve()),
        "schema": schema,
        "plan": plan.model_dump(mode="json"),
        "max_result_rows": settings.analysis_max_result_rows,
        "memory_limit_mb": settings.analysis_memory_limit_mb,
        "timeout_seconds": int(settings.analysis_timeout_seconds),
    }
    environment = _sandbox_environment()

    try:
        completed = subprocess.run(
            [sys.executable, "-m", "app.services.analysis_worker"],
            input=json.dumps(request, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=settings.analysis_timeout_seconds,
            env=environment,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppException(
            code="ANALYSIS_TIMEOUT",
            message="The analysis took too long to complete",
            status_code=422,
        ) from exc
    except OSError as exc:
        logger.exception("analysis_worker_start_failed")
        raise AppException(
            code="ANALYSIS_EXECUTION_FAILED",
            message="The analysis could not be executed",
            status_code=422,
        ) from exc

    if completed.returncode != 0:
        logger.error("analysis_worker_failed stderr=%s", completed.stderr[-2000:])
        raise AppException(
            code="ANALYSIS_EXECUTION_FAILED",
            message="The analysis could not be executed",
            status_code=422,
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        logger.error("analysis_worker_invalid_output stdout=%s", completed.stdout[-2000:])
        raise AppException(
            code="ANALYSIS_EXECUTION_FAILED",
            message="The analysis returned an invalid result",
            status_code=422,
        ) from exc

    if isinstance(payload, dict) and "error" in payload:
        error = payload["error"]
        code = str(error.get("code", "ANALYSIS_EXECUTION_FAILED"))
        message = str(error.get("message", "The analysis failed"))
        logger.error(
            "analysis_worker_reported_error code=%s stderr=%s",
            code,
            completed.stderr[-4000:],
        )
        raise AppException(code=code, message=message, status_code=422)
    return _validate_result(payload, settings.analysis_max_result_rows)


def _sandbox_environment() -> dict[str, str]:
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "LANG",
        "LC_ALL",
    }
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def _validate_result(payload: object, max_rows: int) -> ExecutionResult:
    if not isinstance(payload, dict):
        raise _invalid_result("The analysis result must be a JSON object")
    columns = payload.get("columns")
    rows = payload.get("rows")
    if not isinstance(columns, list) or not columns or len(columns) > MAX_RESULT_COLUMNS:
        raise _invalid_result("The analysis returned an invalid column set")
    if not isinstance(rows, list) or len(rows) > max_rows:
        raise _invalid_result("The analysis returned too many rows")

    names: list[str] = []
    normalized_columns: list[dict[str, str]] = []
    for column in columns:
        if not isinstance(column, dict):
            raise _invalid_result("The analysis returned an invalid column")
        name = column.get("name")
        dtype = column.get("dtype")
        if not isinstance(name, str) or not name or len(name) > 128:
            raise _invalid_result("The analysis returned an invalid column name")
        if dtype not in {"integer", "number", "boolean", "datetime", "string"}:
            raise _invalid_result("The analysis returned an invalid column type")
        names.append(name)
        normalized_columns.append({"name": name, "dtype": dtype})
    if len(names) != len(set(names)):
        raise _invalid_result("The analysis returned duplicate column names")

    normalized_rows: list[dict[str, Any]] = []
    name_set = set(names)
    for row in rows:
        if not isinstance(row, dict) or set(row) != name_set:
            raise _invalid_result("The analysis returned an invalid row")
        normalized_row: dict[str, Any] = {}
        for name, value in row.items():
            normalized_row[name] = _validate_value(value)
        normalized_rows.append(normalized_row)

    row_count = payload.get("row_count")
    truncated = payload.get("truncated")
    if not isinstance(row_count, int) or row_count < len(normalized_rows):
        raise _invalid_result("The analysis returned an invalid row count")
    if not isinstance(truncated, bool):
        raise _invalid_result("The analysis returned invalid truncation metadata")
    return ExecutionResult(
        columns=normalized_columns,
        rows=normalized_rows,
        row_count=row_count,
        truncated=truncated,
    )


def _validate_value(value: object) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str) and len(value) > 1000:
            raise _invalid_result("The analysis returned an oversized string")
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or abs(value) > MAX_ABS_NUMERIC_VALUE:
            raise _invalid_result("The analysis returned an invalid numeric value")
        return value
    raise _invalid_result("The analysis returned an unsupported value")


def _invalid_result(message: str) -> AppException:
    return AppException(
        code="ANALYSIS_RESULT_INVALID",
        message=message,
        status_code=422,
    )
