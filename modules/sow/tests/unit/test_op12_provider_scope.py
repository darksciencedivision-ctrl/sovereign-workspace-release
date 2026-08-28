"""Phase 18B `.scope` — OP-12 live scope + per-provider subscription allowance (directive §17;
operator directive §12/§13; register OP-12).

What this pins, all deterministic and fail-closed (no network, no CLI, no live call):

  * **The scope is code-pinned per authorizing register row.** `OP-6` authorizes exactly the two
    providers it always did; `OP-12` authorizes those two PLUS `grok_build` and
    `google_antigravity`. A config citing OP-6 while naming a Grok/Antigravity provider RAISES —
    a config can never borrow another row's scope, which is the same property U237 found broken
    from the other end (the instruction "extend `config/live_operation.json`" was impossible
    because the code pinned the OP-6 pair and raised on anything else).
  * **Per-provider terminal allowance.** Operator directive §12: `grok_build_subscription` and
    `google_antigravity_subscription` are SEPARATE resources at allowance **1 each**, never
    merged, never raised without a separate operator amendment. The existing pair stays at the
    OP-6 allowance of 2. The cap is code-pinned, so an operator config that says
    `terminals_per_subscription: 2` still yields 1 for the two new providers.
  * **Three independent layers refuse a widened allowance** — `LiveAuthorization.terminals_for`,
    `SubscriptionGovernor.register_subscription`, and the durable `TerminalLeaseLedger.acquire`.
  * **No shorthand aliases for the new providers.** `codex` normalizes to `openai_codex_cli`
    because that alias is unambiguous. `gemini` is NOT an alias for `google_antigravity`: the
    frozen node@1.0 enum already contains a DIFFERENT member spelled `gemini_cli` (the retired
    personal-account CLI the operator directive §4.2/§14 forbids falling back to), so an
    ambiguous alias in permission logic is refused by not existing.
  * **The frozen schema was not touched.** node@1.0's `adapter` enum still has no member for
    either provider — that was U227, and this unit recorded it rather than editing a frozen
    artifact or fabricating a false member. OP-12.1 (2026-08-01) later ruled it by SUCCESSOR
    schema: `node@1.1` carries the wider enum, `@1.0` is still byte-frozen, and the assertions
    below pin exactly that (see the U227 section at the foot of this file).
  * **Credential isolation** (operator directive §13): the worker env-scrub union already
    classifies `XAI_API_KEY` / `GEMINI_API_KEY` / `GOOGLE_API_KEY`; pinned here so it stays true.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from control_plane.profiles.live_authorization import (
    ANTIGRAVITY_PROVIDER,
    GROK_PROVIDER,
    LiveAuthorization,
    LiveAuthorizationError,
    authorized_providers,
    authorizing_register_rows,
    load_live_authorization,
    provider_terminal_cap,
)
from node_runtime.supervisor.subscription_governor import (
    MAX_ALLOWANCE,
    SubscriptionGovernor,
    SubscriptionLimitExceeded,
    assert_resource_binding,
    canonical_subscription_ref,
    provider_allowance_cap,
)
from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger
from node_runtime.supervisor.worker_pane_spawn import worker_env_scrub_names

_REPO_ROOT = Path(__file__).resolve().parents[2]

_OP6 = {
    "config_version": "1.1",
    "live_operation_authorized": True,
    "register_row": "OP-6",
    "scope": {"providers": ["claude_code", "openai_codex_cli"], "terminals_per_subscription": 2},
}
_OP12 = {
    "config_version": "1.1",
    "live_operation_authorized": True,
    "register_row": "OP-12",
    "scope": {"providers": ["claude_code", "openai_codex_cli", GROK_PROVIDER, ANTIGRAVITY_PROVIDER],
              "terminals_per_subscription": 2},
}


def _write(tmp_path: Path, obj: object) -> Path:
    p = tmp_path / "live_operation.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


# ---- the code-pinned scope, per authorizing row -----------------------------------------

class TestScopeIsPinnedPerRegisterRow:
    def test_op12_config_authorizes_all_four_providers(self, tmp_path: Path) -> None:
        auth = load_live_authorization(path=_write(tmp_path, _OP12))
        assert auth.authorized is True
        assert auth.register_row == "OP-12"
        assert auth.providers == frozenset(
            {"claude_code", "openai_codex_cli", GROK_PROVIDER, ANTIGRAVITY_PROVIDER})
        for provider in sorted(auth.providers):
            auth.assert_provider_live(provider)      # none of the four raises

    def test_op6_row_cannot_borrow_the_op12_scope(self, tmp_path: Path) -> None:
        """The exact U237 property, from the other side: naming a Grok/Antigravity provider under
        the OP-6 row is refused, so the operator's live switch has ONE unambiguous meaning."""
        for extra in (GROK_PROVIDER, ANTIGRAVITY_PROVIDER):
            bad = {**_OP6, "scope": {"providers": ["claude_code", extra],
                                     "terminals_per_subscription": 2}}
            with pytest.raises(LiveAuthorizationError) as exc:
                load_live_authorization(path=_write(tmp_path, bad))
            assert "OP-6" in str(exc.value) and extra in str(exc.value)

    def test_op6_config_still_behaves_exactly_as_before(self, tmp_path: Path) -> None:
        auth = load_live_authorization(path=_write(tmp_path, _OP6))
        assert auth.providers == frozenset({"claude_code", "openai_codex_cli"})
        assert auth.register_row == "OP-6"
        assert auth.is_provider_live(GROK_PROVIDER) is False
        with pytest.raises(LiveAuthorizationError):
            auth.assert_provider_live(ANTIGRAVITY_PROVIDER)

    def test_an_unknown_register_row_raises(self, tmp_path: Path) -> None:
        for row in ("OP-13", "OP-9", "op-12", "", None, 12):
            with pytest.raises(LiveAuthorizationError):
                load_live_authorization(path=_write(tmp_path, {**_OP12, "register_row": row}))

    def test_a_provider_no_row_authorizes_raises_under_every_row(self, tmp_path: Path) -> None:
        for row in authorizing_register_rows():
            bad = {**_OP12, "register_row": row,
                   "scope": {"providers": ["some_future_frontier"], "terminals_per_subscription": 1}}
            with pytest.raises(LiveAuthorizationError):
                load_live_authorization(path=_write(tmp_path, bad))

    def test_no_shorthand_alias_for_the_new_providers(self, tmp_path: Path) -> None:
        """`gemini` is ambiguous (node@1.0 has a DIFFERENT member `gemini_cli`) and `grok` is a
        runner-parameter spelling, not a provider identity. Permission logic fails closed by
        having no alias at all; the config must name the canonical id."""
        for shorthand in ("grok", "gemini", "antigravity", "gemini_cli", "Grok Build"):
            bad = {**_OP12, "scope": {"providers": [shorthand], "terminals_per_subscription": 1}}
            with pytest.raises(LiveAuthorizationError):
                load_live_authorization(path=_write(tmp_path, bad))

    def test_public_accessors_replace_the_private_read(self) -> None:
        """U230: `_AUTHORIZED_PROVIDERS` was read through a private name by the recon engine."""
        assert authorized_providers("OP-6") == frozenset({"claude_code", "openai_codex_cli"})
        assert GROK_PROVIDER in authorized_providers("OP-12")
        assert GROK_PROVIDER in authorized_providers()          # union over every row
        assert authorized_providers("OP-6") < authorized_providers()
        with pytest.raises(LiveAuthorizationError):
            authorized_providers("OP-99")
        assert set(authorizing_register_rows()) == {"OP-6", "OP-12"}
        # the returned sets are immutable snapshots — a caller cannot widen the scope in place
        assert isinstance(authorized_providers(), frozenset)


