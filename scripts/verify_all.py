"""Run all acceptance commands and write one compact machine-readable report."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "verify_report.json"

COMMANDS = [
    ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
    ("format", [sys.executable, "-m", "ruff", "format", "--check", "."]),
    ("pytest", [sys.executable, "-m", "pytest", "-q"]),
    ("e2e", [sys.executable, "scripts/smoke_e2e.py"]),
]


def main() -> None:
    report: dict[str, object] = {"started_at": time.time(), "commands": []}
    all_ok = True
    for name, command in COMMANDS:
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
            check=False,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        (PROJECT_ROOT / f"verify_{name}.log").write_text(output, encoding="utf-8")
        ok = completed.returncode == 0
        all_ok = all_ok and ok
        report["commands"].append(
            {
                "name": name,
                "ok": ok,
                "returncode": completed.returncode,
                "seconds": round(time.perf_counter() - started, 2),
                "tail": output[-4000:],
            }
        )
        print(f"{name}: {'PASS' if ok else 'FAIL'} ({completed.returncode})", flush=True)
    report["ok"] = all_ok
    report["finished_at"] = time.time()
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    raise SystemExit(0 if all_ok else 1)


def launch_detached() -> None:
    """Start the verification worker outside the current terminal session."""

    kwargs: dict[str, object] = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--worker"],
        cwd=PROJECT_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        **kwargs,
    )
    print("Verification worker started; see verify_report.json when it completes.")


if __name__ == "__main__":
    if "--worker" in sys.argv or "--foreground" in sys.argv:
        main()
    else:
        launch_detached()
