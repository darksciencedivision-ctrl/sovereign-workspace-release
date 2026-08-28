"""VRAM residency planner (invariant 22; Plan §18.2, OP-7 §12.2 — Phase 15E `.picker`).

Invariant 22 in full: *local concurrency is hardware-bounded (8–14B tier); VRAM residency is
**scheduled, visible, never mid-generation eviction**.* OP-7 §12.2 makes the same rule a UI
requirement: the per-pane model picker enumerates the operator's local models and shows each
one's residency state — resident / loading / awaiting-eviction — so swaps are visible and a
model that is mid-generation is never yanked out of VRAM to make room for another.

This module is that scheduler, as a **pure, deterministic, fail-closed** state machine. It
holds NO GPU handle and makes NO real VRAM measurement: the total budget and each model's
footprint are injected inputs (the host reads them from `ollama ps` / `ollama list` in an
operator-run driver — the Phase-1 spike substitution pattern). Everything here is testable
without a GPU, and the picker renders exactly the `snapshot()` this produces — no fabricated
residency state ever reaches the UI.

Determinism: eviction order is least-recently-touched first, where "recency" is an internal
monotonic counter bumped on every load/touch — never a wall clock (`Date.now()`-class calls
are banned in this build and would defeat replay anyway).

Fail-closed choices (Buildout Directive §4 — deterministic lifecycle logic, never inference):
  * an unsized model is NEVER scheduled (we cannot prove it fits) — refused, not guessed;
  * a model larger than the whole budget is refused (can never be resident);
  * when room can only be made by evicting a **generating** model, the load is NOT forced:
    the blocking generators are flagged AWAITING_EVICTION (visible) and the new model is
    QUEUED until they finish — invariant 22's "never mid-generation eviction", enforced in
    code, not by convention.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Residency states the picker renders (OP-7 §12.2 names the middle three explicitly).
NOT_LOADED = "not_loaded"              # known model, not in VRAM
LOADING = "loading"                   # scheduled to load; VRAM reserved, transition visible
RESIDENT = "resident"                 # in VRAM, ready to serve
AWAITING_EVICTION = "awaiting_eviction"  # resident+generating, marked to leave once idle
QUEUED = "queued"                     # wants VRAM but blocked behind a generating model
EVICTED = "evicted"                   # was resident, reclaimed; footprint still known
#: NOT a planner state — the DISPLAY state for "there is no residency view at all" (the daemon is
#: unreachable, or the VRAM budget could not be established so no planner was built). It exists
#: because the alternative is worse: defaulting an unknown model to NOT_LOADED tells the operator a
#: model the daemon is actively serving is not in VRAM, which is a fabricated fact, not a missing
#: one (gate-validator FAIL-1 / spec-audit MAJOR-2, 2026-07-26). The planner never produces it.
UNKNOWN = "unknown"

# States that currently occupy VRAM (count against the budget).
_OCCUPYING = frozenset({LOADING, RESIDENT, AWAITING_EVICTION})


class ResidencyError(Exception):
    """A residency operation was refused fail-closed (unsized model, over-budget, bad state)."""


@dataclass
class _Model:
    name: str
    footprint_mb: int
    status: str = NOT_LOADED
    generating: bool = False
    touched: int = 0                  # monotonic recency stamp (LRU key), 0 = never touched


@dataclass
class ResidencyDecision:
    """The outcome of `request_load`, fully explaining what the planner did (auditability)."""

    model: str
    scheduled: bool                   # True ⇒ now LOADING (room found), False ⇒ QUEUED/refused
    status: str                       # the model's status AFTER the decision
    evicted: list[str] = field(default_factory=list)      # models reclaimed to make room
    awaiting_eviction: list[str] = field(default_factory=list)  # generators flagged to leave
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "model": self.model, "scheduled": self.scheduled, "status": self.status,
            "evicted": list(self.evicted), "awaiting_eviction": list(self.awaiting_eviction),
            "reason": self.reason,
        }


class ResidencyPlanner:
    """Schedules which local models are VRAM-resident under a fixed budget, honouring invariant
    22. All footprints/budget are caller-injected megabytes; nothing here touches a GPU."""

    def __init__(self, total_vram_mb: int) -> None:
        if not isinstance(total_vram_mb, int) or isinstance(total_vram_mb, bool) or total_vram_mb <= 0:
            raise ResidencyError("total_vram_mb must be a positive int — fail closed")
        self._total = total_vram_mb
        self._models: dict[str, _Model] = {}
        self._clock = 0                # monotonic recency source (deterministic, no wall clock)

    # -- registration -----------------------------------------------------------------
    def register_model(self, name: str, footprint_mb: int) -> None:
        """Declare (or update) a local model's VRAM footprint. Required before it can load —
        an unsized model is refused, never scheduled on a guess."""
        if not isinstance(name, str) or not name.strip():
            raise ResidencyError("model name must be a non-empty string — fail closed")
        if not isinstance(footprint_mb, int) or isinstance(footprint_mb, bool) or footprint_mb <= 0:
            raise ResidencyError(f"footprint for {name!r} must be a positive int MB — fail closed")
        existing = self._models.get(name)
        if existing is None:
            self._models[name] = _Model(name=name, footprint_mb=footprint_mb)
        else:
            existing.footprint_mb = footprint_mb

    # -- accounting -------------------------------------------------------------------
    def used_vram_mb(self) -> int:
        return sum(m.footprint_mb for m in self._models.values() if m.status in _OCCUPYING)

    def free_vram_mb(self) -> int:
        return self._total - self.used_vram_mb()

    def total_vram_mb(self) -> int:
        return self._total

    def residency_of(self, name: str) -> str:
        m = self._models.get(name)
        return m.status if m is not None else NOT_LOADED

    def _touch(self, m: _Model) -> None:
        self._clock += 1
        m.touched = self._clock

    # -- scheduling -------------------------------------------------------------------
    def request_load(self, name: str) -> ResidencyDecision:
        """Schedule `name` into VRAM (state → LOADING), evicting only idle models to fit.

        Never evicts a generating model: if the only way to fit is to reclaim VRAM held by a
        model that is mid-generation, that generator is flagged AWAITING_EVICTION and `name`
        is QUEUED (scheduled=False) until the generator goes idle. Fail-closed for unsized /
        over-budget models."""
        m = self._models.get(name)
        if m is None:
            raise ResidencyError(f"model {name!r} not registered (unknown footprint) — fail closed")
        if m.footprint_mb > self._total:
            raise ResidencyError(
                f"model {name!r} footprint {m.footprint_mb}MB exceeds total VRAM {self._total}MB — "
                f"can never be resident, fail closed")

        if m.status in (RESIDENT, LOADING):
            self._touch(m)
            return ResidencyDecision(model=name, scheduled=True, status=m.status,
                                     reason=f"already {m.status}")

        # A model that was AWAITING_EVICTION being requested again cancels its pending eviction.
        if m.status == AWAITING_EVICTION:
            m.status = RESIDENT
            self._touch(m)
            return ResidencyDecision(model=name, scheduled=True, status=RESIDENT,
                                     reason="re-requested while awaiting eviction — kept resident")

        deficit = m.footprint_mb - self.free_vram_mb()
        if deficit <= 0:
            m.status = LOADING
            self._touch(m)
            return ResidencyDecision(model=name, scheduled=True, status=LOADING,
                                     reason="fits in free VRAM")

        # Need to reclaim `deficit` MB. Evict IDLE resident models, least-recently-touched first.
        # A model that is mid-generation is NEVER in this set (invariant 22 — never
        # mid-generation eviction); it is handled below as an AWAITING_EVICTION blocker instead.
        evictable = sorted(
            (x for x in self._models.values()
             if x.status == RESIDENT and not x.generating and x.name != name),
            key=lambda x: x.touched)
        evicted: list[str] = []
        for victim in evictable:
            if deficit <= 0:
                break
            victim.status = EVICTED
            evicted.append(victim.name)
            deficit -= victim.footprint_mb

        if deficit <= 0:
            m.status = LOADING
            self._touch(m)
            return ResidencyDecision(
                model=name, scheduled=True, status=LOADING, evicted=evicted,
                reason=f"evicted idle model(s) {evicted} to fit" if evicted else "fits in free VRAM")

        # Still short. The remaining VRAM is held by models we cannot reclaim right now:
        # generating models (NEVER evict mid-generation — invariant 22) and/or models still
        # LOADING (not yet resident, so not evictable this pass). Flag the generators
        # AWAITING_EVICTION (they leave once idle); the load is QUEUED either way. The reason
        # names the ACTUAL blockers so the picker never mis-attributes a loading occupier to
        # "generating" (spec-audit NIT-1).
        gen_blockers = sorted(
            (x for x in self._models.values()
             if x.status in (RESIDENT, AWAITING_EVICTION) and x.generating and x.name != name),
            key=lambda x: x.touched)
        loading_blockers = sorted(
            (x for x in self._models.values() if x.status == LOADING and x.name != name),
            key=lambda x: x.touched)
        # Flag only the least-recently-touched PREFIX of generators whose cumulative footprint
        # covers the remaining deficit — never more (spec-audit MINOR-1). Flagging every
        # generator would needlessly evict a mid-generation model the operator may still want
        # resident once it goes idle; the minimal prefix is enough to fit `name` and no generator
        # is ever force-evicted (invariant 22 — they leave only after finishing).
        awaiting: list[str] = []
        reclaim = deficit
        for b in gen_blockers:
            if reclaim <= 0:
                break
            if b.status != AWAITING_EVICTION:
                b.status = AWAITING_EVICTION
            awaiting.append(b.name)
            reclaim -= b.footprint_mb
        m.status = QUEUED
        parts: list[str] = []
        if awaiting:
            parts.append(f"generating model(s) {awaiting}")
        if loading_blockers:
            parts.append(f"loading model(s) {[b.name for b in loading_blockers]}")
        held = " and ".join(parts) if parts else "concurrent occupiers"
        return ResidencyDecision(
            model=name, scheduled=False, status=QUEUED, evicted=evicted, awaiting_eviction=awaiting,
            reason=(f"blocked: remaining VRAM held by {held} — queued, never mid-generation "
                    "eviction (invariant 22)"))

    def complete_load(self, name: str) -> None:
        """The host reports the (async) load finished: LOADING → RESIDENT."""
        m = self._models.get(name)
        if m is None or m.status != LOADING:
            raise ResidencyError(f"complete_load({name!r}): not in LOADING state — fail closed")
        m.status = RESIDENT
        self._touch(m)

    # -- generation lifecycle ---------------------------------------------------------
    def mark_generating(self, name: str) -> None:
        """Pin a resident model as mid-generation (never evictable until idle)."""
        m = self._models.get(name)
        if m is None or m.status not in (RESIDENT, AWAITING_EVICTION):
            raise ResidencyError(
                f"mark_generating({name!r}): only a resident model can generate — fail closed")
        m.generating = True
        self._touch(m)

    def mark_idle(self, name: str) -> list[str]:
        """Generation finished. If the model was flagged AWAITING_EVICTION it is now reclaimed
        (the visible swap), and any QUEUED model that now fits is promoted to LOADING. Returns
        the list of models promoted to LOADING by the freed VRAM (may be empty)."""
        m = self._models.get(name)
        if m is None:
            raise ResidencyError(f"mark_idle({name!r}): unknown model — fail closed")
        m.generating = False
        if m.status == AWAITING_EVICTION:
            m.status = EVICTED
        return self._promote_queued()

    def _promote_queued(self) -> list[str]:
        """After VRAM frees up, promote QUEUED models that now fit — least-recently-touched
        first, deterministic. A promoted model goes to LOADING."""
        promoted: list[str] = []
        # QUEUED models never got a touch stamp for this wait; order by name for determinism.
        for m in sorted((x for x in self._models.values() if x.status == QUEUED),
                        key=lambda x: x.name):
            if m.footprint_mb <= self.free_vram_mb():
                m.status = LOADING
                self._touch(m)
                promoted.append(m.name)
        return promoted

    # -- picker surface ---------------------------------------------------------------
    def snapshot(self) -> dict[str, object]:
        """The residency view the per-pane picker renders (OP-7 §12.2). Deterministic order
        (by model name). Nothing here is fabricated — a model absent from VRAM reads
        NOT_LOADED, exactly as tracked."""
        models = [
            {"model": m.name, "footprint_mb": m.footprint_mb, "status": m.status,
             "generating": m.generating}
            for m in sorted(self._models.values(), key=lambda x: x.name)
        ]
        return {
            "total_vram_mb": self._total,
            "used_vram_mb": self.used_vram_mb(),
            "free_vram_mb": self.free_vram_mb(),
            "models": models,
        }

    def residency_map(self) -> dict[str, str]:
        """model → residency status, for the picker to annotate its local-model options."""
        return {m.name: m.status for m in self._models.values()}