# ---- per-provider terminal allowance (operator directive §12) ----------------------------

class TestPerProviderAllowance:
    def test_new_providers_are_capped_at_one_even_when_the_config_says_two(
            self, tmp_path: Path) -> None:
        auth = load_live_authorization(path=_write(tmp_path, _OP12))
        assert auth.terminals_per_subscription == 2          # the OP-6 pair's allowance
        assert auth.terminals_for("claude_code") == 2
        assert auth.terminals_for("openai_codex_cli") == 2
        assert auth.terminals_for(GROK_PROVIDER) == 1        # OP-12 §12 — never merged, never raised
        assert auth.terminals_for(ANTIGRAVITY_PROVIDER) == 1

    def test_a_narrowed_config_narrows_everyone(self, tmp_path: Path) -> None:
        narrowed = {**_OP12, "scope": {**_OP12["scope"], "terminals_per_subscription": 1}}
        auth = load_live_authorization(path=_write(tmp_path, narrowed))
        assert auth.terminals_for("claude_code") == 1        # config may NARROW
        assert auth.terminals_for(GROK_PROVIDER) == 1

    def test_terminals_for_is_zero_when_the_provider_is_not_live(self, tmp_path: Path) -> None:
        auth = load_live_authorization(path=_write(tmp_path, _OP6))
        assert auth.terminals_for(GROK_PROVIDER) == 0        # not in scope ⇒ no terminals
        denied = LiveAuthorization.denied("no config")
        for provider in ("claude_code", GROK_PROVIDER, ANTIGRAVITY_PROVIDER, "nonsense"):
            assert denied.terminals_for(provider) == 0

    def test_unknown_provider_has_no_cap_of_its_own(self) -> None:
        assert provider_terminal_cap(GROK_PROVIDER) == 1
        assert provider_terminal_cap("claude_code") == MAX_ALLOWANCE
        assert provider_terminal_cap("some_future_frontier") == 0   # fail closed

    def test_as_dict_publishes_the_per_provider_view(self, tmp_path: Path) -> None:
        auth = load_live_authorization(path=_write(tmp_path, _OP12))
        view = auth.as_dict()["terminals_by_provider"]
        assert view == {ANTIGRAVITY_PROVIDER: 1, GROK_PROVIDER: 1,
                        "claude_code": 2, "openai_codex_cli": 2}


