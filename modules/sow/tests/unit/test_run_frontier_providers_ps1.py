"""Phase 18A — deterministic tests for the PowerShell provider runner.

Operator directive §16 asks for "PowerShell parameter validation; PowerShell syntax parsing" as
first-class tests. Both run here: the syntax test parses the script with PowerShell's own AST
parser (skipped, not faked, where no PowerShell exists), and the prohibition tests read the source
for the things the runner must never do (§3): mutate git, touch LOOP_STATE.json, start the
autonomous loop, read credentials, or install/authenticate as a side effect of `status`.

No network and no provider process: nothing here executes the runner's actions. The host-coupled
end-to-end run is opt-in via SOW_PROVIDER_HOST_CHECK=1 so the default suite stays hermetic.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "tools" / "providers" / "run_frontier_providers.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")

needs_powershell = pytest.mark.skipif(POWERSHELL is None,
                                      reason="no PowerShell interpreter on this host")


def run_powershell(script: str, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=timeout, check=False,
                          stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def source() -> str:
    return RUNNER.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code_only(source: str) -> str:
    """The runner with comments removed — block comments (`<# … #>`) and line comments.

    The prohibition tests below assert the ABSENCE of certain acts. Scanning the raw file would
    make the script's own promise not to touch `LOOP_STATE.json` read as a violation, so the
    scan runs over executable text only. (A `#` inside a string literal would be over-stripped;
    this runner has none, and over-stripping can only make these tests stricter, never laxer.)"""
    import re
    stripped = re.sub(r"<#.*?#>", "", source, flags=re.S)
    return "\n".join(line.split("#", 1)[0] for line in stripped.splitlines())


class TestRunnerExists:
    def test_runner_is_where_the_operator_directive_says_it_is(self):
        assert RUNNER.is_file(), f"expected the runner at {RUNNER}"


class TestPowerShellSyntax:
    @needs_powershell
    def test_script_parses_with_zero_errors(self):
        """PowerShell's own parser is the authority on whether this script is loadable."""
        script = (
            "$errors = $null; $tokens = $null; "
            f"$null = [System.Management.Automation.Language.Parser]::ParseFile('{RUNNER}', "
            "[ref]$tokens, [ref]$errors); "
            "if ($errors) { $errors | ForEach-Object { $_.Message }; exit 1 } else { exit 0 }"
        )
        proc = run_powershell(script)
        assert proc.returncode == 0, f"parse errors:\n{proc.stdout}\n{proc.stderr}"

    @needs_powershell
    def test_parameters_and_validate_sets_are_declared_as_specified(self):
        """§3: the exact parameter surface, with closed value sets on Provider and Action."""
        script = (
            "$errors = $null; $tokens = $null; "
            f"$ast = [System.Management.Automation.Language.Parser]::ParseFile('{RUNNER}', "
            "[ref]$tokens, [ref]$errors); "
            "$p = $ast.ParamBlock.Parameters | ForEach-Object { "
            "  $name = $_.Name.VariablePath.UserPath; "
            "  $vs = @($_.Attributes | Where-Object { $_.TypeName.Name -eq 'ValidateSet' } | "
            "    ForEach-Object { $_.PositionalArguments | ForEach-Object { $_.Value } }); "
            "  [pscustomobject]@{ name = $name; "
            "    type = $(if ($_.StaticType) { $_.StaticType.Name } else { '' }); "
            "    validateSet = $vs } }; "
            "$p | ConvertTo-Json -Depth 5 -Compress"
        )
        proc = run_powershell(script)
        assert proc.returncode == 0, proc.stderr
        params = json.loads(proc.stdout.strip())
        by_name = {p["name"]: p for p in params}
        assert set(by_name) == {"Provider", "Action", "RepoRoot", "Model", "Prompt",
                                "InstallMissing", "NoLaunch"}, by_name.keys()
        assert set(by_name["Provider"]["validateSet"]) == {"all", "grok", "gemini"}
        assert set(by_name["Action"]["validateSet"]) == {"status", "install", "login", "probe",
                                                         "launch"}
        assert by_name["InstallMissing"]["type"] == "SwitchParameter"
        assert by_name["NoLaunch"]["type"] == "SwitchParameter"

    @needs_powershell
    @pytest.mark.parametrize("bad_args", ["-Provider openai -Action status",
                                          "-Provider grok -Action uninstall"])
    def test_out_of_set_arguments_are_rejected_before_anything_runs(self, bad_args):
        """Parameter binding fails before the script body executes, so no provider call, install,
        or launch can happen on a mistyped invocation."""
        # 77 is this test's own sentinel, deliberately outside the runner's documented table (which
        # now uses 7 for an unverifiable install) so a pass cannot be produced by the runner.
        proc = run_powershell(
            "$ErrorActionPreference='Stop'; "
            f"try {{ & '{RUNNER}' {bad_args} | Out-Null; exit 0 }} catch {{ exit 77 }}")
        assert proc.returncode == 77, proc.stdout + proc.stderr


