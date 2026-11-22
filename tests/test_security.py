"""Security boundary tests for plans, paths, sandboxing, and rate limits."""

from __future__ import annotations

import asyncio
import os
import socket
import uuid
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.errors import AppException
from app.core.rate_limit import check_rate_limit
from app.schemas.analysis import AnalysisPlan
from app.services.analysis_validator import validate_analysis_plan
from app.services.dataset_service import resolve_stored_path
from app.services.sandbox_runner import _sandbox_environment, _validate_result

SCHEMA = {
    "columns": [
        {"name": "region", "dtype": "string"},
        {"name": "amount", "dtype": "number"},
        {"name": "date", "dtype": "datetime"},
    ]
}


def test_plan_rejects_unknown_columns_and_injection_names() -> None:
    plan = AnalysisPlan.model_validate(
        {
            "title": "malicious",
            "metrics": [{"aggregation": "sum", "column": "__import__"}],
            "group_by": ["region"],
        }
    )

    with pytest.raises(AppException) as exc_info:
        validate_analysis_plan(plan, SCHEMA, max_result_rows=100)

    assert exc_info.value.code == "ANALYSIS_PLAN_INVALID"
    assert any("Unknown metric column" in issue for issue in exc_info.value.detail)


def test_plan_rejects_invalid_sort_and_non_numeric_metric() -> None:
    plan = AnalysisPlan.model_validate(
        {
            "title": "bad plan",
            "metrics": [{"aggregation": "sum", "column": "region", "alias": "bad"}],
            "group_by": ["region"],
            "sort": [{"field": "injected", "direction": "desc"}],
        }
    )

    with pytest.raises(AppException) as exc_info:
        validate_analysis_plan(plan, SCHEMA, max_result_rows=100)

    issues = "\n".join(exc_info.value.detail)
    assert "not numeric" in issues
    assert "Sort field" in issues


def test_dataset_path_traversal_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "datasets").mkdir()

    with pytest.raises(AppException) as exc_info:
        resolve_stored_path(tmp_path, "../outside.parquet")

    assert exc_info.value.code == "DATASET_PATH_INVALID"


def test_sandbox_environment_does_not_inherit_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_KEY", "secret-model-key")
    monkeypatch.setenv("JWT_SECRET", "secret-jwt-value")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///secret.db")

    environment = _sandbox_environment()

    assert "AI_API_KEY" not in environment
    assert "JWT_SECRET" not in environment
    assert "DATABASE_URL" not in environment


@pytest.mark.parametrize(
    "payload",
    [
        {"columns": [], "rows": [], "row_count": 0, "truncated": False},
        {
            "columns": [{"name": "x", "dtype": "number"}],
            "rows": [{"x": float("inf")}],
            "row_count": 1,
            "truncated": False,
        },
        {
            "columns": [{"name": "x", "dtype": "number"}],
            "rows": [{"x": 1}, {"x": 2}],
            "row_count": 1,
            "truncated": False,
        },
    ],
)
def test_result_validator_rejects_invalid_worker_output(payload: object) -> None:
    with pytest.raises(AppException):
        _validate_result(payload, max_rows=100)


def test_rate_limit_falls_back_to_memory_and_blocks_excess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr("app.core.rate_limit._increment_redis", unavailable)
    settings = Settings(
        _env_file=None,
        app_env="development",
        rate_limit_enabled=True,
        rate_limit_window_seconds=60,
        redis_url="redis://127.0.0.1:1/0",
    )
    scope = f"test-{uuid.uuid4().hex}"

    async def exercise() -> None:
        await check_rate_limit(user_id=1, settings=settings, scope=scope, limit=1)
        with pytest.raises(AppException) as exc_info:
            await check_rate_limit(user_id=1, settings=settings, scope=scope, limit=1)
        assert exc_info.value.code == "RATE_LIMIT_EXCEEDED"
        assert exc_info.value.headers

    asyncio.run(exercise())


def test_sandbox_environment_has_no_common_secret_prefixes() -> None:
    environment = _sandbox_environment()
    assert not any(key.startswith(("AI_", "JWT_", "AWS_", "OPENAI_")) for key in environment)
    assert os.environ.get("PATH") == environment.get("PATH")


def test_network_guard_keeps_socket_class_for_ssl_imports() -> None:
    from app.services.analysis_worker import _disable_network

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo
    try:
        _disable_network()
        assert isinstance(socket.socket, type)
        with pytest.raises(PermissionError):
            socket.create_connection(("127.0.0.1", 9), timeout=0.1)
        with pytest.raises(PermissionError):
            socket.getaddrinfo("example.com", 443)
    finally:
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        socket.create_connection = original_create_connection
        socket.getaddrinfo = original_getaddrinfo
