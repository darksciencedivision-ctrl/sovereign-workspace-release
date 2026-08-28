"""Governed LIVE WORKER pane authorization (Phase 17B `.ticket`; directive §16 track 17B, U70).

16B wired the per-pane picker's READ path and RECORDED a selection; nothing was ever born from it
(`governed:false`, `selected_awaiting_governed_spawn`) — the operator's first-use finding F3: "a
picker selection records + badges but launches nothing". 17B `.ticket` builds the authorization half:
one picker selection → the SAME gate chain the conductor pane runs → an executable interactive launch
spec, or a fail-closed refusal.

What these tests pin, with ZERO live calls:

  * the selection guard is the ONE shared authority (`pane_node_spawn.assert_selection_spawnable`):
    greyed option, unknown mode, unoffered role, conductor role, naked identity are all refused
    BEFORE any gate/governor/planner mutation;
  * a frontier worker runs the full live chain — profile/roster + LIVE_OPERATION_AUTHORIZED,
    provider-live, R8 §6 operator terms, CLI presence, I-X3 acquire — and yields an INTERACTIVE argv
    (no `-p`, no `codex exec`), never a headless one-shot;
  * a LOCAL worker is NOT subscription-governed (invariant 19/22): no I-X3 count, no live gate, but
    it MUST route through the ResidencyPlanner and is refused when VRAM cannot be proven to fit;
  * the chrome is carried VERBATIM from the picker option (invariant 3 — a badge can never diverge
    from what the operator selected) and `model_verified` is never upgraded here;
  * D-LOOP-1: `teardown()` releases a frontier terminal and is a no-op for a local node.
"""
from __future__ import annotations

import pytest

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from node_runtime.supervisor.frontier_spawn import ClaudeCliUnavailable
from adapters.frontier.codex import CODEX_ADAPTER, SANDBOX_READ_ONLY
from adapters.local.ollama_session import build_interactive_ollama_command
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader, ProfileViolation
from node_runtime.supervisor.frontier_spawn import LiveTermsNotConfirmed
from node_runtime.supervisor.pane_node_spawn import PaneSelection, SpawnRefused
from node_runtime.supervisor.subscription_governor import (
    SubscriptionGovernor,
    SubscriptionLimitExceeded,
    canonical_subscription_ref,
)
from node_runtime.supervisor.worker_pane_spawn import (
    OLLAMA_LOCAL_ADAPTER,
    WorkerPaneRefused,
    authorize_worker_pane,
    worker_identity,
)
from scheduler.residency_planner.residency_planner import ResidencyPlanner

WORKSPACE = "D:/repo"


def _authorized(*providers: str) -> LiveAuthorization:
    return LiveAuthorization(
        authorized=True, providers=frozenset(providers or (CLAUDE_CODE_ADAPTER,)),
        terminals_per_subscription=2, register_row="OP-6", source="(test)",
        reason="test authorization")


def _loader() -> ProfileLoader:
    return ProfileLoader(DeploymentProfile("cloud"))


def _frontier_option(adapter: str = CLAUDE_CODE_ADAPTER, *, slug: str | None = "fable-5",
                     available: bool = True, roles: tuple[str, ...] = ("reasoning", "coding")) -> dict:
    return {"provider": adapter, "adapter": adapter, "locality": "frontier",
            "subscription_backed": True, "label": slug or "CLI default", "model_slug": slug,
            "verified": False, "is_fallback": slug is None, "roles": list(roles),
            "residency": None, "available": available,
            "unavailable_reason": None if available else "not authorized"}


def _local_option(tag: str = "qwen3:8b", *, available: bool = True,
                  roles: tuple[str, ...] = ("reasoning", "coding")) -> dict:
    return {"provider": OLLAMA_LOCAL_ADAPTER, "adapter": OLLAMA_LOCAL_ADAPTER, "locality": "local",
            "subscription_backed": False, "label": tag, "model_slug": tag, "verified": True,
            "is_fallback": False, "roles": list(roles), "residency": "not_loaded",
            "available": available, "unavailable_reason": None if available else "daemon down"}


def _established_budget(total_mb: int = 12288) -> dict:
    """An ESTABLISHED budget dict, as the host enumeration returns alongside a usable planner.

    Required now: `_authorize_local` refuses an authorization whose budget is not established, so a
    planner with no provenance is (correctly) a fail-closed refusal rather than a silent admission
    against a total nobody vouched for (spec-audit MAJOR-1, 2026-07-26)."""
    return {"vram_budget_mb": total_mb, "budget_source": "(test) established budget",
            "estimate": True, "established": True}


