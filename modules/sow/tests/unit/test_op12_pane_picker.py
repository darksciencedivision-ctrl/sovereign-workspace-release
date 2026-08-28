"""Phase 18B `.picker` — the two OP-12 providers in the per-pane picker and in the governed
interactive pane authorization. Pure/deterministic: no CLI is spawned and no credential is read.

What these tests hold to, stated once so a later edit has to argue with it:
  * a model id is NEVER invented — the option set IS the CLI's own `models` listing, and an
    unenumerated provider yields zero options WITH a reason (operator directive §8/§14);
  * every refusal names the RIGHT provider — one provider's message under another's label is the
    §14 defect this file mutation-checks;
  * the I-X3 buckets are separate and capped at 1 EACH, never merged (§12);
  * the interactive argv is a TUI launch (no `-p`, no `--output-format`) with the permission mode,
    workspace and (grok) cross-session memory pinned (§9/§11, T2).
"""
from __future__ import annotations

import re

import pytest

from adapters.frontier.antigravity import (
    ANTIGRAVITY_ADAPTER,
    ANTIGRAVITY_DISPLAY,
    build_interactive_antigravity_command,
)
from adapters.frontier.grok_build import (
    GROK_ADAPTER,
    GROK_DISPLAY,
    build_interactive_grok_command,
)
from control_plane.nodes.pane_picker import (
    ProviderCliInventory,
    build_pane_picker,
    registered_frontier_providers,
    registered_providers,
)
from control_plane.profiles.live_authorization import LiveAuthorization
from node_runtime.supervisor.frontier_provider_spawn import (
    AntigravityCliUnavailable,
    GrokCliUnavailable,
    capability_for_antigravity,
    capability_for_grok,
)
from node_runtime.supervisor.pane_node_spawn import PaneSelection
from node_runtime.supervisor.subscription_governor import (
    SubscriptionGovernor,
    canonical_subscription_ref,
)
from node_runtime.supervisor.worker_pane_spawn import (
    FRONTIER_PANE_ADAPTERS,
    authorize_worker_pane,
    worker_env_scrub_names,
)

GROK_MODELS = ("grok-4.5",)
AGY_MODELS = ("gemini-3.6-flash-high", "gemini-3.1-pro-high")


def _live(*providers: str, terminals: int = 1) -> LiveAuthorization:
    return LiveAuthorization(
        authorized=True, providers=frozenset(providers), terminals_per_subscription=terminals,
        register_row="OP-12", source="(test)", reason="test authorization")


def _denied() -> LiveAuthorization:
    return LiveAuthorization.denied("no live-operation config (enforcement-by-absence)")


def _signed_in(models: tuple[str, ...] = GROK_MODELS) -> ProviderCliInventory:
    return ProviderCliInventory(present=True, authenticated=True, models=models, note="probe ok")


def _no_auth_surface(models: tuple[str, ...] = AGY_MODELS) -> ProviderCliInventory:
    return ProviderCliInventory(present=True, authenticated=None, models=models, note="probe ok")


def _opts(picker: dict, provider: str) -> list[dict]:
    return [o for o in picker["options"] if o["provider"] == provider]


def _group(picker: dict, provider: str) -> dict:
    return next(g for g in picker["providers"] if g["provider"] == provider)


# --------------------------------------------------------------------------------------------
# the option set is the CLI's own listing — never composed, never defaulted
# --------------------------------------------------------------------------------------------

def test_options_are_exactly_the_models_the_cli_enumerated() -> None:
    picker = build_pane_picker(_live(GROK_ADAPTER, ANTIGRAVITY_ADAPTER),
                               grok=_signed_in(), antigravity=_no_auth_surface())
    assert [o["label"] for o in _opts(picker, GROK_ADAPTER)] == list(GROK_MODELS)
    assert [o["label"] for o in _opts(picker, ANTIGRAVITY_ADAPTER)] == list(AGY_MODELS)
    for o in _opts(picker, GROK_ADAPTER) + _opts(picker, ANTIGRAVITY_ADAPTER):
        # the slug IS the enumerated id, and no option is a CLI-default fallback: these CLIs
        # publish their ids, so there is no label to resolve and nothing to fall back to.
        assert o["model_slug"] == o["label"]
        assert o["is_fallback"] is False
        assert o["verified"] is True
        assert o["available"] is True
        assert o["roles"] == ["reasoning"]     # U260: coding needs a mode §11 forbids


