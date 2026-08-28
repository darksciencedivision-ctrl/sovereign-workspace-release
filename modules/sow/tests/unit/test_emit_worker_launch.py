"""Governed WORKER LAUNCH TICKET emitter (Phase 17B `.ticket`; directive §16 track 17B, U70).

The conductor got its executable authorization at 17A `.lease`; a picker selection still got nothing
— it was recorded and badged, and the pane stayed empty (operator finding F3). This emitter is the
worker's equivalent: ONE picker selection in, a governed ticket the shell can execute out, or a
fail-closed refusal.

These tests pin that contract without a live call:

  * the ticket is produced ONLY through the governed chain (`authorize_worker_pane`), and a FRONTIER
    ticket carries a DURABLE I-X3 lease that is still held when it is emitted (the session outlives
    the emitter) while the emitter's own in-process count is released (D-LOOP-1);
  * a LOCAL ticket carries NO lease and says so (`subscription_governed:false`) — invariant 19: a
    local model is governed by VRAM residency, not by a subscription — and carries its residency;
  * a durable count already at the allowance REFUSES a frontier ticket, even though the emitter's own
    governor is empty (the cross-process half of I-X3);
  * every refusal (greyed option, conductor role, unauthorized live config, absent CLI, unfittable
    model, malformed selection) is a well-formed REFUSAL ticket with a reason and NO argv and NO
    lease — never a fabricated authorization, never a leaked terminal;
  * the CLI reads the selection from STDIN and prints exactly one JSON line; a usage error exits 2
    with no JSON (the shell treats that as "unavailable", never as a launch).
"""
from __future__ import annotations

import io
import json

import pytest

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from adapters.frontier.claude_model_probe import ModelProbeLedger, ModelProbeRecord
from adapters.frontier.antigravity import ANTIGRAVITY_ADAPTER, ANTIGRAVITY_MODEL_FLAG
from adapters.frontier.codex import CODEX_ADAPTER
from adapters.frontier.grok_build import GROK_ADAPTER, GROK_MODEL_FLAG
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from node_runtime.supervisor.subscription_governor import (
    SubscriptionGovernor,
    canonical_subscription_ref,
)
from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger
from scheduler.residency_planner.residency_planner import ResidencyPlanner
from tools.live.emit_worker_launch import (
    WORKER_TICKET_SCHEMA,
    build_worker_launch_ticket,
    build_worker_lease_release_session,
    main,
)

HOLDER = 5150
SESSION = "pane-2#5150.1"
PANE = "pane-2"


def _authorized(*providers: str) -> LiveAuthorization:
    return LiveAuthorization(
        authorized=True,
        providers=frozenset(providers or (CLAUDE_CODE_ADAPTER, CODEX_ADAPTER)),
        terminals_per_subscription=2, register_row="OP-6", source="(test)",
        reason="test authorization")


def _unauthorized() -> LiveAuthorization:
    return LiveAuthorization(authorized=False, providers=frozenset(),
                             terminals_per_subscription=0, register_row=None, source="(test)",
                             reason="live_operation.json absent — fail closed")


def _ledger(tmp_path, *, alive=(HOLDER,)) -> TerminalLeaseLedger:
    live = set(alive)
    return TerminalLeaseLedger(path=tmp_path / "leases.json", pid_alive=lambda p: p in live)


def _probe_record(**over) -> ModelProbeRecord:
    kw = dict(label="fable-5", candidates=("fable-5", "claude-fable-5"),
              accepted_slug="claude-fable-5", checkpoint="claude-fable-5-20260701",
              conclusive=True, is_fallback=False, attempts=(), probed_at="2026-07-25T00:00:00Z",
              note="accepted")
    kw.update(over)
    return ModelProbeRecord(**kw)


def _planner() -> ResidencyPlanner:
    planner = ResidencyPlanner(12288)
    planner.register_model("qwen3:8b", 5200)
    return planner


def _frontier_selection(adapter: str = CLAUDE_CODE_ADAPTER, *, slug: str | None = "fable-5",
                        role: str = "reasoning", available: bool = True) -> dict:
    return {"option": {"provider": adapter, "adapter": adapter, "locality": "frontier",
                       "subscription_backed": True, "label": slug or "CLI default",
                       "model_slug": slug, "verified": False, "is_fallback": False,
                       "roles": ["conductor", "reasoning", "coding"], "residency": None,
                       "available": available,
                       "unavailable_reason": None if available else "not authorized"},
            "role": role, "mode": "autonomous"}


def _local_selection(tag: str = "qwen3:8b", *, role: str = "reasoning") -> dict:
    return {"option": {"provider": "ollama_local", "adapter": "ollama_local", "locality": "local",
                       "subscription_backed": False, "label": tag, "model_slug": tag,
                       "verified": True, "is_fallback": False, "roles": ["reasoning", "coding"],
                       "residency": "not_loaded", "available": True, "unavailable_reason": None},
            "role": role, "mode": "attended"}


def _offered(*selections: dict) -> list[dict]:
    """The host-enumeration stand-in the emitter verifies a selection against. Built FROM the
    selections under test so a test says "the host offers this" explicitly — the production path
    enumerates the real host instead (`offered_options=None`)."""
    return [dict(sel["option"], roles=list(sel["option"].get("roles") or []))
            for sel in selections if isinstance(sel, dict) and isinstance(sel.get("option"), dict)]


#: The budget provenance the host enumeration returns alongside a usable planner. Required now: an
#: authorization whose budget was never ESTABLISHED is refused, so a planner alone is not enough
#: (spec-audit MAJOR-1, 2026-07-26).
_ESTABLISHED_BUDGET = {"vram_budget_mb": 12288, "budget_source": "(test) established",
                       "estimate": True, "established": True}


