"""Phase 18B `.adapter` — deterministic tests for the two OP-12 frontier provider adapters.

Covers the operator directive §16 items that belong to the ADAPTER sub-step: model enumeration,
missing executable, version parsing, authentication classification, headless command construction,
credential non-disclosure, and the argv/permission guard. Nothing here spawns a provider process
or touches the network: every probe is driven through an injected fake runner, and the only
backends the suite constructs are the mocks.

Three owed items from the 18A gate are closed here and pinned so they cannot silently reopen:
  * **U249** — single-dash flag spellings (`-dangerously-skip-permissions`, `-mode accept-edits`)
    walked through a guard whose docstring called it structural. Both sides are dash-normalised now.
  * **U250** — the endpoint-override and agent-identity flags the recorded capture documents were
    in neither the forbidden list nor U235, while the module claimed no endpoint override could
    redirect a call (true of the env surface only).
  * **U235** — instruction-injection flags stay OUT of the permission list (that decision is
    preserved verbatim) and become a separately-named untrusted-input set the adapter never emits.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from adapters.base.contract import AdapterContext, NakedLaunchRefused
from adapters.frontier import antigravity as AG
from adapters.frontier import grok_build as GB
from adapters.frontier import provider_cli_common as C
from tools.providers import frontier_provider_recon as R

# The capture the operator directive §2 makes authoritative (recorded 2026-07-31).
GROK_MODELS_OUT = (
    "You are logged in with grok.com.\n"
    "\n"
    "Default model: grok-4.5\n"
    "\n"
    "Available models:\n"
    "  * grok-4.5 (default)\n"
)


def test_current_grok_zero_exit_signed_out_metadata_is_auth_required() -> None:
    signed_out = "You are not authenticated.\n\nDefault model: grok-4.5\nAvailable models:\n  * grok-4.5 (default)\n"
    inventory = C.parse_grok_models(signed_out)
    assert inventory.auth_required_reported is True
    calls = iter([
        (0, "grok 0.2.118", "", False, None),
        (0, signed_out, "", False, None),
    ])
    probe = GB.probe_grok(runner=lambda _argv: next(calls), executable="grok")
    assert probe.auth_state == C.AUTH_REQUIRED
    assert probe.selectable_models() == ()
# A three-slug SUBSET of the eleven the capture records, chosen to include the two other
# vendors' models the Antigravity subscription lists (U246). GROK_MODELS_OUT is verbatim.
AGY_MODELS_OUT = (
    "gemini-3.6-flash-high\n"
    "gemini-3.1-pro-high\n"
    "claude-sonnet-4-6\n"
)

OK = lambda out="", err="": (0, out, err, False, None)          # noqa: E731
FAIL = lambda rc, out="", err="": (rc, out, err, False, None)   # noqa: E731


def fake_runner(responses):
    """Runner keyed by the joined ARGUMENT tail (argv minus the executable), matching the 18A
    suite's convention so a test never has to know the resolved executable path."""

    def run(argv):
        key = " ".join(list(argv)[1:])
        if key not in responses:
            raise AssertionError(f"unscripted provider call: {key!r}")
        return responses[key]

    return run


def grok_runner(models_out=GROK_MODELS_OUT, version="grok 0.2.118 (1e1687c1cf)"):
    return fake_runner({"--version": OK(version), "models": OK(models_out)})


def agy_runner(models_out=AGY_MODELS_OUT, version="1.1.9"):
    return fake_runner({"--version": OK(version), "models": OK(models_out)})


def ctx(**kw):
    base = dict(node_id="n-1", role="worker", project_id="p-1", permission_profile_id="pp-1",
                mcp_credential_id="mcp-ref-1", spawned_by_supervisor=True)
    base.update(kw)
    return AdapterContext(**base)


