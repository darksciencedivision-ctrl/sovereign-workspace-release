"""Governed CONDUCTOR LAUNCH TICKET emitter (Phase 17A `.lease`).

`emit_conductor_spawn` proved pane 1 goes through the full live-gate chain, but it deliberately
DEFERRED the interactive `claude` drive and tore its I-X3 terminal down before emitting — so the
shell had gates without a session, and a count that died with the emitter. 17A needs the opposite
shape: a ticket the SHELL can execute, whose terminal stays counted for as long as the shell holds
the session.

These tests pin that contract without a live call:

  * the ticket is produced ONLY through the same gate chain (`spawn_conductor_pane`): live-operation
    authorization, provider-live, R8 §6 operator terms, `claude` presence, I-X3;
  * the ticket carries an INTERACTIVE argv (no `-p` / `--output-format json`) and the NAMES (never
    the values, §2.2) of the credential-bearing env vars the shell must drop before spawning;
  * the durable lease is HELD when the ticket is emitted (`in_use == 1`) — unlike the 16C spawn feed,
    the count deliberately survives the emitter, because the session will;
  * the in-process governor is still released (D-LOOP-1 for the emitter's own bookkeeping) — the
    DURABLE lease is the only thing that outlives it, and it is explicitly named in the ticket;
  * a durable count already at the allowance REFUSES the ticket — the shell cannot launch an
    uncounted third terminal even though its own governor is empty;
  * every governance refusal (unauthorized live config, unconfirmed terms, absent CLI, corrupt
    ledger) yields a fail-closed REFUSAL ticket with a reason and NO argv — never a fabricated
    authorization, and never a leaked lease;
  * release is a first-class emitter mode, so the shell can hand the terminal back when the session
    ends (and the loop can prove no lease outlived the work unit).
"""
from __future__ import annotations

import json

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from adapters.frontier.claude_model_probe import ModelProbeLedger, ModelProbeRecord
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger
from node_runtime.supervisor.conductor_permission_profile import HOOK_PATH
from tools.live.emit_conductor_launch import (
    CONDUCTOR_NODE_ID,
    CONDUCTOR_SUBSCRIPTION_REF,
    CONDUCTOR_WORKSPACE,
    LAUNCH_TICKET_SCHEMA,
    LEASE_RELEASE_SCHEMA,
    LEASE_STATUS_SCHEMA,
    build_conductor_launch_ticket,
    build_lease_release,
    build_lease_release_session,
    build_lease_status,
    main,
)

HOLDER = 4242


def _authorized() -> LiveAuthorization:
    return LiveAuthorization(
        authorized=True, providers=frozenset({CLAUDE_CODE_ADAPTER}), terminals_per_subscription=2,
        register_row="OP-6", source="(test)", reason="test authorization")


def _ledger(tmp_path, *, alive=(HOLDER,)):
    live = set(alive)
    return TerminalLeaseLedger(path=tmp_path / "leases.json", pid_alive=lambda p: p in live)


def _ticket(tmp_path, **over):
    kwargs = dict(
        holder_pid=HOLDER, ledger=_ledger(tmp_path), live_auth=_authorized(),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
        cli_present=True)
    kwargs.update(over)
    return build_conductor_launch_ticket(**kwargs)


# ---- the authorized ticket ------------------------------------------------