def _ticket(selection: dict, tmp_path, **kw) -> dict:
    offered = kw.pop("offered_options", _offered(selection) if isinstance(selection, dict) else [])
    call = dict(holder_pid=HOLDER, session_id=SESSION, pane_id=PANE, selection=selection,
                offered_options=offered,
                ledger=_ledger(tmp_path), live_auth=_authorized(), governor=SubscriptionGovernor(),
                profile_loader=ProfileLoader(DeploymentProfile("cloud")),
                operator_terms_confirmed=True,
                residency_planner=_planner(), residency_budget=_ESTABLISHED_BUDGET,
                workspace="D:/repo", cli_present=True,
                ollama_present=True, probe_ledger=ModelProbeLedger(path=tmp_path / "probe.json"))
    call.update(kw)
    # The disclosed budget must be the total the planner ENFORCES — the gate asserts the pairing, so
    # a fixture that hard-codes one figure while the test builds a planner with another is testing a
    # ticket the product can never emit (validator MINOR-4). Derived unless a test pins it on purpose.
    planner = call.get("residency_planner")
    if "residency_budget" not in kw and planner is not None:
        call["residency_budget"] = dict(_ESTABLISHED_BUDGET, vram_budget_mb=planner.total_vram_mb())
    # `registrar` defaults to None but a test may override it (W-13 injects one that fails on disk),
    # so it is merged rather than passed positionally — passing both would be a duplicate keyword.
    return build_worker_launch_ticket(**{"registrar": None, **call})


# ---- frontier: authorized, interactive, durably counted ----------------------------------------

def test_a_frontier_ticket_is_authorized_interactive_and_holds_a_durable_lease(tmp_path):
    led = _ledger(tmp_path)
    t = _ticket(_frontier_selection(), tmp_path, ledger=led)

    assert t["schema"] == WORKER_TICKET_SCHEMA
    assert t["authorized"] is True and t["refused"] is False
    assert t["node_state"] == "launch_authorized"
    assert t["launch"]["interactive"] is True and t["launch"]["one_shot"] is False
    assert "-p" not in t["launch"]["argv"] and "--print" not in t["launch"]["argv"]
    assert t["launch"]["cwd"] == "D:/repo" and t["launch"]["executable"]
    assert isinstance(t["launch"]["env_scrub_names"], list)
    assert "env" not in t["launch"]                     # §2.2 — names only, never values
    # governed identity minted PYTHON-side: the shell cannot name its own node
    assert t["identity"]["node_id"] == "worker-pane-2"
    assert t["identity"]["permission_profile_id"] == "pp-worker-reasoning"
    assert t["identity"]["session_id"] == SESSION and t["identity"]["pane_id"] == PANE
    # the durable terminal is HELD (it will outlive this emitter) …
    assert t["subscription_governed"] is True
    assert t["lease"]["durable"] is True and t["lease"]["holder_pid"] == HOLDER
    assert t["lease"]["session_id"] == SESSION and t["lease"]["in_use"] == 1
    assert led.in_use(canonical_subscription_ref(CLAUDE_CODE_ADAPTER)) == 1
    # … while the emitter's OWN in-process count is handed back (D-LOOP-1)
    assert t["governor_released"] is True
    assert t["gates"]["ix3_counted"] is True
    assert t["containment"]["supervisor_bound"] is False   # a ticket is never containment
    assert t["chrome"]["governed"] is True and t["chrome"]["interactive"] is True


def test_the_frontier_ticket_asks_for_the_slug_the_cli_actually_accepts(tmp_path):
    """17A's `.roundtrip` lesson applied to workers: the picker offers the operator's LABEL slug
    (`fable-5`), which this host's CLI rejects; the probe ledger's accepted id is what must reach
    argv, and where it came from must be stated."""
    probe = ModelProbeLedger(path=tmp_path / "probe.json")
    probe.write(_probe_record())
    t = _ticket(_frontier_selection(), tmp_path, probe_ledger=probe)
    assert t["launch"]["argv"][-2:] == ["--model", "claude-fable-5"]
    assert t["model_probe"]["model_available"] is True
    assert t["model_probe"]["source"] == "probe-ledger"


def test_a_conclusively_unavailable_slug_becomes_the_recorded_cli_default_fallback(tmp_path):
    probe = ModelProbeLedger(path=tmp_path / "probe.json")
    probe.write(_probe_record(accepted_slug=None, checkpoint=None, is_fallback=True,
                              note="every candidate rejected"))
    t = _ticket(_frontier_selection(), tmp_path, probe_ledger=probe)
    assert "--model" not in t["launch"]["argv"]
    assert t["chrome"]["is_fallback"] is True            # surfaced on the badge, never silent
    assert t["model_probe"]["model_available"] is False


def test_a_codex_ticket_is_interactive_sandboxed_and_counted_on_its_own_subscription(tmp_path):
    led = _ledger(tmp_path)
    t = _ticket(_frontier_selection(CODEX_ADAPTER, slug="gpt-5.5"), tmp_path, ledger=led)
    assert t["authorized"] is True
    assert "exec" not in t["launch"]["argv"]
    assert "--sandbox" in t["launch"]["argv"]
    assert t["lease"]["subscription_ref"] == canonical_subscription_ref(CODEX_ADAPTER)
    assert led.in_use(canonical_subscription_ref(CLAUDE_CODE_ADAPTER)) == 0   # separate allowance


def test_a_durable_count_at_the_allowance_refuses_a_new_frontier_ticket(tmp_path):
    led = _ledger(tmp_path)
    ref = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)
    for i in (1, 2):
        led.acquire(subscription_ref=ref, provider=CLAUDE_CODE_ADAPTER, node_id=f"other-{i}",
                    allowance=2, holder_pid=HOLDER, purpose="held elsewhere", session_id=f"s{i}")
    t = _ticket(_frontier_selection(), tmp_path, ledger=led)
    assert t["authorized"] is False and t["refused"] is True
    assert "limit" in t["reason"].lower() or "allowance" in t["reason"].lower()
    assert t["launch"] is None and t["lease"] is None
    assert led.in_use(ref) == 2                          # nothing leaked


