"""Run a real HTTP end-to-end acceptance flow against a temporary Uvicorn server."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


PORT = _free_port()
BASE_URL = f"http://127.0.0.1:{PORT}"
REPORT_PATH = PROJECT_ROOT / "e2e_report.json"
CSV_DATA = (
    "date,region,channel,amount,quantity\n"
    "2026-01-15,华东,线上,1200.50,3\n"
    "2026-02-15,华南,线下,800.00,2\n"
    "2026-03-15,华东,线下,1500.25,4\n"
    "2026-04-15,华北,线上,600.00,1\n"
)


def _wait_for_health(client: httpx.Client, deadline: float) -> None:
    while time.monotonic() < deadline:
        try:
            if client.get("/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("API did not become healthy")


def _wait_for_ready(
    client: httpx.Client, headers: dict[str, str], dataset_id: int
) -> dict[str, Any]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        detail = client.get(f"/datasets/{dataset_id}", headers=headers).json()
        if detail.get("status") == "ready":
            return detail
        if detail.get("status") == "failed":
            raise RuntimeError(f"Dataset parse failed: {detail.get('error_message')}")
        time.sleep(0.2)
    raise RuntimeError("Dataset did not become ready")


def run_flow(client: httpx.Client) -> dict[str, Any]:
    email = f"e2e-{int(time.time() * 1000)}@example.com"
    register = client.post(
        "/auth/register",
        json={"email": email, "password": "correct horse battery"},
    )
    register.raise_for_status()
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    upload = client.post(
        "/datasets",
        headers=headers,
        files={"file": ("sales.csv", CSV_DATA.encode("utf-8"), "text/csv")},
        data={"name": "E2E 销售数据"},
    )
    upload.raise_for_status()
    dataset_id = upload.json()["id"]
    detail = _wait_for_ready(client, headers, dataset_id)

    chat = client.post(
        f"/datasets/{dataset_id}/chat",
        headers=headers,
        json={"question": "各区域销售额合计是多少？"},
    )
    if chat.is_error:
        raise RuntimeError(f"Chat failed: {chat.status_code} {chat.text}")
    chat.raise_for_status()
    answer = chat.json()

    events: list[str] = []
    with client.stream(
        "POST",
        f"/datasets/{dataset_id}/chat/stream",
        headers=headers,
        json={
            "question": "各区域销售额趋势",
            "conversation_id": answer["conversation_id"],
        },
    ) as response:
        response.raise_for_status()
        events = [line for line in response.iter_lines() if line.startswith("event: ")]

    history = client.get(
        f"/conversations/{answer['conversation_id']}/messages",
        headers=headers,
    )
    history.raise_for_status()
    usage = client.get("/account/ai-usage", headers=headers)
    usage.raise_for_status()
    metrics = client.get("/metrics")
    metrics.raise_for_status()

    deleted = client.delete(f"/datasets/{dataset_id}", headers=headers)
    deleted.raise_for_status()

    return {
        "email": email,
        "dataset_rows": detail["row_count"],
        "columns": [column["name"] for column in detail["schema"]["columns"]],
        "chart_type": answer["chart_spec"]["type"],
        "chart_series": [series["name"] for series in answer["chart_spec"]["series"]],
        "result_rows": len(answer["result_table"]),
        "conclusion": answer["conclusion"],
        "history_messages": len(history.json()),
        "sse_events": events,
        "ai_calls": usage.json()["calls"],
        "metrics_available": "chatbi_http_requests_total" in metrics.text,
        "dataset_deleted": deleted.status_code == 204,
    }


def main() -> None:
    """Start Uvicorn with an isolated database and exercise the full API."""

    with tempfile.TemporaryDirectory(
        prefix="chatbi-e2e-",
        ignore_cleanup_errors=True,
    ) as temp_name:
        temp = Path(temp_name)
        env = os.environ.copy()
        env.update(
            {
                "APP_ENV": "test",
                "DATA_DIR": str(temp / "data"),
                "DATABASE_URL": f"sqlite:///{(temp / 'chatbi.db').as_posix()}",
                "AI_PROVIDER": "local",
                "RATE_LIMIT_ENABLED": "false",
                "JWT_SECRET": "e2e-" + "x" * 64,
                "LOG_LEVEL": "WARNING",
                "PYTHONIOENCODING": "utf-8",
            }
        )
        migration = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if migration.returncode != 0:
            raise RuntimeError(f"Migration failed:\n{migration.stdout}\n{migration.stderr}")

        log_path = temp / "server.log"
        with log_path.open("w", encoding="utf-8") as log_file:
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(PORT),
                    "--log-level",
                    "warning",
                ],
                cwd=PROJECT_ROOT,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            try:
                with httpx.Client(base_url=BASE_URL, timeout=30, trust_env=False) as client:
                    _wait_for_health(client, time.monotonic() + 20)
                    result = run_flow(client)
                    if not (
                        result["dataset_rows"] == 4
                        and result["chart_type"] in {"bar", "line"}
                        and any("amount合计" in name for name in result["chart_series"])
                        and result["result_rows"] > 0
                        and result["history_messages"] == 4
                        and "event: final" in result["sse_events"]
                        and result["ai_calls"] == 4
                        and result["metrics_available"]
                        and result["dataset_deleted"]
                    ):
                        raise RuntimeError(f"Unexpected E2E result: {result}")
                    REPORT_PATH.write_text(
                        json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    print(json.dumps(result, ensure_ascii=False, indent=2))
            except Exception as exc:
                REPORT_PATH.write_text(
                    json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                log_file.flush()
                print(log_path.read_text(encoding="utf-8")[-8000:], file=sys.stderr)
                raise
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=10)


if __name__ == "__main__":
    main()
