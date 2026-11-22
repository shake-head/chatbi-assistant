"""Settings loading and secret validation tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import (
    DEVELOPMENT_JWT_SECRET,
    PRODUCTION_PLACEHOLDER_JWT_SECRET,
    Settings,
)


def test_default_settings_use_local_sqlite_database() -> None:
    settings = Settings(
        _env_file=None,
        data_dir=Path("var"),
        database_url="",
        jwt_secret=DEVELOPMENT_JWT_SECRET,
    )

    assert settings.app_env == "development"
    assert settings.database_url == "sqlite:///var/chatbi.db"
    assert settings.max_dataset_rows == 1_000_000
    assert settings.jwt_secret_value == DEVELOPMENT_JWT_SECRET


def test_empty_database_url_is_derived_from_custom_data_dir(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, database_url="")

    assert settings.database_url == f"sqlite:///{(tmp_path / 'chatbi.db').as_posix()}"


def test_ensure_data_dir_creates_missing_directory(tmp_path: Path) -> None:
    data_dir = tmp_path / "nested" / "data"
    settings = Settings(_env_file=None, data_dir=data_dir)

    settings.ensure_data_dir()

    assert data_dir.is_dir()


@pytest.mark.parametrize(
    "secret",
    [DEVELOPMENT_JWT_SECRET, PRODUCTION_PLACEHOLDER_JWT_SECRET, "too-short"],
)
def test_production_rejects_unsafe_jwt_secret(secret: str) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, app_env="production", jwt_secret=secret)


def test_production_accepts_strong_jwt_secret() -> None:
    settings = Settings(_env_file=None, app_env="production", jwt_secret="s" * 32)

    assert settings.jwt_secret_value == "s" * 32


def test_secrets_are_hidden_from_settings_repr() -> None:
    settings = Settings(
        _env_file=None,
        jwt_secret="sensitive-jwt-value-that-must-not-be-logged",
        ai_api_key="sensitive-model-key",
    )

    representation = repr(settings)

    assert "sensitive-jwt-value" not in representation
    assert "sensitive-model-key" not in representation
