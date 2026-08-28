"""Durable I-X3 terminal-lease ledger (Phase 17A `.lease`).

Until now the subscription governor (`SubscriptionGovernor`) was purely IN-PROCESS: every bounded
emitter built a fresh governor, acquired, and released at teardown, so a terminal held by the
LONG-LIVED shell (a real interactive `claude` session in pane 1) could never be counted. 17A needs a
live session that OUTLIVES the emitter that gated it — so the count has to outlive the emitter too,
or the I-X3 cap becomes decorative.

These tests pin the durable ledger's contract, all deterministic and fail-closed:

  * a lease survives the process that took it (it is a file record, not memory);
  * the OP-6 allowance is enforced ACROSS processes — the (allowance+1)-th acquire is refused with
    `SubscriptionLimitExceeded`, and the governor's `MAX_ALLOWANCE` cap is re-asserted here so no
    caller can widen concurrency by passing a bigger number;
  * a lease whose HOLDER PROCESS IS DEAD is reaped — a crashed shell never wedges the count
    (fail-closed the other way would be a permanent denial of the operator's own subscription);
  * acquire is idempotent per (subscription_ref, node_id) — a re-run of the same governed spawn
    re-uses its lease instead of double-counting;
  * `seed_governor` projects the durable live leases into an in-process `SubscriptionGovernor`, which
    is how the emitter's gate chain sees terminals held by OTHER processes;
  * release is by lease id (and by node), idempotent, and never touches another holder's lease;
  * the ledger file is the only state; a corrupt/absent file reads as EMPTY but a corrupt file is
    never silently overwritten with a fabricated count — it fails closed on read.
"""
from __future__ import annotations

import json
import os

import pytest

from node_runtime.supervisor.subscription_governor import (
    MAX_ALLOWANCE,
    SubscriptionGovernor,
    SubscriptionLimitExceeded,
)
from node_runtime.supervisor.terminal_lease import (
    DEFAULT_LEDGER_PATH,
    LEDGER_PATH_ENV,
    LeaseLedgerCorrupt,
    LeaseLedgerLocked,
    TerminalLease,
    TerminalLeaseLedger,
    default_ledger_path,
    win_pid_alive,
)

#: Win32: OpenProcess failed because the process EXISTS but belongs to someone else.
ERROR_ACCESS_DENIED = 5

REF = "claude-sub"
PROVIDER = "claude_code"


def _ledger(tmp_path, *, alive=None, pid=None):
    """A ledger on a temp file. `alive` decides pid liveness deterministically (no real processes)."""
    live_pids = set(alive if alive is not None else [os.getpid()])
    return TerminalLeaseLedger(
        path=tmp_path / "leases.json",
        pid_alive=lambda p: p in live_pids,
    ), (pid if pid is not None else os.getpid())


def test_lease_survives_the_process_that_took_it(tmp_path):
    """The point of the whole module: a SECOND ledger object over the same file sees the lease."""
    led, pid = _ledger(tmp_path)
    lease = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1",
                        allowance=2, holder_pid=pid, purpose="conductor-pane")
    assert isinstance(lease, TerminalLease)
    assert lease.lease_id and lease.node_id == "conductor-pane-1" and lease.holder_pid == pid

    reopened = TerminalLeaseLedger(path=tmp_path / "leases.json", pid_alive=lambda p: p == pid)
    live = reopened.live(REF)
    assert [ln.lease_id for ln in live] == [lease.lease_id]
    assert reopened.in_use(REF) == 1


def test_allowance_is_enforced_across_processes(tmp_path):
    """Two holders fill the OP-6 allowance of 2; a THIRD is refused — fail closed, no third terminal."""
    led, pid = _ledger(tmp_path)
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2, holder_pid=pid)
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n2", allowance=2, holder_pid=pid)
    assert led.in_use(REF) == 2
    with pytest.raises(SubscriptionLimitExceeded) as exc:
        led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n3", allowance=2, holder_pid=pid)
    assert "allowance" in str(exc.value)
    assert led.in_use(REF) == 2  # the refusal never mutated the ledger


def test_allowance_above_the_governor_cap_is_refused(tmp_path):
    """Defense in depth: the ledger re-asserts the governor's OP-6 hard cap, so a widened caller
    cannot buy a third terminal by passing allowance=3."""
    led, pid = _ledger(tmp_path)
    with pytest.raises(ValueError) as exc:
        led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1",
                    allowance=MAX_ALLOWANCE + 1, holder_pid=pid)
    assert str(MAX_ALLOWANCE) in str(exc.value)
    assert led.in_use(REF) == 0


