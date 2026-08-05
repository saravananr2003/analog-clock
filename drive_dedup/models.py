"""Data models for Drive image duplicate detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


IMAGE_MIME_PREFIXES = ("image/",)
IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
    ".tiff",
    ".tif",
    ".heic",
    ".heif",
}


@dataclass
class DriveImage:
    """Metadata and fingerprints for a Drive image file."""

    id: str
    name: str
    mime_type: str
    size: int
    md5_checksum: Optional[str] = None
    created_time: Optional[str] = None
    modified_time: Optional[str] = None
    parents: list[str] = field(default_factory=list)
    web_view_link: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    perceptual_hash: Optional[str] = None
    content_hash: Optional[str] = None

    @property
    def pixel_count(self) -> int:
        if self.width and self.height:
            return self.width * self.height
        return 0

    @property
    def display_size(self) -> str:
        if self.size < 1024:
            return f"{self.size} B"
        if self.size < 1024 * 1024:
            return f"{self.size / 1024:.1f} KB"
        return f"{self.size / (1024 * 1024):.2f} MB"


@dataclass
class DuplicateGroup:
    """A set of images considered duplicates of each other."""

    group_id: int
    match_type: str  # "exact" or "similar"
    keep: DriveImage
    remove: list[DriveImage] = field(default_factory=list)
    reason: str = ""

    @property
    def members(self) -> list[DriveImage]:
        return [self.keep, *self.remove]

    @property
    def reclaimable_bytes(self) -> int:
        return sum(img.size for img in self.remove)