# ---- local: residency-governed, never subscription-governed ------------------------------------

def test_a_local_ticket_carries_no_lease_and_says_it_is_not_subscription_governed(tmp_path):
    led = _ledger(tmp_path)
    t = _ticket(_local_selection(), tmp_path, ledger=led)
    assert t["authorized"] is True
    assert t["launch"]["argv"][1:] == ["run", "qwen3:8b"]
    assert t["subscription_governed"] is False
    assert t["lease"] is None
    assert t["residency"] is not None and t["residency"]["model"] == "qwen3:8b"
    assert t["chrome"]["subscription"] is None
    assert led.snapshot() == {}                          # no terminal counted for a local model
    assert t["gates"]["local_runtime_present"] is True


def test_a_local_model_whose_vram_cannot_be_proven_is_refused(tmp_path):
    t = _ticket(_local_selection("unregistered:70b"), tmp_path)
    assert t["authorized"] is False and t["refused"] is True
    assert "vram" in t["reason"].lower() or "residency" in t["reason"].lower()
    assert t["launch"] is None


def test_a_local_ticket_is_refused_when_the_ollama_runtime_is_absent(tmp_path):
    t = _ticket(_local_selection(), tmp_path, ollama_present=False)
    assert t["authorized"] is False and "ollama" in t["reason"].lower()


# ---- refusals: fail-closed, well-formed, no argv, no lease -------------------------------------

@pytest.mark.parametrize("selection,marker", [
    (_frontier_selection(available=False), "unavailable"),
    (_frontier_selection(role="conductor"), "role"),
    ({"option": {}, "role": "reasoning", "mode": "autonomous"}, "role"),
    ({"option": _frontier_selection()["option"], "role": "reasoning", "mode": "sideways"}, "mode"),
    ({"role": "reasoning", "mode": "autonomous"}, "option"),
    ("not-a-selection", "selection"),
])
def test_bad_selections_yield_a_refusal_ticket_never_an_authorization(selection, marker, tmp_path):
    led = _ledger(tmp_path)
    t = _ticket(selection, tmp_path, ledger=led)
    assert t["schema"] == WORKER_TICKET_SCHEMA
    assert t["authorized"] is False and t["refused"] is True
    assert marker in t["reason"].lower()
    assert t["launch"] is None and t["lease"] is None and t["chrome"] is None
    assert led.snapshot() == {}


def test_an_unauthorized_live_config_refuses_a_frontier_ticket(tmp_path):
    t = _ticket(_frontier_selection(), tmp_path, live_auth=_unauthorized())
    assert t["authorized"] is False and t["refused"] is True
    assert "live operation not authorized" in t["reason"].lower()
    assert t["gates"]["live_operation_authorized"] is False


def test_an_absent_cli_refuses_the_ticket_and_the_gate_record_says_which_gate(tmp_path):
    t = _ticket(_frontier_selection(), tmp_path, cli_present=False)
    assert t["authorized"] is False
    assert t["gates"]["cli_present"] is False
    assert t["gates"]["ix3_counted"] is False


def test_unconfirmed_operator_terms_refuse_the_ticket(tmp_path):
    t = _ticket(_frontier_selection(), tmp_path, operator_terms_confirmed=False)
    assert t["authorized"] is False and "terms" in t["reason"].lower()
    assert t["gates"]["operator_terms_confirmed"] is False


# ---- release ------------------------------------------------------------------------------------

def test_release_by_session_hands_the_terminal_back_across_every_subscription(tmp_path):
    led = _ledger(tmp_path)
    t = _ticket(_frontier_selection(CODEX_ADAPTER, slug="gpt-5.5"), tmp_path, ledger=led)
    assert t["authorized"] is True
    out = build_worker_lease_release_session(SESSION, ledger=led)
    assert out["released"] is True and out["released_count"] == 1
    assert led.in_use(canonical_subscription_ref(CODEX_ADAPTER)) == 0
    # idempotent: a second release reports nothing to reclaim, with no error
    again = build_worker_lease_release_session(SESSION, ledger=led)
    assert again["released"] is False and again["error"] is None


# ---- the CLI contract the shell parses -----------------------------------------------------------

def test_cli_reads_the_selection_from_stdin_and_prints_one_json_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOW_TERMINAL_LEASE_LEDGER", str(tmp_path / "leases.json"))
    monkeypatch.setenv("SOW_MODEL_PROBE_LEDGER", str(tmp_path / "probe.json"))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_local_selection())))
    code = main(["--emit-worker-launch", "--holder-pid", str(HOLDER), "--session-id", SESSION,
                 "--pane-id", PANE])
    out = capsys.readouterr().out.strip().splitlines()
    assert code == 0 and len(out) == 1
    payload = json.loads(out[0])
    assert payload["schema"] == WORKER_TICKET_SCHEMA
    # `isinstance(bool)` was the whole assertion until the 18B close, and it is satisfied by ANY
    # ticket — including the fail-closed refusal this test was silently producing when the host
    # enumeration raised under the live-call guard (validator MAJOR-2). Assert the CONTRACT the
    # shell parses, on whichever branch this host produces: an authorization carries an executable
    # launch, a refusal carries a reason and NOTHING executable. There is no third shape, and
    # neither branch may be an authorization without argv.
    assert isinstance(payload["authorized"], bool)
    if payload["authorized"]:
        assert payload["launch"] and payload["launch"].get("argv")
        assert payload.get("reason") in (None, "")
    else:
        assert payload["launch"] is None
        assert isinstance(payload.get("reason"), str) and payload["reason"].strip()
        assert payload.get("refused_by")


