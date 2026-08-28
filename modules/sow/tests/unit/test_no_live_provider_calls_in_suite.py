"""The suite-wide no-live-provider guard, tested at the seam it exists to defend (U163).

Measured on 2026-07-30: `pytest tests/` spent real `claude` subscription calls, because the
adapter's spawn had moved from `subprocess.run` (which three tests patched) to
`run_managed_process` (which nothing patched). The tests kept passing; one of them — the case whose
whole purpose is proving a `live` leg is unreachable in a mock-first suite — reported `live`.

These checks fail if the guard is deleted, weakened, or routed around.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from adapters.frontier.claude_code import ClaudeCliBackend  # noqa: E402
from tests.live_call_guard import billable_provider_call, LiveProviderCallInTests  # noqa: E402


def test_the_real_adapter_cannot_spawn_the_provider_cli_from_a_test() -> None:
    """The path the three drifted tests took, through the adapter's own `generate`."""
    backend = ClaudeCliBackend()
    with pytest.raises(LiveProviderCallInTests) as caught:
        backend.generate("this must never reach the operator's subscription", max_tokens=1)
    assert "run_managed_process" in str(caught.value)


def test_a_direct_subprocess_call_to_a_provider_cli_is_refused_too() -> None:
    for cmd in (["claude", "hello"], ["codex", "exec", "hello"],
                [r"C:\Program Files\nodejs\claude.cmd", "-p", "hi"]):
        with pytest.raises(LiveProviderCallInTests):
            subprocess.run(cmd, capture_output=True)
        with pytest.raises(LiveProviderCallInTests):
            subprocess.Popen(cmd)


def test_a_credential_free_metadata_probe_is_allowed_through(tmp_path: Path) -> None:
    """U165. The guard exists so a pytest run never SPENDS a subscription call — and
    `codex --version` / `login status` / `exec --help` spend nothing: they are exactly how
    `.detect` proves the CLI is present, and refusing them by name alone turned nine honest
    host-probe tests red. The binary here is provider-NAMED and deliberately absent, so the
    FileNotFoundError proves the guard handed the spawn on rather than refusing it — while
    still reaching no real CLI.
    """
    fake = tmp_path / "codex.exe"
    for args in (["--version"], ["login", "status"], ["exec", "--help"], ["--help"]):
        with pytest.raises(FileNotFoundError):
            subprocess.run([str(fake), *args], capture_output=True)


def test_a_metadata_form_carrying_anything_else_is_still_refused(tmp_path: Path) -> None:
    """The allowance is by WHOLE argv, not by prefix: a prompt smuggled after a benign
    subcommand is a model call, and a bare invocation (which opens the interactive session)
    is refused as well. Fail closed on anything not enumerated."""
    fake = tmp_path / "codex.exe"
    for args in (["exec", "--help", "and now actually do this"], ["exec", "hi"],
                 ["--version", "hi"], ["login"], []):
        with pytest.raises(LiveProviderCallInTests):
            subprocess.run([str(fake), *args], capture_output=True)