def test_acquire_is_idempotent_per_node(tmp_path):
    """A re-run of the same governed spawn re-uses its own lease rather than double-counting."""
    led, pid = _ledger(tmp_path)
    a = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2, holder_pid=pid)
    b = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2, holder_pid=pid)
    assert a.lease_id == b.lease_id
    assert led.in_use(REF) == 1


def test_dead_holder_leases_are_reaped(tmp_path):
    """A crashed shell must not wedge the operator's subscription: a lease whose holder pid is gone
    is not live, is reported by `reap()`, and frees the slot."""
    led, _ = _ledger(tmp_path, alive=[111])
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2, holder_pid=111)
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n2", allowance=2, holder_pid=111)
    assert led.in_use(REF) == 2

    # the holder process dies
    dead = TerminalLeaseLedger(path=tmp_path / "leases.json", pid_alive=lambda p: False)
    reaped = dead.reap()
    assert sorted(ln.node_id for ln in reaped) == ["n1", "n2"]
    assert dead.in_use(REF) == 0
    # and the slot is genuinely reusable
    dead2 = TerminalLeaseLedger(path=tmp_path / "leases.json", pid_alive=lambda p: p == 222)
    dead2.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n3", allowance=2, holder_pid=222)
    assert dead2.in_use(REF) == 1


def test_release_is_by_lease_id_idempotent_and_scoped(tmp_path):
    led, pid = _ledger(tmp_path)
    a = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2, holder_pid=pid)
    b = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n2", allowance=2, holder_pid=pid)
    assert led.release(a.lease_id) is True
    assert led.release(a.lease_id) is False          # idempotent, no error
    assert [ln.lease_id for ln in led.live(REF)] == [b.lease_id]   # the other holder is untouched
    assert led.release("no-such-lease") is False


def test_release_node_releases_only_that_node(tmp_path):
    led, pid = _ledger(tmp_path)
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2, holder_pid=pid)
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n2", allowance=2, holder_pid=pid)
    assert led.release_node(REF, "n1") == 1
    assert [ln.node_id for ln in led.live(REF)] == ["n2"]


def test_two_sessions_of_the_same_node_are_two_counted_terminals(tmp_path):
    """U75 (`.pty`): the conductor NODE id is a constant (`conductor-pane-1`), so node-keyed
    idempotence would count N real interactive sessions as ONE terminal — I-X3 defeated the moment
    the shell can actually launch. A lease is keyed to the SESSION that holds it."""
    led, pid = _ledger(tmp_path)
    a = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1",
                    allowance=2, holder_pid=pid, session_id="pane-1#1")
    b = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1",
                    allowance=2, holder_pid=pid, session_id="pane-1#2")
    assert a.lease_id != b.lease_id
    assert a.session_id == "pane-1#1" and b.session_id == "pane-1#2"
    assert led.in_use(REF) == 2
    # and the cap still binds: a THIRD session of the same node is refused, not silently adopted
    with pytest.raises(SubscriptionLimitExceeded):
        led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1",
                    allowance=2, holder_pid=pid, session_id="pane-1#3")


def test_acquire_stays_idempotent_within_one_session(tmp_path):
    """Idempotence is preserved where it was correct — a RE-RUN of the same governed spawn for the
    same session (and the sessionless, not-yet-launched case) re-uses its lease."""
    led, pid = _ledger(tmp_path)
    a = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2,
                    holder_pid=pid, session_id="s1")
    b = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2,
                    holder_pid=pid, session_id="s1")
    assert a.lease_id == b.lease_id
    c = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n2", allowance=2, holder_pid=pid)
    d = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n2", allowance=2, holder_pid=pid)
    assert c.lease_id == d.lease_id and c.session_id == ""
    assert led.in_use(REF) == 2


def test_release_session_releases_exactly_that_session(tmp_path):
    """U77 (`.pty`): the shell knows the SESSION key before it asks for a ticket, so a ticket whose
    delivery fails (parse refusal / timeout) can be reclaimed by key — without touching the other
    live session of the same node."""
    led, pid = _ledger(tmp_path)
    keep = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1",
                       allowance=2, holder_pid=pid, session_id="s-live")
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1",
                allowance=2, holder_pid=pid, session_id="s-orphan")
    assert led.release_session(REF, "s-orphan") == 1
    assert [ln.lease_id for ln in led.live(REF)] == [keep.lease_id]
    assert led.release_session(REF, "s-orphan") == 0        # idempotent: nothing left to reclaim
    assert led.release_session(REF, "") == 0                # never a wildcard over sessionless leases