# ---- the governor: separate resources, allowance 1, never merged -------------------------

class TestGovernorResources:
    def test_the_two_new_resources_carry_the_operator_named_ids(self) -> None:
        assert canonical_subscription_ref(GROK_PROVIDER) == "grok_build_subscription"
        assert canonical_subscription_ref(ANTIGRAVITY_PROVIDER) == "google_antigravity_subscription"
        # and they are distinct from each other and from the existing pair — never one bucket
        refs = {canonical_subscription_ref(p) for p in
                ("claude_code", "openai_codex_cli", GROK_PROVIDER, ANTIGRAVITY_PROVIDER)}
        assert len(refs) == 4

    def test_existing_provider_refs_are_unchanged(self) -> None:
        assert canonical_subscription_ref("claude_code") == "sub-claude_code"
        assert canonical_subscription_ref("openai_codex_cli") == "sub-openai_codex_cli"

    def test_registering_a_new_provider_above_one_is_refused(self) -> None:
        gov = SubscriptionGovernor()
        for provider in (GROK_PROVIDER, ANTIGRAVITY_PROVIDER):
            with pytest.raises(ValueError) as exc:
                gov.register_subscription(canonical_subscription_ref(provider), provider,
                                          allowance=2)
            assert "OP-12" in str(exc.value)
        assert provider_allowance_cap(GROK_PROVIDER) == 1
        assert provider_allowance_cap("claude_code") == MAX_ALLOWANCE

    def test_a_second_grok_terminal_is_refused_while_claude_still_gets_two(self) -> None:
        gov = SubscriptionGovernor()
        grok_ref = canonical_subscription_ref(GROK_PROVIDER)
        gov.register_subscription(grok_ref, GROK_PROVIDER, allowance=1)
        gov.acquire(grok_ref, "node-a")
        with pytest.raises(SubscriptionLimitExceeded):
            gov.acquire(grok_ref, "node-b")

        claude_ref = canonical_subscription_ref("claude_code")
        gov.register_subscription(claude_ref, "claude_code", allowance=2)
        gov.acquire(claude_ref, "node-c")
        gov.acquire(claude_ref, "node-d")            # OP-6 allowance is untouched by OP-12
        assert gov.active_count(claude_ref) == 2
        assert gov.active_count(grok_ref) == 1       # separate buckets, never merged

        gov.release(grok_ref, "node-a")
        assert gov.active_count(grok_ref) == 0
        gov.acquire(grok_ref, "node-b")              # the slot is reusable after release

    def test_the_antigravity_resource_never_lends_a_terminal_to_grok(self) -> None:
        gov = SubscriptionGovernor()
        for provider in (GROK_PROVIDER, ANTIGRAVITY_PROVIDER):
            ref = canonical_subscription_ref(provider)
            gov.register_subscription(ref, provider, allowance=1)
            gov.acquire(ref, f"node-{provider}")
        # both at their allowance simultaneously; neither can take a second
        for provider in (GROK_PROVIDER, ANTIGRAVITY_PROVIDER):
            with pytest.raises(SubscriptionLimitExceeded):
                gov.acquire(canonical_subscription_ref(provider), "intruder")


class TestDurableLedgerHonoursTheSameCap:
    def test_a_widened_allowance_is_refused_at_the_durable_layer_too(self, tmp_path: Path) -> None:
        ledger = TerminalLeaseLedger(tmp_path / "leases.json")
        with pytest.raises(ValueError) as exc:
            ledger.acquire(subscription_ref=canonical_subscription_ref(GROK_PROVIDER),
                           provider=GROK_PROVIDER, node_id="n1", allowance=2, holder_pid=1)
        assert "OP-12" in str(exc.value)

    def test_one_durable_terminal_is_granted_and_a_second_refused(self, tmp_path: Path) -> None:
        ledger = TerminalLeaseLedger(tmp_path / "leases.json", pid_alive=lambda _pid: True)
        ref = canonical_subscription_ref(ANTIGRAVITY_PROVIDER)
        ledger.acquire(subscription_ref=ref, provider=ANTIGRAVITY_PROVIDER, node_id="n1",
                       allowance=1, holder_pid=1)
        with pytest.raises(SubscriptionLimitExceeded):
            ledger.acquire(subscription_ref=ref, provider=ANTIGRAVITY_PROVIDER, node_id="n2",
                           allowance=1, holder_pid=1)


# ---- credential isolation (operator directive §13) ---------------------------------------