def test_a_model_this_provider_does_not_own_is_offered_but_says_who_pays_for_it() -> None:
    """U246, decided at `.picker` review round 1. `agy models` lists two OTHER vendors' models. They
    stay offered under this provider with the id the CLI published — concealing who serves them
    would be §14 pointing the wrong way — but the note must state that the session is counted
    against THIS subscription, or the operator reads their concurrency and their bill wrong."""
    picker = build_pane_picker(
        _live(ANTIGRAVITY_ADAPTER),
        antigravity=_no_auth_surface(models=("gemini-3.6-flash-high", "claude-sonnet-4-6",
                                             "gpt-oss-120b-medium")))
    by_slug = {o["model_slug"]: o for o in _opts(picker, ANTIGRAVITY_ADAPTER)}
    assert set(by_slug) == {"gemini-3.6-flash-high", "claude-sonnet-4-6", "gpt-oss-120b-medium"}
    for foreign in ("claude-sonnet-4-6", "gpt-oss-120b-medium"):
        note = by_slug[foreign]["note"]
        assert "U246" in note and "counted against it" in note, foreign
        assert "agy" in note                       # names the subscription that pays, by its command
    # …and the provider's OWN line carries no such note: a disclosure on everything discloses nothing
    assert "U246" not in by_slug["gemini-3.6-flash-high"]["note"]


def test_a_provider_with_no_enumeration_offers_nothing_and_says_why() -> None:
    """The failure mode this replaces: a 'CLI default' entry for a provider whose default we never
    read. Zero options, and the reason lives on the GROUP because there is no option to carry it."""
    picker = build_pane_picker(_live(GROK_ADAPTER, ANTIGRAVITY_ADAPTER))
    for provider, command in ((GROK_ADAPTER, "grok"), (ANTIGRAVITY_ADAPTER, "agy")):
        assert _opts(picker, provider) == []
        status = _group(picker, provider)["status"]
        assert status["available"] is False
        assert status["option_count"] == 0
        assert f"`{command}` CLI not detected" in status["reason"]


def test_an_empty_listing_from_a_healthy_cli_is_its_own_recorded_fact() -> None:
    picker = build_pane_picker(_live(GROK_ADAPTER), grok=_signed_in(models=()))
    status = _group(picker, GROK_ADAPTER)["status"]
    assert _opts(picker, GROK_ADAPTER) == []
    assert "enumerated no models" in status["reason"]
    assert "never invented" in status["reason"] or "is ever invented" in status["reason"]


def test_a_duplicate_or_blank_slug_never_doubles_an_option() -> None:
    picker = build_pane_picker(_live(GROK_ADAPTER),
                               grok=_signed_in(models=("grok-4.5", "grok-4.5", "  ", "")))
    assert [o["label"] for o in _opts(picker, GROK_ADAPTER)] == ["grok-4.5"]


# --------------------------------------------------------------------------------------------
# fail closed, and name the RIGHT provider (§14)
# --------------------------------------------------------------------------------------------

def test_no_live_authorization_greys_both_providers_with_their_own_reason() -> None:
    picker = build_pane_picker(_denied(), grok=_signed_in(), antigravity=_no_auth_surface())
    for provider in (GROK_ADAPTER, ANTIGRAVITY_ADAPTER):
        options = _opts(picker, provider)
        assert options, "an unauthorized provider is greyed, never hidden"
        for o in options:
            assert o["available"] is False
            assert provider in o["unavailable_reason"]
            assert "live operation not authorized" in o["unavailable_reason"]


