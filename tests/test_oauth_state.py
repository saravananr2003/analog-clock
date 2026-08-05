"""Tests for OAuth PKCE state persistence."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import drive_dedup.oauth_state as oauth_state
from drive_dedup.auth import exchange_web_code
from drive_dedup.web.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_save_and_pop_oauth_state(tmp_path: Path, monkeypatch) -> None:
    state_file = tmp_path / "oauth_states.json"
    monkeypatch.setattr(oauth_state, "DEFAULT_STATE_PATH", state_file)

    oauth_state.save_oauth_state(
        "abc123",
        code_verifier="verifier-one",
        redirect_uri="http://127.0.0.1:8000/auth/callback",
    )
    assert state_file.exists()

    pending = oauth_state.pop_oauth_state("abc123")
    assert pending is not None
    assert pending["code_verifier"] == "verifier-one"
    assert pending["redirect_uri"].endswith("/auth/callback")

    # One-time use
    assert oauth_state.pop_oauth_state("abc123") is None


def test_exchange_web_code_passes_code_verifier(monkeypatch) -> None:
    fake_flow = MagicMock()
    fake_creds = MagicMock()
    fake_flow.credentials = fake_creds

    monkeypatch.setattr(
        "drive_dedup.auth.create_web_flow",
        lambda redirect_uri, credentials_path=None: fake_flow,
    )
    monkeypatch.setattr("drive_dedup.auth.save_credentials", lambda *a, **k: None)

    exchange_web_code(
        code="auth-code",
        redirect_uri="http://127.0.0.1:8000/auth/callback",
        code_verifier="pkce-verifier",
    )

    assert fake_flow.code_verifier == "pkce-verifier"
    fake_flow.fetch_token.assert_called_once_with(
        code="auth-code",
        code_verifier="pkce-verifier",
    )


def test_auth_login_persists_verifier(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    state_file = tmp_path / "oauth_states.json"
    monkeypatch.setattr(oauth_state, "DEFAULT_STATE_PATH", state_file)
    monkeypatch.setattr("drive_dedup.web.app.credentials_exist", lambda: True)

    fake_flow = MagicMock()
    fake_flow.code_verifier = "generated-verifier"
    fake_flow.authorization_url.return_value = (
        "https://accounts.google.com/o/oauth2/auth?state=x",
        "x",
    )
    monkeypatch.setattr("drive_dedup.web.app.create_web_flow", lambda *_a, **_k: fake_flow)

    response = client.get("/auth/login", follow_redirects=False)
    assert response.status_code in {302, 307}
    assert "accounts.google.com" in response.headers.get("location", "")

    data = oauth_state._load()
    assert len(data) == 1
    saved = next(iter(data.values()))
    assert saved["code_verifier"] == "generated-verifier"
    assert saved["redirect_uri"].endswith("/auth/callback")


def test_auth_callback_uses_saved_verifier(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    state_file = tmp_path / "oauth_states.json"
    monkeypatch.setattr(oauth_state, "DEFAULT_STATE_PATH", state_file)
    oauth_state.save_oauth_state(
        "state-1",
        code_verifier="saved-verifier",
        redirect_uri="http://testserver/auth/callback",
    )

    called: dict = {}

    def fake_exchange(**kwargs):
        called.update(kwargs)
        return MagicMock()

    monkeypatch.setattr("drive_dedup.web.app.exchange_web_code", fake_exchange)

    response = client.get(
        "/auth/callback",
        params={"code": "abc", "state": "state-1"},
        follow_redirects=False,
    )
    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/?auth=success"
    assert called["code"] == "abc"
    assert called["code_verifier"] == "saved-verifier"
    assert called["redirect_uri"] == "http://testserver/auth/callback"
