"""Phase 16D `.statusbar` — tests for the governed subscription-status feed emitter.

Proves the emitter (`tools/live/emit_subscription_status.py`) builds a REAL `SubscriptionGovernor`
seeded from the enforced `LiveAuthorization` scope and emits a readable n/allowance count — the count
the shell status bar renders instead of "concurrency count unavailable" — and that it is:
  * SCHEMA-pinned (a drifted producer is refused by the shell source);
  * HONEST (in_use = 0 with no held terminal; the count is the authorized ceiling; live per-session
    tracking recorded OWED to 16F — never fabricated);
  * FAIL-CLOSED (a DENIED / malformed authorization ⇒ status:null, the em-dash unknown, not 0/2);
  * a pure record — no model call, no credential (§2.2/§2.4).
"""
from __future__ import annotations

import json

import pytest

from control_plane.profiles.live_authorization import (
    LiveAuthorization,
    load_live_authorization,
)
from node_runtime.supervisor.subscription_governor import (
    SubscriptionGovernor,
    canonical_subscription_ref,
)
from node_runtime.supervisor.terminal_lease import LEDGER_PATH_ENV, TerminalLeaseLedger
from tools.live import emit_subscription_status as em

PROVIDERS = ("claude_code", "openai_codex_cli")


@pytest.fixture(autouse=True)
def _scratch_ledger(monkeypatch, tmp_path):
    """Phase 17A `.pty`: the feed now seeds `in_use` from the DURABLE lease ledger (U76), so every
    test here must run against a scratch file — reading the host's real ledger would make the
    expected counts depend on whether the operator's own conductor happens to be running."""
    monkeypatch.setenv(LEDGER_PATH_ENV, str(tmp_path / "leases.json"))


def _authorized(terminals: int = 2) -> LiveAuthorization:
    """A valid OP-6 authorization, constructed directly so the test does not depend on the
    gitignored config file existing on the host."""
    return LiveAuthorization(
        authorized=True,
        providers=frozenset(PROVIDERS),
        terminals_per_subscription=terminals,
        register_row="OP-6",
        source="(test)",
        reason="test authorization",
    )


# --- schema + shape -----------------------------------------------------------------------------

def test_feed_is_schema_pinned():
    feed = em.build_subscription_status_feed(live_auth=_authorized())
    assert feed["schema"] == em.SUBSCRIPTION_STATUS_FEED_SCHEMA == "subscription_status_feed@1.0"