def test_seed_governor_counts_each_session_separately(tmp_path):
    """The in-process governor keys `active` by node id, so seeding two sessions of ONE node under
    that id would collapse them to a single holder and hand the emitter's gate chain a free slot
    that does not exist. Seeding is by LEASE key."""
    led, pid = _ledger(tmp_path)
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1", allowance=2,
                holder_pid=pid, session_id="s1")
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1", allowance=2,
                holder_pid=pid, session_id="s2")
    gov = SubscriptionGovernor()
    led.seed_governor(gov, subscription_ref=REF, provider=PROVIDER, allowance=2)
    assert gov.active_count(REF) == 2
    with pytest.raises(SubscriptionLimitExceeded):
        gov.acquire(REF, "conductor-pane-1")


def test_a_legacy_1_0_ledger_reads_as_sessionless_never_as_corrupt(tmp_path):
    """A ledger written before per-session keys (a live shell mid-upgrade) is READ, not rejected:
    its records are sessionless, so the count stays honest instead of failing closed on the
    operator's own held terminal."""
    path = tmp_path / "leases.json"
    path.write_text(json.dumps({
        "schema": "terminal_lease_ledger@1.0", "updated": "2026-07-25T00:00:00+00:00",
        "leases": [{"lease_id": "lease-old", "subscription_ref": REF, "provider": PROVIDER,
                    "node_id": "conductor-pane-1", "holder_pid": os.getpid(),
                    "acquired_at": "2026-07-25T00:00:00+00:00", "purpose": "legacy"}],
    }, indent=2), encoding="utf-8")
    led = TerminalLeaseLedger(path=path, pid_alive=lambda p: True, clock=lambda: "2026-07-25T00:00:00+00:00")
    live = led.live(REF)
    assert [ln.lease_id for ln in live] == ["lease-old"] and live[0].session_id == ""


def test_a_legacy_sessionless_lease_is_UPGRADED_not_duplicated(tmp_path):
    """Schema transition (@1.0 → @1.1): a shell that already holds a sessionless lease and then
    takes a session-keyed one must not consume 2 of 2 — one real session, two records, and the
    operator locked out of their own subscription mid-upgrade."""
    led, pid = _ledger(tmp_path)
    legacy = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1",
                         allowance=2, holder_pid=pid)          # sessionless, as @1.0 wrote them
    upgraded = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1",
                           allowance=2, holder_pid=pid, session_id="pane-1#1")
    assert upgraded.lease_id == legacy.lease_id                 # the SAME terminal, re-keyed
    assert upgraded.session_id == "pane-1#1"
    assert led.in_use(REF) == 1


def test_another_processes_sessionless_lease_is_never_adopted(tmp_path):
    """The upgrade above is scoped to OUR pid: a sessionless lease held by a different process is
    someone else's terminal and must still count against us."""
    led, pid = _ledger(tmp_path, alive=[os.getpid(), 999])
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="worker-x", allowance=2,
                holder_pid=999)
    mine = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="worker-x", allowance=2,
                       holder_pid=pid, session_id="s-mine")
    assert mine.session_id == "s-mine"
    assert led.in_use(REF) == 2


def test_seed_governor_projects_other_processes_holdings(tmp_path):
    """This is how the emitter's IN-PROCESS gate chain sees a terminal held by the shell: the durable
    live leases are seeded as active holders, so the next in-process acquire is refused honestly."""
    led, pid = _ledger(tmp_path)
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="shell-held-1", allowance=2, holder_pid=pid)
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="shell-held-2", allowance=2, holder_pid=pid)

    gov = SubscriptionGovernor()
    led.seed_governor(gov, subscription_ref=REF, provider=PROVIDER, allowance=2)
    assert gov.active_count(REF) == 2
    with pytest.raises(SubscriptionLimitExceeded):
        gov.acquire(REF, "conductor-pane-1")


def test_seed_governor_leaves_room_when_below_allowance(tmp_path):
    led, pid = _ledger(tmp_path)
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="shell-held-1", allowance=2, holder_pid=pid)
    gov = SubscriptionGovernor()
    led.seed_governor(gov, subscription_ref=REF, provider=PROVIDER, allowance=2)
    gov.acquire(REF, "conductor-pane-1")            # the free slot is genuinely free
    assert gov.active_count(REF) == 2


