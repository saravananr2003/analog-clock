"""Duplicate detection and keep/remove recommendation logic."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

import imagehash

from drive_dedup.models import DriveImage, DuplicateGroup

COPY_NAME_RE = re.compile(
    r"(copy of\s+|[\s_-]\(\d+\)|[\s_-]copy(?:\s*\d+)?)",
    re.IGNORECASE,
)


def _name_score(name: str) -> int:
    """Higher is better. Prefer names that do not look like copies."""
    score = 0
    if COPY_NAME_RE.search(name):
        score -= 50
    # Prefer shorter, cleaner names slightly.
    score -= min(len(name), 80) // 10
    return score


def choose_keeper(images: list[DriveImage]) -> DriveImage:
    """Pick the image to keep from a duplicate set.

    Preference order:
      1. Highest resolution (pixel count)
      2. Largest file size
      3. Cleaner filename (not "Copy of …")
      4. Oldest created time (likely original)
      5. Stable id tie-breaker
    """
    def sort_key(img: DriveImage) -> tuple:
        return (
            img.pixel_count,
            img.size,
            _name_score(img.name),
            # Invert created_time so older ranks higher when sorted reverse.
            -(_timestamp_key(img.created_time)),
            img.id,
        )

    return max(images, key=sort_key)


def _timestamp_key(value: str | None) -> int:
    if not value:
        return 0
    # ISO8601 like 2024-01-01T12:00:00.000Z — lexicographic sort works,
    # but we map to an int-ish key for the negated sort above.
    digits = re.sub(r"\D", "", value)
    try:
        return int(digits[:14]) if digits else 0
    except ValueError:
        return 0


def find_exact_duplicates(images: Iterable[DriveImage]) -> list[DuplicateGroup]:
    """Group images that share the same content hash / Drive md5Checksum."""
    by_hash: dict[str, list[DriveImage]] = defaultdict(list)
    for image in images:
        digest = image.content_hash or image.md5_checksum
        if digest:
            by_hash[digest].append(image)

    groups: list[DuplicateGroup] = []
    group_id = 1
    for digest, members in by_hash.items():
        if len(members) < 2:
            continue
        keep = choose_keeper(members)
        remove = [m for m in members if m.id != keep.id]
        groups.append(
            DuplicateGroup(
                group_id=group_id,
                match_type="exact",
                keep=keep,
                remove=remove,
                reason=f"Identical content hash ({digest[:12]}…)",
            )
        )
        group_id += 1
    return groups


def find_similar_duplicates(
    images: Iterable[DriveImage],
    max_distance: int = 5,
    already_grouped_ids: set[str] | None = None,
) -> list[DuplicateGroup]:
    """Group near-duplicate images by perceptual hash Hamming distance.

    Images already claimed by exact-match groups are skipped so we do not
    double-recommend the same removal.
    """
    already_grouped_ids = already_grouped_ids or set()
    candidates = [
        img
        for img in images
        if img.perceptual_hash and img.id not in already_grouped_ids
    ]

    # Union-find style clustering via pairwise comparison.
    parent = {img.id: img.id for img in candidates}
    by_id = {img.id: img for img in candidates}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    hashed = [(img, imagehash.hex_to_hash(img.perceptual_hash)) for img in candidates]
    for i, (img_a, hash_a) in enumerate(hashed):
        for img_b, hash_b in hashed[i + 1 :]:
            if hash_a - hash_b <= max_distance:
                union(img_a.id, img_b.id)

    clusters: dict[str, list[DriveImage]] = defaultdict(list)
    for img_id in parent:
        clusters[find(img_id)].append(by_id[img_id])

    groups: list[DuplicateGroup] = []
    group_id = 1
    for members in clusters.values():
        if len(members) < 2:
            continue
        keep = choose_keeper(members)
        remove = [m for m in members if m.id != keep.id]
        groups.append(
            DuplicateGroup(
                group_id=group_id,
                match_type="similar",
                keep=keep,
                remove=remove,
                reason=f"Visually similar (pHash distance ≤ {max_distance})",
            )
        )
        group_id += 1
    return groups


def find_duplicates(
    images: list[DriveImage],
    include_similar: bool = True,
    max_distance: int = 5,
) -> list[DuplicateGroup]:
    """Find exact and optionally similar duplicate groups."""
    exact = find_exact_duplicates(images)
    exact_ids = {img.id for group in exact for img in group.members}

    similar: list[DuplicateGroup] = []
    if include_similar:
        similar = find_similar_duplicates(
            images,
            max_distance=max_distance,
            already_grouped_ids=exact_ids,
        )
        # Renumber similar groups to continue after exact groups.
        offset = len(exact)
        for group in similar:
            group.group_id += offset

    return exact + similar


def format_bytes(num: int) -> str:
    if num < 1024:
        return f"{num} B"
    if num < 1024 * 1024:
        return f"{num / 1024:.1f} KB"
    if num < 1024 * 1024 * 1024:
        return f"{num / (1024 * 1024):.2f} MB"
    return f"{num / (1024 * 1024 * 1024):.2f} GB"
