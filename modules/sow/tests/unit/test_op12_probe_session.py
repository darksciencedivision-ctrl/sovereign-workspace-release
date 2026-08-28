"""Phase 18C `.probe-path` — the GOVERNED, SUPERVISED session the OP-12 live probe runs inside
(discharges U234).

18A built the probe and refused to run it: the child would have been a bare `subprocess.run` with
no node identity, no I-X3 lease and no teardown accounting — a naked session (invariant 2 / I-C1).
18B `.scope` removed the impossibility that had kept that refusal academic (an OP-12 config can now
open the live gate), so `_SUPERVISED_PROBE_PATH = False` became the ONLY thing between
`-Action probe` and an unsupervised frontier CLI. The 18A round-4 validator ruled that opening the
switch before this path exists is *a gate failure at 18C*.

This module pins the path itself, entirely offline — no CLI is resolved, no child is spawned, no
live call is made. Every test drives `governed_probe_session`, a context manager that runs the SAME
gate chain the interactive pane authorization runs (`_authorize_frontier`), in the same order, and
then holds a DURABLE I-X3 lease for exactly as long as the one-shot child runs:

  profile/live gate -> assert_provider_live -> R8 §6 operator terms -> CLI presence (per-provider
  exception, operator directive §14) -> durable lease acquire -> [child] -> release on EVERY path.

What is deliberately NOT claimed here: a Sovereign node RECORD. OP-12.1 (2026-08-01) ruled U227 by
successor schema, so `NodeRegistry.register` now ADMITS both adapter ids under `node@1.1` — but
nothing in this module was wired to call it, then or now. The session mints a governed IDENTITY (the
same way `worker_identity` does for a pane, which also registers no record) and says so. The reason
narrowed from "the vocabulary refuses it" to "no caller creates one"; the claim did not.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from control_plane.profiles.live_authorization import (
    ANTIGRAVITY_PROVIDER,
    GROK_PROVIDER,
    LiveAuthorizationError,
    load_live_authorization,
)
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader, ProfileViolation
from node_runtime.supervisor.frontier_spawn import LiveTermsNotConfirmed
from node_runtime.supervisor.frontier_provider_spawn import (
    AntigravityCliUnavailable,
    GrokCliUnavailable,
)
from node_runtime.supervisor.provider_probe_session import (
    DEFAULT_PROBE_TIMEOUT_S,
    GATE_PROBE_IDENTITY,
    PROBE_LEASE_PURPOSE,
    PROFILE_ENV,
    GovernedProbeSession,
    ProbeSessionRefused,
    governed_probe_session,
    probe_identity,
    profile_loader_from_host,
    supervised_probe_runner,
)
from node_runtime.supervisor.subscription_governor import (
    SubscriptionGovernor,
    SubscriptionLimitExceeded,
    canonical_subscription_ref,
)
from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger

_OP12 = {
    "config_version": "1.1",
    "live_operation_authorized": True,
    "register_row": "OP-12",
    "scope": {"providers": ["claude_code", "openai_codex_cli", GROK_PROVIDER, ANTIGRAVITY_PROVIDER],
              "terminals_per_subscription": 2},
}
_OP6 = {
    "config_version": "1.1",
    "live_operation_authorized": True,
    "register_row": "OP-6",
    "scope": {"providers": ["claude_code", "openai_codex_cli"], "terminals_per_subscription": 2},
}


def _cfg(tmp_path: Path, obj: object = _OP12) -> Path:
    p = tmp_path / "live_operation.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def _ledger(tmp_path: Path) -> TerminalLeaseLedger:
    return TerminalLeaseLedger(tmp_path / "leases.json", pid_alive=lambda _p: True)


def _loader(profile_id: str = "cloud") -> ProfileLoader:
    return ProfileLoader(DeploymentProfile(profile_id))


def _session(tmp_path: Path, provider: str = GROK_PROVIDER, **kw):
    """The standard fully-injected session: real gates, no host reads at all."""
    params = {
        "live_auth": load_live_authorization(path=_cfg(tmp_path)),
        "ledger": _ledger(tmp_path),
        "workspace": str(tmp_path),
        "executable": str(tmp_path / "fake-cli"),
        "cli_present": True,
        # Required keywords — see `TestTheTwoExternallySourcedGatesCannotBeDefaulted` for why this
        # helper supplying them is a convenience and never a fallback. `registrar=None` is the
        # explicit "no node record" choice these session-level tests make: the record wiring is
        # measured in tests/unit/test_provider_node_registration.py against a real registrar, and
        # a default registrar here would write to the operator's durable node log from the suite.
        "profile_loader": _loader(),
        "operator_terms_confirmed": True,
        "registrar": None,
        "holder_pid": 4242,
        "probe_id": "probe1",
    }
    params.update(kw)
    return governed_probe_session(provider, **params)


# ---- identity ----------------------------------------------------------------------------------

class TestTheIdentityIsMintedHereNotAsked:
    def test_a_probe_identity_is_deterministic_and_distinct_from_a_pane_node(self) -> None:
        ident = probe_identity("probe1")
        assert ident["node_id"] == "probe-probe1"
        assert ident["permission_profile_id"] == "pp-probe-reasoning"

    @pytest.mark.parametrize("bad", ["", "   ", "a b", "a/b", "a#b", "x" * 65])
    def test_an_unsafe_probe_id_is_refused_before_it_can_become_a_lease_key(self, bad: str) -> None:
        # `#` is the lease-key delimiter; whitespace/separators make a key nobody can reclaim by.
        with pytest.raises(ProbeSessionRefused) as exc:
            probe_identity(bad)
        # The GATE id, not just the exception: the constant's own comment says a receipt asserting
        # "refused on identity" must not be satisfiable by a pane-path refusal, and nothing held
        # that until this line (18C validator MINOR-2).
        assert exc.value.gate == GATE_PROBE_IDENTITY == "probe_identity"

    def test_the_probe_id_charset_matches_the_pane_one(self) -> None:
        """Two modules deliberately spell the same rule (the pane one is private to its module);
        deliberate duplication is fine, undetectable drift is not."""
        from node_runtime.supervisor import provider_probe_session as P
        from node_runtime.supervisor import worker_pane_spawn as W
        assert P._PROBE_ID_RE.pattern == W._PANE_ID_RE.pattern


# ---- the gate chain ----------------------------------------------------------------------------

class TestEveryGateTheInteractivePathRunsRunsHereToo:
    def test_absent_live_config_denies_and_takes_no_lease(self, tmp_path: Path) -> None:
        """Absence ⇒ DENIED. The refusal surfaces as `ProfileViolation` because the ROSTER gate runs
        first and wraps it — the same order, and the same wrapping, the interactive pane path has."""
        led = _ledger(tmp_path)
        auth = load_live_authorization(path=tmp_path / "absent.json")
        with pytest.raises(ProfileViolation) as exc:
            with _session(tmp_path, live_auth=auth, ledger=led):
                raise AssertionError("the body must never run behind a denied gate")
        assert "not authorized" in str(exc.value)
        assert led.in_use(canonical_subscription_ref(GROK_PROVIDER)) == 0
        # …and the second, independent gate would have refused too (defence in depth, not order).
        with pytest.raises(LiveAuthorizationError):
            auth.assert_provider_live(GROK_PROVIDER)

    def test_an_op6_switch_denies_the_op12_providers(self, tmp_path: Path) -> None:
        """The operator's CURRENT switch cites OP-6. That is the fail-closed world 18C starts in."""
        auth = load_live_authorization(path=_cfg(tmp_path, _OP6))
        for provider in (GROK_PROVIDER, ANTIGRAVITY_PROVIDER):
            with pytest.raises(ProfileViolation):
                with _session(tmp_path, provider, live_auth=auth):
                    raise AssertionError("no body behind a denied gate")
            with pytest.raises(LiveAuthorizationError):
                auth.assert_provider_live(provider)

    def test_unconfirmed_operator_terms_refuse(self, tmp_path: Path) -> None:
        with pytest.raises(LiveTermsNotConfirmed):
            with _session(tmp_path, operator_terms_confirmed=False):
                raise AssertionError("no body without the R8 §6 operator determination")

    def test_an_absent_cli_raises_that_providers_own_exception(self, tmp_path: Path) -> None:
        """Operator directive §14: one provider's failure text is never printed under another's.

        `executable=""` is the host-free seam: "resolution produced nothing", as distinct from
        `None`, which means "go read this host". A deterministic test that reached the real resolver
        would be testing the host's PATH — the D-P18-5 lesson, one caller further down."""
        with pytest.raises(GrokCliUnavailable):
            with _session(tmp_path, GROK_PROVIDER, cli_present=False, executable=""):
                pass
        with pytest.raises(AntigravityCliUnavailable):
            with _session(tmp_path, ANTIGRAVITY_PROVIDER, cli_present=False, executable=""):
                pass

    def test_a_present_gate_with_no_resolved_binary_is_refused(self, tmp_path: Path) -> None:
        """Fail closed rather than emit a bare NAME for a PATH search at spawn time."""
        with pytest.raises(ProbeSessionRefused) as exc:
            with _session(tmp_path, cli_present=True, executable=""):
                pass
        assert exc.value.gate == "binary_unresolved"

    def test_a_provider_outside_the_op12_pair_is_refused_by_this_module(self, tmp_path: Path) -> None:
        with pytest.raises(ProbeSessionRefused) as exc:
            with _session(tmp_path, "claude_code"):
                pass
        assert exc.value.gate == "unknown_adapter"


