"""Shared scan orchestration for CLI and web app."""

from __future__ import annotations

import hashlib
import io
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from PIL import Image, ImageDraw, ImageFont

from drive_dedup.auth import build_drive_service, load_credentials
from drive_dedup.drive_client import DriveClient
from drive_dedup.duplicates import find_duplicates
from drive_dedup.models import DriveImage, DuplicateGroup
from drive_dedup.serializer import groups_summary


ProgressCallback = Callable[[str, int, int], None]


@dataclass
class ScanJob:
    id: str
    status: str = "queued"  # queued | running | completed | failed
    message: str = "Waiting to start"
    current: int = 0
    total: int = 0
    folder_id: Optional[str] = None
    exact_only: bool = False
    threshold: int = 5
    demo: bool = False
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    groups: list[DuplicateGroup] = field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class ScanManager:
    """In-memory scan job tracker (single-user local app)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, ScanJob] = {}
        self._latest_id: Optional[str] = None
        self._demo_thumbs: dict[str, bytes] = {}

    @property
    def latest_job(self) -> Optional[ScanJob]:
        with self._lock:
            if self._latest_id is None:
                return None
            return self._jobs.get(self._latest_id)

    def get_job(self, job_id: str) -> Optional[ScanJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def get_demo_thumbnail(self, file_id: str) -> Optional[bytes]:
        with self._lock:
            return self._demo_thumbs.get(file_id)

    def start_scan(
        self,
        *,
        folder_id: Optional[str] = None,
        exact_only: bool = False,
        threshold: int = 5,
        demo: bool = False,
    ) -> ScanJob:
        job = ScanJob(
            id=uuid.uuid4().hex[:12],
            folder_id=folder_id or None,
            exact_only=exact_only,
            threshold=threshold,
            demo=demo,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._jobs[job.id] = job
            self._latest_id = job.id

        thread = threading.Thread(target=self._run_job, args=(job.id,), daemon=True)
        thread.start()
        return job

    def _update(self, job_id: str, **kwargs: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in kwargs.items():
                setattr(job, key, value)

    def _run_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        try:
            self._update(job_id, status="running", message="Starting scan…")
            if job.demo:
                groups = self._run_demo(job_id)
            else:
                groups = self._run_live(job)
            summary = groups_summary(groups)
            summary["job_id"] = job_id
            summary["demo"] = job.demo
            summary["folder_id"] = job.folder_id
            self._update(
                job_id,
                status="completed",
                message="Scan complete",
                groups=groups,
                result=summary,
                finished_at=datetime.now(timezone.utc).isoformat(),
                current=job.total or 1,
                total=job.total or 1,
            )
        except Exception as exc:  # noqa: BLE001 — surface to UI
            self._update(
                job_id,
                status="failed",
                message="Scan failed",
                error=str(exc),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )

    def _run_live(self, job: ScanJob) -> list[DuplicateGroup]:
        creds = load_credentials()
        if creds is None:
            raise RuntimeError(
                "Not authenticated with Google Drive. Connect your account first."
            )
        client = DriveClient(build_drive_service(creds=creds))

        self._update(job.id, message="Listing images from Google Drive…")
        images = client.list_images(
            folder_id=job.folder_id,
            progress=lambda n: self._update(
                job.id, message=f"Listed {n} image(s)…", current=n, total=max(n, 1)
            ),
        )
        if not images:
            return []

        compute_perceptual = not job.exact_only
        self._update(
            job.id,
            message="Hashing images…",
            current=0,
            total=len(images),
        )

        def on_hash(done: int, total: int) -> None:
            self._update(
                job.id,
                message=f"Hashing images ({done}/{total})…",
                current=done,
                total=total,
            )

        client.enrich_with_hashes(
            images,
            compute_perceptual=compute_perceptual,
            progress=on_hash,
        )
        self._update(job.id, message="Finding duplicates…")
        return find_duplicates(
            images,
            include_similar=compute_perceptual,
            max_distance=job.threshold,
        )

    def _run_demo(self, job_id: str) -> list[DuplicateGroup]:
        self._update(job_id, message="Building demo library…", current=0, total=6)
        images: list[DriveImage] = []
        thumbs: dict[str, bytes] = {}

        # Exact duplicates: same content hash, different names/sizes presentation.
        for index, (name, size, created) in enumerate(
            [
                ("vacation-beach.jpg", 420_000, "2022-06-12T10:00:00.000Z"),
                ("Copy of vacation-beach.jpg", 420_000, "2023-01-04T10:00:00.000Z"),
                ("vacation-beach (1).jpg", 390_000, "2024-02-18T10:00:00.000Z"),
            ],
            start=1,
        ):
            file_id = f"demo-exact-{index}"
            color = (32, 140, 150) if index == 1 else (40, 150, 160)
            thumbs[file_id] = _make_demo_jpeg(
                color=color,
                label="Beach",
                subtitle=name,
                size=(1200 if index == 1 else 1000, 800 if index == 1 else 700),
            )
            images.append(
                DriveImage(
                    id=file_id,
                    name=name,
                    mime_type="image/jpeg",
                    size=size,
                    width=1200 if index == 1 else 1000,
                    height=800 if index == 1 else 700,
                    content_hash="demo-exact-hash",
                    md5_checksum="demo-exact-hash",
                    perceptual_hash="ffffffffffffffff",
                    created_time=created,
                    web_view_link="https://drive.google.com",
                )
            )
            self._update(job_id, current=index, total=6)

        # Similar (near-duplicate) set with close perceptual hashes.
        similar_specs = [
            ("trail-morning.png", (210, 120, 70), "ffffffffffffffff"),
            ("trail-morning-edit.png", (200, 125, 80), "fffffffffffffffe"),
            ("IMG_8841.png", (205, 118, 75), "fffffffffffffffc"),
        ]
        for offset, (name, color, phash) in enumerate(similar_specs, start=1):
            file_id = f"demo-similar-{offset}"
            thumbs[file_id] = _make_demo_jpeg(
                color=color,
                label="Trail",
                subtitle=name,
                size=(1600 if offset == 1 else 1400, 1066 if offset == 1 else 900),
            )
            images.append(
                DriveImage(
                    id=file_id,
                    name=name,
                    mime_type="image/png",
                    size=510_000 - offset * 20_000,
                    width=1600 if offset == 1 else 1400,
                    height=1066 if offset == 1 else 900,
                    content_hash=hashlib.md5(name.encode()).hexdigest(),
                    perceptual_hash=phash,
                    created_time=f"2021-0{offset}-15T08:00:00.000Z",
                    web_view_link="https://drive.google.com",
                )
            )
            self._update(job_id, current=3 + offset, total=6, message="Hashing demo images…")

        with self._lock:
            self._demo_thumbs.update(thumbs)

        self._update(job_id, message="Finding duplicates…")
        return find_duplicates(images, include_similar=True, max_distance=5)


def _make_demo_jpeg(
    *,
    color: tuple[int, int, int],
    label: str,
    subtitle: str,
    size: tuple[int, int],
) -> bytes:
    width, height = size
    image = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(image)
    # Soft diagonal wash for atmosphere.
    overlay = Image.new("RGB", (width, height), (255, 255, 255))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.polygon(
        [(0, 0), (width, 0), (width, height // 2), (0, height)],
        fill=(245, 240, 230),
    )
    image = Image.blend(image, overlay, 0.18)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((48, height // 2 - 24), label, fill=(250, 250, 248), font=font)
    draw.text((48, height // 2 + 8), subtitle[:40], fill=(245, 245, 240), font=font)
    out = io.BytesIO()
    image.thumbnail((480, 480), Image.Resampling.LANCZOS)
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


scan_manager = ScanManager()
