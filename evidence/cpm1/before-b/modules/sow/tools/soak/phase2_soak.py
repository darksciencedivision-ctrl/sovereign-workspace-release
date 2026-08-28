"""Phase 2 accelerated soak (loop directive substitution for Plan section 7-P2's 24 h run):
8 real simulated-node processes, time-compressed heartbeats, induced kills + a hang lane,
>= 30 min wall. Machine-checked exit criteria:
  1. no orphan processes after terminate_all (OS-level pid liveness, not registry claims)
  2. event log complete (every spawn has a terminal exit; every incarnation ends TERMINATED)
  3. event log ordered (contiguous seq + intact hash chain via verify_file)
  4. every recorded transition replays legally through the state machine
  5. restarts + disconnect-reclaims actually occurred (fault pressure was real)
Report: tools/soak/results/PHASE2_SOAK_<ts>.json  (verdict computed from criteria).

Run (repo root): py -3.12 tools/soak/phase2_soak.py --duration-s 1800
Smoke:           py -3.12 tools/soak/phase2_soak.py --duration-s 60 --kill-every-s 8
"""
from __future__ import annotations

import argparse
import ctypes
import json
import platform
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from control_plane.nodes import (  # noqa: E402
    AppendOnlyEventLog,
    HeartbeatPolicy,
    IllegalTransition,
    NodeProcessManager,
    NodeRegistry,
    NodeState,
    RestartPolicy,
    validate_transition,
    verify_file,
)

SIM = str(ROOT / "tests" / "fixtures" / "sim_node.py")


def pid_alive(pid: int) -> bool:
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        return code.value == 259  # STILL_ACTIVE
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def replay_legality(log_path: Path) -> dict:
    """Replay every transition event through the state machine; any illegality fails."""
    per_node: dict[tuple[str, int], NodeState] = {}
    problems: list[str] = []
    transitions = 0
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            key = (row.get("node_id"), row.get("incarnation"))
            if row["kind"] == "spawn":
                if key in per_node and per_node[key] is not NodeState.TERMINATED:
                    problems.append(f"{key}: respawned while {per_node[key].value}")
                per_node[key] = NodeState.SPAWNING
            elif row["kind"] == "transition":
                transitions += 1
                frm, to = NodeState(row["data"]["frm"]), NodeState(row["data"]["to"])
                current = per_node.get(key)
                if current is None:
                    problems.append(f"{key}: transition before spawn (seq {row['seq']})")
                    continue
                if current is not frm:
                    problems.append(f"{key}: log says {frm.value} but replay is at {current.value} (seq {row['seq']})")
                try:
                    validate_transition(frm, to)
                except IllegalTransition as exc:
                    problems.append(f"{key}: {exc} (seq {row['seq']})")
                per_node[key] = to
    non_terminal = [f"{k}" for k, s in per_node.items() if s is not NodeState.TERMINATED]
    return {"ok": not problems and not non_terminal, "transitions": transitions,
            "incarnations": len(per_node), "problems": problems[:20], "non_terminal": non_terminal[:20]}


