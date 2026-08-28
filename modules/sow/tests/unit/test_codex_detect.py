"""Phase 15C `.detect` (unit): the Codex CLI detection/probe surface.

Deterministic, no-subprocess proofs of the probe logic for every branch (present/authed,
unparseable version, below-minimum, unauthenticated, absent). The load-bearing properties:
  - the probe NEVER raises — every failure is captured as fail-closed data (Buildout §4);
  - unparseable / below-min version ⇒ meets_minimum False (fail closed, never passes);
  - a non-positive/ambiguous `login status` ⇒ authenticated False (never assume auth on silence);
  - the operator-named GPT-5.5 models are recorded UNVERIFIED (no offline enumeration; the
    accepted id is a live-smoke fact for `.adapter`) — never fabricated as a confirmed CLI slug.
The real `CodexCli` (which would spawn `codex`) is NEVER invoked here; the live probe is in the
integration suite. `codex exec` is never called anywhere in `.detect` (no live model call).
"""
from __future__ import annotations

import subprocess

import pytest

from adapters.frontier.codex import (
    CODEX_ADAPTER,
    CODEX_CANDIDATE_MODEL_REFS,
    MIN_CODEX_VERSION,
    CandidateModelRef,
    CodexCli,
    CodexProbe,
    CodexUnavailable,
    CodexVersionError,
    MockCodexCli,
    parse_codex_version,
    probe_codex,
)


# ---- provider id matches the frozen schema enum / live-auth scope --------------------------

def test_provider_id_is_frozen_schema_enum_value() -> None:
    assert CODEX_ADAPTER == "openai_codex_cli"
    from control_plane.profiles.live_authorization import _AUTHORIZED_PROVIDERS
    assert CODEX_ADAPTER in _AUTHORIZED_PROVIDERS  # the live gate keys on exactly this id


# ---- version parsing: fail closed on garbage ----------------------------------------------

def test_parse_codex_version_extracts_first_triple() -> None:
    assert parse_codex_version("codex-cli 0.144.6") == (0, 144, 6)
    assert parse_codex_version("0.1.0\n") == (0, 1, 0)


def test_parse_codex_version_raises_on_unparseable() -> None:
    with pytest.raises(CodexVersionError):
        parse_codex_version("codex-dev")
    with pytest.raises(CodexVersionError):
        parse_codex_version("")


# ---- candidate model refs are honest: recorded, unverified, not fabricated -----------------

def test_candidate_models_are_operator_named_and_honest() -> None:
    names = {c.operator_name for c in CODEX_CANDIDATE_MODEL_REFS}
    assert names == {"ChatGPT 5.6 Sol", "5.5", "5.5 Sol"}
    for c in CODEX_CANDIDATE_MODEL_REFS:
        assert isinstance(c, CandidateModelRef)
    registered = next(c for c in CODEX_CANDIDATE_MODEL_REFS if c.operator_name == "ChatGPT 5.6 Sol")
    assert registered.provisional_slug == "gpt-5.6-sol"
    assert registered.verified is True and registered.conductor_capable is True
    provisional = [c for c in CODEX_CANDIDATE_MODEL_REFS if c is not registered]
    assert all(c.verified is False for c in provisional)
    assert all("live" in c.note.lower() for c in provisional)


# ---- probe: present + authenticated + version at/above the minimum --------------------------

def test_probe_present_authed_meets_minimum() -> None:
    probe = probe_codex(MockCodexCli(version="codex-cli 0.144.6", authenticated=True))
    assert isinstance(probe, CodexProbe)
    assert probe.present is True
    assert probe.version_tuple == (0, 144, 6) and probe.meets_minimum is True
    assert probe.authenticated is True and "chatgpt" in probe.auth_detail.lower()
    assert probe.model_flag_supported is True               # `-m/--model` seen in exec --help
    assert probe.noninteractive_exec_supported is True
    assert probe.candidate_models == CODEX_CANDIDATE_MODEL_REFS
    assert probe.detail == "ok"


def test_probe_flags_below_minimum() -> None:
    probe = probe_codex(MockCodexCli(version="codex-cli 0.0.1"))
    assert probe.present is True and probe.version_tuple == (0, 0, 1)
    assert probe.version_tuple < MIN_CODEX_VERSION and probe.meets_minimum is False


def test_probe_flags_unparseable_version() -> None:
    probe = probe_codex(MockCodexCli(version="codex-dev-build"))
    assert probe.present is True and probe.version_tuple is None and probe.meets_minimum is False


