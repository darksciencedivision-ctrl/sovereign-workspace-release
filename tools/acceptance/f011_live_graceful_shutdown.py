#!/usr/bin/env python
"""F-011 live acceptance: the REAL modules stop cooperatively through the shell's graceful channel.

Not part of the pytest suite: it launches the real SOVEREIGN server and Token Center as child
processes under the real shell JobSupervisor, which is a host action. Everything it creates is its
own - a fresh state root under %TEMP%, free ports chosen here, children inside a job object this
process owns (kill-on-close) - and it is removed at the end. No operator state, port or shortcut is
touched: SOVEREIGN's state and evidence dirs and Token Center's data dir and USERPROFILE all point
into the owned root.

For each module it asserts, from observation rather than from the signal call returning:
  1. the module became ready over HTTP and durable state was written through its real API;
  2. JobSupervisor.stop() reports graceful=True, forced=False, a zero exit code, and a wait far
     inside the grace window (the hard-kill fallback did not fire);
  3. the process is actually gone;
  4. the SQLite database passes PRAGMA integrity_check and still holds what was written
     (SOVEREIGN additionally reopens through SovereignStore, which re-verifies its event hash chain).
A negative control - a child that ignores the event - must come back forced=True, proving the
record distinguishes a cooperative exit from the fallback.

Run with the SOVEREIGN venv interpreter from the repository root:
  modules\\sovereign\\.venv\\Scripts\\python.exe tools\\acceptance\\f011_live_graceful_shutdown.py --out <file.json>
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "modules" / "sovereign"))

from shell.src.logring import LogRing  # noqa: E402
from shell.src.supervisor import JobSupervisor  # noqa: E402

_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ENV_ALLOW = ("SYSTEMROOT", "PATH", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def base_env(**extra: str) -> dict:
    env = {k: os.environ[k] for k in ENV_ALLOW if k in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def http(method: str, url: str, body: dict | None = None, headers: dict | None = None,
         timeout: float = 5.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json", **(headers or {})})
    with _NO_PROXY.open(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def wait_ready(url: str, ph, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if not ph.is_alive():
            return False
        try:
            status, _ = http("GET", url, timeout=2)
            if status == 200:
                return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def sqlite_facts(db: Path, query: str | None = None, args: tuple = ()) -> dict:
    wal = db.with_name(db.name + "-wal")
    facts = {"db_exists": db.is_file(), "wal_exists_after_exit": wal.exists(),
             "wal_bytes_after_exit": wal.stat().st_size if wal.exists() else 0}
    if not db.is_file():
        return facts
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        facts["integrity_check"] = con.execute("PRAGMA integrity_check").fetchone()[0]
        if query:
            facts["query_rows"] = con.execute(query, args).fetchall()
    finally:
        con.close()
    return facts


def stop_and_observe(sup: JobSupervisor, module_id: str, ph, grace_s: int) -> dict:
    record = sup.stop(module_id, grace_s=grace_s)
    record["grace_s"] = grace_s
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {ph.pid}", "/NH"], capture_output=True,
                             text=True, timeout=15).stdout
        record["pid_still_listed"] = str(ph.pid) in out
    except (OSError, subprocess.SubprocessError) as exc:
        record["pid_still_listed"] = f"unknown: {exc}"
    return record


def sovereign(sup: JobSupervisor, state: Path) -> dict:
    root = REPO / "modules" / "sovereign"
    python = root / ".venv" / "Scripts" / "python.exe"
    port = free_port()
    runtime = state / "runtime"
    ring = LogRing()
    env = base_env(USERPROFILE=str(state / "home"), SOVEREIGN_WORKSPACE_STATE=str(state),
                   SOVEREIGN_STATE_DIR=str(runtime), SOVEREIGN_EVIDENCE_DIR=str(runtime / "evidence"))
    (state / "home").mkdir(parents=True, exist_ok=True)
    argv = [str(python), "-m", "sovereign_product.server", "--root", str(root), "--host", "127.0.0.1",
            "--port", str(port), "--workers", "1"]
    ph = sup.spawn("f011-sovereign", argv, str(root), env, log_ring=ring)
    result: dict = {"module": "sovereign", "pid": ph.pid, "port": port}
    result["ready"] = wait_ready(f"http://127.0.0.1:{port}/v1/health", ph, 60)
    if not result["ready"]:
        result["stop"] = stop_and_observe(sup, "f011-sovereign", ph, 10)
        result["log_tail"] = ring.read_lines()[-40:]
        return result
    status, body = http("POST", f"http://127.0.0.1:{port}/v1/sessions", {"title": "f011-live-shutdown"},
                        headers={"Origin": f"http://127.0.0.1:{port}"})
    session_id = json.loads(body)["session"]["session_id"]
    result["write"] = {"status": status, "session_id": session_id}
    time.sleep(0.5)
    result["stop"] = stop_and_observe(sup, "f011-sovereign", ph, 10)
    db = runtime / "sovereign.db"
    result["sqlite"] = sqlite_facts(db)
    from sovereign_product.store import SovereignStore  # noqa: PLC0415 - verifies the event chain on open
    try:
        store = SovereignStore(db)
        session = store.get_session(session_id, include_messages=False)
        result["reopen"] = {"event_chain_verified": True,
                            "session_title": session.get("title") if isinstance(session, dict)
                            else getattr(session, "title", None)}
    except Exception as exc:  # noqa: BLE001 - recorded as a failure
        result["reopen"] = {"event_chain_verified": False, "error": repr(exc)}
    result["log_tail"] = ring.read_lines()[-15:]
    return result


def tokencenter(sup: JobSupervisor, state: Path, python312: str) -> dict:
    root = REPO / "modules" / "tokencenter"
    port = free_port()
    data = state / "data"
    home = state / "home-tc"
    home.mkdir(parents=True, exist_ok=True)
    ring = LogRing()
    env = base_env(USERPROFILE=str(home), TOKENCENTER_DATA_DIR=str(data))
    argv = [python312, str(root / "piggybank.py"), "--port", str(port)]
    ph = sup.spawn("f011-tokencenter", argv, str(root), env, log_ring=ring)
    result: dict = {"module": "tokencenter", "pid": ph.pid, "port": port}
    result["ready"] = wait_ready(f"http://127.0.0.1:{port}/healthz", ph, 30)
    db = data / "piggybank.sqlite"
    deadline = time.time() + 15
    while result["ready"] and not db.is_file() and time.time() < deadline:
        time.sleep(0.25)
    result["db_written_before_stop"] = db.is_file()
    result["stop"] = stop_and_observe(sup, "f011-tokencenter", ph, 5)
    result["sqlite"] = sqlite_facts(db)
    result["log_tail"] = ring.read_lines()[-15:]
    return result


def negative_control(sup: JobSupervisor) -> dict:
    """A child that never watches the event: the record must say the fallback fired."""
    ph = sup.spawn("f011-ignores-event", [sys.executable, "-c", "import time; time.sleep(120)"],
                   str(REPO), base_env())
    time.sleep(1.0)
    return {"module": "negative-control", "pid": ph.pid,
            "stop": stop_and_observe(sup, "f011-ignores-event", ph, 2)}


def verdict(sov: dict, tc: dict, neg: dict) -> list[str]:
    problems = []
    for r, grace in ((sov, 10), (tc, 5)):
        name = r["module"]
        s = r.get("stop", {})
        if not r.get("ready"):
            problems.append(f"{name}: never became ready")
        if not (s.get("graceful") is True and s.get("forced") is False):
            problems.append(f"{name}: not a cooperative exit: {s}")
        if s.get("exit_code") != 0:
            problems.append(f"{name}: exit code {s.get('exit_code')}")
        if s.get("waited_ms", 10**9) >= grace * 1000:
            problems.append(f"{name}: waited the whole grace window ({s.get('waited_ms')} ms)")
        if s.get("pid_still_listed") is not False:
            problems.append(f"{name}: process still listed after stop")
        if r.get("sqlite", {}).get("integrity_check") != "ok":
            problems.append(f"{name}: database integrity_check {r.get('sqlite')}")
    if sov.get("write", {}).get("status") != 201:
        problems.append("sovereign: the durable write did not succeed")
    if not sov.get("reopen", {}).get("event_chain_verified"):
        problems.append(f"sovereign: reopen/event-chain verification failed: {sov.get('reopen')}")
    if sov.get("reopen", {}).get("session_title") != "f011-live-shutdown":
        problems.append("sovereign: the written session is not durable after shutdown")
    if not tc.get("db_written_before_stop"):
        problems.append("tokencenter: its database was never written, so shutdown durability is unobserved")
    if neg["stop"].get("forced") is not True or neg["stop"].get("graceful") is not False:
        problems.append(f"negative control did not report the fallback: {neg['stop']}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep-state", action="store_true")
    args = ap.parse_args()
    python312 = subprocess.run(["py", "-3.12", "-c", "import sys;print(sys.executable)"],
                               capture_output=True, text=True, check=True).stdout.strip()
    state = Path(tempfile.mkdtemp(prefix="sws-f011-"))
    sup = JobSupervisor(max_processes=4)
    started = time.time()
    try:
        sov = sovereign(sup, state / "sovereign")
        tc = tokencenter(sup, state / "tokencenter", python312)
        neg = negative_control(sup)
    finally:
        sup.close()
    problems = verdict(sov, tc, neg)
    report = {
        "check": "F-011 live graceful shutdown (real modules, owned processes, isolated state)",
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "head": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                               text=True).stdout.strip(),
        "state_root": str(state), "seconds": round(time.time() - started, 1),
        "sovereign": sov, "tokencenter": tc, "negative_control": neg,
        "verdict": "PASS" if not problems else "FAIL", "problems": problems,
    }
    Path(args.out).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"f011_live_graceful_shutdown: {report['verdict']}")
    for p in problems:
        print(f"  {p}")
    if not args.keep_state:
        shutil.rmtree(state, ignore_errors=True)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