def _selection(option: dict, *, role: str = "reasoning", mode: str = "autonomous",
               node_id: str = "worker-pane-2", profile: str = "pp-worker-reasoning",
               subscription_ref: str | None = None) -> PaneSelection:
    return PaneSelection(option=option, role=role, mode=mode, node_id=node_id,
                         permission_profile_id=profile, subscription_ref=subscription_ref)


def _planner(total_mb: int = 12288, *, register: dict[str, int] | None = None) -> ResidencyPlanner:
    planner = ResidencyPlanner(total_mb)
    for name, mb in (register or {"qwen3:8b": 5200}).items():
        planner.register_model(name, mb)
    return planner


# ---- identity ---------------------------------------------------------------------------------

def test_worker_identity_is_minted_python_side_and_is_deterministic():
    a = worker_identity("pane-3", "reasoning")
    b = worker_identity("pane-3", "reasoning")
    assert a == b
    assert a["node_id"] == "worker-pane-3"
    assert a["permission_profile_id"] == "pp-worker-reasoning"
    assert worker_identity("pane-3", "coding")["permission_profile_id"] == "pp-worker-coding"


def test_worker_identity_refuses_an_empty_pane_or_unknown_role():
    with pytest.raises(WorkerPaneRefused):
        worker_identity("", "reasoning")
    with pytest.raises(WorkerPaneRefused):
        worker_identity("pane-3", "conductor")


@pytest.mark.parametrize("pane", ["../escape", "pane 2", "p" * 65, "pane/2", "pane\t2"])
def test_worker_identity_bounds_the_shell_supplied_pane_id(pane):
    """A node id becomes a durable lease KEY; whitespace/path separators/unbounded strings make a
    terminal nobody can reliably reclaim (spec-audit MINOR-10)."""
    with pytest.raises(WorkerPaneRefused) as err:
        worker_identity(pane, "reasoning")
    assert "pane id" in str(err.value)


def test_a_local_pane_that_would_displace_another_model_is_refused():
    """Invariant 22 forbids mid-generation eviction, and this planner cannot tell whether a model it
    considers idle is answering right now — so it refuses to displace anything at all."""
    planner = ResidencyPlanner(6000)
    planner.register_model("qwen3:8b", 5200)
    planner.register_model("other:7b", 5000)
    planner.request_load("other:7b")
    planner.complete_load("other:7b")
    with pytest.raises(WorkerPaneRefused) as err:
        authorize_worker_pane(_selection(_local_option()), live_auth=_authorized(),
                              governor=SubscriptionGovernor(), profile_loader=_loader(),
                              operator_terms_confirmed=True, workspace=WORKSPACE,
                              residency_planner=planner,
                              residency_budget=_established_budget(planner.total_vram_mb()),
                              ollama_present=True)
    assert "displacing" in str(err.value)


def test_a_refused_local_pane_leaves_the_planner_state_untouched():
    """The refusal must be decided BEFORE `request_load` mutates anything: a refused pane that had
    already marked itself LOADING (and another model evicted) would corrupt the residency view the
    operator sees — invariant 22's "scheduled, VISIBLE" (validator FINDING 3)."""
    planner = ResidencyPlanner(10000)
    planner.register_model("resident-a", 8000)
    planner.register_model("qwen3:8b", 5000)
    planner.request_load("resident-a")
    planner.complete_load("resident-a")
    before_map = dict(planner.residency_map())
    before_free = planner.free_vram_mb()

    with pytest.raises(WorkerPaneRefused):
        authorize_worker_pane(_selection(_local_option()), live_auth=_authorized(),
                              governor=SubscriptionGovernor(), profile_loader=_loader(),
                              operator_terms_confirmed=True, workspace=WORKSPACE,
                              residency_planner=planner, residency_budget=_established_budget(), ollama_present=True, executable="ollama")

    assert planner.residency_map() == before_map     # no phantom LOADING, nothing evicted
    assert planner.free_vram_mb() == before_free


