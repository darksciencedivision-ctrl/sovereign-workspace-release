"""Phase 15C `.detect` (integration): the REAL Codex CLI presence/version/auth probe.

The honest LIVE proof for `.detect`. It actually spawns the benign, local, credential-free
metadata calls — `codex --version`, `codex login status`, `codex exec --help` — and asserts the
detection facts the `.adapter` supervised spawn gate will act on. It makes NO live model call
(`codex exec <prompt>` is never run). When `codex` is absent it SKIPS-WITH-RECORD (directive
§10.4, the exact operator remediation is printed) — never faked.

Entry condition (OP-7 item 1 / OP-8): `codex` installed + authenticated by the operator
(`npm install -g @openai/codex` ; `codex login`). If present but unauthenticated, the probe
still runs and records `authenticated=False` (a real, honest negative), OpenAI legs OWED.
"""
from __future__ import annotations

import pytest

from adapters import detect
from adapters.frontier.codex import (
    MIN_CODEX_VERSION,
    CodexCli,
    probe_codex,
)

_CLI = CodexCli()
_PRESENT = detect.codex_available() and _CLI.executable is not None

pytestmark = pytest.mark.skipif(
    not _PRESENT,
    reason=("codex CLI not present on host — .detect live probe SKIPPED-WITH-RECORD (§10.4). "
            "Operator remediation: `npm install -g @openai/codex` then `codex login`."))


def test_live_codex_version_meets_gate() -> None:
    """A REAL `codex --version` spawn: present, a parseable version, at/above the minimum."""
    probe = probe_codex(_CLI)
    assert probe.present is True, probe.detail
    assert probe.version_tuple is not None, f"unparseable live version: {probe.version!r}"
    assert probe.version_tuple >= MIN_CODEX_VERSION, probe.version
    assert probe.meets_minimum is True
    assert probe.executable and "codex" in probe.executable.lower()


def test_live_codex_structural_exec_and_model_flag() -> None:
    """The CLI structurally supports non-interactive exec + per-node model selection (`-m/--model`)
    — probed from `codex exec --help`, NOT a model call."""
    probe = probe_codex(_CLI)
    assert probe.model_flag_supported is True, "codex exec --help did not advertise -m/--model"
    assert probe.noninteractive_exec_supported is True


def test_live_codex_auth_state_is_reported_honestly() -> None:
    """`codex login status` is read and its result recorded verbatim. We do NOT require authed
    (a present-but-unauthenticated host is a real, honest negative — OpenAI legs OWED); we require
    only that the auth state is a real observation, never fabricated, and the token is never in it."""
    probe = probe_codex(_CLI)
    assert isinstance(probe.authenticated, bool)
    assert probe.auth_detail and probe.auth_detail != "(cli absent)"
    # §2.2: the reported detail is a STATE line, never a credential (no token-looking blob)
    assert "sk-" not in probe.auth_detail.lower()
    # The exact registered conductor is distinguished from the old provisional worker labels.
    by_name = {c.operator_name: c for c in probe.candidate_models}
    assert set(by_name) == {"ChatGPT 5.6 Sol", "5.5", "5.5 Sol"}
    assert by_name["ChatGPT 5.6 Sol"].verified is True
    assert by_name["ChatGPT 5.6 Sol"].conductor_capable is True
    assert by_name["5.5"].verified is False
    assert by_name["5.5 Sol"].verified is False