class TestRunnerProhibitions:
    """Static reading of the source for the acts §3 forbids. A grep is a blunt instrument, but it
    is the right one here: these are *absence* requirements, and absence is what a reader of the
    file must be able to confirm."""

    @pytest.mark.parametrize("forbidden", [
        "git commit", "git add", "git push", "git checkout", "git reset", "git tag",
        "LOOP_STATE", "run_loop.ps1",
    ])
    def test_the_runner_never_touches_git_or_the_loop(self, code_only, forbidden):
        assert forbidden not in code_only, f"runner must not perform {forbidden!r} (directive §3)"

    @pytest.mark.parametrize("forbidden", [
        "XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
        "Get-StoredCredential", "CredentialManager", "auth.json", "credentials.json",
        "cookies.sqlite",
    ])
    def test_the_runner_never_reads_a_credential(self, code_only, forbidden):
        assert forbidden not in code_only, f"runner must not reference {forbidden!r} (directive §13)"

    def test_no_file_read_targets_credential_material(self, code_only):
        """`Get-Content.*token` used to sit in the list above, where a literal `in` check made it
        unfalsifiable — it is a regex, and the list is matched as substrings (round-3 spec-audit
        MINOR-14). The runner DOES use Get-Content (for its own temp report), so the real
        question is what it reads, and that needs an actual regex."""
        import re
        hits = re.findall(r"Get-Content[^\r\n]*", code_only)
        for hit in hits:
            assert not re.search(r"token|credential|secret|auth\.json|cookies|\.netrc", hit,
                                 re.I), f"a file read targets credential material: {hit!r}"

    def test_installation_is_gated_behind_the_explicit_switch(self, source):
        assert "-InstallMissing was not supplied" in source
        assert "$EXIT_INSTALL_NOT_AUTHORIZED" in source
        # the two vendor install commands exist exactly once each, inside the install action
        assert source.count("npm install -g") == 1
        assert source.count("antigravity.google/cli/install.ps1") == 1

    def test_status_action_cannot_install_or_authenticate(self, source):
        """The status path must not be able to reach the install or login functions."""
        start = source.index("function Invoke-StatusAction")
        end = source.index("function Invoke-InstallAction")
        status_body = source[start:end]
        for forbidden in ("Invoke-InstallAction", "Invoke-LoginAction", "npm install",
                          "Invoke-RestMethod", "login"):
            assert forbidden not in status_body, forbidden

    def test_distinct_exit_codes_are_defined_for_each_refusal(self, source):
        for name in ("$EXIT_OK", "$EXIT_INSTALL_NOT_AUTHORIZED", "$EXIT_PROBE_REFUSED",
                     "$EXIT_PATH_REFRESH_REQUIRED", "$EXIT_PROVIDER_UNAVAILABLE",
                     "$EXIT_ENVIRONMENT", "$EXIT_INSTALL_UNVERIFIED"):
            assert name in source

    def test_path_refresh_after_install_has_its_own_exit_code(self, source):
        """§4.2 — if PATH changes need a new terminal, say so and stop with a distinct code."""
        assert "$EXIT_PATH_REFRESH_REQUIRED" in source
        assert "NEW terminal" in source

    def test_executable_is_resolved_by_discovery_not_hardcoded(self, source):
        assert "Get-Command" in source
        for hardcoded in ("AppData\\Roaming\\npm\\grok", "AppData\\Local\\agy"):
            assert hardcoded not in source

    def test_launch_uses_the_existing_desktop_launcher(self, source):
        """§15 — do not invent a new desktop launch command."""
        assert "apps\\desktop" in source
        assert "npm start" in source

    def test_only_non_secret_command_hints_are_exported(self, source):
        assert "SOVEREIGN_GROK_COMMAND" in source
        assert "SOVEREIGN_ANTIGRAVITY_COMMAND" in source
        assert "$env:SOVEREIGN_GROK_TOKEN" not in source

    def test_classification_logic_is_not_duplicated_in_powershell(self, source):
        """Status semantics live in ONE place (the tested Python engine); a second copy in
        PowerShell could drift and re-introduce transcript-keyword classification."""
        assert "frontier_provider_recon.py" in source
        for keyword_classifier in ("-match 'not logged in'", "-match 'quota'", "-match 'rate limit'"):
            assert keyword_classifier not in source


