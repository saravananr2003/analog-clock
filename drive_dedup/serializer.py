"""Serialize domain models for the web API / JSON reports."""

from __future__ import annotations

from drive_dedup.duplicates import format_bytes
from drive_dedup.models import DriveImage, DuplicateGroup


def image_to_dict(image: DriveImage, *, action: str | None = None) -> dict:
    payload = {
        "id": image.id,
        "name": image.name,
        "mime_type": image.mime_type,
        "size": image.size,
        "size_label": image.display_size,
        "width": image.width,
        "height": image.height,
        "resolution": (
            f"{image.width}×{image.height}"
            if image.width and image.height
            else "Unknown"
        ),
        "created_time": image.created_time,
        "modified_time": image.modified_time,
        "web_view_link": image.web_view_link,
        "content_hash": image.content_hash or image.md5_checksum,
        "perceptual_hash": image.perceptual_hash,
        "thumbnail_url": f"/api/thumbnail/{image.id}",
    }
    if action is not None:
        payload["action"] = action
    return payload


def group_to_dict(group: DuplicateGroup) -> dict:
    return {
        "group_id": group.group_id,
        "match_type": group.match_type,
        "reason": group.reason,
        "reclaimable_bytes": group.reclaimable_bytes,
        "reclaimable_label": format_bytes(group.reclaimable_bytes),
        "keep": image_to_dict(group.keep, action="keep"),
        "remove": [image_to_dict(img, action="remove") for img in group.remove],
        "images": [
            image_to_dict(group.keep, action="keep"),
            *[image_to_dict(img, action="remove") for img in group.remove],
        ],
    }


def groups_summary(groups: list[DuplicateGroup]) -> dict:
    remove_count = sum(len(g.remove) for g in groups)
    reclaimable = sum(g.reclaimable_bytes for g in groups)
    return {
        "group_count": len(groups),
        "remove_count": remove_count,
        "reclaimable_bytes": reclaimable,
        "reclaimable_label": format_bytes(reclaimable),
        "groups": [group_to_dict(g) for g in groups],
    }
