"""The picker renders the operator's 8B ceiling honestly (LOCAL-01 F-1, ENTRY 017 + S-17/S-19).

Measured at the parent seal `8d9f5d24`, live, before this change:

    qwen3:8b         offered available:true  -> ticket AUTHORIZED
    phi4:14b         offered available:true  -> ticket AUTHORIZED     <- breaks the ceiling
    deepseek-r1:70b  offered available:true  -> ticket refused@vram_admission

The third row is the S-17 defect in its clearest form: the picker rendered a control the product
would not perform, and the operator only found out after choosing. The second is worse — a 14.7B
model on an 8 GB card was authorized to spawn.

These tests pin the display half. `tests/unit/test_local_model_ceiling.py` pins the decision, and
the authorization half agrees because `emit_worker_launch`'s `selection_offered` guard reads the
same `available` flag the operator saw.
"""
from __future__ import annotations

from control_plane.nodes.pane_picker import _local_options, build_pane_picker
from control_plane.profiles.live_authorization import LiveAuthorization

CEILING_TEXT = "above the operator's 8B ceiling (ENTRY 017)"
REASONS = {
    "phi4:14b": f"phi4:14b has 14.7B parameters, {CEILING_TEXT}.",
    "deepseek-r1:70b": f"deepseek-r1:70b has 70.6B parameters, {CEILING_TEXT}.",
}
MODELS = ["qwen3:8b", "phi4:14b", "deepseek-r1:70b", "sam860/dolphin3-llama3.2:3b"]


def _by_label(options):
    return {o["label"]: o for o in options}


class TestOverCeilingModelsAreGreyedNotHidden:
    def test_every_installed_model_is_still_listed(self):
        """ENTRY 017: over-ceiling models are "excluded from selection with a stated reason, not
        silently hidden". Hiding them would leave the operator wondering where a model he knows he
        installed went — the N-22 lesson."""
        options = _local_options(MODELS, None, None, REASONS)
        assert set(_by_label(options)) == set(MODELS)

    def test_only_models_within_the_ceiling_are_selectable(self):
        options = _by_label(_local_options(MODELS, None, None, REASONS))
        assert options["qwen3:8b"]["available"] is True
        assert options["sam860/dolphin3-llama3.2:3b"]["available"] is True
        assert options["phi4:14b"]["available"] is False
        assert options["deepseek-r1:70b"]["available"] is False

    def test_every_refused_model_carries_the_reason_the_operator_reads(self):
        options = _by_label(_local_options(MODELS, None, None, REASONS))
        for tag in ("phi4:14b", "deepseek-r1:70b"):
            assert options[tag]["unavailable_reason"] == REASONS[tag]
            assert CEILING_TEXT in options[tag]["unavailable_reason"]

    def test_no_greyed_option_is_ever_left_without_a_reason(self):
        """The silent-gap guard. A greyed control with no explanation is the blank-panel defect
        this program has closed three times in other places."""
        for opt in _local_options(MODELS, None, None, REASONS):
            if not opt["available"]:
                assert opt["unavailable_reason"], f"{opt['label']} greyed with no reason"

    def test_an_admitted_model_carries_no_reason(self):
        options = _by_label(_local_options(MODELS, None, None, REASONS))
        assert options["qwen3:8b"]["unavailable_reason"] is None


class TestTheTwoGatesCompose:
    def test_the_host_wide_vram_refusal_wins_over_the_per_model_ceiling(self):
        """When no local pane can run at all, that is the fact the operator needs — telling him a
        model is too large implies a smaller one would work, and none would."""
        host_reason = ("no local pane can be authorized: this host's VRAM admission budget could "
                       "not be established")
        options = _by_label(_local_options(MODELS, None, host_reason, REASONS))
        assert [o["available"] for o in options.values()] == [False] * len(MODELS)
        for opt in options.values():
            assert opt["unavailable_reason"] == host_reason

    def test_with_no_ceiling_map_every_enumerated_model_is_offered(self):
        """Back-compat: the parameter is optional and its absence changes nothing, so callers that
        do not classify (tests, older drivers) behave exactly as before."""
        options = _local_options(MODELS, None, None)
        assert all(o["available"] for o in options)

    def test_ceiling_reasons_for_models_that_are_not_installed_are_ignored(self):
        options = _local_options(["qwen3:8b"], None, None,
                                 {"phi4:14b": "not installed here"})
        assert len(options) == 1 and options[0]["available"] is True


class TestTheWholePickerStaysAgnostic:
    def _picker(self):
        live = LiveAuthorization.denied(
            "no live-operation config (enforcement-by-absence)")
        return build_pane_picker(live, ollama_models=MODELS, residency=None,
                                 local_ceiling_reasons=REASONS)

    def test_counts_report_the_ceiling_honestly(self):
        picker = self._picker()
        assert picker["counts"]["local"] == len(MODELS)
        local = [o for o in picker["options"] if o["provider"] == "ollama_local"]
        assert sum(1 for o in local if o["available"]) == 2

    def test_frontier_rows_remain_visible_and_honestly_unavailable(self):
        """S-20. Frontier is DENIED today, and its entries are never removed — they are shown and
        marked unavailable. A picker that dropped them would hide the operator's own switch."""
        picker = self._picker()
        providers = {g["provider"] for g in picker["providers"]}
        assert {"claude_code", "openai_codex_cli", "ollama_local"} <= providers
        frontier = [o for o in picker["options"] if o["provider"] != "ollama_local"]
        assert frontier, "frontier options must still be rendered"
        assert all(o["available"] is False for o in frontier)

    def test_local_is_not_gated_behind_the_frontier_switch(self):
        """S-20's core rule, and the one the live gate breaks elsewhere (LOCAL-01 D-4): with
        `live_operation.json` absent, frontier is refused and local is still offered."""
        picker = self._picker()
        assert picker["authorization"]["authorized"] is False
        local = [o for o in picker["options"] if o["provider"] == "ollama_local"]
        assert any(o["available"] for o in local)
