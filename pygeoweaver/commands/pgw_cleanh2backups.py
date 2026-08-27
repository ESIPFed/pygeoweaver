"""CLI helpers for listing and removing H2 safety backups."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import click

from pygeoweaver.h2_utils import (
    H2_BACKUP_RETENTION_COUNT,
    cleanup_h2_backups,
    format_bytes,
    get_h2_backup_base_dir,
    list_h2_backups,
)


def print_h2_backup_list(backup_root: Optional[str] = None) -> List[dict]:
    root = backup_root or get_h2_backup_base_dir()
    backups = list_h2_backups(root)
    click.echo(f"H2 backup root: {root}")
    if not backups:
        click.echo("No H2 safety backups found.")
        return []

    click.echo(f"Found {len(backups)} backup(s) (newest first):\n")
    for item in backups:
        stamp = datetime.fromtimestamp(float(item["mtime"])).isoformat(timespec="seconds")
        flag = " [IN PROGRESS]" if item.get("in_progress") else ""
        click.echo(
            f"  {format_bytes(int(item['size_bytes'])):>10}  {stamp}  {item['path']}{flag}"
        )
    return backups


def clean_h2_backups_command(
    keep: Optional[int] = None,
    remove_all: bool = False,
    paths: Optional[List[str]] = None,
    list_only: bool = False,
    dry_run: bool = False,
    yes: bool = False,
    force: bool = False,
    backup_root: Optional[str] = None,
) -> bool:
    """
    List or delete Geoweaver H2 safety backups under ~/geoweaver/h2_backups.
    """
    root = backup_root or get_h2_backup_base_dir()
    backups = print_h2_backup_list(root)

    if list_only or (keep is None and not remove_all and not paths):
        if backups and list_only is False and keep is None and not remove_all and not paths:
            click.echo()
            click.echo("To free disk space after verifying data:")
            click.echo(f"  gw cleanh2backups --keep {H2_BACKUP_RETENTION_COUNT}   # keep newest N")
            click.echo("  gw cleanh2backups --all -y              # delete all backups")
            click.echo("  gw cleanh2backups --path DIR -y         # delete one backup dir")
        return True

    if not backups and not paths:
        return True

    action = "Would delete" if dry_run else "Delete"
    if paths:
        preview = cleanup_h2_backups(
            paths=list(paths),
            backup_root=root,
            dry_run=True,
            allow_in_progress=force,
        )
    elif remove_all:
        preview = cleanup_h2_backups(
            remove_all=True,
            backup_root=root,
            dry_run=True,
            allow_in_progress=force,
        )
    else:
        preview = cleanup_h2_backups(
            keep=keep,
            backup_root=root,
            dry_run=True,
            allow_in_progress=force,
        )

    targets = preview["deleted"] + preview["skipped_in_progress"]
    if not preview["deleted"] and not preview["skipped_in_progress"]:
        click.echo("Nothing to delete (already within retention, or paths not found).")
        return True

    click.echo()
    click.echo(f"{action} {len(preview['deleted'])} backup dir(s):")
    for path in preview["deleted"]:
        click.echo(f"  - {path}")
    if preview["skipped_in_progress"]:
        click.echo("Skipped in-progress (pass --force to remove):")
        for path in preview["skipped_in_progress"]:
            click.echo(f"  - {path}")

    if dry_run:
        click.echo("Dry run only; no files were removed.")
        return True

    if not yes:
        if not click.confirm("Proceed with deletion?", default=False):
            click.echo("Aborted.")
            return False

    result = cleanup_h2_backups(
        keep=None if (paths or remove_all) else keep,
        remove_all=remove_all,
        paths=list(paths) if paths else None,
        backup_root=root,
        dry_run=False,
        allow_in_progress=force,
    )

    click.echo(
        click.style(
            f"Removed {len(result['deleted'])} backup(s); "
            f"{len(result['remaining'])} remaining under {result['backup_root']}",
            fg="green",
        )
    )
    if result["errors"]:
        click.echo(click.style(f"Failed to remove: {result['errors']}", fg="red"))
        return False
    return True