def test_the_cli_never_probes_the_op12_clis_for_a_local_selection(tmp_path, monkeypatch, capsys):
    """Validator MAJOR-3. `_assert_option_offered` verifies the caller's selection against the
    host's own enumeration, and until the 18B close it built that enumeration by probing EVERY
    provider — so launching a local `qwen3:8b` pane, with no subscription and no credential, sent
    a metadata request to grok.com under the operator's SuperGrok session before the pane opened.
    D-P18-7 disclosed that cost for the picker drawer, where the operator asked to see every
    provider; on a local launch it is undisclosed AND unowed (invariants 19/20).

    Pinned by making the real probe fatal: if the launch path reaches it, this test fails."""
    import tools.live.enumerate_pane_picker as epp

    def _forbidden() -> None:
        raise AssertionError("the launch path probed the OP-12 CLIs for a LOCAL selection - that "
                             "is an outbound provider metadata call a local pane never owes")

    monkeypatch.setattr(epp, "_probe_op12_providers", _forbidden)
    monkeypatch.setenv("SOW_TERMINAL_LEASE_LEDGER", str(tmp_path / "leases.json"))
    monkeypatch.setenv("SOW_MODEL_PROBE_LEDGER", str(tmp_path / "probe.json"))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_local_selection())))
    code = main(["--emit-worker-launch", "--holder-pid", str(HOLDER), "--session-id", SESSION,
                 "--pane-id", PANE])
    assert code == 0
    assert json.loads(capsys.readouterr().out.strip())["schema"] == WORKER_TICKET_SCHEMA


@pytest.mark.parametrize("provider,expect_real_probe", [
    ("ollama_local", False),
    (CLAUDE_CODE_ADAPTER, False),
    (CODEX_ADAPTER, False),
    (GROK_ADAPTER, True),
    (ANTIGRAVITY_ADAPTER, True),
    (None, False),
])
def test_the_host_enumeration_probes_the_op12_clis_only_for_an_op12_selection(
        provider, expect_real_probe, monkeypatch) -> None:
    """The scoping rule itself, read off the call rather than inferred. `op12_probes=None` asks
    `build_host_picker` for the REAL host probe; anything else is the host-free stand-in.

    A wrong entry here is the dangerous failure, not a missing one (U275): scoping a provider OUT
    that needs the probe would verify an OP-12 selection against an enumeration that offers no
    OP-12 options, refusing every such launch — fail-closed, but for a fabricated reason.

    18C `.close` narrowed this further (U290): an OP-12 selection is verified against the real
    listing of ITS OWN provider only. Asking for both meant authorizing a Gemini pane emitted
    `grok --version`/`grok models` to grok.com — the cross-provider half of the egress U276 closed
    for a local selection."""
    import tools.live.emit_worker_launch as ewl

    seen: dict = {}

    def _spy(*, op12_probes=None):
        seen["op12_probes"] = op12_probes
        return ({"options": []}, {})

    def _only(p, *, probe=None):
        seen["scoped_to"] = p
        return ("scoped", p)

    monkeypatch.setattr("tools.live.enumerate_pane_picker.build_host_picker", _spy)
    monkeypatch.setattr("tools.live.enumerate_pane_picker.only_op12_probe", _only)
    ewl._host_offered_options(provider=provider)
    if expect_real_probe:
        assert seen["scoped_to"] == provider, (
            "an OP-12 selection must be verified against the real listing of ITS OWN provider")
        assert seen["op12_probes"] == ("scoped", provider)
    else:
        assert "scoped_to" not in seen, "a non-OP-12 selection must probe no OP-12 CLI at all"
        assert seen["op12_probes"] is not None, "a non-OP-12 selection must not pay for the probe"


def test_only_op12_probe_spawns_for_one_provider_and_reports_the_other_unprobed() -> None:
    """The scoping primitive itself (U290). The un-selected provider must be the honest
    not-probed stand-in — never a fabricated availability, and never a second host call."""
    from tools.live.enumerate_pane_picker import ANTIGRAVITY_ADAPTER as A
    from tools.live.enumerate_pane_picker import GROK_ADAPTER as G
    from tools.live.enumerate_pane_picker import only_op12_probe

    for selected, other in ((G, A), (A, G)):
        probed: list[str] = []
        grok, agy = only_op12_probe(selected, probe=lambda p: (probed.append(p), _fake_probe(p))[1])
        by_id = {grok.provider: grok, agy.provider: agy}
        assert probed == [selected], f"{selected}: probed {probed}"
        assert by_id[selected].present is True
        assert by_id[selected].detail == "probed"
        assert by_id[other].present is False
        assert by_id[other].detail == "no host probe performed"
        assert by_id[other].auth_detail == "not probed on this run"

    with pytest.raises(ValueError):
        only_op12_probe("claude_code")


def _fake_probe(provider: str):
    from tools.live.enumerate_pane_picker import AUTH_UNVERIFIED, ProviderCliProbe

    return ProviderCliProbe(provider, True, "exe", "1.0", (1, 0, 0), True, AUTH_UNVERIFIED,
                            "probed-auth", ("m-1",), None, "ok", "probed")


def test_an_injected_op12_probe_seam_reaches_the_host_enumeration(monkeypatch) -> None:
    """Validator MAJOR-2: `enumerate_pane_picker` publishes a host-free seam and it stopped at this
    module, so a deterministic test that went through `main()` fired a real `grok --version`. The
    seam is threaded now — an explicit `op12_probes` is passed through verbatim even for an OP-12
    selection, which is the case that would otherwise touch the host."""
    import tools.live.emit_worker_launch as ewl
    from tools.live.enumerate_pane_picker import no_op12_probes

    sentinel = no_op12_probes()
    seen: dict = {}

    def _spy(*, op12_probes=None):
        seen["op12_probes"] = op12_probes
        return ({"options": []}, {})

    monkeypatch.setattr("tools.live.enumerate_pane_picker.build_host_picker", _spy)
    ewl._host_offered_options(provider=GROK_ADAPTER, op12_probes=sentinel)
    assert seen["op12_probes"] is sentinel


