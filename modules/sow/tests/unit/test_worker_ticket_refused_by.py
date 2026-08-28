"""The worker launch ticket reports WHICH gate refused (`refused_by`), machine-readably.

Why the field exists (gate-validator BLOCKING-1c, 2026-07-26): the in-Electron receipt proved its
fail-closed legs by regex-matching the refusal PROSE. An enumeration crash whose message contained
the word "VRAM" satisfied the leg that was supposed to prove the invariant-22 admission gate — the
leg was green and proved nothing. A gate id cannot be borrowed that way, so each leg now asserts one.

These tests pin the mapping the legs depend on. Every gate is driven through the real
`build_worker_launch_ticket` with injected dependencies — no live call, no host dependence.
"""
from __future__ import annotations

import pytest

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from adapters.local.ollama_session import OLLAMA_LOCAL_ADAPTER
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger
from scheduler.residency_planner.residency_planner import ResidencyPlanner
from tools.live.emit_worker_launch import build_worker_launch_ticket

PANE = "pane-7"
SESSION = "sess-7"


def _auth(authorized: bool = True) -> LiveAuthorization:
    return LiveAuthorization(
        authorized=authorized, providers=frozenset({CLAUDE_CODE_ADAPTER} if authorized else set()),
        terminals_per_subscription=2, register_row="OP-6", source="(test)", reason="test")


def _local_option(**over: object) -> dict:
    option = {"provider": OLLAMA_LOCAL_ADAPTER, "adapter": OLLAMA_LOCAL_ADAPTER, "locality": "local",
              "subscription_backed": False, "label": "qwen3:8b", "model_slug": "qwen3:8b",
              "verified": True, "is_fallback": False, "roles": ["reasoning", "coding"],
              "residency": "not_loaded", "available": True, "unavailable_reason": None}
    option.update(over)
    return option


def _frontier_option(**over: object) -> dict:
    option = {"provider": CLAUDE_CODE_ADAPTER, "adapter": CLAUDE_CODE_ADAPTER,
              "locality": "frontier", "subscription_backed": True, "label": "fable-5",
              "model_slug": "fable-5", "verified": False, "is_fallback": False,
              "roles": ["reasoning", "coding"], "residency": None, "available": True,
              "unavailable_reason": None}
    option.update(over)
    return option


def _ticket(option: dict, role: str = "reasoning", *, offered: list | None = None, **kw: object):
    return build_worker_launch_ticket(
        registrar=None,
        holder_pid=4242, session_id=SESSION, pane_id=str(kw.pop("pane_id", PANE)),
        selection={"option": option, "role": role, "mode": "autonomous"},
        live_auth=kw.pop("live_auth", _auth()),          # type: ignore[arg-type]
        profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=kw.pop("operator_terms_confirmed", True),  # type: ignore[arg-type]
        ledger=TerminalLeaseLedger(path=str(kw.pop("ledger_path"))) if "ledger_path" in kw else None,
        offered_options=[option] if offered is None else offered,
        **kw)  # type: ignore[arg-type]


def _planner(total: int = 20000, footprint: int = 5000) -> ResidencyPlanner:
    p = ResidencyPlanner(total)
    p.register_model("qwen3:8b", footprint)
    return p


def test_an_authorized_ticket_reports_no_refusing_gate(tmp_path) -> None:
    ticket = _ticket(_local_option(), residency_planner=_planner(), ollama_present=True,
                     residency_budget={"vram_budget_mb": 20000, "established": True,
                                       "estimate": True, "budget_source": "(test)"})
    assert ticket["authorized"] is True
    assert ticket["refused_by"] is None


def test_an_option_this_host_never_offered_is_refused_by_the_host_enumeration_gate() -> None:
    forged = _local_option(model_slug="not-offered-by-this-host")
    ticket = _ticket(forged, offered=[_local_option()])
    assert ticket["authorized"] is False
    assert ticket["refused_by"] == "host_enumeration"
    assert "is not one this host currently offers" in ticket["reason"]


def test_a_role_the_host_descriptor_does_not_offer_is_also_the_enumeration_gate() -> None:
    ticket = _ticket(_local_option(roles=["coding"]), role="reasoning")
    assert ticket["refused_by"] == "host_enumeration"