# ---- I-X3: the lease is real, durable, and returns to zero --------------------------------------

class TestTheLeaseIsHeldForExactlyTheChildsLifetime:
    def test_the_lease_is_held_inside_the_block_and_released_after(self, tmp_path: Path) -> None:
        led = _ledger(tmp_path)
        ref = canonical_subscription_ref(GROK_PROVIDER)
        with _session(tmp_path, ledger=led) as sess:
            assert isinstance(sess, GovernedProbeSession)
            assert led.in_use(ref) == 1
            assert sess.subscription_ref == ref
            assert sess.allowance == 1              # OP-12 §12, never 2
            assert sess.in_use == 1
            assert sess.lease_id
        assert led.in_use(ref) == 0
        assert sess.teardown_record["lease_released"] is True
        assert sess.teardown_record["governor_released"] is True
        assert sess.teardown_record["in_use_after"] == 0

    def test_the_lease_is_released_even_when_the_body_raises(self, tmp_path: Path) -> None:
        led = _ledger(tmp_path)
        ref = canonical_subscription_ref(ANTIGRAVITY_PROVIDER)
        with pytest.raises(RuntimeError):
            with _session(tmp_path, ANTIGRAVITY_PROVIDER, ledger=led) as sess:
                assert led.in_use(ref) == 1
                raise RuntimeError("the child blew up")
        assert led.in_use(ref) == 0
        assert sess.teardown_record["lease_released"] is True

    def test_a_second_concurrent_probe_on_the_same_provider_is_refused(self, tmp_path: Path) -> None:
        """Allowance 1 (operator directive §12) — and the directive's own §17 rule: never two
        simultaneous same-provider sessions."""
        led = _ledger(tmp_path)
        with _session(tmp_path, ledger=led, probe_id="first"):
            with pytest.raises(SubscriptionLimitExceeded):
                with _session(tmp_path, ledger=led, probe_id="second"):
                    raise AssertionError("a second grok terminal must never be authorized")

    def test_the_in_process_governor_holds_the_LEASE_KEY_and_hands_it_back(
            self, tmp_path: Path) -> None:
        """The governor must count the same key `seed_governor` projects with. Counting the bare
        node id instead is invisible to the refusal path (the durable ledger refuses anyway) and
        LEAKS here: the release is then a no-op against a holder that is never removed, while
        `teardown_record` still reports released. Asserted against the governor's own state, which
        is why an injected governor exists in this test at all."""
        gov = SubscriptionGovernor()
        ref = canonical_subscription_ref(GROK_PROVIDER)
        with _session(tmp_path, governor=gov, probe_id="grok") as sess:
            assert (gov.status()[ref]["active"]) == [f"{sess.node_id}#{sess.session_id}"]
            assert gov.active_count(ref) == 1
        assert gov.active_count(ref) == 0
        assert sess.teardown_record["governor_released"] is True

    def test_two_probes_with_the_SAME_probe_id_are_still_two_terminals(self, tmp_path: Path) -> None:
        """The defect this test was written for: `probe_id` is derived from the provider's own
        command name, so two concurrent probes share a node id. Counting the governor by node id made
        the second an IDEMPOTENT re-acquire — it ran uncounted and then released a lease the first
        still needed. Counted by lease key, the second is refused (U75, from the other end)."""
        led = _ledger(tmp_path)
        with _session(tmp_path, ledger=led, probe_id="grok") as first:
            with pytest.raises(SubscriptionLimitExceeded):
                with _session(tmp_path, ledger=led, probe_id="grok"):
                    raise AssertionError("a second terminal on one subscription must be refused")
            # …and the FIRST probe still holds its own terminal afterwards
            assert led.in_use(canonical_subscription_ref(GROK_PROVIDER)) == 1
            assert first.lease_id

    def test_each_session_gets_its_own_id_even_for_one_probe_id(self, tmp_path: Path) -> None:
        led = _ledger(tmp_path)
        with _session(tmp_path, ledger=led, probe_id="grok") as a:
            pass
        with _session(tmp_path, ledger=led, probe_id="grok") as b:
            pass
        assert a.session_id and b.session_id and a.session_id != b.session_id
        assert a.node_id == b.node_id == "probe-grok"

    def test_the_two_op12_subscriptions_are_never_merged(self, tmp_path: Path) -> None:
        led = _ledger(tmp_path)
        with _session(tmp_path, GROK_PROVIDER, ledger=led, probe_id="g"):
            with _session(tmp_path, ANTIGRAVITY_PROVIDER, ledger=led, probe_id="a"):
                assert led.in_use(canonical_subscription_ref(GROK_PROVIDER)) == 1
                assert led.in_use(canonical_subscription_ref(ANTIGRAVITY_PROVIDER)) == 1

    def test_a_terminal_held_by_the_shell_is_seen_by_this_probe(self, tmp_path: Path) -> None:
        """The cross-process half of I-X3: a durable lease another holder wrote counts here."""
        led = _ledger(tmp_path)
        ref = canonical_subscription_ref(GROK_PROVIDER)
        led.acquire(subscription_ref=ref, provider=GROK_PROVIDER, node_id="worker-pane3",
                    allowance=1, holder_pid=999, purpose="operator pane", session_id="s1")
        with pytest.raises(SubscriptionLimitExceeded):
            with _session(tmp_path, ledger=led):
                raise AssertionError("the probe must not exceed the operator's own terminal")

    def test_the_lease_records_the_probe_purpose(self, tmp_path: Path) -> None:
        led = _ledger(tmp_path)
        with _session(tmp_path, ledger=led):
            held = led.live(canonical_subscription_ref(GROK_PROVIDER))
            assert len(held) == 1 and held[0].purpose == PROBE_LEASE_PURPOSE
        # Compared against LITERALS as well as the constant: an assertion that only imports the
        # value it compares against is satisfied by a blank purpose, which is exactly the case the
        # comment on that constant says an operator reading the ledger must not meet.
        assert "probe" in PROBE_LEASE_PURPOSE and "18C" in PROBE_LEASE_PURPOSE

    def test_the_governor_release_is_MEASURED_not_assumed(self, tmp_path: Path) -> None:
        """`governor_released` was a fixed `True` away from being un-noticed. Suppress the release
        and the record must say so — a teardown record that cannot report a failed teardown is
        decoration (invariant 27)."""
        class _StuckGovernor(SubscriptionGovernor):
            def release(self, ref: str, key: str) -> None:      # noqa: D102 — deliberately inert
                return None

        gov = _StuckGovernor()
        with _session(tmp_path, governor=gov, probe_id="grok") as sess:
            pass
        assert sess.teardown_record["governor_released"] is False

    def test_the_governor_slot_is_released_even_if_the_durable_release_explodes(
            self, tmp_path: Path) -> None:
        """The ledger writes files, so an `OSError` out of `release` is reachable, and it used to
        escape the `finally` BEFORE `gov.release` — leaking an in-process terminal for the life of
        the process (18C validator MINOR-4)."""
        led = _ledger(tmp_path)
        gov = SubscriptionGovernor()
        ref = canonical_subscription_ref(GROK_PROVIDER)

        def boom(_lease_id: str) -> bool:
            raise OSError("the ledger file went away")

        with pytest.raises(OSError):
            with _session(tmp_path, ledger=led, governor=gov, probe_id="grok"):
                led.release = boom          # type: ignore[method-assign]
        assert gov.active_count(ref) == 0

    def test_the_terminals_other_holders_hold_are_projected_and_recorded(self,
                                                                        tmp_path: Path) -> None:
        """`seeded_from_ledger` is the projection that makes another holder's terminal visible to
        THIS process's governor. Asserting it keeps the field from becoming dead observability."""
        led = _ledger(tmp_path)
        ref = canonical_subscription_ref(ANTIGRAVITY_PROVIDER)
        led.acquire(subscription_ref=ref, provider=ANTIGRAVITY_PROVIDER, node_id="worker-pane7",
                    allowance=1, holder_pid=999, purpose="operator pane", session_id="s9")
        gov = SubscriptionGovernor()
        # The foreign holder is projected into THIS process's governor by the seed, which is what
        # makes the refusal below an I-X3 decision rather than a coincidence of one ledger read.
        with pytest.raises(SubscriptionLimitExceeded):
            with _session(tmp_path, ANTIGRAVITY_PROVIDER, ledger=led, governor=gov, probe_id="a"):
                raise AssertionError("the operator's own terminal must be counted")
        assert "worker-pane7" in gov.status()[ref]["active"][0]