# ---- auth fail-closed: silence / negative / ambiguous ⇒ NOT authenticated ------------------

def test_probe_unauthenticated_fails_closed() -> None:
    probe = probe_codex(MockCodexCli(authenticated=False, auth_detail="Not logged in"))
    assert probe.present is True and probe.meets_minimum is True   # present+versioned…
    assert probe.authenticated is False                            # …but not authed
    assert probe.detail == "present but not authenticated"


def test_real_cli_login_status_treats_not_logged_in_as_unauthenticated() -> None:
    """The real `CodexCli.login_status` classifier fails closed on a 'not logged in' result even
    with rc==0, and never treats an ambiguous/empty output as authenticated."""
    cli = CodexCli(executable="codex")

    def _fake(_a, **_k):
        return subprocess.CompletedProcess(_a, 0, stdout="Not logged in\n", stderr="")

    orig = subprocess.run
    subprocess.run = _fake  # type: ignore[assignment]
    try:
        authed, detail = cli.login_status()
    finally:
        subprocess.run = orig  # type: ignore[assignment]
    assert authed is False and "not logged in" in detail.lower()


def test_real_cli_login_status_reports_authed_on_chatgpt_login() -> None:
    cli = CodexCli(executable="codex")

    def _fake(_a, **_k):
        return subprocess.CompletedProcess(_a, 0, stdout="", stderr="Logged in using ChatGPT\n")

    orig = subprocess.run
    subprocess.run = _fake  # type: ignore[assignment]
    try:
        authed, detail = cli.login_status()
    finally:
        subprocess.run = orig  # type: ignore[assignment]
    assert authed is True and "chatgpt" in detail.lower()


# ---- W-47 (R-05): a signed-out sentence that CONTAINS "logged in" ---------------------------
# `login_status` asked `any("logged in" in low)` and then subtracted an exact-substring blacklist
# ("not logged in", "no login", "please log in", ...). Every signed-out phrasing OUTSIDE that list
# therefore classified as AUTHENTICATED at rc==0 -- "no longer", "not currently", "previously",
# "never", "aren't", and a message saying the check itself FAILED. Six of them, measured.

SIGNED_OUT_PROSE = [
    "You are no longer logged in",
    "You are not currently logged in. Run codex login.",
    "You were logged in previously; the session has expired.",
    "Never logged in on this machine.",
    "You aren" + chr(39) + "t logged in.",
    "Failed to check whether you are logged in.",
    "Could not determine whether you are logged in.",
]


@pytest.mark.parametrize("prose", SIGNED_OUT_PROSE)
def test_a_signed_out_sentence_containing_logged_in_is_NOT_authenticated(prose, monkeypatch) -> None:
    """R-05. Every one of these says the operator is NOT signed in, and every one contains the
    substring the classifier looked for. rc==0 throughout, because `codex login status` reporting a
    signed-out state is a SUCCESSFUL call -- the exit code is not the evidence here, which is why
    the phrase had to carry the weight and why it must be read as a declaration, not a substring."""
    cli = CodexCli(executable="codex")
    monkeypatch.setattr(subprocess, "run",
                        lambda _a, **_k: subprocess.CompletedProcess(_a, 0, stdout=prose + chr(10), stderr=""))
    authed, _detail = cli.login_status()
    assert authed is False


@pytest.mark.parametrize("line", [
    "Logged in using ChatGPT",
    "Logged in as user@example.com using ChatGPT",
    "logged in",
    "You are logged in using ChatGPT",
    "You" + chr(39) + "re logged in as someone@example.com",
])
def test_a_DECLARATIVE_login_line_still_authenticates(line, monkeypatch) -> None:
    """The other direction. This is an anchoring rule, not a ban on the phrase, and without this
    leg the unit would be satisfied by a classifier that never authenticates anything."""
    cli = CodexCli(executable="codex")
    monkeypatch.setattr(subprocess, "run",
                        lambda _a, **_k: subprocess.CompletedProcess(_a, 0, stdout=line + chr(10), stderr=""))
    authed, _detail = cli.login_status()
    assert authed is True


def test_the_negative_marker_list_STILL_gates_a_line_that_passes_the_anchor(monkeypatch) -> None:
    """The blacklist is now defence in depth rather than the primary gate, so its own reachability
    has to be proven separately -- otherwise the existing "Not logged in" test would be passing on
    the anchor alone and nothing would be exercising the list it claims to check."""
    cli = CodexCli(executable="codex")
    out = "Logged in as someone@example.com" + chr(10) + "warning: no login session is active" + chr(10)
    monkeypatch.setattr(subprocess, "run",
                        lambda _a, **_k: subprocess.CompletedProcess(_a, 0, stdout=out, stderr=""))
    authed, _detail = cli.login_status()
    assert authed is False


