"""THE CONDUCTOR SEAT IS AGNOSTIC (LOCAL-01 F-3 · ENTRY 018).

The operator, verbatim: *"the conductor seat is agnostic. It needs to have the local library
anyways. It's not frontier only. That would defeat the whole purpose of the system."*

Measured at the parent seal `8d9f5d24`, five things stood between the Conductor and a local model,
and each has a test here:

  1. `CONDUCTOR_MODEL_REGISTRY` held three rows, all frontier, so `resolve_conductor_descriptor`
     failed closed on every local model.
  2. `provider_commands._COMMANDS` mapped two frontier adapters, so `commands_for("ollama_local")`
     raised `ConductorProviderUnavailable`.
  3. `spawn_conductor_pane` routed EVERY conductor through the frontier gate chain and required a
     `subscription_ref` — and `assert_provider_live("ollama_local")` was measured REFUSING, which is
     the S-20 violation exactly ("local is never gated behind a frontier switch").
  4. `load_runtime_conductor_descriptor` resolved `claude_code/fable-5` whenever
     `live_operation.json` was absent — its permanent state under OD-31.
  5. `select_conductor` persisted the operator's choice INTO `live_operation.json`, so choosing a
     free local model required the spend-authorization file to exist.

Nothing here creates `live_operation.json`, and every test asserts the frontier refusal is intact.
"""
from __future__ import annotations

import json

import pytest

from adapters.conductor.provider_commands import (
    ConductorProviderUnavailable,
    commands_for,
)
from adapters.local.ollama_session import OLLAMA_LOCAL_ADAPTER
from control_plane.conductor.registry import (
    ConductorRegistryError,
    registered_conductor_models,
    resolve_conductor_descriptor,
)
from control_plane.conductor.selection import ConductorSelection
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from node_runtime.supervisor.conductor_pane_spawn import spawn_conductor_pane
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor


class _Verdict:
    """The shape `adapters.local.model_ceiling` returns, reduced to what the registry reads."""

    def __init__(self, name, admitted=True):
        self.name = name
        self.admitted = admitted


ADMITTED = [_Verdict("qwen3:8b"), _Verdict("dolphin3:8b"),
            _Verdict("phi4:14b", admitted=False)]   # over the ceiling — must NOT become a seat

DENIED = LiveAuthorization.denied("no live-operation config (enforcement-by-absence)")


def _local_selection(model="qwen3:8b"):
    return ConductorSelection(model=model, reason="operator_selected",
                              since="2026-08-30T00:00:00+00:00", adapter=OLLAMA_LOCAL_ADAPTER,
                              directive_version="v2.4")


class TestTheRegistryOffersTheLocalLibrary:
    def test_local_models_are_conductor_capable_seats(self):
        seats = registered_conductor_models(ADMITTED)
        local = [s for s in seats if s.locality == "local"]
        assert {s.model_id for s in local} == {"qwen3:8b", "dolphin3:8b"}
        assert all(s.conductor_capable for s in local)

    def test_a_model_over_the_ceiling_is_never_a_conductor_seat(self):
        """The Conductor reads the SAME ceiling verdicts the picker does (S-20). A model the picker
        greys must not be reachable as a conductor through a second, laxer path."""
        seats = registered_conductor_models(ADMITTED)
        assert "phi4:14b" not in {s.model_id for s in seats}

    def test_the_frontier_seats_are_still_registered(self):
        """S-20: frontier entries are never removed. They stay registered and are refused later, by
        the live gate, which is where the refusal belongs."""
        seats = registered_conductor_models(ADMITTED)
        frontier = {(s.provider_id, s.model_id) for s in seats if s.locality == "frontier"}
        assert ("claude_code", "fable-5") in frontier
        assert ("openai_codex_cli", "gpt-5.6-sol") in frontier

    def test_a_local_descriptor_carries_no_subscription(self):
        """Invariant 19. Minting `sub-ollama_local` would open an I-X3 bucket for a resource with no
        allowance to spend, and the always-visible n/2 bar would count a terminal nobody pays for."""
        d = resolve_conductor_descriptor(OLLAMA_LOCAL_ADAPTER, "qwen3:8b", local_verdicts=ADMITTED)
        assert d.locality == "local"
        assert d.subscription_ref == ""
        assert d.registered is True and d.conductor_capable is True

    def test_an_uninstalled_local_model_still_fails_closed(self):
        with pytest.raises(ConductorRegistryError):
            resolve_conductor_descriptor(OLLAMA_LOCAL_ADAPTER, "not-installed:70b",
                                         local_verdicts=ADMITTED)

    def test_no_local_seats_when_the_daemon_gives_nothing(self):
        """An unreachable daemon means no local conductor seats — reported as absence, not raised."""
        seats = registered_conductor_models([])
        assert all(s.locality == "frontier" for s in seats)


