"""Google Drive OAuth2 authentication helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Full Drive scope is required to trash/delete files after confirmation.
SCOPES = ["https://www.googleapis.com/auth/drive"]

DEFAULT_CREDENTIALS_PATH = Path("credentials/credentials.json")
DEFAULT_TOKEN_PATH = Path("credentials/token.json")


def get_credentials(
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> Credentials:
    """Load or create OAuth credentials for the Google Drive API.

    Place your Google Cloud OAuth client secrets at
    ``credentials/credentials.json`` (Desktop app type), then run the CLI.
    On first run a browser window opens for consent and a token is cached.
    """
    credentials_path = Path(
        credentials_path
        or os.environ.get("DRIVE_DEDUP_CREDENTIALS", DEFAULT_CREDENTIALS_PATH)
    )
    token_path = Path(token_path or os.environ.get("DRIVE_DEDUP_TOKEN", DEFAULT_TOKEN_PATH))

    creds: Optional[Credentials] = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"OAuth client secrets not found at {credentials_path}.\n\n"
                "Setup steps:\n"
                "  1. Open https://console.cloud.google.com/\n"
                "  2. Create (or select) a project\n"
                "  3. Enable the Google Drive API\n"
                "  4. Configure OAuth consent screen\n"
                "  5. Create OAuth client ID credentials (Desktop app)\n"
                "  6. Download the JSON and save it as credentials/credentials.json\n"
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def build_drive_service(
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
):
    """Return an authenticated Google Drive API v3 service."""
    creds = get_credentials(credentials_path=credentials_path, token_path=token_path)
    return build("drive", "v3", credentials=creds, cache_discovery=False)
