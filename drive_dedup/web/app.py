"""FastAPI web application for visual Google Drive image deduplication."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from drive_dedup import __version__
from drive_dedup.auth import (
    build_drive_service,
    credentials_exist,
    create_web_flow,
    exchange_web_code,
    is_authenticated,
    load_credentials,
)
from drive_dedup.drive_client import DriveClient
from drive_dedup.oauth_state import pop_oauth_state, save_oauth_state
from drive_dedup.scan_service import scan_manager

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(WEB_DIR / "templates"))

app = FastAPI(title="Drive Dedup", version=__version__)
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


def _public_base_url(request: Request) -> str:
    configured = os.environ.get("DRIVE_DEDUP_BASE_URL")
    if configured:
        return configured.rstrip("/")
    # Prefer the Host the browser used so redirect_uri matches Google Console.
    return str(request.base_url).rstrip("/")


def _redirect_uri(request: Request) -> str:
    return f"{_public_base_url(request)}/auth/callback"


class ScanRequest(BaseModel):
    folder_id: Optional[str] = None
    exact_only: bool = False
    threshold: int = Field(default=5, ge=0, le=64)
    demo: bool = False


class RemoveRequest(BaseModel):
    file_ids: list[str] = Field(default_factory=list)
    confirm: bool = False
    demo: bool = False


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "version": __version__,
            "authenticated": is_authenticated(),
            "credentials_ready": credentials_exist(),
        },
    )


@app.get("/api/status")
async def api_status() -> dict:
    latest = scan_manager.latest_job
    return {
        "authenticated": is_authenticated(),
        "credentials_ready": credentials_exist(),
        "version": __version__,
        "latest_job": _job_payload(latest) if latest else None,
    }


@app.get("/auth/login")
async def auth_login(request: Request) -> RedirectResponse:
    if not credentials_exist():
        raise HTTPException(
            status_code=400,
            detail=(
                "Missing credentials/credentials.json. Create a Google OAuth client "
                "and save the JSON there first."
            ),
        )
    state = secrets.token_urlsafe(24)
    redirect_uri = _redirect_uri(request)
    flow = create_web_flow(redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    if not flow.code_verifier:
        raise HTTPException(
            status_code=500,
            detail="OAuth PKCE code_verifier was not generated; cannot continue login.",
        )
    save_oauth_state(
        state,
        code_verifier=flow.code_verifier,
        redirect_uri=redirect_uri,
    )
    return RedirectResponse(auth_url)


@app.get("/auth/callback")
async def auth_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
) -> RedirectResponse:
    if error:
        return RedirectResponse(f"/?auth=error&message={error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Invalid OAuth callback")

    pending = pop_oauth_state(state)
    if pending is None:
        return RedirectResponse(
            "/?auth=error&message=Login+session+expired.+Please+connect+again."
        )

    try:
        exchange_web_code(
            code=code,
            redirect_uri=pending["redirect_uri"],
            code_verifier=pending["code_verifier"],
        )
    except Exception as exc:  # noqa: BLE001 — show friendly auth errors in UI
        return RedirectResponse(f"/?auth=error&message={quote(str(exc))}")
    return RedirectResponse("/?auth=success")


@app.post("/api/scan")
async def api_scan(body: ScanRequest) -> dict:
    if not body.demo and not is_authenticated():
        raise HTTPException(status_code=401, detail="Connect Google Drive first")
    job = scan_manager.start_scan(
        folder_id=body.folder_id,
        exact_only=body.exact_only,
        threshold=body.threshold,
        demo=body.demo,
    )
    return _job_payload(job)


@app.get("/api/scan/{job_id}")
async def api_scan_status(job_id: str) -> dict:
    job = scan_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scan job not found")
    return _job_payload(job, include_result=True)


@app.get("/api/thumbnail/{file_id}")
async def api_thumbnail(
    file_id: str,
    max_edge: int = Query(default=480, ge=64, le=1280),
) -> Response:
    demo_bytes = scan_manager.get_demo_thumbnail(file_id)
    if demo_bytes is not None:
        return Response(content=demo_bytes, media_type="image/jpeg")

    creds = load_credentials()
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        client = DriveClient(build_drive_service(creds=creds))
        data = client.get_thumbnail_jpeg(file_id, max_edge=max_edge)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=f"Thumbnail unavailable: {exc}") from exc
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.post("/api/remove")
async def api_remove(body: RemoveRequest) -> dict:
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Removal requires confirm=true after explicit user confirmation",
        )
    if not body.file_ids:
        raise HTTPException(status_code=400, detail="No file ids provided")

    if body.demo or all(file_id.startswith("demo-") for file_id in body.file_ids):
        return {
            "trashed": body.file_ids,
            "failed": [],
            "demo": True,
            "message": f"Demo mode: pretend-trashed {len(body.file_ids)} file(s).",
        }

    if not is_authenticated():
        raise HTTPException(status_code=401, detail="Connect Google Drive first")

    client = DriveClient(build_drive_service(creds=load_credentials()))
    success, failures = client.trash_files(body.file_ids)
    return {
        "trashed": success,
        "failed": [{"id": fid, "error": err} for fid, err in failures],
        "demo": False,
        "message": f"Moved {len(success)} file(s) to Google Drive Trash.",
    }


def _job_payload(job, *, include_result: bool = True) -> dict:
    payload = {
        "id": job.id,
        "status": job.status,
        "message": job.message,
        "current": job.current,
        "total": job.total,
        "demo": job.demo,
        "error": job.error,
        "folder_id": job.folder_id,
        "exact_only": job.exact_only,
        "threshold": job.threshold,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }
    if include_result and job.result is not None:
        payload["result"] = job.result
    return payload


def create_app() -> FastAPI:
    return app
