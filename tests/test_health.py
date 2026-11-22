"""Smoke tests for the application entry point."""

from fastapi.testclient import TestClient

from app import __version__
from app.main import app

client = TestClient(app)


def test_health_check_reports_service_ready() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "chatbi-api",
        "version": __version__,
    }


def test_openapi_document_exposes_health_endpoint() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    document = response.json()
    assert document["info"]["title"] == "AI Data Analysis Assistant API"
    assert "/health" in document["paths"]
