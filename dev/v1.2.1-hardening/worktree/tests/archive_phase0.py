"""Hash-verified, one-time archive move for explicitly identified phase-0 files."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "archive" / "phase0"
DESTINATION = ARCHIVE / "original_root"

TARGETS = [
    Path("CLAUDE-CODE-DIRECTIVE.md"),
    Path("CODEX-DIRECTIVE.md"),
    Path("debate_table_snapshot_20260710T233903.zip"),
    Path("phase0_closeout_20260716.zip"),
    Path("spike"),
    Path("audit/architecture_map.md"),
    Path("audit/closeout_evidence.md"),
    Path("audit/independent_review_third_model_20260717.md"),
    Path("audit/phase1_recommendation.md"),
    Path("audit/resume_session_20260715.md"),
    Path("audit/runtime_failures.md"),
    Path("audit/soak_app.stderr.log"),
    Path("audit/soak_app.stdout.log"),
    Path("audit/soak_evidence.json"),
    Path("audit/soak_report.md"),
    Path("audit/soak_restart.stderr.log"),
    Path("audit/soak_restart.stdout.log"),
    Path("audit/soak_runner.exitcode.txt"),
    Path("audit/soak_runner.stderr.log"),
    Path("audit/soak_runner.stdout.log"),
    Path("audit/sovereign_inventory.md"),
    Path("tests/run_live_soak.ps1"),
    Path("tests/test_spike_reasoning.py"),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path: Path, displayed_path: str) -> dict:
    stat = path.stat()
    return {
        "path": displayed_path,
        "size": stat.st_size,
        "sha256": digest(path),
        "mtime": datetime.fromtimestamp(
            stat.st_mtime, timezone.utc
        ).isoformat(),
        "mtime_ns": stat.st_mtime_ns,
    }


def source_files() -> list[tuple[Path, Path]]:
    files = []
    for relative in TARGETS:
        source = ROOT / relative
        if not source.exists():
            continue
        if source.is_dir():
            files.extend(
                (child, child.relative_to(ROOT))
                for child in sorted(source.rglob("*"))
                if child.is_file() and "__pycache__" not in child.parts
            )
        else:
            files.append((source, relative))
    unique = {}
    for source, relative in files:
        unique[relative.as_posix()] = (source, relative)
    return [unique[key] for key in sorted(unique)]


def main() -> int:
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    DESTINATION.mkdir(parents=True, exist_ok=True)
    sources = source_files()
    before = [
        record(source, relative.as_posix())
        for source, relative in sources
    ]
    (ARCHIVE / "MANIFEST_BEFORE.json").write_text(
        json.dumps(before, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    moved = []
    for source, relative in sources:
        destination = DESTINATION / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        moved.append((destination, relative))

    # Remove now-empty source directories only after their contents moved.
    for relative in sorted(
        {relative.parent for _, relative in sources},
        key=lambda value: len(value.parts),
        reverse=True,
    ):
        directory = ROOT / relative
        if directory != ROOT and directory.exists():
            try:
                directory.rmdir()
            except OSError:
                pass

    after = [
        {
            **record(
                destination,
                (Path("archive/phase0/original_root") / relative).as_posix(),
            ),
            "original_path": relative.as_posix(),
        }
        for destination, relative in moved
    ]
    (ARCHIVE / "MANIFEST_AFTER.json").write_text(
        json.dumps(after, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    after_by_original = {item["original_path"]: item for item in after}
    failures = []
    for item in before:
        archived = after_by_original.get(item["path"])
        if not archived or any(
            archived[key] != item[key] for key in ("size", "sha256", "mtime_ns")
        ):
            failures.append(item["path"])
    verification = {
        "verified": not failures,
        "file_count": len(before),
        "failures": failures,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    (ARCHIVE / "VERIFICATION.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if verification["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