def test_an_already_resident_model_is_authorized_without_displacing_anything():
    """Re-selecting a model that is already in VRAM displaces nothing, so it must NOT be caught by
    the no-displacement rule (a fail-closed check that refuses the safe case is just a bug)."""
    planner = ResidencyPlanner(6000)
    planner.register_model("qwen3:8b", 5200)
    planner.request_load("qwen3:8b")
    planner.complete_load("qwen3:8b")
    session = authorize_worker_pane(
        _selection(_local_option()), live_auth=_authorized(), governor=SubscriptionGovernor(),
        profile_loader=_loader(), operator_terms_confirmed=True, workspace=WORKSPACE,
        residency_planner=planner, residency_budget=_established_budget(planner.total_vram_mb()),
        ollama_present=True, executable="ollama")
    assert session.chrome.residency == "resident"
    session.teardown()


def test_a_local_session_carries_the_budget_provenance_it_was_authorized_against():
    session = authorize_worker_pane(
        _selection(_local_option()), live_auth=_authorized(), governor=SubscriptionGovernor(),
        profile_loader=_loader(), operator_terms_confirmed=True, workspace=WORKSPACE,
        residency_planner=_planner(), residency_budget=dict(_established_budget(), estimate=True),
        ollama_present=True, executable="ollama")
    assert session.residency_budget["estimate"] is True
    session.teardown()


def test_an_absent_budget_is_a_refusal_not_an_admission_against_an_unknown_total():
    """Was: "recorded as unknown-and-estimated". That was a fail-OPEN — an authorization went out
    against a planner whose total nothing vouched for, disclosed only as `vram_budget_mb: null`
    (spec-audit MAJOR-1, 2026-07-26). A budget nobody established is now a refusal."""
    with pytest.raises(WorkerPaneRefused) as exc:
        authorize_worker_pane(
            _selection(_local_option()), live_auth=_authorized(), governor=SubscriptionGovernor(),
            profile_loader=_loader(), operator_terms_confirmed=True, workspace=WORKSPACE,
            residency_planner=_planner(), ollama_present=True, executable="ollama")
    assert "could not be established" in str(exc.value)
    assert "no VRAM budget provenance supplied with the planner" in str(exc.value)


# ---- the shared selection guard (fail-closed, before any mutation) -----------------------------

@pytest.mark.parametrize("bad,exc_msg", [
    (dict(option=_frontier_option(available=False)), "unavailable"),
    (dict(mode="whatever"), "unknown pane mode"),
    (dict(role="translator"), "not offered"),
    (dict(role="conductor"), "conductor"),
    (dict(node_id=""), "node identity"),
    (dict(profile=""), "permission profile"),
])
def test_selection_refusals_happen_before_any_governor_mutation(bad, exc_msg):
    option = bad.pop("option", _frontier_option(roles=("conductor", "reasoning", "coding")))
    governor = SubscriptionGovernor()
    sel = _selection(option, subscription_ref="sub-claude", **bad)
    with pytest.raises(SpawnRefused) as err:
        authorize_worker_pane(sel, live_auth=_authorized(), governor=governor,
                              profile_loader=_loader(), operator_terms_confirmed=True,
                              workspace=WORKSPACE, cli_present=True)
    assert exc_msg in str(err.value)
    assert governor.status() == {}          # nothing registered, nothing acquired


def test_a_frontier_selection_without_a_subscription_ref_is_refused_uncounted():
    with pytest.raises(WorkerPaneRefused) as err:
        authorize_worker_pane(_selection(_frontier_option()), live_auth=_authorized(),
                              governor=SubscriptionGovernor(), profile_loader=_loader(),
                              operator_terms_confirmed=True, workspace=WORKSPACE, cli_present=True)
    assert "I-X3" in str(err.value)


# ---- frontier: the full live gate chain --------------------------------------------------------

