"""Claims the worker launch ticket makes about ITSELF have to be true.

Every case here is a finding from the 2026-07-26 independent gate-validator pass and spec-audit of
17B `.ticket`, where a statement in the code or the ticket was not delivered by the code under it:

  * `exe = resolved or "claude"` — a fail-OPEN under the module's own claim that "the shell spawns
    exactly what was gated": with presence injected and detection empty, the ticket carried a bare
    binary NAME for the shell to PATH-search (spec-audit MINOR-4).
  * `chrome.node_state = "ready"` on a frontier authorization where nothing has spawned — a live-node
    state asserted about a node that does not exist, in the same ticket that says
    `containment.supervisor_bound: false` (spec-audit MINOR-1).
  * `governor_released` documented "measured, not asserted" while the refusal branch read the node id
    off a ticket whose `identity` is null: the comparison used a sentinel that can never be a holder,
    so it was vacuously true on exactly the branch where a leak is possible (spec-audit MINOR-5).
  * `_assert_option_offered` took the FIRST identity match, assuming the identity fields key an
    option — true on today's roster, asserted nowhere (spec-audit MINOR-6).
  * the enumeration-fault gate id (`host_enumeration`) exists so an enumeration crash cannot read as
    another gate firing, and had no test (validator MINOR-2).

Zero live calls, zero host dependence.
"""
from __future__ import annotations

import re

import pytest

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from node_runtime.supervisor.pane_node_spawn import PaneSelection
from node_runtime.supervisor.subscription_governor import (
    SubscriptionGovernor,
    canonical_subscription_ref,
)
from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger
from node_runtime.supervisor.worker_pane_spawn import (
    GATE_BINARY_UNRESOLVED,
    OLLAMA_LOCAL_ADAPTER,
    WorkerPaneRefused,
    _NOTE_SILENT_FLAGS,
    authorize_worker_pane,
)
from adapters.frontier.antigravity import ANTIGRAVITY_ADAPTER
from adapters.frontier.grok_build import GROK_ADAPTER
from adapters.frontier.provider_cli_common import FORBIDDEN_PERMISSION_MODES
from scheduler.residency_planner.residency_planner import ResidencyPlanner
from tools.live.emit_worker_launch import build_worker_launch_ticket

WORKSPACE = "D:/repo"
SUB = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)


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


def _local_option(**over: object) -> dict:
    option = {"provider": OLLAMA_LOCAL_ADAPTER, "adapter": OLLAMA_LOCAL_ADAPTER, "locality": "local",
              "subscription_backed": False, "label": "qwen3:8b", "model_slug": "qwen3:8b",
              "verified": True, "is_fallback": False, "roles": ["reasoning", "coding"],
              "residency": "not_loaded", "available": True, "unavailable_reason": None}
    option.update(over)
    return option


def _selection(option: dict, *, role: str = "reasoning", sub: str | None = None) -> PaneSelection:
    return PaneSelection(option=option, role=role, mode="autonomous", node_id="worker-pane-2",
                         permission_profile_id=f"pp-worker-{role}", subscription_ref=sub)


def _budget(total: int) -> dict:
    return {"vram_budget_mb": total, "budget_source": "(test) established", "estimate": True,
            "established": True}


def _planner(total: int = 20000, footprint: int = 5000) -> ResidencyPlanner:
    p = ResidencyPlanner(total)
    p.register_model("qwen3:8b", footprint)
    return p


# -- a bare binary name is never emitted -----------------------------------------------------------

@pytest.mark.parametrize("resolved", [None, "", "   "])
def test_a_presence_gate_that_resolved_no_binary_refuses_instead_of_emitting_a_name(
    monkeypatch: pytest.MonkeyPatch, resolved,
) -> None:
    """`cli_present=True` with detection returning nothing used to fall back to `"claude"`. The
    shell then PATH-searches a name — whatever answers to it at spawn time, which is precisely what
    the renderer's binary allowlist cannot check and what this module promises not to do."""
    from adapters import detect

    monkeypatch.setattr(detect, "claude_code_executable", lambda: resolved)
    with pytest.raises(WorkerPaneRefused) as exc:
        authorize_worker_pane(
            _selection(_frontier_option(), sub=SUB), live_auth=_auth(CLAUDE_CODE_ADAPTER),
            governor=SubscriptionGovernor(), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
            operator_terms_confirmed=True, workspace=WORKSPACE, cli_present=True)
    assert exc.value.gate == GATE_BINARY_UNRESOLVED
    assert "PATH-search" in str(exc.value)


