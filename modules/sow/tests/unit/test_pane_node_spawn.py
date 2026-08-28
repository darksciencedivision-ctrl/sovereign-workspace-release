"""Governed node spawn FROM a per-pane picker selection (Phase 15E `.spawn`, OP-7 §12.2/§12.3).

The picker (`.picker`) only OFFERS options; this sub-step turns ONE selected option
(provider × model × role) plus a mode (attended | autonomous) into a governed, supervised
spawn — or a fail-closed refusal. These unit tests prove, without a live call:

  * frontier selections spawn through the REAL supervised path + the I-X3 SubscriptionGovernor
    (allowance=2), and TEAR DOWN releases the count (D-LOOP-1);
  * local selections route through the ResidencyPlanner (invariant 22 — visible residency),
    never through the subscription governor;
  * every fail-closed refusal: a greyed (unavailable) option, an un-offered role (I-SC1), an
    unknown mode, a naked identity (invariant 2/29), a missing residency planner for a local
    model, an unregistered local model, a frontier selection with no subscription;
  * attended and autonomous nodes are BOTH governed through the same supervised path — the mode
    is chrome, never an authority grant (invariant 1);
  * the pane chrome's model badge is carried verbatim from the picker option (no divergent
    re-resolution).
"""
from __future__ import annotations

import pytest

from adapters.coding.opencode.harness import (
    HarnessProbe,
    MockOpenCodeHarness,
    OpenCodeUnavailable,
)
from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER, MockClaudeCliBackend
from adapters.frontier.codex import CODEX_ADAPTER, MockCodexCliBackend
from control_plane.nodes.pane_picker import build_pane_picker
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from node_runtime.supervisor.pane_node_spawn import (
    PaneSelection,
    SpawnRefused,
    spawn_node_from_selection,
)
from node_runtime.supervisor.subscription_governor import (
    SubscriptionGovernor,
    SubscriptionLimitExceeded,
)
from scheduler.residency_planner.residency_planner import ResidencyPlanner


def _authorized(*providers: str) -> LiveAuthorization:
    return LiveAuthorization(
        authorized=True, providers=frozenset(providers), terminals_per_subscription=2,
        register_row="OP-6", source="(test)", reason="test authorization")


def _denied() -> LiveAuthorization:
    return LiveAuthorization.denied("no live-operation config (enforcement-by-absence)")


def _loader() -> ProfileLoader:
    return ProfileLoader(DeploymentProfile("cloud"))


def _option(picker: dict, provider: str, label: str) -> dict:
    for o in picker["options"]:
        if o["provider"] == provider and o["label"] == label:
            return o
    raise AssertionError(f"no option {provider}/{label}")


# ---- frontier: governed spawn + I-X3 + teardown ---------------------------------------------

def test_frontier_claude_selection_spawns_governed_node() -> None:
    live = _authorized(CLAUDE_CODE_ADAPTER)
    picker = build_pane_picker(live, claude_available=True)
    sel = PaneSelection(option=_option(picker, CLAUDE_CODE_ADAPTER, "Opus 4.8"),
                        role="reasoning", mode="autonomous", node_id="claude-a",
                        permission_profile_id="pp-frontier", subscription_ref="claude-sub")
    gov = SubscriptionGovernor()
    spawn = spawn_node_from_selection(
        sel, live=live, governor=gov, profile_loader=_loader(), mcp_client=object(),
        operator_terms_confirmed=True, backend=MockClaudeCliBackend())

    assert spawn.chrome.governed is True
    assert spawn.chrome.locality == "frontier"
    assert spawn.chrome.adapter == CLAUDE_CODE_ADAPTER
    assert spawn.chrome.role == "reasoning" and spawn.chrome.mode == "autonomous"
    assert spawn.chrome.node_state == "ready"
    # subscription n/2 visible in chrome (I-X3, OP-6 allowance)
    assert spawn.chrome.subscription == {"ref": "claude-sub", "in_use": 1, "allowance": 2}
    assert spawn.chrome.residency is None
    assert spawn.handle.capability().adapter == CLAUDE_CODE_ADAPTER
    assert gov.active_count("claude-sub") == 1
    # D-LOOP-1: teardown releases the governed count
    spawn.teardown()
    assert gov.active_count("claude-sub") == 0


