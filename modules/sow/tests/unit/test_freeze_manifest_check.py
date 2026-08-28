"""The freeze check is RUN, and its coverage is PROVED (punch list 2.3 / W-20).

Operator ruling D-1: classify by PROVENANCE, not by directory. The tracked,
manifest-bound `.claude/**` files — `agents/gate-validator.md`,
`agents/spec-auditor.md`, `hooks/guard.py`, `settings.json` — are product /
frozen-set content. Ephemeral session caches, conversations, auth material and
runtime scratch stay excluded.

MEASURED CORRECTION to the directive's red-run premise. It states the check
"exits 1 today: four `.claude/**` files removed, freeze integrity hash mismatch".
On this tree it exits **0**, all four files are tracked and present, and all four
are already in the frozen set — which is what the review's R-20 narrowing said
(the failure is package-only, not live-tree).

So a test that merely asserts "the check passes" would be green on first contact
and prove nothing. What is falsifiable, and what this file pins instead, is
COVERAGE: perturbing a frozen file's recorded hash MUST move
`freeze_integrity_sha256`. If any of the four were reclassified as mutable — the
directory-based reading D-1 rejects — the perturbation would stop moving that
hash and these tests go red.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.manifest import compute_manifest as mod  # noqa: E402

#: The provenance-bound files D-1 names. Product content, not session scratch.
D1_FROZEN_CLAUDE_FILES = (
    ".claude/agents/gate-validator.md",
    ".claude/agents/spec-auditor.md",
    ".claude/hooks/guard.py",
    ".claude/settings.json",
)


#: Keys `build_manifest` adds AFTER computing the freeze hash, and therefore deliberately outside
#: it: an amendment or a register append must never be able to move the number the operator's
#: signature binds (U222). Excluding them here is what makes this a reproduction of the real
#: payload rule rather than an approximation of it.
_ADDED_AFTER_THE_HASH = ("freeze_integrity_sha256", "schema_amendments",
                         "mutable_audit_files", "operator_signature")


def _integrity_of(core: dict) -> str:
    """Recompute the freeze hash exactly as `build_manifest` does."""
    body = {k: v for k, v in core.items() if k not in _ADDED_AFTER_THE_HASH}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest().upper()


def _entry(core: dict, rel_path: str) -> dict:
    for group in core["contents"].values():
        for entry in group:
            if entry.get("path") == rel_path:
                return entry
    raise AssertionError(f"{rel_path} is in no group of the manifest's `contents`")


def test_the_freeze_check_passes_on_this_tree() -> None:
    """The green half. Recorded as the state of THIS host, not as a cross-platform claim."""
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "manifest" / "compute_manifest.py"), "--check"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    assert proc.returncode == 0, (
        f"freeze check exited {proc.returncode}\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    assert "freeze check OK" in proc.stdout


@pytest.mark.parametrize("rel_path", D1_FROZEN_CLAUDE_FILES)
def test_each_D1_provenance_bound_file_is_inside_the_freeze_integrity_hash(rel_path: str) -> None:
    """D-1 made executable, and falsifiable. Perturbing the recorded hash of one of these files
    must MOVE `freeze_integrity_sha256`; if it does not, the file is outside the envelope the
    operator's signature binds — which is the directory-based classification D-1 rejects."""
    core = mod.build_manifest()
    baseline = core["freeze_integrity_sha256"]
    assert baseline == _integrity_of(core), (
        "the payload rule reproduced here no longer matches build_manifest()")

    perturbed = copy.deepcopy(core)
    entry = _entry(perturbed, rel_path)
    entry["sha256"] = "0" * 64
    assert _integrity_of(perturbed) != baseline, (
        f"{rel_path} is NOT covered by freeze_integrity_sha256: its hash can change without "
        f"moving the number the operator's signature binds")


@pytest.mark.parametrize("rel_path", D1_FROZEN_CLAUDE_FILES)
def test_each_D1_provenance_bound_file_is_tracked_and_present(rel_path: str) -> None:
    """A frozen-set entry that is untracked is a claim about a file the repository does not
    carry — the packaged-candidate failure R-20 narrows to."""
    assert (REPO / rel_path).is_file(), f"{rel_path} is missing from the tree"
    proc = subprocess.run(["git", "ls-files", "--error-unmatch", rel_path],
                          cwd=REPO, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"{rel_path} is present but NOT git-tracked"


def test_the_coverage_check_goes_RED_if_a_D1_file_is_reclassified(monkeypatch) -> None:
    """RED-BEFORE-GREEN, committed rather than narrated.

    The directive's stated red run ("the check exits 1: four `.claude/**` files removed") does not
    reproduce on this tree — it exits 0, and all four files are tracked, present and already
    frozen, which is the review's R-20 narrowing. So the calibration is done against the failure
    that IS reachable: reclassifying one of these files out of the frozen set, which is exactly the
    directory-based reading operator ruling D-1 rejects.

    Without this, every assertion above would be green on first contact and would prove nothing.
    """
    monkeypatch.setattr(mod, "EXTRA",
                        [p for p in mod.EXTRA if p != ".claude/settings.json"])
    core = mod.build_manifest()
    with pytest.raises(AssertionError, match="is in no group"):
        _entry(core, ".claude/settings.json")
    # …and with it gone from `contents`, perturbing it cannot move the freeze hash at all — which
    # is the property the coverage test asserts, now shown failing on demand.
    assert _integrity_of(core) == core["freeze_integrity_sha256"]


def test_a_mutable_file_is_deliberately_OUTSIDE_the_freeze_hash() -> None:
    """The other direction, so the test above cannot pass by the envelope covering everything.
    Registers and evidence are append-only and change at every gate; a freeze that broke on every
    legitimate append would make the signature meaningless."""
    core = mod.build_manifest()
    baseline = core["freeze_integrity_sha256"]
    perturbed = copy.deepcopy(core)
    registers = perturbed["mutable_audit_files"]["registers"]
    assert registers, "the mutable register set is empty — this test would prove nothing"
    registers[0]["sha256"] = "0" * 64
    assert _integrity_of(perturbed) == baseline, (
        "a mutable audit file moved freeze_integrity_sha256 — every register append would then "
        "invalidate the operator's signature (U222)")