def test_the_new_providers_api_keys_are_scrubbed_from_every_child_env() -> None:
    """§13: the app never transmits `XAI_API_KEY` / `GEMINI_API_KEY` / `GOOGLE_API_KEY`. The
    existing union classifier already catches all three (GOOGLE_ prefix, API_KEY substring);
    pinned here so a future narrowing of either list goes red instead of leaking."""
    names = worker_env_scrub_names(
        {"XAI_API_KEY": "x", "GEMINI_API_KEY": "y", "GOOGLE_API_KEY": "z",
         "XAI_API_BASE_URL": "u", "GROK_SANDBOX": "keep", "PATH": "keep"})
    assert {"XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"} <= set(names)
    assert "GROK_SANDBOX" not in names       # the CLI's containment lever survives (18A N-1)
    assert "PATH" not in names


# ---- the review round's findings, each with a test that can go red -----------------------

class TestTheExampleConfigActuallyWorks:
    """U237's lesson was: do not publish an instruction you have not executed. The first cut of
    this sub-step published an OP-12 `.example` that CRASHED the status-bar feed — the emitter
    registered every scoped provider at the GLOBAL allowance, the governor refused 2 for a
    1-terminal subscription, and the whole bar (claude and codex included) degraded to the
    em-dash. So the published file is now executed by a test, verbatim."""

    def test_the_published_example_loads_and_scopes_exactly_what_it_says(self) -> None:
        raw = json.loads((_REPO_ROOT / "config" / "live_operation.example.json")
                         .read_text(encoding="utf-8"))
        assert raw["register_row"] == "OP-12"
        auth = load_live_authorization(path=_REPO_ROOT / "config" / "live_operation.example.json")
        assert auth.authorized is True
        assert auth.providers == authorized_providers("OP-12")

    def test_the_published_example_produces_a_readable_subscription_feed(
            self, tmp_path: Path) -> None:
        from tools.live.emit_subscription_status import build_subscription_status_feed
        from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger
        published = load_live_authorization(
            path=_REPO_ROOT / "config" / "live_operation.example.json")
        feed = build_subscription_status_feed(
            live_auth=published,
            ledger=TerminalLeaseLedger(tmp_path / "leases.json", pid_alive=lambda _p: True))
        assert feed["authorized"] is True
        assert feed["status"] is not None, "the bar must not degrade to UNKNOWN on a valid config"
        assert feed["allowance_by_provider"] == {
            ANTIGRAVITY_PROVIDER: 1, GROK_PROVIDER: 1, "claude_code": 2, "openai_codex_cli": 2}
        by_ref = {ref: row["allowance"] for ref, row in feed["status"].items()}
        assert by_ref[canonical_subscription_ref(GROK_PROVIDER)] == 1
        assert by_ref[canonical_subscription_ref("claude_code")] == 2


class TestTheRefIsBoundToItsProvider:
    """A cap enforced on the provider argument alone was not a cap: two spellings of one
    subscription are two buckets, and re-registering the operator-named ref under a
    higher-capped provider raised the bucket to 2 while still reporting the wrong provider."""

    def test_a_second_ref_spelling_cannot_open_a_second_bucket(self) -> None:
        gov = SubscriptionGovernor()
        with pytest.raises(ValueError) as exc:
            gov.register_subscription(f"sub-{GROK_PROVIDER}", GROK_PROVIDER, allowance=1)
        assert "grok_build_subscription" in str(exc.value)

    def test_another_provider_cannot_register_the_operator_named_resource(self) -> None:
        gov = SubscriptionGovernor()
        with pytest.raises(ValueError) as exc:
            gov.register_subscription(canonical_subscription_ref(GROK_PROVIDER), "claude_code",
                                      allowance=2)
        assert "belongs to" in str(exc.value)

    def test_a_ref_cannot_change_provider_by_re_registration(self) -> None:
        gov = SubscriptionGovernor()
        gov.register_subscription("sub-anthropic", "claude_code", allowance=2)
        with pytest.raises(ValueError):
            gov.register_subscription("sub-anthropic", "openai_codex_cli", allowance=2)
        assert gov.status()["sub-anthropic"]["provider"] == "claude_code"

    def test_the_binding_is_a_public_check_both_layers_can_call(self) -> None:
        assert_resource_binding(canonical_subscription_ref(GROK_PROVIDER), GROK_PROVIDER)  # ok
        assert_resource_binding("sub-anything", "claude_code")   # pre-OP-12 refs stay free-form
        with pytest.raises(ValueError):
            assert_resource_binding("sub-anything", ANTIGRAVITY_PROVIDER)

    def test_the_durable_ledger_binds_the_same_way(self, tmp_path: Path) -> None:
        ledger = TerminalLeaseLedger(tmp_path / "leases.json", pid_alive=lambda _p: True)
        with pytest.raises(ValueError):
            ledger.acquire(subscription_ref=f"sub-{GROK_PROVIDER}", provider=GROK_PROVIDER,
                           node_id="n1", allowance=1, holder_pid=1)


