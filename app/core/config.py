"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_JWT_SECRET = "development-only-jwt-secret-do-not-deploy"
PRODUCTION_PLACEHOLDER_JWT_SECRET = "replace-with-at-least-32-random-characters"


class Settings(BaseSettings):
    """Runtime configuration for the API service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    data_dir: Path = Path("./var")
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: SecretStr = SecretStr(DEVELOPMENT_JWT_SECRET)
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "chatbi-api"
    access_token_expire_minutes: int = Field(default=60, ge=1, le=10080)

    max_upload_size_mb: int = Field(default=50, ge=1, le=1024)
    max_dataset_rows: int = Field(default=1_000_000, ge=1)
    max_history_messages: int = Field(default=10, ge=0, le=100)

    ai_provider: Literal["auto", "openai_compatible", "local"] = "auto"
    ai_api_base_url: str = ""
    ai_api_key: SecretStr | None = None
    ai_model: str = ""
    ai_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    ai_max_retries: int = Field(default=2, ge=0, le=5)
    ai_input_cost_per_million_usd: float = Field(default=0.0, ge=0)
    ai_output_cost_per_million_usd: float = Field(default=0.0, ge=0)
    ai_monthly_budget_usd: float = Field(default=5.0, ge=0)

    analysis_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    analysis_memory_limit_mb: int = Field(default=1024, ge=128, le=8192)
    analysis_max_result_rows: int = Field(default=1000, ge=1, le=10000)

    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    ai_rate_limit_requests: int = Field(default=30, ge=1, le=10000)
    upload_rate_limit_requests: int = Field(default=10, ge=1, le=10000)

    @model_validator(mode="after")
    def apply_environment_defaults(self) -> Settings:
        """Derive local paths and reject unsafe production secrets."""

        self.data_dir = self.data_dir.expanduser()
        if not self.database_url.strip():
            database_path = (self.data_dir / "chatbi.db").as_posix()
            self.database_url = f"sqlite:///{database_path}"

        if self.app_env == "production":
            secret = self.jwt_secret.get_secret_value()
            if secret in {DEVELOPMENT_JWT_SECRET, PRODUCTION_PLACEHOLDER_JWT_SECRET}:
                raise ValueError("JWT_SECRET must be replaced in production")
            if len(secret) < 32:
                raise ValueError("JWT_SECRET must contain at least 32 characters in production")

        return self

    def ensure_data_dir(self) -> None:
        """Create the configured local data directory when it does not exist."""

        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "datasets").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "tmp").mkdir(parents=True, exist_ok=True)

    @property
    def max_upload_size_bytes(self) -> int:
        """Return the upload limit in bytes."""

        return self.max_upload_size_mb * 1024 * 1024

    @property
    def jwt_secret_value(self) -> str:
        """Return the JWT secret without exposing it in settings representations."""

        return self.jwt_secret.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""

    return Settings()