def test_frontier_codex_selection_spawns_with_role() -> None:
    live = _authorized(CODEX_ADAPTER)
    picker = build_pane_picker(live, codex_available=True, codex_authenticated=True)
    sel = PaneSelection(option=_option(picker, CODEX_ADAPTER, "5.5"), role="coding",
                        mode="autonomous", node_id="codex-a", permission_profile_id="pp",
                        subscription_ref="codex-sub")
    gov = SubscriptionGovernor()
    spawn = spawn_node_from_selection(
        sel, live=live, governor=gov, profile_loader=_loader(), mcp_client=object(),
        operator_terms_confirmed=True, backend=MockCodexCliBackend())
    assert spawn.chrome.adapter == CODEX_ADAPTER and spawn.chrome.role == "coding"
    assert gov.active_count("codex-sub") == 1
    spawn.teardown()
    assert gov.active_count("codex-sub") == 0


def test_ix3_third_frontier_terminal_refused_through_coordinator() -> None:
    """The existing governed refusal (SubscriptionLimitExceeded) flows straight through the
    coordinator — I-X3 allowance=2 is enforced at the supervised spawn path, not re-implemented."""
    live = _authorized(CLAUDE_CODE_ADAPTER)
    picker = build_pane_picker(live, claude_available=True)
    opt = _option(picker, CLAUDE_CODE_ADAPTER, "Fable 5")
    gov = SubscriptionGovernor()
    loader = _loader()

    def _spawn(node_id: str):
        sel = PaneSelection(option=opt, role="reasoning", mode="autonomous", node_id=node_id,
                            permission_profile_id="pp", subscription_ref="claude-sub")
        return spawn_node_from_selection(sel, live=live, governor=gov, profile_loader=loader,
                                         mcp_client=object(), operator_terms_confirmed=True,
                                         backend=MockClaudeCliBackend())

    _spawn("n1"); _spawn("n2")
    assert gov.active_count("claude-sub") == 2
    with pytest.raises(SubscriptionLimitExceeded):
        _spawn("n3")
    assert gov.active_count("claude-sub") == 2


# ---- fail-closed selection validation --------------------------------------------------------

def test_unavailable_option_refused_fail_closed() -> None:
    """A greyed (unavailable) picker option cannot be spawned — refuse before touching any spawn
    path or the governor (the picker already recorded WHY it is unavailable)."""
    live = _denied()
    picker = build_pane_picker(live, codex_available=True, codex_authenticated=True)
    opt = _option(picker, CLAUDE_CODE_ADAPTER, "Opus 4.8")
    assert opt["available"] is False
    sel = PaneSelection(option=opt, role="reasoning", mode="autonomous", node_id="n1",
                        permission_profile_id="pp", subscription_ref="claude-sub")
    gov = SubscriptionGovernor()
    with pytest.raises(SpawnRefused) as ei:
        spawn_node_from_selection(sel, live=live, governor=gov, profile_loader=_loader(),
                                  mcp_client=object(), operator_terms_confirmed=True,
                                  backend=MockClaudeCliBackend())
    assert "unavailable" in str(ei.value).lower()
    assert gov.active_count("claude-sub") == 0


def test_role_not_offered_refused() -> None:
    live = _authorized(CLAUDE_CODE_ADAPTER)
    picker = build_pane_picker(live, claude_available=True)
    # codex options do NOT offer conductor; claude does not offer "voice"
    sel = PaneSelection(option=_option(picker, CLAUDE_CODE_ADAPTER, "Opus 4.8"), role="voice",
                        mode="autonomous", node_id="n1", permission_profile_id="pp",
                        subscription_ref="claude-sub")
    with pytest.raises(SpawnRefused) as ei:
        spawn_node_from_selection(sel, live=live, governor=SubscriptionGovernor(),
                                  profile_loader=_loader(), mcp_client=object(),
                                  operator_terms_confirmed=True, backend=MockClaudeCliBackend())
    assert "role" in str(ei.value).lower()


def test_conductor_role_deferred_to_conductor_pane_substep() -> None:
    """The picker OFFERS conductor for Anthropic, but the conductor node is born by the dedicated
    conductor-first path (`.conductor-pane`), not this worker-spawn dispatcher — refuse (deferred),
    never build a worker handle under a "conductor" chrome badge."""
    live = _authorized(CLAUDE_CODE_ADAPTER)
    picker = build_pane_picker(live, claude_available=True)
    opt = _option(picker, CLAUDE_CODE_ADAPTER, "Opus 4.8")
    assert "conductor" in opt["roles"]  # the picker really does offer it
    sel = PaneSelection(option=opt, role="conductor", mode="autonomous", node_id="c1",
                        permission_profile_id="pp", subscription_ref="claude-sub")
    gov = SubscriptionGovernor()
    with pytest.raises(SpawnRefused) as ei:
        spawn_node_from_selection(sel, live=live, governor=gov, profile_loader=_loader(),
                                  mcp_client=object(), operator_terms_confirmed=True,
                                  backend=MockClaudeCliBackend())
    assert "conductor" in str(ei.value).lower()
    assert gov.active_count("claude-sub") == 0  # nothing spawned