def test_snapshot_is_the_observable_count(tmp_path):
    led, pid = _ledger(tmp_path)
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2,
                holder_pid=pid, purpose="conductor-pane")
    snap = led.snapshot()
    assert snap[REF]["in_use"] == 1
    assert snap[REF]["provider"] == PROVIDER
    assert snap[REF]["holders"][0]["node_id"] == "n1"
    assert snap[REF]["holders"][0]["purpose"] == "conductor-pane"
    # a snapshot never leaks an environment/credential surface — it is identity + counting only
    # (`scope` says which ledger the holder is recorded in, U111 — still counting, not a surface)
    assert set(snap[REF]["holders"][0]) == {
        "lease_id", "node_id", "session_id", "holder_pid", "acquired_at", "purpose", "scope"}


def test_absent_file_reads_empty(tmp_path):
    led = TerminalLeaseLedger(path=tmp_path / "nope" / "leases.json", pid_alive=lambda p: True)
    assert led.live() == []
    assert led.in_use(REF) == 0
    assert led.snapshot() == {}


def test_corrupt_file_fails_closed_and_is_not_overwritten(tmp_path):
    """A corrupt ledger is NOT silently reset — that would fabricate a zero count and hand out a
    terminal the operator may already be using. It fails closed; the operator/loop repairs it."""
    p = tmp_path / "leases.json"
    p.write_text("{not json", encoding="utf-8")
    led = TerminalLeaseLedger(path=p, pid_alive=lambda x: True)
    with pytest.raises(LeaseLedgerCorrupt):
        led.live()
    with pytest.raises(LeaseLedgerCorrupt):
        led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2, holder_pid=1)
    assert p.read_text(encoding="utf-8") == "{not json"   # untouched


def test_windows_access_denied_counts_as_ALIVE(tmp_path):
    """Regression (gate-validator R3 / spec-audit F3): `OpenProcess` returns NULL both for "gone"
    and for "exists but you may not touch it" (an elevated/other-user shell holding a terminal).
    Reading access-denied as dead would reap a LIVE holder's lease and mint a terminal past the
    I-X3 cap — fail-open in the one direction that matters."""
    closed: list[int] = []
    def probe(err, handle=0):
        return win_pid_alive(
            1234,
            open_process=lambda p: handle,
            last_error=lambda: err,
            wait=lambda h: 0x00000102,   # WAIT_TIMEOUT ⇒ still running
            close=closed.append)
    assert probe(ERROR_ACCESS_DENIED) is True            # exists, not ours ⇒ alive
    assert probe(87) is False                            # ERROR_INVALID_PARAMETER ⇒ gone
    assert probe(0, handle=99) is True                   # opened + not signalled ⇒ alive
    assert closed == [99]                                # and the handle is always closed


def test_a_live_holders_lock_is_never_broken(tmp_path):
    """Regression (spec-audit F8): breaking a lock on AGE alone lets two writers each unlink the
    other's fresh lock and silently lose an acquire. Ownership is the rule — a lock whose owner pid
    is alive is waited on (and refused on timeout), never stolen."""
    p = tmp_path / "leases.json"
    led = TerminalLeaseLedger(path=p, pid_alive=lambda x: x == 777,
                              lock_timeout_s=0.1, stale_lock_s=0.0)
    lock = p.with_suffix(p.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("777", encoding="utf-8")             # a LIVE holder, and instantly "stale" by age
    with pytest.raises(LeaseLedgerLocked):
        led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2, holder_pid=777)
    assert lock.exists(), "the live holder's lock must survive"


def test_a_dead_holders_lock_is_broken(tmp_path):
    """The other half: a writer that crashed holding the lock must not wedge the ledger forever."""
    p = tmp_path / "leases.json"
    led = TerminalLeaseLedger(path=p, pid_alive=lambda x: x == 555,
                              lock_timeout_s=1.0, stale_lock_s=999.0)
    lock = p.with_suffix(p.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("999", encoding="utf-8")             # a DEAD owner, and far from stale by age
    lease = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2,
                        holder_pid=555)
    assert lease.node_id == "n1"
    assert not lock.exists(), "the lock is released after the mutation"


