"""Phase 14E `.roster` — assembled roster liveness matrix + item-7 Ollama smoke.

Deterministic tests (allow_live=False) prove the four-role composition and its HONEST
classification without any daemon. The two live tests (skipped-with-record when Ollama is
absent, directive §10.4) are the item-7 receipt: a real on-host Ollama model list + a real
generate + measured latency. Nothing is faked — an absent daemon skips, it does not fabricate.
"""
from __future__ import annotations

from adapters import detect
from tools.assembled.roster_report import (
    DETERMINISTIC_SUBSTITUTE,
    LIVE,
    MOCK,
    assembled_report,
    assembled_roster,
    run_ollama_smoke,
)

import pytest

_OLLAMA = detect.ollama_available()
_REASONING_LIVE = bool(_OLLAMA and detect.ollama_models())


# --- deterministic composition (no daemon) -----------------------------------------------

def test_four_assembled_roles_present_and_ordered() -> None:
    roles = assembled_roster(allow_live=False)
    assert [r.role for r in roles] == [
        "conductor", "frontier_worker", "coding_worker", "local_reasoning_worker"]
    # directive §9 table 14E: one conductor + one frontier + one coding/local + one local reasoning
    assert len({r.role for r in roles}) == 4


def test_every_role_has_a_reason_and_valid_liveness() -> None:
    for r in assembled_roster(allow_live=False):
        assert r.liveness in {LIVE, MOCK, DETERMINISTIC_SUBSTITUTE}
        assert r.reason.strip(), f"{r.role} must carry an honest reason"


def test_conductor_is_mock_and_carries_no_credential() -> None:
    conductor = assembled_roster(allow_live=False)[0]
    assert conductor.liveness == MOCK
    assert conductor.model is None
    # §2.2: no credential/token anywhere in the classification
    assert "credential" in conductor.reason.lower() or "no credential" in conductor.reason.lower()


def test_frontier_worker_is_mock_and_owed_not_claimed_live() -> None:
    frontier = next(r for r in assembled_roster(allow_live=False) if r.role == "frontier_worker")
    assert frontier.liveness == MOCK
    assert frontier.owed is True  # live claude smoke is OWED — must never be classified LIVE here
    assert "skip-with-record" in frontier.reason.lower()


def test_allmock_view_has_no_live_leg() -> None:
    # With detection disabled, no leg may claim LIVE (fail-closed: only real detection unlocks live).
    roles = assembled_roster(allow_live=False)
    assert all(r.liveness != LIVE for r in roles)
    coding = next(r for r in roles if r.role == "coding_worker")
    assert coding.liveness == MOCK  # no OpenCode detection under allow_live=False


def test_report_structure_is_complete() -> None:
    report = assembled_report(allow_live=False, run_smoke=False)
    assert report["phase"] == "14E" and report["sub_step"] == "roster"
    assert report["role_count"] == 4
    assert set(report["owed_roles"]) == {"frontier_worker"}
    assert report["item7_ollama_smoke"]["generated"] is False  # smoke disabled → honestly not generated
    assert report["honesty_note"].strip()


def test_no_role_dict_leaks_a_token_field() -> None:
    # Belt-and-braces on §2.2: the serialized matrix exposes refs/kinds/models — never a secret.
    for r in assembled_roster(allow_live=False):
        d = r.as_dict()
        keys = " ".join(d.keys()).lower()
        for banned in ("token", "secret", "api_key", "apikey", "password", "oauth"):
            assert banned not in keys


def test_frontier_gate_state_matches_real_authorization() -> None:
    # The frontier reason must reflect the ENFORCED runtime gate, not a hardcoded claim. Under OP-6
    # the loop may create config/live_operation.json, so the gate reads SATISFIED when the config is
    # present (this host) and DENIED-by-absence when it is absent (a fresh clone). Either way the
    # assembled-roster frontier leg stays MOCK/owed (live claude smoke not made here).
    from control_plane.profiles.live_authorization import load_live_authorization
    live_ok = load_live_authorization().is_provider_live("claude_code")
    frontier = next(r for r in assembled_roster(allow_live=True) if r.role == "frontier_worker")
    assert frontier.liveness == MOCK and frontier.owed is True
    if live_ok:
        assert "satisfied (config present" in frontier.reason.lower()
    else:
        assert "denied-by-absence" in frontier.reason.lower()


def test_coding_worker_is_live_direct_when_coder_present_but_no_opencode(monkeypatch) -> None:
    # A real local coder with OpenCode absent is a DIRECT Ollama coder (a real local backend),
    # not a mock — the classification must not under-claim it as MOCK (spec-audit MINOR-3).
    monkeypatch.setattr("tools.assembled.roster_report.detect.opencode_available", lambda: False)
    if not _REASONING_LIVE:  # needs a real detected coder model to exercise the live-direct branch
        pytest.skip("no live Ollama coder model detected — direct-coder branch not exercisable")
    coding = next(r for r in assembled_roster(allow_live=True) if r.role == "coding_worker")
    # either a real coder is present (LIVE direct) or none is (MOCK) — never a false MOCK when a
    # coder model is genuinely detected
    if coding.model:
        assert coding.liveness == LIVE and coding.backend_kind == "ollama"
        assert "direct" in coding.reason.lower()


def test_smoke_degrades_honestly_when_daemon_absent(monkeypatch) -> None:
    # Force the "no daemon" branch regardless of host: it must report unavailable, not fabricate.
    monkeypatch.setattr("tools.assembled.roster_report.detect.ollama_available", lambda timeout=3.0: False)
    out = run_ollama_smoke()
    assert out["available"] is False and out["generated"] is False
    assert "skip-with-record" in out["reason"].lower()


# --- item-7 live receipt (on-host Ollama smoke re-run) ------------------------------------

@pytest.mark.skipif(not _OLLAMA, reason="Ollama daemon not reachable — item-7 smoke SKIP-WITH-RECORD (§10.4)")
def test_item7_ollama_smoke_runs_live() -> None:
    out = run_ollama_smoke()
    assert out["available"] is True
    assert out["models"], "real model list must be non-empty"
    assert out["model"], "a reasoning-tier model must be chosen"
    assert out["generated"] is True, "the real model must return non-empty output"
    assert isinstance(out["latency_s"], float) and out["latency_s"] >= 0.0
    assert out["response_preview"].strip()


@pytest.mark.skipif(not _REASONING_LIVE, reason="no live Ollama reasoning model — local_reasoning stays mock")
def test_local_reasoning_worker_is_live_when_ollama_present() -> None:
    roles = assembled_roster(allow_live=True)
    lr = next(r for r in roles if r.role == "local_reasoning_worker")
    assert lr.liveness == LIVE
    assert lr.backend_kind == "ollama" and lr.model
    # and it appears in the report's live_roles set
    report = assembled_report(allow_live=True, run_smoke=False)
    assert "local_reasoning_worker" in report["live_roles"]