def test_emit_prints_one_json_line_only(capsys):
    rc = em.main(["--emit-subscription-status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.endswith("\n")
    assert len(out.strip().splitlines()) == 1  # exactly one JSON line — the stable shell contract
    parsed = json.loads(out)
    assert parsed["schema"] == em.SUBSCRIPTION_STATUS_FEED_SCHEMA


def test_usage_on_wrong_invocation_exits_2(capsys):
    assert em.main([]) == 2
    assert em.main(["--nope"]) == 2
    err = capsys.readouterr().err
    assert "emit_subscription_status" in err


# --- authorized: real, readable, HONEST count ----------------------------------------------------

def test_authorized_emits_readable_zero_over_ceiling():
    feed = em.build_subscription_status_feed(live_auth=_authorized(terminals=2))
    assert feed["authorized"] is True
    assert feed["providers"] == sorted(PROVIDERS)
    assert feed["allowance"] == 2
    status = feed["status"]
    assert status is not None  # readable — NOT the fail-closed unknown
    # one subscription per authorized provider, each at the ceiling with an HONEST zero in_use
    assert set(providers_of(status)) == set(PROVIDERS)
    for rec in status.values():
        assert rec["allowance"] == 2
        assert rec["in_use"] == 0          # no live terminal held by the shell (honest zero)
        assert rec["active"] == []


def test_allowance_follows_authorization_not_a_governor_default():
    feed = em.build_subscription_status_feed(live_auth=_authorized(terminals=1))
    assert feed["allowance"] == 1
    for rec in feed["status"].values():
        assert rec["allowance"] == 1      # a narrowed config binds the display ceiling


def test_live_session_tracking_reports_both_the_conductor_and_workers_counted():
    """Phase 17A `.pty` (U76): `in_use` is sourced from the durable cross-process ledger, so the
    CONDUCTOR's live terminal is counted. The worker half was owed to 17B and 17B CLOSED it —
    `emit_worker_launch` calls `TerminalLeaseLedger.acquire` for every frontier pane before it
    emits an authorized ticket — but this feed went on publishing `owed:true, issue:"17B"` through
    the whole of Phase 18, and this test pinned the stale claim in place (spec-audit MINOR-6).

    An overstated `owed` is not harmless here: it is the feed's own disclaimer about its count, so
    it tells an operator reading the bar that a live worker terminal may be invisible when it is
    not. The flag now says what the ledger does; the ASSERTION below is against the behaviour, so
    a future path that stops taking the lease has to falsify it rather than reword it."""
    feed = em.build_subscription_status_feed(live_auth=_authorized())
    owed = feed["live_session_tracking"]
    assert owed["owed"] is False and owed["issue"] is None
    assert owed["conductor_counted"] is True and owed["worker_counted"] is True
    assert "durable" in owed["note"] and "I-X3" in owed["note"]
    assert owed["ledger_error"] is None
    assert feed["durable_leases"]["error"] is None


def test_the_worker_counted_claim_is_a_property_of_the_launch_path_not_a_constant():
    """`worker_counted: true` is a claim ABOUT another module, and a constant cannot disagree with
    itself. Read it off the launch path: an authorized FRONTIER worker ticket carries a durable
    lease and reports `ix3_counted`. If that stops being true, this test goes red and the feed's
    disclaimer has to be restored rather than quietly outliving the behaviour."""
    import inspect

    from tools.live import emit_worker_launch as ewl

    src = inspect.getsource(ewl.build_worker_launch_ticket)
    assert "led.acquire(" in src, "no durable lease is taken on the worker launch path"
    assert '"durable": True' in src
    assert 'gates["ix3_counted"] = True' in src


# --- U76: ONE subscription ref, and a bar that sees a genuinely held terminal ---------------------

def test_every_product_path_counts_this_subscription_under_the_SAME_ref(tmp_path):
    """U76 regression, stated as agreement BETWEEN the product paths rather than against the helper
    that defines the spelling (which would pass while a third module kept its own): the launch
    ticket, the 16C governed spawn feed and this status feed must all name ONE bucket. The I-X3 cap
    is enforced per ref, so a second spelling is a second full allowance for one subscription."""
    from tools.live import emit_conductor_launch as launch
    from tools.live import emit_conductor_spawn as spawn

    feed = em.build_subscription_status_feed(live_auth=_authorized())
    refs = {launch.CONDUCTOR_SUBSCRIPTION_REF, spawn.CONDUCTOR_SUBSCRIPTION_REF}
    assert len(refs) == 1, f"one real subscription, {len(refs)} spellings: {sorted(refs)}"
    assert refs.pop() in feed["status"]


def test_a_held_durable_lease_is_visible_in_the_bar(tmp_path):
    """The defect the operator would have seen: the shell holds a live conductor terminal and the
    status bar reports 0/2, because the bar built a fresh in-process governor that knows nothing of
    it. The count is now seeded from the durable ledger."""
    led = TerminalLeaseLedger(path=tmp_path / "held.json", pid_alive=lambda p: True)
    ref = canonical_subscription_ref("claude_code")
    led.acquire(subscription_ref=ref, provider="claude_code", node_id="conductor-pane-1",
                allowance=2, holder_pid=4321, session_id="pane-1#1")
    feed = em.build_subscription_status_feed(live_auth=_authorized(terminals=2), ledger=led)
    rec = feed["status"][ref]
    assert rec["in_use"] == 1 and rec["allowance"] == 2
    assert feed["durable_leases"]["seeded"][ref] == ["conductor-pane-1#pane-1#1"]
    # the other provider is untouched — the ledger holds nothing for it
    assert feed["status"][canonical_subscription_ref("openai_codex_cli")]["in_use"] == 0


def test_a_dead_holders_lease_is_not_counted_in_the_bar(tmp_path):
    """A crashed shell must not leave the operator's bar reading 1/2 forever."""
    led = TerminalLeaseLedger(path=tmp_path / "dead.json", pid_alive=lambda p: p != 4321)
    ref = canonical_subscription_ref("claude_code")
    TerminalLeaseLedger(path=tmp_path / "dead.json", pid_alive=lambda p: True).acquire(
        subscription_ref=ref, provider="claude_code", node_id="conductor-pane-1", allowance=2,
        holder_pid=4321, session_id="s1")
    feed = em.build_subscription_status_feed(live_auth=_authorized(terminals=2), ledger=led)
    assert feed["status"][ref]["in_use"] == 0


def test_an_unreadable_ledger_yields_the_UNKNOWN_bar_never_a_fabricated_zero(tmp_path):
    """Now that the count comes from the ledger, a ledger the emitter could not read must produce
    `status:null` — the em-dash unknown. A readable-looking `0/2` beside a read fault is exactly the
    fabricated zero the status-bar contract forbids ("0 is a claim"), and precisely the display
    defect U76 was opened for."""
    bad = tmp_path / "corrupt.json"
    bad.write_text('{"schema": "something-else", "leases": []}', encoding="utf-8")
    led = TerminalLeaseLedger(path=bad, pid_alive=lambda p: True)
    feed = em.build_subscription_status_feed(live_auth=_authorized(terminals=2), ledger=led)
    assert feed["status"] is None                                   # the em-dash unknown in the bar
    assert "LeaseLedgerCorrupt" in feed["durable_leases"]["error"]
    assert "LeaseLedgerCorrupt" in feed["live_session_tracking"]["ledger_error"]
    assert feed["allowance"] == 2                                   # the ceiling is still reported


def test_held_terminals_render_active_path():
    """The `held` injection exercises the acquire() path exactly as a live spawn would — so the
    'active'/'at-capacity' render is real, not a mock. The shell contract passes no `held`."""
    feed = em.build_subscription_status_feed(
        live_auth=_authorized(terminals=2), held={"claude_code": ["worker-A"]})
    rec = [r for r in feed["status"].values() if r["provider"] == "claude_code"][0]
    assert rec["in_use"] == 1
    assert rec["active"] == ["worker-A"]
    # the other provider stays a truthful idle 0
    other = [r for r in feed["status"].values() if r["provider"] == "openai_codex_cli"][0]
    assert other["in_use"] == 0


def test_uses_the_injected_governor_real_api():
    """The emitter registers + acquires through the REAL governor API (not a hand-built dict): a
    caller's governor sees the registrations, proving no fabricated status."""
    gov = SubscriptionGovernor()
    em.build_subscription_status_feed(live_auth=_authorized(terminals=2), governor=gov)
    assert gov.active_count("sub-claude_code") == 0
    assert set(gov.status().keys()) == {"sub-claude_code", "sub-openai_codex_cli"}


# --- fail-closed: DENIED / malformed ⇒ status:null (the em-dash unknown, never 0/2) --------------

def test_denied_authorization_is_failclosed_unknown():
    denied = LiveAuthorization.denied("no live-operation config (enforcement-by-absence)")
    feed = em.build_subscription_status_feed(live_auth=denied)
    assert feed["authorized"] is False
    assert feed["status"] is None        # fail-closed unknown — NOT a fabricated 0/2
    assert feed["providers"] == []
    assert "enforcement-by-absence" in feed["reason"]
    assert feed["schema"] == em.SUBSCRIPTION_STATUS_FEED_SCHEMA


def test_absent_config_path_is_denied_not_crash(tmp_path):
    """A missing config resolves to DENIED (enforcement-by-absence); the emitter emits the honest
    unknown feed, never raising into the shell."""
    missing = tmp_path / "nope.json"
    auth = load_live_authorization(missing)
    assert auth.authorized is False
    feed = em.build_subscription_status_feed(live_auth=auth)
    assert feed["status"] is None and feed["authorized"] is False


def test_malformed_config_path_reports_failclosed(monkeypatch, tmp_path):
    """A present-but-malformed config RAISES in the loader; the emitter (default path) turns that
    into an honest unreadable feed (status:null) rather than crashing the shell."""
    bad = tmp_path / "live_operation.json"
    bad.write_text("{ not json", encoding="utf-8")
    monkeypatch.setenv("SOVEREIGN_LIVE_OPERATION_CONFIG", str(bad))
    feed = em.build_subscription_status_feed()   # default path → env override → malformed → raises → caught
    assert feed["authorized"] is False
    assert feed["status"] is None
    assert "LiveAuthorizationError" in feed["reason"]


# --- no live side effects --------------------------------------------------------------------------

def test_no_credential_no_network_pure_record(monkeypatch):
    """The emitter must not touch the network or a credential store — it only reads the authorization
    gate and builds an in-memory governor. Guard urllib so a regression is caught."""
    import urllib.request

    def _boom(*a, **k):  # pragma: no cover - only runs on a regression
        raise AssertionError("emit_subscription_status made a network call (§2.4 violation)")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    feed = em.build_subscription_status_feed(live_auth=_authorized())
    assert feed["authorized"] is True


def providers_of(status: dict) -> list[str]:
    return [rec["provider"] for rec in status.values()]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
