"""Per-pane model picker data model (OP-7 §12.2 — Phase 15E `.picker`).

Proves the picker offers both live provider adapters (probed model labels) + the operator's
live-enumerated local models with residency state, and — crucially — that it FAILS CLOSED:
an unauthorized frontier provider still appears but greyed with a specific reason (never hidden,
never fabricated). Pure/deterministic."""
from __future__ import annotations

from control_plane.nodes.pane_picker import build_pane_picker
from control_plane.profiles.live_authorization import LiveAuthorization
from scheduler.residency_planner.residency_planner import LOADING, RESIDENT
from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from adapters.frontier.codex import CODEX_ADAPTER


def _authorized(*providers: str) -> LiveAuthorization:
    return LiveAuthorization(
        authorized=True, providers=frozenset(providers), terminals_per_subscription=2,
        register_row="OP-6", source="(test)", reason="test authorization")


def _denied() -> LiveAuthorization:
    return LiveAuthorization.denied("no live-operation config (enforcement-by-absence)")


def _opts_for(picker: dict, provider: str) -> list[dict]:
    return [o for o in picker["options"] if o["provider"] == provider]


def test_both_frontier_providers_offered_when_authorized() -> None:
    live = _authorized(CLAUDE_CODE_ADAPTER, CODEX_ADAPTER)
    picker = build_pane_picker(live, claude_available=True, codex_available=True,
                               codex_authenticated=True)
    anth = _opts_for(picker, CLAUDE_CODE_ADAPTER)
    codex = _opts_for(picker, CODEX_ADAPTER)
    # Opus 4.8 / Fable 5 / CLI default  and  5.5 / 5.5 Sol / CLI default
    assert {o["label"] for o in anth} == {"Opus 4.8", "Fable 5", "CLI default"}
    assert {o["label"] for o in codex} == {"ChatGPT 5.6 Sol", "5.5", "5.5 Sol", "CLI default"}
    assert all(o["available"] for o in anth + codex)
    # both registered providers can conduct, but only exact registered conductor models expose it
    assert any("conductor" in o["roles"] for o in anth)
    assert [o["label"] for o in codex if "conductor" in o["roles"]] == ["ChatGPT 5.6 Sol"]


def test_frontier_slugs_are_unverified_labels_never_fabricated() -> None:
    live = _authorized(CLAUDE_CODE_ADAPTER)
    picker = build_pane_picker(live, claude_available=True)
    for o in _opts_for(picker, CLAUDE_CODE_ADAPTER):
        # operator label carried, verification still False until a live smoke
        assert o["verified"] is False
        # CLI-default option is a recorded fallback with a None slug
        if o["label"] == "CLI default":
            assert o["model_slug"] is None and o["is_fallback"] is True


def test_unauthorized_frontier_is_shown_but_greyed_with_reason() -> None:
    live = _denied()
    picker = build_pane_picker(live, codex_available=True, codex_authenticated=True)
    frontier = _opts_for(picker, CLAUDE_CODE_ADAPTER) + _opts_for(picker, CODEX_ADAPTER)
    assert frontier, "frontier options must still be listed, never hidden"
    for o in frontier:
        assert o["available"] is False
        assert o["unavailable_reason"] and "not authorized" in o["unavailable_reason"]


def test_anthropic_greyed_when_cli_absent_even_if_authorized() -> None:
    # authorization alone is NOT sufficient — the host `claude` CLI must also be present
    # (symmetric with codex; spec-audit MINOR-2). Fail closed to available=False with a reason.
    live = _authorized(CLAUDE_CODE_ADAPTER)
    picker = build_pane_picker(live, claude_available=False)
    anth = _opts_for(picker, CLAUDE_CODE_ADAPTER)
    assert anth and all(o["available"] is False for o in anth)
    assert all("not detected" in o["unavailable_reason"] for o in anth)


def test_codex_unavailable_names_each_missing_condition() -> None:
    live = _authorized(CODEX_ADAPTER)                 # authorized, but CLI absent + unauthenticated
    picker = build_pane_picker(live, codex_available=False, codex_authenticated=False)
    codex = _opts_for(picker, CODEX_ADAPTER)
    for o in codex:
        assert o["available"] is False
        r = o["unavailable_reason"]
        assert "not detected" in r and "not authenticated" in r  # both conditions named


def test_local_models_enumerated_with_residency_state() -> None:
    live = _denied()                                  # frontier off; local needs no auth (§2.4)
    picker = build_pane_picker(
        live,
        ollama_models=["qwen3:8b", "qwen2.5-coder:7b"],
        residency={"qwen3:8b": RESIDENT, "qwen2.5-coder:7b": LOADING},
    )
    local = _opts_for(picker, "ollama_local")
    by = {o["label"]: o for o in local}
    assert set(by) == {"qwen3:8b", "qwen2.5-coder:7b"}
    assert all(o["available"] for o in local)         # local always available, no credential gate
    assert by["qwen3:8b"]["residency"] == RESIDENT
    assert by["qwen2.5-coder:7b"]["residency"] == LOADING
    assert by["qwen2.5-coder:7b"]["model_slug"] == "qwen2.5-coder:7b"
    # roles are the coarse worker menu, UNIFORM for every local model — no capability is inferred
    # from the model name (I-SC1); real fit is descriptor-resolved at `.spawn`.
    for o in local:
        assert o["roles"] == ["reasoning", "coding"]


def test_local_model_without_residency_reads_not_loaded() -> None:
    picker = build_pane_picker(_denied(), ollama_models=["llama3:8b"], residency={})
    (opt,) = _opts_for(picker, "ollama_local")
    assert opt["residency"] == "not_loaded"           # honest default, not fabricated resident


def test_empty_ollama_enumeration_yields_zero_local_options() -> None:
    picker = build_pane_picker(_denied(), ollama_models=[])
    assert _opts_for(picker, "ollama_local") == []
    assert picker["counts"]["local"] == 0             # recorded 0, never a fabricated model


def test_duplicate_ollama_names_deduped() -> None:
    picker = build_pane_picker(_denied(), ollama_models=["m:1", "m:1", "  ", "m:2"])
    local = _opts_for(picker, "ollama_local")
    assert [o["label"] for o in local] == ["m:1", "m:2"]


def test_counts_and_authorization_provenance() -> None:
    live = _authorized(CLAUDE_CODE_ADAPTER)
    picker = build_pane_picker(live, ollama_models=["a:1"], claude_available=True,
                               codex_available=False, codex_authenticated=False)
    c = picker["counts"]
    assert c["frontier"] == 7                          # 3 anthropic + 4 codex
    assert c["local"] == 1
    assert c["total"] == 8
    # only the authorized anthropic set (3) is available; codex (3) + is not
    assert c["available"] == 3 + 1                      # 3 anthropic + 1 local
    assert picker["authorization"]["authorized"] is True
    assert picker["authorization"]["providers"] == [CLAUDE_CODE_ADAPTER]