# ---- credentials: names only, never values ------------------------------------------------------

class TestCredentialIsolation:
    def test_the_scrub_names_cover_the_op12_keys(self, tmp_path: Path) -> None:
        env = {"XAI_API_KEY": "x", "GEMINI_API_KEY": "y", "GOOGLE_API_KEY": "z", "PATH": "/bin"}
        with _session(tmp_path, base_env=env) as sess:
            assert {"XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"} <= set(sess.env_scrub_names)

    def test_no_credential_VALUE_can_reach_the_session_document(self, tmp_path: Path) -> None:
        env = {"XAI_API_KEY": "sk-secret-value", "PATH": "/bin"}
        with _session(tmp_path, base_env=env) as sess:
            assert "sk-secret-value" not in json.dumps(sess.as_dict())

    def test_the_child_environment_has_the_keys_removed(self, tmp_path: Path) -> None:
        env = {"XAI_API_KEY": "sk-secret-value", "PATH": "/bin"}
        with _session(tmp_path, base_env=env) as sess:
            assert "XAI_API_KEY" not in sess.child_env()
            assert sess.child_env().get("PATH") == "/bin"


# ---- what the session honestly is, and is not ---------------------------------------------------

class TestTheSessionStatesItsOwnLimits:
    def test_it_is_headless_one_shot_and_says_so(self, tmp_path: Path) -> None:
        with _session(tmp_path) as sess:
            d = sess.as_dict()
            assert d["supervised"] is True and d["one_shot"] is True and d["interactive"] is False

    def test_a_session_opened_with_no_registrar_says_it_has_no_node_record(
            self, tmp_path: Path) -> None:
        """INVERTED at 18D `.close`, and the inversion is the point. Through 18C this asserted
        that the module never claims a registered node, because none could exist (U227) and then
        because nothing was wired. OP-12.1 ruled U227 and `.close` wired it, so the claim is now
        conditional on the caller's own `registrar` argument: this helper passes `None`, which
        means no record — and `node_registered` must report exactly that, never a leftover
        hardcoded False that would read the same for a registrar that silently failed."""
        with _session(tmp_path) as sess:
            d = sess.as_dict()
            assert d["node_registered"] is False
            assert d["node_record"] is None


