"""THE TIER-4 CROSS-ENTRY-POINT CONTROL-STATE MATRIX (obligation 1 of the Tier-4 boundary).

One synthetic provider observation is put through the three PRODUCTION entry points that can reach
a control decision about a provider, and their answers are compared:

    the same (exit code, stdout, stderr) triple
          |-- adapters.frontier.provider_cli_common.probe_provider_cli   (the adapter probe)
          |-- tools.providers.frontier_provider_recon.probe_status       (the recon probe)
          '-- FrontierProviderCliBackend.generate                        (the runtime path)

WHY THIS EXISTS. Tier 4 repaired eleven defects and most of them were one shape: a surface reading
prose for a fact that structured evidence already carried. Every one of those surfaces answers a
question about the SAME provider, and W-49 ([[U468]]) proved they had already silently drifted --
the two probes gave OPPOSITE auth verdicts for one real `grok models` call. Per-unit tests pin each
surface against its own expectations; nothing until now asserted that the surfaces AGREE.

WHAT IT IS NOT. It is deliberately not a fourth classifier. Nothing here re-reads a transcript, and
no marker list, parser or shape rule is duplicated. Each surface is asked for the control state IT
ALREADY PUBLISHES -- `ProviderCliProbe.auth_state` / `.selectable_models()`, `ProviderStatus.state`
/ `.auth_state` / `.auth_confirmed`, and what `generate` RAISES -- and the projections below map
those published values onto one small vocabulary so they can be compared at all. A projection that
had to parse anything would be the fourth classifier, and would make this file agree with itself
rather than with the product.

THE INVARIANT, and it is deliberately weaker than equality. The three surfaces serve different
purposes and return different objects; a probe reports what is KNOWN about a provider, the runtime
reports what happened to ONE invocation. They may REPRESENT a state differently. They may not
DISAGREE about an authoritative control decision:

  * no surface may report a session ASSERTED while another reports authentication BLOCKED;
  * if any surface reports authentication BLOCKED, no surface may PERMIT execution;
  * if no surface reports authentication BLOCKED, no surface may pause ON AUTHENTICATION -- an
    auth pause nothing established is [[U467]]/W-48's defect, and it takes a whole node down.

Cross-references: [[U462]] W-44, [[U464]] W-45, [[U465]] W-46, [[U466]] W-47, [[U467]] W-48,
[[U468]] W-49, [[U470]] W-50, [[U471]] W-51.
"""
from __future__ import annotations

import types
from dataclasses import dataclass

import pytest

from adapters.frontier import grok_build as GB
from adapters.frontier import process_tree
from adapters.frontier import provider_cli_common as C
from tools.live.enumerate_pane_picker import _op12_inventory
from tools.providers import frontier_provider_recon as R

# --------------------------------------------------------------------------------------------
# The comparison vocabulary. Two independent axes, because collapsing them is how "the probe said
# UNVERIFIED and the runtime returned an answer" would read as a contradiction when it is not.
# --------------------------------------------------------------------------------------------
AUTH_BLOCKED = "AUTH_BLOCKED"            # this surface authoritatively refuses ON AUTHENTICATION
AUTH_ASSERTED = "AUTH_ASSERTED"          # this surface authoritatively reports a live session
AUTH_NOT_ASSERTED = "AUTH_NOT_ASSERTED"  # nothing authoritative either way (silence, or a failure
                                         # that is not about authentication)

EXEC_PERMITTED = "EXEC_PERMITTED"        # this surface would let work proceed
EXEC_PAUSED_AUTH = "EXEC_PAUSED_AUTH"    # node-wide pause, cause: authentication
EXEC_PAUSED_RATE = "EXEC_PAUSED_RATE"    # node-wide pause, cause: quota/rate
EXEC_REFUSED = "EXEC_REFUSED"            # not permitted, and NOT on an authentication verdict


@dataclass(frozen=True)
class Observation:
    """One provider process result, plus what each surface is expected to publish for it.

    `version_out` is held constant at a valid declaration in every row: the version axis is W-52's
    and is not what this matrix measures. Fixing it means any difference the matrix reports comes
    from the auth/inventory/outcome axes it is actually about.
    """

    key: str
    what: str
    rc: int | None
    out: str
    err: str = ""
    version_out: str = "grok 0.2.118 (1e1687c1cf)"


