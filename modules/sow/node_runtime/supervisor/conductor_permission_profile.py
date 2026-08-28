"""Applied transport profile for the attended conductor's direct voice turns.

The conductor remains fully attended for physical typing. The launch-ticket-pinned hook forwards
events to the Electron main supervisor process, which owns exact-turn admission and the deny-all
decision. Vendor chrome and hook-local state are never authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = ROOT / "tools" / "live" / "voice_turn_boundary.js"
BOUNDARY_SCHEMA = "voice_turn_boundary@1.0"
PROMPT_MARKER_FORMAT = "[[SOVEREIGN_VOICE_CHAT_V2:{turn_id_hex32}]] "
# The vendor CLI dispatches a hook `command` through the host's shell — PowerShell on Windows, as its
# own parser error proved (U162). PowerShell reads a command line whose FIRST token is quoted as an
# EXPRESSION, so `"<node.exe>" "<hook.js>"` is a parse error, not a command; the call operator is what
# makes a quoted executable path executable there.
POWERSHELL_CALL_OPERATOR = "& "
VERIFY_TIMEOUT_S = 60.0
# A PreToolUse probe with no supervisor listening: the only correct answer is deny.
_PROBE_EVENT = {"hook_event_name": "PreToolUse", "tool_name": "SovereignHookDispatchProbe"}


class PermissionProfileUnavailable(RuntimeError):
    """The profile cannot be applied; a live session must not launch without it."""


@dataclass(frozen=True)
class AppliedConductorPermissionProfile:
    settings_json: str
    boundary: dict[str, Any]


def _hook(command: str) -> dict[str, Any]:
    return {"hooks": [{"type": "command", "command": command}]}


def dispatch_shell(windows: bool | None = None) -> str:
    """The shell the vendor CLI's hook dispatcher uses on this host."""
    return "powershell" if (os.name == "nt" if windows is None else windows) else "sh"


def _powershell_single_quote(arg: str) -> str:
    """One argv element, so that a NATIVE child receives it byte-for-byte from PowerShell.

    TWO parsers sit between this string and the child, and both have to be satisfied:

    1. PowerShell's own. Inside SINGLE quotes it interprets nothing — no `$` expansion, no
       subexpression, no backtick escape — and the only character needing escaping is the quote
       itself, escaped by DOUBLING. Single quotes are therefore the right construct: there is no
       escape table to get wrong.
    2. `CommandLineToArgvW`. Windows PowerShell re-serialises arguments onto a command line when it
       invokes a native executable, and a literal `"` written plainly is consumed there as a
       delimiter — measured: an argument `a"b` arrived at the child as `ab`. So a quote must reach
       that layer already escaped as `\\"`, and any run of backslashes IMMEDIATELY BEFORE a quote
       must be doubled, or the backslashes escape each other and the quote goes back to being a
       delimiter.

    Satisfying only the first parser stops the code EXECUTION and still corrupts the argument. Both
    are needed for "receives it literally", which is the property this unit claims.
    """
    out: list[str] = []
    backslashes = 0
    for ch in arg:
        if ch == "\\":
            backslashes += 1
            out.append(ch)
            continue
        if ch == '"':
            out.append("\\" * backslashes)   # double the run that precedes the quote
            out.append('\\"')
        else:
            out.append(ch)
        backslashes = 0
    return "'" + "".join(out).replace("'", "''") + "'"


