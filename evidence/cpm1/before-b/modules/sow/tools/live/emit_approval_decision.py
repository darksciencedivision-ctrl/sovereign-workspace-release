"""APPROVAL-DECISION router emitter, over the session-event queue — Phase 17D `.events` (OP-11 §16).

The operator's Approve/Reject on a drawer row routes back to the GOVERNED authority
(`ApprovalQueue.resolve`), self-authorizing nothing (invariant 1). This emitter is that route: it
rebuilds the queue from the SAME recorded session events the drawer was folded from (`--events`) and
calls `ApprovalQueue.resolve(item, operator, decision)`, which enforces operator-only authority
(invariant 1) and refuses an approve of a non-approvable item (invariant 16, no override path). The
shell (Node) never decides — it forwards `--item`/`--decision` and this Python authority resolves or
refuses.

On a RESOLVE the feed carries the `decision_event` the shell must append to its log — minted by the
authority that made the decision, so the shell never authors a decision record of its own, and so the
resolve PERSISTS: every later rebuild replays it through `ApprovalQueue.resolve` and the decided item
stops appearing in the drawer. A governed REFUSAL mints nothing (there is nothing to persist).

Still owed and stated on every feed (`side_effects_owed`): the downstream effect of an APPROVE — the
broker executing the queued command, `ObjectiveIntake` assigning an approved plan — is not fired from
this decide path.

No live call, no credential, no network, no MCP server (§2.2/§2.4, D-LOOP-1). A GOVERNED refusal is a
well-formed `resolved:false, refused:true` feed — honest, not a crash. A fault fails closed to
`resolved:false, unavailable:true`. `--emit-approval-decision` prints ONLY the feed JSON (one line).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Run as a script — put the repo root on sys.path exactly as the sibling emitters do.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.orchestration.session_approvals import (  # noqa: E402
    SESSION_DECISION_FEED_SCHEMA,
    read_session_events,
    route_session_decision,
)


def _arg(argv: list[str], flag: str, default: str = "") -> str:
    """Read `--flag value` from argv, fail-closed to `default` if absent/trailing."""
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def _unavailable(item_id: str, decision: str, reason: str) -> dict:
    return {
        "schema": SESSION_DECISION_FEED_SCHEMA,
        "resolved": False, "refused": False, "unavailable": True,
        "reason": reason, "item_id": item_id, "decision": decision,
        "self_authorized": False, "torn_down": True,
    }


def emit(item_id: str, decision: str, reason: str, events_path: str) -> dict:
    """Route the decision through the governed authority over the recorded session events."""
    try:
        events = read_session_events(events_path) if events_path else []
    except Exception as exc:  # noqa: BLE001 — an unreadable log is unavailable, never a resolve
        return _unavailable(item_id, decision, f"{type(exc).__name__}: {exc}")
    try:
        return route_session_decision(events=events, item_id=item_id, decision=decision, reason=reason)
    except Exception as exc:  # noqa: BLE001 — even a programming fault is reported, never faked
        return _unavailable(item_id, decision, f"{type(exc).__name__}: {exc}")


def main(argv: list[str]) -> int:
    if "--emit-approval-decision" in argv:
        out = emit(_arg(argv, "--item"), _arg(argv, "--decision"), _arg(argv, "--reason"),
                   _arg(argv, "--events"))
        sys.stdout.write(json.dumps(out, default=str) + "\n")
        return 0
    sys.stderr.write(
        "usage: emit_approval_decision.py --emit-approval-decision --item <id> "
        "--decision <approve|reject> [--reason <text>] [--events <session-events.jsonl>]\n"
        "  routes the operator's decide through the governed ApprovalQueue.resolve over the session's\n"
        "  own recorded approval events (Phase 17D .events).\n"
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised via tests calling main()
    raise SystemExit(main(sys.argv[1:]))
