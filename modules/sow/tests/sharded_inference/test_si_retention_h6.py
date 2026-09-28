"""H6: a safe prune for LONG run evidence (``state_admin prune``), dry run by default.

Every LONG chunk's output and hash-chained checkpoint stays in ``<evidence>/long/<job id>`` for
good, so the state home grows without bound. The prune removes a run only when its job is final,
finished long enough ago, and its checkpoints verify a completed or failed run. It never touches a
job that may still run or resume (queued, running, interrupted), a cancelled or unfinished run, a
run whose checkpoints do not verify, or a directory with no job. Failure injection: each of those.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import long_workload as LW  # noqa: E402
from sovereign_product import paths as P  # noqa: E402
from sovereign_product import state_admin as SA  # noqa: E402
from sovereign_product.store import SovereignStore  # noqa: E402

from test_si_p6_long_route import FakeLlama, _small_root, clean_env  # noqa: E402,F401

LATER = datetime(2030, 1, 1, tzinfo=timezone.utc)  # every job below is "old" by then


class Crash(BaseException):
    pass


def _setup(tmp_path):
    root = _small_root(tmp_path)
    paths = P.resolve_product_paths(root, create=True)
    store = SovereignStore(paths.db_path)
    session = store.create_session()["session_id"]
    return root, paths, store, session


def _job(store, session, status, *, run=None, paths=None, root=None, crash_after=None):
    job_id = store.create_job(session, "LONG", "Draft a rollout plan.")["job_id"]
    if run is not None:
        client = FakeLlama()
        if crash_after is not None:
            real = client.chat

            def chat(**kw):
                if len(client.chats) >= crash_after:
                    raise Crash()
                return real(**kw)

            client.chat = chat
        stop = {"cancel": run == "cancelled"}
        executor = LW.LongWorkloadExecutor(root=root, evidence_dir=paths.evidence_dir,
                                           client=client, config=LW.load_config(root))
        try:
            executor.run(job_id, "Draft a rollout plan.",
                         cancel_requested=lambda: stop["cancel"] and len(client.chats) >= 1,
                         progress_callback=lambda p: None)
        except Crash:
            pass
    if status != "queued":
        store.transition_job(job_id, "running")
    if status not in ("queued", "running"):
        store.transition_job(job_id, status)
    return job_id


def test_h6_prune_removes_only_old_finished_runs_and_says_why_it_keeps_the_rest(clean_env,
                                                                               tmp_path):
    root, paths, store, session = _setup(tmp_path)
    done = _job(store, session, "completed", run="completed", paths=paths, root=root)
    failed_run = _job(store, session, "failed", run="completed", paths=paths, root=root)
    interrupted = _job(store, session, "interrupted", run="completed", paths=paths, root=root)
    running = _job(store, session, "running", run="partial", paths=paths, root=root,
                   crash_after=1)
    cancelled = _job(store, session, "cancelled", run="cancelled", paths=paths, root=root)
    unfinished = _job(store, session, "failed", run="partial", paths=paths, root=root,
                      crash_after=1)
    tampered = _job(store, session, "completed", run="completed", paths=paths, root=root)
    checkpoint = sorted((paths.evidence_dir / "long" / tampered / "checkpoints").glob("*.json"))[1]
    record = json.loads(checkpoint.read_text(encoding="utf-8"))
    record["payload"]["summary"] = "tampered"
    checkpoint.write_text(json.dumps(record), encoding="utf-8")
    (paths.evidence_dir / "long" / "job_orphan").mkdir()
    store.close()

    dry = SA.prune(root, older_than_days=30, now=LATER)
    assert dry["applied"] is False
    assert {r["job_id"] for r in dry["would_remove"]} == {done, failed_run}
    assert dry["bytes_to_free"] > 0
    reasons = {k["job_id"]: k["reason"] for k in dry["kept"]}
    assert "interrupted" in reasons[interrupted] and "resume" in reasons[interrupted]
    assert "running" in reasons[running]
    assert "cancelled" in reasons[cancelled]
    assert "not finished" in reasons[unfinished]
    assert "do not verify" in reasons[tampered]
    assert "no LONG job" in reasons["job_orphan"]
    assert (paths.evidence_dir / "long" / done).is_dir(), "a dry run deletes nothing"

    applied = SA.prune(root, older_than_days=30, now=LATER, apply=True)
    assert {r["job_id"] for r in applied["removed"]} == {done, failed_run}
    remaining = {p.name for p in (paths.evidence_dir / "long").iterdir()}
    assert remaining == {interrupted, running, cancelled, unfinished, tampered, "job_orphan"}
    assert SA.prune(root, older_than_days=30, now=LATER, apply=True)["removed"] == []


def test_h6_recent_runs_are_kept_and_the_cli_is_a_dry_run_by_default(clean_env, tmp_path,
                                                                    capsys):
    root, paths, store, session = _setup(tmp_path)
    done = _job(store, session, "completed", run="completed", paths=paths, root=root)
    store.close()
    kept = SA.prune(root, older_than_days=30)  # finished just now
    assert kept["would_remove"] == [] and "less than 30 days" in kept["kept"][0]["reason"]

    assert SA.main(["--root", str(root), "prune", "--older-than-days", "0"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["applied"] is False and [r["job_id"] for r in report["would_remove"]] == [done]
    assert (paths.evidence_dir / "long" / done).is_dir()
    assert SA.main(["--root", str(root), "prune", "--older-than-days", "0", "--apply"]) == 0
    assert not (paths.evidence_dir / "long" / done).exists()


def test_h6_a_negative_age_is_refused(clean_env, tmp_path):
    root, paths, store, session = _setup(tmp_path)
    store.close()
    with pytest.raises(SA.StateAdminError, match="negative"):
        SA.prune(root, older_than_days=-1)


def test_h6_the_watch_log_rotates_instead_of_growing_for_good(clean_env, tmp_path, monkeypatch):
    from sovereign_product import supervisor_service as ss

    root = tmp_path / "bare"
    root.mkdir()
    monkeypatch.setattr(ss, "cmd_ensure", lambda root, port: {"ensured": True, "running": True})
    monkeypatch.setattr(ss, "WATCH_LOG_MAX_BYTES", 2000)
    ss.cmd_watch(root, sleep=lambda s: None, max_iterations=200)  # ~100 bytes per line
    log = ss.service_dir(root) / "watch.log"
    assert log.stat().st_size < 2000 + 200
    older = log.with_name("watch.log.1")
    assert older.is_file() and older.stat().st_size < 2000 + 200
    last = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert last["iteration"] == 200, "the newest lines are in watch.log"