def _runner_for(obs: Observation):
    """A five-tuple runner (the production runner contract) that answers `--version` with the fixed
    declaration and EVERY other call with the observation. Both probes drive the same one."""

    def run(argv):
        if any(str(a) == "--version" for a in argv):
            return 0, obs.version_out, "", False, None
        return obs.rc, obs.out, obs.err, False, None

    return run


# --------------------------------------------------------------------------------------------
# The three drivers. Each returns the surface's OWN published object; the projections are separate
# so it is visible that nothing is re-derived on the way.
# --------------------------------------------------------------------------------------------
def _adapter_probe(obs: Observation, *, parse_models=C.parse_grok_models,
                   reports_auth: bool = True) -> C.ProviderCliProbe:
    return C.probe_provider_cli(provider="grok", executable="grok", runner=_runner_for(obs),
                                min_version=GB.MIN_GROK_VERSION, parse_models=parse_models,
                                reports_auth=reports_auth)


def _recon_probe(obs: Observation, *, spec=R.GROK_SPEC) -> R.ProviderStatus:
    return R.probe_status(spec, _runner_for(obs), check_registration=False, executable="grok")


def _runtime(obs: Observation, monkeypatch):
    """Drive `generate` over the SAME triple, and return `(result, outcome)`.

    `outcome` is obtained by calling the PRODUCTION classifier on the same triple -- the identical
    call `generate` makes internally. It is the reference the runtime's behaviour is graded
    against, which is precisely W-50's property (the verdict is the fact), and it is composition
    rather than a second opinion.
    """
    monkeypatch.setattr(
        process_tree, "run_managed_process",
        lambda cmd, **kw: types.SimpleNamespace(returncode=obs.rc, stdout=obs.out,
                                                stderr=obs.err, spawned_pids=()))
    backend = GB.GrokCliBackend("grok")
    backend._LIVE_SPAWN_PATH_WIRED = True     # the U268 refusal is a different property
    outcome = C.classify_provider_outcome(obs.rc, obs.out, obs.err,
                                          structured_error=C.structured_error_of(obs.out))
    try:
        return ("RETURNED", backend.generate("q")), outcome
    except C.ProviderAuthPause as exc:
        return ("PAUSE", str(exc)), outcome
    except RuntimeError as exc:
        return ("ERROR", str(exc)), outcome


# --------------------------------------------------------------------------------------------
# The projections. Each reads ONLY fields the surface already computed.
# --------------------------------------------------------------------------------------------
def _project_adapter(probe: C.ProviderCliProbe) -> tuple[str, str]:
    auth = {C.AUTH_REQUIRED: AUTH_BLOCKED,
            C.AUTH_AUTHENTICATED: AUTH_ASSERTED}.get(probe.auth_state, AUTH_NOT_ASSERTED)
    if probe.auth_state == C.AUTH_REQUIRED:
        return auth, EXEC_PAUSED_AUTH
    # `selectable_models()` IS this surface's execution decision -- it is what the picker offers
    # (`tools/live/enumerate_pane_picker._op12_inventory`), so nothing else may stand in for it.
    return auth, (EXEC_PERMITTED if probe.selectable_models() else EXEC_REFUSED)


def _project_recon(status: R.ProviderStatus) -> tuple[str, str]:
    auth = {R.AUTH_REQUIRED: AUTH_BLOCKED,
            R.AUTH_AUTHENTICATED: AUTH_ASSERTED}.get(status.auth_state, AUTH_NOT_ASSERTED)
    if status.state == R.STATE_AUTH_REQUIRED:
        return auth, EXEC_PAUSED_AUTH
    return auth, (EXEC_PERMITTED if status.state == R.STATE_AVAILABLE else EXEC_REFUSED)


def _project_runtime(result, outcome: C.ProviderOutcome) -> tuple[str, str]:
    kind = result[0]
    if kind == "PAUSE":
        # WHICH pause is read off the classifier verdict, never off the message text. The runtime
        # raises ONE exception type for both causes; the cause is `outcome.outcome`.
        if outcome.outcome == C.OUTCOME_AUTH_REQUIRED:
            return AUTH_BLOCKED, EXEC_PAUSED_AUTH
        return AUTH_NOT_ASSERTED, EXEC_PAUSED_RATE
    if kind == "ERROR":
        return AUTH_NOT_ASSERTED, EXEC_REFUSED
    # The runtime NEVER asserts a session: a successful invocation is evidence the call worked, not
    # a verdict about the operator's login. Only the probes have an auth-reporting surface.
    return AUTH_NOT_ASSERTED, EXEC_PERMITTED


