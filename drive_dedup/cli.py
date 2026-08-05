"""Command-line interface for Google Drive image deduplication."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from drive_dedup import __version__
from drive_dedup.auth import build_drive_service
from drive_dedup.drive_client import DriveClient
from drive_dedup.duplicates import find_duplicates, format_bytes
from drive_dedup.models import DuplicateGroup

console = Console()


def _print_groups(groups: list[DuplicateGroup]) -> None:
    if not groups:
        console.print("[green]No duplicate images found.[/green]")
        return

    total_remove = sum(len(g.remove) for g in groups)
    reclaimable = sum(g.reclaimable_bytes for g in groups)
    console.print(
        f"\nFound [bold]{len(groups)}[/bold] duplicate group(s), "
        f"[bold]{total_remove}[/bold] file(s) recommended for removal "
        f"([cyan]{format_bytes(reclaimable)}[/cyan] reclaimable).\n"
    )

    for group in groups:
        table = Table(
            title=f"Group {group.group_id} — {group.match_type.upper()} — {group.reason}",
            show_lines=True,
        )
        table.add_column("Action", style="bold")
        table.add_column("Name")
        table.add_column("Size")
        table.add_column("Resolution")
        table.add_column("File ID")
        table.add_column("Link")

        keep = group.keep
        res = f"{keep.width}x{keep.height}" if keep.width and keep.height else "?"
        table.add_row(
            "[green]KEEP[/green]",
            keep.name,
            keep.display_size,
            res,
            keep.id,
            keep.web_view_link or "",
        )
        for img in group.remove:
            res = f"{img.width}x{img.height}" if img.width and img.height else "?"
            table.add_row(
                "[red]REMOVE[/red]",
                img.name,
                img.display_size,
                res,
                img.id,
                img.web_view_link or "",
            )
        console.print(table)
        console.print()


def _save_report(groups: list[DuplicateGroup], path: Path) -> None:
    payload = []
    for group in groups:
        payload.append(
            {
                "group_id": group.group_id,
                "match_type": group.match_type,
                "reason": group.reason,
                "keep": {
                    "id": group.keep.id,
                    "name": group.keep.name,
                    "size": group.keep.size,
                    "link": group.keep.web_view_link,
                },
                "remove": [
                    {
                        "id": img.id,
                        "name": img.name,
                        "size": img.size,
                        "link": img.web_view_link,
                    }
                    for img in group.remove
                ],
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    console.print(f"Report saved to [cyan]{path}[/cyan]")


@click.group()
@click.version_option(__version__, prog_name="drive-dedup")
def main() -> None:
    """Find and remove duplicate images on Google Drive."""


@main.command("scan")
@click.option(
    "--folder-id",
    default=None,
    help="Optional Drive folder ID to limit the scan.",
)
@click.option(
    "--credentials",
    "credentials_path",
    type=click.Path(path_type=Path),
    default=Path("credentials/credentials.json"),
    show_default=True,
    help="Path to OAuth client secrets JSON.",
)
@click.option(
    "--token",
    "token_path",
    type=click.Path(path_type=Path),
    default=Path("credentials/token.json"),
    show_default=True,
    help="Path to cached OAuth token JSON.",
)
@click.option(
    "--exact-only",
    is_flag=True,
    help="Only detect exact byte/content duplicates (skip perceptual matching).",
)
@click.option(
    "--threshold",
    default=5,
    show_default=True,
    help="Max perceptual-hash Hamming distance for similar images (0–64).",
)
@click.option(
    "--skip-download",
    is_flag=True,
    help="Use Drive md5Checksum only; do not download for perceptual hashing.",
)
@click.option(
    "--report",
    type=click.Path(path_type=Path),
    default=Path("reports/duplicates.json"),
    show_default=True,
    help="Where to write the JSON recommendation report.",
)
@click.option(
    "--remove",
    "do_remove",
    is_flag=True,
    help="After showing recommendations, prompt to trash recommended files.",
)
@click.option(
    "--yes",
    is_flag=True,
    help="Skip the interactive confirmation prompt (use with --remove).",
)
def scan(
    folder_id: Optional[str],
    credentials_path: Path,
    token_path: Path,
    exact_only: bool,
    threshold: int,
    skip_download: bool,
    report: Path,
    do_remove: bool,
    yes: bool,
) -> None:
    """Scan Drive for duplicate images and recommend removals."""
    console.print("[bold]Google Drive Image Deduplicator[/bold]")
    console.print("Authenticating…")
    service = build_drive_service(
        credentials_path=credentials_path,
        token_path=token_path,
    )
    client = DriveClient(service)

    console.print("Listing images from Google Drive…")
    images = client.list_images(
        folder_id=folder_id,
        progress=lambda n: console.print(f"  listed {n} image(s)", end="\r"),
    )
    console.print(f"\nFound [bold]{len(images)}[/bold] image(s).")

    if not images:
        return

    compute_perceptual = not exact_only and not skip_download
    needs_download = compute_perceptual or any(
        not (img.md5_checksum or img.content_hash) for img in images
    )

    if needs_download:
        console.print(
            "Downloading images to compute hashes"
            + (" (perceptual + content)" if compute_perceptual else " (content)")
            + "…"
        )

        def _progress(done: int, total: int) -> None:
            console.print(f"  hashed {done}/{total}", end="\r")

        client.enrich_with_hashes(
            images,
            compute_perceptual=compute_perceptual,
            progress=_progress,
        )
        console.print()
    else:
        for img in images:
            if img.md5_checksum and not img.content_hash:
                img.content_hash = img.md5_checksum
        console.print("Using Drive md5Checksum for exact matching (no downloads).")

    groups = find_duplicates(
        images,
        include_similar=not exact_only and not skip_download,
        max_distance=threshold,
    )
    _print_groups(groups)
    _save_report(groups, report)

    if not groups:
        return

    if not do_remove:
        console.print(
            "Review the recommendations above. To trash recommended files, re-run with "
            "[cyan]--remove[/cyan] (you will be asked to confirm)."
        )
        return

    remove_ids = [img.id for g in groups for img in g.remove]
    remove_names = {img.id: img.name for g in groups for img in g.remove}
    reclaimable = sum(g.reclaimable_bytes for g in groups)

    console.print(
        f"About to move [red]{len(remove_ids)}[/red] file(s) to Trash "
        f"([cyan]{format_bytes(reclaimable)}[/cyan])."
    )
    if not yes:
        if not Confirm.ask("Confirm removal of recommended duplicates?", default=False):
            console.print("[yellow]Aborted. No files were changed.[/yellow]")
            return

    console.print("Moving files to Trash…")
    success, failures = client.trash_files(
        remove_ids,
        progress=lambda done, total: console.print(f"  trashed {done}/{total}", end="\r"),
    )
    console.print()
    console.print(f"[green]Moved {len(success)} file(s) to Trash.[/green]")
    if failures:
        console.print(f"[red]Failed to trash {len(failures)} file(s):[/red]")
        for file_id, err in failures:
            console.print(f"  - {remove_names.get(file_id, file_id)}: {err}")
    else:
        console.print("You can restore them from Google Drive Trash if needed.")


@main.command("remove-from-report")
@click.option(
    "--report",
    type=click.Path(exists=True, path_type=Path),
    default=Path("reports/duplicates.json"),
    show_default=True,
    help="JSON report previously written by the scan command.",
)
@click.option(
    "--credentials",
    "credentials_path",
    type=click.Path(path_type=Path),
    default=Path("credentials/credentials.json"),
    show_default=True,
)
@click.option(
    "--token",
    "token_path",
    type=click.Path(path_type=Path),
    default=Path("credentials/token.json"),
    show_default=True,
)
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
@click.option(
    "--group",
    "group_ids",
    multiple=True,
    type=int,
    help="Only remove from specific group id(s). Repeatable.",
)
def remove_from_report(
    report: Path,
    credentials_path: Path,
    token_path: Path,
    yes: bool,
    group_ids: tuple[int, ...],
) -> None:
    """Trash recommended files from a previous scan report after confirmation."""
    data = json.loads(report.read_text(encoding="utf-8"))
    selected = data
    if group_ids:
        wanted = set(group_ids)
        selected = [g for g in data if g.get("group_id") in wanted]

    remove_items = []
    for group in selected:
        remove_items.extend(group.get("remove") or [])

    if not remove_items:
        console.print("[yellow]No removable files in the selected report groups.[/yellow]")
        return

    table = Table(title="Files recommended for removal", show_lines=True)
    table.add_column("Name")
    table.add_column("Size")
    table.add_column("File ID")
    for item in remove_items:
        size = item.get("size") or 0
        table.add_row(item.get("name", "?"), format_bytes(int(size)), item.get("id", ""))
    console.print(table)

    if not yes:
        if not Confirm.ask(
            f"Move {len(remove_items)} recommended duplicate(s) to Trash?",
            default=False,
        ):
            console.print("[yellow]Aborted. No files were changed.[/yellow]")
            return

    service = build_drive_service(
        credentials_path=credentials_path,
        token_path=token_path,
    )
    client = DriveClient(service)
    ids = [item["id"] for item in remove_items if item.get("id")]
    success, failures = client.trash_files(ids)
    console.print(f"[green]Moved {len(success)} file(s) to Trash.[/green]")
    if failures:
        console.print(f"[red]Failed: {len(failures)}[/red]")
        for file_id, err in failures:
            console.print(f"  - {file_id}: {err}")


if __name__ == "__main__":
    main()
