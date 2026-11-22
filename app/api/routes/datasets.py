"""Dataset upload, listing, detail, reparse, and deletion endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, Response, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import AppSettings, CurrentUser, DbSession, SessionFactoryDep, UploadRateLimit
from app.core.errors import AppException, not_found_error
from app.models import Dataset
from app.schemas.dataset import DatasetList, DatasetRead, DatasetSchema, DatasetSummary
from app.services.dataset_parser import SUPPORTED_EXTENSIONS
from app.services.dataset_service import (
    parse_dataset_job,
    remove_dataset_directory,
    reparse_dataset_job,
    serialize_schema,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])
UPLOAD_CHUNK_BYTES = 1024 * 1024


def _to_summary(dataset: Dataset) -> DatasetSummary:
    return DatasetSummary(
        id=dataset.id,
        name=dataset.name,
        status=dataset.status,
        row_count=dataset.row_count,
        error_message=dataset.error_message,
        created_at=dataset.created_at,
    )


def _to_read(dataset: Dataset) -> DatasetRead:
    schema = serialize_schema(dataset)
    return DatasetRead(
        **_to_summary(dataset).model_dump(),
        schema_payload=DatasetSchema.model_validate(schema) if schema else None,
    )


def _owned_dataset(db: DbSession, dataset_id: int, user_id: int) -> Dataset:
    dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id, Dataset.user_id == user_id))
    if dataset is None:
        raise not_found_error("Dataset")
    return dataset


def _save_upload(upload: UploadFile, target: Path, max_bytes: int) -> None:
    size = 0
    try:
        with target.open("wb") as output:
            while chunk := upload.file.read(UPLOAD_CHUNK_BYTES):
                size += len(chunk)
                if size > max_bytes:
                    raise AppException(
                        code="FILE_TOO_LARGE",
                        message="The uploaded file exceeds the size limit",
                        status_code=413,
                    )
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        upload.file.close()

    if size == 0:
        target.unlink(missing_ok=True)
        raise AppException(
            code="EMPTY_FILE",
            message="The uploaded file is empty",
            status_code=422,
        )


@router.post(
    "",
    response_model=DatasetRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a CSV or Excel dataset",
)
def upload_dataset(
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    session_factory: SessionFactoryDep,
    _rate_limit: UploadRateLimit,
    file: Annotated[UploadFile, File(description="CSV, XLSX, or XLS file")],
    name: Annotated[str | None, Form(max_length=255)] = None,
) -> DatasetRead:
    """Store an upload immediately and parse it asynchronously."""

    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise AppException(
            code="UNSUPPORTED_FILE_TYPE",
            message="Only .csv, .xlsx, and .xls files are supported",
            status_code=415,
        )

    settings.ensure_data_dir()
    upload_id = uuid4().hex
    raw_path = settings.data_dir / "tmp" / f"{upload_id}{extension}"
    relative_target = f"datasets/{user.id}/{upload_id}/data.parquet"
    target_path = settings.data_dir / relative_target
    _save_upload(file, raw_path, settings.max_upload_size_bytes)

    dataset_name = (name or Path(filename).stem).strip()[:255] or "dataset"
    dataset = Dataset(
        user_id=user.id,
        name=dataset_name,
        file_path=relative_target,
        schema_json={},
        row_count=0,
        status="parsing",
    )
    try:
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
    except Exception:
        db.rollback()
        raw_path.unlink(missing_ok=True)
        target_path.unlink(missing_ok=True)
        raise

    background_tasks.add_task(
        parse_dataset_job,
        session_factory,
        dataset_id=dataset.id,
        raw_path=raw_path,
        data_dir=settings.data_dir,
        extension=extension,
        max_rows=settings.max_dataset_rows,
    )
    return _to_read(dataset)


@router.get("", response_model=DatasetList, summary="List current user's datasets")
def list_datasets(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DatasetList:
    """List only datasets owned by the authenticated user."""

    base_query = select(Dataset).where(Dataset.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(Dataset).where(Dataset.user_id == user.id))
    datasets = db.scalars(
        base_query.order_by(Dataset.created_at.desc(), Dataset.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return DatasetList(items=[_to_summary(dataset) for dataset in datasets], total=total or 0)


@router.get("/{dataset_id}", response_model=DatasetRead, summary="Get dataset details")
def get_dataset(dataset_id: int, db: DbSession, user: CurrentUser) -> DatasetRead:
    """Return metadata and schema for an owned dataset."""

    return _to_read(_owned_dataset(db, dataset_id, user.id))


@router.post(
    "/{dataset_id}/reparse",
    response_model=DatasetRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Reparse dataset schema",
)
def reparse_dataset(
    dataset_id: int,
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    session_factory: SessionFactoryDep,
) -> DatasetRead:
    """Rebuild the schema from the stored Parquet file in the background."""

    dataset = _owned_dataset(db, dataset_id, user.id)
    dataset.status = "parsing"
    dataset.error_message = None
    db.commit()
    db.refresh(dataset)
    background_tasks.add_task(
        reparse_dataset_job,
        session_factory,
        dataset_id=dataset.id,
        data_dir=settings.data_dir,
        max_rows=settings.max_dataset_rows,
    )
    return _to_read(dataset)


@router.delete(
    "/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a dataset and its stored files",
)
def delete_dataset(
    dataset_id: int,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
) -> Response:
    """Delete an owned dataset, its conversations, and managed files."""

    dataset = _owned_dataset(db, dataset_id, user.id)
    remove_dataset_directory(settings, dataset)
    db.delete(dataset)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
