"""OpenCode as a pickable coding slot (EPC-04 W-2).

The operator's ask was specific: *"I want open code, the harness, an available slot to be picked in
one of the terminals, and then I'll load a model into it."* These tests hold the picker to that
sentence, and to the two rules the picker already had — greyed-with-reason rather than hidden, and
never an option the spawn path would refuse for a reason the picker could have shown.
"""
from __future__ import annotations

import pytest

from control_plane.nodes import pane_picker as pp
from control_plane.profiles.live_authorization import LiveAuthorization

MODELS = ["qwen3:8b", "qwen2.5-coder:3b", "llama3.2:3b", "devstral:24b"]


def _picker(**kw):
    kw.setdefault("ollama_models", list(MODELS))
    kw.setdefault("opencode_present", True)
    live = LiveAuthorization.denied("no live-operation config (enforcement-by-absence)")
    return pp.build_pane_picker(live, **kw)


def _opencode(picker):
    return [o for o in picker["options"] if o["provider"] == "opencode_local"]


def test_opencode_is_offered_as_a_selectable_option_with_its_local_models():
    """W-2's done-when: 'the picker offers OpenCode as a selectable option, with the local models
    it can drive.'"""
    options = _opencode(_picker())
    assert options, "OpenCode is not in the picker at all"
    assert {o["model_slug"] for o in options} == {"qwen2.5-coder:3b", "devstral:24b"}
    assert all(o["available"] for o in options)
    assert all(o["label"].startswith("OpenCode") for o in options)


def test_opencode_is_its_own_provider_group_not_a_row_inside_the_ollama_one():
    picker = _picker()
    groups = {g["provider"]: g for g in picker["providers"]}
    assert "opencode_local" in groups
    assert _opencode(picker) == groups["opencode_local"]["options"]
    # and the bare Ollama group is untouched by it
    assert all(o["provider"] == "ollama_local" for o in groups["ollama_local"]["options"])


def test_a_general_chat_model_is_not_offered_as_a_coding_harness():
    """Narrowing the menu is a USABILITY decision, and it is stated as one: it gates nothing."""
    assert "llama3.2:3b" not in {o["model_slug"] for o in _opencode(_picker())}


def test_opencode_options_are_greyed_with_a_reason_when_the_cli_is_absent_never_hidden():
    """S-19 / ENTRY 017: 'excluded from selection with a stated reason, not silently hidden'."""
    options = _opencode(_picker(opencode_present=False))
    assert options, "absent must GREY the options, not remove them"
    assert not any(o["available"] for o in options)
    for opt in options:
        assert "opencode" in opt["unavailable_reason"].lower()


def test_the_host_vram_refusal_greys_opencode_for_the_same_reason_as_every_local_option():
    """It is the same weights on the same card; a coding pane gets no exemption from invariant 22."""
    reason = "no VRAM budget could be established on this host"
    options = _opencode(_picker(local_unavailable_reason=reason))
    assert options and all(o["unavailable_reason"] == reason for o in options)


def test_the_operator_ceiling_greys_the_model_it_names_and_only_that_model():
    ceiling = {"devstral:24b": "above the operator's 8B ceiling"}
    by_slug = {o["model_slug"]: o for o in _opencode(_picker(local_ceiling_reasons=ceiling))}
    assert by_slug["devstral:24b"]["available"] is False
    assert by_slug["qwen2.5-coder:3b"]["available"] is True


def test_an_opencode_option_is_coding_only_and_never_a_conductor_seat():
    """A harness with write hands is not a seat to conduct from."""
    for opt in _opencode(_picker()):
        assert opt["roles"] == ["coding"]
        assert opt["conductor_capable"] is False


def test_an_opencode_pane_advertises_no_subscription():
    """Invariant 19/27: counting a terminal for it would advertise spend that does not exist."""
    for opt in _opencode(_picker()):
        assert opt["subscription_backed"] is False
        assert opt["locality"] == "local"
    assert "opencode_local" not in pp.registered_frontier_providers()


def test_opencode_options_are_counted_as_local_and_included_in_the_flat_list():
    picker = _picker()
    grouped = [o for g in picker["providers"] for o in g["options"]]
    assert grouped == picker["options"]
    assert picker["counts"]["total"] == picker["counts"]["frontier"] + picker["counts"]["local"]
    assert picker["counts"]["total"] == len(picker["options"])
    assert len(_opencode(picker)) > 0            # the assertions above are not vacuous


def test_an_empty_ollama_enumeration_yields_no_opencode_options_never_a_fabricated_one():
    assert _opencode(_picker(ollama_models=[])) == []


def test_picker_and_spawn_agree_on_the_opencode_adapter_id():
    """The picker spells `opencode_local` itself rather than importing it (the dependency runs the
    other way). This is the test that makes the duplication safe — it fails if they drift."""
    from node_runtime.supervisor.worker_pane_spawn import OPENCODE_LOCAL_ADAPTER

    assert pp._OPENCODE_PROVIDER == OPENCODE_LOCAL_ADAPTER


def test_every_offered_opencode_option_can_reach_a_governed_launch_path():
    """U256's rule applied to the new provider: an id in the table that the authorizer does not
    dispatch is silently unspawnable, and `registered_providers()` must not call it registered."""
    assert "opencode_local" in pp.registered_providers()


@pytest.mark.parametrize("present", [True, False])
def test_the_probe_is_injectable_so_the_suite_does_not_depend_on_the_host(present):
    """`opencode_present=None` probes the real machine; an explicit value must win over it."""
    assert bool(_opencode(_picker(opencode_present=present))[0]["available"]) is present