def test_the_conductor_role_is_refused_by_the_worker_role_gate() -> None:
    """The leg the receipt calls `conductor_role_refused`. It must be THIS gate: any other refusal
    (an absent CLI, a full I-X3 count) reaching that leg would have read as proof the worker path
    refuses the conductor role (validator MINOR-2)."""
    ticket = _ticket(_frontier_option(roles=["reasoning", "coding", "conductor"]), "conductor")
    assert ticket["authorized"] is False
    assert ticket["refused_by"] == "worker_role"
    assert "conductor" in ticket["reason"]


def test_a_greyed_option_is_refused_by_the_selection_guard() -> None:
    greyed = _local_option(available=False, unavailable_reason="daemon down")
    ticket = _ticket(greyed)
    assert ticket["refused_by"] == "selection_guard"


def test_an_unparseable_selection_is_refused_by_the_selection_guard() -> None:
    ticket = build_worker_launch_ticket(
        registrar=None,
        holder_pid=1, session_id=SESSION, pane_id=PANE, selection="not a dict",
        live_auth=_auth(), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, offered_options=[])
    assert ticket["refused_by"] == "selection_guard"


def test_a_local_pane_that_does_not_fit_is_refused_by_the_vram_admission_gate() -> None:
    """The leg the receipt calls `local_budget_refused`. `vram_admission` is reachable ONLY from the
    worker path's invariant-22 checks — an enumeration fault reports `host_enumeration` instead, and
    the leg that used to accept it now fails."""
    ticket = _ticket(_local_option(), residency_planner=_planner(total=1000, footprint=4983),
                     ollama_present=True,
                     residency_budget={"vram_budget_mb": 1000, "established": True,
                                       "estimate": True, "budget_source": "(test) established"})
    assert ticket["authorized"] is False
    assert ticket["refused_by"] == "vram_admission"