def test_a_nonzero_exit_is_never_authenticated_however_positive_the_text(monkeypatch) -> None:
    """Structured evidence outranks prose, which is this tier governing rule. A CLI that failed
    and still printed a positive-looking line is not evidence of a session."""
    cli = CodexCli(executable="codex")
    monkeypatch.setattr(subprocess, "run",
                        lambda _a, **_k: subprocess.CompletedProcess(_a, 1, stdout="Logged in using ChatGPT" + chr(10), stderr=""))
    authed, _detail = cli.login_status()
    assert authed is False

def test_login_status_detail_is_normalized_not_raw_pii(monkeypatch) -> None:
    """spec-audit MINOR-1: the recorded auth_detail is a CLASSIFIED state (+ method), NEVER the raw
    CLI line — so an account email some builds print ("Logged in as user@…") cannot land in an
    evidence-bound field. The method token survives; the raw line/email does not."""
    cli = CodexCli(executable="codex")

    def _fake(_a, **_k):
        return subprocess.CompletedProcess(
            _a, 0, stdout="", stderr="Logged in as secret.person@example.com using ChatGPT\n")

    monkeypatch.setattr(subprocess, "run", _fake)
    authed, detail = cli.login_status()
    assert authed is True
    assert "chatgpt" in detail.lower()                 # classified method preserved
    assert "@" not in detail and "example.com" not in detail  # raw email / line NOT echoed
    assert detail == "logged in (chatgpt)"


# ---- probe: absent CLI ⇒ fail-closed data, not an exception --------------------------------

def test_probe_reports_absent_when_cli_missing() -> None:
    class _Absent:
        executable = None

        def version(self) -> str:
            raise CodexUnavailable("not on PATH")

        def login_status(self) -> tuple[bool, str]:
            raise CodexUnavailable("not on PATH")

        def exec_help(self) -> str:
            raise CodexUnavailable("not on PATH")

    probe = probe_codex(_Absent())
    assert probe.present is False and probe.meets_minimum is False
    assert probe.authenticated is False
    # candidates still recorded even when absent (roster surfaces them as OWED, never silent)
    assert probe.candidate_models == CODEX_CANDIDATE_MODEL_REFS


# ---- version probe fails closed on a hung CLI ----------------------------------------------

def test_version_fails_closed_on_timeout() -> None:
    cli = CodexCli(executable="codex")

    def _hang(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="codex --version", timeout=1)

    orig = subprocess.run
    subprocess.run = _hang  # type: ignore[assignment]
    try:
        with pytest.raises(CodexUnavailable):
            cli.version()
    finally:
        subprocess.run = orig  # type: ignore[assignment]


# ---- §2.2: the probe never uses a credential-carrying flag ---------------------------------

def test_probe_never_builds_a_credential_carrying_command() -> None:
    """Defence-in-depth: the detection probe must never invoke the CLI's credential-input flags
    (`--with-api-key`/`--with-access-token`) nor `codex exec` (a live model call). We assert the
    real CLI's probe methods only ever spawn the benign metadata argv."""
    cli = CodexCli(executable="codex")
    seen: list[list[str]] = []

    def _spy(argv, **_k):
        seen.append(list(argv))
        # minimal valid outputs so each probe method returns
        text = "codex-cli 0.144.6" if argv[-1] == "--version" else (
            "Logged in using ChatGPT" if argv[-1] == "status" else "-m, --model <MODEL>")
        return subprocess.CompletedProcess(argv, 0, stdout=text, stderr="")

    orig = subprocess.run
    subprocess.run = _spy  # type: ignore[assignment]
    try:
        probe_codex(cli)
    finally:
        subprocess.run = orig  # type: ignore[assignment]
    flat = " ".join(tok for argv in seen for tok in argv).lower()
    assert seen, "probe made no calls"
    for forbidden in ("--with-api-key", "--with-access-token", "api_key", "--model"):
        assert forbidden not in flat, f"{forbidden} appeared in a detection probe command"
    # only the three benign metadata calls were made — in particular the ONLY `exec` call is the
    # structural `exec --help`, never a live `codex exec <prompt>` model call.
    tails = {tuple(argv[1:]) for argv in seen}
    assert tails == {("--version",), ("login", "status"), ("exec", "--help")}
