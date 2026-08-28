"""U292(a) / U283 on the pane-worker emitter — the two gate inputs this module may not invent.

Directive §17.2(3) sends the `gates.operator_terms_confirmed` parameter default here for "the
U283-style closure", and the same closure covers its twin on the same signature, because they are
one defect with two spellings: `build_worker_launch_ticket` answered two questions that are not
its to answer.

  * `profile_loader: ProfileLoader | None = None` fell back to
    `ProfileLoader(DeploymentProfile("cloud"))`. Which deployment profile is in force is the HOST's
    fact. Manufacturing `cloud` made invariant 20's air-gap half **structurally unreachable on the
    product path** — the shell could open a frontier pane on an air-gapped host, and every test
    that "covered" the air-gap injected the loader the product never passed. That is U91's shape,
    found by both reviewers on `provider_probe_session` at 18C `.probe-path` and closed there
    (U283); this module was the surface U292(a) recorded as still carrying it.
  * `operator_terms_confirmed: bool = True` published `gates.operator_terms_confirmed: true` in
    every ticket while no production caller supplied it — a PARAMETER DEFAULT rendered as a
    measurement. The 18C receipt had to disclose exactly that in `scope_note_gate_map` and exclude
    the gate from its verdict. That is U98's shape.

Both are now REQUIRED keywords, and `main()` — the sole production caller — supplies each with its
authorizing artifact named at the call site. These tests fail if either default comes back.

Zero live calls, zero host dependence: no test here spawns anything or reads a real switch.
"""
from __future__ import annotations

import inspect
import io
import json

import pytest
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader, ProfileViolation

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from control_plane.profiles.live_authorization import LiveAuthorization
from node_runtime.supervisor.provider_probe_session import profile_loader_from_host
from tools.live import emit_worker_launch as EWL

PANE, SESSION, HOLDER = "pane-2", "pane-2#7.1", 4242


def _auth(*providers: str) -> LiveAuthorization:
    return LiveAuthorization(
        authorized=bool(providers), providers=frozenset(providers), terminals_per_subscription=2,
        register_row="OP-6", source="(test)", reason="test authorization")


def _frontier_option(**over: object) -> dict:
    option = {"provider": CLAUDE_CODE_ADAPTER, "adapter": CLAUDE_CODE_ADAPTER,
              "locality": "frontier", "subscription_backed": True, "label": "fable-5",
              "model_slug": "fable-5", "verified": False, "is_fallback": False,
              "roles": ["reasoning", "coding"], "residency": None, "available": True,
              "unavailable_reason": None}
    option.update(over)
    return option


def _selection(option: dict | None = None) -> dict:
    return {"option": option if option is not None else _frontier_option(),
            "role": "reasoning", "mode": "autonomous"}


# ---------------------------------------------------------------------------------------------
# 1. The signature itself: neither question has a default answer any more
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["profile_loader", "operator_terms_confirmed"])
def test_the_gate_input_is_a_required_keyword(name: str) -> None:
    param = inspect.signature(EWL.build_worker_launch_ticket).parameters[name]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty, (
        f"{name} has a default again: this module is answering a question that belongs to the "
        f"host (profile) or the operator (terms) — U283/U292(a)")


@pytest.mark.parametrize("omit", ["profile_loader", "operator_terms_confirmed"])
def test_omitting_a_gate_input_raises_rather_than_assuming_one(omit: str) -> None:
    call = dict(holder_pid=HOLDER, session_id=SESSION, pane_id=PANE, selection=_selection(),
                live_auth=_auth(), offered_options=[_frontier_option()],
                profile_loader=ProfileLoader(DeploymentProfile("cloud")),
                operator_terms_confirmed=True)
    call.pop(omit)
    with pytest.raises(TypeError):
        EWL.build_worker_launch_ticket(
        registrar=None,**call)


def test_the_emitter_never_manufactures_a_deployment_profile() -> None:
    """The literal that made the air-gap branch unreachable must not exist as CODE in the function.

    Comment lines are excluded on purpose: the closure's own explanation quotes the literal it
    removed, and a check that cannot tell an explanation from an instruction would forbid saying
    what was fixed."""
    code = "\n".join(line for line in inspect.getsource(EWL.build_worker_launch_ticket).splitlines()
                     if not line.lstrip().startswith("#"))
    assert 'DeploymentProfile("cloud")' not in code
    assert "DeploymentProfile('cloud')" not in code


# ---------------------------------------------------------------------------------------------
# 2. The gate the emitter PUBLISHES is now the value it was GIVEN — on both branches
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("confirmed", [True, False])
def test_the_published_terms_gate_tracks_the_injected_value(confirmed: bool, tmp_path) -> None:
    ticket = EWL.build_worker_launch_ticket(
        registrar=None,
        holder_pid=HOLDER, session_id=SESSION, pane_id=PANE, selection=_selection(),
        live_auth=_auth(CLAUDE_CODE_ADAPTER), offered_options=[_frontier_option()],
        profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=confirmed, cli_present=True,
        ledger=EWL.TerminalLeaseLedger(path=str(tmp_path / "leases.json")))
    assert ticket["gates"]["operator_terms_confirmed"] is confirmed
    if not confirmed:
        assert ticket["authorized"] is False
        assert ticket["refused_by"] == "operator_terms"


