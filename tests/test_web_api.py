"""API tests for the Drive Dedup web app (demo mode, no Google credentials)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from drive_dedup.web.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_index_renders(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Drive Dedup" in response.text
    assert "Try a visual demo" in response.text


def test_status_endpoint(client: TestClient) -> None:
    response = client.get("/api/status")
    assert response.status_code == 200
    payload = response.json()
    assert "authenticated" in payload
    assert "credentials_ready" in payload


def test_demo_scan_and_thumbnails(client: TestClient) -> None:
    start = client.post("/api/scan", json={"demo": True, "threshold": 5})
    assert start.status_code == 200
    job_id = start.json()["id"]

    result = None
    for _ in range(40):
        status = client.get(f"/api/scan/{job_id}")
        assert status.status_code == 200
        body = status.json()
        if body["status"] == "completed":
            result = body["result"]
            break
        if body["status"] == "failed":
            pytest.fail(body.get("error") or "demo scan failed")
        time.sleep(0.05)

    assert result is not None
    assert result["group_count"] >= 1
    assert result["remove_count"] >= 1
    assert result["groups"]

    first_image = result["groups"][0]["images"][0]
    thumb = client.get(first_image["thumbnail_url"])
    assert thumb.status_code == 200
    assert thumb.headers["content-type"].startswith("image/")
    assert len(thumb.content) > 100


def test_remove_requires_confirm(client: TestClient) -> None:
    response = client.post(
        "/api/remove",
        json={"file_ids": ["demo-exact-2"], "confirm": False, "demo": True},
    )
    assert response.status_code == 400


def test_demo_remove_with_confirm(client: TestClient) -> None:
    response = client.post(
        "/api/remove",
        json={
            "file_ids": ["demo-exact-2", "demo-exact-3"],
            "confirm": True,
            "demo": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["demo"] is True
    assert set(payload["trashed"]) == {"demo-exact-2", "demo-exact-3"}