def test_authorized_ticket_is_interactive_and_gated(tmp_path):
    t = _ticket(tmp_path)
    assert t["schema"] == LAUNCH_TICKET_SCHEMA
    assert t["authorized"] is True and t["refused"] is False and t["reason"] is None
    assert t["node_state"] == "launch_authorized"
    launch = t["launch"]
    assert launch["argv"][0] == "claude"
    assert launch["interactive"] is True and launch["one_shot"] is False
    assert "-p" not in launch["argv"] and "--output-format" not in launch["argv"]
    # `locality` is new in LOCAL-01 F-3 and says WHICH gate chain ran. The conductor seat is
    # agnostic (ENTRY 018), so a ticket must state whether it was gated as a subscription-backed
    # frontier session or as a local one that authorizes no spend — otherwise the four verdicts
    # below are unreadable, because two of them are "not applicable" on the local path rather
    # than "false". The frontier verdicts themselves are unchanged, which is the point.
    assert t["gates"] == {
        "live_operation_authorized": True, "operator_terms_confirmed": True,
        "cli_present": True, "ix3_counted": True, "locality": "frontier"}
    # the governed identity the session must be spawned UNDER — the shell cannot invent it
    assert t["identity"]["node_id"] == CONDUCTOR_NODE_ID
    assert t["identity"]["permission_profile_id"]
    # The supervisor-issued profile is now APPLIED, not merely named.  A marked voice turn arms a
    # deny-all PreToolUse boundary before the model sees the prompt; ordinary typed turns retain the
    # attended conductor's governed tool path.
    boundary = t["authority_boundary"]
    assert boundary["schema"] == "voice_turn_boundary@1.0"
    assert boundary["supervisor_owned"] is True
    assert boundary["non_executing_voice_turns"] is True
    assert boundary["enforced_by_supervisor_process"] is False
    assert boundary["permission_profile_id"] == t["identity"]["permission_profile_id"]
    assert boundary["prompt_marker_format"] == (
        "[[SOVEREIGN_VOICE_CHAT_V2:{turn_id_hex32}]] "
    )
    assert len(boundary["hook_sha256"]) == 64
    assert boundary["hook_argv"] == [boundary["hook_runtime"], str(HOOK_PATH)]
    settings_at = launch["argv"].index("--settings")
    settings = json.loads(launch["argv"][settings_at + 1])
    assert set(settings["hooks"]) >= {
        "UserPromptSubmit", "PreToolUse", "PermissionRequest", "Stop", "StopFailure",
        "SessionEnd",
    }
    assert settings["hooks"]["PreToolUse"][0]["matcher"] == ".*"
    # …and the ticket says plainly what remains NOT contained.
    assert t["containment"]["authorized"] is True
    assert t["containment"]["supervisor_bound"] is False
    # …and, since `.pty`, WHO binds it and exactly what that binding must cover — the OS job-object
    # half stays honestly owed (U25), unchanged for every shell session.
    assert "SessionManager.spawn" in t["containment"]["bound_by"]
    assert t["containment"]["requires"] == ["supervised_admission", "workspace_cwd_binding",
                                            "credential_env_scrub", "permission_profile_binding",
                                            "lease_release_on_session_exit"]
    assert t["containment"]["os_job_object"] is False and "U25" in t["containment"]["owed_to"]
    # The permission-profile binding is no longer owed. OS containment and heartbeat remain named.
    assert t["containment"]["still_owed"] == ["os_job_object_or_acl (U25)",
                                              "node_heartbeat (U78(a))"]
    assert t["identity"]["permission_profile_id"]
    # the chrome the shell renders for pane 1 comes from the SAME governed spawn, not a JS literal
    assert t["chrome"]["role"] == "conductor" and t["chrome"]["governed"] is True
    assert t["chrome"]["interactive"] is True


def test_ticket_carries_scrub_names_never_values(tmp_path):
    """§2.2: the shell must drop the credential-bearing vars before spawning, so it needs their
    NAMES. It never needs — and never receives — a value."""
    t = _ticket(tmp_path)
    names = t["launch"]["env_scrub_names"]
    assert isinstance(names, list) and names == sorted(names)
    assert all(isinstance(n, str) for n in names)
    assert t["launch"]["env_credential_scrubbed"] is True
    blob = json.dumps(t)
    assert "ANTHROPIC_API_KEY=" not in blob  # nothing key=value shaped is ever emitted
    for n in names:
        assert f'"{n}"' in blob  # present as a NAME only
    # no environment mapping anywhere in the ticket
    assert "env" not in t["launch"]


