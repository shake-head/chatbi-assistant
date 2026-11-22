"""Exercise the full API through the running Docker Compose service."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from smoke_e2e import run_flow

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "docker-api-report.json"


def main() -> None:
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30, trust_env=False) as client:
        result = run_flow(client)
        checks = {
            "dataset_rows": result["dataset_rows"] == 4,
            "chart": result["chart_type"] in {"bar", "line"},
            "metric": any("amount合计" in name for name in result["chart_series"]),
            "result_rows": result["result_rows"] > 0,
            "history": result["history_messages"] == 4,
            "sse": "event: final" in result["sse_events"],
            "ai_calls": result["ai_calls"] == 4,
            "metrics": result["metrics_available"],
            "delete": result["dataset_deleted"],
        }
        report = {"ok": all(checks.values()), "checks": checks, "result": result}
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["ok"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