def test_ordinary_spawns_are_untouched() -> None:
    """The guard discriminates by provider name; it is not a blanket ban on child processes —
    several suites prove real behaviour by running node/python/powershell."""
    done = subprocess.run([sys.executable, "-c", "print('ok')"], capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout.strip() == "ok"


def test_the_managed_boundary_still_runs_a_non_provider_command() -> None:
    from adapters.frontier import process_tree

    done = process_tree.run_managed_process(
        [sys.executable, "-c", "print('managed')"], timeout=60.0, env=None,
        stdin=subprocess.DEVNULL)
    assert done.returncode == 0 and "managed" in done.stdout


# ---- W-21 / R-19: the guard classified by the FIRST token only ---------------------------------
# `live_provider_name` read `Path(cmd[0]).stem`, so every wrapper shape walked straight past it: the
# thing that actually executes `claude` is not always argv[0]. The review executed this table and
# every row was PERMITTED. The Windows-path row is the host-specific one -- `Path().stem` does not
# split on a backslash under POSIX, so a Windows-style path evades a POSIX-hosted guard while
# passing on this Windows host.
#
# Fail-closed is the guard's stated posture ("an argv shape nobody has established as free is
# treated as one that costs"), and it is the right posture for a guard whose failure mode is
# spending the operator's real subscription quota.

EVASIONS = [
    ("npx wrapper",            ["npx", "claude", "-p", "hi"]),
    ("cmd /c wrapper",         ["cmd", "/c", "claude", "-p", "hi"]),
    ("wsl wrapper",            ["wsl", "claude", "-p", "hi"]),
    ("powershell -Command",    ["powershell", "-Command", "claude -p hi"]),
    ("bash -lc",               ["bash", "-lc", "claude -p hi"]),
    ("string argv",            "claude -p hi"),
    ("windows path",           ["C:\\tools\\claude.exe", "-p", "hi"]),
    ("quoted windows path",    ['"C:\\tools\\claude.exe"', "-p", "hi"]),
    ("nested wrapper",         ["cmd", "/c", "npx", "codex", "exec", "hi"]),
    ("grok behind a wrapper",  ["bash", "-lc", "grok -p hi"]),
    ("agy behind a wrapper",   ["wsl", "agy", "-p", "hi"]),
]


@pytest.mark.parametrize("label,cmd", EVASIONS, ids=[e[0] for e in EVASIONS])
def test_no_wrapper_shape_hides_a_billable_provider_call(label: str, cmd) -> None:
    """W-21 NEGATIVE. Each of these was PERMITTED before the repair."""
    assert billable_provider_call(cmd) is not None, (
        f"{label}: {cmd!r} would spend a subscription call and the guard permitted it")


def test_ordinary_wrapped_spawns_are_still_untouched() -> None:
    """POSITIVE. Broadening the scan must not refuse the ordinary spawns several tests rely on --
    a guard that refuses everything is not a guard, it is an outage."""
    for cmd in (
        ["node", "-e", "console.log(1)"],
        ["cmd", "/c", "echo", "hi"],
        ["bash", "-lc", "echo hi"],
        ["powershell", "-NoProfile", "-Command", "Write-Output 1"],
        ["wsl", "echo", "hi"],
        [sys.executable, "-c", "pass"],
        "echo hi",
    ):
        assert billable_provider_call(cmd) is None, f"{cmd!r} was refused but spends nothing"


def test_a_credential_free_probe_survives_the_broadened_scan(tmp_path: Path) -> None:
    """POSITIVE. The U165 allowance is why nine honest host-probe tests exist; a direct metadata
    call must stay free."""
    for cmd in (["codex", "--version"], ["claude", "--help"], ["codex", "login", "status"],
                ["codex", "exec", "--help"]):
        assert billable_provider_call(cmd) is None, f"{cmd!r} is credential-free and must pass"


def test_a_provider_NAME_used_as_an_argument_VALUE_is_not_a_spawn() -> None:
    """REGRESSION. The first cut of the broadened scan looked at every token and refused

        powershell -NoProfile -NonInteractive -Command
          "... & 'run_frontier_providers.ps1' -Provider grok -Action uninstall ..."

    because `grok` appears as the VALUE of `-Provider`. That is data, not a command, and refusing
    it broke a real PowerShell-syntax test — caught only by the FULL suite, not by the spawn-heavy
    subset the unit checked. A guard that refuses argument values is an outage, so the scan now
    looks at EXECUTABLE POSITIONS: argv[0], a token after a non-flag, a token after a
    command-introducing flag, or a token after PowerShell's `&` call operator.
    """
    ps1 = ("$ErrorActionPreference='Stop'; try { & "
           "'D:\\repo\\tools\\providers\\run_frontier_providers.ps1' "
           "-Provider grok -Action uninstall | Out-Null; exit 0 } catch { exit 77 }")
    assert billable_provider_call(
        ["powershell.EXE", "-NoProfile", "-NonInteractive", "-Command", ps1]) is None

    for cmd in (
        ["node", "cli.js", "--provider", "claude", "--dry-run"],
        ["py", "-3.12", "tool.py", "--adapter", "codex"],
        ["pwsh", "-File", "x.ps1", "-Provider", "agy"],
    ):
        assert billable_provider_call(cmd) is None, (
            f"{cmd!r} names a provider as an argument value; it does not run one")


def test_a_wrapped_metadata_probe_is_refused_because_the_allowance_is_drawn_tight() -> None:
    """The deliberate cost of fail-closed, asserted rather than discovered later: the allowlist is
    matched against a DIRECT argv, so a wrapped `--version` is refused. That is the safe direction
    -- the guard cannot tell which token the wrapper will actually execute."""
    assert billable_provider_call(["npx", "claude", "--version"]) is not None