def test_the_durable_lease_is_held_after_the_emitter_returns(tmp_path):
    """The load-bearing difference from `emit_conductor_spawn`: the count SURVIVES, because the
    session will. The in-process governor is still released (the emitter's own D-LOOP-1)."""
    led = _ledger(tmp_path)
    t = _ticket(tmp_path, ledger=led)
    lease = t["lease"]
    assert lease["node_id"] == CONDUCTOR_NODE_ID
    assert lease["subscription_ref"] == CONDUCTOR_SUBSCRIPTION_REF
    assert lease["holder_pid"] == HOLDER
    assert lease["in_use"] == 1 and lease["allowance"] == 2
    assert lease["durable"] is True
    assert led.in_use(CONDUCTOR_SUBSCRIPTION_REF) == 1          # still held on the file
    assert t["governor_released"] is True                        # the in-process count is not leaked
    assert t["release_with"] == ["--release-lease", lease["lease_id"]]


def test_ticket_is_idempotent_for_the_same_node(tmp_path):
    led = _ledger(tmp_path)
    a = _ticket(tmp_path, ledger=led)
    b = _ticket(tmp_path, ledger=led)
    assert a["lease"]["lease_id"] == b["lease"]["lease_id"]
    assert led.in_use(CONDUCTOR_SUBSCRIPTION_REF) == 1


# ---- `.pty`: per-SESSION terminals, workspace binding, session reclaim -----

def test_two_sessions_of_pane_one_are_two_counted_terminals(tmp_path):
    """U75: the conductor node id is a constant, so node-keyed counting reported two REAL live
    sessions as one terminal. The ticket now counts per session — and the second ticket sees the
    first session's terminal in its own gate chain."""
    led = _ledger(tmp_path)
    a = _ticket(tmp_path, ledger=led, session_id="pane-1#1")
    b = _ticket(tmp_path, ledger=led, session_id="pane-1#2")
    assert a["authorized"] is True and b["authorized"] is True
    assert a["lease"]["lease_id"] != b["lease"]["lease_id"]
    assert a["lease"]["session_id"] == "pane-1#1" and b["lease"]["session_id"] == "pane-1#2"
    assert b["lease"]["in_use"] == 2
    assert led.in_use(CONDUCTOR_SUBSCRIPTION_REF) == 2
    # and the THIRD session of the same pane is refused by the durable cap, not silently adopted
    c = _ticket(tmp_path, ledger=led, session_id="pane-1#3")
    assert c["refused"] is True and "allowance" in c["reason"]


def test_the_ticket_identifies_the_session_and_its_bound_workspace(tmp_path):
    """The shell cannot invent either: the session key it must count under and the cwd it must bind
    the ConPTY to both come from the governed ticket (U78(a) workspace-binding half)."""
    t = _ticket(tmp_path, session_id="pane-1#7", workspace=str(tmp_path / "ws"))
    assert t["identity"]["session_id"] == "pane-1#7"
    assert t["identity"]["workspace"] == str(tmp_path / "ws")
    assert t["launch"]["cwd"] == str(tmp_path / "ws")


def test_release_session_reclaims_an_undelivered_ticket(tmp_path):
    """U77: the lease is taken Python-side BEFORE the shell parses the ticket, so a shape refusal or
    a timeout used to strand a terminal the shell could not name. It names the SESSION instead —
    chosen before it asked — and reclaims exactly that one."""
    led = _ledger(tmp_path)
    keep = _ticket(tmp_path, ledger=led, session_id="pane-1#live")
    _ticket(tmp_path, ledger=led, session_id="pane-1#undelivered")
    assert led.in_use(CONDUCTOR_SUBSCRIPTION_REF) == 2

    out = build_lease_release_session("pane-1#undelivered", ledger=led)
    assert out["schema"] == LEASE_RELEASE_SCHEMA
    assert out["released"] is True and out["released_count"] == 1
    assert led.in_use(CONDUCTOR_SUBSCRIPTION_REF) == 1
    assert [ln.lease_id for ln in led.live(CONDUCTOR_SUBSCRIPTION_REF)] == [keep["lease"]["lease_id"]]
    again = build_lease_release_session("pane-1#undelivered", ledger=led)
    assert again["released"] is False and again["error"] is None    # idempotent, not an error