# ---------------------------------------------------------------------------------------------
# 3. The PRODUCTION path — `main()` — supplies both, and invariant 20 is reachable through it
#
# This is the leg that matters: U283's air-gap half was proved by EXECUTION, not by argument, and
# the only honest way to show a default is gone is to drive the caller that used to rely on it.
# ---------------------------------------------------------------------------------------------
def _run_main(monkeypatch, selection: dict, tmp_path) -> dict:
    monkeypatch.setattr(EWL, "_default_ledger",
                        lambda: EWL.TerminalLeaseLedger(path=str(tmp_path / "leases.json")))
    monkeypatch.setattr(EWL, "load_live_authorization", lambda: _auth(CLAUDE_CODE_ADAPTER))
    monkeypatch.setattr(EWL, "_detect_frontier_cli", lambda adapter, injected=None: True)
    monkeypatch.setattr("tools.live.enumerate_pane_picker.build_host_picker",
                        lambda *a, **kw: ({"options": [selection["option"]]}, {}))
    monkeypatch.setattr(EWL.sys, "stdin", io.StringIO(json.dumps(selection)))
    out = io.StringIO()
    monkeypatch.setattr(EWL.sys, "stdout", out)
    rc = EWL.main(["--emit-worker-launch", "--holder-pid", str(HOLDER),
                   "--session-id", SESSION, "--pane-id", PANE])
    assert rc == 0
    return json.loads(out.getvalue())


def test_the_production_path_refuses_a_frontier_pane_on_an_airgapped_host(monkeypatch, tmp_path):
    """Invariant 20, reached through `main()` and nothing injected but the host's own env var. On
    the pre-fix tree this returned an AUTHORIZED ticket: the emitter handed the gate chain a
    `cloud` loader it made up, so the air-gap could not refuse."""
    monkeypatch.setenv("SOVEREIGN_DEPLOYMENT_PROFILE", "offline_airgapped")
    ticket = _run_main(monkeypatch, _selection(), tmp_path)
    assert ticket["authorized"] is False
    assert ticket["refused_by"] == "profile_roster"


def test_the_same_production_path_still_authorizes_on_a_cloud_host(monkeypatch, tmp_path):
    """The other direction, so the test above cannot pass by refusing everything."""
    monkeypatch.setenv("SOVEREIGN_DEPLOYMENT_PROFILE", "cloud")
    from adapters import detect
    monkeypatch.setattr(detect, "claude_code_executable", lambda: "C:/tools/claude.exe")
    ticket = _run_main(monkeypatch, _selection(), tmp_path)
    assert ticket["authorized"] is True, ticket["reason"]
    assert ticket["gates"]["operator_terms_confirmed"] is True


def test_an_unset_profile_variable_is_cloud_and_an_unknown_one_raises(monkeypatch, tmp_path):
    """Both of `profile_loader_from_host`'s branches, inherited rather than re-derived (one
    implementation of the question — U283).

    Only ONE of them fails closed. An UNKNOWN id raises, which does. An UNSET variable resolves to
    `cloud` — the most permissive profile — which on the Buildout §4 "missing policy" axis is
    fail-OPEN, and the source docstring's "fails closed twice over" overstates it (gate-validator
    F8). It is defensible as a default (this build's host is a cloud-profile workstation and every
    downstream live gate still has to pass) but it is a default, not a refusal, and this test is
    named for what it measures rather than for what the docstring claims. Recorded as U306."""
    monkeypatch.delenv("SOVEREIGN_DEPLOYMENT_PROFILE", raising=False)
    from adapters import detect
    monkeypatch.setattr(detect, "claude_code_executable", lambda: "C:/tools/claude.exe")
    assert _run_main(monkeypatch, _selection(), tmp_path)["authorized"] is True

    monkeypatch.setenv("SOVEREIGN_DEPLOYMENT_PROFILE", "banana")
    with pytest.raises(ProfileViolation) as exc:
        _run_main(monkeypatch, _selection(), tmp_path)
    assert "banana" in str(exc.value)


# ---------------------------------------------------------------------------------------------
# 4. Invariant 20 is reached BEFORE the enumeration that costs egress (spec-audit F2, U303)
#
# The verdict was already right once the manufactured `cloud` loader was gone. What was wrong was
# the ORDER: `_assert_option_offered` enumerates first, and for an OP-12 selection that enumeration
# is `grok models` / `agy models`, which leave the host. "Excluded from the offline profile" has to
# mean the network was never touched.
# ---------------------------------------------------------------------------------------------
def _op12_option(**over: object) -> dict:
    option = _frontier_option(provider=EWL.GROK_ADAPTER, adapter=EWL.GROK_ADAPTER,
                              label="grok-4", model_slug="grok-4")
    option.update(over)
    return option


