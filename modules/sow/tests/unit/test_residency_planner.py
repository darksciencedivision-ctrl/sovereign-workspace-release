"""VRAM residency planner (invariant 22; OP-7 §12.2 — Phase 15E `.picker`).

Proves the three things invariant 22 demands: residency is SCHEDULED (fits within a budget,
evicts idle models LRU-first to make room), VISIBLE (snapshot() renders exact per-model state),
and NEVER mid-generation eviction (a generating model is queued-around, never yanked). Pure and
deterministic — no GPU, no wall clock."""
from __future__ import annotations

import pytest

from scheduler.residency_planner.residency_planner import (
    AWAITING_EVICTION,
    EVICTED,
    LOADING,
    NOT_LOADED,
    QUEUED,
    RESIDENT,
    ResidencyError,
    ResidencyPlanner,
)


def _planner(total: int = 10000) -> ResidencyPlanner:
    return ResidencyPlanner(total)


def test_construction_rejects_non_positive_budget() -> None:
    for bad in (0, -1, True, 1.5):
        with pytest.raises(ResidencyError):
            ResidencyPlanner(bad)  # type: ignore[arg-type]


def test_unregistered_model_is_never_scheduled() -> None:
    p = _planner()
    with pytest.raises(ResidencyError):
        p.request_load("ghost")           # unknown footprint ⇒ fail closed, never guessed


def test_register_rejects_bad_footprint() -> None:
    p = _planner()
    for bad in (0, -100, True, 3.2, "big"):
        with pytest.raises(ResidencyError):
            p.register_model("m", bad)     # type: ignore[arg-type]


def test_model_larger_than_budget_can_never_be_resident() -> None:
    p = _planner(total=4000)
    p.register_model("huge", 8000)
    with pytest.raises(ResidencyError):
        p.request_load("huge")


def test_load_fits_in_free_vram() -> None:
    p = _planner(total=10000)
    p.register_model("a", 6000)
    d = p.request_load("a")
    assert d.scheduled and d.status == LOADING and d.evicted == []
    assert p.residency_of("a") == LOADING
    assert p.used_vram_mb() == 6000 and p.free_vram_mb() == 4000
    p.complete_load("a")
    assert p.residency_of("a") == RESIDENT


def test_lru_eviction_of_idle_model_to_make_room() -> None:
    p = _planner(total=10000)
    p.register_model("a", 5000)
    p.register_model("b", 4000)
    p.register_model("c", 5000)
    for m in ("a", "b"):
        p.request_load(m)
        p.complete_load(m)                # a resident (touched first), then b (touched later)
    # c needs 5000 but only 1000 free ⇒ must evict; a is least-recently-touched ⇒ a goes.
    d = p.request_load("c")
    assert d.scheduled and d.status == LOADING
    assert d.evicted == ["a"]             # LRU victim, not b
    assert p.residency_of("a") == EVICTED
    assert p.residency_of("b") == RESIDENT
    assert p.residency_of("c") == LOADING


def test_generating_model_is_never_evicted_new_load_is_queued() -> None:
    p = _planner(total=10000)
    p.register_model("gen", 7000)
    p.register_model("new", 5000)
    p.request_load("gen")
    p.complete_load("gen")
    p.mark_generating("gen")              # gen is mid-generation, holds 7000MB
    d = p.request_load("new")             # needs 5000, only 3000 free, gen is the only holder
    assert not d.scheduled                # invariant 22: NOT forced
    assert d.status == QUEUED
    assert d.awaiting_eviction == ["gen"] # the generator is flagged to leave, not evicted now
    assert p.residency_of("gen") == AWAITING_EVICTION   # still resident-in-VRAM, still generating
    assert p.residency_of("new") == QUEUED
    # the generator STILL occupies VRAM (never mid-generation eviction)
    assert p.used_vram_mb() == 7000


def test_queued_model_is_promoted_when_generator_goes_idle() -> None:
    p = _planner(total=10000)
    p.register_model("gen", 7000)
    p.register_model("new", 5000)
    p.request_load("gen"); p.complete_load("gen"); p.mark_generating("gen")
    p.request_load("new")                 # QUEUED behind gen
    promoted = p.mark_idle("gen")         # generation finishes ⇒ the visible swap happens
    assert p.residency_of("gen") == EVICTED
    assert promoted == ["new"]
    assert p.residency_of("new") == LOADING


