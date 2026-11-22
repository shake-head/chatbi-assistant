"""Prepare a safe local .env for development and local Redis."""

from __future__ import annotations

import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"
PLACEHOLDER_SECRETS = {
    "",
    "replace-with-at-least-32-random-characters",
    "development-only-jwt-secret-do-not-deploy",
}


def set_value(content: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}=.*$", flags=re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(content):
        return pattern.sub(line, content, count=1)
    return content.rstrip() + "\n" + line + "\n"


def main() -> None:
    content = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    if not content.strip():
        content = EXAMPLE_PATH.read_text(encoding="utf-8")

    changed: list[str] = []
    updates = {
        "APP_ENV": "development",
        "DATA_DIR": "./var",
        "REDIS_URL": "redis://localhost:6379/0",
        "RATE_LIMIT_ENABLED": "true",
        "AI_PROVIDER": "auto",
        "PYTHON_BASE_IMAGE": (
            "swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/python:3.11-slim"
        ),
    }

    existing_secret = re.search(r"^JWT_SECRET=(.*)$", content, flags=re.MULTILINE)
    current_secret = existing_secret.group(1).strip() if existing_secret else ""
    if current_secret in PLACEHOLDER_SECRETS or len(current_secret) < 32:
        updates["JWT_SECRET"] = secrets.token_urlsafe(64)

    for key, value in updates.items():
        previous = re.search(rf"^{re.escape(key)}=(.*)$", content, flags=re.MULTILINE)
        before = previous.group(1) if previous else None
        content = set_value(content, key, value)
        if before != value:
            changed.append(key)

    ENV_PATH.write_text(content, encoding="utf-8")
    print("local .env ready")
    print("changed keys:", ", ".join(changed) if changed else "none")
    print("JWT secret: generated or already strong")


if __name__ == "__main__":
    main()