# ---- the supervised runner ----------------------------------------------------------------------

class TestTheSupervisedRunner:
    def test_it_runs_the_child_inside_the_job_object_boundary(self, tmp_path: Path,
                                                              monkeypatch) -> None:
        from node_runtime.supervisor import provider_probe_session as P

        seen: dict[str, object] = {}

        class _Proc:
            returncode, stdout, stderr, spawned_pids = 0, "ok", "", (11, 12)

        def fake(cmd, *, timeout, env, stdin, cwd=None, input_text=None):
            seen.update(cmd=list(cmd), env=dict(env), cwd=cwd, timeout=timeout, stdin=stdin)
            return _Proc()

        monkeypatch.setattr(P, "run_managed_process", fake)
        with _session(tmp_path, base_env={"XAI_API_KEY": "x", "PATH": "/bin"}) as sess:
            run = supervised_probe_runner(sess, timeout_s=30.0)
            rc, out, err, timed, spawn_error = run([sess.executable, "-p", "hi"])
        assert (rc, out, err, timed, spawn_error) == (0, "ok", "", False, None)
        assert seen["cwd"] == str(tmp_path)          # workspace binding, not "wherever we started"
        assert seen["timeout"] == 30.0               # bounded: a hung child cannot hold the terminal
        # stdin CLOSED — an inherited non-TTY stdin lets a TUI-capable CLI block forever
        assert seen["stdin"] == subprocess.DEVNULL
        assert "XAI_API_KEY" not in seen["env"]
        assert sess.spawned_pids == (11, 12)         # the job object's pids, recorded for teardown

    def test_a_timeout_is_reported_not_raised(self, tmp_path: Path, monkeypatch) -> None:
        import subprocess

        from node_runtime.supervisor import provider_probe_session as P

        def fake(cmd, **_kw):
            raise subprocess.TimeoutExpired(cmd, 1.0)

        monkeypatch.setattr(P, "run_managed_process", fake)
        with _session(tmp_path) as sess:
            rc, out, err, timed, spawn_error = supervised_probe_runner(sess)([sess.executable])
        assert rc is None and timed is True and spawn_error is None
        # `run_managed_process` checks its cleanup error BEFORE re-raising the timeout, so a
        # TimeoutExpired that reaches here is proof the boundary tore the tree down first.
        assert sess.process_tree_clean is True

    def test_a_missing_binary_is_a_spawn_error_not_a_timeout(self, tmp_path: Path,
                                                             monkeypatch) -> None:
        from node_runtime.supervisor import provider_probe_session as P

        monkeypatch.setattr(P, "run_managed_process",
                            lambda cmd, **_kw: (_ for _ in ()).throw(FileNotFoundError("nope")))
        with _session(tmp_path) as sess:
            rc, out, err, timed, spawn_error = supervised_probe_runner(sess)([sess.executable])
        assert rc is None and timed is False and "FileNotFoundError" in (spawn_error or "")

    def test_the_child_must_be_the_file_the_gate_RESOLVED(self, tmp_path: Path,
                                                          monkeypatch) -> None:
        """The gate refuses an unresolved binary so the child cannot be a PATH lookup at spawn
        time — but through 18C's first cut the runner then executed whatever argv it was handed,
        and `session.executable` appeared only in the report. The two agreed by call-site
        coincidence. Now the runner is the second half of the same gate (18C validator MAJOR-4)."""
        from node_runtime.supervisor import provider_probe_session as P

        spawned: list[list[str]] = []
        monkeypatch.setattr(P, "run_managed_process",
                            lambda cmd, **_kw: spawned.append(list(cmd)))
        with _session(tmp_path) as sess:
            with pytest.raises(ProbeSessionRefused) as exc:
                supervised_probe_runner(sess)(["grok", "-p", "hi"])   # a bare NAME, not the file
            assert exc.value.gate == "binary_unresolved"
            with pytest.raises(ProbeSessionRefused):
                supervised_probe_runner(sess)([])                     # nor an empty argv
        assert spawned == []                     # nothing was spawned on either refusal

    def test_a_containment_failure_is_reported_and_recorded_not_raised(self, tmp_path: Path,
                                                                       monkeypatch) -> None:
        """`ProcessTreeCleanupError` is the ONE signal the boundary exists to produce (invariant
        29). Letting it escape made an invariant-29 containment failure reach the operator as
        "provider engine failed with exit N (this is a tool failure, not a governed refusal)"."""
        from adapters.frontier.process_tree import ProcessTreeCleanupError
        from node_runtime.supervisor import provider_probe_session as P

        def fake(cmd, **_kw):
            raise ProcessTreeCleanupError("descendants remain after shutdown: [4242]")

        monkeypatch.setattr(P, "run_managed_process", fake)
        with _session(tmp_path) as sess:
            rc, out, err, timed, spawn_error = supervised_probe_runner(sess)([sess.executable])
            assert rc is None and timed is False
            assert "ProcessTreeCleanupError" in (spawn_error or "")
            assert sess.process_tree_clean is False
        # …and it survives into the MEASURED teardown record, where a receipt can read it.
        assert sess.teardown_record["process_tree_clean"] is False

    def test_the_default_timeout_is_the_bounded_one_the_docstring_claims(self, tmp_path: Path,
                                                                        monkeypatch) -> None:
        """Every other runner test passes `timeout_s` explicitly, so the default never ran under
        test and could be set to `None` — an unbounded child holding the subscription's single
        terminal — with the suite green (18C validator MEDIUM-5)."""
        from node_runtime.supervisor import provider_probe_session as P

        seen: dict[str, object] = {}

        class _Proc:
            returncode, stdout, stderr, spawned_pids = 0, "", "", ()

        def fake(cmd, *, timeout, env, stdin, cwd=None, input_text=None):
            seen["timeout"] = timeout
            return _Proc()

        monkeypatch.setattr(P, "run_managed_process", fake)
        with _session(tmp_path) as sess:
            supervised_probe_runner(sess)([sess.executable])
        assert isinstance(DEFAULT_PROBE_TIMEOUT_S, float) and 0 < DEFAULT_PROBE_TIMEOUT_S <= 600
        assert seen["timeout"] == DEFAULT_PROBE_TIMEOUT_S


