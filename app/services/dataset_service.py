"""Dataset persistence, parsing jobs, and safe file cleanup."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import AppException
from app.models import Dataset
from app.services.dataset_parser import (
    build_schema,
    coerce_types,
    convert_to_parquet,
    load_dataframe,
)

logger = logging.getLogger(__name__)


def dataset_file_path(settings: Settings, dataset: Dataset) -> Path:
    """Resolve a stored relative dataset path without allowing traversal."""

    return resolve_stored_path(settings.data_dir, dataset.file_path)


def resolve_stored_path(data_dir: Path, relative_path: str) -> Path:
    """Resolve a managed dataset path and reject paths outside the data root."""

    root = (data_dir / "datasets").resolve()
    target = (data_dir / relative_path).resolve()
    if target != root and not target.is_relative_to(root):
        raise AppException(
            code="DATASET_PATH_INVALID",
            message="Dataset storage path is invalid",
            status_code=500,
        )
    return target


def remove_dataset_directory(settings: Settings, dataset: Dataset) -> None:
    """Delete only the dataset's own directory under the managed data root."""

    try:
        target = dataset_file_path(settings, dataset)
        if target.parent.exists() and target.parent.name != "datasets":
            shutil.rmtree(target.parent)
    except (OSError, AppException):
        logger.exception("dataset_file_cleanup_failed dataset_id=%s", dataset.id)


def parse_dataset_job(
    factory: sessionmaker[Session],
    *,
    dataset_id: int,
    raw_path: Path,
    data_dir: Path,
    extension: str,
    max_rows: int,
) -> None:
    """Parse an upload in the background and mark the dataset ready or failed."""

    with factory() as db:
        dataset = db.get(Dataset, dataset_id)
        if dataset is None:
            raw_path.unlink(missing_ok=True)
            return
        target = resolve_stored_path(data_dir, dataset.file_path)

        try:
            frame = load_dataframe(raw_path, extension, max_rows)
            frame = coerce_types(frame)
            convert_to_parquet(frame, target)
            dataset.schema_json = build_schema(frame)
            dataset.row_count = len(frame)
            dataset.status = "ready"
            dataset.error_message = None
            db.commit()
        except AppException as exc:
            _mark_failed(db, dataset, exc.message, target)
        except Exception:
            logger.exception("dataset_parse_failed dataset_id=%s", dataset_id)
            _mark_failed(db, dataset, "The dataset could not be processed", target)
        finally:
            raw_path.unlink(missing_ok=True)


def reparse_dataset_job(
    factory: sessionmaker[Session],
    *,
    dataset_id: int,
    data_dir: Path,
    max_rows: int,
) -> None:
    """Rebuild schema metadata from the persisted Parquet data body."""

    with factory() as db:
        dataset = db.get(Dataset, dataset_id)
        if dataset is None:
            return
        target = resolve_stored_path(data_dir, dataset.file_path)
        try:
            if not target.exists():
                raise FileNotFoundError(target)
            frame = pd.read_parquet(target)
            if len(frame) > max_rows:
                raise AppException(
                    code="DATASET_TOO_LARGE",
                    message=f"The dataset exceeds the {max_rows} row limit",
                    status_code=413,
                )
            dataset.schema_json = build_schema(frame)
            dataset.row_count = len(frame)
            dataset.status = "ready"
            dataset.error_message = None
            db.commit()
        except AppException as exc:
            _mark_failed(db, dataset, exc.message, target)
        except Exception:
            logger.exception("dataset_reparse_failed dataset_id=%s", dataset_id)
            _mark_failed(db, dataset, "The dataset could not be reprocessed", target)


def _mark_failed(
    db: Session,
    dataset: Dataset,
    message: str,
    target: Path,
) -> None:
    dataset.status = "failed"
    dataset.error_message = message[:1000]
    dataset.schema_json = {}
    dataset.row_count = 0
    db.commit()
    if target.exists():
        target.unlink(missing_ok=True)


def serialize_schema(dataset: Dataset) -> dict[str, Any] | None:
    """Return stored schema JSON only for successfully parsed datasets."""

    if dataset.status != "ready" or not dataset.schema_json:
        return None
    return dataset.schema_json
