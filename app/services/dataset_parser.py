"""Safe dataset file loading, type normalization, and schema generation."""

from __future__ import annotations

import csv
import math
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.errors import AppException

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
NUMERIC_PATTERN = re.compile(r"^-?[0-9][0-9,]*(?:\.[0-9]+)?$")
DATE_HINT_PATTERN = re.compile(r"[-/:年月日]")


def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Trim column names, remove blank/unnamed empty columns, and de-duplicate."""

    unnamed_empty = [
        column
        for column in frame.columns
        if str(column).strip().lower().startswith("unnamed:") and frame[column].isna().all()
    ]
    if unnamed_empty:
        frame = frame.drop(columns=unnamed_empty)

    seen: dict[str, int] = {}
    normalized: list[str] = []
    for index, column in enumerate(frame.columns):
        name = str(column).strip() or f"column_{index + 1}"
        count = seen.get(name, 0) + 1
        seen[name] = count
        normalized.append(name if count == 1 else f"{name}_{count}")

    result = frame.copy()
    result.columns = normalized
    return result


def load_dataframe(path: Path, extension: str, max_rows: int) -> pd.DataFrame:
    """Read CSV or Excel data and enforce size, shape, and row limits."""

    if extension not in SUPPORTED_EXTENSIONS:
        raise AppException(
            code="UNSUPPORTED_FILE_TYPE",
            message="Only CSV and Excel files are supported",
            status_code=415,
        )
    try:
        if extension == ".csv":
            frame = _read_csv(path)
        elif extension == ".xlsx":
            frame = pd.read_excel(path, engine="openpyxl")
        else:
            frame = pd.read_excel(path, engine="xlrd")
    except AppException:
        raise
    except Exception as exc:
        raise AppException(
            code="DATASET_PARSE_FAILED",
            message="The uploaded file could not be parsed as tabular data",
            status_code=422,
        ) from exc

    frame = normalize_columns(frame)
    if len(frame.columns) == 0:
        raise AppException(
            code="DATASET_EMPTY",
            message="The dataset does not contain any columns",
            status_code=422,
        )
    if len(frame.columns) > 200:
        raise AppException(
            code="DATASET_TOO_WIDE",
            message="The dataset must contain no more than 200 columns",
            status_code=422,
        )
    if len(frame) == 0:
        raise AppException(
            code="DATASET_EMPTY",
            message="The dataset does not contain any rows",
            status_code=422,
        )
    if len(frame) > max_rows:
        raise AppException(
            code="DATASET_TOO_LARGE",
            message=f"The dataset exceeds the {max_rows} row limit",
            status_code=413,
        )
    return frame


def _read_csv(path: Path) -> pd.DataFrame:
    sample = path.read_bytes()[:65536]
    encoding = "utf-8-sig"
    for candidate in ("utf-8-sig", "gb18030"):
        try:
            sample.decode(candidate)
        except UnicodeDecodeError:
            continue
        encoding = candidate
        break

    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample.decode(encoding, errors="replace")[:8192])
        if dialect.delimiter in {",", "\t", ";", "|"}:
            delimiter = dialect.delimiter
    except csv.Error:
        pass
    return pd.read_csv(
        path,
        encoding=encoding,
        sep=delimiter,
        low_memory=False,
    )


def coerce_types(frame: pd.DataFrame) -> pd.DataFrame:
    """Infer stable column types and convert values without inventing data."""

    result = frame.copy()
    for column in result.columns:
        series = result[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            result[column] = pd.to_datetime(series, errors="coerce")
        elif pd.api.types.is_bool_dtype(series):
            result[column] = series.astype("boolean")
        elif pd.api.types.is_integer_dtype(series):
            result[column] = series.astype("Int64")
        elif pd.api.types.is_float_dtype(series):
            result[column] = series.astype("Float64")
        elif pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            result[column] = _coerce_text_series(series)
    return result


def _coerce_text_series(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    text = text.mask(text == "")
    sample = text.dropna().head(2000)
    if sample.empty:
        return text

    if _looks_like_datetime(sample):
        parsed = pd.to_datetime(text, errors="coerce", format="mixed")
        if parsed.notna().sum() / max(len(sample), 1) >= 0.8:
            return parsed

    numeric_sample = sample.str.replace(",", "", regex=False)
    numeric_ratio = numeric_sample.str.match(NUMERIC_PATTERN).fillna(False).mean()
    if numeric_ratio >= 0.9:
        numeric = pd.to_numeric(text.str.replace(",", "", regex=False), errors="coerce")
        valid = numeric.dropna()
        if not valid.empty and (valid % 1 == 0).all():
            return numeric.astype("Int64")
        return numeric.astype("Float64")

    return text


def _looks_like_datetime(sample: pd.Series) -> bool:
    sample_text = sample.astype(str)
    if not sample_text.str.contains(DATE_HINT_PATTERN, regex=True).any():
        return False
    parsed = pd.to_datetime(sample_text, errors="coerce", format="mixed")
    return parsed.notna().mean() >= 0.8


def build_schema(frame: pd.DataFrame) -> dict[str, Any]:
    """Build JSON-safe column summaries and sample rows for prompts and APIs."""

    columns: list[dict[str, Any]] = []
    for name in frame.columns:
        series = frame[name]
        dtype = _schema_dtype(series)
        non_null = series.dropna()
        minimum = _json_value(non_null.min()) if not non_null.empty else None
        maximum = _json_value(non_null.max()) if not non_null.empty else None
        columns.append(
            {
                "name": str(name),
                "dtype": dtype,
                "nullable": bool(series.isna().any()),
                "unique_count": int(series.nunique(dropna=True)),
                "sample_values": [_json_value(value) for value in non_null.head(5)],
                "minimum": minimum,
                "maximum": maximum,
            }
        )

    sample_rows = [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in frame.head(5).to_dict(orient="records")
    ]
    return {"columns": columns, "row_count": len(frame), "sample_rows": sample_rows}


def _schema_dtype(series: pd.Series) -> str:
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "number"
    return "string"


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool):
        return value
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def convert_to_parquet(frame: pd.DataFrame, target: Path) -> None:
    """Persist the normalized data body as Parquet."""

    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(target, index=False)