def test_claude_worker_pane_is_interactive_governed_and_counted():
    governor = SubscriptionGovernor()
    ref = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)
    session = authorize_worker_pane(
        _selection(_frontier_option(), subscription_ref=ref), live_auth=_authorized(),
        governor=governor, profile_loader=_loader(), operator_terms_confirmed=True,
        workspace=WORKSPACE, cli_present=True, model="claude-fable-5", executable="claude.EXE")

    assert session.launch["argv"] == ["claude.EXE", "--model", "claude-fable-5"]
    assert session.launch["interactive"] is True and session.launch["one_shot"] is False
    assert "-p" not in session.launch["argv"] and "--print" not in session.launch["argv"]
    assert session.launch["cwd"] == WORKSPACE
    assert session.launch["env_credential_scrubbed"] is True
    assert isinstance(session.launch["env_scrub_names"], list)
    # the badge is the picker option, verbatim (invariant 3)
    assert session.chrome.model_label == "fable-5"
    assert session.chrome.model_slug == "claude-fable-5"
    assert session.chrome.model_verified is False
    assert session.chrome.governed is True and session.chrome.interactive is True
    assert session.chrome.role == "reasoning" and session.chrome.locality == "frontier"
    # counted (I-X3) while it is held
    assert governor.active_count(ref) == 1
    assert session.chrome.subscription == {"ref": ref, "in_use": 1, "allowance": 2}
    assert session.residency_decision is None
    session.teardown()                                   # D-LOOP-1
    assert governor.active_count(ref) == 0


def test_claude_worker_with_a_probed_unavailable_slug_records_the_cli_default_fallback():
    """A slug the CLI has been PROBED to reject must not reach argv (the 17A `.roundtrip` defect:
    a live session that answers every prompt with "there's an issue with the selected model")."""
    ref = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)
    session = authorize_worker_pane(
        _selection(_frontier_option(), subscription_ref=ref), live_auth=_authorized(),
        governor=SubscriptionGovernor(), profile_loader=_loader(), operator_terms_confirmed=True,
        workspace=WORKSPACE, cli_present=True, model_available=False, executable="claude")
    assert session.launch["argv"] == ["claude"]          # CLI default — no invented slug
    assert session.chrome.model_slug is None
    assert session.chrome.is_fallback is True            # never silent (directive §11 15B)
    session.teardown()


def test_codex_worker_pane_is_interactive_read_only_sandboxed_and_workspace_scoped():
    ref = canonical_subscription_ref(CODEX_ADAPTER)
    session = authorize_worker_pane(
        _selection(_frontier_option(CODEX_ADAPTER, slug="gpt-5.5"), subscription_ref=ref),
        live_auth=_authorized(CODEX_ADAPTER), governor=SubscriptionGovernor(),
        profile_loader=_loader(), operator_terms_confirmed=True, workspace=WORKSPACE,
        cli_present=True, executable="codex.CMD")
    argv = session.launch["argv"]
    assert argv[0] == "codex.CMD"
    assert "exec" not in argv                            # interactive TUI, not the one-shot path
    assert argv[1:3] == ["-m", "gpt-5.5"]
    assert "--sandbox" in argv and SANDBOX_READ_ONLY in argv
    assert "--cd" in argv and WORKSPACE in argv
    assert session.launch["one_shot"] is False
    session.teardown()


def test_codex_coding_role_is_refused_without_an_isolated_worktree():
    ref = canonical_subscription_ref(CODEX_ADAPTER)
    with pytest.raises(WorkerPaneRefused) as err:
        authorize_worker_pane(
            _selection(_frontier_option(CODEX_ADAPTER, slug="gpt-5.5"), role="coding",
                       profile="pp-worker-coding", subscription_ref=ref),
            live_auth=_authorized(CODEX_ADAPTER), governor=SubscriptionGovernor(),
            profile_loader=_loader(), operator_terms_confirmed=True, workspace=WORKSPACE,
            cli_present=True)
    assert "worktree" in str(err.value)


@pytest.mark.parametrize("kwargs,exc", [
    # an unauthorized live config is caught by the ROSTER gate first (ProfileViolation wrapping the
    # LiveAuthorizationError) — the whole-roster check runs before the spawn-site re-assertion
    ({"live_auth": LiveAuthorization(authorized=False, providers=frozenset(),
                                     terminals_per_subscription=0, register_row=None,
                                     source="(test)", reason="absent")}, ProfileViolation),
    ({"operator_terms_confirmed": False}, LiveTermsNotConfirmed),
])
def test_frontier_governance_refusals_leave_no_terminal_counted(kwargs, exc):
    governor = SubscriptionGovernor()
    ref = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)
    call = dict(live_auth=_authorized(), governor=governor, profile_loader=_loader(),
                operator_terms_confirmed=True, workspace=WORKSPACE, cli_present=True)
    call.update(kwargs)
    with pytest.raises(exc):
        authorize_worker_pane(_selection(_frontier_option(), subscription_ref=ref), **call)
    assert governor.active_count(ref) == 0