def test_unknown_mode_refused() -> None:
    live = _authorized(CLAUDE_CODE_ADAPTER)
    picker = build_pane_picker(live, claude_available=True)
    sel = PaneSelection(option=_option(picker, CLAUDE_CODE_ADAPTER, "Opus 4.8"), role="reasoning",
                        mode="spectator", node_id="n1", permission_profile_id="pp",
                        subscription_ref="claude-sub")
    with pytest.raises(SpawnRefused) as ei:
        spawn_node_from_selection(sel, live=live, governor=SubscriptionGovernor(),
                                  profile_loader=_loader(), mcp_client=object(),
                                  operator_terms_confirmed=True, backend=MockClaudeCliBackend())
    assert "mode" in str(ei.value).lower()


@pytest.mark.parametrize("node_id,profile", [("", "pp"), ("n1", "")])
def test_naked_session_refused(node_id: str, profile: str) -> None:
    """No node identity OR no supervisor-issued permission profile ⇒ refuse (invariant 2/29 — no
    naked session), before any spawn path."""
    live = _authorized(CLAUDE_CODE_ADAPTER)
    picker = build_pane_picker(live, claude_available=True)
    sel = PaneSelection(option=_option(picker, CLAUDE_CODE_ADAPTER, "Opus 4.8"), role="reasoning",
                        mode="autonomous", node_id=node_id, permission_profile_id=profile,
                        subscription_ref="claude-sub")
    with pytest.raises(SpawnRefused):
        spawn_node_from_selection(sel, live=live, governor=SubscriptionGovernor(),
                                  profile_loader=_loader(), mcp_client=object(),
                                  operator_terms_confirmed=True, backend=MockClaudeCliBackend())


def test_frontier_missing_subscription_ref_refused() -> None:
    """A frontier (subscription-backed) selection with no subscription_ref cannot be governed by
    I-X3 — refuse fail-closed rather than spawn an uncounted terminal."""
    live = _authorized(CLAUDE_CODE_ADAPTER)
    picker = build_pane_picker(live, claude_available=True)
    sel = PaneSelection(option=_option(picker, CLAUDE_CODE_ADAPTER, "Opus 4.8"), role="reasoning",
                        mode="autonomous", node_id="n1", permission_profile_id="pp",
                        subscription_ref=None)
    with pytest.raises(SpawnRefused) as ei:
        spawn_node_from_selection(sel, live=live, governor=SubscriptionGovernor(),
                                  profile_loader=_loader(), mcp_client=object(),
                                  operator_terms_confirmed=True, backend=MockClaudeCliBackend())
    assert "subscription" in str(ei.value).lower()


# ---- attended vs autonomous: both governed, no extra authority (invariant 1) -----------------

def test_attended_and_autonomous_both_governed_same_authority() -> None:
    live = _authorized(CLAUDE_CODE_ADAPTER)
    picker = build_pane_picker(live, claude_available=True)
    opt = _option(picker, CLAUDE_CODE_ADAPTER, "Opus 4.8")
    gov = SubscriptionGovernor()
    loader = _loader()

    def _spawn(node_id: str, mode: str):
        sel = PaneSelection(option=opt, role="reasoning", mode=mode, node_id=node_id,
                            permission_profile_id="pp-shared", subscription_ref="claude-sub")
        return spawn_node_from_selection(sel, live=live, governor=gov, profile_loader=loader,
                                         mcp_client=object(), operator_terms_confirmed=True,
                                         backend=MockClaudeCliBackend())

    attended = _spawn("attended-node", "attended")
    autonomous = _spawn("autonomous-node", "autonomous")
    # distinguished ONLY in chrome (OP-7 §12.3)
    assert attended.chrome.mode == "attended" and autonomous.chrome.mode == "autonomous"
    # same supervised path, same permission profile — the mode grants NO extra authority (inv 1)
    assert attended.handle.context.permission_profile_id == "pp-shared"
    assert autonomous.handle.context.permission_profile_id == "pp-shared"
    assert attended.handle.context.spawned_by_supervisor is True
    assert attended.chrome.governed is autonomous.chrome.governed is True
    attended.teardown(); autonomous.teardown()


# ---- local: residency planner routing (invariant 22) -----------------------------------------