class TestExitCodeContract:
    """The runner's exit codes are its machine-readable surface, and both of the mechanisms that
    were supposed to deliver them were broken in the first implementation (spec-audit F-6)."""

    def test_actions_report_through_the_script_scoped_variable(self, code_only):
        """F-6b: a native command's stdout joins the caller's output stream, so `exit (Invoke-X)`
        received an array on exactly the paths where a command had run."""
        assert "$script:ActionExit" in code_only
        assert "exit $script:ActionExit" in code_only
        assert "exit (Invoke-" not in code_only

    def test_interactive_flows_are_not_piped(self, code_only):
        """N-14: piping a full-screen TUI's stdout typically breaks its rendering, and the
        Antigravity sign-in is only a TUI. Safe to leave unpiped precisely because the exit code
        no longer travels through the pipeline."""
        assert "& $entry.executable login\n" in code_only or \
               "& $entry.executable login\r\n" in code_only
        assert "| Out-Host" not in code_only

    def test_the_action_dispatch_does_not_swallow_native_output(self, code_only):
        """...which only works if main does not pipe the action functions to Out-Null either."""
        import re
        for m in re.finditer(r"Invoke-\w+Action[^\r\n]*\| Out-Null", code_only):
            raise AssertionError(f"action output swallowed: {m.group(0)}")

    def test_a_failed_install_is_not_reported_as_a_successful_one(self, code_only):
        """N-7b: without an exit-code check, a failed install fell through to the PATH branch and
        told the operator it had installed and needed a new terminal."""
        assert "$installExit = $LASTEXITCODE" in code_only
        assert "install command FAILED" in code_only

    def test_the_status_surface_prints_the_caveat_and_the_auth_fact(self, code_only):
        """The engine's honesty fields are worthless if the operator's surface drops them
        (validator F4: deleting either print left the suite green)."""
        assert "$Entry.state_caveat" in code_only
        assert "$Entry.auth_confirmed" in code_only
        assert "$p.auth_confirmed" in code_only        # and in the capability table

    def test_environment_failures_do_not_use_terminating_write_error(self, code_only):
        """F-6a: Write-Error terminates under $ErrorActionPreference='Stop', so the documented
        `exit 6` never ran and callers saw exit 1."""
        assert "Write-Error" not in code_only
        assert "function Write-Failure" in code_only

    @needs_powershell
    def test_a_bad_repo_root_exits_with_the_documented_environment_code(self, tmp_path):
        """End-to-end proof of F-6a: this path used to report 1."""
        proc = run_powershell(
            f"& '{RUNNER}' -Action status -RepoRoot '{tmp_path}'; exit $LASTEXITCODE")
        assert proc.returncode == 6, proc.stdout + proc.stderr

    @needs_powershell
    def test_a_refused_probe_exits_three_and_spends_nothing(self, tmp_path):
        """Runs the whole runner->engine->gate path without contacting a provider.

        The live-operation config is pinned to a FIXTURE that authorizes only claude_code. An
        earlier version read the host's real (gitignored) switch, which is denied today but which
        the operator is expected to extend at 18C — at which point a plain `pytest tests/` on this
        host would have spawned a real provider CLI and spent a live subscription call
        (gate-validator F6). A test that becomes a live-spend the day the operator acts on a
        documented entry condition is not hermetic; this one cannot become that."""
        cfg = tmp_path / "live_operation.json"
        cfg.write_text(json.dumps({
            "config_version": "1.1", "live_operation_authorized": True, "register_row": "OP-6",
            "scope": {"providers": ["claude_code"], "terminals_per_subscription": 2},
        }), encoding="utf-8")
        script = (f"$env:SOVEREIGN_LIVE_OPERATION_CONFIG='{cfg.as_posix()}'; "
                  f"& '{RUNNER}' -Action probe; exit $LASTEXITCODE")
        proc = run_powershell(script, timeout=180)
        assert proc.returncode == 3, proc.stdout + proc.stderr
        assert "executed   : False" in proc.stdout
        assert "spending anything" in proc.stdout

    @needs_powershell
    def test_an_engine_crash_is_not_reported_as_a_governed_refusal(self, tmp_path):
        """F-16 with teeth: a stub engine that exits 5 must produce exit 6 (tool failure), never
        exit 3 (the fail-closed denial). Collapsing that branch used to leave the suite green."""
        (tmp_path / "AUTONOMOUS_BUILD_DIRECTIVE.md").write_text("stub", encoding="utf-8")
        engine = tmp_path / "tools" / "providers" / "frontier_provider_recon.py"
        engine.parent.mkdir(parents=True)
        engine.write_text(
            "import json, sys\n"
            "i = sys.argv.index('--emit')\n"
            "open(sys.argv[i + 1], 'w', encoding='utf-8').write(json.dumps({'probes': []}))\n"
            "raise SystemExit(5)\n", encoding="utf-8")
        proc = run_powershell(
            f"& '{RUNNER}' -Action probe -RepoRoot '{tmp_path}'; exit $LASTEXITCODE", timeout=180)
        assert proc.returncode == 6, proc.stdout + proc.stderr
        assert "not a governed refusal" in (proc.stdout + proc.stderr)

    @needs_powershell
    def test_the_governed_record_reaches_the_operators_screen(self, tmp_path):
        """Operator directive §17 requires the live receipt to confirm the lease returned to zero.
        Through 18C's first cut the engine MEASURED all of this and the runner printed none of it:
        stdout went to `Out-Null`, the report temp file was deleted in the `finally`, and
        `Invoke-ProbeAction` printed five fields — while the script's own header promised "holds
        ONE I-X3 lease ... releases the lease on every exit path". A promise the operator's surface
        cannot check is not observable (invariant 27). Stub engine: no provider is contacted."""
        (tmp_path / "AUTONOMOUS_BUILD_DIRECTIVE.md").write_text("stub", encoding="utf-8")
        engine = tmp_path / "tools" / "providers" / "frontier_provider_recon.py"
        engine.parent.mkdir(parents=True)
        report = {"probes": [{
            "provider": "grok_build", "display": "Grok Build", "executed": True, "accepted": True,
            "reason": "accepted", "gate": {"allowed": True, "reason": "in scope"},
            "supervised_execution": True,
            "governed": {
                "subscription_ref": "grok_build_subscription", "allowance": 1, "in_use": 1,
                "lease_id": "lease-abc123", "lease_key": "probe-grok#s1", "node_registered": False,
                "spawned_pids": [4242],
                "teardown": {"lease_released": True, "governor_released": True, "in_use_after": 0,
                             "process_tree_clean": True, "measured": True},
            }}]}
        engine.write_text(
            "import json, sys\n"
            "i = sys.argv.index('--emit')\n"
            f"open(sys.argv[i + 1], 'w', encoding='utf-8').write(json.dumps({report!r}))\n",
            encoding="utf-8")
        proc = run_powershell(
            f"& '{RUNNER}' -Action probe -RepoRoot '{tmp_path}'; exit $LASTEXITCODE", timeout=180)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert "grok_build_subscription" in out and "allowance 1" in out
        assert "lease-abc123" in out and "probe-grok#s1" in out
        assert "node_registered=False" in out
        assert "in_use_after=0" in out and "process_tree_clean=True" in out
        assert "measured=True" in out

    @needs_powershell
    def test_a_probe_that_opened_no_session_says_so_rather_than_printing_nothing(self, tmp_path):
        """A refusal before the session is the case where the ABSENCE of a lease is the fact worth
        seeing. Under `Set-StrictMode -Version Latest` a missing `governed` property is an error,
        so this also pins that the runner handles the refusal shape the engine really emits."""
        (tmp_path / "AUTONOMOUS_BUILD_DIRECTIVE.md").write_text("stub", encoding="utf-8")
        engine = tmp_path / "tools" / "providers" / "frontier_provider_recon.py"
        engine.parent.mkdir(parents=True)
        report = {"probes": [{
            "provider": "google_antigravity", "display": "Gemini · Antigravity",
            "executed": False, "accepted": False, "reason": "refused before any lease",
            "gate": {"allowed": True, "reason": "in scope"},
            "refused_by": "ProfileViolation"}]}
        engine.write_text(
            "import json, sys\n"
            "i = sys.argv.index('--emit')\n"
            f"open(sys.argv[i + 1], 'w', encoding='utf-8').write(json.dumps({report!r}))\n",
            encoding="utf-8")
        proc = run_powershell(
            f"& '{RUNNER}' -Action probe -RepoRoot '{tmp_path}'; exit $LASTEXITCODE", timeout=180)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert "refused before any lease was taken" in out


