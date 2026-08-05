"""Serializer unit tests."""

from drive_dedup.models import DriveImage, DuplicateGroup
from drive_dedup.serializer import group_to_dict, groups_summary


def test_group_to_dict_includes_thumbnail_urls() -> None:
    keep = DriveImage(
        id="keep1",
        name="a.jpg",
        mime_type="image/jpeg",
        size=1000,
        width=100,
        height=100,
    )
    drop = DriveImage(
        id="drop1",
        name="b.jpg",
        mime_type="image/jpeg",
        size=900,
        width=90,
        height=90,
    )
    group = DuplicateGroup(
        group_id=1,
        match_type="exact",
        keep=keep,
        remove=[drop],
        reason="test",
    )
    payload = group_to_dict(group)
    assert payload["images"][0]["action"] == "keep"
    assert payload["images"][1]["action"] == "remove"
    assert payload["images"][0]["thumbnail_url"] == "/api/thumbnail/keep1"
    summary = groups_summary([group])
    assert summary["remove_count"] == 1
    assert summary["reclaimable_bytes"] == 900
