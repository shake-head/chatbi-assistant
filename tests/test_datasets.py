"""Dataset upload, parsing, ownership, and cleanup tests."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
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


def _upload_csv(
    client: TestClient,
    user: dict[str, object],
    *,
    content: bytes = CSV_DATA.encode("utf-8"),
    filename: str = "sales.csv",
    name: str = "销售数据",
) -> dict[str, object]:
    response = client.post(
        "/datasets",
        headers=_headers(user),
        files={"file": (filename, content, "text/csv")},
        data={"name": name},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_upload_csv_parses_schema_and_sample_rows(
    client: TestClient,
    registered_user: dict[str, object],
) -> None:
    created = _upload_csv(client, registered_user)

    detail = client.get(
        f"/datasets/{created['id']}",
        headers=_headers(registered_user),
    )

    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "ready"
    assert body["row_count"] == 4
    assert body["name"] == "销售数据"
    assert body["schema"]["row_count"] == 4
    columns = {column["name"]: column for column in body["schema"]["columns"]}
    assert columns["date"]["dtype"] == "datetime"
    assert columns["region"]["dtype"] == "string"
    assert columns["amount"]["dtype"] == "number"
    assert columns["quantity"]["dtype"] == "integer"
    assert body["schema"]["sample_rows"][0]["region"] == "华东"


def test_excel_upload_is_supported(
    client: TestClient,
    registered_user: dict[str, object],
) -> None:
    buffer = BytesIO()
    pd.DataFrame(
        {
            "月份": ["2026-01", "2026-02"],
            "区域": ["华东", "华南"],
            "销售额": [100, 200],
        }
    ).to_excel(buffer, index=False, engine="openpyxl")

    response = client.post(
        "/datasets",
        headers=_headers(registered_user),
        files={
            "file": (
                "sales.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 202
    dataset_id = response.json()["id"]
    detail = client.get(
        f"/datasets/{dataset_id}",
        headers=_headers(registered_user),
    ).json()
    assert detail["status"] == "ready"
    assert detail["row_count"] == 2
    assert detail["schema"]["columns"][2]["name"] == "销售额"


def test_dataset_list_and_reparse(
    client: TestClient,
    registered_user: dict[str, object],
) -> None:
    created = _upload_csv(client, registered_user)

    listed = client.get("/datasets", headers=_headers(registered_user))
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == created["id"]

    reparsed = client.post(
        f"/datasets/{created['id']}/reparse",
        headers=_headers(registered_user),
    )
    assert reparsed.status_code == 202
    detail = client.get(
        f"/datasets/{created['id']}",
        headers=_headers(registered_user),
    ).json()
    assert detail["status"] == "ready"
    assert detail["schema"]["row_count"] == 4


def test_users_cannot_read_or_delete_another_users_dataset(
    client: TestClient,
    registered_user: dict[str, object],
) -> None:
    created = _upload_csv(client, registered_user)
    other_user = _register(client, "other@example.com")

    detail = client.get(f"/datasets/{created['id']}", headers=_headers(other_user))
    delete = client.delete(f"/datasets/{created['id']}", headers=_headers(other_user))
    listing = client.get("/datasets", headers=_headers(other_user))

    assert detail.status_code == 404
    assert delete.status_code == 404
    assert listing.json()["total"] == 0


def test_delete_removes_database_record_and_files(
    client: TestClient,
    registered_user: dict[str, object],
    test_settings: object,
) -> None:
    created = _upload_csv(client, registered_user)
    user_id = int(registered_user["user"]["id"])  # type: ignore[index]
    user_dataset_root = test_settings.data_dir / "datasets" / str(user_id)  # type: ignore[attr-defined]
    assert any(user_dataset_root.iterdir())

    response = client.delete(
        f"/datasets/{created['id']}",
        headers=_headers(registered_user),
    )

    assert response.status_code == 204
    missing = client.get(
        f"/datasets/{created['id']}",
        headers=_headers(registered_user),
    )
    assert missing.status_code == 404
    assert not any(user_dataset_root.iterdir())


def test_unsupported_and_empty_files_are_rejected(
    client: TestClient,
    registered_user: dict[str, object],
) -> None:
    unsupported = client.post(
        "/datasets",
        headers=_headers(registered_user),
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    empty = client.post(
        "/datasets",
        headers=_headers(registered_user),
        files={"file": ("empty.csv", b"", "text/csv")},
    )

    assert unsupported.status_code == 415
    assert unsupported.json()["code"] == "UNSUPPORTED_FILE_TYPE"
    assert empty.status_code == 422
    assert empty.json()["code"] == "EMPTY_FILE"


def test_invalid_excel_is_marked_failed(
    client: TestClient,
    registered_user: dict[str, object],
) -> None:
    response = client.post(
        "/datasets",
        headers=_headers(registered_user),
        files={"file": ("broken.xlsx", b"not an excel file", "application/octet-stream")},
    )
    assert response.status_code == 202

    detail = client.get(
        f"/datasets/{response.json()['id']}",
        headers=_headers(registered_user),
    ).json()
    assert detail["status"] == "failed"
    assert detail["error_message"]
    assert detail["schema"] is None