# =============================================================================================
# The argv emission guard — U249 / U250 / U235
# =============================================================================================
class TestArgvGuard:
    @pytest.mark.parametrize("argv", [
        ["grok", "--always-approve"],
        ["agy", "--dangerously-skip-permissions"],
        ["grok", "--permission-mode", "bypassPermissions"],
        ["agy", "--mode", "accept-edits"],
    ])
    def test_the_18a_refusals_still_hold(self, argv):
        with pytest.raises(ValueError):
            C.assert_no_forbidden_provider_args(argv)

    @pytest.mark.parametrize("argv", [
        ["agy", "-dangerously-skip-permissions"],
        ["grok", "-always-approve"],
        ["agy", "-mode", "accept-edits"],
        ["agy", "-mode=accept-edits"],
        ["grok", "-permission-mode=bypassPermissions"],
    ])
    def test_u249_single_dash_spellings_are_refused_too(self, argv):
        """`agy --help` is Go `flag`-package output: single- and double-dash spellings are
        interchangeable on that CLI. The guard compared double-dash tokens only, so the single-dash
        twin of every forbidden flag passed through a check described as structural."""
        with pytest.raises(ValueError):
            C.assert_no_forbidden_provider_args(argv)

    def test_a_benign_mode_is_still_accepted_in_either_spelling(self):
        C.assert_no_forbidden_provider_args(["grok", "--permission-mode", "plan"])
        C.assert_no_forbidden_provider_args(["agy", "-mode", "plan"])

    @pytest.mark.parametrize("flag", ["--xai-api-base-url", "--cli-chat-proxy-base-url",
                                      "--grok-ws-url", "--grok-ws-origin", "--leader-socket"])
    def test_u250_endpoint_overrides_are_refused_on_the_argv_surface_too(self, flag):
        """The env scrub removes `XAI_API_BASE_URL`, and the module claimed on that basis that no
        endpoint override could redirect a call. These are its argv twins, documented in
        `grok agent --help`: the two policies now agree instead of one covering for the other."""
        assert flag in C.FORBIDDEN_PROVIDER_ARGS
        with pytest.raises(ValueError):
            C.assert_no_forbidden_provider_args(["grok", "agent", flag, "https://example.invalid"])

    @pytest.mark.parametrize("flag", ["--agent", "--agent-profile", "--reauth"])
    def test_u250_identity_and_auth_flags_are_refused(self, flag):
        """`--agent`/`--agent-profile` widen *who acts* — the module's own stated rationale for
        guarding `--agents`. `--reauth` starts an authentication flow inside a headless child;
        authentication is an explicit operator action through the runner, never an adapter's."""
        assert flag in C.FORBIDDEN_PROVIDER_ARGS
        with pytest.raises(ValueError):
            C.assert_no_forbidden_provider_args(["grok", flag, "x"])

    @pytest.mark.parametrize("flag", ["--cwd", "--add-dir"])
    def test_the_workspace_binding_flags_are_deliberately_not_banned(self, flag):
        """U250 left this to 18B and it is decided here rather than left ambiguous: these BIND a
        workspace, which is what the isolation path needs, so banning them would ban the adapter's
        own containment — and this build emits them itself."""
        assert flag not in C.FORBIDDEN_PROVIDER_ARGS
        emitted = (GB.GrokCliBackend("grok", workdir="D:/ws").build_command("hi")
                   + AG.AntigravityCliBackend("agy", workdir="D:/ws").build_command("hi"))
        assert flag in emitted

    def test_project_is_unbanned_for_a_different_reason_than_the_other_two(self):
        """spec-audit Md-3: `--project` was grouped with `--cwd`/`--add-dir` under a
        workspace-binding warrant that is false of it — the capture calls it "Project ID for the
        current CLI session", a session selector, not a directory bind. It stays unbanned because
        U250 left the call to 18B and banning a selector nothing emits is noise (U266); the warrant
        is now stated separately, and this pins the "nothing emits it" half."""
        assert "--project" not in C.FORBIDDEN_PROVIDER_ARGS
        emitted = (GB.GrokCliBackend("grok", workdir="D:/ws").build_command("hi")
                   + AG.AntigravityCliBackend("agy", workdir="D:/ws").build_command("hi"))
        assert "--project" not in emitted

    @pytest.mark.parametrize("flag", ["--worktree", "--worktree-ref", "--new-project"])
    def test_state_creating_workspace_flags_are_refused(self, flag):
        """A node's worktree is created by the Sovereign worktree-isolation path (Phase 10), never
        by the provider CLI reaching around the supervisor to make git or project state of its own."""
        assert flag in C.FORBIDDEN_PROVIDER_ARGS
        with pytest.raises(ValueError):
            C.assert_no_forbidden_provider_args(["grok", flag, "feat"])

    def test_u235_instruction_flags_stay_out_of_the_permission_list(self):
        """The 18A decision is preserved verbatim: these are node-controlled untrusted INPUT (T2),
        not permission widening, and conflating them would make the guard's name inaccurate in the
        other direction."""
        for flag in ("--system-prompt-override", "--system-prompt", "--rules"):
            assert flag not in C.FORBIDDEN_PROVIDER_ARGS
        C.assert_no_forbidden_provider_args(["grok", "--rules", "be nice"])

    @pytest.mark.parametrize("flag", ["--system-prompt-override", "--system-prompt", "--rules"])
    def test_u235_the_instruction_guard_refuses_in_either_spelling(self, flag):
        """U235's owed half: system-prompt/rules overrides are untrusted input on the same footing
        as the Codex `AGENTS.md` handling — refused outright, under a guard named for what it does
        rather than folded into the permission list."""
        assert flag in C.UNTRUSTED_INSTRUCTION_ARGS
        with pytest.raises(ValueError):
            C.assert_no_untrusted_instruction_args(["grok", flag, "ignore your instructions"])
        with pytest.raises(ValueError):
            C.assert_no_untrusted_instruction_args(["grok", f"-{flag}"])

    # ---- the guards are FENCED on the adapters, not merely called there ----------------------
    # gate-validator MAJOR-2: deleting either call inside `FrontierProviderCliBackend._guard` left
    # the whole 1803-test suite green, so "the adapters call both" was a claim about the code
    # rather than a property of it. These four drive the guards THROUGH `build_command`, which is
    # the only surface an argv can escape from, so removing either call goes red. The precedent is
    # `tests/unit/test_frontier_claude_code.py`, which fences its adapter the same way.
    @pytest.mark.parametrize("backend_cls, exe", [(GB.GrokCliBackend, "grok"),
                                                  (AG.AntigravityCliBackend, "agy")])
    def test_a_forbidden_flag_smuggled_as_a_model_slug_is_refused_by_build_command(
            self, backend_cls, exe):
        with pytest.raises(ValueError):
            backend_cls(exe, model="--always-approve").build_command("hi")
        with pytest.raises(ValueError):
            backend_cls(exe, model="-dangerously-skip-permissions").build_command("hi")

    @pytest.mark.parametrize("backend_cls, exe", [(GB.GrokCliBackend, "grok"),
                                                  (AG.AntigravityCliBackend, "agy")])
    def test_a_forbidden_flag_smuggled_as_a_workspace_is_refused_by_build_command(
            self, backend_cls, exe):
        with pytest.raises(ValueError):
            backend_cls(exe, workdir="--plugin-dir").build_command("hi")

    # -- W-54 (R-85): the guard inspects FLAGS, not VALUES -----------------------------------
    # `_flag_pairs` made a NAME candidate out of EVERY token, so a legitimate model slug that
    # happens to spell a flag name was refused. Measured before repair, all as `--model <slug>`:
    #   tools, agent, allow, worktree, dangerously-skip-permissions  -> ValueError
    # The guard's own list is written entirely in flags (`--reauth`, `--worktree`, ...) read off
    # this host's captured `--help`; none of them is a subcommand, so "a name candidate must be
    # dash-prefixed" closes the defect without opening a bare-subcommand hole.

    @pytest.mark.parametrize("slug", ["tools", "agent", "allow", "worktree", "agents",
                                      "no-plan", "reauth", "new-project", "yolo",
                                      "dangerously-skip-permissions", "always-approve"])
    @pytest.mark.parametrize("backend_cls, exe", [(GB.GrokCliBackend, "grok"),
                                                  (AG.AntigravityCliBackend, "agy")])
    def test_W54_a_model_slug_that_SPELLS_a_flag_name_still_builds(self, backend_cls, exe, slug):
        """R-85. A provider is free to name a model `tools`; this build is not free to refuse it for
        resembling one of our own flag names. The VALUE position is what makes it a value."""
        argv = backend_cls(exe, model=slug).build_command("hi")
        assert slug in argv
        assert argv[argv.index(slug) - 1].lstrip("-") in ("model", "m")

    @pytest.mark.parametrize("backend_cls, exe", [(GB.GrokCliBackend, "grok"),
                                                  (AG.AntigravityCliBackend, "agy")])
    def test_W54_a_DASH_PREFIXED_value_is_still_treated_as_a_flag(self, backend_cls, exe):
        """The property that must NOT loosen, and the reason the rule is "dash-prefixed" rather than
        "not in value position": a token carrying a dash is treated as a flag WHEREVER it appears,
        so the smuggling guard above keeps working. Without this the repair would trade one defect
        for a worse one."""
        for smuggled in ["--tools", "-tools", "--always-approve", "-dangerously-skip-permissions",
                         "--allow", "--worktree"]:
            with pytest.raises(ValueError):
                backend_cls(exe, model=smuggled).build_command("hi")

    def test_W54_the_guard_still_refuses_the_flag_forms_directly(self):
        """The guard called on argv directly, both spellings and the inline form, so the repair is
        not measured only through the two builders."""
        for argv in (["agy", "--tools", "x"], ["agy", "-tools", "x"],
                     ["agy", "--allow", "rule"], ["agy", "--permission-mode=bypassPermissions"],
                     ["agy", "--permission-mode", "bypassPermissions"]):
            with pytest.raises(ValueError):
                C.assert_no_forbidden_provider_args(argv)

    def test_W54_a_flag_VALUE_never_satisfies_the_permission_mode_rule(self):
        """The mode rule reads a flag's value on purpose, and that must be unchanged: it is the one
        place a VALUE is authoritative, and it is keyed to the flag that owns it."""
        C.assert_no_forbidden_provider_args(["agy", "--model", "bypassPermissions"])
        with pytest.raises(ValueError):
            C.assert_no_forbidden_provider_args(["agy", "--permission-mode", "bypassPermissions"])

    def test_W54_an_instruction_override_slug_also_builds_when_it_is_a_VALUE(self):
        """The other guard, same defect. `rules` and `system-prompt` are model-slug-shaped words."""
        for slug in ["rules", "system-prompt", "system-prompt-override"]:
            C.assert_no_untrusted_instruction_args(["agy", "--model", slug, "-p", "hi"])
        with pytest.raises(ValueError):
            C.assert_no_untrusted_instruction_args(["agy", "--rules", "x"])

    @pytest.mark.parametrize("backend_cls, exe", [(GB.GrokCliBackend, "grok"),
                                                  (AG.AntigravityCliBackend, "agy")])
    def test_an_instruction_override_smuggled_into_argv_is_refused_by_build_command(
            self, backend_cls, exe):
        """The instruction guard specifically — this is the one whose removal left the suite green.
        `--rules` is in NEITHER forbidden list, so only `assert_no_untrusted_instruction_args` can
        refuse it, and only if `build_command` actually calls it."""
        assert "--rules" not in C.FORBIDDEN_PROVIDER_ARGS
        with pytest.raises(ValueError):
            backend_cls(exe, model="--rules").build_command("hi")
        with pytest.raises(ValueError):
            backend_cls(exe, workdir="--system-prompt-override").build_command("hi")

    def test_every_forbidden_flag_is_either_in_the_capture_or_declared_absent(self):
        """U263 / operator directive §2: the module claims its refusals were read off the installed
        surface. Four are Claude/Codex spellings carried over from 18A and are DECLARED as such;
        every other entry must appear in the recorded capture. Add a remembered flag without
        evidence and this goes red — which is what makes the §2 claim mean anything."""
        import pathlib

        capture = (pathlib.Path(__file__).resolve().parents[2]
                   / "docs" / "evidence" / "live" / "phase18a_host_recon.json")
        text = capture.read_text(encoding="utf-8").lower()
        undeclared = [f for f in C.FORBIDDEN_PROVIDER_ARGS
                      if f not in C.CAPTURE_ABSENT_SUPERSET_ARGS and f not in text]
        assert not undeclared, f"asserted from memory, not from the capture: {undeclared}"
        for f in C.CAPTURE_ABSENT_SUPERSET_ARGS:
            assert f in C.FORBIDDEN_PROVIDER_ARGS
            assert f not in text, f"{f} IS in the capture — it is no longer a declared superset"

    def test_a_prompt_that_looks_like_a_flag_is_not_misread(self):
        """Both builders guard the FLAGS before the prompt is appended, so a benign prompt whose
        text happens to equal a forbidden token is never read as smuggling one (argv is a list;
        subprocess never word-splits it)."""
        argv = GB.GrokCliBackend("grok").build_command("--always-approve")
        assert argv[-1] == "--always-approve"
        argv = AG.AntigravityCliBackend("agy").build_command("--dangerously-skip-permissions")
        assert argv[-1] == "--dangerously-skip-permissions"