def _local_picker(models: list[str], planner: ResidencyPlanner) -> dict:
    return build_pane_picker(_denied(), ollama_models=models, residency=planner.residency_map())


def test_local_selection_routes_through_residency_planner() -> None:
    planner = ResidencyPlanner(total_vram_mb=12000)
    planner.register_model("llama3:8b", 6000)
    picker = _local_picker(["llama3:8b"], planner)
    sel = PaneSelection(option=_option(picker, "ollama_local", "llama3:8b"), role="reasoning",
                        mode="autonomous", node_id="local-a", permission_profile_id="pp-local")
    gov = SubscriptionGovernor()
    spawn = spawn_node_from_selection(sel, live=_denied(), governor=gov, profile_loader=_loader(),
                                      mcp_client=object(), residency_planner=planner)
    assert spawn.chrome.locality == "local"
    assert spawn.chrome.subscription is None            # local is NOT subscription-governed
    assert spawn.chrome.residency == "loading"          # request_load scheduled it into VRAM
    assert spawn.chrome.node_state == "loading"
    assert spawn.residency_decision["scheduled"] is True
    assert planner.residency_of("llama3:8b") == "loading"
    assert gov.status() == {}                           # governor never touched for a local model
    assert spawn.handle.context.spawned_by_supervisor is True
    spawn.teardown()                                    # no-op for local, must not raise


def test_local_selection_queued_when_vram_blocked_is_still_governed_and_visible() -> None:
    planner = ResidencyPlanner(total_vram_mb=10000)
    planner.register_model("big-a", 7000)
    planner.register_model("big-b", 7000)
    planner.request_load("big-a"); planner.complete_load("big-a"); planner.mark_generating("big-a")
    picker = _local_picker(["big-a", "big-b"], planner)
    sel = PaneSelection(option=_option(picker, "ollama_local", "big-b"), role="reasoning",
                        mode="autonomous", node_id="local-b", permission_profile_id="pp-local")
    spawn = spawn_node_from_selection(sel, live=_denied(), governor=SubscriptionGovernor(),
                                      profile_loader=_loader(), mcp_client=object(),
                                      residency_planner=planner)
    # blocked behind a generating model — QUEUED (never mid-generation eviction), visible in chrome
    assert spawn.residency_decision["scheduled"] is False
    assert spawn.chrome.residency == "queued"
    assert spawn.chrome.node_state == "queued_for_vram"
    assert spawn.chrome.governed is True                # a queued node is still a governed spawn


def test_local_missing_residency_planner_refused() -> None:
    """A local selection MUST route through the residency planner (OP-7 §12.2) — refuse if absent."""
    picker = build_pane_picker(_denied(), ollama_models=["m1"])
    sel = PaneSelection(option=_option(picker, "ollama_local", "m1"), role="reasoning",
                        mode="autonomous", node_id="local-a", permission_profile_id="pp-local")
    with pytest.raises(SpawnRefused) as ei:
        spawn_node_from_selection(sel, live=_denied(), governor=SubscriptionGovernor(),
                                  profile_loader=_loader(), mcp_client=object(),
                                  residency_planner=None)
    assert "residency" in str(ei.value).lower()


def test_local_unregistered_model_refused_fail_closed() -> None:
    """Planner present but the model has no known footprint ⇒ can't prove it fits VRAM ⇒ refuse."""
    planner = ResidencyPlanner(total_vram_mb=12000)  # nothing registered
    picker = build_pane_picker(_denied(), ollama_models=["ghost:70b"])
    sel = PaneSelection(option=_option(picker, "ollama_local", "ghost:70b"), role="reasoning",
                        mode="autonomous", node_id="local-a", permission_profile_id="pp-local")
    with pytest.raises(SpawnRefused) as ei:
        spawn_node_from_selection(sel, live=_denied(), governor=SubscriptionGovernor(),
                                  profile_loader=_loader(), mcp_client=object(),
                                  residency_planner=planner)
    assert "residency" in str(ei.value).lower() or "vram" in str(ei.value).lower()


