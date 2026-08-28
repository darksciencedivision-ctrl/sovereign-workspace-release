"""The voice-turn hook must be RUNNABLE by the vendor CLI's own hook dispatcher (U162).

Iteration 92's exact-source live receipt (PHASE17C_CLOSE_SELFCHECK, 2026-07-30) reached the live
conductor and then failed four containment legs with the pane showing::

    UserPromptSubmit hook error
    Failed with non-blocking status code: At line:1 char:36

`char:36` is exactly one past ``"<node.exe>" `` — PowerShell's parser, refusing a command line whose
FIRST token is a quoted string (it reads it as an expression, and the second string is then an
unexpected token). The pinned `hook_command` was `subprocess.list2cmdline([node, hook])`, which is
correct CreateProcess quoting and INVALID PowerShell. So no hook ran: no turn was armed, the model's
tool call was never denied by the supervisor, and the vendor's own approval prompt caught it instead.

The lesson is not "quote differently" — it is that a hook whose command string the dispatcher cannot
parse FAILS OPEN for tool denial while every unit test that checks the string still passes. These
tests therefore execute the emitted command through the real dispatcher, and require the profile to
refuse to build when that execution cannot be proved.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from node_runtime.supervisor.conductor_permission_profile import (  # noqa: E402
    HOOK_PATH,
    PermissionProfileUnavailable,
    build_conductor_permission_profile,
)

WINDOWS = os.name == "nt"
POWERSHELL = shutil.which("powershell.exe") or shutil.which("powershell")
PRETOOLUSE = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash"})


def _dispatch(command: str) -> subprocess.CompletedProcess[str]:
    """Run a hook command the way the vendor dispatcher does on this host."""
    if WINDOWS:
        argv = [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command]
    else:
        argv = [shutil.which("sh") or "/bin/sh", "-c", command]
    return subprocess.run(argv, input=PRETOOLUSE, capture_output=True, text=True, timeout=60)


requires_dispatcher = pytest.mark.skipif(
    WINDOWS and not POWERSHELL, reason="no PowerShell on this host to dispatch a hook through"
)


@requires_dispatcher
def test_the_pinned_hook_command_actually_runs_under_the_host_dispatcher() -> None:
    """The command the ticket pins must produce a fail-closed DENY, not a parser error."""
    profile = build_conductor_permission_profile("pp-dispatch-test")
    command = profile.boundary["hook_command"]

    done = _dispatch(command)

    assert done.returncode == 0, f"dispatcher could not run the pinned hook: {done.stderr[:400]}"
    decision = json.loads(done.stdout)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    # No supervisor is listening for this probe, so the ONLY honest answer is deny.
    assert decision["permissionDecision"] == "deny"


@pytest.mark.skipif(not WINDOWS or not POWERSHELL, reason="the defect is Windows-dispatcher specific")
def test_the_shipped_regression_form_is_still_rejected_by_the_dispatcher() -> None:
    """Pins the defect itself, so the check above cannot pass vacuously.

    This is the exact string iteration 92 shipped; if PowerShell ever started accepting it the test
    above would stop being evidence of anything.
    """
    node = shutil.which("node")
    assert node, "Node.js is required for this build"
    bare = subprocess.list2cmdline([str(Path(node).resolve()), str(HOOK_PATH.resolve())])
    assert not bare.startswith("&")

    done = _dispatch(bare)

    assert done.returncode != 0
    assert "UnexpectedToken" in done.stderr or "Unexpected token" in done.stderr
    assert done.stdout.strip() == "", "a command that never parsed cannot have decided anything"


@requires_dispatcher
def test_the_boundary_records_the_dispatch_shell_and_its_verification() -> None:
    profile = build_conductor_permission_profile("pp-dispatch-test")
    boundary = profile.boundary

    assert boundary["hook_command_shell"] == ("powershell" if WINDOWS else "sh")
    assert boundary["hook_command_verified"] is True
    probe = boundary["hook_command_probe"]
    assert probe["shell"] == boundary["hook_command_shell"]
    assert probe["exit_code"] == 0
    assert probe["decision"] == "deny"
    # the argv vector stays the authority; the command string is a dispatcher-specific rendering of it
    assert boundary["hook_argv"] == [boundary["hook_runtime"], str(HOOK_PATH.resolve())]
    if WINDOWS:
        assert boundary["hook_command"].startswith("& ")


def test_a_command_the_dispatcher_cannot_run_refuses_the_whole_profile() -> None:
    """Fail closed: no settings JSON, therefore no launch, when the hook cannot be proved runnable."""

    def broken(command: str, *, shell: str) -> dict[str, object]:
        raise PermissionProfileUnavailable("dispatcher rejected the pinned hook command")

    with pytest.raises(PermissionProfileUnavailable):
        build_conductor_permission_profile("pp-dispatch-test", verifier=broken)


def test_a_verifier_that_reports_anything_but_a_deny_is_refused() -> None:
    """An 'allow' from an unsupervised probe means the hook is not fail-closed — refuse the launch."""

    def allowing(command: str, *, shell: str) -> dict[str, object]:
        return {"shell": shell, "exit_code": 0, "decision": "allow"}

    with pytest.raises(PermissionProfileUnavailable):
        build_conductor_permission_profile("pp-dispatch-test", verifier=allowing)