def test_the_local_path_refuses_a_bare_name_too(monkeypatch: pytest.MonkeyPatch) -> None:
    from adapters import detect

    monkeypatch.setattr(detect, "ollama_executable", lambda: None)
    with pytest.raises(WorkerPaneRefused) as exc:
        authorize_worker_pane(
            _selection(_local_option()), live_auth=_auth(), governor=SubscriptionGovernor(),
            profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
            workspace=WORKSPACE, residency_planner=_planner(), residency_budget=_budget(20000),
            ollama_present=True)
    assert exc.value.gate == GATE_BINARY_UNRESOLVED


def test_a_resolved_binary_is_carried_through_verbatim() -> None:
    """The fail-closed rule must not break the normal case."""
    session = authorize_worker_pane(
        _selection(_frontier_option(), sub=SUB), live_auth=_auth(CLAUDE_CODE_ADAPTER),
        governor=SubscriptionGovernor(), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, workspace=WORKSPACE, cli_present=True,
        executable="C:/tools/claude.exe")
    assert session.launch["executable"] == "C:/tools/claude.exe"
    assert session.launch["argv"][0] == "C:/tools/claude.exe"
    session.teardown()


# -- a node that has not been born is not "ready" --------------------------------------------------

def test_a_frontier_authorization_does_not_report_a_live_node_state() -> None:
    session = authorize_worker_pane(
        _selection(_frontier_option(), sub=SUB), live_auth=_auth(CLAUDE_CODE_ADAPTER),
        governor=SubscriptionGovernor(), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, workspace=WORKSPACE, cli_present=True, executable="claude")
    assert session.chrome.node_state == "launch_authorized"
    assert session.chrome.node_state != "ready", (
        "nothing has spawned: the same ticket reports containment.supervisor_bound false")
    session.teardown()


def test_a_local_authorization_does_not_report_a_live_node_state_either() -> None:
    """The local branch was NOT already honest — it derived node_state from the residency decision,
    which is a fact about a MODEL, not about a node. Deriving is not the same as being true: a
    scheduled load reported "loading" harmlessly, but an already-resident model reported "ready" for
    a node that has not been born, in the same ticket that says supervisor_bound false (invariant
    3/27, spec-audit MAJOR-1 2026-07-26). Both branches now report the authorization state; the
    residency fact keeps its own field, where it is true."""
    session = authorize_worker_pane(
        _selection(_local_option()), live_auth=_auth(), governor=SubscriptionGovernor(),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
        workspace=WORKSPACE, residency_planner=_planner(), residency_budget=_budget(20000),
        ollama_present=True, executable="ollama")
    assert session.chrome.node_state == "launch_authorized"
    assert session.chrome.residency == "loading"       # scheduled, not yet resident — the model fact
    session.teardown()


def test_an_already_resident_local_model_is_not_reported_as_a_ready_node() -> None:
    """The reachable half of spec-audit MAJOR-1: on the operator's own host every `/api/ps` model is
    seeded RESIDENT (enumerate_pane_picker), so this is the state a re-selection actually produces —
    and it was the one that read `ready`."""
    planner = ResidencyPlanner(20000)
    planner.register_model("qwen3:8b", 5200)
    planner.request_load("qwen3:8b")
    planner.complete_load("qwen3:8b")
    session = authorize_worker_pane(
        _selection(_local_option()), live_auth=_auth(), governor=SubscriptionGovernor(),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
        workspace=WORKSPACE, residency_planner=planner, residency_budget=_budget(20000),
        ollama_present=True, executable="ollama")
    assert session.chrome.residency == "resident"      # the model IS in VRAM — that stays true
    assert session.chrome.node_state == "launch_authorized"
    assert session.chrome.node_state != "ready", (
        "no process exists: the same ticket reports containment.supervisor_bound false")
    session.teardown()


# -- governor_released is measured on the branch where a leak is possible ---------------------------

def _ticket(option: dict, *, offered: list | None = None, **kw):
    return build_worker_launch_ticket(
        registrar=None,
        holder_pid=4242, session_id="s-1", pane_id="pane-2",
        selection={"option": option, "role": "reasoning", "mode": "autonomous"},
        profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=kw.pop("operator_terms_confirmed", True),
        offered_options=[option] if offered is None else offered, **kw)


