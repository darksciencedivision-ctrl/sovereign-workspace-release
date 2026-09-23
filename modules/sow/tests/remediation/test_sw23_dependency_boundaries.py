"""SW-23 - dependency advisory triage, made executable.

The full dated inventory + per-advisory disposition is in
`docs/security/dependency-advisory-triage-20260923.md`. These tests are the regression guard for
the two dispositions that code can enforce:

  * chromadb (4 advisories, no published fix): ACCEPTED behind a compensating boundary - the
    product uses ONLY a local embedded PersistentClient, never Chroma's server/HTTP/auth stack
    that every advisory requires. If a future change reintroduced server mode, this guard fails
    and forces a re-triage.
  * anyio (3 advisories, all fixed in 4.14.2): the sovereign locks are at/above the fix floor;
    the Debate pin (below the floor) is a documented, operator-gated bump - this test keeps the
    triage doc and the shipped lock in sync until that bump lands.
"""
from __future__ import annotations

import re
from pathlib import Path

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SOVEREIGN = RELEASE_ROOT / "modules" / "sovereign"
DEBATE = RELEASE_ROOT / "modules" / "debate"
TRIAGE_DOC = RELEASE_ROOT / "docs" / "security" / "dependency-advisory-triage-20260923.md"

ANYIO_FIX_FLOOR = (4, 14, 2)  # GHSA-3w57-8xmc-8v26 / -5p39-cfhj-2xmp / -82r6-8w77-94w6

# Server-mode markers that would take chromadb outside the local-PersistentClient boundary.
CHROMA_SERVER_MARKERS = ("HttpClient", "chroma_server", "chromadb.config", "fastapi", "chroma run")


def _iter_source(root: Path):
    for p in root.rglob("*.py"):
        if ".venv" in p.parts or "site-packages" in p.parts:
            continue
        yield p


def _pinned_version(lock_path: Path, package: str):
    text = lock_path.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(package)}==(\d+)\.(\d+)\.(\d+)", text, re.MULTILINE)
    return tuple(int(g) for g in m.groups()) if m else None


# -- chromadb compensating boundary --------------------------------------------------------------
def test_chromadb_used_only_as_local_persistentclient():
    """The mitigation for the 4 unfixable chromadb advisories is that no server is ever run."""
    uses_persistent = False
    offenders = []
    for path in _iter_source(SOVEREIGN):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "chromadb" not in text:
            continue
        if "PersistentClient" in text:
            uses_persistent = True
        for marker in CHROMA_SERVER_MARKERS:
            if marker in text:
                offenders.append(f"{path.relative_to(RELEASE_ROOT)}: {marker}")
    assert uses_persistent, "expected a local chromadb.PersistentClient in the sovereign source"
    assert not offenders, (
        "chromadb server-mode marker(s) found - the SW-23 compensating boundary "
        f"(local PersistentClient only) is broken, re-triage required: {offenders}")


# -- anyio fix floor -----------------------------------------------------------------------------
def test_sovereign_anyio_lock_meets_fix_floor():
    ver = _pinned_version(SOVEREIGN / "requirements.lock.txt", "anyio")
    assert ver is not None, "anyio not pinned in the sovereign lock"
    assert ver >= ANYIO_FIX_FLOOR, f"sovereign anyio {ver} is below the 4.14.2 fix floor (SW-23)"


def test_debate_anyio_bump_is_applied_or_documented():
    """Debate's anyio pin is below the fix floor until the operator-approved bump lands. Until
    then the triage doc must record it as pending, so doc and lock never silently diverge; once
    the lock is bumped to >=4.14.2 this passes on the version alone."""
    ver = _pinned_version(DEBATE / "requirements.lock.txt", "anyio")
    assert ver is not None, "anyio not pinned in the debate lock"
    if ver >= ANYIO_FIX_FLOOR:
        return  # bump applied
    doc = TRIAGE_DOC.read_text(encoding="utf-8")
    assert "debate" in doc.lower() and "4.14.2" in doc, (
        "debate anyio is below the fix floor but the triage doc does not record the pending bump")


# -- the dated deliverable exists ----------------------------------------------------------------
def test_triage_doc_exists_and_is_dated():
    assert TRIAGE_DOC.is_file(), f"SW-23 triage deliverable missing: {TRIAGE_DOC}"
    doc = TRIAGE_DOC.read_text(encoding="utf-8")
    assert "2026-09-23" in doc and "SW-23" in doc
