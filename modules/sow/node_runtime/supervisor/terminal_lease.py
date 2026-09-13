"""Durable I-X3 terminal leases — the count that outlives the process that took it.

Phase 17A `.lease` (directive §16 track 17A). `SubscriptionGovernor` is an IN-PROCESS counter: every
bounded emitter in this build creates one, acquires, and releases at teardown (D-LOOP-1). That was
correct while no live terminal outlived its emitter. 17A ends that: the CONDUCTOR pane runs a REAL
interactive `claude` session inside the shell's ConPTY, owned by the long-lived Electron process,
gated by a short-lived Python emitter. If the count died with the emitter, I-X3 would be decorative —
the shell could hold two sessions while every emitter reported 0/2.

This module is the durable half: a small, file-backed, cross-process lease ledger.

  * **Authority stays where it is.** The ledger COUNTS; it does not authorize. The allowance is
    passed in by the caller from the enforced `LiveAuthorization.terminals_for(provider)` (the
    per-provider allowance, itself code-pinned per authorizing register row), and the governor's
    `MAX_ALLOWANCE` hard cap, its per-provider cap and its ref-to-provider binding are all
    re-asserted here as defense in depth — a widened caller cannot buy a further terminal by
    passing a bigger number, and cannot buy one by inventing a second ref spelling either.
  * **Fail closed on the count, open on the corpse.** Over-allowance ⇒ `SubscriptionLimitExceeded`,
    no mutation. But a lease whose HOLDER PROCESS IS DEAD is reaped: a crashed shell must not wedge
    the operator's own subscription forever. Liveness is a pid check, injectable for tests.
  * **Counting state only (§2.2).** A lease record is identity + pid + timestamp + purpose. No env,
    no argv, no token, nothing credential-bearing is ever persisted or returned.
  * **A corrupt ledger fails closed and is never silently reset** — resetting would fabricate a zero
    count and hand out a terminal the operator may already be using.

Concurrency: every mutation is a read-modify-write under an exclusive lock file
(`O_CREAT|O_EXCL`, bounded spin), and the ledger is written via a temp file + `os.replace` so a
reader never observes a half-written document. A lock is broken only when its recorded owner pid is
GONE (age is the fallback for a pid that was never written) — an age-only rule lets two writers each
unlink the other's fresh lock and silently lose an acquire. Sufficient for the writers this build
has on one host; it is not a distributed lock and does not pretend to be.

A lease is keyed to `(subscription_ref, node_id, session_id)` (schema `@1.1`, Phase 17A `.pty`,
closing U75). The conductor NODE id is a constant (`conductor-pane-1`), so node-only keying counted N
real interactive sessions as ONE terminal — latent while nothing launched, load-bearing the moment the
shell can spawn. `session_id` is the identity of the ConPTY session that will hold the terminal;
sessionless (`""`) leases keep the old node-level idempotence for the not-yet-launched case, and a
`@1.0` ledger written by an older process is read as sessionless rather than rejected.

KNOWN LIMITS, recorded rather than implied away: release performs no ownership check, so the durable
cap binds cooperating local callers, not a hostile one; and pid recycling is not defended against.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from node_runtime.supervisor.subscription_governor import (
    MAX_ALLOWANCE,
    SubscriptionGovernor,
    SubscriptionLimitExceeded,
    assert_resource_binding,
    provider_allowance_cap,
)

#: Pinned so a drifted producer/consumer is refused rather than misread. `@1.1` adds `session_id`
#: (U75 — a lease belongs to a SESSION, not to a node id that never changes).
LEDGER_SCHEMA = "terminal_lease_ledger@1.1"

#: Schemas this ledger will READ. `@1.0` records predate per-session keys and are read as
#: sessionless — a live shell holding a `@1.0` lease must not have its terminal declared corrupt
#: (fail-closed on an unreadable file is right; fail-closed on our own older format is not).
READABLE_LEDGER_SCHEMAS = ("terminal_lease_ledger@1.1", "terminal_lease_ledger@1.0")

def _sow_store_root() -> Path:
    """F-131. The durable node store. The shell passes SOVEREIGN_STORE_ROOT=${state_root}/store;
    honour it so the lease ledger (which every governed frontier launch must write) lives in the
    writable state root and survives an upgrade that replaces the install tree. Falls back to the
    in-repo `.sovereign_store` only when the env is unset (a developer running standalone)."""
    declared = (os.environ.get("SOVEREIGN_STORE_ROOT") or "").strip()
    if declared:
        return Path(declared)
    state = (os.environ.get("SOVEREIGN_WORKSPACE_STATE") or "").strip()
    if state:
        return Path(state) / "store"
    return Path(__file__).resolve().parents[2] / ".sovereign_store"


#: A lease is host state, never a committed artifact. Now under the shell-declared store root.
DEFAULT_LEDGER_PATH = _sow_store_root() / "leases" / "terminal_leases.json"

#: Env override so a self-check or a test can run against a SCRATCH ledger instead of the operator's
#: real one. Without it an in-runtime check would acquire (and then release) a lease on the same
#: `(subscription_ref, node_id)` the operator's own running conductor may hold — uncounting a live
#: session — and would have to assert a globally-empty count, which is false on a host that is
#: legitimately busy. Isolation, not a weakening: the mechanism under test is identical.
LEDGER_PATH_ENV = "SOW_TERMINAL_LEASE_LEDGER"


def default_ledger_path() -> Path:
    """The host ledger path, honoring `SOW_TERMINAL_LEASE_LEDGER` (scratch ledgers for checks)."""
    override = os.environ.get(LEDGER_PATH_ENV)
    return Path(override) if override else DEFAULT_LEDGER_PATH

_LEASE_FIELDS = ("lease_id", "subscription_ref", "provider", "node_id", "session_id", "holder_pid",
                 "acquired_at", "purpose")


class LeaseLedgerCorrupt(Exception):
    """The ledger file exists but is not a readable `terminal_lease_ledger` document (see
    `READABLE_LEDGER_SCHEMAS`). Fail closed: refuse to read or mutate rather than reset it to an
    invented empty count. NOTE the transition is one-way — any mutation rewrites the file as the
    current schema, so a rolled-back pre-`.pty` binary would read its own ledger as corrupt (fail
    closed, and recorded here rather than discovered)."""


class LeaseLedgerLocked(Exception):
    """The exclusive lock could not be taken within the timeout — refuse rather than race."""


@dataclass(frozen=True)
class TerminalLease:
    """One counted subscription terminal, held by `holder_pid` until released or reaped.

    `session_id` identifies the SESSION that holds it (the shell's ConPTY session). Empty means a
    sessionless lease — the not-yet-launched case, and every `@1.0` record."""

    lease_id: str
    subscription_ref: str
    provider: str
    node_id: str
    holder_pid: int
    acquired_at: str
    purpose: str = ""
    session_id: str = ""

    @property
    def lease_key(self) -> str:
        """The identity a terminal is counted under: the session where there is one, else the node.

        Used when projecting into the in-process governor, whose `active` set is keyed by node id —
        two sessions of one node must not collapse into a single holder there either."""
        return f"{self.node_id}#{self.session_id}" if self.session_id else self.node_id

    def as_dict(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in _LEASE_FIELDS}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "TerminalLease":
        return TerminalLease(
            lease_id=str(d["lease_id"]), subscription_ref=str(d["subscription_ref"]),
            provider=str(d["provider"]), node_id=str(d["node_id"]),
            holder_pid=int(d["holder_pid"]), acquired_at=str(d["acquired_at"]),
            purpose=str(d.get("purpose", "")), session_id=str(d.get("session_id", "")))


#: Win32 error codes used by the liveness check.
_ERROR_ACCESS_DENIED = 5
_WAIT_TIMEOUT = 0x00000102
_SYNCHRONIZE = 0x00100000


def win_pid_alive(pid: int, open_process: Callable[[int], int], last_error: Callable[[], int],
                  wait: Callable[[int], int], close: Callable[[int], Any]) -> bool:
    """The Windows liveness rule, isolated from `ctypes` so it is actually testable.

    `OpenProcess` returning NULL means one of two very different things, and conflating them is
    fail-OPEN in the direction that matters: `ERROR_ACCESS_DENIED` means the process EXISTS but
    belongs to another user / an elevated session (an elevated shell holding a lease), while
    `ERROR_INVALID_PARAMETER` means it is gone. Treating access-denied as dead would reap a LIVE
    holder's lease and mint a terminal past the I-X3 cap — so access-denied counts as alive, exactly
    as the POSIX branch treats `PermissionError`."""
    handle = open_process(int(pid))
    if not handle:
        return last_error() == _ERROR_ACCESS_DENIED
    try:
        return wait(handle) == _WAIT_TIMEOUT   # still running (not signalled ⇒ not exited)
    finally:
        close(handle)


def pid_is_alive(pid: int) -> bool:
    """Is `pid` a live process on this host? Deterministic, no third-party dependency.

    Windows: `win_pid_alive` above. POSIX: `os.kill(pid, 0)`; `PermissionError` means the process
    exists but is not ours, which still counts as alive. NOTE `os.kill(pid, 0)` is NOT used on
    Windows — CPython maps it onto `TerminateProcess`, i.e. asking would kill the answer.

    KNOWN LIMIT (recorded, not papered over): a pid can be RECYCLED by the OS, so a lease could in
    principle be kept alive by an unrelated process that inherited the number. `.pty` added the
    per-session lease key but NOT start-time binding, so this limit stands unchanged."""
    if pid <= 0:
        return False
    if sys.platform == "win32":  # pragma: no cover - the rule itself is tested via win_pid_alive
        import ctypes

        kernel32 = ctypes.windll.kernel32
        return win_pid_alive(
            pid,
            open_process=lambda p: kernel32.OpenProcess(_SYNCHRONIZE, False, p),
            last_error=lambda: ctypes.get_last_error() or kernel32.GetLastError(),
            wait=lambda h: kernel32.WaitForSingleObject(h, 0),
            close=kernel32.CloseHandle)
    try:  # pragma: no cover - POSIX branch
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TerminalLeaseLedger:
    """Cross-process I-X3 lease ledger over one JSON file.

    `pid_alive` and `clock` are injectable so the contract is tested deterministically with no real
    processes and no wall-clock dependence."""

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        pid_alive: Callable[[int], bool] | None = None,
        clock: Callable[[], str] | None = None,
        lock_timeout_s: float = 5.0,
        stale_lock_s: float = 20.0,
        baseline_path: str | os.PathLike[str] | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else default_ledger_path()
        self._lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._pid_alive = pid_alive if pid_alive is not None else pid_is_alive
        self._clock = clock if clock is not None else _now_iso
        self._lock_timeout_s = float(lock_timeout_s)
        self._stale_lock_s = float(stale_lock_s)
        # DIAGNOSTIC SCOPE (U111). The env override exists so a check never adopts or releases a
        # terminal the operator's own shell holds — but a ledger that only counts its own scratch
        # records leaves the I-X3 cap unenforced for exactly that window (17E holds TWO live frontier
        # terminals there). So a redirected ledger keeps its own file for WRITES and counts the
        # durable ledger's live leases as a read-only BASELINE for every admission decision. The
        # override is the only thing that triggers it: an explicitly constructed ledger (a test, a
        # fixture, the baseline itself) is never silently overlaid on the operator's file.
        env_override = os.environ.get(LEDGER_PATH_ENV)
        if baseline_path is not None:
            self.baseline_path: Path | None = Path(baseline_path)
        elif path is None and env_override and Path(env_override) != DEFAULT_LEDGER_PATH:
            self.baseline_path = DEFAULT_LEDGER_PATH
        else:
            self.baseline_path = None

    # ---- file primitives ------------------------------------------------

    def _read(self) -> list[TerminalLease]:
        """Every lease on file (live or not). Absent ⇒ empty; unreadable ⇒ fail closed."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise LeaseLedgerCorrupt(f"lease ledger {self.path} unreadable: {exc}") from exc
        if not raw.strip():
            # W-14/A-4: an EMPTY ledger is not an ABSENT one, and the difference decides whether a
            # terminal is handed out. Absent (FileNotFoundError, above) means no terminal was ever
            # taken. Empty means a file exists and says nothing -- what a LOST WRITE leaves behind,
            # which `_write` made reachable by not fsyncing (R-26, repaired below). Reading it as
            # zero fabricated a count and granted an over-cap acquire, in a module whose stated
            # guarantee is that a corrupt ledger fails closed and is never silently reset. Same
            # branch shape, same exception, as the JSON error below.
            raise LeaseLedgerCorrupt(
                f"lease ledger {self.path} exists but holds nothing - fail closed, not reset: an "
                f"absent ledger means no terminal was ever taken, an empty one means a write was "
                f"lost, and reading it as zero would hand out a terminal already in use")
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LeaseLedgerCorrupt(f"lease ledger {self.path} is not valid JSON: {exc}") from exc
        if not isinstance(doc, dict) or doc.get("schema") not in READABLE_LEDGER_SCHEMAS:
            raise LeaseLedgerCorrupt(
                f"lease ledger {self.path} carries schema {doc.get('schema') if isinstance(doc, dict) else '?'!r}, "
                f"expected one of {READABLE_LEDGER_SCHEMAS} — fail closed, not reset")
        entries = doc.get("leases")
        if not isinstance(entries, list):
            raise LeaseLedgerCorrupt(f"lease ledger {self.path} has no `leases` list — fail closed")
        out: list[TerminalLease] = []
        for e in entries:
            try:
                out.append(TerminalLease.from_dict(e))
            except (KeyError, TypeError, ValueError) as exc:
                raise LeaseLedgerCorrupt(
                    f"lease ledger {self.path} holds a malformed lease record: {exc}") from exc
        return out

    def _write(self, leases: Iterable[TerminalLease]) -> None:
        """Atomic replace so no reader ever sees a half-written ledger."""
        doc = {"schema": LEDGER_SCHEMA, "updated": self._clock(),
               "leases": [ln.as_dict() for ln in leases]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + f".tmp-{os.getpid()}")
        # W-14/R-26: fsync the BYTES before the rename. `os.replace` is atomic for the NAME only;
        # without this the content can still be lost on a crash, which leaves exactly the
        # zero-length ledger `_read` now refuses. Donor: `control_plane/nodes/event_log.py:77-78`,
        # which fsyncs every append. `newline="\n"` per the environment rule on text writes (U274).
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(doc, indent=2) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)
        # ...and the DIRECTORY entry, so the rename itself survives a crash. POSIX only: Windows
        # cannot open a directory for fsync, and NTFS journals the rename, so on this build's target
        # host (SS3.1) the file half above is the one that carries the risk.
        if hasattr(os, "O_DIRECTORY"):
            dir_fd = os.open(self.path.parent, os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

    class _Lock:
        def __init__(self, ledger: "TerminalLeaseLedger") -> None:
            self._ledger = ledger
            self._fd: int | None = None

        def __enter__(self) -> "TerminalLeaseLedger._Lock":
            led = self._ledger
            led.path.parent.mkdir(parents=True, exist_ok=True)
            deadline = time.monotonic() + led._lock_timeout_s
            while True:
                try:
                    self._fd = os.open(str(led._lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                    os.write(self._fd, str(os.getpid()).encode("ascii"))
                    return self
                except FileExistsError:
                    # Break a lock left behind by a CRASHED writer — but never one a LIVE writer
                    # holds. Age alone is not enough: two processes can both see "old enough" and
                    # each unlink the other's fresh lock, and then both proceed into a
                    # read-modify-write (a silently lost acquire = an uncounted terminal). The lock
                    # file carries its owner's pid, so the primary rule is ownership: break it only
                    # if that process is GONE. Age is the fallback for a lock whose pid is
                    # unreadable (a writer killed between create and write).
                    owner = ""
                    try:
                        fd = os.open(str(led._lock_path), os.O_RDONLY)
                        try:
                            owner = os.read(fd, 32).decode("ascii", "ignore").strip()
                        finally:
                            os.close(fd)
                    except OSError:
                        owner = ""
                    try:
                        if owner.isdigit() and not led._pid_alive(int(owner)):
                            os.unlink(led._lock_path)
                            continue
                        if not owner.isdigit():
                            age = time.time() - os.path.getmtime(led._lock_path)
                            if age > led._stale_lock_s:
                                os.unlink(led._lock_path)
                                continue
                    except OSError:
                        pass  # it vanished under us — retry
                    if time.monotonic() >= deadline:
                        raise LeaseLedgerLocked(
                            f"lease ledger lock {led._lock_path} held > {led._lock_timeout_s}s — "
                            f"refuse to race the count (fail closed)")
                    time.sleep(0.02)

        def __exit__(self, *exc: Any) -> None:
            if self._fd is not None:
                try:
                    os.close(self._fd)
                finally:
                    # W-73: a waiter can hold a transient O_RDONLY handle on this very lock
                    # file (it reads the owner pid during its own retry, terminal_lease.py
                    # :329). On Windows that denies the unlink, and the swallowed error used
                    # to orphan the lock under a LIVE owner pid - which the break rules above
                    # deliberately never remove - wedging every later acquirer into
                    # LeaseLedgerLocked for the life of the ledger. The denying handles are
                    # milliseconds; retry rather than swallow.
                    deadline = time.monotonic() + 2.0
                    while True:
                        try:
                            os.unlink(self._ledger._lock_path)
                            break
                        except FileNotFoundError:
                            break
                        except OSError:
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(0.005)

    # ---- queries --------------------------------------------------------

    @property
    def scope(self) -> str:
        """`diagnostic` when this ledger writes to a redirected file and counts the durable one as a
        baseline; `durable` when it IS the file the count is kept in."""
        return "diagnostic" if self.baseline_path is not None else "durable"

    def _baseline(self) -> "TerminalLeaseLedger | None":
        """The read-only durable ledger a diagnostic scope counts. Constructed with an EXPLICIT path,
        so it is itself always `durable` — the overlay is exactly one level deep."""
        if self.baseline_path is None:
            return None
        return TerminalLeaseLedger(path=self.baseline_path, pid_alive=self._pid_alive,
                                   clock=self._clock)

    def live(self, subscription_ref: str | None = None) -> list[TerminalLease]:
        """Leases whose holder process is still alive (dead holders are simply not live here; call
        `reap()` to also drop them from the file).

        THIS LEDGER'S OWN records only — mutations are scoped to them, so a diagnostic check can
        never release a terminal the operator's shell holds. Use `in_use` for the governing count.

        W-73: the read takes the same filesystem mutex as the writers. Measured without it, a
        query's open handle blocked `os.replace` mid-acquire/release (WinError 5), and a
        transient denial inside that window surfaced as LeaseLedgerCorrupt("unreadable") -
        corruption that never happened. The mutators call `_read` directly INSIDE their own
        `_Lock`; this was the one unlocked direct reader of the file. Reads are milliseconds;
        `lock_timeout_s` is 5 s."""
        with self._Lock(self):
            return [ln for ln in self._read()
                    if self._pid_alive(ln.holder_pid)
                    and (subscription_ref is None or ln.subscription_ref == subscription_ref)]

    def baseline_live(self, subscription_ref: str | None = None) -> list[TerminalLease]:
        """Live leases held in the DURABLE ledger this diagnostic scope overlays (empty when durable).

        Raises `LeaseLedgerCorrupt` if the baseline exists but cannot be read: an uncountable
        baseline is ambiguity, and ambiguity fails closed rather than counting a reassuring zero."""
        base = self._baseline()
        return base.live(subscription_ref) if base is not None else []

    def own_in_use(self, subscription_ref: str) -> int:
        """How many terminals THIS ledger's own records hold."""
        return len(self.live(subscription_ref))

    def baseline_in_use(self, subscription_ref: str) -> int:
        """How many terminals the durable ledger holds that this scope can see but never touch."""
        return len(self.baseline_live(subscription_ref))

    def in_use(self, subscription_ref: str) -> int:
        """The GOVERNING count: both holder classes. Identical to `own_in_use` in durable scope."""
        return self.own_in_use(subscription_ref) + self.baseline_in_use(subscription_ref)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Per-subscription observable count (invariant 27) — identity + counting only.

        In diagnostic scope a reader must be able to tell WHOSE terminals it is looking at, so each
        entry carries `own_in_use`/`baseline_in_use` and every holder names its scope. An honest
        total that cannot be attributed is no more readable than the dishonest zero it replaces."""
        out: dict[str, dict[str, Any]] = {}

        def _fold(lease: TerminalLease, holder_scope: str) -> None:
            entry = out.setdefault(lease.subscription_ref, {
                "provider": lease.provider, "in_use": 0, "own_in_use": 0, "baseline_in_use": 0,
                "scope": self.scope, "holders": []})
            entry["in_use"] += 1
            entry["own_in_use" if holder_scope == self.scope else "baseline_in_use"] += 1
            entry["holders"].append({
                "lease_id": lease.lease_id, "node_id": lease.node_id, "session_id": lease.session_id,
                "holder_pid": lease.holder_pid, "acquired_at": lease.acquired_at,
                "purpose": lease.purpose, "scope": holder_scope})

        for ln in self.live():
            _fold(ln, self.scope)
        for ln in self.baseline_live():
            _fold(ln, "durable")
        return out

    # ---- mutations ------------------------------------------------------

    def acquire(
        self,
        *,
        subscription_ref: str,
        provider: str,
        node_id: str,
        allowance: int,
        holder_pid: int,
        purpose: str = "",
        session_id: str = "",
    ) -> TerminalLease:
        """Take one durable terminal for `node_id` (optionally for one `session_id`), or refuse.

        Idempotent per (subscription_ref, node_id, session_id): an existing LIVE lease for the same
        node AND session is returned unchanged, so a re-run of one governed spawn never
        double-counts. Two DIFFERENT sessions of the same node are two terminals (U75) — the
        conductor node id never changes, so node-only idempotence would hide a real second session."""
        if not subscription_ref:
            raise ValueError("subscription_ref is required — refuse to count an anonymous terminal")
        if not node_id:
            raise ValueError("node_id is required — refuse an uncounted/naked terminal (inv 2)")
        if allowance < 1:
            raise ValueError("allowance must be >= 1")
        if allowance > MAX_ALLOWANCE:
            raise ValueError(
                f"allowance {allowance} exceeds the governor cap of {MAX_ALLOWANCE} (OP-6) — refuse "
                f"to widen concurrency past the operator ruling (I-X3)")
        provider_cap = provider_allowance_cap(provider)
        if allowance > provider_cap:
            # OP-12 §12, at the DURABLE layer: the cap has to bind here too, or a caller that
            # bypassed the in-process governor could still write a second Grok/Antigravity lease.
            raise ValueError(
                f"allowance {allowance} exceeds the per-provider cap of {provider_cap} for "
                f"{provider!r} (OP-12 §12) — refuse to widen concurrency past the operator "
                f"ruling (I-X3, durable count)")
        # …and the same ref↔provider binding, for the same reason: the durable count is keyed on
        # the ref, so a second spelling would be a second durable bucket holding a second terminal.
        assert_resource_binding(subscription_ref, provider)
        if holder_pid <= 0:
            raise ValueError("holder_pid must be a real process — a lease has an owner or it is not one")

        # U111: read the durable baseline BEFORE taking our own lock — a corrupt/unreadable baseline
        # raises here and refuses the acquire, and a diagnostic scope never holds two locks at once.
        # The window between this read and the write below is a narrowing, not a guarantee: the
        # operator's shell could acquire concurrently. Counting a stale baseline is strictly closer
        # to the cap than counting zero, which is what this scope did before.
        baseline = self.baseline_live(subscription_ref)
        with self._Lock(self):
            leases = self._read()
            kept = [ln for ln in leases if self._pid_alive(ln.holder_pid)]
            same_sub = [ln for ln in kept if ln.subscription_ref == subscription_ref]
            sid = str(session_id or "")
            for ln in same_sub:
                if ln.node_id == node_id and ln.session_id == sid:
                    if len(kept) != len(leases):
                        self._write(kept)   # persist the reap we just did
                    return ln
            # SCHEMA TRANSITION (@1.0 → @1.1): a sessionless lease held by the SAME process for the
            # SAME node is the same terminal, written before per-session keys existed. Upgrade it in
            # place rather than adding a second record — otherwise one real session, mid-upgrade,
            # would consume 2 of 2 and lock the operator out of their own subscription.
            if sid:
                for ln in same_sub:
                    if ln.node_id == node_id and not ln.session_id and ln.holder_pid == int(holder_pid):
                        upgraded = TerminalLease(
                            lease_id=ln.lease_id, subscription_ref=ln.subscription_ref,
                            provider=ln.provider, node_id=ln.node_id, holder_pid=ln.holder_pid,
                            acquired_at=ln.acquired_at, purpose=ln.purpose, session_id=sid)
                        self._write([x for x in kept if x.lease_id != ln.lease_id] + [upgraded])
                        return upgraded
            if len(same_sub) + len(baseline) >= allowance:
                raise SubscriptionLimitExceeded(
                    f"subscription {subscription_ref!r} at allowance {allowance} "
                    f"(held by: {sorted(ln.node_id for ln in same_sub)}"
                    + (f", durable baseline: {sorted(ln.node_id for ln in baseline)}" if baseline else "")
                    + ") — refuse a further live terminal (I-X3, durable count)")
            lease = TerminalLease(
                lease_id=f"lease-{uuid.uuid4().hex[:12]}", subscription_ref=subscription_ref,
                provider=provider, node_id=node_id, holder_pid=int(holder_pid),
                acquired_at=self._clock(), purpose=purpose, session_id=str(session_id or ""))
            self._write([*kept, lease])
            return lease

    def release(self, lease_id: str) -> bool:
        """Release one lease by id. Returns True if it was present. Idempotent."""
        with self._Lock(self):
            leases = self._read()
            kept = [ln for ln in leases if ln.lease_id != lease_id]
            found = len(kept) != len(leases)
            live_kept = [ln for ln in kept if self._pid_alive(ln.holder_pid)]
            if found or len(live_kept) != len(kept):
                self._write(live_kept)
            return found

    def release_node(self, subscription_ref: str, node_id: str) -> int:
        """Release every lease held by one node on one subscription. Returns how many."""
        with self._Lock(self):
            leases = self._read()
            kept = [ln for ln in leases
                    if not (ln.subscription_ref == subscription_ref and ln.node_id == node_id)]
            n = len(leases) - len(kept)
            live_kept = [ln for ln in kept if self._pid_alive(ln.holder_pid)]
            if n or len(live_kept) != len(kept):
                self._write(live_kept)
            return n

    def release_session(self, subscription_ref: str, session_id: str) -> int:
        """Release the lease(s) held by one SESSION on one subscription. Returns how many.

        This is the reclaim path for U77: the shell chooses the session key BEFORE it asks for a
        ticket, so a ticket whose delivery then fails (shape refusal, emitter timeout) can be handed
        back by key even though the shell never learned the lease id. An empty `session_id` matches
        nothing — it must never become a wildcard that reclaims every sessionless lease."""
        if not session_id:
            return 0
        with self._Lock(self):
            leases = self._read()
            kept = [ln for ln in leases
                    if not (ln.subscription_ref == subscription_ref and ln.session_id == session_id)]
            n = len(leases) - len(kept)
            live_kept = [ln for ln in kept if self._pid_alive(ln.holder_pid)]
            if n or len(live_kept) != len(kept):
                self._write(live_kept)
            return n

    def reap(self) -> list[TerminalLease]:
        """Drop every lease whose holder process is gone; returns the reaped leases."""
        with self._Lock(self):
            leases = self._read()
            live = [ln for ln in leases if self._pid_alive(ln.holder_pid)]
            dead = [ln for ln in leases if not self._pid_alive(ln.holder_pid)]
            if dead:
                self._write(live)
            return dead

    # ---- projection into the in-process governor ------------------------

    def seed_governor(
        self,
        governor: SubscriptionGovernor,
        *,
        subscription_ref: str,
        provider: str,
        allowance: int,
    ) -> list[TerminalLease]:
        """Project the DURABLE live leases into an in-process governor.

        This is how a short-lived emitter's gate chain sees terminals held by the long-lived shell:
        after seeding, `governor.acquire` refuses exactly when the durable count is already at the
        allowance. Returns the seeded leases (observability — invariant 27)."""
        governor.register_subscription(subscription_ref, provider, allowance=allowance)
        # U111: in diagnostic scope the durable holders are seeded too — a bounded emitter's gate
        # chain must refuse for the operator's terminals exactly as it does for the check's own.
        seeded = [*self.live(subscription_ref), *self.baseline_live(subscription_ref)]
        for ln in seeded:
            try:
                # by LEASE KEY, not node id: the governor's `active` is a SET of node ids, so two
                # sessions of one node would seed as a single holder and leave the gate chain a free
                # slot that does not exist (U75).
                governor.acquire(subscription_ref, ln.lease_key)
            except SubscriptionLimitExceeded:
                # The durable count already exceeds the (possibly narrowed) allowance. Held terminals
                # are never evicted mid-generation (invariant 22 / governor policy); the governor is
                # already at its cap, so every FUTURE acquire is refused — which is the correct
                # fail-closed outcome. Stop seeding.
                break
        return seeded
