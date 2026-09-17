"""Persist an operator's pre-launch conductor dropdown selection in host-local runtime state.

TWO STORES, because the two selections are different KINDS of fact (LOCAL-01 F-3, ENTRY 018).

A **frontier** selection names a provider the operator pays for, so it lives where the spend
authorization lives: `config/live_operation.json`, alongside the register row that authorizes it.
That is unchanged.

A **local** selection authorizes no spend, names no subscription and needs no credential. Writing it
into `live_operation.json` — which is what this module used to do for every selection — was three
separate defects at once:

  1. it made choosing a free local model **require the spend-authorization file to exist**, and
     under OD-31 that file is deliberately ABSENT, so the read raised `FileNotFoundError` and no
     local conductor could ever be selected;
  2. it would have had a builder CREATE that file as a side effect of an unrelated choice, which
     S-18 forbids outright and which the operator reserved to himself;
  3. it is the S-20 defect in storage form — local gated behind a frontier switch.

So a local selection is written to the gitignored runtime lane instead
(`.runtime/conductor-selection.json`), which is host-local state exactly like the file it replaces,
carries no authorization, and never enters the release candidate (the N-16 remedy, applied here).

`assert_provider_live` is likewise asserted only for frontier: it is the live/spend gate, and a
local model has nothing for it to authorize.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.local.ollama_session import OLLAMA_LOCAL_ADAPTER  # noqa: E402
from adapters.local.llamacpp import LLAMACPP_LOCAL_ADAPTER  # noqa: E402
from control_plane.conductor.registry import (  # noqa: E402
    LOCAL_CONDUCTOR_SELECTION_PATH,
    descriptor_from_mapping,
)
from control_plane.profiles.live_authorization import load_live_authorization  # noqa: E402

CONFIG = ROOT / "config" / "live_operation.json"


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Replace `path` atomically so a crash mid-write can never leave a half-parsed selection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def select(raw: dict) -> dict:
    descriptor = descriptor_from_mapping(raw)
    record = {
        "provider_id": descriptor.provider_id,
        "adapter_id": descriptor.adapter_id,
        "model_id": descriptor.model_id,
        "display_name": descriptor.display_name,
        "permission_profile_id": descriptor.permission_profile_id,
        "workspace": descriptor.workspace,
    }

    if descriptor.locality == "local" or descriptor.adapter_id in (
            OLLAMA_LOCAL_ADAPTER, LLAMACPP_LOCAL_ADAPTER):
        # No live gate: there is no spend to authorize. No `live_operation.json`: it stays absent.
        _atomic_write_json(LOCAL_CONDUCTOR_SELECTION_PATH,
                           {"schema": "local_conductor_selection@1.0", "conductor": record})
        return {"ok": True, "descriptor": descriptor.as_dict(),
                "stored_in": str(LOCAL_CONDUCTOR_SELECTION_PATH),
                "note": ("local conductor selection — no subscription, no credential, no live "
                         "authorization involved; live_operation.json is untouched")}

    auth = load_live_authorization()
    auth.assert_provider_live(descriptor.adapter_id)
    current = json.loads(CONFIG.read_text(encoding="utf-8"))
    current["conductor"] = record
    _atomic_write_json(CONFIG, current)
    return {"ok": True, "descriptor": descriptor.as_dict(), "stored_in": str(CONFIG)}


def main(argv: list[str]) -> int:
    if "--select-stdin" not in argv:
        sys.stderr.write("usage: select_conductor.py --select-stdin\n")
        return 2
    try:
        raw = json.loads(sys.stdin.read())
        sys.stdout.write(json.dumps(select(raw)) + "\n")
        return 0
    except Exception as exc:
        sys.stdout.write(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}) + "\n")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
