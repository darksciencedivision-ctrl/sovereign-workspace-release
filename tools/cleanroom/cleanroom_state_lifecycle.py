"""Clean-room SW-25 proof: a READ-ONLY install runs its state lifecycle against an external root.

Run by Test-CleanRoomBoot.ps1 against the extracted (and read-only) distribution, with the system
Python 3.12 - every module exercised here is stdlib-only, so no venv is needed:

    python cleanroom_state_lifecycle.py --root <dist>/modules/sovereign --work <scratch dir>

The state root is pointed at <work>/ws via SOVEREIGN_WORKSPACE_STATE, so the operator's real
%LOCALAPPDATA% is never touched. Steps (any failure -> exit 1 with the failing step named):

  1. launch-state   ensure_state_home creates + version-stamps an external state home
  2. assign-model   a model assignment lands in the operator overrides and is effective,
                    while the read-only shipped manifest is untouched
  3. write-state    the product database is written in the external runtime dir
  4. backup         state_admin backup produces a verified archive
  5. damage         the database and overrides are altered/removed
  6. rollback       state stamped by a NEWER build (schema 99) is refused, fail closed
  7. restore        state_admin restore brings back the database and the override, keeps the
                    replaced home, and the restored home opens again

The caller separately proves no file in the extracted distribution changed.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--work", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    os.environ["SOVEREIGN_WORKSPACE_STATE"] = str(work / "ws")
    for key in ("SOVEREIGN_STATE_HOME", "SOVEREIGN_STATE_DIR", "SOVEREIGN_EVIDENCE_DIR",
                "SOVEREIGN_DB_PATH"):
        os.environ.pop(key, None)
    sys.path.insert(0, str(root))

    from sovereign_product import manifest_overrides as mo
    from sovereign_product import paths
    from sovereign_product import state_admin
    from sovereign_product import state_migration as sm
    import system_manifest

    steps: list[dict] = []

    def step(name: str, ok: bool, detail: str) -> None:
        steps.append({"step": name, "ok": bool(ok), "detail": detail})
        if not ok:
            raise AssertionError(f"{name}: {detail}")

    try:
        home = paths.resolve_state_home(root)
        sm.ensure_state_home(root)
        version = sm.read_state_version(home)
        step("launch-state", home.is_dir() and not home.is_relative_to(root)
             and version is not None and version["schema"] == sm.STATE_SCHEMA,
             f"external state home {home} stamped schema {version and version['schema']}")

        manifest_path = root / "SYSTEM_MANIFEST.json"
        shipped_before = manifest_path.read_bytes()
        shipped = system_manifest.load_shipped_manifest(manifest_path=manifest_path)
        mo.write_model_overrides(root, shipped, {"CRITIC": "cleanroom-probe:1b"})
        effective = system_manifest.load_system_manifest(manifest_path=manifest_path)
        step("assign-model",
             effective["MODELS"]["CRITIC"] == "cleanroom-probe:1b"
             and manifest_path.read_bytes() == shipped_before,
             "override effective; shipped manifest bytes unchanged")

        db = paths.resolve_runtime_dir(root) / "sovereign.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(db)) as conn, conn:
            conn.execute("CREATE TABLE probe (v TEXT)")
            conn.execute("INSERT INTO probe VALUES ('before-backup')")
        step("write-state", db.is_file() and not db.is_relative_to(root), f"db at {db}")

        archive = work / "state-backup.zip"
        result = state_admin.backup(root, archive)
        step("backup", archive.is_file() and result["files"] >= 3,
             f"{result['files']} files backed up")

        with closing(sqlite3.connect(db)) as conn, conn:
            conn.execute("UPDATE probe SET v = 'damaged'")
        mo.overrides_path(root).unlink()
        step("damage", True, "db altered, overrides removed")

        (home / sm.STATE_VERSION_FILE).write_text(json.dumps({"schema": 99}), encoding="utf-8")
        try:
            sm.ensure_state_home(root)
            refused = False
        except sm.StateVersionError:
            refused = True
        step("rollback", refused, "state from a newer build refused")

        restored = state_admin.restore(root, archive)
        with closing(sqlite3.connect(db)) as conn:
            value = conn.execute("SELECT v FROM probe").fetchone()[0]
        sm.ensure_state_home(root)
        effective = system_manifest.load_system_manifest(manifest_path=manifest_path)
        step("restore",
             value == "before-backup"
             and effective["MODELS"]["CRITIC"] == "cleanroom-probe:1b"
             and restored["previous_state_kept_at"] is not None,
             f"db={value!r}, override restored, previous home kept")
    except Exception as exc:  # report, never traceback-only
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}", "steps": steps},
                         indent=2))
        return 1
    print(json.dumps({"ok": True, "steps": steps}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