def test_ledger_path_honors_the_scratch_override(tmp_path, monkeypatch):
    """A self-check must be able to run against a SCRATCH ledger: without it, an in-runtime check
    would acquire (and then release) a lease on the same node id the operator's own running
    conductor holds — uncounting a live session — and would have to assert a globally empty count."""
    monkeypatch.delenv(LEDGER_PATH_ENV, raising=False)
    assert default_ledger_path() == DEFAULT_LEDGER_PATH
    monkeypatch.setenv(LEDGER_PATH_ENV, str(tmp_path / "scratch.json"))
    assert default_ledger_path() == tmp_path / "scratch.json"
    assert TerminalLeaseLedger().path == tmp_path / "scratch.json"


def test_ledger_file_shape_is_versioned_json(tmp_path):
    led, pid = _ledger(tmp_path)
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2, holder_pid=pid)
    doc = json.loads((tmp_path / "leases.json").read_text(encoding="utf-8"))
    assert doc["schema"] == "terminal_lease_ledger@1.1"   # @1.1 adds the per-session key (U75)
    assert isinstance(doc["leases"], list) and len(doc["leases"]) == 1
    rec = doc["leases"][0]
    assert rec["subscription_ref"] == REF and rec["provider"] == PROVIDER
    # no env, no token, no argv is ever persisted in the ledger (§2.2 — counting state only)
    assert set(rec) == {"lease_id", "subscription_ref", "provider", "node_id", "session_id",
                        "holder_pid", "acquired_at", "purpose"}


# ---------------------------------------------------------------------------------------------
# U111 — DIAGNOSTIC SCOPE: a redirected ledger writes its own records but COUNTS the durable ones
# ---------------------------------------------------------------------------------------------
# Opened at 17B `.spawn` (spec-audit MINOR-8) with 17E named as owner, and found again by the 17E
# spec-auditor (F1) with the exposure doubled: the fully-live run holds TWO live frontier terminals
# on the operator's subscription while `SOW_TERMINAL_LEASE_LEDGER` points at a per-pid scratch file,
# so for that window the real governor counts ZERO — and an operator shell already at its allowance
# of 2 could bring the true total to 4. The redirection itself is right: a check must never adopt or
# release a terminal the operator's own shell holds. What was missing is the other half — the cap has
# to be enforced across BOTH holder classes. So a redirected ledger is a DIAGNOSTIC one: it writes
# only its own scratch records, and it counts the durable ledger's live leases as a read-only
# baseline it can see but never touch.


def _diagnostic(tmp_path, *, alive=None):
    """A diagnostic-scope ledger (scratch file) over a separate durable baseline file."""
    live_pids = set(alive if alive is not None else [os.getpid()])
    scratch = TerminalLeaseLedger(
        path=tmp_path / "scratch.json", baseline_path=tmp_path / "durable.json",
        pid_alive=lambda p: p in live_pids)
    durable = TerminalLeaseLedger(path=tmp_path / "durable.json", pid_alive=lambda p: p in live_pids)
    return scratch, durable, os.getpid()


def test_a_redirected_ledger_declares_itself_diagnostic(tmp_path, monkeypatch):
    """The scope is not a comment: the env override IS the diagnostic mechanism, and an explicitly
    constructed ledger (every test, every fixture) is never silently pointed at the operator's file."""
    monkeypatch.setenv(LEDGER_PATH_ENV, str(tmp_path / "scratch.json"))
    redirected = TerminalLeaseLedger()
    assert redirected.scope == "diagnostic"
    assert redirected.baseline_path == DEFAULT_LEDGER_PATH
    # an explicit path is a caller's own ledger, not a diagnostic overlay on the host's
    assert TerminalLeaseLedger(path=tmp_path / "other.json").scope == "durable"
    monkeypatch.delenv(LEDGER_PATH_ENV, raising=False)
    assert TerminalLeaseLedger().scope == "durable"
    assert TerminalLeaseLedger().baseline_path is None


