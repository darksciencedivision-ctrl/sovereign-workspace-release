"""CR-021 (TokenCenter overlapping full rescans) and CR-022 (one malformed numeric field aborts
the whole refresh)."""
from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

TC = Path(__file__).resolve().parents[4] / "modules" / "tokencenter"
if str(TC) not in sys.path:
    sys.path.insert(0, str(TC))

import piggybank as pb  # noqa: E402


# -- CR-022 ----------------------------------------------------------------
def test_cr022_safe_int_coerces_and_counts_warnings():
    pb._reset_parse_warnings()
    assert pb._safe_int("100") == 100
    assert pb._safe_int(None) == 0 and pb._safe_int("") == 0 and pb._safe_int(0) == 0
    assert pb.parse_warning_count() == 0  # missing/empty is not a warning
    assert pb._safe_int("garbage") == 0
    assert pb._safe_int("12.5") == 0  # non-integer text
    assert pb.parse_warning_count() == 2  # two genuinely malformed values


def test_cr022_malformed_record_does_not_abort_collector(tmp_path):
    home = tmp_path
    sessions = home / ".codex" / "sessions" / "2026" / "09"
    sessions.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        {"type": "turn_context", "payload": {"model": "gpt-x"}},
        # malformed numeric field — must be skipped, not abort the whole scan
        {"type": "event_msg", "timestamp": now, "payload": {"type": "token_count",
            "info": {"last_token_usage": {"total_tokens": "garbage", "input_tokens": 5}}}},
        # valid record after the malformed one — must still be collected
        {"type": "event_msg", "timestamp": now, "payload": {"type": "token_count",
            "info": {"last_token_usage": {"total_tokens": 100, "input_tokens": 10,
                                          "output_tokens": 90}}}},
    ]
    (sessions / "s.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")

    pb._reset_parse_warnings()
    cutoff = datetime.now(timezone.utc).replace(year=2000)
    events, status = pb.collect_codex(home, cutoff)
    assert len(events) == 1 and events[0].total_tokens == 100
    assert pb.parse_warning_count() >= 1


# -- CR-021 ----------------------------------------------------------------
def test_cr021_peak_collector_concurrency_is_one(tmp_path, monkeypatch):
    peak = {"cur": 0, "max": 0}
    lock = threading.Lock()

    def fake_collect_all(home, lookback_days):
        with lock:
            peak["cur"] += 1
            peak["max"] = max(peak["max"], peak["cur"])
        time.sleep(0.05)
        with lock:
            peak["cur"] -= 1
        return [], []

    monkeypatch.setattr(pb, "collect_all", fake_collect_all)
    monkeypatch.setattr(pb, "save_snapshot", lambda summary: None)
    monkeypatch.setattr(pb, "_collect_fingerprint", lambda home, days: None)  # force a real scan each time

    state = pb.State(tmp_path, lookback_days=14)
    threads = [threading.Thread(target=state.refresh) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak["max"] == 1, f"peak collector concurrency was {peak['max']}"


def test_cr021_unchanged_inputs_are_not_rescanned(tmp_path, monkeypatch):
    calls = {"n": 0}

    def counting_collect_all(home, lookback_days):
        calls["n"] += 1
        return [], []

    monkeypatch.setattr(pb, "collect_all", counting_collect_all)
    monkeypatch.setattr(pb, "save_snapshot", lambda summary: None)

    state = pb.State(tmp_path, lookback_days=14)  # empty home => stable fingerprint
    state.refresh()
    state.refresh()  # inputs unchanged: must reuse the first scan (coalesced), not re-scan
    assert calls["n"] == 1, f"collect_all ran {calls['n']} times for unchanged inputs"

    # touch an input so the fingerprint changes => a real re-scan happens
    root = tmp_path / ".grok" / "logs"
    root.mkdir(parents=True)
    (root / "unified.jsonl").write_text("{}\n", encoding="utf-8")
    state.refresh()
    assert calls["n"] == 2, "a changed input must trigger a re-scan"