# =============================================================================================
# Credential isolation (operator directive §13) — enumeration, scrub, non-disclosure
# =============================================================================================
class TestCredentialIsolation:
    @pytest.mark.parametrize("key", ["XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                                     "GROK_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
                                     "ANTIGRAVITY_API_KEY", "XAI_API_BASE_URL"])
    def test_every_directive_named_key_is_scrubbed(self, key):
        assert C.is_provider_credential_env_key(key)
        env = C.scrub_provider_env({key: "s3cret", "PATH": "/usr/bin"})
        assert key not in env and env["PATH"] == "/usr/bin"

    def test_a_future_provider_key_is_scrubbed_by_default(self):
        assert C.is_provider_credential_env_key("XAI_SESSION_TOKEN")
        assert C.is_provider_credential_env_key("SOME_VENDOR_SECRET")

    def test_the_allowlist_membership_is_pinned_not_merely_honoured(self):
        """Parameterising over the set could not fail for any key ADDED to it — an allowlist that
        exempts names from a fail-closed classifier has to have its membership pinned, or "narrow
        and enumerated" is a word rather than a property (spec-audit MINOR). `GROK_SANDBOX` is the
        only member with capture evidence (`[env: GROK_SANDBOX=]`); the four config/auth-directory
        pointers that used to ride along were removed (U265)."""
        assert C.PRESERVED_PROVIDER_CONFIG_KEYS == frozenset({"GROK_SANDBOX"})
        assert not C.is_provider_credential_env_key("GROK_SANDBOX")
        assert C.scrub_provider_env({"GROK_SANDBOX": "some-profile"})["GROK_SANDBOX"] == "some-profile"

    @pytest.mark.parametrize("key", ["GROK_CONFIG_DIR", "GROK_HOME", "ANTIGRAVITY_HOME",
                                     "ANTIGRAVITY_CONFIG_DIR"])
    def test_the_undocumented_config_pointers_are_scrubbed_again(self, key):
        """U265: nothing in the capture documents these, so lifting them over the classifier was an
        analogy to `CODEX_HOME` rather than evidence — and it is not the same mechanism, because
        `CODEX_HOME` survives passively while these were actively exempted."""
        assert C.is_provider_credential_env_key(key)
        assert key not in C.scrub_provider_env({key: "C:/x"})

    @pytest.mark.parametrize("key", ["NODE_OPTIONS", "NODE_EXTRA_CA_CERTS"])
    def test_the_node_injection_variables_are_scrubbed(self, key):
        """U264: `grok` is installed with `npm install -g`. `NODE_OPTIONS` can inject a `--require`
        module into the child and `NODE_EXTRA_CA_CERTS` can trust an interception proxy's CA;
        neither name carries a prefix or substring the nets would have caught."""
        assert C.is_provider_credential_env_key(key)
        assert key not in C.scrub_provider_env({key: "x"})

    @pytest.mark.parametrize("key", ["HTTP_PROXY", "HTTPS_PROXY"])
    def test_the_proxy_variables_survive_and_that_is_recorded_not_claimed_away(self, key):
        """The honest half of U264: an operator's proxy is preserved because removing it breaks the
        CLI on a network that requires one — so a host-level proxy remains an environment route
        this build does NOT close. The claim in the code is narrowed to match; this pins the fact."""
        assert not C.is_provider_credential_env_key(key)
        assert key in C.scrub_provider_env({key: "http://proxy.invalid:8080"})

    @pytest.mark.parametrize("backend_cls, exe", [(GB.GrokCliBackend, "grok"),
                                                  (AG.AntigravityCliBackend, "agy")])
    def test_the_backend_env_carries_no_credential(self, backend_cls, exe):
        # the GROK_SANDBOX value is an opaque placeholder, NOT a profile name: this build refuses
        # to invent one, and a test that named one would be doing what the module refuses to do
        env = backend_cls(exe).build_env({"XAI_API_KEY": "k", "GEMINI_API_KEY": "k",
                                          "PATH": "/usr/bin", "GROK_SANDBOX": "<operator-set>"})
        assert "XAI_API_KEY" not in env and "GEMINI_API_KEY" not in env
        assert env["PATH"] == "/usr/bin" and env["GROK_SANDBOX"] == "<operator-set>"

    @pytest.mark.parametrize("backend_cls, exe", [(GB.GrokCliBackend, "grok"),
                                                  (AG.AntigravityCliBackend, "agy")])
    def test_no_credential_flag_can_reach_the_command_line(self, backend_cls, exe):
        argv = backend_cls(exe, model="m").build_command("hello")
        for bad in ("--api-key", "--with-api-key", "--with-access-token"):
            assert bad not in argv

    def test_the_published_policy_matches_the_code(self):
        """The evidence surface must be checkable against the classifier, exceptions included —
        evidence that omits the allowlist cannot be audited."""
        policy = C.credential_policy()
        assert set(policy["scrubbed_env_keys"]) == set(C.PROVIDER_CREDENTIAL_ENV_KEYS)
        assert set(policy["scrubbed_key_prefixes"]) == set(C.CREDENTIAL_KEY_PREFIXES)
        assert set(policy["scrubbed_key_substrings"]) == set(C.CREDENTIAL_KEY_SUBSTRINGS)
        assert set(policy["preserved_non_secret_config_keys"]) == set(C.PRESERVED_PROVIDER_CONFIG_KEYS)
        assert policy["reads_credentials_by_design"] is False

    def test_the_no_credentials_claim_carries_evidence_that_can_go_missing(self):
        """A bare boolean is a constant asserted against itself: it cannot go false when the code
        misbehaves. Round 4 corrected that in the recon report by naming the enforcing tests; the
        policy object re-created the defect one layer down when it moved here (spec-audit Md-6).
        Rename or delete a named test and this goes red, so the claim cannot outlive its evidence."""
        import pathlib

        repo_root = pathlib.Path(__file__).resolve().parents[2]
        refs = C.credential_policy()["claim_basis"]["enforced_by"]
        assert refs, "a claim with no named evidence is prose"
        for ref in refs:
            path, _, node = ref.partition("::")
            source = (repo_root / path).read_text(encoding="utf-8")
            for name in node.split("::"):
                assert f"class {name}" in source or f"def {name}" in source, (
                    f"{ref} names {name!r}, which does not exist in {path}")