def test_the_ticket_builder_threads_its_probe_seam_all_the_way_to_the_enumeration(
        tmp_path, monkeypatch) -> None:
    """The seam is only worth having if the PRODUCT path carries it. Exercised end-to-end through
    `build_worker_launch_ticket` with `offered_options=None` — i.e. the real verification path,
    enumerating rather than being handed a list — and an OP-12 selection, the one case that would
    otherwise reach the host. Dropping the argument from the call site inside the ticket builder
    left every other test in this file green (mutation, 18B close)."""
    from tools.live.enumerate_pane_picker import no_op12_probes

    sel = _frontier_selection(GROK_ADAPTER, slug="grok-4.5", role="reasoning")
    sentinel = no_op12_probes()
    seen: dict = {}

    def _spy(*, op12_probes=None):
        seen["op12_probes"] = op12_probes
        return ({"options": _offered(sel)}, {})

    monkeypatch.setattr("tools.live.enumerate_pane_picker.build_host_picker", _spy)
    _ticket(sel, tmp_path, offered_options=None, op12_probes=sentinel)
    assert seen["op12_probes"] is sentinel, (
        "the ticket builder enumerated the host WITHOUT the caller's host-free seam - a "
        "deterministic caller cannot keep the product path off the OP-12 CLIs")


