"""One-time, copy-only migration of install-tree state into the external state home (SW-25).

Before SW-25, SOVEREIGN kept its mutable state beneath the install root:
``<root>/runtime``, ``<root>/published`` and ``<root>/library/queues``. When the
install declares the external layout (``STATE_LAYOUT.json``) or the launcher passes
``SOVEREIGN_STATE_HOME``, that state now lives in the state home instead. The first
process that needs it calls :func:`ensure_state_home`, which COPIES each legacy
piece across (operator decision: copy, never move, so a rollback to an older build
still finds its own state) and then writes ``STATE_MIGRATION.json``. The receipt's
presence means "done"; later calls are a cheap no-op.

Crash safety: each piece is copied into ``<home>/.migration-staging/`` and then
renamed into place, so a destination is either absent/empty or complete. A
destination that already holds data is never overwritten; the receipt records it
as ``skipped_destination_not_empty``. Leftover staging from an interrupted run is
discarded and redone.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .paths import resolve_state_home

MIGRATION_RECEIPT = "STATE_MIGRATION.json"
STAGING_DIRNAME = ".migration-staging"
# Legacy piece -> the same relative location under the state home.
LEGACY_PIECES = ("runtime", "published", "library/queues")
# Provisioned install ASSETS that happen to live under <root>/runtime (operator decision 3: the
# llama.cpp binary stays in the install tree). They are not state and are not copied.
ASSET_EXCLUDES = ("llama.cpp",)

LOCK_FILENAME = ".migration.lock"
LOCK_WAIT_SECONDS = 60.0
LOCK_STALE_SECONDS = 600.0

_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _has_content(path: Path) -> bool:
    if not path.is_dir():
        return False
    for item in path.rglob("*"):
        if item.is_file() and item.name != ".gitkeep":
            return True
    return False


def _tree_stats(path: Path) -> dict[str, int]:
    files = 0
    size = 0
    for item in path.rglob("*"):
        if item.is_file():
            files += 1
            size += item.stat().st_size
    return {"files": files, "bytes": size}


def _ignore_assets(directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in ASSET_EXCLUDES or name == ".gitkeep"}


def _write_receipt(home: Path, payload: Mapping[str, Any]) -> None:
    target = home / MIGRATION_RECEIPT
    temporary = home / f".{MIGRATION_RECEIPT}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)


def read_receipt(home: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads((home / MIGRATION_RECEIPT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


class _MigrationLock:
    """Cross-process exclusion: the supervisor and the product server may both start first."""

    def __init__(self, home: Path) -> None:
        self.path = home / LOCK_FILENAME

    def __enter__(self) -> "_MigrationLock":
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                except OSError:
                    continue  # released between the open and the stat; retry now
                if age > LOCK_STALE_SECONDS:
                    try:
                        self.path.unlink()  # a crashed migrator's lock
                    except OSError:
                        pass
                    continue
                if time.monotonic() > deadline:
                    raise TimeoutError(f"state migration lock is held: {self.path}")
                time.sleep(0.1)
                continue
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            return self

    def __exit__(self, *exc: object) -> None:
        try:
            self.path.unlink()
        except OSError:
            pass


def ensure_state_home(
    root: str | os.PathLike[str] | Path,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Make sure the state home exists and legacy install-tree state has been copied into it.

    Returns a summary: ``{"state_home", "external", "migrated", "receipt"}``. Legacy
    layout (state home == install root) is a no-op.
    """

    product_root = Path(root).expanduser().resolve(strict=False)
    home = resolve_state_home(product_root, env=env)
    if home == product_root:
        return {"state_home": str(home), "external": False, "migrated": False, "receipt": None}

    home.mkdir(parents=True, exist_ok=True)
    existing = read_receipt(home)
    if existing is not None:
        return {"state_home": str(home), "external": True, "migrated": False,
                "receipt": existing}
    with _LOCK, _MigrationLock(home):
        existing = read_receipt(home)  # another process may have finished while we waited
        if existing is not None:
            return {"state_home": str(home), "external": True, "migrated": False,
                    "receipt": existing}

        staging = home / STAGING_DIRNAME
        if staging.exists():
            shutil.rmtree(staging)  # an interrupted earlier run; redo it from the source
        pieces: dict[str, Any] = {}
        for piece in LEGACY_PIECES:
            source = product_root.joinpath(*piece.split("/"))
            destination = home.joinpath(*piece.split("/"))
            if not _has_content(source):
                pieces[piece] = {"status": "no_legacy_state"}
                continue
            if _has_content(destination):
                pieces[piece] = {"status": "skipped_destination_not_empty"}
                continue
            staged = staging / piece.replace("/", "__")
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, staged, ignore=_ignore_assets)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                # Empty (or .gitkeep-only) placeholder, e.g. created by the shell from the
                # adapter's runtime_writes before the module launched.
                shutil.rmtree(destination)
            os.replace(staged, destination)
            pieces[piece] = {"status": "copied", "source": str(source), **_tree_stats(destination)}
        if staging.exists():
            shutil.rmtree(staging)

        receipt = {
            "schema": 1,
            "kind": "sovereign-state-migration",
            "mode": "copy",
            "migrated_from": str(product_root),
            "state_home": str(home),
            "completed_utc": _utc_now(),
            "pieces": pieces,
        }
        _write_receipt(home, receipt)
        return {"state_home": str(home), "external": True, "migrated": True, "receipt": receipt}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m sovereign_product.state_migration")
    parser.add_argument("--root", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(ensure_state_home(args.root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
