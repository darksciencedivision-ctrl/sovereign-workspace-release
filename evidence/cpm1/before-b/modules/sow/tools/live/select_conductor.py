"""Persist an operator's pre-launch conductor dropdown selection in host-local runtime state."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.conductor.registry import descriptor_from_mapping  # noqa: E402
from control_plane.profiles.live_authorization import load_live_authorization  # noqa: E402

CONFIG = ROOT / "config" / "live_operation.json"


def select(raw: dict) -> dict:
    descriptor = descriptor_from_mapping(raw)
    auth = load_live_authorization()
    auth.assert_provider_live(descriptor.adapter_id)
    current = json.loads(CONFIG.read_text(encoding="utf-8"))
    current["conductor"] = {
        "provider_id": descriptor.provider_id,
        "adapter_id": descriptor.adapter_id,
        "model_id": descriptor.model_id,
        "display_name": descriptor.display_name,
        "permission_profile_id": descriptor.permission_profile_id,
        "workspace": descriptor.workspace,
    }
    fd, name = tempfile.mkstemp(prefix="live_operation.", suffix=".json", dir=CONFIG.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(current, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(name, CONFIG)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
    return {"ok": True, "descriptor": descriptor.as_dict()}


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
