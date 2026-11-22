"""Diagnose common local startup blockers without printing secrets."""

from __future__ import annotations

import json
import socket
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app.core.config import Settings

REPORT_PATH = Path("startup_report.json")


def main() -> None:
    report: dict[str, object] = {"env_file_exists": Path(".env").is_file()}
    try:
        settings = Settings()
        report.update(
            {
                "config_ok": True,
                "app_env": settings.app_env,
                "log_level": settings.log_level,
                "data_dir": str(settings.data_dir.resolve()),
                "database": _safe_database(settings.database_url),
                "ai_provider": settings.ai_provider,
                "hosted_ai_configured": bool(
                    settings.ai_api_base_url.strip() and settings.ai_model.strip()
                ),
                "rate_limit_enabled": settings.rate_limit_enabled,
            }
        )
    except Exception as exc:
        report.update({"config_ok": False, "config_error": type(exc).__name__})
        _write(report)
        return

    try:
        import app.main  # noqa: F401

        report["app_import_ok"] = True
    except Exception as exc:
        report["app_import_ok"] = False
        report["app_import_error"] = f"{type(exc).__name__}: {exc}"

    report["data_dir_exists"] = settings.data_dir.exists()
    report["data_dir_writable"] = _is_writable(settings.data_dir)

    try:
        engine = create_engine(settings.database_url)
        with engine.connect() as connection:
            report["database_reachable"] = True
            report["database_tables"] = sorted(inspect(connection).get_table_names())
        engine.dispose()
    except Exception as exc:
        report["database_reachable"] = False
        report["database_error"] = f"{type(exc).__name__}: {exc}"

    report["port_8000_available"] = _port_available(8000)
    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
            decode_responses=True,
        )
        report["redis_ping"] = bool(client.ping())
        client.close()
    except Exception as exc:
        report["redis_ping"] = False
        report["redis_error"] = f"{type(exc).__name__}: {exc}"
    _write(report)


def _safe_database(database_url: str) -> str:
    if database_url.startswith("sqlite:///"):
        return database_url
    return database_url.split("@")[-1]


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _write(report: dict[str, object]) -> None:
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