def test_frontier_worker_is_refused_when_the_cli_is_absent():
    ref = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)
    with pytest.raises(ClaudeCliUnavailable) as err:
        authorize_worker_pane(_selection(_frontier_option(), subscription_ref=ref),
                              live_auth=_authorized(), governor=SubscriptionGovernor(),
                              profile_loader=_loader(), operator_terms_confirmed=True,
                              workspace=WORKSPACE, cli_present=False)
    assert "cli" in str(err.value).lower()


def test_the_ix3_allowance_is_enforced_for_worker_panes():
    governor = SubscriptionGovernor()
    ref = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)
    held = [authorize_worker_pane(
        _selection(_frontier_option(), node_id=f"worker-pane-{i}", subscription_ref=ref),
        live_auth=_authorized(), governor=governor, profile_loader=_loader(),
        operator_terms_confirmed=True, workspace=WORKSPACE, cli_present=True) for i in (2, 3)]
    with pytest.raises(SubscriptionLimitExceeded):
        authorize_worker_pane(
            _selection(_frontier_option(), node_id="worker-pane-4", subscription_ref=ref),
            live_auth=_authorized(), governor=governor, profile_loader=_loader(),
            operator_terms_confirmed=True, workspace=WORKSPACE, cli_present=True)
    for s in held:
        s.teardown()
    assert governor.active_count(ref) == 0


# ---- local: residency-governed, never subscription-governed ------------------------------------

def test_local_worker_routes_through_the_residency_planner_and_is_not_subscription_counted():
    governor = SubscriptionGovernor()
    planner = _planner()
    session = authorize_worker_pane(
        _selection(_local_option()), live_auth=_authorized(), governor=governor,
        profile_loader=_loader(), operator_terms_confirmed=True, workspace=WORKSPACE,
        residency_planner=planner, residency_budget=_established_budget(), ollama_present=True, executable="ollama.EXE")
    assert session.launch["argv"] == ["ollama.EXE", "run", "qwen3:8b"]
    assert session.launch["one_shot"] is False
    assert session.chrome.locality == "local"
    assert session.chrome.subscription is None           # invariant 19: local is not I-X3-governed
    assert session.chrome.residency in ("loading", "resident", "queued")
    assert session.residency_decision is not None
    assert governor.status() == {}
    session.teardown()                                   # no-op for a local node


def test_local_worker_without_a_planner_is_refused():
    with pytest.raises(WorkerPaneRefused) as err:
        authorize_worker_pane(_selection(_local_option()), live_auth=_authorized(),
                              governor=SubscriptionGovernor(), profile_loader=_loader(),
                              operator_terms_confirmed=True, workspace=WORKSPACE,
                              ollama_present=True)
    assert "residency" in str(err.value).lower()


def test_local_worker_whose_vram_cannot_be_proven_is_refused():
    planner = _planner(register={"qwen3:8b": 5200})
    with pytest.raises(WorkerPaneRefused) as err:
        authorize_worker_pane(_selection(_local_option("unregistered:70b")),
                              live_auth=_authorized(), governor=SubscriptionGovernor(),
                              profile_loader=_loader(), operator_terms_confirmed=True,
                              workspace=WORKSPACE, residency_planner=planner, residency_budget=_established_budget(), ollama_present=True)
    assert "vram" in str(err.value).lower() or "residency" in str(err.value).lower()


def test_local_worker_is_refused_when_the_ollama_runtime_is_absent():
    with pytest.raises(WorkerPaneRefused) as err:
        authorize_worker_pane(_selection(_local_option()), live_auth=_authorized(),
                              governor=SubscriptionGovernor(), profile_loader=_loader(),
                              operator_terms_confirmed=True, workspace=WORKSPACE,
                              residency_planner=_planner(), residency_budget=_established_budget(), ollama_present=False)
    assert "ollama" in str(err.value).lower()


def test_local_coding_role_is_refused_as_deferred_not_unavailable():
    with pytest.raises(WorkerPaneRefused) as err:
        authorize_worker_pane(_selection(_local_option(), role="coding",
                                         profile="pp-worker-coding"),
                              live_auth=_authorized(), governor=SubscriptionGovernor(),
                              profile_loader=_loader(), operator_terms_confirmed=True,
                              workspace=WORKSPACE, residency_planner=_planner(), residency_budget=_established_budget(),
                              ollama_present=True)
    msg = str(err.value)
    assert "deferred" in msg and "OpenCode" in msg


