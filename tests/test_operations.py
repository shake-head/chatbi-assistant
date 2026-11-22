"""Observability, request IDs, metrics, and AI usage endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

CSV_DATA = "date,region,amount\n2026-01-15,华东,1200.50\n2026-02-15,华南,800.00\n"


def _headers(user: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['access_token']}"}


def _register(client: TestClient, email: str) -> dict[str, object]:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "correct horse battery"},
    )
    assert response.status_code == 201
    return response.json()


def _upload(client: TestClient, user: dict[str, object]) -> int:
    response = client.post(
        "/datasets",
        headers=_headers(user),
        files={"file": ("sales.csv", CSV_DATA.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 202
    return int(response.json()["id"])


def test_ai_usage_endpoint_aggregates_only_current_user(
    client: TestClient,
    registered_user: dict[str, object],
) -> None:
    dataset_id = _upload(client, registered_user)
    chat = client.post(
        f"/datasets/{dataset_id}/chat",
        headers=_headers(registered_user),
        json={"question": "各区域销售额合计"},
    )
    assert chat.status_code == 200

    usage = client.get("/account/ai-usage", headers=_headers(registered_user))
    other = _register(client, "usage-other@example.com")
    other_usage = client.get("/account/ai-usage", headers=_headers(other))

    assert usage.status_code == 200
    body = usage.json()
    assert body["calls"] == 2
    assert body["successful_calls"] == 2
    assert body["total_tokens"] > 0
    assert body["cost_usd"] == 0
    assert body["monthly_budget_usd"] == 5
    assert other_usage.json()["calls"] == 0


def test_request_id_security_headers_and_metrics(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "test-request-123"})

    assert response.headers["X-Request-ID"] == "test-request-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "X-Process-Time" in response.headers

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "chatbi_http_requests_total" in metrics.text
    assert "chatbi_http_request_duration_seconds" in metrics.text


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "bad@value"})

    assert response.headers["X-Request-ID"] != "bad@value"
    assert len(response.headers["X-Request-ID"]) == 32