def test_only_minimal_lru_prefix_of_generators_is_flagged() -> None:
    # Two generators each large enough to cover the deficit on their own. A queued load must flag
    # ONLY the least-recently-touched one (enough to fit once it idles), never both — flagging the
    # second would needlessly evict a mid-generation model still wanted resident (spec-audit
    # MINOR-1). Invariant 22 holds either way (nothing is force-evicted).
    p = _planner(total=12000)
    p.register_model("gen_old", 5000)
    p.register_model("gen_new", 5000)
    p.register_model("want", 4000)
    p.request_load("gen_old"); p.complete_load("gen_old"); p.mark_generating("gen_old")
    p.request_load("gen_new"); p.complete_load("gen_new"); p.mark_generating("gen_new")
    # 10000 used, 2000 free; want needs 4000 ⇒ deficit 2000. gen_old (touched first) covers it.
    d = p.request_load("want")
    assert not d.scheduled and d.status == QUEUED
    assert d.awaiting_eviction == ["gen_old"]                 # ONLY the LRU generator, not both
    assert p.residency_of("gen_old") == AWAITING_EVICTION
    assert p.residency_of("gen_new") == RESIDENT              # untouched, still resident+generating
    assert "['gen_old']" in d.reason and "gen_new" not in d.reason


def test_prefix_extends_when_one_generator_cannot_cover_deficit() -> None:
    # When no single generator covers the deficit, the LRU prefix extends until it does.
    p = _planner(total=12000)
    p.register_model("g1", 3000)          # touched first ⇒ LRU-first
    p.register_model("g2", 3000)          # touched second
    p.register_model("g3", 3000)          # touched third
    p.register_model("big", 10000)
    for g in ("g1", "g2", "g3"):
        p.request_load(g); p.complete_load(g); p.mark_generating(g)
    # 9000 used, 3000 free; big needs 10000 ⇒ deficit 7000. g1(3000)+g2(3000)=6000 < 7000,
    # +g3(3000)=9000 ≥ 7000 ⇒ all three flagged (prefix extends to cover, never beyond need).
    d = p.request_load("big")
    assert not d.scheduled and d.status == QUEUED
    assert d.awaiting_eviction == ["g1", "g2", "g3"]


def test_blocked_reason_names_loading_not_generating() -> None:
    # A load blocked purely behind another model that is still LOADING (not generating) must
    # be QUEUED and its reason must name a LOADING blocker, never mis-attribute it to
    # "generating" (spec-audit NIT-1).
    p = _planner(total=10000)
    p.register_model("x", 7000)
    p.register_model("y", 5000)
    p.request_load("x")                   # x is LOADING (occupies 7000), not generating
    d = p.request_load("y")               # only 3000 free, x is the blocker
    assert not d.scheduled and d.status == QUEUED
    assert d.awaiting_eviction == []      # nothing is generating ⇒ nothing flagged to evict
    assert "loading model(s) ['x']" in d.reason
    assert "generating model(s)" not in d.reason


def test_mark_generating_requires_resident_model() -> None:
    p = _planner()
    p.register_model("a", 1000)
    with pytest.raises(ResidencyError):
        p.mark_generating("a")            # only LOADING, never resident yet ⇒ fail closed
    p.request_load("a")
    with pytest.raises(ResidencyError):
        p.mark_generating("a")            # LOADING is not yet RESIDENT ⇒ fail closed


def test_re_request_of_awaiting_eviction_keeps_it_resident() -> None:
    p = _planner(total=10000)
    p.register_model("gen", 7000)
    p.register_model("new", 5000)
    p.request_load("gen"); p.complete_load("gen"); p.mark_generating("gen")
    p.request_load("new")                 # flags gen AWAITING_EVICTION
    assert p.residency_of("gen") == AWAITING_EVICTION
    d = p.request_load("gen")             # operator picks gen's pane again ⇒ cancel the eviction
    assert d.scheduled and p.residency_of("gen") == RESIDENT


def test_complete_load_requires_loading_state() -> None:
    p = _planner()
    p.register_model("a", 1000)
    with pytest.raises(ResidencyError):
        p.complete_load("a")              # NOT_LOADED ⇒ fail closed


def test_snapshot_is_deterministic_and_reflects_state() -> None:
    p = _planner(total=8000)
    p.register_model("zeta", 3000)
    p.register_model("alpha", 4000)
    p.request_load("zeta"); p.complete_load("zeta")
    p.request_load("alpha")
    snap = p.snapshot()
    assert snap["total_vram_mb"] == 8000
    assert snap["used_vram_mb"] == 7000
    assert snap["free_vram_mb"] == 1000
    names = [m["model"] for m in snap["models"]]
    assert names == ["alpha", "zeta"]     # sorted by name ⇒ deterministic
    by = {m["model"]: m for m in snap["models"]}
    assert by["zeta"]["status"] == RESIDENT
    assert by["alpha"]["status"] == LOADING
    assert by["alpha"]["generating"] is False


def test_residency_map_annotates_absent_models_as_not_loaded() -> None:
    p = _planner()
    p.register_model("a", 1000)
    rm = p.residency_map()
    assert rm == {"a": NOT_LOADED}
    assert p.residency_of("never-registered") == NOT_LOADED
