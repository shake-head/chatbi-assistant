"""Shared test fixtures with an isolated SQLite database."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import create_db_engine, get_db, get_session_factory
from app.main import app


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        _env_file=None,
        app_env="test",
        data_dir=tmp_path / "data",
        ai_provider="local",
    )
    settings.ensure_data_dir()
    return settings


@pytest.fixture
def db_session_factory(tmp_path: Path) -> Generator[sessionmaker[Session], None, None]:
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def client(
    db_session_factory: sessionmaker[Session],
    test_settings: Settings,
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: db_session_factory
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def registered_user(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/auth/register",
        json={"email": "owner@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 201
    return response.json()
