"""Persist short-lived OAuth PKCE state across the browser redirect.

google-auth-oauthlib enables PKCE by default. The authorization step creates a
``code_verifier`` that must be presented again when exchanging the auth code.
Because login and callback are separate HTTP requests (and may even hit a
reloaded uvicorn worker), we store the verifier keyed by OAuth ``state``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

DEFAULT_STATE_PATH = Path(
    os.environ.get("DRIVE_DEDUP_OAUTH_STATE", ".cache/oauth_states.json")
)
STATE_TTL_SECONDS = 15 * 60


def _path() -> Path:
    return DEFAULT_STATE_PATH


def _load() -> dict:
    path = _path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    now = time.time()
    return {
        key: value
        for key, value in data.items()
        if isinstance(value, dict) and float(value.get("expires_at", 0)) > now
    }


def _save(data: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def save_oauth_state(
    state: str,
    *,
    code_verifier: str,
    redirect_uri: str,
) -> None:
    data = _load()
    data[state] = {
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "expires_at": time.time() + STATE_TTL_SECONDS,
    }
    _save(data)


def pop_oauth_state(state: str) -> Optional[dict]:
    data = _load()
    value = data.pop(state, None)
    _save(data)
    if not value:
        return None
    return value