def test_the_two_cap_tables_cannot_disagree() -> None:
    """They were two tables with OPPOSITE fail directions; now the governor reads the one
    authority. Asserted for every provider any ruling covers, so a future OP-13 id added to the
    scope and the cap table cannot inherit a governor ceiling of 2 by being forgotten."""
    for provider in sorted(authorized_providers()):
        assert provider_allowance_cap(provider) == provider_terminal_cap(provider), provider


def test_the_recon_ids_equal_the_control_plane_exports() -> None:
    """The recon tool re-declares these ids deliberately (its control-plane imports are lazy and
    exception-wrapped so a broken control plane cannot crash the diagnostic). Deliberate is fine;
    undetectable drift is not."""
    import tools.providers.frontier_provider_recon as recon
    assert recon.GROK_PROVIDER == GROK_PROVIDER
    assert recon.ANTIGRAVITY_PROVIDER == ANTIGRAVITY_PROVIDER
    assert recon.GROK_SUBSCRIPTION == canonical_subscription_ref(GROK_PROVIDER)
    assert recon.ANTIGRAVITY_SUBSCRIPTION == canonical_subscription_ref(ANTIGRAVITY_PROVIDER)
    assert recon.DEFAULT_TERMINAL_ALLOWANCE == provider_terminal_cap(GROK_PROVIDER)