def test_a_refusal_after_the_identity_was_minted_measures_the_real_node(tmp_path) -> None:
    """A governor still holding the minted node after a refusal must report
    `governor_released: false`. The refusal branch used to read the node id off the ticket, which is
    `null` there, falling back to a sentinel that can never be a holder — so the field said "nothing
    leaked" without looking (spec-audit MINOR-5)."""
    gov = SubscriptionGovernor()
    gov.register_subscription(SUB, CLAUDE_CODE_ADAPTER, allowance=2)
    gov.acquire(SUB, "worker-pane-2")                  # a terminal this node already holds
    # refuse AFTER minting: the provider is not live, which is asserted downstream of the identity
    ticket = _ticket(_frontier_option(), live_auth=_auth(), governor=gov,
                     ledger=TerminalLeaseLedger(path=str(tmp_path / "leases.json")),
                     cli_present=True)
    assert ticket["authorized"] is False
    assert ticket["identity"] is None                  # a refusal ticket names no identity …
    assert ticket["governor_released"] is False        # … but the measurement still found the node


def test_a_refusal_before_any_identity_existed_reports_nothing_leaked() -> None:
    """The sentinel survives only where it is honest: no identity was ever minted, so nothing could
    have been acquired."""
    ticket = build_worker_launch_ticket(
        registrar=None,
        holder_pid=1, session_id="s-1", pane_id="pane-2", selection="not a dict",
        live_auth=_auth(), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, offered_options=[])
    assert ticket["authorized"] is False
    assert ticket["governor_released"] is True


# -- an ambiguous offer is refused, not resolved by ordering ----------------------------------------

def test_two_host_options_with_the_same_identity_refuse_instead_of_binding_the_first() -> None:
    first = _frontier_option(label="Fable 5", verified=True)
    second = _frontier_option(label="Fable 5 (preview)", verified=False)
    ticket = _ticket(first, offered=[first, second], live_auth=_auth(CLAUDE_CODE_ADAPTER),
                     cli_present=True)
    assert ticket["authorized"] is False
    assert ticket["refused_by"] == "host_enumeration"
    assert "matches 2 distinct options" in ticket["reason"]