# =============================================================================================
# Model enumeration (operator directive §8) — from the CLI's own list, fail closed
# =============================================================================================
class TestModelEnumeration:
    def test_grok_models_are_read_from_the_cli_listing(self):
        probe = GB.probe_grok(runner=grok_runner(), executable="C:/x/grok.cmd")
        assert probe.present is True
        assert probe.models == ("grok-4.5",)
        assert probe.default_model == "grok-4.5"
        assert probe.auth_state == C.AUTH_AUTHENTICATED

    def test_antigravity_models_are_read_from_the_cli_listing(self):
        probe = AG.probe_antigravity(runner=agy_runner(), executable="C:/x/agy.exe")
        assert probe.models == ("gemini-3.6-flash-high", "gemini-3.1-pro-high", "claude-sonnet-4-6")
        assert probe.default_model is None
        # no offline auth surface on this CLI: never AUTHENTICATED, never AUTH_REQUIRED
        assert probe.auth_state == C.AUTH_UNVERIFIED

    def test_an_unparseable_listing_yields_no_models_rather_than_a_guess(self):
        probe = GB.probe_grok(runner=grok_runner(models_out="Error: could not reach the service\n"),
                              executable="grok")
        assert probe.models == ()
        assert "fail closed" in probe.model_note

    def test_a_failed_listing_is_not_an_inventory(self):
        runner = fake_runner({"--version": OK("grok 0.2.118"),
                              "models": FAIL(1, "", "not logged in")})
        probe = GB.probe_grok(runner=runner, executable="grok")
        assert probe.models == ()
        assert probe.auth_state == C.AUTH_REQUIRED

    def test_a_missing_executable_is_a_recorded_fact_not_a_crash(self):
        probe = GB.probe_grok(runner=fake_runner({}), executable=None)
        assert probe.present is False and probe.models == ()
        assert "not found" in probe.detail

    @pytest.mark.parametrize("raw, expected", [("grok 0.2.118 (1e1687c1cf)", (0, 2, 118)),
                                               ("1.1.9", (1, 1, 9)), ("nonsense", None)])
    def test_version_parsing(self, raw, expected):
        assert C.parse_version(raw) == expected

    def test_an_unparseable_version_fails_closed(self):
        probe = AG.probe_antigravity(runner=agy_runner(version="dev-build"), executable="agy")
        assert probe.version_tuple is None and probe.meets_minimum is False

    def test_the_enumerator_never_invents_a_model_for_an_empty_listing(self):
        probe = AG.probe_antigravity(runner=agy_runner(models_out="\n\n"), executable="agy")
        assert probe.models == ()
        assert probe.selectable_models() == ()


# =============================================================================================
# Headless command construction (operator directive §10) — the installed surface is authoritative
# =============================================================================================
class TestHeadlessCommandConstruction:
    def test_grok_headless_argv(self):
        argv = GB.GrokCliBackend("grok", model="grok-4.5", workdir="D:/ws").build_command("hi")
        assert argv[0] == "grok"
        assert argv[argv.index("--cwd") + 1] == "D:/ws"
        assert argv[argv.index("--permission-mode") + 1] == GB.GROK_HEADLESS_PERMISSION_MODE
        # cross-session memory is a blanket-context vector (invariants 8/9); pinned off because the
        # capture documents `--no-memory` on the surface this build uses
        assert GB.GROK_NO_MEMORY_FLAG in argv
        assert argv[argv.index("-m") + 1] == "grok-4.5"
        assert argv[argv.index("--output-format") + 1] == "json"
        assert argv[-2] == "-p" and argv[-1] == "hi"

    def test_grok_omits_the_flag_this_build_does_not_have(self):
        """Operator directive §10 quoted `--no-auto-update`; this build of `grok` has no such flag
        and the installed surface wins (§2). Including it would abort the call on an unknown flag."""
        argv = GB.GrokCliBackend("grok").build_command("hi")
        assert "--no-auto-update" not in argv

    def test_antigravity_headless_argv(self):
        argv = AG.AntigravityCliBackend("agy", model="gemini-3.1-pro-high",
                                        workdir="D:/ws").build_command("hi")
        assert argv[0] == "agy"
        assert "--cwd" not in argv                      # this CLI has no such flag
        assert argv[argv.index("--add-dir") + 1] == "D:/ws"
        assert argv[argv.index("--mode") + 1] == AG.ANTIGRAVITY_HEADLESS_MODE
        assert argv[argv.index("--model") + 1] == "gemini-3.1-pro-high"
        assert argv[argv.index("--output-format") + 1] == "json"
        assert argv[-2] == "-p" and argv[-1] == "hi"

    @pytest.mark.parametrize("backend_cls, exe", [(GB.GrokCliBackend, "grok"),
                                                  (AG.AntigravityCliBackend, "agy")])
    def test_no_model_means_the_cli_default_and_no_invented_slug(self, backend_cls, exe):
        argv = backend_cls(exe).build_command("hi")
        assert "-m" not in argv and "--model" not in argv

    @pytest.mark.parametrize("backend_cls, exe", [(GB.GrokCliBackend, "grok"),
                                                  (AG.AntigravityCliBackend, "agy")])
    def test_the_restrictive_mode_is_pinned_explicitly(self, backend_cls, exe):
        """Pinned so a node-controlled config file cannot supply a permissive default instead
        (§11). It is an argument the harness honours, not OS-level containment (I-29, U25)."""
        argv = backend_cls(exe).build_command("hi")
        flag = "--permission-mode" if exe == "grok" else "--mode"
        assert flag in argv
        assert argv[argv.index(flag) + 1] not in C.FORBIDDEN_PERMISSION_MODES

    @pytest.mark.parametrize("backend_cls", [GB.GrokCliBackend, AG.AntigravityCliBackend])
    def test_only_the_reasoning_role_exists_and_a_coding_role_is_refused(self, backend_cls):
        """Recorded decision: a coding role would need either an auto-approving permission mode
        (forbidden by §11) or a sandbox profile whose values neither CLI documents (fabrication).
        Directive §10's own "initial provider behavior" IS the reasoning role. Refused, not faked."""
        with pytest.raises(ValueError):
            backend_cls("x", role="coding")