def assert_no_authoritative_disagreement(projections: dict[str, tuple[str, str]]) -> None:
    """The invariant. Representation may differ; the authoritative control decision may not."""
    auths = {a for a, _ in projections.values()}
    execs = {e for _, e in projections.values()}
    if AUTH_BLOCKED in auths:
        assert AUTH_ASSERTED not in auths, (
            f"one surface reports a session while another refuses on authentication: {projections}")
        assert EXEC_PERMITTED not in execs, (
            f"authentication is BLOCKED and some surface still permits execution: {projections}")
    else:
        assert EXEC_PAUSED_AUTH not in execs, (
            f"a surface paused a node on authentication that no surface established: {projections}")


# --------------------------------------------------------------------------------------------
# THE MATRIX
# --------------------------------------------------------------------------------------------
GENUINE_LOGIN = Observation(
    key="genuine-authenticated-declaration",
    what="the CLI's own declarative login line, plus a real inventory",
    rc=0,
    out=("You are logged in with grok.com.\n"
         "\n"
         "Default model: grok-4.5\n"
         "\n"
         "Available models:\n"
         "  * grok-4.5 (default)\n"))

CONDITIONAL_LOGIN_PROSE = Observation(
    key="conditional-login-prose-only",
    what="help text that MENTIONS being logged in and declares nothing (W-46 / [[U465]])",
    rc=0,
    out=("If you are logged in elsewhere, run the logout command first.\n"
         "To check whether you are logged in, run the whoami command.\n"))

EXPLICIT_SIGNED_OUT = Observation(
    key="explicit-signed-out",
    what="the CLI reports the operator is signed out and FAILS the call",
    rc=1,
    out="",
    err="Error: not authenticated. Please log in before running this command.\n")

ORDINARY_SUCCESS_ABOUT_AUTH = Observation(
    key="ordinary-success-discussing-auth",
    what="a successful ANSWER whose subject is authentication (W-48 / [[U467]])",
    rc=0,
    out=("Handling sign-in failures: services usually surface a message such as "
         "'not authenticated' or 'please log in', and clients should treat http 401 as a "
         "credential problem rather than a transport one.\n"))

ORDINARY_SUCCESS_ABOUT_RATE = Observation(
    key="ordinary-success-discussing-rate-limits",
    what="a successful ANSWER whose subject is rate limiting (W-48 / [[U467]])",
    rc=0,
    out=("Designing a rate limit: return http 429 with a Retry-After header once the quota for "
         "the window is exhausted, and document the usage limit alongside the endpoint.\n"))

GENUINE_RATE_LIMIT = Observation(
    key="genuine-rate-limit-failure",
    what="a real quota condition: the call FAILS and says so",
    rc=1,
    out="",
    err="Error: usage limit reached for this subscription. Your quota resets at 00:00 UTC.\n")

ANTI_SHADOW = Observation(
    key="anti-shadow-verdict-without-a-visible-marker",
    what=("the structured verdict is AUTH_REQUIRED while the runtime's human-readable EXCERPT "
          "carries no auth marker at all (W-50 / H20 / [[U470]])"),
    rc=1,
    out="Error: not authenticated. Please log in.\n",
    err="warning: telemetry collection is disabled by configuration\n")

MATRIX = (GENUINE_LOGIN, CONDITIONAL_LOGIN_PROSE, EXPLICIT_SIGNED_OUT,
          ORDINARY_SUCCESS_ABOUT_AUTH, ORDINARY_SUCCESS_ABOUT_RATE, GENUINE_RATE_LIMIT,
          ANTI_SHADOW)


@pytest.mark.parametrize("obs", MATRIX, ids=[o.key for o in MATRIX])
def test_the_three_entry_points_do_not_disagree(obs, monkeypatch):
    """THE MATRIX ITSELF. One observation, three production entry points, one invariant."""
    adapter = _adapter_probe(obs)
    recon = _recon_probe(obs)
    result, outcome = _runtime(obs, monkeypatch)
    projections = {"probe_provider_cli": _project_adapter(adapter),
                   "probe_status": _project_recon(recon),
                   "runtime.generate": _project_runtime(result, outcome)}
    assert_no_authoritative_disagreement(projections)