def test_one_providers_reason_never_names_the_other() -> None:
    """§14 in its strictest reading, asserted rather than trusted: Grok is authorized and present,
    Antigravity is neither. Neither option set may carry the other's command or hint."""
    picker = build_pane_picker(_live(GROK_ADAPTER), grok=_signed_in())
    for o in _opts(picker, GROK_ADAPTER):
        assert o["available"] is True
    agy_reason = _group(picker, ANTIGRAVITY_ADAPTER)["status"]["reason"]
    assert "agy" in agy_reason and "antigravity.google" in agy_reason
    assert "grok" not in agy_reason and "xai" not in agy_reason.lower()


def test_a_signed_out_grok_is_refused_with_its_own_login_hint() -> None:
    picker = build_pane_picker(
        _live(GROK_ADAPTER),
        grok=ProviderCliInventory(present=True, authenticated=False, models=GROK_MODELS))
    # selectable_models() already withholds the list on AUTH_REQUIRED, but the picker must not
    # depend on that to be honest — with a list forced in, the options are still greyed.
    reason = _group(picker, GROK_ADAPTER)["status"]["reason"]
    assert "no signed-in session" in reason
    assert "grok login" in reason
    assert all(o["available"] is False for o in _opts(picker, GROK_ADAPTER))


def test_antigravitys_unverifiable_auth_blocks_nothing_but_is_disclosed() -> None:
    """The CLI has no offline auth surface at all. Blocking on that would make the provider
    permanently unselectable on a signed-in host; claiming it is fine would be an auth claim
    nothing observed. So: offered, with the gap stated in the note (§6)."""
    picker = build_pane_picker(_live(ANTIGRAVITY_ADAPTER), antigravity=_no_auth_surface())
    options = _opts(picker, ANTIGRAVITY_ADAPTER)
    assert all(o["available"] is True for o in options)
    assert all("no offline auth surface" in o["note"] for o in options)
    assert all("UNVERIFIED" in o["note"] for o in options)


def test_a_present_but_unusable_cli_is_not_told_to_install_itself() -> None:
    picker = build_pane_picker(
        _live(GROK_ADAPTER),
        grok=ProviderCliInventory(present=True, authenticated=True,
                                  blocked_reason="`grok_build` CLI version not usable (none)"))
    reason = _group(picker, GROK_ADAPTER)["status"]["reason"]
    assert "version not usable" in reason
    assert "npm install" not in reason


# --------------------------------------------------------------------------------------------
# registration / counters
# --------------------------------------------------------------------------------------------

def test_both_providers_are_registered_and_counted_as_frontier() -> None:
    assert {GROK_ADAPTER, ANTIGRAVITY_ADAPTER} <= registered_providers()
    assert {GROK_ADAPTER, ANTIGRAVITY_ADAPTER} <= registered_frontier_providers()
    # U256: registration means "the pane authorizer will dispatch it", not "it is in a list".
    assert registered_frontier_providers() <= set(FRONTIER_PANE_ADAPTERS)


def test_counts_include_the_new_providers_in_the_frontier_total() -> None:
    picker = build_pane_picker(_live(GROK_ADAPTER, ANTIGRAVITY_ADAPTER),
                               grok=_signed_in(), antigravity=_no_auth_surface(),
                               ollama_models=["a:8b"], residency={})
    counts = picker["counts"]
    assert counts["total"] == len(picker["options"])
    assert counts["frontier"] + counts["local"] == counts["total"]
    # the three enumerated OP-12 models are inside the frontier count, not lost between the two
    assert counts["frontier"] >= len(GROK_MODELS) + len(AGY_MODELS)
    assert counts["local"] == 1


def test_the_two_subscriptions_are_separate_buckets_capped_at_one_each() -> None:
    grok_ref = canonical_subscription_ref(GROK_ADAPTER)
    agy_ref = canonical_subscription_ref(ANTIGRAVITY_ADAPTER)
    assert grok_ref != agy_ref
    gov = SubscriptionGovernor()
    gov.register_subscription(grok_ref, GROK_ADAPTER, allowance=1)
    gov.register_subscription(agy_ref, ANTIGRAVITY_ADAPTER, allowance=1)
    gov.acquire(grok_ref, "worker-p1")
    # the Antigravity terminal is unaffected by Grok being at capacity — never merged (§12)
    gov.acquire(agy_ref, "worker-p2")
    assert gov.active_count(grok_ref) == 1 and gov.active_count(agy_ref) == 1