# =============================================================================================
# Backend behaviour — exit-code-first, auth pause, instrumentation
# =============================================================================================
class TestBackendBehaviour:
    def test_the_mock_backend_is_deterministic_and_counts_calls(self):
        b = GB.MockGrokCliBackend(model="grok-4.5")
        first, second = b.generate("x"), b.generate("x")
        assert first == second and b.calls == 2

    @pytest.mark.parametrize("text", ["not logged in", "HTTP 401", "usage limit reached",
                                      "rate limit exceeded"])
    def test_auth_and_quota_conditions_are_a_pause_not_a_task_failure(self, text):
        assert C.is_auth_pause_text(text) is True

    def test_an_ordinary_runtime_fault_is_not_an_auth_pause(self):
        assert C.is_auth_pause_text("panic: index out of range") is False

    def test_a_zero_exit_transcript_with_historical_error_words_is_not_demoted(self):
        """The Codex-period lesson, binding for every provider (operator directive §6): exit code
        first. A successful call whose text mentions a past login problem is a SUCCESS."""
        out = json.dumps({"result": "Earlier you were not logged in; now you are. All good."})
        res = C.classify_provider_outcome(0, out, "", structured_error=C.structured_error_of(out))
        assert res.ok is True and res.basis == "exit-code-zero"

    def test_a_structured_error_field_on_a_zero_exit_is_a_failure(self):
        out = json.dumps({"error": {"code": "bad_request"}})
        res = C.classify_provider_outcome(0, out, "", structured_error=C.structured_error_of(out))
        assert res.ok is False and res.basis == "structured-error-field"

    def test_a_nonzero_exit_with_an_auth_marker_is_auth_required(self):
        res = C.classify_provider_outcome(1, "", "not logged in — run `grok login`")
        assert res.outcome == C.OUTCOME_AUTH_REQUIRED

    def test_the_response_text_is_extracted_from_structured_output(self):
        assert C.extract_provider_text(json.dumps({"result": "hello"})) == "hello"
        assert C.extract_provider_text("plain text") == "plain text"

    @pytest.mark.parametrize("backend_cls, exe", [(GB.GrokCliBackend, "grok"),
                                                  (AG.AntigravityCliBackend, "agy")])
    def test_generate_refuses_while_no_supervised_path_exists(self, backend_cls, exe):
        """U268 — the fence behind the sentence. "Reachable only from a governed live path" was
        true only because nothing imported these modules, which is the absence of a caller, not a
        mechanism: `NodeRegistry` gates node RECORDS, and `AdapterContext.spawned_by_supervisor` is
        a caller-set bool. `generate` now refuses outright, and refuses BEFORE the call counter, so
        the refusal cannot be mistaken for a spent attempt."""
        backend = backend_cls(exe)
        assert backend._LIVE_SPAWN_PATH_WIRED is False
        with pytest.raises(C.ProviderAuthPause) as exc:
            backend.generate("hi")
        assert "naked" in str(exc.value) and "nothing was spent" in str(exc.value).lower()
        assert backend.calls == 0

    # -- W-50 (R-24): generate() CONSUMES the classifier verdict -----------------------------
    # It used to re-derive the pause by searching `outcome.detail`, which is
    # `redact_diagnostics(stderr or stdout)` -- ONE stream, and at most MAX_DIAGNOSTIC_CHARS of it.
    # The classifier had already read BOTH streams in full. Measured divergence, twice:
    #   auth marker on STDOUT with any stderr noise -> detail is the stderr, marker absent;
    #   auth marker past the 600-char redaction limit -> truncated away.
    # Both made a real authentication failure an ordinary RuntimeError, and the node was never
    # paused. The verdict is the fact; the detail is a human-readable excerpt, and an excerpt is
    # not evidence.

    @staticmethod
    def _run_generate(monkeypatch, rc, out, err):
        import types

        from adapters.frontier import process_tree

        monkeypatch.setattr(
            process_tree, "run_managed_process",
            lambda cmd, **kw: types.SimpleNamespace(returncode=rc, stdout=out, stderr=err,
                                                    spawned_pids=()))
        backend = GB.GrokCliBackend("grok")
        backend._LIVE_SPAWN_PATH_WIRED = True
        return backend

    def test_1_a_stdout_only_auth_failure_pauses_the_node(self, monkeypatch):
        b = self._run_generate(monkeypatch, 1, "Error: not authenticated. Please log in.", "")
        with pytest.raises(C.ProviderAuthPause):
            b.generate("q")

    def test_2_a_stderr_only_auth_failure_pauses_the_node(self, monkeypatch):
        b = self._run_generate(monkeypatch, 1, "", "not authenticated")
        with pytest.raises(C.ProviderAuthPause):
            b.generate("q")

    def test_3_the_verdict_is_STREAM_SYMMETRIC_because_it_is_classified_once(self, monkeypatch):
        """Auth evidence reaching the classifier from EITHER stream produces the SAME verdict and
        the same pause, because there is ONE classification over both.

        Written this way after a first attempt tried to straddle a marker across the two streams
        and could not: the classifier joins them with a newline, so a contiguous marker never
        spans the boundary. Symmetry is the property that is actually true and actually matters --
        a per-stream rule would answer differently depending on where the CLI happened to print,
        which is exactly the defect this unit repairs."""
        marker = "not authenticated"
        on_stdout = C.classify_provider_outcome(1, f"Error: {marker}", "warning: noise")
        on_stderr = C.classify_provider_outcome(1, "warning: noise", f"Error: {marker}")
        assert on_stdout.outcome == on_stderr.outcome == C.OUTCOME_AUTH_REQUIRED
        for out, err in ((f"Error: {marker}", "warning: noise"),
                         ("warning: noise", f"Error: {marker}")):
            b = self._run_generate(monkeypatch, 1, out, err)
            with pytest.raises(C.ProviderAuthPause):
                b.generate("q")
    def test_4_an_ordinary_failure_is_NOT_an_auth_pause(self, monkeypatch):
        """The direction that stops the unit being satisfied by pausing on everything. A node-wide
        pause for an ordinary fault is its own defect (see W-48)."""
        b = self._run_generate(monkeypatch, 1, "boom", "segfault")
        with pytest.raises(RuntimeError) as exc:
            b.generate("q")
        assert not isinstance(exc.value, C.ProviderAuthPause)

    def test_5_an_exit_zero_answer_mentioning_auth_prose_does_not_pause(self, monkeypatch):
        """Exit-code-first. rc == 0 is structured evidence of success and is never demoted by
        transcript text -- the same rule W-48 restored on the codex path."""
        answer = "If not logged in, redirect to the rate limit page."
        b = self._run_generate(monkeypatch, 0, answer, "")
        assert answer in b.generate("q")

    def test_6_the_VERDICT_pauses_even_when_the_detail_carries_no_trigger_prose(self, monkeypatch):
        """THE DECISIVE TEST. It proves the repair CONSUMES the structured verdict rather than
        coincidentally re-deriving the same answer from text: the excerpt that reaches `generate`
        contains NONE of the trigger prose, so any downstream re-scan must answer 'no pause'.

        Constructed two ways, because they are two different mechanisms:
          (a) WRONG STREAM  -- the marker is on stdout, `detail` is built from the stderr;
          (b) TRUNCATION    -- the marker sits past the redaction limit.
        Each is asserted to be genuinely prose-free before being used, so the test cannot pass by
        accident if `redact_diagnostics` changes."""
        wrong_stream = (1, "Error: not authenticated.", "warning: config file not found")
        truncated = (1, ("x" * (C.MAX_DIAGNOSTIC_CHARS + 100)) + " not authenticated", "")
        for rc, out, err in (wrong_stream, truncated):
            outcome = C.classify_provider_outcome(rc, out, err)
            assert outcome.outcome == C.OUTCOME_AUTH_REQUIRED, "the classifier must see it"
            assert not C.is_auth_pause_text(outcome.detail), (
                "the excerpt still carries the trigger, so this case cannot prove consumption")
            b = self._run_generate(monkeypatch, rc, out, err)
            with pytest.raises(C.ProviderAuthPause):
                b.generate("q")

    def test_a_usage_limit_verdict_also_pauses(self, monkeypatch):
        """`USAGE_LIMIT` is the rate/quota half of the same fail-closed pause (Plan 18.4), and it
        is a SEPARATE verdict value -- consuming only the auth one would leave it an ordinary
        failure."""
        b = self._run_generate(monkeypatch, 1, "", "usage limit reached for this account")
        assert C.classify_provider_outcome(1, "", "usage limit reached for this account").outcome \
            == C.OUTCOME_USAGE_LIMIT
        with pytest.raises(C.ProviderAuthPause):
            b.generate("q")

    # -- W-51 (R-25): an unprobed label must not reach `--model` -----------------------------
    # `resolve_model_ref` refused an out-of-inventory slug ONLY when `available` was truthy, so an
    # EMPTY or UNESTABLISHED inventory disabled the very check meant to stop an unverified label.
    # Measured before repair: requested="attacker-or-unprobed-label", available=() returned the
    # slug carried "unverified", and it reached argv as
    #   ['agy', '--mode', 'plan', '--model', 'attacker-or-unprobed-label', ...]
    #
    # EMPTY MUST MEAN "no verified model information", NEVER "therefore every requested model is
    # permitted" — which is the same optimistic reading of emptiness W-44/W-45 repaired one layer up.

    def test_W51_none_preserves_the_provider_default_path(self):
        """`None` IS NOT an unverified label. It means "omit the flag, let the CLI use its own
        configured default", and that path is deliberately untouched — breaking it to make the
        negative green would be repairing the wrong thing."""
        slug, note = C.resolve_model_ref(None, ())
        assert slug is None
        assert "no model selected" in note
        assert C.resolve_model_ref(None, ("model-A",))[0] is None
        assert AG.AntigravityCliBackend("agy").build_command("hi").count("--model") == 0

    def test_W51_a_verified_model_is_accepted_and_emitted_exactly_once(self):
        slug, note = C.resolve_model_ref("model-A", ("model-A", "model-B"))
        assert slug == "model-A"
        assert "confirmed present" in note
        argv = AG.AntigravityCliBackend("agy", model=slug).build_command("hi")
        assert argv.count("--model") == 1
        assert argv[argv.index("--model") + 1] == "model-A"

    def test_W51_an_unknown_model_against_a_real_inventory_is_refused(self):
        """INHERITED / CONTROL — this already held before W-51 and is not what the unit repaired.
        It is pinned so the repair cannot be mistaken for having introduced it."""
        with pytest.raises(ValueError):
            C.resolve_model_ref("model-X", ("model-A", "model-B"))

    def test_W51_DECISIVE_an_unknown_model_against_an_EMPTY_inventory_is_refused(self):
        """The unit. An inventory the provider genuinely established as empty still corroborates
        NOTHING, so an explicit non-null request has no evidence behind it and is refused."""
        with pytest.raises(ValueError) as exc:
            C.resolve_model_ref("attacker-or-unprobed-label", ())
        assert "attacker-or-unprobed-label" in str(exc.value)

    def test_W51_an_UNESTABLISHED_inventory_is_refused_and_says_so_DIFFERENTLY(self):
        """The evidence rule for this unit. "the provider legitimately exposes no selectable
        models" and "the inventory was never established — probe failed, parser refused, call
        errored" reach the SAME decision for an explicit request, and they are NOT the same fact.
        The diagnostic must not pretend they are: W-44/W-45 are what happens when downstream code
        reads emptiness optimistically."""
        with pytest.raises(ValueError) as established:
            C.resolve_model_ref("some-label", ())
        with pytest.raises(ValueError) as unestablished:
            C.resolve_model_ref("some-label", None)
        assert str(established.value) != str(unestablished.value)
        assert "empty" in str(established.value).lower()
        assert "not established" in str(unestablished.value).lower()

    @pytest.mark.parametrize("bad", ["", "   ", "--model", "-m", "a b", "x" * 200])
    def test_W51_a_malformed_slug_never_reaches_argv(self, bad):
        """Refused BEFORE argv. An empty/whitespace label is the existing `None` path (no flag
        emitted); anything else non-null must be corroborated and cannot be."""
        if not bad.strip():
            assert C.resolve_model_ref(bad, ("model-A",))[0] is None
            return
        with pytest.raises(ValueError):
            C.resolve_model_ref(bad, ("model-A",))

    def test_W51_CROSS_UNIT_a_failed_listing_cannot_let_a_label_escape_through_model(self):
        """The case that proves W-51 closes the hole W-44/W-45 exposed. The parser refuses a
        provider's error page, so there is no trustworthy inventory — and an arbitrary caller label
        still cannot escape through `--model`."""
        inv = C.parse_antigravity_models("Traceback" + chr(10) + "401" + chr(10))
        assert inv.models == ()                      # W-44/W-45 hold
        with pytest.raises(ValueError):
            C.resolve_model_ref("renderer-supplied-label", inv.models)
        with pytest.raises(ValueError):
            AG.roster_descriptor("renderer-supplied-label", inv.models)

    def test_W51_the_roster_refuses_rather_than_publishing_an_unverified_slug(self):
        """The surface. `roster_descriptor` used to publish the slug with `verified: False` and a
        note admitting nothing could confirm it — honest, but it still handed the caller a slug.
        Refusal is the acceptance this unit was given."""
        with pytest.raises(ValueError):
            AG.roster_descriptor("unprobed-label", ())
        with pytest.raises(ValueError):
            AG.roster_descriptor("unprobed-label", None)
        ok = AG.roster_descriptor("model-A", ("model-A",))["model_ref"]
        assert ok["resolved_slug"] == "model-A" and ok["verified"] is True

    def test_a_missing_executable_is_distinguishable_from_an_auth_problem(self):
        """Operator directive §14 requires "provider executable not installed" and "authentication
        required" to read differently. Both pause the node fail-closed, so the not-spawnable case
        is a SUBCLASS rather than a separate control path."""
        assert issubclass(C.ProviderNotSpawnable, C.ProviderAuthPause)
        assert C.ProviderNotSpawnable is not C.ProviderAuthPause