def test_diagnostic_scope_counts_the_operator_terminals_it_cannot_see(tmp_path):
    """The U111 hole itself: with the operator's shell holding one durable terminal, a diagnostic
    ledger used to report 0 and admit 2 more. It now reports the total and admits only the rest."""
    scratch, durable, pid = _diagnostic(tmp_path)
    durable.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1",
                    allowance=2, holder_pid=pid, purpose="the operator's own shell")
    assert scratch.own_in_use(REF) == 0
    assert scratch.baseline_in_use(REF) == 1
    assert scratch.in_use(REF) == 1, "the governing count is both holder classes"
    scratch.acquire(subscription_ref=REF, provider=PROVIDER, node_id="selfcheck-worker",
                    allowance=2, holder_pid=pid, purpose="in-Electron check")
    assert scratch.in_use(REF) == 2
    with pytest.raises(SubscriptionLimitExceeded) as exc:
        scratch.acquire(subscription_ref=REF, provider=PROVIDER, node_id="selfcheck-second",
                        allowance=2, holder_pid=pid)
    assert "durable baseline" in str(exc.value), "the refusal must name the holders it cannot see"


def test_a_diagnostic_ledger_never_writes_to_or_releases_the_durable_one(tmp_path):
    """Counting both is the whole change — adopting the operator's leases would be the old bug in
    the other direction (a check releasing a terminal the operator's live conductor still holds)."""
    scratch, durable, pid = _diagnostic(tmp_path)
    held = durable.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1",
                           allowance=2, holder_pid=pid)
    before = (tmp_path / "durable.json").read_bytes()
    mine = scratch.acquire(subscription_ref=REF, provider=PROVIDER, node_id="selfcheck-worker",
                           allowance=2, holder_pid=pid)
    assert scratch.release(mine.lease_id) is True
    assert scratch.release(held.lease_id) is False, "a diagnostic ledger cannot release a durable lease"
    assert scratch.release_node(REF, "conductor-pane-1") == 0
    assert (tmp_path / "durable.json").read_bytes() == before, "the durable ledger was written to"
    assert durable.in_use(REF) == 1
    assert scratch.own_in_use(REF) == 0 and scratch.in_use(REF) == 1


def test_diagnostic_snapshot_separates_the_two_holder_classes(tmp_path):
    """Invariant 27: the count is observable, and a reader can tell WHOSE terminals it is looking at
    — otherwise the honest total is just as unreadable as the dishonest zero was."""
    scratch, durable, pid = _diagnostic(tmp_path)
    durable.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1",
                    allowance=2, holder_pid=pid)
    scratch.acquire(subscription_ref=REF, provider=PROVIDER, node_id="selfcheck-worker",
                    allowance=2, holder_pid=pid)
    snap = scratch.snapshot()[REF]
    assert snap["in_use"] == 2 and snap["own_in_use"] == 1 and snap["baseline_in_use"] == 1
    assert snap["scope"] == "diagnostic"
    assert sorted((h["node_id"], h["scope"]) for h in snap["holders"]) == [
        ("conductor-pane-1", "durable"), ("selfcheck-worker", "diagnostic")]
    # a subscription held ONLY by the operator must not vanish from a diagnostic snapshot
    durable.acquire(subscription_ref="other-sub", provider=PROVIDER, node_id="n", allowance=2,
                    holder_pid=pid)
    assert scratch.snapshot()["other-sub"]["baseline_in_use"] == 1


def test_a_durable_scope_snapshot_is_unchanged_in_shape(tmp_path):
    """The product path must read exactly as before: own == total, baseline zero, scope durable."""
    led, pid = _ledger(tmp_path)
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2, holder_pid=pid)
    snap = led.snapshot()[REF]
    assert snap["in_use"] == 1 and snap["own_in_use"] == 1 and snap["baseline_in_use"] == 0
    assert snap["scope"] == "durable" and led.baseline_in_use(REF) == 0
    assert all(h["scope"] == "durable" for h in snap["holders"])


def test_seed_governor_projects_the_operator_terminals_too(tmp_path):
    """A bounded emitter under a diagnostic ledger must inherit the same refusal: its in-process gate
    chain has to see the terminals the operator's shell holds, or the cap is decorative there too."""
    scratch, durable, pid = _diagnostic(tmp_path)
    durable.acquire(subscription_ref=REF, provider=PROVIDER, node_id="conductor-pane-1",
                    allowance=2, holder_pid=pid)
    scratch.acquire(subscription_ref=REF, provider=PROVIDER, node_id="selfcheck-worker",
                    allowance=2, holder_pid=pid)
    gov = SubscriptionGovernor()
    seeded = scratch.seed_governor(gov, subscription_ref=REF, provider=PROVIDER, allowance=2)
    assert sorted(ln.node_id for ln in seeded) == ["conductor-pane-1", "selfcheck-worker"]
    with pytest.raises(SubscriptionLimitExceeded):
        gov.acquire(REF, "a-third-node")