def _stub_entry(**overrides) -> dict:
    """A complete provider entry as the engine emits one.

    Complete because the runner reads it under `Set-StrictMode -Version Latest`, where a missing
    property is an error — a half-built fixture would fail for the wrong reason and prove nothing.
    """
    entry = {
        "provider": "grok_build", "display": "Grok Build", "command": "grok",
        "command_found": False, "executable": None, "version": None,
        "state": "NOT_INSTALLED", "state_caveat": None,
        "auth_confirmed": False, "auth_state": "UNVERIFIED", "auth_detail": "stub",
        "models": [], "default_model": None,
        "headless_supported": True, "interactive_supported": True,
        "structured_output_supported": True,
        "subscription_resource": "grok_build_subscription", "terminal_allowance": 1,
        "lease_state": "none", "registration_state": "NOT_REGISTERED",
        "registration_detail": "stub", "install_command": "npm install -g @xai-official/grok",
    }
    entry.update(overrides)
    return entry


def _stub_engine(tmp_path: Path, providers: list[dict]) -> None:
    """Plant a stub recon engine under a stub repo root.

    The runner resolves its engine from `-RepoRoot`, so this drives the PowerShell paths that
    matter WITHOUT a provider CLI, a network call, or the real host state."""
    (tmp_path / "AUTONOMOUS_BUILD_DIRECTIVE.md").write_text("stub", encoding="utf-8")
    engine = tmp_path / "tools" / "providers" / "frontier_provider_recon.py"
    engine.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"providers": providers})
    assert "'''" not in payload
    engine.write_text(
        "import json, sys\n"
        "i = sys.argv.index('--emit')\n"
        # the report travels as JSON text, not as a Python literal: `true`/`null` are not Python
        f"report = json.loads(r'''{payload}''')\n"
        "open(sys.argv[i + 1], 'w', encoding='utf-8').write(json.dumps(report))\n",
        encoding="utf-8")