def completeness(log_path: Path) -> dict:
    spawns: set[tuple[str, int]] = set()
    exits: set[tuple[str, int]] = set()
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            key = (row.get("node_id"), row.get("incarnation"))
            if row["kind"] == "spawn":
                spawns.add(key)
            elif row["kind"] == "exit":
                exits.add(key)
    missing = sorted(str(k) for k in spawns - exits)
    return {"ok": not missing, "spawns": len(spawns), "exits": len(exits), "missing_exit": missing[:20]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", type=int, default=8)
    parser.add_argument("--duration-s", type=float, default=1800.0)
    parser.add_argument("--hb-ms", type=int, default=250)
    parser.add_argument("--kill-every-s", type=float, default=20.0)
    parser.add_argument("--exercise-every-s", type=float, default=5.0)
    parser.add_argument("--hang-lane-s", type=float, default=45.0)
    parser.add_argument("--seed", type=int, default=20260716)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = results_dir / f"PHASE2_SOAK_{ts}_events.jsonl"

    log = AppendOnlyEventLog(log_path)
    manager = NodeProcessManager(
        NodeRegistry(log), log,
        HeartbeatPolicy(interval_s=args.hb_ms / 1000.0, miss_factor=6.0, spawn_grace_s=15.0),
        RestartPolicy(max_restarts=100000, backoff_s=0.2),
    )

    all_pids: set[int] = set()
    stats = Counter()
    timeline: list[dict] = []
    start = time.monotonic()

    for i in range(args.nodes - 1):
        record = manager.spawn(f"sim-{i}", [sys.executable, SIM, "--hb-ms", str(args.hb_ms)])
        all_pids.add(record.pid)
    hang = manager.spawn(f"sim-{args.nodes - 1}",
                         [sys.executable, SIM, "--hb-ms", str(args.hb_ms), "--hang-after-s", str(args.hang_lane_s)])
    all_pids.add(hang.pid)

    next_kill = start + args.kill_every_s
    next_exercise = start + args.exercise_every_s
    next_checkpoint = start + 60.0
    exercise_state: dict[str, list[NodeState]] = defaultdict(list)

    while time.monotonic() - start < args.duration_s:
        manager.poll()
        all_pids.update(manager.managed_pids())
        now = time.monotonic()

        if now >= next_kill:
            next_kill = now + args.kill_every_s
            hang_lane = f"sim-{args.nodes - 1}"  # hang lane has its own fault; keep the DISCONNECTED path deterministic
            candidates = [r for r in manager.registry.alive()
                          if r.state in (NodeState.READY, NodeState.ASSIGNED, NodeState.BUSY) and r.node_id != hang_lane]
            if candidates:
                victim = rng.choice(candidates)
                manager.kill_node(victim.node_id, incarnation=victim.incarnation, expected=False)
                stats["induced_kills"] += 1

        if now >= next_exercise:
            next_exercise = now + args.exercise_every_s
            ready = [r for r in manager.registry.alive() if r.state is NodeState.READY]
            if ready:
                node = rng.choice(ready)
                try:
                    steps = ([NodeState.ASSIGNED, NodeState.BUSY, NodeState.PAUSED, NodeState.BUSY, NodeState.READY]
                             if rng.random() < 0.3 else [NodeState.ASSIGNED, NodeState.BUSY, NodeState.READY])
                    for step in steps:
                        current = manager.registry.get(node.node_id, node.incarnation)
                        if current.state in (NodeState.DISCONNECTED, NodeState.TERMINATED):
                            break  # a fault beat us to it; that's the point of a soak
                        manager.registry.transition(node.node_id, step, incarnation=node.incarnation, reason="soak exercise")
                        stats["exercised_transitions"] += 1
                except IllegalTransition:
                    stats["exercise_races_refused"] += 1  # refusal IS correct fail-closed behavior

        if now >= next_checkpoint:
            next_checkpoint = now + 60.0
            histogram = Counter(r.state.value for r in manager.registry.alive())
            timeline.append({"t_s": round(now - start, 1), "alive": len(manager.registry.alive()),
                             "states": dict(histogram), "restarts": dict(manager._restarts)})
            print(f"[soak] t={now - start:6.0f}s alive={len(manager.registry.alive())} "
                  f"kills={stats['induced_kills']} states={dict(histogram)}", flush=True)

        time.sleep(0.2)

    leftovers = manager.terminate_all()
    time.sleep(1.0)
    still_alive = sorted(pid for pid in all_pids if pid_alive(pid))
    log.close()

    verify = verify_file(log_path)
    replay = replay_legality(log_path)
    complete = completeness(log_path)
    restarts_total = sum(manager._restarts.values())
    disconnects = sum(1 for line in log_path.open(encoding="utf-8")
                      if '"kind":"transition"' in line and '"to":"DISCONNECTED"' in line)

    criteria = [
        {"criterion": "no orphan processes after terminate_all (OS pid check)",
         "value": {"terminate_all_leftovers": leftovers, "os_alive": still_alive}, "pass": not leftovers and not still_alive},
        {"criterion": "event log ordered (contiguous seq + hash chain)",
         "value": {"rows": verify.rows, "problems": verify.problems[:5]}, "pass": verify.ok},
        {"criterion": "event log complete (every spawn has terminal exit)", "value": complete, "pass": complete["ok"]},
        {"criterion": "all transitions replay legally; all incarnations end TERMINATED",
         "value": {k: replay[k] for k in ("transitions", "incarnations", "problems", "non_terminal")}, "pass": replay["ok"]},
        {"criterion": "fault pressure real (induced kills, restarts, disconnect-reclaims all > 0)",
         "value": {"induced_kills": stats["induced_kills"], "restarts": restarts_total, "disconnect_transitions": disconnects},
         "pass": stats["induced_kills"] > 0 and restarts_total > 0 and disconnects > 0},
        {"criterion": f"duration >= requested ({args.duration_s:.0f}s)",
         "value": round(time.monotonic() - start, 1), "pass": (time.monotonic() - start) >= args.duration_s},
    ]
    report = {
        "soak": "phase2@1.0", "generated": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "platform": platform.platform(),
        "config": vars(args), "stats": dict(stats), "restarts_total": restarts_total,
        "timeline": timeline, "criteria": criteria, "event_log": log_path.name,
        "verdict": "PASS" if all(c["pass"] for c in criteria) else "FAIL",
    }
    report_path = results_dir / f"PHASE2_SOAK_{ts}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"[soak] verdict={report['verdict']} report={report_path}", flush=True)
    for c in criteria:
        print(f"[soak]   {'PASS' if c['pass'] else 'FAIL'}: {c['criterion']}", flush=True)
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
