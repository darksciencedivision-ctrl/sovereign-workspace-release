"""Operator amendment: one conductor lifecycle, registered OpenAI and Claude adapters."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from adapters.frontier.codex import CODEX_ADAPTER
from control_plane.conductor.registry import (
    ConductorRegistryError,
    load_runtime_conductor_descriptor,
    registered_conductor_models,
    resolve_conductor_descriptor,
)
from control_plane.nodes.pane_picker import build_pane_picker
from control_plane.profiles.live_authorization import LiveAuthorization
from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger
from tools.live.emit_conductor_launch import build_conductor_launch_ticket, build_lease_release


def _auth(*providers: str) -> LiveAuthorization:
    return LiveAuthorization(
        authorized=True, providers=frozenset(providers), terminals_per_subscription=1,
        register_row="OP-12", source="test", reason="operator test authorization")


def test_registry_has_exact_openai_and_existing_anthropic_conductors() -> None:
    rows = {(m.provider_id, m.model_id): m for m in registered_conductor_models()}
    openai = rows[(CODEX_ADAPTER, "gpt-5.6-sol")]
    assert openai.display_name == "ChatGPT 5.6 Sol"
    assert openai.conductor_capable and openai.worker_capable
    assert (CLAUDE_CODE_ADAPTER, "fable-5") in rows


def test_picker_exposes_only_registered_conductor_capable_options_for_conductor_role() -> None:
    picker = build_pane_picker(
        _auth(CODEX_ADAPTER, CLAUDE_CODE_ADAPTER), claude_available=True,
        codex_available=True, codex_authenticated=True)
    conductors = [o for o in picker["options"] if "conductor" in o["roles"]]
    assert any(o["model_slug"] == "gpt-5.6-sol" and o["label"] == "ChatGPT 5.6 Sol"
               for o in conductors)
    assert any(o["provider"] == CLAUDE_CODE_ADAPTER for o in conductors)
    assert all(o["registered"] and o["conductor_capable"] for o in conductors)
    assert not any(o["model_slug"] in {"5.5", "5.5 Sol"} for o in conductors)


def test_unknown_provider_model_combination_fails_closed() -> None:
    with pytest.raises(ConductorRegistryError):
        resolve_conductor_descriptor(CODEX_ADAPTER, "invented-model")
    with pytest.raises(ConductorRegistryError):
        resolve_conductor_descriptor("unknown-provider", "gpt-5.6-sol")


def test_openai_ticket_uses_openai_command_identity_and_only_openai_lease(tmp_path: Path) -> None:
    ledger = TerminalLeaseLedger(tmp_path / "leases.json")
    desc = resolve_conductor_descriptor(CODEX_ADAPTER, "gpt-5.6-sol", workspace=str(tmp_path))
    ticket = build_conductor_launch_ticket(
        holder_pid=12345, session_id="openai-conductor", ledger=ledger,
        live_auth=_auth(CODEX_ADAPTER), descriptor=desc, cli_present=True)
    assert ticket["authorized"] is True
    assert ticket["conductor_descriptor"] == desc.as_dict()
    assert ticket["chrome"]["provider"] == CODEX_ADAPTER
    assert ticket["chrome"]["model_label"] == "ChatGPT 5.6 Sol"
    assert ticket["chrome"]["model_slug"] == "gpt-5.6-sol"
    assert "codex" in ticket["launch"]["argv"][0].lower()
    assert ticket["launch"]["argv"][1:3] == ["-m", "gpt-5.6-sol"]
    assert ["--config", "check_for_update_on_startup=false"] == ticket["launch"]["argv"][-4:-2]
    assert ticket["launch"]["argv"][-2:] == ["--ask-for-approval", "untrusted"]
    assert ticket["lease"]["subscription_ref"] == "sub-openai_codex_cli"
    assert "sub-claude_code" not in ledger.snapshot()
    assert build_lease_release(ticket["lease"]["lease_id"], ledger=ledger)["released"] is True
    assert ledger.snapshot() == {}


def test_anthropic_ticket_uses_same_lifecycle_without_openai_fallback(tmp_path: Path) -> None:
    ledger = TerminalLeaseLedger(tmp_path / "leases.json")
    desc = resolve_conductor_descriptor(CLAUDE_CODE_ADAPTER, "fable-5", workspace=str(tmp_path))
    ticket = build_conductor_launch_ticket(
        holder_pid=12345, session_id="claude-conductor", ledger=ledger,
        live_auth=_auth(CLAUDE_CODE_ADAPTER), descriptor=desc, cli_present=True)
    assert ticket["authorized"] is True
    assert ticket["chrome"]["provider"] == CLAUDE_CODE_ADAPTER
    assert ticket["launch"]["argv"][0].lower().endswith(("claude", "claude.exe", "claude.cmd"))
    assert ticket["lease"]["subscription_ref"] == "sub-claude_code"
    assert "sub-openai_codex_cli" not in ledger.snapshot()
    build_lease_release(ticket["lease"]["lease_id"], ledger=ledger)


class TestTheDefaultSelectionSaysWhereItCameFrom:
    """U331, the compounding half (19.6).

    `config/live_operation.json` is gitignored, so on any clone without the operator's host switch
    `load_runtime_conductor_descriptor` resolves `claude_code`/`fable-5` — the RECORDED operator
    selection (D-COND-03), not a vendor default, which is the distinction invariant 3 turns on. The
    Electron readiness layer then failed that descriptor permanently with a message that read like
    a configuration error. The readiness pin is removed in the same unit; what these tests pin is
    the other half: the descriptor now STATES which of the two it is, so the shell reports the
    difference instead of the operator inferring it from a failure.
    """

    def test_an_absent_preference_file_is_the_recorded_default_and_says_so(
            self, tmp_path: Path) -> None:
        desc = load_runtime_conductor_descriptor(tmp_path / "no-such-live_operation.json")
        assert (desc.provider_id, desc.model_id) == (CLAUDE_CODE_ADAPTER, "fable-5")
        assert desc.selection_source == "recorded_default_selection"
        assert desc.as_dict()["selection_source"] == "recorded_default_selection"

    def test_a_file_without_a_conductor_key_is_also_the_recorded_default(
            self, tmp_path: Path) -> None:
        path = tmp_path / "live_operation.json"
        path.write_text(json.dumps({"authorized": True}), encoding="utf-8")
        assert load_runtime_conductor_descriptor(path).selection_source \
            == "recorded_default_selection"

    def test_a_host_preference_is_reported_as_the_operators_own_selection(
            self, tmp_path: Path) -> None:
        path = tmp_path / "live_operation.json"
        path.write_text(json.dumps(
            {"conductor": {"provider_id": CODEX_ADAPTER, "model_id": "gpt-5.6-sol"}}),
            encoding="utf-8")
        desc = load_runtime_conductor_descriptor(path)
        assert (desc.provider_id, desc.model_id) == (CODEX_ADAPTER, "gpt-5.6-sol")
        assert desc.selection_source == "live_operation_preference"

    def test_an_unreadable_or_unregistered_preference_still_fails_closed(
            self, tmp_path: Path) -> None:
        """Provenance is a label, never a widening: a malformed file and an unregistered pair are
        refused exactly as before, and neither is quietly substituted with the default."""
        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        with pytest.raises(ConductorRegistryError):
            load_runtime_conductor_descriptor(broken)
        unregistered = tmp_path / "unregistered.json"
        unregistered.write_text(json.dumps(
            {"conductor": {"provider_id": "some_other_cli", "model_id": "x"}}), encoding="utf-8")
        with pytest.raises(ConductorRegistryError):
            load_runtime_conductor_descriptor(unregistered)

    def test_a_descriptor_resolved_directly_states_no_provenance_rather_than_guessing(self) -> None:
        assert resolve_conductor_descriptor(CODEX_ADAPTER, "gpt-5.6-sol").selection_source \
            == "unstated"


def test_unavailable_claude_is_honestly_not_selectable() -> None:
    picker = build_pane_picker(
        _auth(CODEX_ADAPTER), claude_available=True,
        codex_available=True, codex_authenticated=True)
    claude = [o for o in picker["options"] if o["provider"] == CLAUDE_CODE_ADAPTER]
    assert claude and all(not o["available"] for o in claude)
    assert all("not authorized" in (o["unavailable_reason"] or "") for o in claude)