class TestInstallActionBehaviour:
    """The install path, EXERCISED — not grepped.

    Round 3 of review neutered every install assertion this file had by deleting the guards and
    leaving the string literals the tests searched for: the whole failed-install guard could go
    with 40 tests still green, and `if (-not $Authorized)` could be turned into `if ($false)` with
    all 184 green (gate-validator M-2). Absence tests are the right shape for "never touches git";
    they are the wrong shape for "this branch cannot be reached", which is a behaviour.

    Nothing here installs anything: `npm` and `Invoke-RestMethod` are shadowed by functions in the
    calling scope, which PowerShell resolves before any external command, so the vendor commands
    are named and never run."""

    @needs_powershell
    def test_install_without_the_switch_installs_nothing(self, tmp_path):
        """§3's single most important prohibition: no install without an explicit -InstallMissing."""
        _stub_engine(tmp_path, [_stub_entry()])
        marker = tmp_path / "npm_was_invoked.txt"
        proc = run_powershell(
            f"function npm {{ 'invoked' | Out-File -FilePath '{marker.as_posix()}' }}; "
            f"& '{RUNNER}' -Action install -RepoRoot '{tmp_path}'; exit $LASTEXITCODE", timeout=180)
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert not marker.exists(), "npm was invoked without -InstallMissing"
        assert "-InstallMissing was not supplied" in proc.stdout

    @needs_powershell
    def test_a_failed_npm_install_is_not_reported_as_one_needing_a_new_terminal(self, tmp_path):
        """N-7b with teeth. A failing install must exit 5 and say so — never fall through to the
        PATH-refresh branch, which asserts an install that did not happen and returns 4."""
        _stub_entry_absent = _stub_entry(command="sow-nonexistent-grok")
        _stub_engine(tmp_path, [_stub_entry_absent])
        proc = run_powershell(
            "function npm { Write-Host 'stub npm: failing'; $global:LASTEXITCODE = 1 }; "
            f"& '{RUNNER}' -Action install -InstallMissing -RepoRoot '{tmp_path}'; "
            "exit $LASTEXITCODE", timeout=180)
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 5, combined
        assert "install command FAILED" in combined
        assert "NEW terminal" not in combined, "a failed install claimed a successful one"

    @needs_powershell
    def test_a_throwing_vendor_installer_exits_5_and_not_the_undocumented_1(self, tmp_path):
        """The Antigravity path fetches and executes remote code. If that fetch or that script
        throws, it is an install failure with a documented code — untrapped it was a terminating
        error under -Stop and exited 1, which the exit-code table does not carry (A-9)."""
        _stub_engine(tmp_path, [_stub_entry(provider="google_antigravity", display="Gemini",
                                            command="sow-nonexistent-agy",
                                            subscription_resource="google_antigravity_subscription",
                                            install_command="(vendor installer)")])
        proc = run_powershell(
            "function Invoke-RestMethod { throw 'stub: the fetch failed' }; "
            f"& '{RUNNER}' -Action install -InstallMissing -RepoRoot '{tmp_path}'; "
            "exit $LASTEXITCODE", timeout=180)
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 5, combined
        assert "install command FAILED" in combined
        assert "NEW terminal" not in combined

    @needs_powershell
    def test_a_silent_vendor_installer_is_reported_as_unverifiable_not_as_installed(self, tmp_path):
        """The defect round 3 found: `Invoke-Expression` of a PowerShell installer does not set
        `$LASTEXITCODE`, so the check read a STALE 0 and a silent failure was announced as an
        install needing a new terminal (exit 4). It must now say it cannot tell, under exit 7."""
        _stub_engine(tmp_path, [_stub_entry(provider="google_antigravity", display="Gemini",
                                            command="sow-nonexistent-agy",
                                            subscription_resource="google_antigravity_subscription",
                                            install_command="(vendor installer)")])
        proc = run_powershell(
            "function Invoke-RestMethod { 'Write-Host \"stub installer: did nothing\"' }; "
            f"& '{RUNNER}' -Action install -InstallMissing -RepoRoot '{tmp_path}'; "
            "exit $LASTEXITCODE", timeout=180)
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 7, combined
        assert "CANNOT distinguish" in combined
        assert "installed, but" not in combined

    @needs_powershell
    def test_an_already_installed_provider_is_a_no_op(self, tmp_path):
        """Repeat-safety (§3): running install twice installs nothing the second time."""
        _stub_engine(tmp_path, [_stub_entry(command_found=True, executable="C:/stub/grok.exe",
                                            state="AVAILABLE")])
        marker = tmp_path / "npm_was_invoked.txt"
        proc = run_powershell(
            f"function npm {{ 'invoked' | Out-File -FilePath '{marker.as_posix()}' }}; "
            f"& '{RUNNER}' -Action install -InstallMissing -RepoRoot '{tmp_path}'; "
            "exit $LASTEXITCODE", timeout=180)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert not marker.exists()
        assert "nothing to do (repeat-safe)" in proc.stdout