class TestAnAllowedGateNowRunsThroughAGovernedSession:
    """18B `.scope` removed the impossibility that kept U234 inert: before it, no config could put
    either provider in scope, so the probe gate could never open. Once one could, the probe refused
    on its own supervision outcome — an allowed gate that still spawned nothing.

    **18C `.probe-path` discharges U234**, so the assertions invert: an allowed gate now DOES reach a
    child, and what this class pins is that it reaches it only inside a governed, leased, supervised
    session, and that a supervisor which cannot be reached still refuses rather than downgrading to
    the naked spawn the old refusal described."""

    def _op12_config(self, tmp_path: Path) -> Path:
        return _write(tmp_path, _OP12)

    def _factory(self, tmp_path: Path):
        """The REAL governed session with a temporary ledger + injected presence. The seam supplies
        infrastructure only — every gate below it is the product's own (validator MAJOR-2's lesson:
        a seam that replaces the gates tests nothing)."""
        from node_runtime.supervisor.provider_probe_session import governed_probe_session

        def factory(provider, **kw):
            # `registrar` is popped from the caller's kwargs and replaced with the explicit None
            # these host-free tests want: the product call site passes the DURABLE registrar
            # (`.sovereign_store/nodes/`), and a suite that inherited it would write the operator's
            # node log. What this factory must not do is drop the keyword — the module requires it.
            kw.pop("registrar", None)
            return governed_probe_session(
                provider,
                ledger=TerminalLeaseLedger(tmp_path / "leases.json", pid_alive=lambda _p: True),
                holder_pid=4242, cli_present=True, registrar=None, **kw)
        return factory

    def test_an_op12_config_really_does_open_the_gate(self, tmp_path: Path) -> None:
        import tools.providers.frontier_provider_recon as recon
        allowed, reason = recon.live_probe_gate(GROK_PROVIDER,
                                                config_path=self._op12_config(tmp_path))
        assert allowed is True, reason      # the U237 fix, proven at the surface it was about

    def test_the_child_runs_inside_a_leased_identity_that_is_released_after(
            self, tmp_path: Path, monkeypatch) -> None:
        import tools.providers.frontier_provider_recon as recon
        monkeypatch.setattr(recon, "which_provider", lambda spec: str(tmp_path / "grok.CMD"))
        ledger = TerminalLeaseLedger(tmp_path / "leases.json", pid_alive=lambda _p: True)
        ref = canonical_subscription_ref(GROK_PROVIDER)
        held: list[int] = []

        def runner(argv):
            held.append(ledger.in_use(ref))          # observed WHILE the child "runs"
            return 0, json.dumps({"result": recon.GROK_PROBE_TOKEN}), "", False, None

        out = recon.run_probe(recon.GROK_SPEC, runner=runner, git_status=lambda: "",
                              config_path=self._op12_config(tmp_path),
                              open_session=self._factory(tmp_path))
        assert out["executed"] is True and out["accepted"] is True
        assert held == [1]                            # one terminal, counted, for the child's life
        assert ledger.in_use(ref) == 0                # …and handed back (D-LOOP-1)
        gov = out["governed"]
        assert gov["node_id"] == "probe-grok" and gov["subscription_ref"] == ref
        # `node_registered` is False because THIS factory passes `registrar=None` (see `_factory`)
        # — the durable node log belongs to the product call site, not to the suite. The record
        # wiring is measured against a real registrar in tests/unit/test_provider_node_registration.
        assert gov["allowance"] == 1 and gov["node_registered"] is False
        assert gov["node_record"] is None
        assert gov["teardown"] == {"lease_released": True, "governor_released": True,
                                   "in_use_after": 0, "process_tree_clean": None,
                                   # no registrar ⇒ nothing to close, and no error either: the two
                                   # False-with-error and False-without-error cases are different
                                   # facts and the record says which one this is (18D `.close`)
                                   "node_exit_recorded": False, "node_exit_error": None,
                                   # `None` (not False) because no record exists to have an
                                   # expected-ness: the field describes an exit that was written
                                   "node_exit_expected": None,
                                   "measured": True}
        # `process_tree_clean` is None, not True: an injected runner never entered the boundary, so
        # nothing was OBSERVED about descendants. "Nothing was left behind" and "nothing was
        # checked" are different facts and the record keeps them apart.
        # an INJECTED runner is not the job-object boundary, and the verdict says so rather than
        # inheriting the session's claim
        assert out["supervised_execution"] is False

    def test_a_second_probe_is_refused_while_the_first_holds_the_terminal(
            self, tmp_path: Path, monkeypatch) -> None:
        """Operator directive §17: never two simultaneous same-provider sessions — enforced, not
        merely instructed."""
        import tools.providers.frontier_provider_recon as recon
        monkeypatch.setattr(recon, "which_provider", lambda spec: str(tmp_path / "grok.CMD"))
        cfg, factory = self._op12_config(tmp_path), self._factory(tmp_path)
        inner: dict[str, object] = {}

        def runner(argv):
            inner.update(recon.run_probe(recon.GROK_SPEC, runner=lambda a: (_ for _ in ()).throw(
                AssertionError("a second grok child must never spawn")),
                config_path=cfg, open_session=factory))
            return 0, json.dumps({"result": recon.GROK_PROBE_TOKEN}), "", False, None

        out = recon.run_probe(recon.GROK_SPEC, runner=runner, git_status=lambda: "",
                              config_path=cfg, open_session=factory)
        assert out["accepted"] is True
        assert inner["executed"] is False
        assert inner["refused_by"] == "SubscriptionLimitExceeded"

    def test_an_unreachable_supervisor_refuses_instead_of_downgrading(
            self, tmp_path: Path, monkeypatch) -> None:
        """The old refusal text is kept for exactly this case: no supervisor ⇒ no probe, never a
        silent fall-back to the naked `subprocess.run` it describes."""
        import tools.providers.frontier_provider_recon as recon
        monkeypatch.setattr(recon, "which_provider", lambda spec: str(tmp_path / "grok.CMD"))
        monkeypatch.setattr(recon, "_PROBE_SESSION_MODULE", "node_runtime.supervisor.no_such_module")
        out = recon.run_probe(
            recon.GROK_SPEC,
            runner=lambda a: (_ for _ in ()).throw(AssertionError("nothing may spawn")),
            config_path=self._op12_config(tmp_path))
        assert out["executed"] is False and out["refused_by"] == "supervision"
        assert "U234" in out["reason"] and "naked session" in out["reason"]

    def test_the_UNINJECTED_runner_is_the_supervised_one(self, tmp_path: Path,
                                                         monkeypatch) -> None:
        """**The line that discharges U234, finally pinned.** Every other test in this file passes
        `runner=`, so nothing ever exercised the `runner is None` wiring — and the 18C validator
        swapped `_supervised_runner(session)` for the naked `subprocess_runner()` it exists to
        forbid with the WHOLE suite green. The seam here is one level lower: the real
        `_supervised_runner` runs, and only `run_managed_process` (the OS call) is replaced."""
        import tools.providers.frontier_provider_recon as recon
        from node_runtime.supervisor import provider_probe_session as P

        exe = str(tmp_path / "grok.CMD")
        monkeypatch.setattr(recon, "which_provider", lambda spec: exe)
        seen: dict[str, object] = {}

        class _Proc:
            returncode = 0
            stdout = json.dumps({"result": recon.GROK_PROBE_TOKEN})
            stderr, spawned_pids = "", (4242,)

        def fake_managed(cmd, *, timeout, env, stdin, cwd=None, input_text=None):
            seen.update(cmd=list(cmd), cwd=cwd, stdin=stdin, timeout=timeout,
                        scrubbed="XAI_API_KEY" not in env)
            return _Proc()

        monkeypatch.setattr(P, "run_managed_process", fake_managed)
        monkeypatch.setenv("XAI_API_KEY", "sk-must-not-reach-the-child")
        out = recon.run_probe(recon.GROK_SPEC, runner=None, git_status=lambda: "",
                              repo_root=tmp_path, config_path=self._op12_config(tmp_path),
                              open_session=self._factory(tmp_path))
        assert out["executed"] is True and out["accepted"] is True
        # It went through the BOUNDARY (not `subprocess_runner`, which never calls this)…
        assert seen["cmd"][0] == exe                 # …as the file the gate resolved…
        assert seen["cwd"] == str(tmp_path)          # …bound to the authorized workspace…
        assert seen["stdin"] is subprocess.DEVNULL and seen["scrubbed"] is True
        assert seen["timeout"] == P.DEFAULT_PROBE_TIMEOUT_S
        # …and the verdict claims supervision only because it is true of this run.
        assert out["supervised_execution"] is True
        assert out["governed"]["spawned_pids"] == [4242]
        assert out["governed"]["teardown"]["process_tree_clean"] is True
        assert out["governed"]["teardown"]["in_use_after"] == 0

    def test_the_metadata_runner_is_NOT_the_probes_runner(self) -> None:
        """`subprocess_runner` has been described wrongly in both directions across two phases —
        "benign metadata only" while the probe used it, then "carries the one live prompt" after
        the probe stopped. Pin the current statement to the code."""
        import inspect

        import tools.providers.frontier_provider_recon as recon
        src = inspect.getsource(recon.run_probe)
        assert "_supervised_runner(session)" in src
        assert "subprocess_runner" not in src
        assert "metadata calls only" in (recon.subprocess_runner.__doc__ or "")

    def test_an_air_gapped_host_refuses_before_any_lease_is_written(self, tmp_path: Path,
                                                                    monkeypatch) -> None:
        """Invariant 20 at gate 1, on the product path. Through 18C's first cut the module built
        its own `cloud` loader, so the air-gap refusal came from `_guarded_run` instead — AFTER a
        durable lease had been taken and released for a probe that was never going to run."""
        import tools.providers.frontier_provider_recon as recon

        monkeypatch.setattr(recon, "which_provider", lambda spec: str(tmp_path / "grok.CMD"))
        monkeypatch.setenv(recon._PROFILE_ENV, "offline_airgapped")
        ledger_path = tmp_path / "leases.json"
        out = recon.run_probe(
            recon.GROK_SPEC,
            runner=lambda a: (_ for _ in ()).throw(AssertionError("nothing may spawn")),
            config_path=self._op12_config(tmp_path), open_session=self._factory(tmp_path))
        assert out["executed"] is False
        assert out["refused_by"] == "ProfileViolation"
        assert "air-gapped" in out["reason"]
        assert "governed" not in out          # no session, so no lease and nothing to report
        assert not ledger_path.exists()

    def test_the_flag_names_a_path_that_exists(self) -> None:
        """The flag is a CLAIM. Asserting its value alone would pass over a deleted or renamed
        module; this asserts the claim."""
        import importlib

        import tools.providers.frontier_provider_recon as recon
        assert recon._SUPERVISED_PROBE_PATH is True
        mod = importlib.import_module(recon._PROBE_SESSION_MODULE)
        assert callable(mod.governed_probe_session) and callable(mod.supervised_probe_runner)