@pytest.mark.parametrize("argv", [
    ["--emit-worker-launch", "--session-id", SESSION, "--pane-id", PANE],       # no holder pid
    ["--emit-worker-launch", "--holder-pid", str(HOLDER), "--pane-id", PANE],   # no session id
    ["--emit-worker-launch", "--holder-pid", str(HOLDER), "--session-id", SESSION],  # no pane id
    [],
])
def test_cli_usage_errors_exit_2_with_no_json(argv, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    assert main(argv) == 2
    assert capsys.readouterr().out == ""


def test_cli_refuses_a_non_json_selection_with_a_refusal_ticket(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOW_TERMINAL_LEASE_LEDGER", str(tmp_path / "leases.json"))
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    code = main(["--emit-worker-launch", "--holder-pid", str(HOLDER), "--session-id", SESSION,
                 "--pane-id", PANE])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["authorized"] is False and payload["refused"] is True
    assert "json" in payload["reason"].lower()


# ---- the caller-supplied option is verified against the HOST enumeration (spec-audit MAJOR-2) ----

def test_a_forged_available_flag_is_refused_against_the_host_enumeration(tmp_path):
    """The shell sends the option it rendered; nothing stops a drifted/hostile caller flipping
    `available`. The emitter re-checks it against what the host really offers."""
    greyed = _frontier_selection(available=False)
    forged = _frontier_selection(available=True)
    t = _ticket(forged, tmp_path, offered_options=_offered(greyed))
    assert t["authorized"] is False and t["refused"] is True
    assert "not one this host currently offers" in t["reason"]
    assert t["launch"] is None and t["lease"] is None


def test_a_role_the_host_descriptor_never_offered_is_refused(tmp_path):
    """I-SC1: the role must come from the descriptor, not from the caller's copy of it."""
    host = _frontier_selection()
    host["option"]["roles"] = ["conductor"]              # the host offers no worker role here
    t = _ticket(_frontier_selection(role="reasoning"), tmp_path, offered_options=_offered(host))
    assert t["authorized"] is False
    assert "not offered by the HOST descriptor" in t["reason"]


def test_an_unenumerable_host_refuses_rather_than_trusting_the_caller(tmp_path, monkeypatch):
    def _boom():
        raise RuntimeError("daemon down")

    # patch the ENUMERATOR, not the wrapper, so the wrapper own fail-closed conversion is what runs
    monkeypatch.setattr("tools.live.enumerate_pane_picker.build_host_picker", _boom)
    t = build_worker_launch_ticket(
        registrar=None,
        holder_pid=HOLDER, session_id=SESSION, pane_id=PANE, selection=_frontier_selection(),
        ledger=_ledger(tmp_path), live_auth=_authorized(), governor=SubscriptionGovernor(),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
        residency_planner=_planner(),
        workspace="D:/repo", cli_present=True, ollama_present=True,
        probe_ledger=ModelProbeLedger(path=tmp_path / "probe.json"))
    assert t["authorized"] is False
    assert "daemon down" in t["reason"] or "unverifiable offer" in t["reason"]


# ---- the residency authorization discloses the budget it was made against (validator R2) --------

def test_a_local_ticket_discloses_the_vram_budget_and_whether_it_is_an_estimate(tmp_path):
    budget = {"vram_budget_mb": 12288, "budget_source": "STAND-IN constant", "estimate": True,
              "established": True}
    t = _ticket(_local_selection(), tmp_path, residency_budget=budget)
    assert t["authorized"] is True
    assert t["residency"]["budget"]["estimate"] is True
    assert t["residency"]["budget"]["vram_budget_mb"] == 12288


def test_a_local_pane_that_would_displace_a_running_model_is_refused(tmp_path):
    """Invariant 22's "never mid-generation eviction" cannot be enforced against a `generating`
    flag the host seeding never sets, so this build refuses to displace anything at all."""
    planner = ResidencyPlanner(6000)
    planner.register_model("qwen3:8b", 5200)
    planner.register_model("resident-other:7b", 5000)
    planner.request_load("resident-other:7b")
    planner.complete_load("resident-other:7b")
    t = _ticket(_local_selection(), tmp_path, residency_planner=planner)
    assert t["authorized"] is False and t["refused"] is True
    assert "displacing" in t["reason"]
    assert t["launch"] is None


# ---- a refusal after the durable lease was taken must not leave it counted (validator R1) -------

def test_a_refusal_raised_after_acquire_hands_the_durable_terminal_back(tmp_path):
    ref = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)

    class BreakAfterAcquire(TerminalLeaseLedger):
        """Acquires normally, then fails the very next read — the window in which a lease exists but
        the ticket does not."""

        def in_use(self, subscription_ref: str) -> int:      # noqa: D102
            from node_runtime.supervisor.terminal_lease import LeaseLedgerCorrupt

            raise LeaseLedgerCorrupt("ledger unreadable right after acquire")

    led = BreakAfterAcquire(path=tmp_path / "leases.json", pid_alive=lambda p: p == HOLDER)
    t = _ticket(_frontier_selection(), tmp_path, ledger=led)
    assert t["authorized"] is False and t["lease"] is None
    # the statement "no lease" must be TRUE of the ledger, not merely of the ticket
    assert TerminalLeaseLedger(path=tmp_path / "leases.json",
                               pid_alive=lambda p: p == HOLDER).in_use(ref) == 0
    assert t["governor_released"] is True


# ---- an argv-builder guard is a governed refusal, not a traceback (spec-audit MINOR-8) ----------

def test_a_flag_shaped_model_tag_is_a_refusal_ticket_not_a_crash(tmp_path):
    sel = _local_selection("--sneaky-flag")
    t = _ticket(sel, tmp_path)
    assert t["authorized"] is False and t["refused"] is True
    assert "flag" in t["reason"].lower()


# ---- a codex worker's slug is UNVERIFIED and the ticket says so (spec-audit MINOR-7 / U97) ------

def test_a_codex_ticket_states_that_its_model_id_is_unprobed(tmp_path):
    t = _ticket(_frontier_selection(CODEX_ADAPTER, slug="gpt-5.5"), tmp_path)
    assert t["authorized"] is True
    assert t["model_probe"]["source"] == "unprobed-codex"
    assert t["model_probe"]["model_available"] is None
    assert "U97" in t["model_probe"]["note"]


# ---- a shell-supplied pane id cannot become an arbitrary ledger key (spec-audit MINOR-10) -------

@pytest.mark.parametrize("pane", ["../../etc", "pane 2", "p" * 65, "pane\n2"])
def test_a_pane_id_that_is_not_a_safe_identity_component_is_refused(pane, tmp_path):
    t = _ticket(_local_selection(), tmp_path, pane_id=pane)
    assert t["authorized"] is False and t["refused"] is True
    assert "pane id" in t["reason"]


def test_the_host_option_supplies_the_honesty_fields_not_the_caller(tmp_path):
    """Invariant 3: a caller that flips `verified` (or rewrites the label) must not be able to badge
    a model as VERIFIED. Identity fields select WHICH option; the host says what it IS."""
    host = _frontier_selection()
    forged = _frontier_selection()
    forged["option"]["verified"] = True
    forged["option"]["label"] = "Fable 5 (VERIFIED)"
    t = _ticket(forged, tmp_path, offered_options=_offered(host))
    assert t["authorized"] is True
    assert t["chrome"]["model_verified"] is False          # the host's answer, not the caller's
    assert t["chrome"]["model_label"] == "fable-5"


# ---- U105: the shell reports the env var NAMES it holds, and they are classified too ------------

def test_a_credential_var_only_the_shell_holds_reaches_the_scrub_list(tmp_path, monkeypatch):
    """The end-to-end of U105 through the emitter: the shell says which names IT has, the one
    classifier runs over the union, and the ticket names the shell's spelling — the spelling the
    shell will delete by. Before this the list described the emitter's environment only."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sel = dict(_local_selection(), shell_env_names=["ANTHROPIC_API_KEY", "PATH"])
    t = _ticket(sel, tmp_path, offered_options=_offered(_local_selection()))
    assert t["authorized"] is True
    assert "ANTHROPIC_API_KEY" in t["launch"]["env_scrub_names"]
    assert "PATH" not in t["launch"]["env_scrub_names"]
    assert "env" not in t["launch"]                        # §2.2 — still names, never values


def test_shell_env_names_carrying_a_name_equals_value_pair_is_refused(tmp_path):
    """§2.2 tripwire: this path takes NAMES. A `name=value` entry is a value being pushed at the
    emitter, and a caller that sends one is not one to accept a corrected reading from — the whole
    ticket is refused rather than the pair being split."""
    sel = dict(_local_selection(), shell_env_names=["ANTHROPIC_API_KEY=sk-leaked"])
    t = _ticket(sel, tmp_path, offered_options=_offered(_local_selection()))
    assert t["authorized"] is False and t["refused"] is True
    assert "NAMES only" in t["reason"]
    assert "sk-leaked" not in json.dumps(t), "a refusal must not echo the value back either"
    # its OWN gate id: raised as a bare SpawnRefused these reported the class default
    # `selection_guard`, so any receipt leg asserting that id to prove the SELECTION guard fired
    # would have gone green on an env-payload fault too (spec-audit MINOR-9).
    assert t["refused_by"] == "shell_env_names"


@pytest.mark.parametrize("bad, expect", [
    ("not-a-list", "must be a JSON array"),
    ([123], "non-string entry"),
    ([""], "non-string entry"),
    (["A" * 300], "character entry"),
    ([f"V{i}" for i in range(4097)], "max 4096"),
])
def test_a_malformed_shell_env_names_payload_is_refused_not_ignored(bad, expect, tmp_path):
    """Fail closed, never silently ignore: a caller whose names list is unusable gets a refusal, not
    a ticket whose scrub list quietly describes only this process's environment."""
    sel = dict(_local_selection(), shell_env_names=bad)
    t = _ticket(sel, tmp_path, offered_options=_offered(_local_selection()))
    assert t["authorized"] is False and t["refused"] is True
    assert expect in t["reason"]
    assert t["refused_by"] == "shell_env_names"    # every branch names its own gate, not the default


def test_an_absent_shell_env_names_field_keeps_the_previous_behaviour(tmp_path):
    """Back-compat, stated as a test: a caller that sends no names (every pre-17B caller) still gets
    the emitter's own environment classified — the union is additive, never a new requirement."""
    t = _ticket(_local_selection(), tmp_path)
    assert t["authorized"] is True
    assert isinstance(t["launch"]["env_scrub_names"], list)


# ---- the OP-12 providers through the SAME emitter (18B `.picker`, review round 1) ---------------
# The `.picker` commit taught this emitter both new providers and no test came with it: deleting the
# whole OP-12 branch and reverting `_FRONTIER_ADAPTERS` to the OP-6 pair left all 1858 tests green
# (validator BLOCKING-3). What the branch decides is not cosmetic — it is whether a Grok/Antigravity
# selection is counted as a FRONTIER terminal at all, and what provenance the operator is shown for
# the model id in the ticket.

def _op12_authorized() -> LiveAuthorization:
    """The live authorization an operator citing OP-12 gets: four providers, and — because the cap is
    per provider (§12) — 1 terminal each for the new pair while the OP-6 pair keeps 2."""
    return LiveAuthorization(
        authorized=True,
        providers=frozenset({CLAUDE_CODE_ADAPTER, CODEX_ADAPTER, GROK_ADAPTER, ANTIGRAVITY_ADAPTER}),
        terminals_per_subscription=2, register_row="OP-12", source="(test)",
        reason="test authorization (OP-12)")


@pytest.mark.parametrize("adapter, slug, ref", [
    (GROK_ADAPTER, "grok-4.5", "grok_build_subscription"),
    (ANTIGRAVITY_ADAPTER, "gemini-3.6-flash-high", "google_antigravity_subscription"),
])
def test_an_op12_selection_becomes_a_frontier_ticket_on_its_own_named_subscription(
        adapter, slug, ref, tmp_path):
    led = _ledger(tmp_path)
    t = _ticket(_frontier_selection(adapter, slug=slug), tmp_path, ledger=led,
                live_auth=_op12_authorized())

    assert t["authorized"] is True and t["refused"] is False
    assert t["chrome"]["adapter"] == adapter and t["chrome"]["locality"] == "frontier"
    assert t["launch"]["interactive"] is True and t["launch"]["one_shot"] is False
    # the operator's OWN resource spelling (§12), never the derived `sub-<adapter>` form
    assert t["identity"]["subscription_ref"] == ref
    assert t["lease"]["subscription_ref"] == ref and t["lease"]["durable"] is True
    # …counted at ONE, never merged with the other provider's or with the OP-6 pair's
    assert t["lease"]["allowance"] == 1
    assert led.in_use(ref) == 1
    assert led.in_use(canonical_subscription_ref(CLAUDE_CODE_ADAPTER)) == 0
    assert t["subscription_governed"] is True and t["gates"]["ix3_counted"] is True
    assert t["governor_released"] is True          # the emitter's own count handed back (D-LOOP-1)


@pytest.mark.parametrize("adapter, slug, model_flag", [
    (GROK_ADAPTER, "grok-4.5", GROK_MODEL_FLAG),
    (ANTIGRAVITY_ADAPTER, "gemini-3.6-flash-high", ANTIGRAVITY_MODEL_FLAG),
])
def test_an_op12_ticket_states_that_its_model_id_came_from_the_cli_enumeration(adapter, slug,
                                                                               model_flag,
                                                                               tmp_path):
    """Provenance, not confidence: these two CLIs publish their ids, so the ticket may say the CLI
    named this one — which is stronger than codex's unprobed label and weaker than a live reply. It
    must reuse NEITHER neighbour's wording (that is how `unprobed` reads as `verified`)."""
    t = _ticket(_frontier_selection(adapter, slug=slug), tmp_path, live_auth=_op12_authorized())
    probe = t["model_probe"]
    assert probe["source"] == "cli-enumeration"
    assert probe["model"] == slug and probe["label"] == slug
    assert probe["model_available"] is True
    # the enumerated id is what the CLI is actually asked for — under EACH provider's own model flag
    # (`-m` for grok, `--model` for agy: §14's rule that a provider is addressed in its own terms)
    argv = t["launch"]["argv"]
    assert argv[argv.index(model_flag) + 1] == slug
    assert "no live session has answered" in probe["note"]
    assert probe["source"] not in ("unprobed-codex", "probe-ledger")


def test_a_second_op12_terminal_is_refused_where_a_second_claude_terminal_is_not(tmp_path):
    """The allowance-1 fact, measured rather than asserted: one held Grok terminal exhausts the
    subscription, while the same ledger admits a second claude_code terminal (§12 — the caps are per
    provider and are never merged)."""
    led = _ledger(tmp_path)
    led.acquire(subscription_ref="grok_build_subscription", provider=GROK_ADAPTER,
                node_id="other-grok", allowance=1, holder_pid=HOLDER, purpose="held elsewhere",
                session_id="s1")
    refused = _ticket(_frontier_selection(GROK_ADAPTER, slug="grok-4.5"), tmp_path, ledger=led,
                      live_auth=_op12_authorized())
    assert refused["authorized"] is False and refused["refused"] is True
    assert refused["launch"] is None and refused["lease"] is None

    led2 = _ledger(tmp_path)
    led2.acquire(subscription_ref=canonical_subscription_ref(CLAUDE_CODE_ADAPTER),
                 provider=CLAUDE_CODE_ADAPTER, node_id="other-claude", allowance=2,
                 holder_pid=HOLDER, purpose="held elsewhere", session_id="s1")
    allowed = _ticket(_frontier_selection(), tmp_path, ledger=led2, live_auth=_op12_authorized())
    assert allowed["authorized"] is True, "the OP-6 pair's allowance of 2 must be unchanged (§17)"


@pytest.mark.parametrize("adapter", [GROK_ADAPTER, ANTIGRAVITY_ADAPTER])
def test_an_op12_selection_under_an_op6_config_is_refused_not_quietly_localised(adapter, tmp_path):
    """The state this host is actually in: the operator's live switch cites OP-6, which does not
    authorize either provider. The refusal must be a live-authorization refusal — never a ticket, and
    never a fall-through to the LOCAL branch, which would be a frontier CLI running unleased."""
    t = _ticket(_frontier_selection(adapter, slug="grok-4.5"), tmp_path)   # _authorized() == OP-6
    assert t["authorized"] is False and t["refused"] is True
    assert t["launch"] is None and t["lease"] is None
    assert t["subscription_governed"] is False
    assert adapter in t["reason"]


# ---- W-13 / R-15: the durable lease leaks on any NON-governance exception -----------------------
# `led.acquire(...)` takes the durable I-X3 terminal, and the ONLY release sits inside
# `except _GOVERNANCE_REFUSALS`. The `finally` releases the in-process governor and says in its own
# comment that "the durable lease is untouched". `_GOVERNANCE_REFUSALS` excludes OSError, KeyError
# and IllegalTransition -- and `_register_pane_node`, which runs AFTER the acquire, reaches
# `os.fsync` and raises a bare OSError on a full or failing disk.
#
# The retained lease's `holder_pid` is the long-lived Electron process, so dead-holder reaping can
# never fire; with grok's allowance of 1 the subscription wedges for the life of the app.
#
# Donor: `tools/live/emit_conductor_dispatch.py:182-187` releases the durable lease on the failure
# path and re-raises, so the failure is not swallowed and the terminal is not stranded.

class _RegistrarThatFailsOnDisk:
    """A registrar whose append hits a full/failing disk -- the OSError `_register_pane_node` can
    really raise, from inside the try, AFTER the durable lease was taken."""

    def __init__(self, path):
        self.log_path = path
        self.closed = False

    def register_pane_session(self, *a, **kw):
        raise OSError(28, "No space left on device")

    def close(self):
        self.closed = True


def test_a_non_governance_failure_after_the_acquire_does_not_strand_the_durable_lease(tmp_path):
    """W-13/R-15 NEGATIVE. An OSError is not a governance refusal, so it escapes the only release
    the emitter has. The terminal must still come back: a stranded lease outlives this process."""
    led = _ledger(tmp_path)
    sub = canonical_subscription_ref(GROK_ADAPTER)
    registrar = _RegistrarThatFailsOnDisk(tmp_path / "nodes.jsonl")

    with pytest.raises(OSError):
        _ticket(_frontier_selection(GROK_ADAPTER, slug="grok-4.5"), tmp_path,
                ledger=led, live_auth=_authorized(GROK_ADAPTER), registrar=registrar)

    assert led.in_use(sub) == 0, (
        "the durable I-X3 terminal was left counted for a session that will never exist; its "
        "holder_pid is the long-lived shell, so dead-holder reaping can never reclaim it")
    assert registrar.closed is True, "the node log's exclusive lock must still be released"


def test_a_governed_refusal_after_the_acquire_still_releases_and_still_says_lease_null(tmp_path):
    """POSITIVE control for the branch that already worked: a governance refusal must keep behaving
    exactly as it did -- ticket, `lease: null`, and the terminal handed back."""
    led = _ledger(tmp_path)
    sub = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)
    t = _ticket(_frontier_selection(slug="fable-5"), tmp_path, ledger=led,
                live_auth=_authorized(CLAUDE_CODE_ADAPTER), operator_terms_confirmed=False)
    assert t["refused"] is True
    assert t["lease"] is None
    assert led.in_use(sub) == 0


