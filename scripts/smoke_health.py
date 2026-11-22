"""Start the API locally and verify its health endpoint."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

HEALTH_URL = "http://127.0.0.1:8765/health"
STARTUP_TIMEOUT_SECONDS = 15.0


def main() -> None:
    """Run Uvicorn, poll the health endpoint, and always stop the child process."""

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    payload: dict[str, str] | None = None
    last_error: Exception | None = None
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS

    try:
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
                    if response.status == 200:
                        payload = json.load(response)
                        break
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last_error = exc
            time.sleep(0.25)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)

    if payload is None:
        raise RuntimeError(f"Health check did not become ready: {last_error}")
    if payload.get("status") != "ok":
        raise RuntimeError(f"Unexpected health response: {payload}")

    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