# --------------------------------------------------------------------------------------------
# interactive argv (§9 / §11 / T2)
# --------------------------------------------------------------------------------------------

def test_grok_interactive_argv_is_a_tui_launch_with_the_pins() -> None:
    argv = build_interactive_grok_command("C:/bin/grok.CMD", model="grok-4.5", workdir="C:/ws")
    assert argv[0] == "C:/bin/grok.CMD"
    assert "-p" not in argv and "--single" not in argv and "--output-format" not in argv
    assert argv[argv.index("--cwd") + 1] == "C:/ws"
    assert argv[argv.index("--permission-mode") + 1] == "plan"
    assert "--no-plan" not in argv                    # U327/19.1: it would cancel the pin above
    assert "--minimal" in argv and "--no-alt-screen" in argv
    assert "--no-memory" in argv                      # invariants 8/9: no cross-session carry-in
    assert argv[argv.index("-m") + 1] == "grok-4.5"
    # no prompt is ever appended — the operator's session, not ours
    assert not [a for a in argv[1:] if not a.startswith("-") and a not in
                ("C:/ws", "plan", "grok-4.5")]


def test_antigravity_interactive_argv_is_a_tui_launch_with_the_pins() -> None:
    argv = build_interactive_antigravity_command("C:/bin/agy.EXE", model="gemini-3.1-pro-high",
                                                 workdir="C:/ws")
    assert argv[0] == "C:/bin/agy.EXE"
    for banned in ("-p", "--print", "--prompt", "--prompt-interactive", "--output-format"):
        assert banned not in argv
    assert argv[argv.index("--mode") + 1] == "plan"
    assert argv[argv.index("--add-dir") + 1] == "C:/ws"
    assert argv[argv.index("--model") + 1] == "gemini-3.1-pro-high"


def test_no_model_means_the_cli_default_and_no_model_flag() -> None:
    assert "-m" not in build_interactive_grok_command("grok", model=None, workdir="C:/ws")
    assert "--model" not in build_interactive_antigravity_command("agy", model=" ", workdir="C:/ws")


@pytest.mark.parametrize("builder,exe", [(build_interactive_grok_command, "grok"),
                                         (build_interactive_antigravity_command, "agy")])
def test_the_interactive_builders_refuse_a_smuggled_widening_flag(builder, exe) -> None:
    """The guards are CALLED, not merely available: a forbidden flag smuggled through the one
    caller-controlled string reaches argv unless the builder guards it (the `.adapter` lesson —
    the reviewer deleted both guard calls and 1803 tests stayed green)."""
    with pytest.raises(ValueError):
        builder(exe, model="--always-approve", workdir="C:/ws")
    with pytest.raises(ValueError):
        builder(exe, model="x", workdir="--dangerously-skip-permissions")


# --------------------------------------------------------------------------------------------
# governed interactive pane authorization
# --------------------------------------------------------------------------------------------

class _Loader:
    """Minimal ProfileLoader stand-in: records what it was asked to admit and admits it."""

    def __init__(self) -> None:
        self.caps: list = []

    def assert_startup(self, caps, live_auth=None):  # noqa: ANN001
        self.caps.extend(caps)


def _selection(provider: str, slug: str, *, available: bool = True) -> PaneSelection:
    option = {"provider": provider, "adapter": provider, "locality": "frontier",
              "subscription_backed": True, "label": slug, "model_slug": slug, "verified": True,
              "is_fallback": False, "roles": ["reasoning"], "residency": None,
              "available": available, "unavailable_reason": None if available else "greyed",
              "note": "test"}
    return PaneSelection(option=option, role="reasoning", mode="attended",
                         node_id="worker-p1", permission_profile_id="pp-worker-reasoning",
                         subscription_ref=canonical_subscription_ref(provider))


