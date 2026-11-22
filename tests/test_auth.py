"""Authentication and API error contract tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import create_access_token


def _register(
    client: TestClient,
    email: str = "analyst@example.com",
    password: str = "correct horse battery",
) -> dict[str, object]:
    return client.post(
        "/auth/register",
        json={"email": email, "password": password},
    ).json()


def test_register_returns_token_without_password_hash(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "  Analyst@Example.COM ", "password": "correct horse battery"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0
    assert body["user"]["email"] == "analyst@example.com"
    assert "password_hash" not in body["user"]


def test_duplicate_email_returns_stable_conflict_error(client: TestClient) -> None:
    _register(client)

    response = client.post(
        "/auth/register",
        json={"email": "analyst@example.com", "password": "another password"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "EMAIL_ALREADY_REGISTERED"


def test_login_and_current_user(client: TestClient) -> None:
    _register(client)

    login_response = client.post(
        "/auth/login",
        json={"email": "analyst@example.com", "password": "correct horse battery"},
    )

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "analyst@example.com"


def test_wrong_password_returns_generic_error(client: TestClient) -> None:
    _register(client)

    response = client.post(
        "/auth/login",
        json={"email": "analyst@example.com", "password": "wrong password"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": "INVALID_CREDENTIALS",
        "message": "Email or password is incorrect",
        "detail": None,
    }


def test_protected_route_requires_valid_bearer_token(client: TestClient) -> None:
    missing_response = client.get("/auth/me")
    assert missing_response.status_code == 401
    assert missing_response.json()["code"] == "UNAUTHORIZED"

    invalid_response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert invalid_response.status_code == 401
    assert invalid_response.json()["code"] == "UNAUTHORIZED"


def test_token_for_missing_user_is_rejected(
    client: TestClient,
    test_settings: Settings,
) -> None:
    token, _ = create_access_token(9999, test_settings)

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["message"] == "User no longer exists"


def test_password_over_bcrypt_byte_limit_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "long@example.com", "password": "密" * 30},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_unknown_route_uses_consistent_error_contract(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "Not Found",
        "detail": None,
    }
