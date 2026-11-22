"""Static operations console serving tests."""

from fastapi.testclient import TestClient


def test_root_serves_chinese_console(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'lang="zh-CN"' in response.text
    assert "AI 数据分析助手" in response.text


def test_static_assets_are_served(client: TestClient) -> None:
    css = client.get("/css/app.css")
    js = client.get("/js/app.mjs")
    echarts = client.get("/vendor/echarts.min.js")

    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert js.status_code == 200
    assert (
        "text/javascript" in js.headers["content-type"]
        or "javascript" in js.headers["content-type"]
    )
    assert echarts.status_code == 200


def test_existing_endpoints_are_unaffected(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_unknown_api_path_still_returns_json_error(client: TestClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["code"] == "NOT_FOUND"