@pytest.mark.parametrize("provider,exe,slug", [
    (GROK_ADAPTER, "C:/bin/grok.CMD", "grok-4.5"),
    (ANTIGRAVITY_ADAPTER, "C:/bin/agy.EXE", "gemini-3.1-pro-high"),
])
def test_a_governed_interactive_pane_is_authorized_and_counts_one_terminal(provider, exe,
                                                                           slug) -> None:
    gov = SubscriptionGovernor()
    loader = _Loader()
    session = authorize_worker_pane(
        _selection(provider, slug), live_auth=_live(provider), governor=gov,
        profile_loader=loader, operator_terms_confirmed=True, workspace="C:/ws",
        cli_present=True, executable=exe)
    ref = canonical_subscription_ref(provider)
    assert session.chrome.adapter == provider
    assert session.chrome.model_slug == slug
    assert session.chrome.locality == "frontier"
    assert session.chrome.interactive is True and session.chrome.governed is True
    assert session.chrome.node_state == "launch_authorized"     # not "ready": nothing is running
    assert session.chrome.subscription == {"ref": ref, "in_use": 1, "allowance": 1}
    assert session.launch["executable"] == exe
    assert session.launch["argv"][0] == exe
    assert session.launch["interactive"] is True and session.launch["one_shot"] is False
    assert session.subscription_governed is True
    # the capability the live gate evaluated is this provider's own
    assert [c.adapter for c in loader.caps] == [provider]
    # D-LOOP-1: the terminal is handed back within the unit
    session.teardown()
    assert gov.active_count(ref) == 0


@pytest.mark.parametrize("provider,exc", [(GROK_ADAPTER, GrokCliUnavailable),
                                          (ANTIGRAVITY_ADAPTER, AntigravityCliUnavailable)])
def test_an_absent_cli_raises_that_providers_own_exception(provider, exc) -> None:
    gov = SubscriptionGovernor()
    with pytest.raises(exc) as caught:
        authorize_worker_pane(
            _selection(provider, "m"), live_auth=_live(provider), governor=gov,
            profile_loader=_Loader(), operator_terms_confirmed=True, workspace="C:/ws",
            cli_present=False)
    command = "grok" if provider == GROK_ADAPTER else "agy"
    assert f"`{command}` CLI not detected" in str(caught.value)
    # nothing was acquired on the way to a refusal
    assert gov.active_count(canonical_subscription_ref(provider)) == 0


@pytest.mark.parametrize("provider", [GROK_ADAPTER, ANTIGRAVITY_ADAPTER])
def test_a_second_terminal_on_the_same_subscription_is_refused(provider) -> None:
    from node_runtime.supervisor.subscription_governor import SubscriptionLimitExceeded

    gov = SubscriptionGovernor()
    live = _live(provider)
    first = authorize_worker_pane(
        _selection(provider, "m"), live_auth=live, governor=gov, profile_loader=_Loader(),
        operator_terms_confirmed=True, workspace="C:/ws", cli_present=True,
        executable="C:/bin/x.exe")
    second = _selection(provider, "m")
    second = PaneSelection(option=second.option, role="reasoning", mode="attended",
                           node_id="worker-p2",
                           permission_profile_id=second.permission_profile_id,
                           subscription_ref=second.subscription_ref)
    with pytest.raises(SubscriptionLimitExceeded):
        authorize_worker_pane(second, live_auth=live, governor=gov, profile_loader=_Loader(),
                              operator_terms_confirmed=True, workspace="C:/ws", cli_present=True,
                              executable="C:/bin/x.exe")
    first.teardown()


