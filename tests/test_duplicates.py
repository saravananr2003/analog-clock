"""Unit tests for duplicate detection and keep recommendations."""

from __future__ import annotations

from drive_dedup.duplicates import (
    choose_keeper,
    find_duplicates,
    find_exact_duplicates,
    find_similar_duplicates,
    format_bytes,
)
from drive_dedup.models import DriveImage


def _img(
    id: str,
    name: str,
    size: int = 1000,
    width: int | None = 100,
    height: int | None = 100,
    content_hash: str | None = None,
    perceptual_hash: str | None = None,
    created_time: str | None = "2024-01-01T00:00:00.000Z",
) -> DriveImage:
    return DriveImage(
        id=id,
        name=name,
        mime_type="image/jpeg",
        size=size,
        width=width,
        height=height,
        content_hash=content_hash,
        md5_checksum=content_hash,
        perceptual_hash=perceptual_hash,
        created_time=created_time,
    )


def test_choose_keeper_prefers_higher_resolution() -> None:
    low = _img("a", "a.jpg", size=5000, width=100, height=100)
    high = _img("b", "b.jpg", size=1000, width=400, height=400)
    assert choose_keeper([low, high]).id == "b"


def test_choose_keeper_prefers_cleaner_name_when_equal() -> None:
    original = _img("a", "vacation.jpg", size=2000, width=200, height=200)
    copy = _img("b", "Copy of vacation.jpg", size=2000, width=200, height=200)
    assert choose_keeper([copy, original]).id == "a"


def test_choose_keeper_prefers_older_when_otherwise_equal() -> None:
    older = _img(
        "a",
        "photo.jpg",
        size=2000,
        width=200,
        height=200,
        created_time="2020-01-01T00:00:00.000Z",
    )
    newer = _img(
        "b",
        "photo.jpg",
        size=2000,
        width=200,
        height=200,
        created_time="2024-06-01T00:00:00.000Z",
    )
    assert choose_keeper([newer, older]).id == "a"


def test_find_exact_duplicates() -> None:
    images = [
        _img("1", "one.jpg", content_hash="abc"),
        _img("2", "two.jpg", content_hash="abc"),
        _img("3", "three.jpg", content_hash="zzz"),
    ]
    groups = find_exact_duplicates(images)
    assert len(groups) == 1
    assert groups[0].match_type == "exact"
    assert {m.id for m in groups[0].members} == {"1", "2"}
    assert len(groups[0].remove) == 1


def test_find_similar_duplicates_clusters_close_hashes() -> None:
    # Two identical pHash values must cluster; a distant one must not.
    near_a = _img("1", "a.jpg", perceptual_hash="ffffffffffffffff")
    near_b = _img("2", "b.jpg", perceptual_hash="fffffffffffffffe")
    far = _img("3", "c.jpg", perceptual_hash="0000000000000000")
    groups = find_similar_duplicates([near_a, near_b, far], max_distance=5)
    assert len(groups) == 1
    assert {m.id for m in groups[0].members} == {"1", "2"}


def test_find_duplicates_skips_exact_members_in_similar() -> None:
    exact_a = _img(
        "1",
        "a.jpg",
        content_hash="same",
        perceptual_hash="ffffffffffffffff",
    )
    exact_b = _img(
        "2",
        "b.jpg",
        content_hash="same",
        perceptual_hash="ffffffffffffffff",
    )
    similar_only = _img(
        "3",
        "c.jpg",
        content_hash="other",
        perceptual_hash="fffffffffffffffe",
    )
    groups = find_duplicates([exact_a, exact_b, similar_only], include_similar=True)
    # Exact group claims 1 & 2; similar should not create a new group with them.
    exact_groups = [g for g in groups if g.match_type == "exact"]
    similar_groups = [g for g in groups if g.match_type == "similar"]
    assert len(exact_groups) == 1
    assert similar_groups == []


def test_format_bytes() -> None:
    assert format_bytes(500) == "500 B"
    assert "KB" in format_bytes(2048)
    assert "MB" in format_bytes(2 * 1024 * 1024)


def test_reclaimable_bytes() -> None:
    images = [
        _img("1", "keep.jpg", size=5000, content_hash="x"),
        _img("2", "drop.jpg", size=3000, content_hash="x"),
    ]
    groups = find_exact_duplicates(images)
    assert groups[0].reclaimable_bytes == 3000
