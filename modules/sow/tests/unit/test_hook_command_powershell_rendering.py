"""W-38 — an argv vector rendered for the WRONG shell, then run by PowerShell.

F-1 narrowed this unit by measurement: the Python list-argv path is clean (`work&space`, `a&b`,
`%PATH%`, `c|d`, `e\\rf`, `g;h`, `$(id)` and backticks all arrive byte-literal at rc=0 through
`run_managed_process`). The surviving surface is the Node / PowerShell one, and this is it.

`render_hook_command` builds the voice-turn hook's command line with
``subprocess.list2cmdline(argv)`` and prefixes the call operator. `list2cmdline` implements the
quoting rules of **CreateProcess/cmd**. The string is then executed by
``powershell.exe -NoProfile -NonInteractive -Command <command>``, and PowerShell parses a different
language. Measured on this host through the real function and a real `powershell.exe`, BEFORE the
repair:

    argv element                 child received
    'a$(Write-Host INJECTED)b'   INJECTED was EXECUTED; the child got 'ab'
    'a;b'                        rc=1 -- the ';' ENDED the command and the child got only 'a'
    'a$env:PATH'                 the environment variable was EXPANDED into the argument
    'a``b'                       the backtick was consumed as an escape

So a subexpression in an argv element runs as PowerShell code. That is N-03's class on the
PowerShell side.

REACHABILITY, stated rather than implied. The argv rendered here is the voice-turn boundary hook:
an interpreter path, a script path under the repository, and the boundary's own arguments. The
repository path is operator-chosen, and `$`, `` ` ``, `;` and `(` are all legal in a Windows
directory name. `verify_hook_command` then RUNS the rendered string during launch verification, so
the parse happens on the launch path and not only in the vendor's dispatcher.

SCOPE. The `sh` branch of the same function also renders with `list2cmdline`, which is likewise not
sh quoting -- `$` and backtick remain special inside its double quotes. That is the same class, it
is NOT measured here (this host dispatches PowerShell), and the operator ruling for this unit is to
narrow to the measured surface and not broaden. It is recorded, not repaired.
"""
from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from node_runtime.supervisor.conductor_permission_profile import render_hook_command

POWERSHELL = shutil.which("powershell.exe") or shutil.which("powershell")
requires_powershell = pytest.mark.skipif(
    POWERSHELL is None, reason="PowerShell is absent; the rendering under test is its parser's")


#: The probe child prints its OWN argv element, so what is measured is what the process received.
#: `cmd.exe /c echo` was the first choice and is the wrong instrument: cmd re-quotes and re-parses
#: what PowerShell hands it, so a clean pass-through came back wrapped in double quotes and the
#: assertion failed for a reason that had nothing to do with the code under test. A Python child
#: reports `sys.argv[1]` verbatim, with no second parser in the path.
_PROBE = "import sys; sys.stdout.write(sys.argv[1])"


def _child_argv(payload: str) -> tuple[int, str]:
    """Render an argv carrying `payload` for PowerShell, run it, report what the CHILD received."""
    command = render_hook_command([sys.executable, "-c", _PROBE, payload], shell="powershell")
    done = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, timeout=60,
    )
    return done.returncode, (done.stdout or "")


@requires_powershell
@pytest.mark.parametrize("payload", [
    "a$(Write-Host INJECTED)b",   # a subexpression: PowerShell EXECUTED this before the repair
    "a$env:PATH",                 # variable expansion
    "a;b",                        # statement separator
    "a`b",                        # the escape character
    "a'b",                        # a single quote, which the repair's own quoting must survive
    'a"b',                        # a double quote
    "a b",                        # a space, the case ordinary quoting already handled
    "a&b",                        # cmd's separator, harmless to PowerShell but must stay literal
    "a|b",                        # pipeline
    "a@{x}b",                     # hashtable/splat syntax
])
def test_a_metacharacter_bearing_argument_reaches_the_child_LITERALLY(payload: str) -> None:
    """NEGATIVE: every one of these must arrive byte-for-byte, and none may execute."""
    rc, out = _child_argv(payload)
    assert rc == 0, f"the rendered command did not run cleanly for {payload!r}: {out!r}"
    assert out == payload, (
        f"{payload!r} was re-interpreted by PowerShell and the child received {out!r} — "
        "list2cmdline implements cmd/CreateProcess quoting, not PowerShell's"
    )


@requires_powershell
def test_a_subexpression_in_an_argument_does_not_EXECUTE() -> None:
    """NEGATIVE, the sharpest case: this printed INJECTED before the repair.

    Asserted separately from the parametrised literal check because "the child got the wrong text"
    and "the host ran attacker-chosen code" are different failures, and only one of them is a
    security defect.
    """
    # The marker must be checked by EQUALITY, not by absence. The literal payload necessarily
    # contains the marker text, so `"INJECTED" not in out` fails on a correct pass-through — the
    # first version of this test asserted exactly that and reported a green repair as a failure.
    # Equality is the real property: if the subexpression had run, the marker would have gone to
    # stdout on its own and the argument would have arrived with the subexpression REMOVED.
    payload = "safe$(Write-Host INJECTED)tail"
    rc, out = _child_argv(payload)
    assert rc == 0
    assert out == payload, (
        f"the child received {out!r} rather than the literal argument — a subexpression that "
        "executes leaves its own output behind and hands the child the collapsed remainder"
    )


@requires_powershell
def test_an_ordinary_argv_still_works() -> None:
    """POSITIVE: the rendering must remain runnable. This passed before the repair too."""
    rc, out = _child_argv("ordinary-argument")
    assert (rc, out) == (0, "ordinary-argument")


def test_the_rendering_uses_powershell_quoting_not_cmd_quoting() -> None:
    """The rendered STRING is inspected directly, so the property holds without a PowerShell host.

    A test that only ran where PowerShell exists would be skipped on the very hosts a reviewer uses
    to check the repair off-Windows.
    """
    rendered = render_hook_command(["node", "C:/repo/hook.js", "a$(x)b"], shell="powershell")
    assert rendered.startswith("& "), "the call operator must still lead"
    assert "'a$(x)b'" in rendered or "'a$(x)b'" in rendered.replace("''", "'"), (
        f"the argument is not single-quoted for PowerShell: {rendered!r}"
    )


def test_an_embedded_single_quote_is_doubled_not_dropped() -> None:
    """PowerShell escapes a literal quote inside a single-quoted string by DOUBLING it."""
    rendered = render_hook_command(["node", "it's"], shell="powershell")
    assert "'it''s'" in rendered, f"embedded quote not escaped by doubling: {rendered!r}"
