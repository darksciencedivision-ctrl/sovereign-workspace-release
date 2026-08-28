"""The worktree's text bytes match their own blobs (U274, punch list 2.8 / W-26).

`.gitattributes` pins `* text=auto eol=lf`, and it cannot detect a tool that
writes CRLF after checkout. PowerShell 5.1's `Set-Content -Encoding UTF8` writes a
BOM and CRLF; Python's `write_text` translates \\n to \\r\\n on Windows. Either
leaves `git status` CLEAN — git normalises on comparison — while the bytes on disk
differ from the blob, which is how 33 tracked files came to carry CRLF and three
came to carry a BOM without anyone noticing.

That is the specific danger: this drift is INVISIBLE to `git status`, so only a
byte-level check finds it.
"""
from __future__ import annotations

import codecs
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: Excluded, and each one for a stated reason rather than because it was inconvenient.
EXCLUDED: dict[str, str] = {
    # A D-4 protected worktree entry: its ORIGINAL BASELINE BYTES must remain unchanged, which
    # outranks this hygiene rule. It is `w/mixed` and is deliberately left that way.
    "docs/loop/LOOP_STATE.json": "D-4 protected: original baseline bytes must not move",
}
#: `.gitattributes` marks this tree `-text`; git stores it verbatim and must not normalise it.
EXCLUDED_PREFIXES = ("docs/canonical/",)


def _eol_rows() -> list[tuple[str, str, str]]:
    out = subprocess.run(["git", "ls-files", "--eol"], cwd=REPO, capture_output=True,
                         text=True, check=True).stdout.splitlines()
    rows = []
    for line in out:
        # `i/lf    w/crlf  attr/text=auto eol=lf   <TAB>path`. The attr column CONTAINS SPACES, so
        # the path is delimited by the tab and only by the tab — splitting on whitespace puts the
        # path inside the attribute string and every exclusion silently stops matching.
        if "\t" not in line:
            continue
        head, _, rel = line.partition("\t")
        fields = head.split()
        if len(fields) < 2:
            continue
        rows.append((fields[0].removeprefix("i/"), fields[1].removeprefix("w/"), rel.strip()))
    return rows


def _in_scope(rel: str) -> bool:
    return rel not in EXCLUDED and not rel.startswith(EXCLUDED_PREFIXES)


def test_no_tracked_text_file_carries_a_utf8_BOM() -> None:
    """A BOM is CONTENT, not a line ending: it changes the blob and every hash taken over it."""
    offenders = []
    for _index_eol, _worktree_eol, rel in _eol_rows():
        if not _in_scope(rel):
            continue
        path = REPO / rel
        if not path.is_file():
            continue
        if path.read_bytes().startswith(codecs.BOM_UTF8):
            offenders.append(rel)
    assert not offenders, (
        "tracked files carry a UTF-8 BOM (PowerShell 5.1 `Set-Content -Encoding UTF8` writes one):\n  "
        + "\n  ".join(offenders))


def test_no_tracked_text_file_differs_from_its_blob_by_line_endings() -> None:
    """The check `git status` cannot make: it normalises on comparison, so a CRLF worktree against
    an LF blob reads CLEAN while the bytes differ."""
    offenders = [f"{rel}: blob i/{index_eol}, worktree w/{worktree_eol}"
                 for index_eol, worktree_eol, rel in _eol_rows()
                 if _in_scope(rel) and index_eol != worktree_eol]
    assert not offenders, (
        "worktree line endings differ from the committed blob — invisible to `git status`:\n  "
        + "\n  ".join(offenders))


@pytest.mark.parametrize("rel,reason", sorted(EXCLUDED.items()))
def test_every_exclusion_is_still_real_and_still_reasoned(rel: str, reason: str) -> None:
    """An exclusion for a file that no longer exists is a rule nobody is following."""
    assert (REPO / rel).is_file(), f"{rel} is excluded but is not in the tree"
    assert reason.strip(), f"{rel} is excluded with no reason"


def test_the_evidence_writers_pin_their_newline() -> None:
    """The sweep is undone by the next run of any writer that does not pin `newline`. These four
    were identified by tracing each one's OUTPUT to a file measured as CRLF, not by guessing."""
    writers = [
        "tools/benchmark/phase6_probe.py",
        "tools/live/real_parakeet_smoke.py",
        "tools/soak/phase2_soak.py",
        "tools/live/capture_claude_json_shape.py",
    ]
    unpinned = []
    for rel in writers:
        text = (REPO / rel).read_text(encoding="utf-8")
        if 'write_text(' in text and 'newline="\\n"' not in text:
            unpinned.append(rel)
    assert not unpinned, (
        "these writers would re-introduce CRLF on the next run:\n  " + "\n  ".join(unpinned))