@pytest.mark.parametrize("obs", MATRIX, ids=[o.key for o in MATRIX])
def test_the_two_probes_reach_the_same_auth_state_and_inventory(obs):
    """W-49's property, re-asserted at the tier boundary over the WHOLE matrix rather than the four
    shapes that unit measured. The two probes are two CALLERS of one policy, so on the identical
    observation their auth verdict and their inventory must be the SAME value, not merely
    compatible ones -- this is the pair where equality IS the contract."""
    adapter = _adapter_probe(obs)
    recon = _recon_probe(obs)
    assert adapter.auth_state == recon.auth_state, obs.key
    assert adapter.models == recon.models, obs.key
    assert adapter.default_model == recon.default_model, obs.key


# --------------------------------------------------------------------------------------------
# The per-row pins. The matrix above proves NON-DISAGREEMENT; these prove each surface publishes
# the RIGHT state, so the matrix cannot be satisfied by three surfaces being wrong together.
# --------------------------------------------------------------------------------------------
def test_row1_a_genuine_declaration_authenticates_everywhere(monkeypatch):
    adapter = _adapter_probe(GENUINE_LOGIN)
    recon = _recon_probe(GENUINE_LOGIN)
    result, outcome = _runtime(GENUINE_LOGIN, monkeypatch)
    assert adapter.auth_state == C.AUTH_AUTHENTICATED
    assert adapter.selectable_models() == ("grok-4.5",)
    assert recon.state == R.STATE_AVAILABLE and recon.auth_confirmed is True
    assert recon.state_caveat == ""                      # no UNVERIFIED caveat on a real session
    assert outcome.outcome == C.OUTCOME_SUCCESS and result[0] == "RETURNED"
    # and the picker -- the surface that actually OFFERS a node -- offers it
    assert _op12_inventory(adapter).models == ("grok-4.5",)
    assert _op12_inventory(adapter).authenticated is True


def test_row2_conditional_prose_authenticates_nothing(monkeypatch):
    """The half of the invariant that is easy to lose: NOT-BLOCKED is not the same as ASSERTED."""
    adapter = _adapter_probe(CONDITIONAL_LOGIN_PROSE)
    recon = _recon_probe(CONDITIONAL_LOGIN_PROSE)
    result, _ = _runtime(CONDITIONAL_LOGIN_PROSE, monkeypatch)
    assert adapter.auth_state == C.AUTH_UNVERIFIED
    assert recon.auth_state == C.AUTH_UNVERIFIED and recon.auth_confirmed is False
    assert result[0] == "RETURNED"                        # a zero exit is not demoted (directive 6)
    assert _op12_inventory(adapter).authenticated is None, (
        "the picker must distinguish 'not established' from 'signed out' -- None, not False")
    for proj in (_project_adapter(adapter), _project_recon(recon)):
        assert proj[0] == AUTH_NOT_ASSERTED


def test_row3_an_explicit_signed_out_report_blocks_every_surface(monkeypatch):
    adapter = _adapter_probe(EXPLICIT_SIGNED_OUT)
    recon = _recon_probe(EXPLICIT_SIGNED_OUT)
    result, outcome = _runtime(EXPLICIT_SIGNED_OUT, monkeypatch)
    assert adapter.auth_state == C.AUTH_REQUIRED
    assert adapter.selectable_models() == ()
    assert recon.state == R.STATE_AUTH_REQUIRED and recon.auth_state == C.AUTH_REQUIRED
    assert recon.auth_confirmed is False
    assert outcome.outcome == C.OUTCOME_AUTH_REQUIRED
    assert result[0] == "PAUSE", "an explicit signed-out failure must pause the node"
    assert _op12_inventory(adapter).authenticated is False
    assert _op12_inventory(adapter).models == ()


def test_row4_an_answer_about_authentication_pauses_nothing(monkeypatch):
    """[[U467]] at the boundary: the node stays up, and no surface invents a session either."""
    adapter = _adapter_probe(ORDINARY_SUCCESS_ABOUT_AUTH)
    recon = _recon_probe(ORDINARY_SUCCESS_ABOUT_AUTH)
    result, outcome = _runtime(ORDINARY_SUCCESS_ABOUT_AUTH, monkeypatch)
    assert outcome.outcome == C.OUTCOME_SUCCESS and outcome.basis == "exit-code-zero"
    assert result[0] == "RETURNED"
    assert adapter.auth_state == C.AUTH_UNVERIFIED == recon.auth_state
    assert adapter.models == () == recon.models, "prose about auth is not an inventory"