def test_an_authorized_ticket_still_KEEPS_its_durable_lease(tmp_path):
    """POSITIVE. The release must not become unconditional: a successful ticket hands the shell a
    terminal that is still held, because the session outlives this emitter."""
    led = _ledger(tmp_path)
    sub = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)
    t = _ticket(_frontier_selection(), tmp_path, ledger=led)
    assert t["authorized"] is True
    assert t["lease"]["durable"] is True
    assert led.in_use(sub) == 1, "a successful launch must KEEP its durable terminal"


# ---- W-76: the durable side effects are DISCLOSED where the operator actually reads ----

def test_usage_text_discloses_the_three_side_effects(capsys):
    """W-76. A bare invocation prints usage; that text used to name none of the three durable
    effects of emit mode - the terminal it takes, the node record it writes, and the consent
    literal it asserts. Disclosure only: nothing behavioural moved."""
    import tools.live.emit_worker_launch as mod

    code = mod.main([])
    assert code == 2
    err = capsys.readouterr().err
    assert "takes a terminal" in err.lower(), "usage does not disclose the durable I-X3 terminal"
    assert "node record" in err.lower(), "usage does not disclose the durable node record"
    assert "operator_terms_confirmed" in err, "usage does not disclose the consent literal"


def test_module_docstring_names_all_four_frontier_adapters():
    """W-76. The docstring still claimed `claude_code` / `openai_codex_cli`, the OP-6 scope and
    nothing else - false since OP-12 added grok_build + google_antigravity to
    FRONTIER_PANE_ADAPTERS, which is what the code actually delegates to."""
    import tools.live.emit_worker_launch as mod

    doc = mod.__doc__ or ""
    for adapter in ("claude_code", "openai_codex_cli", "grok_build", "google_antigravity"):
        assert adapter in doc, f"the module docstring omits {adapter}"
    assert "the OP-6 scope and nothing else" not in doc, (
        "the stale two-provider claim is still present")
