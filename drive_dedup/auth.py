"""Google Drive OAuth2 authentication helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build

# Full Drive scope is required to trash/delete files after confirmation.
SCOPES = ["https://www.googleapis.com/auth/drive"]

DEFAULT_CREDENTIALS_PATH = Path("credentials/credentials.json")
DEFAULT_TOKEN_PATH = Path("credentials/token.json")


def _credentials_path(path: Optional[Path] = None) -> Path:
    return Path(
        path or os.environ.get("DRIVE_DEDUP_CREDENTIALS", DEFAULT_CREDENTIALS_PATH)
    )


def _token_path(path: Optional[Path] = None) -> Path:
    return Path(path or os.environ.get("DRIVE_DEDUP_TOKEN", DEFAULT_TOKEN_PATH))


def credentials_exist(credentials_path: Optional[Path] = None) -> bool:
    return _credentials_path(credentials_path).exists()


def load_credentials(
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
    *,
    refresh: bool = True,
) -> Optional[Credentials]:
    """Load cached credentials, optionally refreshing. Returns None if unavailable."""
    token_file = _token_path(token_path)
    if not token_file.exists():
        return None

    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds.valid:
        return creds

    if refresh and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds, token_path=token_file)
        return creds

    return None


def save_credentials(creds: Credentials, token_path: Optional[Path] = None) -> None:
    path = _token_path(token_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")


def is_authenticated(
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> bool:
    return load_credentials(credentials_path, token_path) is not None


def get_credentials(
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> Credentials:
    """Load or create OAuth credentials for the Google Drive API (CLI flow)."""
    credentials_path = _credentials_path(credentials_path)
    token_path = _token_path(token_path)

    creds = load_credentials(credentials_path, token_path)
    if creds:
        return creds

    if not credentials_path.exists():
        raise FileNotFoundError(
            f"OAuth client secrets not found at {credentials_path}.\n\n"
            "Setup steps:\n"
            "  1. Open https://console.cloud.google.com/\n"
            "  2. Create (or select) a project\n"
            "  3. Enable the Google Drive API\n"
            "  4. Configure OAuth consent screen\n"
            "  5. Create OAuth client ID credentials (Desktop or Web app)\n"
            "  6. Download the JSON and save it as credentials/credentials.json\n"
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    creds = flow.run_local_server(port=0)
    save_credentials(creds, token_path=token_path)
    return creds


def build_drive_service(
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
    creds: Optional[Credentials] = None,
):
    """Return an authenticated Google Drive API v3 service."""
    if creds is None:
        creds = get_credentials(credentials_path=credentials_path, token_path=token_path)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def create_web_flow(
    redirect_uri: str,
    credentials_path: Optional[Path] = None,
) -> Flow:
    """Create an OAuth flow for the browser-based web app."""
    credentials_path = _credentials_path(credentials_path)
    if not credentials_path.exists():
        raise FileNotFoundError(
            f"OAuth client secrets not found at {credentials_path}. "
            "Download a Desktop or Web client JSON from Google Cloud Console."
        )
    return Flow.from_client_secrets_file(
        str(credentials_path),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )


def exchange_web_code(
    code: str,
    redirect_uri: str,
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
    code_verifier: Optional[str] = None,
) -> Credentials:
    """Exchange an OAuth authorization code and persist the token.

    ``code_verifier`` is required when the authorization URL was created with
    PKCE (the default for google-auth-oauthlib). Pass the same verifier that
    was generated during ``authorization_url()``.
    """
    flow = create_web_flow(redirect_uri, credentials_path=credentials_path)
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(code=code, code_verifier=code_verifier)
    creds = flow.credentials
    save_credentials(creds, token_path=token_path)
    return creds