def test_an_unreadable_durable_ledger_fails_the_diagnostic_count_closed(tmp_path):
    """Ambiguity is not zero: if the baseline cannot be read, a diagnostic ledger refuses to count
    (and therefore to admit) rather than reporting the reassuring number."""
    (tmp_path / "durable.json").write_text("{not json", encoding="utf-8")
    scratch, _durable, pid = _diagnostic(tmp_path)
    with pytest.raises(LeaseLedgerCorrupt):
        scratch.baseline_in_use(REF)
    with pytest.raises(LeaseLedgerCorrupt):
        scratch.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n", allowance=2,
                        holder_pid=pid)


def test_a_dead_operator_holder_does_not_wedge_a_diagnostic_check(tmp_path):
    """The reap rule applies to the baseline as well — a crashed shell's record is not a live
    terminal, and a check must not be denied by a corpse."""
    scratch, _durable, pid = _diagnostic(tmp_path, alive=[os.getpid()])
    TerminalLeaseLedger(path=tmp_path / "durable.json", pid_alive=lambda p: True).acquire(
        subscription_ref=REF, provider=PROVIDER, node_id="crashed-shell", allowance=2,
        holder_pid=999999, purpose="a shell that died")
    assert scratch.baseline_in_use(REF) == 0
    assert scratch.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n", allowance=2,
                           holder_pid=pid).node_id == "n"


# ---- W-14 / A-4 + R-26: an empty ledger is not an absent one -----------------------------------
# `_read` treated a zero-length file as "no leases" and granted an OVER-CAP acquire, while non-JSON
# corruption correctly failed closed. So the module's own guarantee -- "a corrupt ledger fails
# closed and is never silently reset" -- was implemented for the case a filesystem rarely produces
# and missing for the one it does.
#
# Compounding, and causally linked: `_write` wrote a temp file and `os.replace`d it with NO fsync of
# the file, so a crash could leave exactly the zero-length ledger the branch above then read as
# "no terminals are held".

def test_a_zero_length_ledger_fails_closed_exactly_as_a_json_error_does(tmp_path):
    """A zero-byte ledger is NOT an ABSENT ledger. Absent means no terminal was ever taken;
    zero-byte means a file exists and says nothing, which is what a lost write leaves behind."""
    p = tmp_path / "leases.json"
    p.write_bytes(b"")
    led = TerminalLeaseLedger(path=p, pid_alive=lambda x: True)
    with pytest.raises(LeaseLedgerCorrupt):
        led.live()
    with pytest.raises(LeaseLedgerCorrupt):
        led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2, holder_pid=1)


def test_a_whitespace_only_ledger_fails_closed_too(tmp_path):
    """The old guard was `if not raw.strip()`, so whitespace took the same silent path."""
    p = tmp_path / "leases.json"
    p.write_text("   \n\n", encoding="utf-8")
    led = TerminalLeaseLedger(path=p, pid_alive=lambda x: True)
    with pytest.raises(LeaseLedgerCorrupt):
        led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=1, holder_pid=1)


def test_an_ABSENT_ledger_is_still_empty_and_still_grants(tmp_path):
    """POSITIVE. The FileNotFoundError path must not move: no ledger yet really does mean no
    terminals are held, and a first acquire has to work."""
    led, pid = _ledger(tmp_path)
    assert led.in_use(REF) == 0
    lease = led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1",
                        allowance=2, holder_pid=pid)
    assert lease is not None
    assert led.in_use(REF) == 1


def test_the_ledger_write_is_fsynced_before_the_replace(tmp_path, monkeypatch):
    """R-26. Donor: `control_plane/nodes/event_log.py:77-78` fsyncs every append. Without it the
    ledger's own atomicity claim covers the RENAME and not the BYTES, which is how a zero-length
    ledger becomes reachable in the first place."""
    import node_runtime.supervisor.terminal_lease as mod

    real_fsync = os.fsync
    synced: list[int] = []

    def _record(fd):
        synced.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(mod.os, "fsync", _record)
    led, pid = _ledger(tmp_path)
    led.acquire(subscription_ref=REF, provider=PROVIDER, node_id="n1", allowance=2, holder_pid=pid)
    assert synced, "the lease ledger was replaced without fsyncing the bytes it replaced it with"