class TestStatusHonesty:
    @needs_powershell
    @pytest.mark.parametrize("confirmed, must_say, must_not_say", [
        (False, "NOTHING reported a signed-in session",
         "the CLI itself reported a signed-in session"),
        (True, "the CLI itself reported a signed-in session",
         "NOTHING reported a signed-in session"),
    ])
    def test_the_auth_gloss_follows_the_value(self, tmp_path, confirmed, must_say, must_not_say):
        """Round-3 spec-audit MAJOR-1. The parenthetical was printed unconditionally, so
        `auth confirmed : False  (the CLI itself reported a signed-in session ...)` went out on the
        operator's primary surface — and into a committed receipt — for the one provider whose auth
        is unverifiable offline. A gloss that cannot disagree with its value is not a disclosure."""
        _stub_engine(tmp_path, [_stub_entry(auth_confirmed=confirmed)])
        proc = run_powershell(
            f"& '{RUNNER}' -Action status -RepoRoot '{tmp_path}'; exit $LASTEXITCODE", timeout=180)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert must_say in proc.stdout, proc.stdout
        assert must_not_say not in proc.stdout, proc.stdout


class TestLaunchCarriage:
    @needs_powershell
    def test_a_non_available_provider_carries_no_command_hint(self, tmp_path):
        """§15 — hints are exported for AVAILABLE providers only. Untested, the filter could be
        deleted and a stale path exported for a provider the shell must not offer (A-8). The
        fixture is a realistic non-AVAILABLE state that still HAS a resolved executable, because
        with a null path the export is indistinguishable from no export at all."""
        _stub_engine(tmp_path, [_stub_entry(command_found=True, executable="C:/stub/grok.exe",
                                            version="0.0.1", state="UNSUPPORTED_VERSION",
                                            auth_detail="version below the floor")])
        proc = run_powershell(
            "$env:SOVEREIGN_GROK_COMMAND = $null; "
            f"& '{RUNNER}' -Action launch -NoLaunch -RepoRoot '{tmp_path}' | Out-Null; "
            "Write-Host ('HINT=[' + $env:SOVEREIGN_GROK_COMMAND + ']')", timeout=180)
        assert "HINT=[]" in proc.stdout, proc.stdout + proc.stderr


class TestHostCoupledRun:
    """Opt-in only (SOW_PROVIDER_HOST_CHECK=1): actually runs `-Action status` against this host.
    Excluded from the default suite because a provider's `models` command may reach the network
    (§16: no network-dependent test in the deterministic suite)."""

    @needs_powershell
    @pytest.mark.skipif(os.environ.get("SOW_PROVIDER_HOST_CHECK") != "1",
                        reason="host-coupled; set SOW_PROVIDER_HOST_CHECK=1 to run")
    def test_status_runs_and_reports_both_providers(self):
        proc = run_powershell(f"& '{RUNNER}' -Action status; exit $LASTEXITCODE", timeout=300)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "grok_build" in proc.stdout
        assert "google_antigravity" in proc.stdout
