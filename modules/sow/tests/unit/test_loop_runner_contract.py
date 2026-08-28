"""Binding print-mode execution-contract regression (D-LOOP-2 / U159)."""
from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _usage_limit_pattern() -> str:
    """The regex the runner feeds to PowerShell's -match for the provider limit screen."""
    runner = (REPO / "tools" / "loop" / "run_loop.ps1").read_text(encoding="utf-8-sig")
    match = re.search(r'\$usageLimited\s*=\s*\$logText\s*-match\s*"([^"]+)"', runner)
    assert match is not None, "runner no longer detects the provider usage-limit screen"
    return match.group(1)


def test_loop_runner_defaults_to_the_binding_claude_print_mode() -> None:
    runner = (REPO / "tools" / "loop" / "run_loop.ps1").read_text(encoding="utf-8-sig")
    prompt = (REPO / "tools" / "loop" / "driver_prompt.txt").read_text(encoding="utf-8-sig")

    assert '[ValidateSet("claude")]' in runner
    assert '[string]$Builder = "claude"' in runner
    assert "& claude -p " in runner
    assert "codex exec" not in runner
    assert '$Builder -eq "codex"' not in runner
    assert "PRINT-MODE FACT (D-LOOP-2, binding): you are running under 'claude -p'." in prompt
    assert "Drives Claude Code through AUTONOMOUS_BUILD_DIRECTIVE.md" in runner


def test_runner_recognises_every_observed_provider_limit_screen() -> None:
    """A limit the runner does not recognise is spent as a wasted iteration, not waited out.

    Iterations 87-91 all met the Claude Max *weekly* limit screen; the committed pattern
    only knew the *session* wording, so the runner counted those runs as ordinary work.
    """
    pattern = re.compile(_usage_limit_pattern(), re.IGNORECASE)

    for observed in (
        "Claude usage limit reached. Your limit will reset at 12pm.",
        "You've hit your session limit. Resets in 3 hours.",
        "You've hit your weekly limit. Resets Jul 30 at 12pm (America/Chicago).",
    ):
        assert pattern.search(observed), f"runner would not wait out: {observed}"

    # Fail-open the other way is just as bad: ordinary build output must not look like a limit.
    for ordinary in (
        "gate/phase-17c not created; the receipt is red",
        "hit your head on the ceiling of the token budget",
    ):
        assert not pattern.search(ordinary), f"runner would sleep 15 min on: {ordinary}"
