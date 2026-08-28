"""No pytest run may spend a live provider-subscription call (U163).

The mock-first suites already tried to guarantee this, each in its own way — `patch.object(
claude_code_module.subprocess, "run", ...)`, `monkeypatch.setattr(subprocess, "run", forbidden)`.
Those patches stopped intercepting on 2026-07-28, when the frontier adapter moved its spawn from
`subprocess.run` to `run_managed_process` (commit c8af621, the descendant-killing job boundary).
Nothing failed: the calls simply became REAL. Measured on 2026-07-30, `pytest tests/` spent live
`claude` calls in three `test_live_debate_flow` cases and reported a `live` leg for a suite whose
own docstring says `live` must be unreachable in it — the checkpoint was genuine, which is
precisely the problem.

So the seam is no longer allowed to be per-test knowledge. This guard sits at the process boundary
itself and refuses, by executable NAME and argument vector, any BILLABLE spawn of a provider CLI
from inside the test suite:

  * it patches the definition site, so modules imported later bind the guarded function;
  * it patches every already-imported module that holds a `from … import run_managed_process` name;
  * it covers `subprocess.run`/`Popen` too, since a future adapter could route either way.

It does NOT restrict ordinary spawns (node, python, powershell, wsl) — those are how several tests
prove real behaviour. Live provider work belongs to the `tools/live/` smokes and the in-Electron
self-checks, which run outside pytest and record receipts. A test that genuinely must reach a
provider can mark itself `@pytest.mark.live_cli`, and that mark is then visible in the diff.

Nor does it restrict the CREDENTIAL-FREE METADATA calls (U165). Refusing by executable name alone
also refused `codex --version`, `codex login status` and `codex exec --help` — the local probes
Phase 15C `.detect` is built on, which reach no model and cost nothing — and turned nine honest
host-probe tests red the moment the guard landed. The line the guard actually defends is
*spending a subscription call*, so the allowance is drawn there and drawn TIGHT: the WHOLE argv
must equal one of the enumerated forms below. `exec --help` is free; `exec --help <prompt>` is a
model call wearing its clothes, and a bare `codex` opens the interactive session — both refused.

This lives in its own module, not in `conftest.py`, so that a test can import the exception class
and get the SAME object the fixture raises (pytest loads a rootdir conftest under its own module
name, and an importing test would otherwise catch a different class of the same name).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# The CLIs OP-6/OP-9/OP-12 authorized for LIVE use. A call to one of these costs the operator's
# real subscription quota, which a unit-test run must never do implicitly.
#
# `grok` and `agy` joined the set at the Phase-18A gate (round-4 gate-validator finding 1). 18A
# added a real spawn seam for them (`frontier_provider_recon.subprocess_runner`), and the
# validator proved by PATH tripwire that no test reaches it today — so this is a defence added
# BEFORE the regression, which is the only useful time. U163 is the reason it exists at all: a
# `pytest tests/` run once spent real `claude` calls while every test stayed green.
LIVE_PROVIDER_CLIS = frozenset({"claude", "codex", "grok", "agy"})

# Argument vectors that make one of those CLIs print its own version, its own help, or the LOCAL
# state of an existing login — and nothing else. No prompt, no session, no token in the output, no
# quota spent. An ALLOWLIST matched whole, never as a prefix: everything not enumerated here is a
# refusal, so a new subcommand is refused until someone establishes it is free and adds it.
CREDENTIAL_FREE_METADATA_ARGV = frozenset({
    ("--version",), ("-V",),
    ("--help",), ("-h",),
    ("exec", "--help"), ("exec", "-h"),   # structural: does `-m/--model` exist (15C `.detect`)
    ("login", "status"),                  # authenticated yes/no; reports state, never the token
})


class LiveProviderCallInTests(RuntimeError):
    """A test tried to spawn a live provider CLI. The seam it patched is not the seam in use."""


#: A wrapper's argument IS a command line, so these separate one token into several.
#: Command separators. `&` is deliberately absent: it is PowerShell's call operator and
#: carries meaning (`& '…\\claude.exe'`), so it is tokenised rather than discarded.
_COMMAND_SEPARATORS = re.compile(r"[;|\n]+")


def _executable_stem(token: object) -> str:
    """The executable name a token would run, on EITHER platform.

    `Path().stem` does not split on a backslash under POSIX, so `C:\\tools\\claude.exe` resolved to
    the whole string there and walked past this guard — the one host-specific row of the R-19
    table, which passes on Windows and fails on Linux. Normalising the separator first makes the
    classification the same on both, which is what a guard against spending real money should be.
    """
    text = str(token).strip().strip('"').strip("'")
    return Path(text.replace("\\", "/")).stem.lower()


#: Flags whose VALUE is itself a command line. Everything else's value is data -- which is the
#: distinction the first cut of this guard missed: it refused
#: `powershell … -Command "… -Provider grok …"` because `grok` appeared as the value of
#: `-Provider`, and that broke a real PowerShell-syntax test.
_COMMAND_INTRODUCING_FLAGS = frozenset({
    "-c", "-lc", "-command", "/c", "/k", "-e", "--eval", "-encodedcommand", "-file",
})

#: PowerShell's call operator: the token after it IS the executable.
_CALL_OPERATORS = frozenset({"&", "."})


def _is_flag(token: str) -> bool:
    return token.startswith("-") or token.startswith("/")


def _executable_positions(tokens: list[str]) -> list[str]:
    """The tokens in a sequence that could name the thing being EXECUTED.

    argv[0] always; a token after a non-flag (`npx claude`, `wsl claude`); a token after a
    command-introducing flag (`bash -lc …`, `cmd /c …`); a token after a call operator
    (`& 'C:\\…\\claude.exe'`). A token after any OTHER flag is that flag's VALUE and is not an
    executable position — `-Provider grok` names a provider, it does not run one.
    """
    out: list[str] = []
    for index, token in enumerate(tokens):
        if index == 0:
            out.append(token)
            continue
        previous = tokens[index - 1]
        if previous in _CALL_OPERATORS:
            out.append(token)
        elif _is_flag(previous):
            if previous.lower() in _COMMAND_INTRODUCING_FLAGS:
                out.append(token)
        else:
            out.append(token)
    return out


def _candidate_tokens(cmd: object) -> tuple[str, ...]:
    """Every token in an EXECUTABLE POSITION, including inside a wrapper's own argument string
    (`bash -lc "claude -p hi"`, `powershell -Command "claude …"`).

    A wrapper's argument is itself a command line, so it is split into segments and each segment's
    executable positions are examined too — `cmd /c npx codex exec hi` reaches `codex`.
    """
    if isinstance(cmd, (list, tuple)):
        raw = [str(a) for a in cmd]
    elif isinstance(cmd, (str, Path)):
        raw = [str(cmd)]
    else:
        return ()

    out: list[str] = []
    for token in _executable_positions(raw):
        out.append(token)
        for segment in _COMMAND_SEPARATORS.split(token):
            words = [w for w in segment.split() if w]
            if len(words) > 1:
                out.extend(_executable_positions(words))
            elif words:
                out.append(words[0])
    return tuple(t for t in out if t)


def live_provider_name(cmd: object) -> str | None:
    """The provider CLI name this command would execute, or None.

    W-21/R-19: scans EVERY token and the string form, not `Path(cmd[0]).stem`. The thing that
    actually executes `claude` is not always argv[0] — `npx claude`, `cmd /c claude`, `wsl claude`,
    `bash -lc "claude -p hi"`, `powershell -Command "claude …"` — and the review executed every one
    of those shapes straight past the old first-token check.

    Deliberately broad, because the failure mode on the other side is spending the operator's real
    subscription quota. A false refusal costs a test author one `pytest.mark.live_cli` or one
    rephrased fixture, and it is visible in the diff; a false permit is silent and billable.
    """
    for token in _candidate_tokens(cmd):
        stem = _executable_stem(token)
        if stem in LIVE_PROVIDER_CLIS:
            return stem
    return None


def billable_provider_call(cmd: object) -> str | None:
    """The provider CLI name this command would spend QUOTA on, or None (U165).

    None for a command that is not a provider CLI at all, and for the enumerated credential-free
    metadata forms. Everything else that names a provider CLI — including a bare invocation, which
    opens an interactive session — is billable as far as this guard is concerned. Fail closed:
    an argv shape nobody has established as free is treated as one that costs.
    """
    name = live_provider_name(cmd)
    if name is None:
        return None
    # W-21: the metadata allowance is only meaningful for a DIRECT invocation. With a wrapper in
    # front, this guard cannot know which token the wrapper will execute or with what arguments, so
    # `npx claude --version` fails closed even though the same argv run directly would be free.
    # That cost is deliberate and is asserted by a test rather than discovered later.
    direct = (isinstance(cmd, (list, tuple)) and bool(cmd)
              and _executable_stem(cmd[0]) in LIVE_PROVIDER_CLIS)
    if not direct:
        return name
    args = tuple(str(a) for a in cmd[1:])
    return None if args in CREDENTIAL_FREE_METADATA_ARGV else name


def _refuse(name: str, cmd: object) -> LiveProviderCallInTests:
    return LiveProviderCallInTests(
        f"the test suite tried to spawn the live `{name}` CLI ({cmd!r}). A pytest run must not "
        "spend a subscription call: patch the seam the adapter actually uses "
        "(`run_managed_process` in the adapter's own module), or move the leg to a tools/live "
        f"smoke. (Credential-free metadata probes are allowed: {sorted(CREDENTIAL_FREE_METADATA_ARGV)}.)"
    )


def install(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Wrap every process boundary a provider CLI could leave through, for one test."""
    from adapters.frontier import process_tree

    real_managed = process_tree.run_managed_process

    def guarded_managed(cmd, **kwargs):  # type: ignore[no-untyped-def]
        name = billable_provider_call(cmd)
        if name:
            raise _refuse(name, cmd)
        return real_managed(cmd, **kwargs)

    monkeypatch.setattr(process_tree, "run_managed_process", guarded_managed)
    # `from … import run_managed_process` copies the object; the copy is what those callers invoke.
    for module in list(sys.modules.values()):
        if getattr(module, "run_managed_process", None) is real_managed:
            monkeypatch.setattr(module, "run_managed_process", guarded_managed, raising=False)

    real_run = subprocess.run
    real_popen = subprocess.Popen

    def guarded_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        name = billable_provider_call(cmd)
        if name:
            raise _refuse(name, cmd)
        return real_run(cmd, *args, **kwargs)

    class GuardedPopen(real_popen):  # type: ignore[misc, valid-type]
        def __init__(self, cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
            name = billable_provider_call(cmd)
            if name:
                raise _refuse(name, cmd)
            super().__init__(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded_run)
    monkeypatch.setattr(subprocess, "Popen", GuardedPopen)