class TestTheNodeVocabularyIsAFenceNotASentence:
    """U227's whole claim is that no node record can name a provider the canonical vocabulary does
    not admit. That was true only of a hypothetical validator until this guard existed —
    `NodeRegistry.register` took any string, and the event log it writes to is append-only
    (invariant 12).

    **Updated at 18D, and the update is the point.** The operator ruled U227 by SUCCESSOR SCHEMA
    (OP-12.1, directive §17.1): `schemas/node.schema@1.1.json` admits `grok_build` and
    `google_antigravity`, so they now register. The fence did not weaken — it moved. What these
    tests assert is that it is still a fence: an id in NEITHER version is refused exactly as the
    OP-12 ids were, and the refusal is still an auditable event. The full amendment is covered by
    `tests/unit/test_node_schema_amendment.py`; these stay here so the sub-step that wrote the
    fence keeps its own regression."""

    #: an id no schema version admits and no operator has ruled on — cloud Kimi K3 is the live
    #: example (directive §17 keeps it OWED-pending-operator).
    UNADMITTED = "kimi_k3"

    def _registry(self, tmp_path: Path):
        from control_plane.nodes.event_log import AppendOnlyEventLog
        from control_plane.nodes.registry import NodeRegistry
        return NodeRegistry(AppendOnlyEventLog(tmp_path / "events.jsonl"))

    def test_an_unruled_provider_cannot_be_registered_as_a_node_adapter(self, tmp_path: Path) -> None:
        from control_plane.nodes.registry import RegistrationRefused
        reg = self._registry(tmp_path)
        with pytest.raises(RegistrationRefused) as exc:
            reg.register(f"n-{self.UNADMITTED}", "worker_reasoning", self.UNADMITTED,
                         spawned_by_supervisor=True)
        assert "U227" in str(exc.value)

    def test_the_op12_providers_register_only_because_the_operator_ruled(self, tmp_path: Path) -> None:
        """The boundary this class was written to hold, on the other side of the ruling. It is
        `node@1.1` that admits them — not the exemption list, and not a widened frozen enum."""
        reg = self._registry(tmp_path)
        for provider in (GROK_PROVIDER, ANTIGRAVITY_PROVIDER):
            rec = reg.register(f"n-{provider}", "worker_reasoning", provider,
                               spawned_by_supervisor=True)
            assert rec.adapter == provider
        from control_plane.nodes.registry import adapter_version_map
        admitted = adapter_version_map()
        assert admitted[GROK_PROVIDER] == "node@1.1"
        assert admitted[ANTIGRAVITY_PROVIDER] == "node@1.1"

    def test_enum_members_still_register(self, tmp_path: Path) -> None:
        reg = self._registry(tmp_path)
        for adapter in ("claude_code", "openai_codex_cli", "mock", "ollama_local"):
            rec = reg.register(f"n-{adapter}", "worker_reasoning", adapter,
                               spawned_by_supervisor=True)
            assert rec.adapter == adapter

    def test_the_refusal_is_an_auditable_event_not_just_an_exception(self, tmp_path: Path) -> None:
        from control_plane.nodes.registry import RegistrationRefused
        log_path = tmp_path / "events.jsonl"
        reg = self._registry(tmp_path)
        with pytest.raises(RegistrationRefused):
            reg.register("n-x", "worker_reasoning", self.UNADMITTED, spawned_by_supervisor=True)
        rows = [json.loads(ln) for ln in
                log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert any(r.get("kind") == "registration_refused" for r in rows), rows


# ---- U227: the frozen schema was NOT edited and NOT routed around ------------------------

def test_the_frozen_node_schema_adapter_enum_is_untouched() -> None:
    """Unchanged in substance across the OP-12.1 ruling, and that is exactly why it is kept: the
    ruling resolved U227 by ADDING `schemas/node.schema@1.1.json`, never by editing the freeze.
    node@1.0's `adapter` enum still has no member for either provider, and this test fails the
    moment someone edits the frozen file. `@1.1`'s own contents are asserted in
    `tests/unit/test_node_schema_amendment.py`."""
    schema = json.loads((_REPO_ROOT / "schemas" / "node.schema.json").read_text(encoding="utf-8"))
    enum = schema["properties"]["adapter"]["enum"]
    assert schema["$id"] == "https://sovereign.local/schemas/node@1.0"
    assert enum == ["claude_code", "openai_codex_cli", "opencode_local", "gemini_cli",
                    "aider", "ollama_direct", "nvidia_parakeet", "mock"]
    assert GROK_PROVIDER not in enum and ANTIGRAVITY_PROVIDER not in enum


def test_a_recorded_zero_allowance_stays_zero(monkeypatch) -> None:
    """W-65 NEGATIVE. The authority honours an explicit operator-pinned 0; the governor used
    to read that falsy and hand back the GLOBAL cap of 2 - a recorded 'no terminals' became
    'two terminals'."""
    import control_plane.profiles.live_authorization as la
    monkeypatch.setattr(la, "_PROVIDER_TERMINAL_CAP", {"pinned_zero": 0})

    assert provider_allowance_cap("pinned_zero") == 0


def test_an_id_absent_from_the_authority_has_no_governor_ceiling_either(monkeypatch) -> None:
    """W-65 NEGATIVE, the absence leg. Absent answers 0 at the authority - the documented,
    fail-closed default (live_authorization: 'a new provider cannot inherit another's
    concurrency by omission'). The governor must not upgrade that silence to 2."""
    import control_plane.profiles.live_authorization as la
    monkeypatch.setattr(la, "_PROVIDER_TERMINAL_CAP", {})

    assert provider_allowance_cap("some_future_frontier") == 0


def test_a_governor_registration_for_an_uncapped_provider_is_refused(monkeypatch) -> None:
    """W-65 NEGATIVE, behavioural at the public API: with no recorded cap, ANY allowance is
    past the cap, so register_subscription refuses rather than counting an uncountable
    provider. Pre-repair the falsy fallback let allowance=1 straight through."""
    import control_plane.profiles.live_authorization as la
    monkeypatch.setattr(la, "_PROVIDER_TERMINAL_CAP", {})

    governor = SubscriptionGovernor()
    with pytest.raises(ValueError):
        governor.register_subscription("sub-some_future_frontier",
                                       "some_future_frontier", allowance=1)


def test_the_durable_layer_refuses_an_uncapped_provider_too(monkeypatch, tmp_path: Path) -> None:
    """W-65 control: the same corrected ceiling binds the durable lease acquire, not only
    the in-process governor."""
    import control_plane.profiles.live_authorization as la
    monkeypatch.setattr(la, "_PROVIDER_TERMINAL_CAP", {})

    ledger = TerminalLeaseLedger(tmp_path / "leases.json", pid_alive=lambda _p: True)
    with pytest.raises(ValueError):
        ledger.acquire(subscription_ref="sub-some_future_frontier",
                       provider="some_future_frontier", node_id="n1", allowance=1,
                       holder_pid=1)