def test_row5_an_answer_about_rate_limits_pauses_nothing(monkeypatch):
    adapter = _adapter_probe(ORDINARY_SUCCESS_ABOUT_RATE)
    recon = _recon_probe(ORDINARY_SUCCESS_ABOUT_RATE)
    result, outcome = _runtime(ORDINARY_SUCCESS_ABOUT_RATE, monkeypatch)
    assert outcome.outcome == C.OUTCOME_SUCCESS
    assert result[0] == "RETURNED"
    assert adapter.models == () == recon.models
    # W-45 ([[U464]]): the 429 in that prose must not have become a model id anywhere.
    assert "429" not in adapter.models and "429" not in recon.models


def test_row6_a_genuine_rate_limit_pauses_the_runtime_and_is_compatible_at_the_probes(monkeypatch):
    """The row where the surfaces legitimately REPRESENT the same condition differently.

    The probes have no rate-limit state in their vocabulary -- section 6's state set is
    AVAILABLE / NOT_INSTALLED / AUTH_REQUIRED / PROBE_FAILED / UNSUPPORTED_VERSION -- so a quota
    condition on the metadata call surfaces as PROBE_FAILED. That is COMPATIBLE with the runtime's
    quota pause (neither permits execution, neither asserts a session) and it is NOT
    AUTH_REQUIRED, which would be the wrong cause shown to the operator.
    """
    adapter = _adapter_probe(GENUINE_RATE_LIMIT)
    recon = _recon_probe(GENUINE_RATE_LIMIT)
    result, outcome = _runtime(GENUINE_RATE_LIMIT, monkeypatch)
    assert outcome.outcome == C.OUTCOME_USAGE_LIMIT
    assert result[0] == "PAUSE"
    assert adapter.auth_state == C.AUTH_PROBE_FAILED == recon.auth_state
    assert adapter.auth_state != C.AUTH_REQUIRED, "a quota condition is not an auth verdict"
    assert recon.state == R.STATE_PROBE_FAILED
    assert _project_adapter(adapter)[1] == EXEC_REFUSED
    assert _project_runtime(result, outcome) == (AUTH_NOT_ASSERTED, EXEC_PAUSED_RATE)


def test_row7_malformed_listing_prose_yields_no_model_anywhere_and_launches_nothing():
    """The inventory row. Its runtime leg is `resolve_model_ref` -- the production gate between an
    inventory and an argv (W-51 / [[U471]]) -- because that is where a model label becomes a
    launched process, and it is asked with the ANTIGRAVITY parser, whose CLI has no header and no
    auth line and therefore leans entirely on id SHAPE (W-44/W-45)."""
    malformed = Observation(
        key="malformed-model-list-prose", what="an error page where a listing should be", rc=0,
        out=("Traceback (most recent call last):\n"
             "  File 'cli.py', line 12, in main\n"
             "Error: could not reach the model service\n"
             "401\n"
             "Unauthorized\n"))
    adapter = _adapter_probe(malformed, parse_models=C.parse_antigravity_models,
                             reports_auth=False)
    recon = _recon_probe(malformed, spec=R.ANTIGRAVITY_SPEC)
    assert adapter.models == () and recon.models == (), (
        f"a verified model was invented from prose: {adapter.models} / {recon.models}")
    assert adapter.default_model is None and recon.default_model is None
    assert _op12_inventory(adapter).models == ()
    # ...and nothing from that page can be launched, whichever token a caller picks up.
    for label in ("401", "Unauthorized", "Traceback", "4-0-1", "attacker-supplied-label"):
        with pytest.raises(ValueError):
            C.resolve_model_ref(label, adapter.models)
    # The two absences stay distinct ([[U471]]): EMPTY is not NOT-ESTABLISHED.
    with pytest.raises(ValueError, match="EMPTY"):
        C.resolve_model_ref("anything", ())
    with pytest.raises(ValueError, match="NOT ESTABLISHED"):
        C.resolve_model_ref("anything", None)