class TestTheCommandAdapter:
    def test_a_local_conductor_builds_an_interactive_ollama_session(self):
        cmds = commands_for(OLLAMA_LOCAL_ADAPTER)
        argv = cmds.build_command("C:/bin/ollama.exe", "qwen3:8b", "/workspace")
        assert argv == ["C:/bin/ollama.exe", "run", "qwen3:8b"]

    def test_it_is_never_a_one_shot(self):
        """`ollama run <tag> <prompt>` is the one-shot form. A conductor pane is a session the
        operator types into, so no prompt may ever be appended."""
        argv = commands_for(OLLAMA_LOCAL_ADAPTER).build_command("C:/bin/ollama.exe", "qwen3:8b", "/w")
        assert len([a for a in argv if not a.startswith("-")]) == 3

    def test_a_missing_tag_is_refused_rather_than_defaulted(self):
        """The frontier resolvers may fall back to the CLI's own default model and RECORD it.
        `ollama run` has no default, so a missing tag must fail closed instead of launching
        something the operator did not choose."""
        cmds = commands_for(OLLAMA_LOCAL_ADAPTER)
        slug, why = cmds.resolve_model(None)
        assert slug is None and "no default model" in why
        with pytest.raises(ConductorProviderUnavailable):
            cmds.build_command("C:/bin/ollama.exe", None, "/w")

    def test_the_local_capability_is_the_mirror_of_the_frontier_one(self):
        cap = commands_for(OLLAMA_LOCAL_ADAPTER).capability()
        assert cap.locality == "local"
        assert cap.node_class == "conductor"        # the seat is the role, not the vendor
        assert cap.subscription_backed is False
        assert cap.requires_network is False
        assert cap.local_runtime is True
        assert cap.offline_profile_eligible is True


class TestTheGovernedSpawnAdmitsALocalConductor:
    def _spawn(self, profile="cloud", **kw):
        desc = resolve_conductor_descriptor(OLLAMA_LOCAL_ADAPTER, "qwen3:8b",
                                            local_verdicts=ADMITTED)
        args = dict(
            mcp_client=None, governor=SubscriptionGovernor(), subscription_ref="",
            node_id="conductor-pane-1", permission_profile_id="pp-conductor-pane",
            live_auth=DENIED, profile_loader=ProfileLoader(DeploymentProfile(profile)),
            operator_terms_confirmed=False, selection=_local_selection(), descriptor=desc,
            cli_present=True, executable="C:/bin/ollama.exe",
            launcher=lambda **_kw: type("H", (), {"close": lambda self: None})())
        args.update(kw)
        return spawn_conductor_pane(**args)

    def test_it_spawns_with_live_operation_absent_and_terms_unconfirmed(self):
        """The whole of F-3 in one assertion. `live_auth` is DENIED and `operator_terms_confirmed`
        is False — the two gates that refuse every frontier conductor — and a local one still runs,
        because neither question applies to a model that costs nothing."""
        session = self._spawn()
        assert session.launched is True
        assert session.launch["argv"][1:] == ["run", "qwen3:8b"]
        assert session.launch["one_shot"] is False and session.launch["interactive"] is True

    def test_it_holds_no_subscription_terminal(self):
        session = self._spawn()
        assert session.chrome.subscription is None
        assert session.launch["subscription_governed"] is False
        assert session.chrome.locality == "local"

    def test_teardown_releases_nothing_and_does_not_raise(self):
        """A local pane holds no I-X3 count, so `teardown` has nothing to hand back. That is
        correct rather than a missing step, and it must not raise."""
        session = self._spawn()
        session.teardown()

    def test_the_credential_scrub_still_runs(self):
        """A local model needs no credential, which is exactly why this matters: the child must not
        inherit the operator's frontier keys merely because nothing here would use them."""
        assert self._spawn().launch["env_credential_scrubbed"] is True

    def test_the_deployment_profile_gate_is_kept(self):
        """`check_eligible` asks a LOCALITY question (invariant 20), not a spend question, so it
        still applies — and a local model passes it on the air-gapped profile, which is the point."""
        assert self._spawn(profile="offline_airgapped").launched is True

    def test_an_absent_runtime_is_refused_with_a_local_reason(self):
        with pytest.raises(ConductorProviderUnavailable) as exc:
            self._spawn(cli_present=False, launcher=None)
        assert "ollama" in str(exc.value)


