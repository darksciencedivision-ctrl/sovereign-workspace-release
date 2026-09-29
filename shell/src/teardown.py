"""SW-18: the shell's teardown receipt - what stopped with it, how, and what deliberately did not.

"Modules stop with the shell" is only true for the modules the shell OWNS (launched inside its Job
Object). An ATTACHED persistent service - the llama.cpp supervisor - outlives the shell by design and
is never stopped by it. At exit the shell writes one JSON receipt under its own state root so both
facts are recorded rather than implied:

    <workspace state root>/shell/logs/teardown-<utc>.json

* ``owned``    one record per module process the shell was running: graceful (exited on its own
               after the SWS_SHUTDOWN_EVENT) or forced (TerminateJobObject), its exit code, and its
               declared graceful contract. ``graceful_contract_met`` is False only when a module that
               PROMISED graceful shutdown had to be forced - the observable failure.
* ``attached`` every attached persistent service, left running (or observed down), with how to stop
               it outside the shell.

Only the newest KEEP receipts are retained. Stdlib only.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

KEEP = 20
RECEIPT_PREFIX = "teardown-"


def build_receipt(stop_records: list[dict], runners: dict) -> dict:
    """Combine the supervisor's stop records with each module's declared lifecycle."""
    owned = []
    for record in stop_records or []:
        mid = record.get("module_id")
        runner = runners.get(mid)
        adapter = getattr(runner, "adapter", {}) or {}
        contract = (adapter.get("stop") or {}).get("graceful", "none")
        graceful = bool(record.get("graceful"))
        owned.append({
            "module_id": mid,
            "graceful": graceful,
            "forced": bool(record.get("forced")),
            "exit_code": record.get("exit_code"),
            "alive_after_stop": bool(record.get("alive_after_stop")),
            "graceful_contract": contract,
            "graceful_contract_met": graceful or contract != "shutdown_event",
        })
    attached = []
    for mid, runner in sorted(runners.items()):
        if not getattr(runner, "attached", False):
            continue
        service = (getattr(runner, "adapter", {}) or {}).get("service") or {}
        attached.append({
            "module_id": mid,
            "observed_state": getattr(runner, "state", ""),
            "left_running": getattr(runner, "state", "") == "ATTACHED",
            "stopped_by_shell": False,
            "stop_hint": service.get("stop_hint", ""),
        })
    return {
        "schema": 1,
        "kind": "sws-shell-teardown",
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "shell_pid": os.getpid(),
        "owned": sorted(owned, key=lambda r: r["module_id"] or ""),
        "attached": attached,
        "all_owned_stopped": not any(r["alive_after_stop"] for r in owned),
        "graceful_contracts_met": all(r["graceful_contract_met"] for r in owned),
    }


def write_receipt(receipt: dict, directory: str) -> str:
    """Atomically write the receipt and prune old ones. Returns the receipt path."""
    os.makedirs(directory, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    # The random suffix keeps two receipts written within the clock's resolution (Windows: can be
    # milliseconds) from colliding and silently replacing each other; the timestamp still sorts.
    path = os.path.join(directory, f"{RECEIPT_PREFIX}{stamp}-{uuid.uuid4().hex[:8]}.json")
    temporary = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    receipts = sorted(name for name in os.listdir(directory)
                      if name.startswith(RECEIPT_PREFIX) and name.endswith(".json"))
    for name in receipts[:-KEEP]:
        try:
            os.remove(os.path.join(directory, name))
        except OSError:
            pass
    return path


def latest_receipt(directory: str) -> dict | None:
    try:
        receipts = sorted(name for name in os.listdir(directory)
                          if name.startswith(RECEIPT_PREFIX) and name.endswith(".json"))
    except OSError:
        return None
    for name in reversed(receipts):
        try:
            with open(os.path.join(directory, name), encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            continue
    return None


def summarize(receipt: dict) -> list[str]:
    """Human-readable lines for the shell log / launcher."""
    lines = []
    for record in receipt.get("owned", []):
        how = "graceful" if record["graceful"] else "FORCED"
        note = "" if record["graceful_contract_met"] else " (graceful shutdown contract NOT met)"
        lines.append(f"owned    {record['module_id']}: stopped {how}, exit "
                     f"{record['exit_code']}{note}")
    for record in receipt.get("attached", []):
        state = "left running" if record["left_running"] else f"observed {record['observed_state']}"
        lines.append(f"attached {record['module_id']}: {state}, not stopped by the shell. "
                     f"{record['stop_hint']}".rstrip())
    return lines