# =============================================================================================
# Roster surface + the governed adapter contract
# =============================================================================================
class TestRosterAndAdapter:
    @pytest.mark.parametrize("mod, provider", [(GB, "grok_build"), (AG, "google_antigravity")])
    def test_the_roster_descriptor_surfaces_the_model_resolution(self, mod, provider):
        """W-51 changed what this test can ask for, and the change is the point. It used to call
        `roster_descriptor(requested_model="whatever-1")` with NO inventory and assert the slug came
        back resolved -- which is precisely the hole R-25 named: an unestablished inventory let an
        arbitrary label through. The descriptor shape is still what is under test here, so it is now
        asked with a CORROBORATED model; the uncorroborated call is asserted to refuse, one test
        down."""
        d = mod.roster_descriptor(requested_model="whatever-1", available=("whatever-1",))
        assert d["adapter"] == provider and d["locality"] == "frontier"
        assert d["subscription_backed"] is True
        assert d["model_ref"]["resolved_slug"] == "whatever-1"
        assert d["model_ref"]["is_fallback"] is False
        assert d["model_ref"]["verified"] is True

    @pytest.mark.parametrize("mod", [GB, AG])
    def test_W51_the_same_call_with_NO_inventory_is_refused(self, mod):
        """The R-25 hole, at the roster surface, for both OP-12 providers."""
        with pytest.raises(ValueError, match="NOT ESTABLISHED"):
            mod.roster_descriptor(requested_model="whatever-1")

    @pytest.mark.parametrize("mod", [GB, AG])
    def test_no_model_is_a_recorded_fallback_never_a_silent_one(self, mod):
        ref = mod.roster_descriptor()["model_ref"]
        assert ref["resolved_slug"] is None and ref["is_fallback"] is True
        assert "fallback" in ref["note"]

    @pytest.mark.parametrize("mod", [GB, AG])
    def test_a_requested_model_outside_the_cli_listing_is_refused(self, mod):
        """Operator directive §8: do not invent model identifiers. When an inventory is known, a
        slug outside it is refused rather than passed through to fail at spend time."""
        with pytest.raises(ValueError):
            mod.roster_descriptor(requested_model="made-up-9", available=("real-1",))

    @pytest.mark.parametrize("mod", [GB, AG])
    def test_the_adapter_refuses_a_naked_launch(self, mod):
        with pytest.raises(NakedLaunchRefused):
            mod.build_adapter(ctx(spawned_by_supervisor=False), mcp_client=object(),
                              backend=mod.mock_backend())

    @pytest.mark.parametrize("mod, provider", [(GB, "grok_build"), (AG, "google_antigravity")])
    def test_the_adapter_is_the_shared_governed_worker_contract(self, mod, provider):
        a = mod.build_adapter(ctx(), mcp_client=object(), backend=mod.mock_backend())
        cap = a.capability()
        assert cap.adapter == provider
        assert cap.node_class == "worker_reasoning"
        assert cap.locality == "frontier" and cap.subscription_backed is True
        assert cap.offline_profile_eligible is False and cap.requires_network is True
        assert a.holds_provider_credential() is False

    @pytest.mark.parametrize("provider", ["grok_build", "google_antigravity"])
    def test_a_sovereign_node_record_exists_for_these_providers_only_under_the_successor_schema(
            self, provider, tmp_path):
        """The `.scope` boundary, on the other side of the operator's ruling. It said: node@1.0's
        adapter enum has no member for either provider and the amendment is operator-reserved
        (U227), so `gate/phase-18b` must not close on "U227 is answered". It did not. OP-12.1
        (directive §17.1) then made the ruling, additively — `node@1.1` beside the untouched
        `@1.0`. The adapter now registers, and this test pins WHY: because a schema version admits
        it, which is a fact about a hashed, manifest-recorded file, not about this adapter module."""
        from control_plane.nodes.event_log import AppendOnlyEventLog
        from control_plane.nodes.registry import NodeRegistry, adapter_version_map
        reg = NodeRegistry(AppendOnlyEventLog(tmp_path / "events.jsonl"))
        rec = reg.register("n-9", "worker_reasoning", provider, spawned_by_supervisor=True)
        assert rec.adapter == provider
        assert adapter_version_map()[provider] == "node@1.1"