def test_a_budget_that_could_not_be_established_is_a_DIFFERENT_gate_from_a_bad_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two invariant-22 branches are two different facts and now report two different gates.

    They used to share `vram_admission`, and the receipt leg named "a local pane that does not fit
    VRAM was refused" went green on THIS branch — where nothing was measured at all, so nothing
    about fit was proven. The gate ids stopped one refusal FAMILY borrowing another's evidence;
    this was the same borrowing inside a family (spec-audit MAJOR-1, 2026-07-26).

    The host enumeration is stubbed at `_host_planner` because that is the ONLY way a `None` planner
    reaches the authorization: passing `residency_planner=None` to the emitter means "ask the host",
    not "there is no planner"."""
    falsified = {"vram_budget_mb": None, "established": False, "estimate": True,
                 "budget_source": "STAND-IN 12288MB constant - FALSIFIED by the host"}
    monkeypatch.setattr("tools.live.emit_worker_launch._host_planner",
                        lambda: (None, falsified))
    ticket = _ticket(_local_option(), ollama_present=True)
    assert ticket["authorized"] is False
    assert ticket["refused_by"] == "vram_budget_unestablished"
    assert ticket["refused_by"] != "vram_admission"
    assert "could not be established" in ticket["reason"]
    assert "FALSIFIED" in ticket["reason"]


def test_a_budget_that_disagrees_with_the_planner_it_was_decided_by_is_refused() -> None:
    """The ticket DISCLOSES `residency.budget` as the basis the authorization was decided on, while
    the arithmetic runs against the planner's own total — and nothing paired them, so a ticket could
    state a figure the gate never used (validator MINOR-4 / U102)."""
    ticket = _ticket(_local_option(), residency_planner=_planner(total=20000, footprint=5000),
                     ollama_present=True,
                     residency_budget={"vram_budget_mb": 99999, "established": True,
                                       "estimate": True, "budget_source": "(test) overstated"})
    assert ticket["authorized"] is False
    # its OWN id: the budget on this branch WAS established, so stamping it
    # `vram_budget_unestablished` asserts something false about the refusal — the same intra-family
    # borrowing the first split ended, one level down (spec-audit MAJOR-2, 2026-07-26).
    assert ticket["refused_by"] == "vram_budget_mismatch"
    assert ticket["refused_by"] not in ("vram_budget_unestablished", "vram_admission")
    assert "99999" in ticket["reason"] and "20000" in ticket["reason"]


def test_a_model_whose_footprint_the_snapshot_cannot_report_is_its_own_gate(tmp_path) -> None:
    """"We could not tell" is not "it does not fit". The undecidable-fit branch stayed inside
    `vram_admission` after the first split, so a receipt leg asserting the FIT gate could go green
    on a snapshot that reported nothing usable (validator MINOR-1, 2026-07-26)."""
    class _BlindPlanner(ResidencyPlanner):
        def snapshot(self):
            snap = super().snapshot()
            for m in snap["models"]:
                m["footprint_mb"] = None          # the host reported no usable figure
            return snap

    planner = _BlindPlanner(20000)
    planner.register_model("qwen3:8b", 5000)
    ticket = _ticket(_local_option(), residency_planner=planner, ollama_present=True,
                     residency_budget={"vram_budget_mb": 20000, "established": True,
                                       "estimate": True, "budget_source": "(test)"})
    assert ticket["authorized"] is False
    assert ticket["refused_by"] == "vram_footprint_unknown"
    assert "cannot be DECIDED at all" in ticket["reason"]


def test_an_absent_local_runtime_is_its_own_gate_not_the_vram_one() -> None:
    ticket = _ticket(_local_option(), residency_planner=_planner(), ollama_present=False)
    assert ticket["refused_by"] == "runtime_absent"


def test_an_unauthorized_live_config_is_refused_by_the_live_operation_gate() -> None:
    ticket = _ticket(_frontier_option(), live_auth=_auth(False), cli_present=True)
    assert ticket["authorized"] is False
    assert ticket["refused_by"] in ("live_operation", "profile_roster")


def test_unconfirmed_operator_terms_are_refused_by_their_own_gate() -> None:
    ticket = _ticket(_frontier_option(), cli_present=True, operator_terms_confirmed=False)
    assert ticket["refused_by"] == "operator_terms"


def test_an_absent_frontier_cli_is_refused_by_the_cli_gate() -> None:
    ticket = _ticket(_frontier_option(), cli_present=False, operator_terms_confirmed=True)
    assert ticket["refused_by"] == "cli_present"


def test_no_refusal_this_build_can_raise_lands_on_the_unclassified_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback exists so a NEW refusal class can only under-claim; no gate this build routes
    through may reach it, or a receipt leg asserting a real id would silently stop firing.

    This DRIVES each refusal and reads the id off the ticket. The first version of this test asserted
    a hard-coded list against the literal `"unclassified"` — a tautology that stayed green with
    `_gate_id` forced to return the fallback unconditionally (validator R3)."""
    cases = [
        lambda: _ticket(_local_option(model_slug="never-offered"), offered=[_local_option()]),
        lambda: _ticket(_local_option(available=False, unavailable_reason="down")),
        lambda: _ticket(_frontier_option(roles=["reasoning", "conductor"]), "conductor"),
        lambda: _ticket(_local_option(), residency_planner=_planner(total=1000, footprint=4983),
                        ollama_present=True),
        lambda: _ticket(_local_option(), residency_planner=_planner(), ollama_present=False),
        lambda: _ticket(_frontier_option(), cli_present=True, operator_terms_confirmed=False),
        lambda: _ticket(_frontier_option(), cli_present=False),
        lambda: _ticket(_frontier_option(), live_auth=_auth(False), cli_present=True),
        lambda: build_worker_launch_ticket(
            registrar=None,
            holder_pid=1, session_id=SESSION, pane_id="bad pane id",
            selection={"option": _local_option(), "role": "reasoning", "mode": "autonomous"},
            live_auth=_auth(), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
            operator_terms_confirmed=True, offered_options=[_local_option()]),
    ]
    seen = set()
    for call in cases:
        ticket = call()
        assert ticket["authorized"] is False, ticket["reason"]
        assert ticket["refused_by"] != "unclassified", ticket["reason"]
        assert isinstance(ticket["refused_by"], str) and ticket["refused_by"]
        seen.add(ticket["refused_by"])
    # …and they are not all the same id, which would satisfy the assertions above while proving the
    # ids carry no information.
    assert len(seen) >= 5, seen
