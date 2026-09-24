"""SW-25 (part d): versioned state, backup and restore.

Close condition for SW-25: a read-only install launches against a writable external state root,
survives upgrade/rollback, and restores from backup without changing tracked release files. The
clean-room gate proves that end to end on the extracted distribution (cleanroom_state_lifecycle.py +
the 'readonly-install' hash check). These tests inject the failures: state from a newer build, an
unreadable version stamp, tampered / traversal / mismatched / newer backups, a restore over a busy
home, secrets and pid files in a backup, and a live WAL-mode database.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SOV_ROOT = RELEASE_ROOT / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import paths as P  # noqa: E402
from sovereign_product import state_admin as SA  # noqa: E402
from sovereign_product import state_migration as M  # noqa: E402
from sovereign_version import PRODUCT_VERSION  # noqa: E402

STATE_ENV_KEYS = ("SOVEREIGN_STATE_HOME", "SOVEREIGN_STATE_DIR", "SOVEREIGN_WORKSPACE_STATE",
                  "SOVEREIGN_EVIDENCE_DIR", "SOVEREIGN_DB_PATH", "SOVEREIGN_ROOT")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for key in STATE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    local = tmp_path / "LocalAppData"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return local


def _install(tmp_path: Path, layout: str | None = "external") -> Path:
    root = tmp_path / "install root"
    root.mkdir()
    (root / P.ROOT_MARKER).write_text(P.ROOT_MARKER_CONTENT, encoding="utf-8")
    if layout:
        (root / P.STATE_LAYOUT_FILE).write_text(json.dumps({"schema": 1, "state": layout}),
                                                encoding="utf-8")
    return root


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _populated(tmp_path: Path) -> tuple[Path, Path]:
    root = _install(tmp_path)
    M.ensure_state_home(root)
    home = P.resolve_state_home(root)
    runtime = home / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(runtime / "sovereign.db")) as conn, conn:
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.execute("INSERT INTO t VALUES ('original')")
    _write(runtime / "evidence" / "quick" / "a.json", '{"a": 1}')
    _write(home / "config" / "manifest.overrides.json", '{"schema": 1, "MODELS": {}}')
    _write(runtime / "llamacpp_supervisor" / "api_key", "SECRET-KEY")
    _write(runtime / "llamacpp_supervisor" / "consumer.env", "SOVEREIGN_LLAMA_CPP_API_KEY=x")
    _write(runtime / "llamacpp_supervisor" / "AUTOSTART", "1")
    _write(runtime / "llamacpp_supervisor" / "watch.pid", "123")
    _write(runtime / "gpu_occupancy.lock", "lock")
    return root, home


def _db_value(home: Path) -> str:
    with closing(sqlite3.connect(home / "runtime" / "sovereign.db")) as conn:
        return conn.execute("SELECT v FROM t").fetchone()[0]


# --- version stamp --------------------------------------------------------------------------------

def test_sw25d_new_state_home_is_version_stamped(clean_env, tmp_path):
    root = _install(tmp_path)
    M.ensure_state_home(root)
    stamp = M.read_state_version(P.resolve_state_home(root))
    assert stamp["schema"] == M.STATE_SCHEMA
    assert stamp["created_by"] == PRODUCT_VERSION == stamp["last_opened_by"]


def test_sw25d_state_from_a_newer_build_is_refused(clean_env, tmp_path):
    root = _install(tmp_path)
    home = P.resolve_state_home(root)
    _write(home / M.STATE_VERSION_FILE, json.dumps({"schema": M.STATE_SCHEMA + 1,
                                                    "last_opened_by": "9.9.9"}))
    with pytest.raises(M.StateVersionError, match="newer than this build"):
        M.ensure_state_home(root)


@pytest.mark.parametrize("body", ["not json", "{}", '{"schema": "1"}', "[]"])
def test_sw25d_unreadable_version_stamp_fails_closed(clean_env, tmp_path, body):
    root = _install(tmp_path)
    _write(P.resolve_state_home(root) / M.STATE_VERSION_FILE, body)
    with pytest.raises(M.StateVersionError):
        M.ensure_state_home(root)


def test_sw25d_opening_with_a_new_release_records_it(clean_env, tmp_path):
    root = _install(tmp_path)
    home = P.resolve_state_home(root)
    _write(home / M.STATE_VERSION_FILE, json.dumps({"schema": 1, "created_by": "0.0.1",
                                                    "last_opened_by": "0.0.1"}))
    M.ensure_state_home(root)
    stamp = M.read_state_version(home)
    assert stamp["created_by"] == "0.0.1" and stamp["last_opened_by"] == PRODUCT_VERSION


# --- backup ---------------------------------------------------------------------------------------

def test_sw25d_backup_contents_exclude_secrets_pids_and_locks(clean_env, tmp_path):
    root, _home = _populated(tmp_path)
    archive = tmp_path / "b.zip"
    SA.backup(root, archive)
    names = set(zipfile.ZipFile(archive).namelist())
    assert "state/runtime/sovereign.db" in names
    assert "state/runtime/evidence/quick/a.json" in names
    assert "state/config/manifest.overrides.json" in names
    assert "state/runtime/llamacpp_supervisor/AUTOSTART" in names  # operator choice, kept
    assert f"state/{M.STATE_VERSION_FILE}" in names
    for secret in ("api_key", "consumer.env", "watch.pid", "gpu_occupancy.lock"):
        assert not any(n.endswith(secret) for n in names), f"{secret} leaked into the backup"


def test_sw25d_backup_snapshots_a_live_wal_database_consistently(clean_env, tmp_path):
    root = _install(tmp_path)
    M.ensure_state_home(root)
    db = P.resolve_runtime_dir(root) / "sovereign.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    live = sqlite3.connect(db)
    try:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("CREATE TABLE t (v TEXT)")
        live.execute("INSERT INTO t VALUES ('in-wal')")
        live.commit()  # committed to the WAL, not yet checkpointed into the main file
        archive = tmp_path / "b.zip"
        SA.backup(root, archive)
    finally:
        live.close()
    out = tmp_path / "extracted.db"
    out.write_bytes(zipfile.ZipFile(archive).read("state/runtime/sovereign.db"))
    with closing(sqlite3.connect(out)) as conn:
        assert conn.execute("SELECT v FROM t").fetchone()[0] == "in-wal"
    assert not any(n.endswith(("-wal", "-shm")) for n in zipfile.ZipFile(archive).namelist())


def test_sw25d_backup_refuses_to_overwrite_or_to_write_inside_the_state_home(clean_env, tmp_path):
    root, home = _populated(tmp_path)
    existing = _write(tmp_path / "exists.zip", "x")
    with pytest.raises(SA.StateAdminError):
        SA.backup(root, existing)
    with pytest.raises(SA.StateAdminError):
        SA.backup(root, home / "inside.zip")
    assert existing.read_text(encoding="utf-8") == "x"


# --- verify / restore refusals change nothing -----------------------------------------------------

def _rewrite(archive: Path, out: Path, *, mutate=None, extra: dict | None = None,
             manifest_patch=None) -> Path:
    with zipfile.ZipFile(archive) as src, zipfile.ZipFile(out, "w") as dst:
        manifest = json.loads(src.read(SA.BACKUP_MANIFEST))
        if manifest_patch:
            manifest_patch(manifest)
        for info in src.infolist():
            if info.filename == SA.BACKUP_MANIFEST:
                continue
            data = src.read(info.filename)
            if mutate and info.filename == mutate:
                data = data + b"tampered"
            dst.writestr(info.filename, data)
        for name, data in (extra or {}).items():
            dst.writestr(name, data)
        dst.writestr(SA.BACKUP_MANIFEST, json.dumps(manifest))
    return out


@pytest.mark.parametrize("case", ["tampered", "traversal", "unlisted", "newer", "not_a_zip",
                                  "no_manifest"])
def test_sw25d_bad_archives_are_refused_and_state_is_untouched(clean_env, tmp_path, case):
    root, home = _populated(tmp_path)
    good = tmp_path / "good.zip"
    SA.backup(root, good)
    bad = tmp_path / "bad.zip"
    if case == "tampered":
        _rewrite(good, bad, mutate="state/runtime/evidence/quick/a.json")
    elif case == "traversal":
        def patch(m):
            m["files"].append({"path": "../escape.txt", "sha256": "0" * 64, "size": 1})
        _rewrite(good, bad, extra={"state/../escape.txt": b"x"}, manifest_patch=patch)
    elif case == "unlisted":
        _rewrite(good, bad, extra={"state/runtime/smuggled.txt": b"x"})
    elif case == "newer":
        _rewrite(good, bad, manifest_patch=lambda m: m.update(state_schema=M.STATE_SCHEMA + 1))
    elif case == "not_a_zip":
        bad.write_bytes(b"definitely not a zip")
    else:
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("state/runtime/x.txt", "x")
    with closing(sqlite3.connect(home / "runtime" / "sovereign.db")) as conn, conn:
        conn.execute("UPDATE t SET v = 'current'")
    with pytest.raises(SA.StateAdminError):
        SA.restore(root, bad)
    assert _db_value(home) == "current"
    assert not (tmp_path / "escape.txt").exists()
    assert not list(home.parent.glob("sovereign.restoring-*"))
    assert not list(home.parent.glob("sovereign.pre-restore-*"))


def test_sw25d_restore_swaps_in_the_backup_and_keeps_the_replaced_home(clean_env, tmp_path):
    root, home = _populated(tmp_path)
    archive = tmp_path / "b.zip"
    SA.backup(root, archive)
    with closing(sqlite3.connect(home / "runtime" / "sovereign.db")) as conn, conn:
        conn.execute("UPDATE t SET v = 'damaged'")
    (home / "config" / "manifest.overrides.json").unlink()
    result = SA.restore(root, archive)
    assert _db_value(home) == "original"
    assert (home / "config" / "manifest.overrides.json").is_file()
    kept = Path(result["previous_state_kept_at"])
    assert kept.is_dir() and _db_value(kept) == "damaged"
    # Secrets were not in the backup, so they are not resurrected; the supervisor regenerates them.
    assert not (home / "runtime" / "llamacpp_supervisor" / "api_key").exists()
    M.ensure_state_home(root)  # the restored home opens


def test_sw25d_restore_over_a_busy_home_is_refused_cleanly(clean_env, tmp_path, monkeypatch):
    root, home = _populated(tmp_path)
    archive = tmp_path / "b.zip"
    SA.backup(root, archive)
    real_replace = os.replace

    def busy(src, dst):
        if Path(src) == home:
            raise PermissionError("file in use")
        return real_replace(src, dst)

    monkeypatch.setattr(SA.os, "replace", busy)
    with pytest.raises(SA.StateAdminError, match="stop the workspace"):
        SA.restore(root, archive)
    assert _db_value(home) == "original"
    assert not list(home.parent.glob("sovereign.restoring-*"))


def test_sw25d_restore_is_refused_for_an_install_tree_layout(clean_env, tmp_path):
    root = _install(tmp_path, layout=None)
    archive = tmp_path / "b.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(SA.BACKUP_MANIFEST, "{}")
    with pytest.raises(SA.StateAdminError):
        SA.restore(root, archive)


def test_sw25d_cli_reports_refusals_with_exit_code_2(clean_env, tmp_path):
    root, _home = _populated(tmp_path)
    env = {**os.environ, "PYTHONPATH": str(SOV_ROOT)}
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"nope")
    proc = subprocess.run([sys.executable, "-m", "sovereign_product.state_admin", "--root",
                           str(root), "verify", "--archive", str(bad)], cwd=str(SOV_ROOT),
                          env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2 and json.loads(proc.stderr)["ok"] is False
    out = tmp_path / "ok.zip"
    proc = subprocess.run([sys.executable, "-m", "sovereign_product.state_admin", "--root",
                           str(root), "backup", "--out", str(out)], cwd=str(SOV_ROOT),
                          env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["files"] >= 4


def test_sw25d_gate_runs_the_read_only_lifecycle_and_hash_check():
    gate = (RELEASE_ROOT / "tools" / "cleanroom" / "Test-CleanRoomBoot.ps1").read_text(
        encoding="utf-8")
    assert "cleanroom_state_lifecycle.py" in gate
    assert "'readonly-install'" in gate and "IsReadOnly = $true" in gate
    assert all(b < 128 for b in gate.encode("utf-8")), "gate script must stay ASCII"