def test_release_session_is_never_a_wildcard(tmp_path):
    """An empty key must reclaim NOTHING — otherwise a shell that lost its session id could zero the
    operator's own count."""
    led = _ledger(tmp_path)
    _ticket(tmp_path, ledger=led, session_id="pane-1#1")
    out = build_lease_release_session("", ledger=led)
    assert out["released"] is False and out["released_count"] == 0
    assert led.in_use(CONDUCTOR_SUBSCRIPTION_REF) == 1


def test_the_launch_ticket_and_the_16c_spawn_feed_count_ONE_subscription(tmp_path):
    """U76: the cap is enforced PER REF, so the launch path and the 16C governed spawn feed (which
    runs on every shell start) must not open two buckets for the operator's one subscription. Stated
    between the two product constants — comparing either to the helper that defines the spelling
    would pass while the other still drifted."""
    from tools.live.emit_conductor_spawn import CONDUCTOR_SUBSCRIPTION_REF as SPAWN_REF

    assert CONDUCTOR_SUBSCRIPTION_REF == SPAWN_REF
    t = _ticket(tmp_path, session_id="pane-1#1")
    assert t["lease"]["subscription_ref"] == SPAWN_REF


def test_governor_released_is_about_OUR_node_not_an_empty_governor(tmp_path):
    """Regression (gate-validator R2 / spec-audit F5): the in-process governor is deliberately
    SEEDED with the durable leases OTHER processes hold, so "governor empty" is the wrong question
    and would report a phantom leak the moment a worker holds a terminal. The claim is only ever
    about the terminal THIS emitter acquired."""
    led = _ledger(tmp_path)
    led.acquire(subscription_ref=CONDUCTOR_SUBSCRIPTION_REF, provider=CLAUDE_CODE_ADAPTER,
                node_id="worker-a", allowance=2, holder_pid=HOLDER)
    t = _ticket(tmp_path, ledger=led)
    assert t["authorized"] is True                # one slot of two was still free
    assert t["governor_released"] is True         # our node handed its in-process count back
    assert t["lease"]["in_use"] == 2              # and the durable count sees BOTH holders
    assert t["lease"]["seeded_from_ledger"] == ["worker-a"]


def test_refusal_reports_the_gate_that_actually_failed(tmp_path):
    """Regression (spec-audit F9): an I-X3 refusal used to emit `cli_present:false`, telling the
    operator the CLI was missing when it had been detected. Gates are OBSERVED up front."""
    led = _ledger(tmp_path)
    for n in ("worker-a", "worker-b"):
        led.acquire(subscription_ref=CONDUCTOR_SUBSCRIPTION_REF, provider=CLAUDE_CODE_ADAPTER,
                    node_id=n, allowance=2, holder_pid=HOLDER)
    t = _ticket(tmp_path, ledger=led)
    assert t["refused"] is True and "allowance" in t["reason"]
    assert t["gates"]["cli_present"] is True             # it WAS present — do not misdiagnose
    assert t["gates"]["live_operation_authorized"] is True
    assert t["gates"]["ix3_counted"] is False           # the one that actually failed


# ---- fail-closed refusals -------------------------------------------------

def test_durable_count_at_allowance_refuses_the_ticket(tmp_path):
    """Two terminals already held by OTHER processes ⇒ no third, even though this emitter's own
    governor starts empty. This is the whole reason the ledger exists."""
    led = _ledger(tmp_path)
    led.acquire(subscription_ref=CONDUCTOR_SUBSCRIPTION_REF, provider=CLAUDE_CODE_ADAPTER,
                node_id="worker-a", allowance=2, holder_pid=HOLDER)
    led.acquire(subscription_ref=CONDUCTOR_SUBSCRIPTION_REF, provider=CLAUDE_CODE_ADAPTER,
                node_id="worker-b", allowance=2, holder_pid=HOLDER)
    t = _ticket(tmp_path, ledger=led)
    assert t["authorized"] is False and t["refused"] is True
    assert "allowance" in t["reason"]
    assert t["node_state"] == "launch_refused"
    assert t["launch"] is None and t["chrome"] is None and t["lease"] is None
    assert led.in_use(CONDUCTOR_SUBSCRIPTION_REF) == 2          # the refusal leaked nothing