@pytest.mark.parametrize("provider", [GROK_ADAPTER, ANTIGRAVITY_ADAPTER])
def test_an_unauthorized_provider_never_reaches_a_launch_spec(provider) -> None:
    from control_plane.profiles.live_authorization import LiveAuthorizationError

    gov = SubscriptionGovernor()
    # `(LiveAuthorizationError, Exception)` is just `Exception`, so this could not tell a governed
    # refusal from a crash — and the live gate inside `_authorize_frontier` could be deleted with the
    # whole suite green (validator MINOR-1 / mutation B2). The gate is named, and so is its subject.
    with pytest.raises(LiveAuthorizationError) as refusal:
        authorize_worker_pane(
            _selection(provider, "m"), live_auth=_denied(), governor=gov,
            profile_loader=_Loader(), operator_terms_confirmed=True, workspace="C:/ws",
            cli_present=True, executable="C:/bin/x.exe")
    assert provider in str(refusal.value)
    assert gov.active_count(canonical_subscription_ref(provider)) == 0


def test_the_capabilities_are_live_frontier_and_not_the_mock_sentinel() -> None:
    for cap, provider in ((capability_for_grok(), GROK_ADAPTER),
                          (capability_for_antigravity(), ANTIGRAVITY_ADAPTER)):
        assert cap.adapter == provider           # not "mock": ProfileLoader treats it as live
        assert cap.subscription_backed is True
        assert cap.offline_profile_eligible is False   # invariant 20: excluded from the air-gap
        assert cap.requires_network is True
        assert "reasoning" in cap.capabilities


def test_the_env_scrub_covers_both_new_providers_keys() -> None:
    """§13: the child env of ANY worker pane must not carry these. Measured over a supplied env so
    the assertion does not depend on what this host happens to hold."""
    names = worker_env_scrub_names(
        {"XAI_API_KEY": "x", "GEMINI_API_KEY": "x", "GOOGLE_API_KEY": "x",
         "ANTHROPIC_API_KEY": "x", "XAI_API_BASE_URL": "x", "NODE_OPTIONS": "x",
         "NODE_EXTRA_CA_CERTS": "x", "PATH": "x", "SOW_HARMLESS": "x"})
    # The three §17 keys are caught by the pre-existing claude/codex classifiers too, so asserting
    # only those left the OP-12 term in the scrub union removable with the suite green (validator
    # MEDIUM-3 / mutation B3). These three are the ones ONLY the OP-12 classifier covers: an endpoint
    # redirect that would send a session somewhere else, and the two Node injection vectors.
    assert {"XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY",
            "XAI_API_BASE_URL", "NODE_OPTIONS", "NODE_EXTRA_CA_CERTS"} <= set(names)
    assert "PATH" not in names and "SOW_HARMLESS" not in names


# --------------------------------------------------------------------------------------------
# §14 SELECTABLE LABELS — the one verbatim prohibition in the operator directive, and the one
# surface that had no deterministic test at the 18B close (validator BLOCKING-1).
#
# OP12 §14 says, as its only negative about labels: "Do not display `Gemini CLI` for the Google
# AI Pro path." §16 requires deterministic tests for model-picker registration. Before these
# tests, changing ANTIGRAVITY_DISPLAY to the literal forbidden string left the entire Python suite
# green — as did changing GROK_DISPLAY, and as did re-typing either into the picker table. The
# values were right; nothing HELD them right. A receipt binds one tree at one moment; the next
# product edit was unguarded, which is exactly the U275 standard this track wrote and then did not
# apply to itself ("a dispatch table's dangerous failure is a WRONG entry, not a missing one").
# --------------------------------------------------------------------------------------------

_FORBIDDEN_LABEL = re.compile(r"gemini\s*cli", re.I)


def test_the_op12_display_strings_are_the_directive_s14_labels_verbatim() -> None:
    assert GROK_DISPLAY == "Grok Build"
    assert ANTIGRAVITY_DISPLAY == "Gemini · Antigravity"


def test_no_picker_label_anywhere_shows_the_forbidden_gemini_cli_string() -> None:
    """The prohibition is about what the OPERATOR SEES, so it is asserted over the rendered
    surface — every group display and every option label — not just over the two constants. A
    second spelling introduced anywhere in the table or the option builders dies here."""
    picker = build_pane_picker(_live(GROK_ADAPTER, ANTIGRAVITY_ADAPTER),
                               grok=_signed_in(), antigravity=_no_auth_surface())
    shown = ([g["display"] for g in picker["providers"]]
             + [str(o.get("label") or "") for o in picker["options"]])
    offenders = [s for s in shown if _FORBIDDEN_LABEL.search(s)]
    assert offenders == [], (
        "operator directive §14 forbids showing 'Gemini CLI' for the Google AI Pro path (it names "
        f"the RETIRED personal-account CLI — a different product on a different credential); "
        f"found {offenders}")


