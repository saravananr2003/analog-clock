"""Google Drive client for listing, downloading, and trashing images."""

from __future__ import annotations

import hashlib
import io
from typing import Callable, Iterable, Optional

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image
import imagehash

from drive_dedup.models import DriveImage, IMAGE_MIME_PREFIXES


FIELDS = (
    "nextPageToken, files(id, name, mimeType, size, md5Checksum, "
    "createdTime, modifiedTime, parents, webViewLink, thumbnailLink, "
    "imageMediaMetadata(width, height))"
)


class DriveClient:
    """Thin wrapper around the Drive API focused on image deduplication."""

    def __init__(self, service) -> None:
        self.service = service

    def list_images(
        self,
        folder_id: Optional[str] = None,
        include_trashed: bool = False,
        page_size: int = 200,
        progress: Optional[Callable[[int], None]] = None,
    ) -> list[DriveImage]:
        """List image files visible to the authenticated user."""
        query_parts = ["mimeType contains 'image/'", "trashed = false"]
        if include_trashed:
            query_parts = ["mimeType contains 'image/'"]
        if folder_id:
            query_parts.append(f"'{folder_id}' in parents")

        query = " and ".join(query_parts)
        images: list[DriveImage] = []
        page_token: Optional[str] = None

        while True:
            response = (
                self.service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields=FIELDS,
                    pageSize=page_size,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            for item in response.get("files", []):
                mime = item.get("mimeType", "")
                if not any(mime.startswith(prefix) for prefix in IMAGE_MIME_PREFIXES):
                    continue
                meta = item.get("imageMediaMetadata") or {}
                images.append(
                    DriveImage(
                        id=item["id"],
                        name=item.get("name", item["id"]),
                        mime_type=mime,
                        size=int(item.get("size") or 0),
                        md5_checksum=item.get("md5Checksum"),
                        created_time=item.get("createdTime"),
                        modified_time=item.get("modifiedTime"),
                        parents=list(item.get("parents") or []),
                        web_view_link=item.get("webViewLink"),
                        width=meta.get("width"),
                        height=meta.get("height"),
                    )
                )
            if progress:
                progress(len(images))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return images

    def download_bytes(self, file_id: str, max_bytes: Optional[int] = None) -> bytes:
        """Download file content as bytes (optionally capped)."""
        request = self.service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
            if max_bytes is not None and buffer.tell() > max_bytes:
                break
        data = buffer.getvalue()
        if max_bytes is not None:
            return data[:max_bytes]
        return data

    def enrich_with_hashes(
        self,
        images: Iterable[DriveImage],
        compute_perceptual: bool = True,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> list[DriveImage]:
        """Download each image and attach content / perceptual hashes.

        Uses Drive's md5Checksum when available for exact matching so we
        only download files that still need a perceptual hash (or lack md5).
        """
        items = list(images)
        total = len(items)
        for index, image in enumerate(items, start=1):
            if image.md5_checksum:
                image.content_hash = image.md5_checksum
            try:
                raw = self.download_bytes(image.id)
            except HttpError:
                if progress:
                    progress(index, total)
                continue

            if not image.content_hash:
                image.content_hash = hashlib.md5(raw).hexdigest()

            if compute_perceptual:
                try:
                    with Image.open(io.BytesIO(raw)) as pil_image:
                        if image.width is None or image.height is None:
                            image.width, image.height = pil_image.size
                        image.perceptual_hash = str(imagehash.phash(pil_image))
                except Exception:
                    # Unsupported / corrupt image — skip perceptual hash.
                    pass

            if progress:
                progress(index, total)
        return items

    def trash_files(
        self,
        file_ids: Iterable[str],
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """Move files to Drive trash. Returns (success_ids, failures)."""
        ids = list(file_ids)
        success: list[str] = []
        failures: list[tuple[str, str]] = []
        total = len(ids)
        for index, file_id in enumerate(ids, start=1):
            try:
                self.service.files().update(
                    fileId=file_id,
                    body={"trashed": True},
                    supportsAllDrives=True,
                ).execute()
                success.append(file_id)
            except HttpError as exc:
                failures.append((file_id, str(exc)))
            if progress:
                progress(index, total)
        return success, failures

    def get_thumbnail_jpeg(
        self,
        file_id: str,
        max_edge: int = 480,
    ) -> bytes:
        """Download an image and return a JPEG thumbnail."""
        raw = self.download_bytes(file_id)
        with Image.open(io.BytesIO(raw)) as pil_image:
            image = pil_image.convert("RGB")
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85, optimize=True)
            return out.getvalue()
