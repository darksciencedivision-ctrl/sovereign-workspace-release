"""APPROVAL-DRAWER feed emitter, sourced from REAL SESSION EVENTS — Phase 17D `.events` (OP-11 §16).

The operator's drawer must show what THIS session produced and nothing else. Until 17D this emitter
built the drawer from a canned objective and two canned commands, so a freshly launched shell showed
three pending approvals nobody had asked for (finding F2). It now folds the shell's append-only
session-approval log (`--events <path>`, written by `apps/desktop/approvals/session-events.js`)
through `control_plane.orchestration.session_approvals`, which re-derives every row with the same
classifiers that decided it live. **No events ⇒ an empty drawer.** There is no path here that invents
a row; the retired demonstration builder now lives under `tests/support/demo_approval_queue.py`.

No log path (or a missing file) is the ordinary first-launch state — an empty session, emitted as an
empty drawer with `sourced:true`. Fail-closed (invariant 3 / invariant 20 spirit): a log that cannot
be read or re-derived in full ⇒ the unavailable feed (`sourced:false`, `reason`, empty drawer), a
0-exit JSON line the shell renders as "approvals unavailable", never a fabricated pending item.

Cheap and side-effect-free by construction (D-LOOP-1): re-deriving recorded events starts no MCP
server, no flow, no engine, makes no live call (§2.2/§2.4) and writes nothing.

`--emit-approval-drawer` prints ONLY the feed JSON (the stable shell contract, one line).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Run as a script (`py -3.12 tools/live/emit_approval_drawer.py`) — put the repo root on sys.path
# exactly as the sibling emitters do so the shell can invoke this directly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.orchestration.session_approvals import (  # noqa: E402
    build_session_drawer_feed,
    read_session_events,
    unavailable_session_feed,
)


def _arg(argv: list[str], flag: str, default: str = "") -> str:
    """Read `--flag value` from argv, fail-closed to `default` if absent/trailing."""
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def emit(events_path: str) -> dict:
    """Read the session-approval log (if any) and fold it into the drawer feed."""
    try:
        events = read_session_events(events_path) if events_path else []
    except Exception as exc:  # noqa: BLE001 — an unreadable log is unavailable, never faked
        return unavailable_session_feed(f"{type(exc).__name__}: {exc}")
    return build_session_drawer_feed(events)


def main(argv: list[str]) -> int:
    if "--emit-approval-drawer" in argv:
        sys.stdout.write(json.dumps(emit(_arg(argv, "--events")), default=str) + "\n")
        return 0
    sys.stderr.write(
        "usage: emit_approval_drawer.py --emit-approval-drawer [--events <session-events.jsonl>]\n"
        "  prints the approval_drawer_feed@1.1 JSON the shell renders, folded from the session's own\n"
        "  recorded approval events (Phase 17D .events). No log ⇒ an empty drawer.\n"
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised via tests calling main()
    raise SystemExit(main(sys.argv[1:]))