def test_query_reads_take_the_ledger_lock(tmp_path):
    """W-73. The query path is not safe next to a locked replace when it reads unlocked: on Windows
    an open read handle blocks `os.replace`, so an unserialized reader both breaks the writer
    (WinError 5) and can be refused itself as "unreadable". Queries join the same filesystem mutex
    the writers already hold."""
    led, _pid = _ledger(tmp_path)
    entered = []

    class _CountingLock(TerminalLeaseLedger._Lock):
        def __enter__(self):
            entered.append(1)
            return super().__enter__()

    real_lock = TerminalLeaseLedger._Lock
    try:
        led._Lock = _CountingLock
        led.live()
    finally:
        led._Lock = real_lock
    assert entered, "live() read the ledger file without taking the ledger lock"


def test_a_query_reader_never_overlaps_a_locked_write(tmp_path, monkeypatch):
    """W-73, deterministic choreography - no thread racing. Measured at HEAD before this repair:
    9900 acquire/release cycles against two hammering unlocked readers produced 13
    PermissionError[WinError 5] on os.replace - the reader's open handle blocked the rename - and
    each failed release left its lease counted. Here the main thread ISSUES a query while a write
    is provably in flight: pre-repair the unlocked read lands inside the write window (the overlap
    counter fires); post-repair the query blocks on the ledger lock until the write completes."""
    import threading

    import node_runtime.supervisor.terminal_lease as mod

    led, pid = _ledger(tmp_path)
    in_write = threading.Event()
    write_open = threading.Event()
    overlaps = []
    done = []

    real_read = mod.TerminalLeaseLedger._read
    real_write = mod.TerminalLeaseLedger._write

    def _read(self):
        if in_write.is_set():
            overlaps.append(1)
        return real_read(self)

    def _write(self, leases):
        in_write.set()
        write_open.set()
        try:
            return real_write(self, leases)
        finally:
            in_write.clear()

    monkeypatch.setattr(mod.TerminalLeaseLedger, "_read", _read)
    monkeypatch.setattr(mod.TerminalLeaseLedger, "_write", _write)

    def writer():
        # ONE lock cycle only: the acquire whose gated write signals mid-hold. A later release()
        # would need the lock AGAIN and could lose its retry race to the very waiter this test
        # deliberately parks on the lock - the unfair O_EXCL retry would then starve the writer
        # into LeaseLedgerLocked and the fixture, not the product, would have failed (W-73).
        led.acquire(subscription_ref=REF, provider=PROVIDER,
                    node_id="w", allowance=2, holder_pid=pid, session_id="s1")
        done.append(1)

    wt = threading.Thread(target=writer)
    wt.start()
    # Block until the write is IN FLIGHT, then issue the query from THIS thread. Post-repair the
    # query waits on the ledger lock for the rest of the writer's hold; pre-repair it read
    # immediately inside the write window.
    assert write_open.wait(timeout=10), "the writer never reached its write"
    led.in_use(REF)
    wt.join(timeout=30)

    assert done == [1], "the writer did not complete"
    assert not overlaps, (
        "a query read ran inside a locked write's window: %d overlap(s)" % len(overlaps))



def test_the_lock_release_retries_a_transiently_denied_unlink(tmp_path, monkeypatch):
    """W-73, second half. A waiter reading the owner pid holds a transient O_RDONLY handle on the
    lock file; on Windows that denies the holder's unlink at release. The swallowed OSError used
    to orphan the lock under a LIVE owner pid - which the break rules never remove - so every
    later acquirer of that ledger wedged into LeaseLedgerLocked. Release must retry briefly and
    only then give up loudly."""
    import node_runtime.supervisor.terminal_lease as mod

    led, pid = _ledger(tmp_path)
    lock_path = led.path.with_suffix(led.path.suffix + ".lock")

    denied = []
    real_unlink = mod.os.unlink

    def _unlink(path, *a, **kw):
        s = str(path)
        if s.endswith(".lock") and not denied:
            denied.append(s)
            raise PermissionError(13, "transient denial while a waiter reads the pid", s)
        return real_unlink(path, *a, **kw)

    monkeypatch.setattr(mod.os, "unlink", _unlink)

    lease = led.acquire(subscription_ref=REF, provider=PROVIDER,
                        node_id="n1", allowance=2, holder_pid=pid)
    led.release(lease.lease_id)

    assert denied, "the transient unlink denial was never exercised"
    assert not lock_path.exists(), (
        "the lock file survived its own release - an orphan under a live owner pid wedges "
        "every later acquirer of this ledger into LeaseLedgerLocked")
