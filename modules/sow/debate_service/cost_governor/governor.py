"""Debate cost governor (Plan §19.2; invariant 17).

Three limits, all fail-closed and deterministic (never model output):
  - per-debate hard budget (from the request);
  - per-caller period quota (a caller cannot exceed its allotment ACROSS debates, including
    concurrent ones — enforced by RESERVING each open debate's full budget against the quota,
    then reconciling to actual spend at close);
  - global concurrent-debate cap (a shared service cannot become an unbounded token sink).
Budget exhaustion yields a CLEAN cutoff with a partial record — never silent truncation.
Accounting uses Decimal (CLAUDE.md: money/units are never float).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from decimal import Decimal


class DebateRefused(Exception):
    """The governor refused to open/continue a debate (quota/cap/budget). Fail closed."""


@dataclass
class _DebateBudget:
    debate_id: str
    caller: str
    limit: Decimal            # reserved against the caller's quota while open
    spent: Decimal = Decimal(0)

    def remaining(self) -> Decimal:
        return self.limit - self.spent


class CostGovernor:
    def __init__(self, *, per_caller_quota: Decimal | int = 100_000, global_concurrent_cap: int = 4) -> None:
        self._lock = threading.Lock()
        self._quota = Decimal(per_caller_quota)
        self._cap = global_concurrent_cap
        self._caller_committed: dict[str, Decimal] = {}   # finalized spend (closed debates)
        self._active: dict[str, _DebateBudget] = {}

    def _reserved(self, caller: str) -> Decimal:
        return sum((b.limit for b in self._active.values() if b.caller == caller), Decimal(0))

    def open_debate(self, debate_id: str, caller: str, budget_units: int) -> None:
        with self._lock:
            if len(self._active) >= self._cap:
                raise DebateRefused(f"global concurrent-debate cap {self._cap} reached")
            # available = quota - already-committed - already-reserved by in-flight debates.
            # Reserving the full budget at open time closes the concurrent-open bypass.
            available = self._quota - self._caller_committed.get(caller, Decimal(0)) - self._reserved(caller)
            if available <= 0:
                raise DebateRefused(f"caller {caller!r} has exhausted its period quota ({self._quota})")
            limit = min(Decimal(budget_units), available)
            self._active[debate_id] = _DebateBudget(debate_id, caller, limit)

    def charge(self, debate_id: str, amount: int) -> bool:
        """Charge a round's cost against the per-debate budget. Returns False (without
        charging) if it would exceed that budget — the caller must then cut off cleanly."""
        with self._lock:
            b = self._active.get(debate_id)
            if b is None:
                raise DebateRefused(f"no open debate {debate_id}")
            amt = Decimal(amount)
            if b.spent + amt > b.limit:
                return False
            b.spent += amt
            return True

    def close_debate(self, debate_id: str) -> Decimal:
        """Reconcile the reservation to actual spend (commit spent, release the rest) and free
        the global-cap slot. Returns the actual spend."""
        with self._lock:
            b = self._active.pop(debate_id, None)
            if b is None:
                return Decimal(0)
            self._caller_committed[b.caller] = self._caller_committed.get(b.caller, Decimal(0)) + b.spent
            return b.spent

    def reset_period(self, caller: str | None = None) -> None:
        """Operator-invoked period rollover: clear committed spend (all callers or one). The
        'period' quota is otherwise a monotonic lifetime cap until reset."""
        with self._lock:
            if caller is None:
                self._caller_committed.clear()
            else:
                self._caller_committed.pop(caller, None)

    def spent(self, debate_id: str) -> Decimal:
        with self._lock:
            b = self._active.get(debate_id)
            return b.spent if b else Decimal(0)

    def committed(self, caller: str) -> Decimal:
        with self._lock:
            return self._caller_committed.get(caller, Decimal(0))

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)
