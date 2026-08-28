"""W-53 (R-38) — the TWO live execution paths decode provider bytes under ONE policy.

The canonical item: *"encoding policy diverges between `run_managed_process` and the recon runner,
covered by 0.3, add a test asserting one policy."* W-03/A-2 fixed the divergence causally; nothing
ever asserted the PARITY, so a future edit to either runner could reopen it silently.

THE POLICY, inherited from 0.3 and not restated by this file: provider subprocess decoding is pinned
to ``encoding="utf-8", errors="replace"`` so malformed bytes come back as a STRING rather than as
``None``. `text=True` alone resolves to the host ANSI codepage — cp1252 on this host — where an
undefined byte kills subprocess's reader THREAD, and subprocess SWALLOWS that exception. The call
then returns exit 0 with the whole transcript gone, which is the shape A-2 was repaired to prevent.

BEHAVIOURAL, NOT A SOURCE ASSERTION. Every test here spawns a REAL child that writes REAL bytes to
its stdout: ASCII, valid non-ASCII UTF-8 (Latin-1 accents and CJK), and a byte sequence that is not
valid UTF-8 at all. A source-text check would pass for a runner whose keyword arguments were right
and whose behaviour was not, and it would say nothing about the host codepage — which is the actual
mechanism.

WHAT THIS FILE DOES NOT CLAIM: it does not assert the MCP stdio path shares this policy. It
deliberately does not — W-04 pins that one to `strict`, because there the bytes become persisted
content with hashes computed over them. Two different jobs, two different correct answers.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from adapters.frontier import process_tree
from adapters.frontier.provider_cli_common import classify_provider_outcome
from tools.providers.frontier_provider_recon import subprocess_runner

#: The three classes of byte a provider CLI can emit, in one payload.
#:   * plain ASCII                        — must survive verbatim;
#:   * valid non-ASCII UTF-8              — must survive as the CHARACTERS, not as mojibake;
#:   * a lone 0xFF                        — not valid UTF-8 in any position, and undefined in
#:                                          cp1252 too, which is what kills the reader thread.
_ASCII = "ready"
_UNICODE = "café 会议记录"
_BAD = b"\xff\xfe"
_PAYLOAD = _ASCII.encode("ascii") + b" " + _UNICODE.encode("utf-8") + b" " + _BAD + b"\n"

#: A child that writes those exact BYTES to stdout and exits 0. Written through the buffer so no
#: encoder of ours stands between the test and the bytes under test.
_EMIT = (
    "import sys;"
    "sys.stdout.buffer.write(" + repr(_PAYLOAD) + ");"
    "sys.stdout.buffer.flush()"
)

_REPLACEMENT = "�"


def _emit_argv() -> list[str]:
    return [sys.executable, "-c", _EMIT]


def _via_recon_runner() -> str:
    rc, out, err, timed_out, spawn_error = subprocess_runner(timeout_s=60.0)(_emit_argv())
    assert spawn_error is None and timed_out is False, (spawn_error, timed_out)
    assert rc == 0, rc
    return out


def _via_managed_process() -> str:
    proc = process_tree.run_managed_process(
        _emit_argv(), timeout=60.0, env=None, stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.returncode
    return proc.stdout


# ---------------------------------------------------------------------------------------------
# 1. each path, on its own
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("reader", [_via_recon_runner, _via_managed_process],
                         ids=["recon_runner", "run_managed_process"])
def test_a_malformed_byte_yields_a_STRING_not_None_and_not_an_exception(reader) -> None:
    """The A-2 shape, stated as the property rather than as the fix. `None` here is the signature of
    a reader thread that died; an exception is the other way the same edit fails."""
    out = reader()
    assert isinstance(out, str)
    assert out is not None


@pytest.mark.parametrize("reader", [_via_recon_runner, _via_managed_process],
                         ids=["recon_runner", "run_managed_process"])
def test_valid_unicode_survives_and_the_malformed_bytes_are_REPLACED(reader) -> None:
    """Valid UTF-8 must come back as the CHARACTERS — not as cp1252 mojibake, which is what a
    host-codepage decode produces and which would still be a `str` and still pass the test above."""
    out = reader()
    assert _ASCII in out
    assert _UNICODE in out, "valid non-ASCII UTF-8 was not decoded as UTF-8"
    assert _REPLACEMENT in out, "the malformed bytes were not replaced"
    assert "Ã" not in out, "cp1252 mojibake — the host codepage decoded this, not UTF-8"


# ---------------------------------------------------------------------------------------------
# 2. the parity itself — the thing R-38 actually asks for
# ---------------------------------------------------------------------------------------------

def test_BOTH_live_execution_paths_return_the_SAME_TEXT_for_the_same_bytes() -> None:
    """ONE policy, asserted as agreement rather than as two separate correct answers.

    This is the assertion the canonical item names, and it is the one that keeps holding after
    somebody edits a single runner: two paths that are independently 'reasonable' can still
    disagree, which is the whole finding of W-49 and U458 in this programme."""
    assert _via_recon_runner() == _via_managed_process()


def test_the_shared_text_is_the_expected_decode_of_the_exact_bytes() -> None:
    """Agreement alone would be satisfied by two identically WRONG readers, so the shared answer is
    pinned to the decode the policy specifies."""
    expected = _PAYLOAD.decode("utf-8", errors="replace")
    assert _via_recon_runner() == expected
    assert _via_managed_process() == expected


# ---------------------------------------------------------------------------------------------
# 3. the other half inherited from 0.3 — exit 0 with nothing readable is NOT success
# ---------------------------------------------------------------------------------------------

def test_exit_zero_with_no_READABLE_stream_is_not_a_successful_provider_result() -> None:
    """Not strictly encoding parity, but it is the CONSEQUENCE A-2 was repaired to prevent: when the
    codec was unpinned the reader thread died, subprocess swallowed it, and the call returned exit 0
    with `stdout is None`. If that classifies SUCCESS, a provider that said nothing publishes a
    candidate no model wrote.

    Note the distinction the classifier keeps: `None` is the ABSENCE of a stream and fails closed;
    `""` is a command that genuinely said nothing and still classifies SUCCESS, because demoting it
    would redefine success for every quiet zero-exit command in the tree."""
    assert classify_provider_outcome(0, None, "").outcome != "SUCCESS"
    assert classify_provider_outcome(0, "", "").outcome == "SUCCESS"