def test_unauthorized_live_config_refuses(tmp_path):
    unauth = LiveAuthorization.denied("no live_operation config (test)")
    led = _ledger(tmp_path)
    t = _ticket(tmp_path, ledger=led, live_auth=unauth)
    assert t["authorized"] is False and t["refused"] is True and t["launch"] is None
    assert t["gates"]["live_operation_authorized"] is False
    assert led.in_use(CONDUCTOR_SUBSCRIPTION_REF) == 0


def test_unconfirmed_operator_terms_refuse(tmp_path):
    led = _ledger(tmp_path)
    t = _ticket(tmp_path, ledger=led, operator_terms_confirmed=False)
    assert t["refused"] is True and "LiveTermsNotConfirmed" in t["reason"]
    assert t["gates"]["operator_terms_confirmed"] is False
    assert led.in_use(CONDUCTOR_SUBSCRIPTION_REF) == 0


def test_absent_cli_refuses(tmp_path):
    led = _ledger(tmp_path)
    t = _ticket(tmp_path, ledger=led, cli_present=False)
    assert t["refused"] is True and "ClaudeCliUnavailable" in t["reason"]
    assert t["gates"]["cli_present"] is False
    assert led.in_use(CONDUCTOR_SUBSCRIPTION_REF) == 0


def test_corrupt_ledger_refuses_rather_than_launching_uncounted(tmp_path):
    p = tmp_path / "leases.json"
    p.write_text("{not json", encoding="utf-8")
    led = TerminalLeaseLedger(path=p, pid_alive=lambda x: True)
    t = _ticket(tmp_path, ledger=led)
    assert t["refused"] is True and "LeaseLedgerCorrupt" in t["reason"]
    assert t["launch"] is None


# ---- release + status -----------------------------------------------------

def test_release_hands_the_terminal_back(tmp_path):
    led = _ledger(tmp_path)
    t = _ticket(tmp_path, ledger=led)
    out = build_lease_release(t["lease"]["lease_id"], ledger=led)
    assert out["schema"] == LEASE_RELEASE_SCHEMA
    assert out["released"] is True and out["lease_id"] == t["lease"]["lease_id"]
    assert led.in_use(CONDUCTOR_SUBSCRIPTION_REF) == 0
    again = build_lease_release(t["lease"]["lease_id"], ledger=led)
    assert again["released"] is False and again["error"] is None   # idempotent, not an error


def test_lease_status_is_the_observable_count(tmp_path):
    led = _ledger(tmp_path)
    _ticket(tmp_path, ledger=led)
    st = build_lease_status(ledger=led, live_auth=_authorized())
    assert st["schema"] == LEASE_STATUS_SCHEMA
    assert st["allowance"] == 2
    assert st["subscriptions"][CONDUCTOR_SUBSCRIPTION_REF]["in_use"] == 1
    assert st["subscriptions"][CONDUCTOR_SUBSCRIPTION_REF]["holders"][0]["node_id"] == CONDUCTOR_NODE_ID


# ---- CLI surface ----------------------------------------------------------

def test_cli_requires_a_holder_pid(capsys):
    """A lease without a real owner is not a lease — the CLI refuses rather than defaulting to its
    own (about-to-exit) pid, which would count a terminal nobody holds."""
    assert main(["--emit-conductor-launch"]) == 2
    assert "--holder-pid" in capsys.readouterr().err


def test_cli_requires_a_session_id(capsys):
    """U75 at the CLI boundary: a ticket authorizes ONE session, so it is refused without the key
    that session will be counted under (and reclaimed by)."""
    assert main(["--emit-conductor-launch", "--holder-pid", "4242"]) == 2
    assert "--session-id" in capsys.readouterr().err