# =============================================================================================
# One policy, not two — the 18A tool and the 18B adapters share the guard
# =============================================================================================
class TestNoPolicyDrift:
    def test_the_recon_tool_uses_the_shared_guard_object(self):
        """A second copy of the credential/argv policy is how drift starts, and the 18A gate was
        closed twice over findings of exactly that shape. The tool re-exports; it does not restate."""
        assert R._assert_no_forbidden is C.assert_no_forbidden_provider_args
        assert R.is_provider_credential_env_key is C.is_provider_credential_env_key
        assert R.scrub_provider_env is C.scrub_provider_env
        assert R.parse_grok_models is C.parse_grok_models
        assert R.parse_antigravity_models is C.parse_antigravity_models
        assert R._FORBIDDEN_PROVIDER_ARGS is C.FORBIDDEN_PROVIDER_ARGS
        assert R._PRESERVED_PROVIDER_CONFIG_KEYS is C.PRESERVED_PROVIDER_CONFIG_KEYS

    def test_the_probe_argv_the_tool_builds_still_passes_the_widened_guard(self):
        """U250 widened the forbidden list. If a flag the 18A probe legitimately emits had landed
        in it, the tool would have started refusing its own command — this proves it did not."""
        C.assert_no_forbidden_provider_args(R.build_grok_probe_command())
        C.assert_no_forbidden_provider_args(R.build_antigravity_probe_command())
        C.assert_no_untrusted_instruction_args(R.build_grok_probe_command())

    def test_the_provider_ids_are_the_control_plane_exports(self):
        from control_plane.profiles import live_authorization as la
        assert GB.GROK_ADAPTER == la.GROK_PROVIDER
        assert AG.ANTIGRAVITY_ADAPTER == la.ANTIGRAVITY_PROVIDER

    def test_the_subscription_refs_are_the_governors_own_spelling(self):
        """The I-X3 cap is enforced PER REF, so a second spelling of one real subscription is a
        second bucket, each "at allowance" — the U76 defect. The adapters re-spelled these as
        literals one line after citing U254 against exactly that (spec-audit Md-4)."""
        from node_runtime.supervisor.subscription_governor import canonical_subscription_ref
        assert GB.GROK_SUBSCRIPTION == canonical_subscription_ref(GB.GROK_ADAPTER)
        assert AG.ANTIGRAVITY_SUBSCRIPTION == canonical_subscription_ref(AG.ANTIGRAVITY_ADAPTER)
        assert GB.GROK_SUBSCRIPTION != AG.ANTIGRAVITY_SUBSCRIPTION      # never merged (§12)

    def test_the_version_floors_and_pinned_modes_agree_with_the_18a_tool(self):
        """Duplicated constants with no pin are how two truths start. These are small enough to
        keep in both places for readability, so they are pinned equal instead of re-exported."""
        assert GB.MIN_GROK_VERSION == R.MIN_GROK_VERSION
        assert AG.MIN_ANTIGRAVITY_VERSION == R.MIN_ANTIGRAVITY_VERSION
        assert GB.GROK_HEADLESS_PERMISSION_MODE == R.GROK_PROBE_PERMISSION_MODE
        assert AG.ANTIGRAVITY_HEADLESS_MODE == R.ANTIGRAVITY_PROBE_MODE


class TestThePinnedModeSurvivedALiveTest:
    """18E `.live.shape`, 2026-08-02, U310 — a pin that was CHALLENGED on live evidence and kept.

    Grok's single-turn `-p` run returns `{"text": "", "stopReason": "cancelled", …}` on this host:
    exit zero, and the CLI says nothing. The first reading was that `plan` had no approval channel
    to hand a plan to, which would have made the pin the cause of an unanswerable probe. A second
    governed live probe with `--permission-mode default` tested exactly that and cancelled
    IDENTICALLY, so the mode is not the cause and the pin does not move — moving it would have been
    a widening bought with a refuted hypothesis.

    This test exists so the next reader finds the refutation attached to the pin rather than
    re-running it: the value is `plan`, and the reason it is still `plan` is that `default` was
    tried live and changed nothing."""

    def test_the_pin_is_plan_on_both_paths_and_the_two_agree(self):
        assert GB.GROK_HEADLESS_PERMISSION_MODE == "plan"
        argv = GB.build_interactive_grok_command("grok", model="grok-4.5", workdir="C:/ws")
        assert argv[argv.index("--permission-mode") + 1] == "plan"
        headless = GB.GrokCliBackend("grok", model="grok-4.5", workdir="C:/ws").build_command("hi")
        assert headless[headless.index("--permission-mode") + 1] == "plan"

    @pytest.mark.parametrize("build", [
        lambda: GB.build_interactive_grok_command("grok", model="grok-4.5", workdir="C:/ws"),
        lambda: GB.GrokCliBackend("grok", model="grok-4.5", workdir="C:/ws").build_command("hi"),
        lambda: R.build_grok_probe_command(),
    ])
    def test_no_plan_is_never_emitted_beside_the_pin_that_it_cancels(self, build):
        """U327, settled at Phase 19 unit 1. The untagged post-18E range emitted `--no-plan`
        alongside `--permission-mode default`; the installed capture defines that flag as "Disable
        plan mode", so shipping it beside the restored `plan` pin would cancel the pin under a
        second name. It is emitted nowhere and forbidden everywhere — both halves, or neither
        means anything."""
        argv = build()
        assert "--no-plan" not in argv
        with pytest.raises(ValueError):
            C.assert_no_forbidden_provider_args([*argv, "--no-plan"])

    def test_the_policy_refuses_every_auto_approving_mode(self):
        """What actually holds is narrower than the pin and is not affected by it: no widening
        value can be emitted at all. `default` — the value the live test tried — is permitted by
        the guard, which is why trying it was possible and why keeping `plan` is a choice rather
        than an enforcement."""
        from adapters.frontier import provider_cli_common as C
        for permitted in (GB.GROK_HEADLESS_PERMISSION_MODE, "default"):
            C.assert_no_forbidden_provider_args(["grok", "--permission-mode", permitted])
        for widening in ("acceptEdits", "auto", "dontAsk", "bypassPermissions"):
            with pytest.raises(ValueError):
                C.assert_no_forbidden_provider_args(["grok", "--permission-mode", widening])

    def test_a_benign_probe_prompt_is_not_refused_by_the_widened_guard(self):
        """gate-validator finding 8: dash-normalisation (U249) made the 18A probe builder, which
        guarded AFTER appending the prompt, refuse an operator `-Prompt agents`. The builders now
        guard the flags and then append, as the adapters do."""
        for word in ("agents", "tools", "no-plan", "worktree"):
            assert R.build_grok_probe_command(prompt=word)[-1] == word
            assert R.build_antigravity_probe_command(prompt=word)[-1] == word


