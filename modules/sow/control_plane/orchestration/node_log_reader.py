"""Read the durable node event log WITHOUT opening it for append.

EPC-03 L3-5. Presence needs to know which panes the registry has recorded. The obvious way -
construct an `AppendOnlyEventLog` and read it - is forbidden here, and the reason is written
into that class's own caller:

    "each caches `prev_hash` at open time, so two PROCESSES appending would write duplicate
     `seq` values and break the chain permanently. Since `AppendOnlyEventLog` refuses to open a
     corrupt log and a failed registration refuses the session, that would wedge the whole
     governed-probe path with no repair an append-only log permits."

`AppendOnlyEventLog.__init__` opens the file in append mode. A reader that constructed one
while the app held it would be the second opener that comment describes. So this module parses
the JSONL directly, opens read-only, and never takes the registrar's lock.

It is deliberately tolerant. A log that cannot be parsed yields no panes rather than an
exception: this feeds the operator's conductor surface, and a malformed row must not take that
surface down. It is also deliberately NOT a verifier - `event_log.verify_file` owns chain
integrity, and duplicating that check here would create a second opinion about whether the
operator's history is sound.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

#: Terminal states. A node that reached one is not a pane a conductor may address, whatever the
#: last row said about its pid.
_CLOSED_STATES = frozenset({"CLOSED", "RELEASED", "TERMINATED", "FAILED", "GONE"})


def read_node_rows(log_path: str | Path) -> list[dict[str, Any]]:
    """Every well-formed row in the log, oldest first. Never raises."""
    path = Path(log_path)
    rows: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _record_of(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("data")
    if not isinstance(data, dict):
        return {}
    record = data.get("node_record")
    return record if isinstance(record, dict) else {}


def _node_key(row: dict[str, Any], data: dict[str, Any], record: dict[str, Any]) -> str:
    """The STABLE identity of the node this row is about.

    The row's own top-level `node_id` first, and that ordering is the whole correctness of this
    module. Measured against the operator's real store, 2026-09-01: 102 rows, three kinds, and
    only ONE field common to all three -

        spawn       data={adapter, node_record{node_id: <uuid>}, pid, session_id, ...}
        transition  data={frm, to, reason}
        exit        data={exit_code, expected}

    `data.node_key` is absent on every one of them, and `node_record.node_id` is a per-INCARNATION
    uuid that appears only on spawn rows. Preferring it - which this function used to do - keyed
    every spawn under a fresh uuid while the transitions and exits that carry the state and the
    pid keyed under `worker-pane-N`. Nothing ever joined.

    The visible cost, on the operator's own log: 36 phantom nodes reported, every one stuck at
    SPAWNING with pid None, when the truth was two panes, both READY, both with live pids. A
    surface built to stop the conductor guessing would have been guessing differently.
    """
    for candidate in (row.get("node_id"), data.get("node_key"), record.get("node_id")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def latest_pane_state(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold the event log into one current row per node, newest wins.

    An append-only log records a HISTORY: a pane is spawned SPAWNING, attested with a pid, and
    transitions to READY, and every one of those rows is permanent. The current state is the last
    row for that node, never the first one found - reading the first is how a pane stays SPAWNING
    forever in a surface that claims to show what is up now.

    A `transition` row carries the new state in `data.to`, which is the only place it appears;
    a fold that reads only `node_record.state` sees the spawn-time value for ever.
    """
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        record = _record_of(row)
        node_key = _node_key(row, data, record)
        if not node_key:
            continue
        pid = data.get("pid")
        previous = latest.get(node_key, {})
        # Order matters: a transition's `to` is NEWER than the spawn record's `state`.
        state = (data.get("to") or record.get("state") or data.get("state")
                 or previous.get("state") or "UNKNOWN")
        latest[node_key] = {
            "node_id": node_key,
            "state": state,
            # A pid, once attested, is not un-attested by a later row that omits the field.
            "pid": pid if isinstance(pid, int) and pid > 0 else previous.get("pid"),
            "model": (record.get("model_ref") or data.get("model")
                      or previous.get("model")),
            "adapter": record.get("adapter") or data.get("adapter") or previous.get("adapter"),
            "locality": record.get("locality") or previous.get("locality"),
            "node_class": record.get("class") or data.get("node_class") or previous.get("node_class"),
            "incarnation": row.get("incarnation") or previous.get("incarnation"),
        }
    return [r for r in latest.values()
            if str(r.get("state") or "").upper() not in _CLOSED_STATES]


def pane_records(log_path: str | Path) -> list[dict[str, Any]]:
    """The rows `pane_presence` folds. One call for the whole read."""
    return latest_pane_state(read_node_rows(log_path))


class _Row:
    """Attribute view over a folded row, which is the shape `presence_from_records` reads."""

    def __init__(self, data: dict[str, Any]) -> None:
        for key, value in data.items():
            setattr(self, key, value)


def pane_records_as_objects(log_path: str | Path) -> list[_Row]:
    return [_Row(r) for r in pane_records(log_path)]
