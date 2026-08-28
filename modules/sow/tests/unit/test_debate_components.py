"""Phase 7: cost governor, evidence manager, round manager (pure/unit)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from debate_service.cost_governor.governor import CostGovernor, DebateRefused
from debate_service.evidence_manager.manager import EvidenceManager
from debate_service.round_manager.manager import HARD_ROUND_CAP, RoundManager
from tests.fixtures.mock_debater import MockDebater


# ---------- cost governor ----------

def test_per_debate_budget_charged_and_cut_off() -> None:
    g = CostGovernor(per_caller_quota=10_000, global_concurrent_cap=4)
    g.open_debate("d-1", "caller", budget_units=250)
    assert g.charge("d-1", 100) and g.charge("d-1", 100)
    assert not g.charge("d-1", 100)  # 300 > 250 budget -> refused, clean cutoff
    assert g.spent("d-1") == Decimal(200)


def test_global_concurrent_cap() -> None:
    g = CostGovernor(global_concurrent_cap=2)
    g.open_debate("d-1", "a", 100); g.open_debate("d-2", "b", 100)
    with pytest.raises(DebateRefused, match="global concurrent"):
        g.open_debate("d-3", "c", 100)


def test_per_caller_quota_exhausts_across_debates() -> None:
    g = CostGovernor(per_caller_quota=150, global_concurrent_cap=4)
    g.open_debate("d-1", "caller", 100); g.charge("d-1", 100); g.close_debate("d-1")
    g.open_debate("d-2", "caller", 100)  # only 50 headroom left
    assert g.charge("d-2", 50) and not g.charge("d-2", 50)
    g.close_debate("d-2")
    with pytest.raises(DebateRefused, match="quota"):
        g.open_debate("d-3", "caller", 100)


def test_concurrent_debates_cannot_bypass_caller_quota() -> None:
    """MAJOR regression: opening a 2nd debate before charging the 1st must not both get the
    full quota — the quota is RESERVED at open time."""
    g = CostGovernor(per_caller_quota=100, global_concurrent_cap=4)
    g.open_debate("d-1", "w", 100)          # reserves the whole quota
    with pytest.raises(DebateRefused, match="quota"):
        g.open_debate("d-2", "w", 100)      # no headroom left while d-1 is open
    # after d-1 closes having spent only 30, the released reservation is available again
    g.charge("d-1", 30); g.close_debate("d-1")
    g.open_debate("d-2", "w", 100)          # 70 headroom now
    assert g.charge("d-2", 70) and not g.charge("d-2", 1)


def test_close_frees_global_slot() -> None:
    g = CostGovernor(global_concurrent_cap=1)
    g.open_debate("d-1", "a", 100)
    with pytest.raises(DebateRefused, match="global concurrent"):
        g.open_debate("d-2", "b", 100)
    g.close_debate("d-1")                    # frees the slot
    g.open_debate("d-2", "b", 100)
    assert g.active_count() == 1


def test_period_reset_restores_quota() -> None:
    g = CostGovernor(per_caller_quota=100)
    g.open_debate("d-1", "w", 100); g.charge("d-1", 100); g.close_debate("d-1")
    with pytest.raises(DebateRefused, match="quota"):
        g.open_debate("d-2", "w", 100)
    g.reset_period("w")                      # operator period rollover
    g.open_debate("d-2", "w", 100)           # quota restored
    assert g.charge("d-2", 100)


# ---------- evidence manager ----------

def test_unsupported_assertion_marked() -> None:
    em = EvidenceManager(resolver=lambda ref: ref == "m-real@1")
    supported = em.classify_assertion("claim A", ["m-real@1"])
    unsupported = em.classify_assertion("claim B", ["m-missing@1"])
    novote = em.classify_assertion("just an opinion", [])  # a model vote is not evidence
    assert supported["status"] == "SUPPORTED" and supported["resolving_refs"] == ["m-real@1"]
    assert unsupported["status"] == "UNSUPPORTED" and unsupported["unresolved_refs"] == ["m-missing@1"]
    assert novote["status"] == "UNSUPPORTED"


# ---------- round manager ----------

def _rm(quota=100_000, cap=4, round_cost=100):
    g = CostGovernor(per_caller_quota=quota, global_concurrent_cap=cap)
    em = EvidenceManager(resolver=lambda ref: ref.startswith("m-good"))
    return g, RoundManager(g, em, round_cost=round_cost)


def test_converges_early_and_stops() -> None:
    g, rm = _rm()
    g.open_debate("d-1", "c", 10_000)
    debaters = [MockDebater("n1", "X", converge_to="AGREED", converge_after=2, evidence_refs=["m-good1"]),
                MockDebater("n2", "Y", converge_to="AGREED", converge_after=2, evidence_refs=["m-good2"])]
    out = rm.run("d-1", "topic", debaters, max_rounds=5)
    assert out.outcome == "CONVERGED" and out.rounds_used == 2


def test_dissent_preserved_when_no_convergence() -> None:
    g, rm = _rm()
    g.open_debate("d-1", "c", 10_000)
    debaters = [MockDebater("n1", "left", evidence_refs=["m-good1"]),
                MockDebater("n2", "right", evidence_refs=["m-good2"])]
    out = rm.run("d-1", "topic", debaters, max_rounds=3)
    assert out.outcome == "DISSENT_PRESERVED" and out.rounds_used == 3
    assert out.dissent is not None and "left" in out.dissent and "right" in out.dissent


def test_hard_round_cap_enforced() -> None:
    g, rm = _rm(quota=10_000)
    g.open_debate("d-1", "c", 10_000)
    debaters = [MockDebater("n1", "a", evidence_refs=["m-good1"]), MockDebater("n2", "b", evidence_refs=["m-good2"])]
    out = rm.run("d-1", "topic", debaters, max_rounds=99)  # request > cap
    assert out.rounds_used <= HARD_ROUND_CAP


def test_budget_exhaustion_cuts_off_cleanly() -> None:
    g, rm = _rm(round_cost=100)
    g.open_debate("d-1", "c", 250)  # only 2 rounds affordable
    debaters = [MockDebater("n1", "a", evidence_refs=["m-good1"]), MockDebater("n2", "b", evidence_refs=["m-good2"])]
    out = rm.run("d-1", "topic", debaters, max_rounds=5)
    assert out.outcome == "BUDGET_EXHAUSTED" and out.rounds_used == 2  # partial record kept
    assert out.positions  # partial positions preserved, not silently truncated


def test_convergence_requires_a_supported_position() -> None:
    # both agree but neither cites resolving evidence -> not real convergence (votes != evidence)
    g, rm = _rm()
    g.open_debate("d-1", "c", 10_000)
    debaters = [MockDebater("n1", "AGREED", evidence_refs=["m-bad"]),
                MockDebater("n2", "AGREED", evidence_refs=["m-bad"])]
    out = rm.run("d-1", "topic", debaters, max_rounds=3)
    assert out.outcome != "CONVERGED"  # agreement without evidence is not concurrence