def test_one_matching_option_still_binds(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from adapters import detect

    monkeypatch.setattr(detect, "claude_code_executable", lambda: "C:/tools/claude.exe")
    opt = _frontier_option()
    ticket = _ticket(opt, offered=[opt, _frontier_option(model_slug="opus-4.8", label="Opus 4.8")],
                     live_auth=_auth(CLAUDE_CODE_ADAPTER), cli_present=True,
                     ledger=TerminalLeaseLedger(path=str(tmp_path / "leases.json")))
    assert ticket["authorized"] is True
    assert ticket["chrome"]["model_label"] == "fable-5"
    assert ticket["launch"]["executable"] == "C:/tools/claude.exe"


# -- an enumeration fault is its own gate ----------------------------------------------------------

def test_a_host_enumeration_crash_is_reported_under_its_own_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The id exists so an enumeration crash can never be read as evidence that a DOWNSTREAM gate
    fired — the BLOCKING-1c defect. The `_assert_option_offered` sites were covered; this one, the
    fault path itself, was not (validator MINOR-2)."""
    def _boom():
        raise RuntimeError("daemon exploded mid-enumeration")

    monkeypatch.setattr("tools.live.enumerate_pane_picker.build_host_picker", _boom)
    ticket = build_worker_launch_ticket(
        registrar=None,
        holder_pid=1, session_id="s-1", pane_id="pane-2",
        selection={"option": _local_option(), "role": "reasoning", "mode": "attended"},
        live_auth=_auth(), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True)
    assert ticket["authorized"] is False
    assert ticket["refused_by"] == "host_enumeration"
    assert ticket["refused_by"] not in ("vram_admission", "vram_budget_unestablished",
                                        "selection_guard", "unclassified")
# -- the note a ticket carries about itself must be READ OFF the argv it describes ---------------
# Phase 19 unit 1 (OP-13). Both mandatory reviewers found the same residue independently: the
# untagged post-18E range widened the two OP-12 argvs AND hand-edited the launch notes to match
# ("--mode accept-edits", "plan disabled"). Unit 19.1 reverted the argv; nothing in 2262 tests
# could see that the ticket still ADVERTISED the mode the operator had just forbidden, because a
# sentence cannot disagree with a list it was never derived from. It is derived now, and this is
# the test that makes the derivation load-bearing.

def _op12_pane(adapter: str, exe: str):
    option = {"provider": adapter, "adapter": adapter, "locality": "frontier",
              "subscription_backed": True, "label": "m-1", "model_slug": "m-1", "verified": True,
              "is_fallback": False, "roles": ["reasoning"], "residency": None, "available": True,
              "unavailable_reason": None}
    sel = PaneSelection(option=option, role="reasoning", mode="autonomous", node_id="worker-pane-9",
                        permission_profile_id="pp-worker-reasoning",
                        subscription_ref=canonical_subscription_ref(adapter))
    return authorize_worker_pane(
        sel, live_auth=_auth(GROK_ADAPTER, ANTIGRAVITY_ADAPTER), governor=SubscriptionGovernor(),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
        workspace=WORKSPACE, cli_present=True, executable=exe)


@pytest.mark.parametrize("adapter, exe", [(GROK_ADAPTER, "C:/fake/grok.CMD"),
                                          (ANTIGRAVITY_ADAPTER, "C:/fake/agy.CMD")])
def test_the_launch_note_claims_only_flags_the_argv_actually_carries(adapter, exe) -> None:
    session = _op12_pane(adapter, exe)
    argv = session.launch["argv"]
    note = session.launch["note"]
    for token in re.findall(r"--[a-z][a-z-]+", note):
        assert token in argv, f"{adapter}: the note claims {token}, the argv does not carry it"
    for flag in ("--mode", "--permission-mode"):
        for claimed in re.findall(rf"{flag} ([A-Za-z][A-Za-z-]*)", note):
            assert argv[argv.index(flag) + 1] == claimed


@pytest.mark.parametrize("adapter, exe", [(GROK_ADAPTER, "C:/fake/grok.CMD"),
                                          (ANTIGRAVITY_ADAPTER, "C:/fake/agy.CMD")])
def test_no_launch_note_advertises_a_mode_the_guard_forbids(adapter, exe) -> None:
    """The specific regression: `--mode accept-edits` in the ticket the operator reads, while the
    argv says `plan`. Neither the words nor the argv may carry a forbidden mode (D-P18-13/U317)."""
    session = _op12_pane(adapter, exe)
    haystack = (session.launch["note"] + " " + " ".join(session.launch["argv"])).lower()
    for forbidden in FORBIDDEN_PERMISSION_MODES:
        assert forbidden not in haystack
        assert forbidden not in haystack.replace("-", "")     # `acceptedits` AND `accept-edits`
    assert "plan disabled" not in haystack and "--no-plan" not in haystack


@pytest.mark.parametrize("adapter, exe, bind", [(GROK_ADAPTER, "C:/fake/grok.CMD", "--cwd"),
                                                (ANTIGRAVITY_ADAPTER, "C:/fake/agy.CMD",
                                                 "--add-dir")])
def test_the_note_never_prints_the_workspace_path_it_binds(adapter, exe, bind) -> None:
    """`describe_pinned_flags` renders a workspace-valued flag as a phrase, not a path: the
    pre-range notes said "scoped to the authorized workspace" and the derivation keeps that,
    because a ticket note is operator-facing chrome, not a second copy of the argv. Parametrized
    at round 2 - it was Grok-only, so the Antigravity branch's redaction was untested
    (spec-audit MINOR-8 / gate-validator MINOR-1)."""
    session = _op12_pane(adapter, exe)
    assert WORKSPACE not in session.launch["note"]
    assert "scoped to the authorized workspace" in session.launch["note"]
    assert session.launch["argv"][session.launch["argv"].index(bind) + 1] == WORKSPACE


@pytest.mark.parametrize("adapter, exe", [(GROK_ADAPTER, "C:/fake/grok.CMD"),
                                          (ANTIGRAVITY_ADAPTER, "C:/fake/agy.CMD")])
def test_the_note_omits_no_flag_the_argv_carries(adapter, exe) -> None:
    """The OTHER direction, and the one round 2 had to add. The first derivation rendered an
    ENUMERATED set of noteworthy flags: it could not over-claim, but it could silently omit - and
    the flags it would have omitted include `--allow` and `--no-plan`, i.e. precisely the half of
    the widening this unit reverted. Both reviewers found it independently (gate-validator
    MEDIUM-1: dropping the mode flags from the set left the whole suite green; spec-audit
    MEDIUM-1). Disclosure that fails open is not disclosure, so the set is an EXCLUSION list now
    and this test walks argv -> note."""
    session = _op12_pane(adapter, exe)
    argv, note = session.launch["argv"], session.launch["note"]
    for i, tok in enumerate(argv[1:], start=1):
        if not tok.startswith("-") or tok in _NOTE_SILENT_FLAGS:
            continue
        if argv[i - 1] in _NOTE_SILENT_FLAGS:     # a value of a silent flag, not a flag itself
            continue
        assert tok in note, f"{adapter}: the argv carries {tok}, the note does not disclose it"
