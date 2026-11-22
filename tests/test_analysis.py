"""End-to-end analysis, multi-turn, chart, and isolation tests."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

CSV_DATA = (
    "date,region,channel,amount,quantity\n"
    "2026-01-15,华东,线上,1200.50,3\n"
    "2026-02-15,华南,线下,800.00,2\n"
    "2026-03-15,华东,线下,1500.25,4\n"
    "2026-04-15,华北,线上,600.00,1\n"
)


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
        data={"name": "销售数据"},
    )
    assert response.status_code == 202
    return int(response.json()["id"])


def test_chat_returns_chart_table_and_conclusion(
    client: TestClient,
    registered_user: dict[str, object],
) -> None:
    dataset_id = _upload(client, registered_user)

    response = client.post(
        f"/datasets/{dataset_id}/chat",
        headers=_headers(registered_user),
        json={"question": "各区域的销售额合计是多少？"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["conversation_id"] > 0
    assert body["row_count"] == 3
    assert len(body["result_table"]) == 3
    assert body["chart_spec"]["type"] == "bar"
    assert body["chart_spec"]["x_axis"] == "region"
    assert body["chart_spec"]["series"]
    assert any(series["name"].startswith("amount合计") for series in body["chart_spec"]["series"])
    assert "华东" in body["conclusion"]


def test_line_trend_and_multi_turn_history(
    client: TestClient,
    registered_user: dict[str, object],
) -> None:
    dataset_id = _upload(client, registered_user)

    first = client.post(
        f"/datasets/{dataset_id}/chat",
        headers=_headers(registered_user),
        json={"question": "各区域销售额趋势"},
    ).json()
    second = client.post(
        f"/datasets/{dataset_id}/chat",
        headers=_headers(registered_user),
        json={
            "question": "各区域销售额合计",
            "conversation_id": first["conversation_id"],
        },
    )

    assert first["chart_spec"]["type"] == "line"
    assert first["chart_spec"]["x_axis"] == "date_month"
    assert second.status_code == 200
    assert second.json()["conversation_id"] == first["conversation_id"]

    history = client.get(
        f"/conversations/{first['conversation_id']}/messages",
        headers=_headers(registered_user),
    )
    assert history.status_code == 200
    assert [message["role"] for message in history.json()] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]

    conversations = client.get("/conversations", headers=_headers(registered_user))
    assert conversations.status_code == 200
    assert len(conversations.json()) == 1


def test_sse_chat_streams_progress_and_final_answer(
    client: TestClient,
    registered_user: dict[str, object],
) -> None:
    dataset_id = _upload(client, registered_user)

    response = client.post(
        f"/datasets/{dataset_id}/chat/stream",
        headers=_headers(registered_user),
        json={"question": "各区域销售额合计"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: status" in response.text
    assert "event: result" in response.text
    assert "event: final" in response.text
    final_line = next(
        line
        for line in response.text.splitlines()
        if line.startswith("data: {") and '"chart_spec"' in line
    )
    final_payload = json.loads(final_line.removeprefix("data: "))
    assert final_payload["chart_spec"]["type"] == "bar"
    assert final_payload["result_table"]


def test_chat_and_conversations_are_isolated_by_user(
    client: TestClient,
    registered_user: dict[str, object],
) -> None:
    dataset_id = _upload(client, registered_user)
    first = client.post(
        f"/datasets/{dataset_id}/chat",
        headers=_headers(registered_user),
        json={"question": "总销售额"},
    ).json()
    other = _register(client, "other@example.com")

    chat = client.post(
        f"/datasets/{dataset_id}/chat",
        headers=_headers(other),
        json={"question": "总销售额"},
    )
    messages = client.get(
        f"/conversations/{first['conversation_id']}/messages",
        headers=_headers(other),
    )
    conversations = client.get("/conversations", headers=_headers(other))

    assert chat.status_code == 404
    assert messages.status_code == 404
    assert conversations.json() == []


def test_delete_conversation_removes_messages(
    client: TestClient,
    registered_user: dict[str, object],
) -> None:
    dataset_id = _upload(client, registered_user)
    chat = client.post(
        f"/datasets/{dataset_id}/chat",
        headers=_headers(registered_user),
        json={"question": "各区域销售额合计"},
    ).json()

    deleted = client.delete(
        f"/conversations/{chat['conversation_id']}",
        headers=_headers(registered_user),
    )
    history = client.get(
        f"/conversations/{chat['conversation_id']}/messages",
        headers=_headers(registered_user),
    )

    assert deleted.status_code == 204
    assert history.status_code == 404