def test_every_picker_group_display_is_the_adapter_module_s_own_constant() -> None:
    """§14's labels are PUBLISHED by the adapter modules and imported by the picker rather than
    re-typed — this pins that, so a hand-typed second spelling cannot drift from its source even
    to a string that is not the forbidden one. Identity, not equality: a copied literal that
    happens to match today would pass an `==` check and then diverge on the next edit."""
    from control_plane.nodes import pane_picker as pp

    by_provider = {p: display for p, display, _loc in pp._PROVIDER_TABLE}
    assert by_provider[GROK_ADAPTER] is GROK_DISPLAY
    assert by_provider[ANTIGRAVITY_ADAPTER] is ANTIGRAVITY_DISPLAY


def test_the_two_provider_labels_are_distinct_and_name_their_own_vendor() -> None:
    """One provider's text under the other's id is the §14 defect this file already
    mutation-checks for refusal MESSAGES; the selectable label is the same defect, one surface up
    and more visible."""
    assert GROK_DISPLAY != ANTIGRAVITY_DISPLAY
    assert "grok" in GROK_DISPLAY.lower()
    assert "antigravity" in ANTIGRAVITY_DISPLAY.lower()


# --------------------------------------------------------------------------------------------
# U256 — `registered_providers()` is the INTERSECTION of what is RENDERED and what the pane
# authorizer will DISPATCH. The docstring said so; nothing held it (validator MEDIUM-1: replacing
# the body with the bare provider table left the whole suite green). It is a no-op TODAY because
# the two sets coincide — which is precisely the state the guard exists to survive changing.
# --------------------------------------------------------------------------------------------

def test_a_rendered_provider_the_authorizer_will_not_dispatch_is_not_registered(monkeypatch) -> None:
    """Forge the divergence the intersection exists for: `grok_build` still in the picker table
    (so it renders, and an operator can click it) but dropped from the authorizer's dispatch
    tuple. `registered_providers()` must stop claiming it — and with it the status bar's frontier
    set, because a counter for a provider no pane can spawn advertises a terminal the product
    cannot take (invariant 27 / I-X3)."""
    import node_runtime.supervisor.worker_pane_spawn as wps

    narrowed = tuple(a for a in wps.FRONTIER_PANE_ADAPTERS if a != GROK_ADAPTER)
    monkeypatch.setattr(wps, "FRONTIER_PANE_ADAPTERS", narrowed)

    assert GROK_ADAPTER not in registered_providers()
    assert GROK_ADAPTER not in registered_frontier_providers()
    # the provider is still RENDERED — that is the point: the divergence is real, and the
    # registration accessor is the thing that refuses to paper over it
    picker = build_pane_picker(_live(GROK_ADAPTER, ANTIGRAVITY_ADAPTER),
                               grok=_signed_in(), antigravity=_no_auth_surface())
    assert GROK_ADAPTER in [g["provider"] for g in picker["providers"]]
    # and the provider that IS still dispatchable is unaffected
    assert ANTIGRAVITY_ADAPTER in registered_providers()


def test_the_local_provider_is_registered_through_the_authorizers_own_constant() -> None:
    """The intersection names the local adapter from `worker_pane_spawn.OLLAMA_LOCAL_ADAPTER`, not
    from a literal — so a rename on the authorizer side drops it out of `registered_providers()`
    rather than leaving a stale id silently registered."""
    from node_runtime.supervisor.worker_pane_spawn import OLLAMA_LOCAL_ADAPTER

    assert OLLAMA_LOCAL_ADAPTER in registered_providers()
    assert OLLAMA_LOCAL_ADAPTER not in registered_frontier_providers()   # local: no subscription