def test_cli_release_session_prints_one_json_line(tmp_path, capsys, monkeypatch):
    led = _ledger(tmp_path)
    monkeypatch.setattr("tools.live.emit_conductor_launch._default_ledger", lambda: led)
    _ticket(tmp_path, ledger=led, session_id="pane-1#1")
    assert main(["--release-session", "pane-1#1"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == LEASE_RELEASE_SCHEMA and out["released"] is True
    assert led.in_use(CONDUCTOR_SUBSCRIPTION_REF) == 0
    assert main(["--release-session"]) == 2


def test_cli_usage_exits_two(capsys):
    assert main([]) == 2
    assert "usage" in capsys.readouterr().err


def test_cli_release_prints_one_json_line(tmp_path, capsys, monkeypatch):
    led = _ledger(tmp_path)
    monkeypatch.setattr("tools.live.emit_conductor_launch._default_ledger", lambda: led)
    t = _ticket(tmp_path, ledger=led)
    assert main(["--release-lease", t["lease"]["lease_id"]]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == LEASE_RELEASE_SCHEMA and out["released"] is True
    assert led.in_use(CONDUCTOR_SUBSCRIPTION_REF) == 0


# ---- the probed `--model` slug (Phase 17A `.roundtrip`) -------------------
# `.pty` launched with the operator's selection LABEL as the slug, and the CLI answered every prompt
# with "There's an issue with the selected model (fable-5)". The ticket now takes its slug from the
# recorded live probe — OFFLINE (this emitter still makes no live call), and never silently.

def _probe_ledger(tmp_path, record=None):
    led = ModelProbeLedger(path=tmp_path / "probe.json")
    if record is not None:
        led.write(record)
    return led


def _probe_record(**over):
    kw = dict(label="fable-5", candidates=("fable-5", "claude-fable-5"),
              accepted_slug="claude-fable-5", checkpoint="claude-fable-5-20260701",
              conclusive=True, is_fallback=False, attempts=(), probed_at="2026-07-25T00:00:00Z",
              note="accepted")
    kw.update(over)
    return ModelProbeRecord(**kw)


def test_ticket_asks_for_the_slug_the_cli_actually_accepted(tmp_path):
    t = _ticket(tmp_path, probe_ledger=_probe_ledger(tmp_path, _probe_record()))
    assert t["launch"]["argv"][1:3] == ["--model", "claude-fable-5"]
    assert "--settings" in t["launch"]["argv"]
    assert t["chrome"]["model_label"] == "fable-5"          # the SELECTION label is unchanged
    assert t["chrome"]["model_slug"] == "claude-fable-5"
    assert t["chrome"]["is_fallback"] is False
    assert t["model_probe"]["source"] == "probe-ledger"
    assert t["model_probe"]["model_available"] is True


def test_a_conclusively_unavailable_model_launches_on_the_cli_default_and_says_so(tmp_path):
    t = _ticket(tmp_path, probe_ledger=_probe_ledger(
        tmp_path, _probe_record(accepted_slug=None, checkpoint=None, is_fallback=True,
                                note="every candidate rejected")))
    assert "--model" not in t["launch"]["argv"]             # the CLI default, deliberately
    assert t["chrome"]["is_fallback"] is True               # surfaced in the chrome, never silent
    assert "unavailable" in t["selection_record"]["executing"]["note"]
    assert t["selection_record"]["executing"]["is_fallback"] is True
    assert t["model_probe"]["model_available"] is False


def test_an_unprobed_host_is_unchanged_by_the_probe_wiring(tmp_path):
    """Fail-closed direction for a CACHE: no record ⇒ carry the operator's label verbatim, exactly
    as the ticket did before the probe existed. 'Not probed' must never read as 'unavailable'."""
    t = _ticket(tmp_path, probe_ledger=_probe_ledger(tmp_path))
    assert t["launch"]["argv"][1:3] == ["--model", "fable-5"]
    assert "--settings" in t["launch"]["argv"]
    assert t["chrome"]["is_fallback"] is False
    assert t["model_probe"]["source"] == "unprobed"
    assert t["model_probe"]["model_available"] is None


def test_an_inconclusive_probe_does_not_demote_the_selection(tmp_path):
    t = _ticket(tmp_path, probe_ledger=_probe_ledger(
        tmp_path, _probe_record(conclusive=False, accepted_slug=None, checkpoint=None,
                                note="auth/rate — inconclusive")))
    assert t["launch"]["argv"][1:3] == ["--model", "fable-5"]
    assert "--settings" in t["launch"]["argv"]
    assert t["model_probe"]["source"] == "inconclusive"


# ---- W-11 / A-1: the descriptor path must not defeat the probe ledger ---------------------------
# Every test above passes NO descriptor, so they exercise the working branch -- which is why they
# stayed green while the shipped path was broken. `main()` ALWAYS passes
# `descriptor=load_runtime_conductor_descriptor()`, and on any clone without the operator's host
# switch that descriptor resolves `claude_code`/`fable-5` -- the exact slug the probe ledger records
# the CLI rejecting, and the slug 17A `.roundtrip` watched the CLI answer every prompt with
# "There's an issue with the selected model (fable-5)".
#
# The descriptor branch set `model = desc.model_id` and `model_available = True` itself, so the
# ledger consult guarded by `model is None and model_available is None` could never fire on that
# path, and the ticket stamped `source: "registered-exact-slug"` on a label nothing had confirmed.
# `source: unprobed` with a null model is correct; a non-null model there is the trap; and
# "registered-exact-slug" on an unprobed label is the trap wearing a disguise.

def _descriptor(**over):
    from control_plane.conductor.registry import ConductorDescriptor

    kw = dict(role="conductor", provider_id="claude_code", adapter_id=CLAUDE_CODE_ADAPTER,
              model_id="fable-5", display_name="Fable 5",
              permission_profile_id="pp-conductor", workspace=CONDUCTOR_WORKSPACE,
              subscription_ref=CONDUCTOR_SUBSCRIPTION_REF,
              selection_source="recorded_default_selection")
    kw.update(over)
    return ConductorDescriptor(**kw)


def test_a_descriptor_slug_is_still_resolved_through_the_probe_ledger(tmp_path):
    """POSITIVE: a descriptor whose label the ledger has ACCEPTED launches with the accepted slug."""
    t = _ticket(tmp_path, descriptor=_descriptor(),
                probe_ledger=_probe_ledger(tmp_path, _probe_record()))
    assert t["model_probe"]["source"] == "probe-ledger"
    assert t["model_probe"]["model_available"] is True
    assert t["launch"]["argv"][1:3] == ["--model", "claude-fable-5"]
    # …and the label the operator reads is untouched by the probe. On a DESCRIPTOR launch that label
    # is the descriptor's display name (`conductor_pane_spawn.py:272`), which is pre-existing and
    # not this unit's property; what W-11 changes is only which SLUG the CLI is asked for.
    assert t["chrome"]["model_label"] == "Fable 5"
    assert t["chrome"]["model_slug"] == "claude-fable-5"


def test_a_descriptor_never_claims_a_registered_slug_the_ledger_did_not_confirm(tmp_path):
    """NEGATIVE: unprobed must read as unprobed. This is the label that made the defect invisible."""
    t = _ticket(tmp_path, descriptor=_descriptor(), probe_ledger=_probe_ledger(tmp_path))
    assert t["model_probe"]["source"] != "registered-exact-slug", (
        "an unprobed descriptor label was stamped as a registered exact slug")
    assert t["model_probe"]["source"] == "unprobed"
    assert t["model_probe"]["model_available"] is None
    assert t["launch"]["argv"][1:3] == ["--model", "fable-5"]   # the label, carried verbatim


def test_a_descriptor_for_a_conclusively_rejected_slug_falls_back_and_says_so(tmp_path):
    """NEGATIVE: the ledger's FALLBACK verdict must reach a descriptor launch too, or the conductor
    is launched asking for a slug the CLI has already rejected -- the black pane with extra steps."""
    t = _ticket(tmp_path, descriptor=_descriptor(),
                probe_ledger=_probe_ledger(tmp_path, _probe_record(
                    accepted_slug=None, checkpoint=None, is_fallback=True,
                    note="every candidate rejected")))
    assert t["model_probe"]["model_available"] is False
    assert t["model_probe"]["source"] == "probe-ledger"
    assert "--model" not in t["launch"]["argv"]        # the CLI default, deliberately
    assert t["chrome"]["is_fallback"] is True