def render_hook_command(argv: list[str], *, shell: str) -> str:
    """Render an argv vector as a command line THAT SHELL can actually parse.

    The argv vector stays the authority (it is what the boundary pins and what the shell-side
    validator re-derives); this is only its dispatcher-specific rendering.

    W-38. This used `subprocess.list2cmdline` for BOTH shells. `list2cmdline` implements the quoting
    rules of CreateProcess/cmd, and the PowerShell branch then hands the result to
    `powershell.exe -Command`, which parses a different language. Measured on this host through this
    function and a real `powershell.exe`:

        'a$(Write-Host INJECTED)b'  ->  INJECTED was EXECUTED; the child received 'ab'
        'a;b'                       ->  rc=1; the ';' ENDED the command and the child got 'a'
        'a$env:PATH'                ->  the variable was EXPANDED into the argument
        'a`b'                       ->  the backtick was consumed as an escape

    So a subexpression in an argv element ran as PowerShell code — N-03's class on the PowerShell
    side. The argv rendered here is the voice-turn hook (an interpreter path, a script path under
    the repository, and the boundary's arguments); the repository path is operator-chosen, and `$`,
    backtick, `;` and `(` are all legal in a Windows directory name. `verify_hook_command` RUNS this
    string during launch verification, so the parse happens on the launch path.

    The `sh` branch is left ALONE, deliberately. `list2cmdline` is not sh quoting either — `$` and
    backtick remain special inside its double quotes — but that is off-host, unmeasured here, and
    the operator ruling for this unit is to narrow to the measured surface. Recorded, not repaired.
    """
    if shell == "powershell":
        rendered = " ".join(_powershell_single_quote(a) for a in argv)
        return f"{POWERSHELL_CALL_OPERATOR}{rendered}"
    return subprocess.list2cmdline(argv)


def verify_hook_command(command: str, *, shell: str) -> dict[str, Any]:
    """RUN the pinned command through the real dispatcher and require a fail-closed deny.

    A hook the dispatcher cannot parse does not block anything — the vendor reports a non-blocking
    hook error and carries on — so the string being *correct* is not the property that matters; being
    *runnable here* is. Raises PermissionProfileUnavailable rather than returning a verdict, because
    an unverifiable boundary must refuse the launch (invariant 2, fail closed on ambiguity).
    """
    if shell == "powershell":
        exe = shutil.which("powershell.exe") or shutil.which("powershell")
        if not exe:
            raise PermissionProfileUnavailable(
                "PowerShell is unavailable; the voice-turn hook command cannot be verified")
        argv = [exe, "-NoProfile", "-NonInteractive", "-Command", command]
    else:
        exe = shutil.which("sh")
        if not exe:
            raise PermissionProfileUnavailable(
                "sh is unavailable; the voice-turn hook command cannot be verified")
        argv = [exe, "-c", command]
    try:
        done = subprocess.run(
            argv, input=json.dumps(_PROBE_EVENT), capture_output=True, text=True,
            timeout=VERIFY_TIMEOUT_S)
    except (subprocess.SubprocessError, OSError) as exc:
        raise PermissionProfileUnavailable(
            f"the voice-turn hook command could not be dispatched: {exc}") from exc
    if done.returncode != 0:
        raise PermissionProfileUnavailable(
            f"the {shell} dispatcher rejected the voice-turn hook command "
            f"(exit {done.returncode}): {(done.stderr or '').strip()[:200]}")
    try:
        decision = json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"]
    except (ValueError, KeyError, TypeError) as exc:
        raise PermissionProfileUnavailable(
            f"the voice-turn hook produced no readable decision: {(done.stdout or '').strip()[:200]}"
        ) from exc
    if decision != "deny":
        raise PermissionProfileUnavailable(
            f"the voice-turn hook answered {decision!r} with no supervisor listening; "
            "a boundary that does not fail closed is not a boundary")
    return {"shell": shell, "exit_code": done.returncode, "decision": decision}