# ---- the two gates whose input comes from OUTSIDE this module ------------------------------------

class TestTheTwoExternallySourcedGatesCannotBeDefaulted:
    """Both reviewers found the same defect independently at 18C: the module claimed the pane
    path's gate chain and defaulted the two gates a caller supplies. It manufactured
    `ProfileLoader(DeploymentProfile("cloud"))`, so invariant 20's air-gap half could never refuse
    — the validator opened a LEASED session on an air-gapped host to prove it — and it defaulted
    the OPERATOR's R8 §6 determination to confirmed (invariant 1). Both are required now."""

    @pytest.mark.parametrize("missing",
                             ["profile_loader", "operator_terms_confirmed", "registrar"])
    def test_the_gate_is_a_required_keyword(self, tmp_path: Path, missing: str) -> None:
        """`registrar` joined the list at 18D `.close` for the same reason: whether the session
        becomes a Sovereign node RECORD (invariant 2) is the caller's fact, and a default would be
        this module answering it."""
        params = {
            "probe_id": "p", "workspace": str(tmp_path),
            "live_auth": load_live_authorization(path=_cfg(tmp_path)),
            "ledger": _ledger(tmp_path), "executable": str(tmp_path / "cli"), "cli_present": True,
            "profile_loader": _loader(), "operator_terms_confirmed": True, "registrar": None,
        }
        params.pop(missing)
        with pytest.raises(TypeError) as exc:
            governed_probe_session(GROK_PROVIDER, **params).__enter__()
        assert missing in str(exc.value)

    def test_an_air_gapped_profile_refuses_and_takes_NO_lease(self, tmp_path: Path) -> None:
        """Invariant 20, at the gate that claims it. The refusal must land BEFORE the lease: a
        durable terminal written and released for a probe that was never going to run is a lease
        the operator's ledger cannot explain."""
        led = _ledger(tmp_path)
        with pytest.raises(ProfileViolation) as exc:
            with _session(tmp_path, ledger=led, profile_loader=_loader("offline_airgapped")):
                raise AssertionError("no body under an air-gapped profile")
        assert "air-gapped" in str(exc.value)
        assert led.in_use(canonical_subscription_ref(GROK_PROVIDER)) == 0
        assert led.live(canonical_subscription_ref(GROK_PROVIDER)) == []

    def test_the_host_profile_is_read_from_the_environment_and_fails_closed(
            self, monkeypatch) -> None:
        monkeypatch.delenv(PROFILE_ENV, raising=False)
        assert profile_loader_from_host().profile.profile_id == "cloud"
        monkeypatch.setenv(PROFILE_ENV, "  offline_airgapped  ")
        assert profile_loader_from_host().profile.is_airgapped is True
        monkeypatch.setenv(PROFILE_ENV, "")
        assert profile_loader_from_host().profile.profile_id == "cloud"
        # An id nobody recognises is NOT a licence to call a cloud CLI.
        monkeypatch.setenv(PROFILE_ENV, "whatever-the-operator-typed")
        with pytest.raises(ProfileViolation):
            profile_loader_from_host()

    def test_it_agrees_with_the_recon_tools_own_air_gap_verdict(self, monkeypatch) -> None:
        """Two modules answer "is this host air-gapped?"; undetectable drift between them is how
        one path refuses a live call and another permits it (18C spec-audit MINOR-11)."""
        from tools.providers import frontier_provider_recon as R

        assert R._PROFILE_ENV == PROFILE_ENV
        for profile_id in ("cloud", "hybrid", "offline_airgapped"):
            monkeypatch.setenv(PROFILE_ENV, profile_id)
            assert profile_loader_from_host().profile.is_airgapped == R.airgapped()

    def test_the_two_executable_resolvers_agree(self, tmp_path: Path, monkeypatch) -> None:
        """The module's own resolver runs only when a caller omits `executable` — which the
        product path never does — so it could disagree with `which_provider` forever without
        anything noticing (18C spec-audit MINOR-11). A fabricated PATH makes them answer the same
        question, so drift between the two candidate lists goes red here."""
        from node_runtime.supervisor import provider_probe_session as P
        from tools.providers import frontier_provider_recon as R

        bindir = tmp_path / "bin"
        bindir.mkdir()
        for name in ("grok.cmd", "agy.cmd"):
            (bindir / name).write_text("@echo off\n", encoding="utf-8")
        monkeypatch.setenv("PATH", str(bindir))
        monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD;.PS1")
        for provider, spec in ((GROK_PROVIDER, R.GROK_SPEC),
                               (ANTIGRAVITY_PROVIDER, R.ANTIGRAVITY_SPEC)):
            mine, theirs = P._resolve_executable(provider), R.which_provider(spec)
            assert mine is not None and theirs is not None
            assert Path(mine).resolve() == Path(theirs).resolve()

    def test_the_gate_chain_matches_the_pane_paths_gate_chain(self) -> None:
        """A DRIFT DETECTOR for the module's headline claim. The chain is spelled out twice (here
        and in `_authorize_frontier`) and the safety argument rests on their being the same; the
        first cut asserted that in prose and was wrong in two places. Compares the ordered gate
        calls, not the prose about them."""
        import inspect
        import re as _re

        from node_runtime.supervisor import provider_probe_session as P
        from node_runtime.supervisor import worker_pane_spawn as W

        gates = (r"assert_startup", r"assert_provider_live", r"if not operator_terms_confirmed",
                 r"(?:governor|gov)\.acquire")

        def sequence(fn) -> list[str]:
            src = inspect.getsource(fn)
            found = [(m.start(), g) for g in gates for m in _re.finditer(g, src)]
            return [g for _pos, g in sorted(found)]

        assert sequence(P.governed_probe_session.__wrapped__) == list(gates)
        assert sequence(W._authorize_frontier) == list(gates)