@pytest.mark.parametrize("adapter", ["claude_code", "grok_build", "google_antigravity"])
def test_an_airgapped_host_refuses_a_frontier_pane_without_enumerating(monkeypatch, tmp_path,
                                                                      adapter: str) -> None:
    """The refusal AND the silence. `build_host_picker` is replaced with a detonator: if the
    air-gap gate is moved back behind the enumeration, this fails with the call it should not have
    made rather than with an assertion about a gate id."""
    calls: list[object] = []

    def _detonate(*a: object, **kw: object):
        calls.append((a, kw))
        raise AssertionError(
            "the host enumeration ran on an air-gapped profile: for an OP-12 provider this is an "
            "outbound `models` call made to verify a pane invariant 20 forbids opening")

    monkeypatch.setattr("tools.live.enumerate_pane_picker.build_host_picker", _detonate)
    monkeypatch.setenv("SOVEREIGN_DEPLOYMENT_PROFILE", "offline_airgapped")

    ticket = EWL.build_worker_launch_ticket(
        registrar=None,
        holder_pid=HOLDER, session_id=SESSION, pane_id=PANE,
        selection=_selection(_op12_option(provider=adapter, adapter=adapter)),
        live_auth=_auth(adapter), profile_loader=profile_loader_from_host(),
        operator_terms_confirmed=True,
        ledger=EWL.TerminalLeaseLedger(path=str(tmp_path / "leases.json")))

    assert ticket["authorized"] is False
    assert ticket["refused_by"] == "profile_roster", ticket
    assert calls == [], "the enumeration was reached"
    assert ticket["gates"]["selection_offered"] is False


def test_the_same_selection_on_a_cloud_profile_does_reach_the_enumeration(monkeypatch,
                                                                         tmp_path) -> None:
    """The control: the guard above must be the AIR-GAP refusing, not this build having quietly
    stopped verifying selections. On a cloud profile the enumeration is still consulted.

    `op12_probes` is injected as `no_op12_probes()` to keep this test host-free — WITHOUT it the
    suite's live-call guard fires on a real `grok models`, which is itself the measurement behind
    the guard under test: for an OP-12 selection the egress is paid in `_host_offered_options` when
    it builds `only_op12_probe(provider)`, one step EARLIER than `build_host_picker`. The air-gap
    refusal above sits upstream of both, which is why it needs no such injection."""
    from tools.live.enumerate_pane_picker import no_op12_probes

    calls: list[object] = []
    monkeypatch.setattr("tools.live.enumerate_pane_picker.build_host_picker",
                        lambda *a, **kw: (calls.append(kw), ({"options": []}, {}))[1])
    monkeypatch.setenv("SOVEREIGN_DEPLOYMENT_PROFILE", "cloud")

    ticket = EWL.build_worker_launch_ticket(
        registrar=None,
        holder_pid=HOLDER, session_id=SESSION, pane_id=PANE, selection=_selection(_op12_option()),
        live_auth=_auth(EWL.GROK_ADAPTER), profile_loader=profile_loader_from_host(),
        operator_terms_confirmed=True, op12_probes=no_op12_probes(),
        ledger=EWL.TerminalLeaseLedger(path=str(tmp_path / "leases.json")))

    assert len(calls) == 1, "the cloud path stopped verifying the selection against the host"
    # The enumeration ran and offered nothing, so the selection cannot be verified against it —
    # the enumeration's OWN gate id, deliberately distinct from the selection guard.
    assert ticket["authorized"] is False
    assert ticket["refused_by"] == "host_enumeration"


def test_a_local_selection_on_an_airgapped_host_is_not_refused_by_this_guard(monkeypatch,
                                                                            tmp_path) -> None:
    """The guard is scoped to frontier adapters. A local model on an air-gapped host is exactly the
    case the offline profile EXISTS to serve (invariant 19/20), so it must reach the enumeration and
    be judged on its own merits — a guard that refused everything would be no guard at all."""
    calls: list[object] = []
    monkeypatch.setattr("tools.live.enumerate_pane_picker.build_host_picker",
                        lambda *a, **kw: (calls.append(kw), ({"options": []}, {}))[1])
    monkeypatch.setenv("SOVEREIGN_DEPLOYMENT_PROFILE", "offline_airgapped")

    local = _frontier_option(provider="ollama_local", adapter="ollama_local", locality="local",
                             subscription_backed=False, label="qwen3:8b", model_slug="qwen3:8b")
    ticket = EWL.build_worker_launch_ticket(
        registrar=None,
        holder_pid=HOLDER, session_id=SESSION, pane_id=PANE, selection=_selection(local),
        live_auth=_auth(), profile_loader=profile_loader_from_host(),
        operator_terms_confirmed=True,
        ledger=EWL.TerminalLeaseLedger(path=str(tmp_path / "leases.json")))

    assert len(calls) == 1
    assert ticket["refused_by"] != "profile_roster"


def test_main_names_the_authorizing_ruling_for_the_terms_flag() -> None:
    """`operator_terms_confirmed=True` is a CITATION of a recorded operator determination
    (invariant 1). A citation nobody can look up is prose, so the call site has to carry it."""
    src = inspect.getsource(EWL.main)
    assert "profile_loader_from_host()" in src
    assert "operator_terms_confirmed=True" in src
    assert "OP-9" in src and "OP-12" in src