class TestTheFrontierRefusalIsUNCHANGED:
    """S-18. F-3 must not weaken the refusal that keeps frontier providers DENIED — the live gate
    is relied upon, never removed."""

    def test_a_frontier_conductor_is_still_refused_with_live_operation_absent(self):
        desc = resolve_conductor_descriptor("claude_code", "fable-5", local_verdicts=ADMITTED)
        with pytest.raises(Exception) as exc:
            spawn_conductor_pane(
                mcp_client=None, governor=SubscriptionGovernor(),
                subscription_ref=desc.subscription_ref, node_id="conductor-pane-1",
                permission_profile_id="pp-conductor-pane", live_auth=DENIED,
                profile_loader=ProfileLoader(DeploymentProfile("cloud")),
                operator_terms_confirmed=True, selection=ConductorSelection(
                    model="fable-5", reason="operator_selected",
                    since="2026-07-19T00:00:00+00:00", adapter="claude_code",
                    directive_version="v2.4"),
                descriptor=desc, cli_present=True,
                launcher=lambda **_kw: object())
        assert "live operation not authorized" in str(exc.value)

    def test_a_frontier_conductor_still_requires_a_subscription_ref(self):
        desc = resolve_conductor_descriptor("claude_code", "fable-5", local_verdicts=ADMITTED)
        assert desc.subscription_ref == "sub-claude_code"


class TestTheSelectionStore:
    def test_a_local_selection_never_touches_live_operation_json(self, tmp_path, monkeypatch):
        """The defect this closes: `select()` wrote EVERY selection into `config/live_operation.json`
        and read it first, so choosing a free local model required the spend-authorization file to
        exist — and under OD-31 it is deliberately absent. A builder must never create it (S-18)."""
        import control_plane.conductor.registry as registry
        import tools.live.select_conductor as sc

        # `select` resolves the seat through the HOST enumeration. Inject it: otherwise this passed
        # only while the operator's Ollama daemon was serving qwen3:8b.
        real = registry._local_conductor_registrations
        monkeypatch.setattr(registry, "_local_conductor_registrations",
                            lambda verdicts=None: real(ADMITTED if verdicts is None else verdicts))
        store = tmp_path / ".runtime" / "conductor-selection.json"
        monkeypatch.setattr(sc, "LOCAL_CONDUCTOR_SELECTION_PATH", store)
        live_cfg = tmp_path / "live_operation.json"
        monkeypatch.setattr(sc, "CONFIG", live_cfg)

        res = sc.select({"provider_id": OLLAMA_LOCAL_ADAPTER, "adapter_id": OLLAMA_LOCAL_ADAPTER,
                         "model_id": "qwen3:8b", "display_name": "qwen3:8b",
                         "permission_profile_id": "pp-conductor-pane"})
        assert res["ok"] is True
        assert store.exists(), "the local selection must be remembered in the gitignored lane"
        assert not live_cfg.exists(), "live_operation.json must NOT be created by a local selection"
        assert json.loads(store.read_text(encoding="utf-8"))["conductor"]["model_id"] == "qwen3:8b"