def build_conductor_permission_profile(
    permission_profile_id: str,
    *,
    node_executable: str | None = None,
    hook_path: Path = HOOK_PATH,
    windows: bool | None = None,
    verifier: Callable[..., dict[str, Any]] | None = None,
) -> AppliedConductorPermissionProfile:
    if not permission_profile_id:
        raise PermissionProfileUnavailable("permission profile id is empty")
    node = node_executable or shutil.which("node")
    if not node:
        raise PermissionProfileUnavailable("Node.js is unavailable; voice-turn hook cannot run")
    hook = hook_path.resolve()
    try:
        hook.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise PermissionProfileUnavailable("voice-turn hook must live inside the repository") from exc
    if not hook.is_file():
        raise PermissionProfileUnavailable(f"voice-turn hook is missing: {hook}")
    hook_sha = hashlib.sha256(hook.read_bytes()).hexdigest()
    hook_argv = [str(Path(node).resolve()), str(hook)]
    shell = dispatch_shell(windows)
    command = render_hook_command(hook_argv, shell=shell)
    # Prove it RUNS here before anything is allowed to depend on it (U162). The verdict is re-checked
    # here rather than trusted to the verifier, so an injected one cannot widen the contract either.
    probe = (verifier or verify_hook_command)(command, shell=shell)
    if not isinstance(probe, dict) or probe.get("decision") != "deny" or probe.get("exit_code") != 0:
        raise PermissionProfileUnavailable(
            f"the voice-turn hook command was not proved fail-closed under {shell}: {probe!r}")
    settings: dict[str, Any] = {
        "hooks": {
            "UserPromptSubmit": [_hook(command)],
            "PreToolUse": [{"matcher": ".*", **_hook(command)}],
            "PermissionRequest": [{"matcher": ".*", **_hook(command)}],
            "ConfigChange": [_hook(command)],
            "Stop": [_hook(command)],
            "StopFailure": [_hook(command)],
            "SessionEnd": [_hook(command)],
        }
    }
    settings_json = json.dumps(settings, separators=(",", ":"), ensure_ascii=False)
    boundary = {
        "schema": BOUNDARY_SCHEMA,
        "supervisor_owned": True,
        "non_executing_voice_turns": True,
        # The supervisor owns and pins the policy bytes, but Claude Code's hook dispatcher executes
        # them. A dispatcher timeout/failure is not supervisor-process containment, so production
        # direct voice delivery must remain disabled until this fact can truthfully become True.
        "enforced_by_supervisor_process": False,
        "permission_profile_id": permission_profile_id,
        "prompt_marker_format": PROMPT_MARKER_FORMAT,
        "hook_relative_path": hook.relative_to(ROOT).as_posix(),
        "hook_sha256": hook_sha,
        "hook_runtime": str(Path(node).resolve()),
        "hook_argv": hook_argv,
        "hook_command": command,
        "hook_command_shell": shell,
        "hook_command_verified": True,
        "hook_command_probe": probe,
        "settings_sha256": hashlib.sha256(settings_json.encode("utf-8")).hexdigest(),
        "transport_contract": [
            "UserPromptSubmit asks the supervisor process to admit the exact pending payload",
            "PreToolUse and PermissionRequest ask the supervisor process for deny decisions",
            # This said the lifecycle events "notify the supervisor process to disarm". They do not,
            # and must not: the supervised child holds the transport bearer, so a lifecycle event it
            # sends is an OBSERVATION (a forged SessionEnd produced a real deny->allow bypass at
            # iteration 88). The line asserted a disarm the code did not have (U166, spec-audit M4);
            # what actually ends an admitted turn is an operator signal Electron main measures for
            # itself -- their next keystroke, or the Ctrl+Shift+Escape chord -- plus the observed
            # OS-process exit.
            "Stop/StopFailure/SessionEnd are recorded as observations and never disarm",
            "only Electron main's own operator-keyboard observation (or the observed process exit) "
            "ends an admitted voice turn",
            "transport loss blocks or denies fail-closed",
        ],
        "transport_limit": (
            "the ticket pins transport bytes/settings but cannot claim a listening supervisor; "
            "Electron main upgrades the runtime boundary only after its authenticated loopback "
            "authority service is listening and injected into the supervised child"
        ),
    }
    return AppliedConductorPermissionProfile(settings_json=settings_json, boundary=boundary)