class TestTheGuardHasNoExecutionProfileCarveOut:
    """Phase 19 unit 1, operator ruling **OP-13**. The carve-out this class exists to keep out was
    real, shipped, and used: the untagged post-18E range gave `assert_no_forbidden_provider_args`
    an `execution_profile` keyword whose only effect was to let `google_antigravity` emit
    `--mode accept-edits`, and pointed the Antigravity adapter and the 18A probe builder at it.

    D-P18-13 / U317: a provider CLI's own always-approve setting is never operator approval, and
    invariant 29 says the harness is never the basis for a containment claim. The guard is
    unconditional again, and the acceptance standard the operator set is that it refuses
    `accept-edits` **for every execution profile** — including profiles nobody has thought of yet,
    which is why the parameter is absent rather than defaulted off."""

    _PROFILES = ("google_antigravity", "grok_build", "claude_code", "openai_codex_cli", "", "x")

    @pytest.mark.parametrize("profile", _PROFILES)
    @pytest.mark.parametrize("argv", [
        ["agy", "--mode", "accept-edits"],
        ["agy", "-mode", "accept-edits"],
        ["agy", "--mode=accept-edits"],
        ["agy", "--mode", "ACCEPT-EDITS"],
        ["grok", "--permission-mode", "acceptEdits"],
    ])
    def test_no_profile_can_buy_an_auto_approving_mode(self, argv, profile):
        """The profile is passed the only way a caller still can — as a value inside the argv the
        guard reads — and it changes nothing. A `TypeError` here would mean the keyword came back;
        a silent pass would mean the carve-out did."""
        with pytest.raises(ValueError):
            C.assert_no_forbidden_provider_args([*argv, "--model", profile] if profile else argv)

    @pytest.mark.parametrize("profile", _PROFILES)
    def test_the_execution_profile_keyword_no_longer_exists(self, profile):
        with pytest.raises(TypeError):
            C.assert_no_forbidden_provider_args(["agy", "--mode", "accept-edits"],
                                                execution_profile=profile)

    @pytest.mark.parametrize("rule", ["mcp__sovereign__*", "Bash(*)", "mcp__other__*", ""])
    def test_no_allow_rule_survives_either_the_guard_or_any_builder(self, rule):
        """U340, closed at Phase 19 unit 1 after the spec-auditor's MAJOR-4. The untagged post-18E
        range took `--allow` off the forbidden list and permitted ONE exact value,
        `mcp__sovereign__*`, emitting it on all three Grok builders. The installed capture calls
        that flag *"Permission allow rule (compat alias: --allowedTools)"* — provider tool
        permission granted by an argv, which is the one thing this guard's docstring says never
        happens, and D-P18-13 is about the CLASS, not about one enum. So the exemption went with
        the mode carve-out: no rule is special, including the Sovereign one."""
        with pytest.raises(ValueError):
            C.assert_no_forbidden_provider_args(["grok", "--allow", rule] if rule
                                                else ["grok", "--allow"])
        assert not hasattr(C, "SOVEREIGN_GROK_ALLOW_RULE")
        for argv in (R.build_grok_probe_command(),
                     GB.GrokCliBackend("grok", workdir="C:/ws").build_command("hi"),
                     GB.build_interactive_grok_command("grok", workdir="C:/ws")):
            assert "--allow" not in argv

    def test_the_repo_config_does_not_supply_the_value_the_argv_pins(self):
        """spec-audit MEDIUM-6. `grok_build.py`'s restored comment says the pin exists *"so a
        node-controlled `~/.grok/config.toml` cannot supply a permissive default instead"* — and
        the same range that widened the adapters wrote `permission_mode = "default"` into this
        repo's own tracked `.grok/config.toml`. Argv precedence is an assumption about the harness
        (invariant 29 says do not make those), so the second source of truth is simply gone: the
        pin lives in the launch ticket's argv, one place."""
        cfg = (pathlib.Path(__file__).resolve().parents[2] / ".grok" / "config.toml").read_text(
            encoding="utf-8")
        live = [ln.strip() for ln in cfg.splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
        assert not [ln for ln in live if ln.startswith("permission_mode")]
        assert not [ln for ln in live if ln.replace(" ", "").startswith("yolo=true")]
        assert "[mcp_servers.sovereign]" in live     # MCP attachment is declared, not argv-granted

    def test_every_emitted_provider_argv_passes_the_unconditional_guard(self):
        """The other half: with no carve-out, every argv this build actually emits must be one the
        unconditional guard accepts — otherwise the revert would have left the adapters refusing
        their own commands (the failure mode `TestNoPolicyDrift` was written for)."""
        for argv in (
            R.build_grok_probe_command(),
            R.build_antigravity_probe_command(),
            GB.GrokCliBackend("grok", model="grok-4.5", workdir="C:/ws").build_command("hi"),
            AG.AntigravityCliBackend("agy", model="gemini-3.1-pro-high",
                                     workdir="C:/ws").build_command("hi"),
            GB.build_interactive_grok_command("grok", model="grok-4.5", workdir="C:/ws"),
            AG.build_interactive_antigravity_command("agy", model="gemini-3.1-pro-high",
                                                     workdir="C:/ws"),
        ):
            C.assert_no_forbidden_provider_args(argv)
            C.assert_no_untrusted_instruction_args(argv)


class TestExecutableResolution:
    """Which BINARY each provider resolves to — added at `.picker` review round 1.

    Nothing tested either resolver: pointing `detect.grok_executable` at Antigravity's candidate
    list, or `_resolve_frontier_executable`'s grok entry at `detect.claude_code_executable`, left
    all 1858 tests green (validator BLOCKING-4). The docstrings claimed protection the code did not
    have — "a provider added without a resolver raises a KeyError (loudly)" is true of a MISSING
    entry, never of a WRONG one, and a wrong one is precisely what operator directive §14 is about:
    a missing `agy` must not surface as a `claude` problem, and must never run a `claude` terminal.
    """

    @staticmethod
    def _queried(monkeypatch, resolver) -> list[str]:
        """The names a resolver actually asks the host about, in order (nothing is on PATH)."""
        from adapters import detect

        asked: list[str] = []

        def fake_which(name):
            asked.append(name)
            return None

        monkeypatch.setattr(detect.shutil, "which", fake_which)
        assert resolver() is None
        return asked

    def test_each_resolver_asks_for_ITS_OWN_backends_candidate_names(self, monkeypatch):
        from adapters import detect

        grok = self._queried(monkeypatch, detect.grok_executable)
        assert grok == list(GB.GrokCliBackend.executable_candidates)
        assert not any("agy" in n or "claude" in n or "codex" in n for n in grok)

        agy = self._queried(monkeypatch, detect.antigravity_executable)
        assert agy == list(AG.AntigravityCliBackend.executable_candidates)
        assert not any("grok" in n or "claude" in n or "codex" in n for n in agy)

    def test_a_resolver_returns_the_first_name_the_host_resolves(self, monkeypatch):
        """The shim case this exists for: a ConPTY spawn takes a FILE, so the gate must hand back the
        resolved path (`grok.CMD` on this host), not the bare name."""
        from adapters import detect

        monkeypatch.setattr(detect.shutil, "which",
                            lambda n: "C:/npm/grok.CMD" if n == "grok.cmd" else None)
        assert detect.grok_executable() == "C:/npm/grok.CMD"

    def test_every_frontier_pane_adapter_maps_to_its_own_resolver(self, monkeypatch):
        """The pane authorizer's dispatch table, checked by IDENTITY rather than by reading it: a
        provider whose entry points at another's resolver would spawn that other provider's binary
        under this provider's lease."""
        from adapters import detect
        from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
        from adapters.frontier.codex import CODEX_ADAPTER
        from node_runtime.supervisor import worker_pane_spawn as W

        expected = {
            CLAUDE_CODE_ADAPTER: detect.claude_code_executable,
            CODEX_ADAPTER: detect.codex_executable,
            GB.GROK_ADAPTER: detect.grok_executable,
            AG.ANTIGRAVITY_ADAPTER: detect.antigravity_executable,
        }
        # every adapter the authorizer will dispatch has an entry — and it is that adapter's own
        assert set(expected) == set(W.FRONTIER_PANE_ADAPTERS)
        for adapter_id, resolver in expected.items():
            called: list[str] = []
            monkeypatch.setattr(detect, resolver.__name__,
                                lambda _a=adapter_id: called.append(_a) or None)
            assert W._resolve_frontier_executable(adapter_id) is None
            assert called == [adapter_id], (
                f"{adapter_id} resolved through some other provider's resolver")

    def test_an_adapter_with_no_resolver_raises_rather_than_falling_through(self):
        from node_runtime.supervisor import worker_pane_spawn as W

        with pytest.raises(KeyError):
            W._resolve_frontier_executable("some_future_provider")


def test_a_zero_exit_that_produced_no_readable_stream_is_not_SUCCESS() -> None:
    """W-03 / A-2. `stdout=None` is the signature of a reader thread that DIED -- subprocess
    swallows the decode exception -- not of a command that chose to say nothing.

    Exit-code-first (operator directive §6) is NOT weakened here, and the second assertion is what
    pins that: this branch reads the ABSENCE of a stream, never the CONTENT of one. A command that
    legitimately printed nothing on a zero exit is still a SUCCESS, exactly as before.
    """
    res = C.classify_provider_outcome(0, None, "")
    assert res.outcome == C.OUTCOME_NO_OUTPUT
    assert res.ok is False
    assert res.exit_code == 0, "the honest exit code is still reported, not erased"
    assert C.classify_provider_outcome(0, "", "").outcome == C.OUTCOME_SUCCESS
    assert C.classify_provider_outcome(0, "hello", "").outcome == C.OUTCOME_SUCCESS