def test_row8_ANTI_SHADOW_the_runtime_pauses_on_the_verdict_with_no_marker_in_its_excerpt(
        monkeypatch):
    """THE DECISIVE ROW. W-50/H20 preserved at the tier boundary.

    Constructed so the two things that could carry the pause are SEPARATED: the structured verdict
    says AUTH_REQUIRED, and the human-readable excerpt `generate` would have re-scanned in the old
    code carries no auth or usage marker at all. The excerpt's innocence is ASSERTED FIRST, so this
    cannot pass by the runtime coincidentally re-deriving the pause from prose -- which is exactly
    the mistake W-50 repaired and the reason a passing negative test alone proves nothing about
    WHICH guard carried the property.
    """
    result, outcome = _runtime(ANTI_SHADOW, monkeypatch)
    # premise 1: the verdict is the auth one
    assert outcome.outcome == C.OUTCOME_AUTH_REQUIRED
    assert outcome.basis == "nonzero-exit+auth-marker"
    # premise 2: the EXCERPT is innocent -- `detail` is redact_diagnostics(stderr or stdout)
    assert outcome.detail, "the excerpt must exist, or the premise is vacuous"
    assert C.is_auth_pause_text(outcome.detail) is False, (
        f"the excerpt carries a marker, so this row cannot distinguish consumption from "
        f"re-derivation: {outcome.detail!r}")
    # the conclusion: it pauses anyway
    assert result[0] == "PAUSE"
    # and the two probes read the same bytes the same way
    assert _adapter_probe(ANTI_SHADOW).auth_state == C.AUTH_REQUIRED
    assert _recon_probe(ANTI_SHADOW).state == R.STATE_AUTH_REQUIRED


# --------------------------------------------------------------------------------------------
# The CHARACTERIZED asymmetry. Recorded as a test rather than left as prose, because it is the one
# place the three surfaces reach different answers, and a later reader must find the reasoning
# attached to the measurement rather than have to re-derive it.
# --------------------------------------------------------------------------------------------
ZERO_EXIT_SIGNED_OUT = Observation(
    key="zero-exit-signed-out-declaration",
    what="grok's real signed-out `models` surface: it DECLARES the negative state and exits ZERO",
    rc=0,
    out=("You are not authenticated.\n"
         "\n"
         "Available models:\n"
         "  * grok-4.5\n"))


def test_the_zero_exit_signed_out_shape_is_contained_at_the_LAUNCH_gate_not_at_generate(
        monkeypatch):
    """Both probes BLOCK; a zero-exit invocation is still not demoted. That is not a disagreement,
    and the reason has to be written down or it will be 'repaired' into one.

    Grok 0.2.118 exits ZERO when signed out and still lists the public default model. The probes
    read that through the CLI's declared auth-reporting surface and report AUTH_REQUIRED. The
    runtime classifier is exit-code-FIRST by operator directive section 6 -- a zero exit is never
    demoted by transcript text -- which is the property W-48 ([[U467]]) exists to protect, and
    weakening it here would re-open a node-wide pause on any answer that mentions being signed out.

    The two answers are about DIFFERENT questions. The probes answer 'may this provider be
    offered'; the runtime answers 'did this invocation succeed'. They are compatible because the
    auth verdict fences the LAUNCH: with AUTH_REQUIRED the picker offers nothing, so no node exists
    to make the call whose zero exit would be honoured. That containment is asserted here rather
    than assumed -- if `_op12_inventory` ever stopped consulting `selectable_models()`, this test
    fails and the asymmetry becomes a real disagreement.
    """
    adapter = _adapter_probe(ZERO_EXIT_SIGNED_OUT)
    recon = _recon_probe(ZERO_EXIT_SIGNED_OUT)
    result, outcome = _runtime(ZERO_EXIT_SIGNED_OUT, monkeypatch)

    assert adapter.auth_state == C.AUTH_REQUIRED == recon.auth_state
    assert recon.state == R.STATE_AUTH_REQUIRED
    # the CLI did list a model; the probe still refuses to OFFER it
    assert adapter.models == ("grok-4.5",)
    assert adapter.selectable_models() == ()
    inventory = _op12_inventory(adapter)
    assert inventory.models == () and inventory.authenticated is False, (
        "THE CONTAINMENT: the picker must offer nothing for a signed-out provider")
    # the runtime, correctly, does not demote a zero exit
    assert outcome.outcome == C.OUTCOME_SUCCESS and result[0] == "RETURNED"