def test_an_unknown_adapter_is_refused_fail_closed():
    option = _local_option()
    option["adapter"] = "some_new_provider"
    with pytest.raises(WorkerPaneRefused):
        authorize_worker_pane(_selection(option), live_auth=_authorized(),
                              governor=SubscriptionGovernor(), profile_loader=_loader(),
                              operator_terms_confirmed=True, workspace=WORKSPACE,
                              residency_planner=_planner(), residency_budget=_established_budget(), ollama_present=True)


# ---- credential hygiene (§2.2) -----------------------------------------------------------------

def test_the_launch_spec_carries_credential_env_NAMES_only_never_values(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-must-not-appear")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-appear-either")
    ref = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)
    session = authorize_worker_pane(
        _selection(_frontier_option(), subscription_ref=ref), live_auth=_authorized(),
        governor=SubscriptionGovernor(), profile_loader=_loader(), operator_terms_confirmed=True,
        workspace=WORKSPACE, cli_present=True, model="claude-fable-5")
    names = session.launch["env_scrub_names"]
    assert "ANTHROPIC_API_KEY" in names and "OPENAI_API_KEY" in names   # union superset
    assert "sk-must-not-appear" not in repr(session.launch)
    assert "env" not in session.launch
    session.teardown()


# ---- the local argv builder has no bare-binary fallback (spec-audit MINOR-1) --------------------

def test_a_blank_executable_is_refused_rather_than_becoming_a_PATH_search():
    """`exe = executable or "ollama"` was the `resolved or "claude"` shape the `binary_unresolved`
    gate exists to refuse: a blank executable becomes a bare name the shell PATH-searches at spawn,
    so WHAT RUNS is decided after the gate ran — and `ollama` is the very basename the shell's
    allowlist accepts, so nothing downstream would catch it."""
    for blank in ("", "   ", None):
        with pytest.raises(ValueError) as err:
            build_interactive_ollama_command(blank, model="qwen3:8b")
        assert "resolved executable" in str(err.value)
    assert build_interactive_ollama_command("C:\\ol\\ollama.exe", model="qwen3:8b") == [
        "C:\\ol\\ollama.exe", "run", "qwen3:8b"]


# ---- U105: the scrub list is classified over the SHELL's environment too (Phase 17B `.spawn`) ----

def test_a_credential_var_only_the_SHELL_holds_is_still_named_in_the_scrub_list(monkeypatch):
    """U105: the list was measured in the EMITTER's environment and applied to the SHELL's, which is
    sound only while the two match — and 17B itself made divergence reachable (a per-child
    `opts.env`). A var the shell holds and this process does not was therefore never named, so the
    shell never dropped it: a fail-OPEN in the one direction §2.2 cares about."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ref = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)
    session = authorize_worker_pane(
        _selection(_frontier_option(), subscription_ref=ref), live_auth=_authorized(),
        governor=SubscriptionGovernor(), profile_loader=_loader(), operator_terms_confirmed=True,
        workspace=WORKSPACE, cli_present=True, model="claude-fable-5",
        shell_env_names=["ANTHROPIC_API_KEY", "PATH", "Openai_Api_Key"])
    names = session.launch["env_scrub_names"]
    assert "ANTHROPIC_API_KEY" in names
    # Windows preserves the CASE a var was created with while the classifier upper-cases: the shell
    # deletes by EXACT spelling, so the spelling the SHELL holds is the one that has to come back.
    assert "Openai_Api_Key" in names
    assert "PATH" not in names, "a non-credential name must never be scrubbed out of a child env"
    session.teardown()


def test_the_local_locality_gets_the_same_shell_union(monkeypatch):
    """A local pane needs no cloud credential at all, which is exactly why it gets the superset: a
    key left in the child env of a session that has no business seeing it is the same defect."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    session = authorize_worker_pane(
        _selection(_local_option()), live_auth=_authorized(), governor=SubscriptionGovernor(),
        profile_loader=_loader(), operator_terms_confirmed=True, workspace=WORKSPACE,
        residency_planner=_planner(), residency_budget=_established_budget(), ollama_present=True,
        shell_env_names=["ANTHROPIC_API_KEY"])
    assert "ANTHROPIC_API_KEY" in session.launch["env_scrub_names"]
