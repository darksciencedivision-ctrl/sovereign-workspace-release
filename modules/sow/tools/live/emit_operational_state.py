"""Emit persisted operational collaboration state for the desktop Inspector."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from persistence import SovereignStore  # noqa: E402

SCHEMA = "sovereign_operational_state@1.0"


def build_feed(*, project_id: str, store_root: Path) -> dict:
    store = SovereignStore(store_root / "sovereign.db")
    tasks = store.list_operational_tasks(project_id)
    # W-78d: one grouped query for every message of the project, reassembled in the tasks'
    # own order - the per-task loop paid one query AND one SQLite connection per task.
    by_task = store.list_operational_messages_by_task(
        project_id, [task["task_id"] for task in tasks])
    messages = []
    for task in tasks:
        messages.extend(by_task[task["task_id"]])
    debates = store.list_operational_debates(project_id)
    return {
        "schema": SCHEMA,
        "project_id": project_id,
        "tasks": tasks,
        "messages": messages,
        "debates": debates,
        "summary": {
            "task_count": len(tasks),
            "message_count": len(messages),
            "debate_count": len(debates),
            "open_debate_count": sum(d.get("state") == "OPEN" for d in debates),
            # counted separately rather than folded into "not open": a debate that ended without a
            # decision (U416) is not a concluded one, and the Inspector says so (invariant 27).
            "aborted_debate_count": sum(d.get("state") == "ABORTED" for d in debates),
        },
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--store-root", default=str(ROOT / ".sovereign_store"))
    args = parser.parse_args(argv)
    sys.stdout.write(json.dumps(build_feed(
        project_id=args.project, store_root=Path(args.store_root).resolve(),
    ), sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