def test_local_coding_selection_spawns_opencode_harness() -> None:
    planner = ResidencyPlanner(total_vram_mb=12000)
    planner.register_model("qwen2.5-coder:7b", 6000)
    picker = _local_picker(["qwen2.5-coder:7b"], planner)
    sel = PaneSelection(option=_option(picker, "ollama_local", "qwen2.5-coder:7b"), role="coding",
                        mode="autonomous", node_id="coder-a", permission_profile_id="pp-local")
    probe = HarnessProbe(present=True, version="0.99.0-mock", version_tuple=(0, 99, 0),
                         meets_minimum=True, executable="opencode",
                         coder_model="ollama/qwen2.5-coder:7b", detail="ok")
    spawn = spawn_node_from_selection(
        sel, live=_denied(), governor=SubscriptionGovernor(), profile_loader=_loader(),
        mcp_client=object(), residency_planner=planner, workspace_root="/tmp/wt",
        opencode_harness=MockOpenCodeHarness(), opencode_probe=probe)
    assert spawn.chrome.role == "coding" and spawn.chrome.locality == "local"
    assert spawn.chrome.residency == "loading"
    # the handle is the supervised OpenCode harness, proof of no naked session (invariant 2)
    assert spawn.handle.context.spawned_by_supervisor is True
    assert spawn.handle.probe.coder_model == "ollama/qwen2.5-coder:7b"


def test_local_coding_harness_gate_failure_leaks_no_vram_reservation() -> None:
    """MINOR-1 regression: request_load MUTATES residency (reserves VRAM, can flag idle models for
    eviction) and the planner has NO cancel primitive. If the coding-harness gate refuses AFTER a
    reservation, a phantom LOADING entry would leak (contrary to invariant 22 'residency is
    scheduled, visible'). The handle is built BEFORE request_load, so a harness refusal leaves the
    planner byte-untouched."""
    planner = ResidencyPlanner(total_vram_mb=12000)
    planner.register_model("qwen2.5-coder:7b", 6000)
    assert planner.residency_of("qwen2.5-coder:7b") == "not_loaded"
    picker = _local_picker(["qwen2.5-coder:7b"], planner)
    sel = PaneSelection(option=_option(picker, "ollama_local", "qwen2.5-coder:7b"), role="coding",
                        mode="autonomous", node_id="coder-a", permission_profile_id="pp-local")
    # a probe that fails the presence gate ⇒ spawn_opencode_harness raises OpenCodeUnavailable
    absent = HarnessProbe(present=False, version=None, version_tuple=None, meets_minimum=False,
                          executable=None, coder_model=None, detail="absent (test)")
    with pytest.raises(OpenCodeUnavailable):
        spawn_node_from_selection(
            sel, live=_denied(), governor=SubscriptionGovernor(), profile_loader=_loader(),
            mcp_client=object(), residency_planner=planner, workspace_root="/tmp/wt",
            opencode_harness=MockOpenCodeHarness(), opencode_probe=absent)
    # no VRAM reserved: the model is still not_loaded and zero VRAM is in use (no leaked reservation)
    assert planner.residency_of("qwen2.5-coder:7b") == "not_loaded"
    assert planner.used_vram_mb() == 0


# ---- chrome fidelity + teardown idempotence --------------------------------------------------

def test_chrome_model_badge_carried_verbatim_from_picker_option() -> None:
    live = _authorized(CLAUDE_CODE_ADAPTER)
    picker = build_pane_picker(live, claude_available=True)
    opt = _option(picker, CLAUDE_CODE_ADAPTER, "CLI default")
    sel = PaneSelection(option=opt, role="reasoning", mode="autonomous", node_id="c1",
                        permission_profile_id="pp", subscription_ref="claude-sub")
    spawn = spawn_node_from_selection(sel, live=live, governor=SubscriptionGovernor(),
                                      profile_loader=_loader(), mcp_client=object(),
                                      operator_terms_confirmed=True, backend=MockClaudeCliBackend())
    # the badge is the picker's own recorded values — no divergent re-resolution
    assert spawn.chrome.model_label == opt["label"]
    assert spawn.chrome.model_slug == opt["model_slug"]
    assert spawn.chrome.model_verified == opt["verified"]
    spawn.teardown()


def test_teardown_is_idempotent() -> None:
    live = _authorized(CLAUDE_CODE_ADAPTER)
    picker = build_pane_picker(live, claude_available=True)
    sel = PaneSelection(option=_option(picker, CLAUDE_CODE_ADAPTER, "Opus 4.8"), role="reasoning",
                        mode="autonomous", node_id="n1", permission_profile_id="pp",
                        subscription_ref="claude-sub")
    gov = SubscriptionGovernor()
    spawn = spawn_node_from_selection(sel, live=live, governor=gov, profile_loader=_loader(),
                                      mcp_client=object(), operator_terms_confirmed=True,
                                      backend=MockClaudeCliBackend())
    spawn.teardown(); spawn.teardown()  # second call must not raise or wedge the count
    assert gov.active_count("claude-sub") == 0
