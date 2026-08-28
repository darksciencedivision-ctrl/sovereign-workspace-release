"""Mutation runner for the guards added while closing the Phase 18D amendment reviews.

Kept in the tree rather than run once and described, for the same reason as its siblings: a
mutation verdict asserted in a report is prose that cannot disagree with its value. Run it and the
nine verdicts reproduce. Each entry applies the mutation, runs one selector, records RED (a test
caught it) or GREEN (nothing did), restores the original bytes and verifies the restore is
BYTE-IDENTICAL by sha256; exit 1 if anything is GREEN or a restore diverges.

What it covers, and why each exists — every one is a finding from the two mandatory reviewers on
the amendment commit `c40c1e3`:

  * M1/M7 the vocabulary fence's two remaining soft spots: a hand-written enum literal in
    `registry.py` (the check now reads the PARSED source and covers all eleven members, not the
    four that happened never to appear in prose — validator MINOR-4) and a repopulated
    `ADAPTER_EXEMPTIONS`, the one path that widens the node vocabulary with no operator ruling and
    no manifest trace (spec-audit m-7);
  * M2 the U293 ordering fix reverted at a call site that had no red-able test — it was fixed at
    three sites and pinned at one, and the other two only misbehave on a platform whose case
    ordering differs (validator MINOR-1);
  * M3/M4/M6 the amendment ATTRIBUTION, which was asserted and never authenticated: an invented
    ruling id, the authentication removed entirely, and a recorded amendment silently re-labelled
    under a different ruling (spec-audit M-3/m-5);
  * M5 the two integrity hashes the manifest publishes, both previously falsifiable with `--check`
    staying green (validator NIT-1 / spec-audit m-4);
  * M8 a live surface describing U227 as still operator-reserved after OP-12.1 ruled it — the
    MAJOR-1 class, seven stale sites the work commit's "all nine places" claim had missed;
  * M9 the SHIPPED OWED block claiming a leg was performed, which passed all three suites because
    every test asserted against a synthetic fixture (validator MEDIUM-3).

Run from the repo root:  py -3.12 tools/mutation/_op18d_amendment_mutations.py
"""
from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PY = [sys.executable, "-m", "pytest", "-q", "-x"]

MUTATIONS = [
    # (label, file, old, new, test target)
    ("M1 registry re-declares two enum members as string constants",
     "control_plane/nodes/registry.py",
     "class RegistrationRefused(Exception):",
     '_LOCAL_IDS = ["claude_code", "mock"]\n\n\nclass RegistrationRefused(Exception):',
     "tests/unit/test_node_schema_amendment.py::test_the_vocabulary_is_read_from_the_schema_files_not_re_declared"),
    ("M2 U293 fix reverted at the MUTABLE_SETS collection site",
     "tools/manifest/compute_manifest.py",
     '        files = sorted_files(d, pattern)\n        mutable[key] = [describe(p) for p in files]',
     '        files = sorted(d.glob(pattern))\n        mutable[key] = [describe(p) for p in files]',
     "tests/unit/test_node_schema_amendment.py::test_every_glob_collection_site_uses_the_platform_independent_key"),
    ("M3 amendment cites a ruling nobody recorded",
     "tools/manifest/compute_manifest.py",
     '"schemas/node.schema@1.1.json": "OP-12.1 (operator, 2026-08-01)',
     '"schemas/node.schema@1.1.json": "OP-99.9 (operator, 2026-08-01)',
     "tests/unit/test_node_schema_amendment.py::test_the_manifest_is_reproducible_on_this_host"),
    ("M4 attribution authentication removed (any typed string counts again)",
     "tools/manifest/compute_manifest.py",
     "    ruling = match.group(1)\n    for source in RULING_SOURCES:",
     "    ruling = match.group(1)\n    return cited\n    for source in RULING_SOURCES:",
     "tests/unit/test_node_schema_amendment.py::test_an_amendment_citing_a_ruling_nobody_recorded_is_unattributed"),
    ("M5 --check stops verifying the published integrity hashes",
     "tools/manifest/compute_manifest.py",
     'if existing.get("freeze_integrity_sha256") != manifest["freeze_integrity_sha256"]:',
     'if False and existing.get("freeze_integrity_sha256") != manifest["freeze_integrity_sha256"]:',
     "tests/unit/test_node_schema_amendment.py::test_check_verifies_the_two_integrity_hashes_it_publishes"),
    ("M6 attribution drift no longer reported",
     "tools/manifest/compute_manifest.py",
     'elif old_attr.get(e["path"]) != e.get("authorized_by"):',
     'elif False and old_attr.get(e["path"]) != e.get("authorized_by"):',
     "tests/unit/test_node_schema_amendment.py::test_relabelling_a_recorded_amendment_under_another_ruling_is_drift"),
    ("M7 ADAPTER_EXEMPTIONS repopulated with an unruled id",
     "control_plane/nodes/registry.py",
     "ADAPTER_EXEMPTIONS: frozenset[str] = frozenset()",
     'ADAPTER_EXEMPTIONS: frozenset[str] = frozenset({"kimi_k3"})',
     "tests/unit/test_node_schema_amendment.py::test_the_exemption_list_is_empty_and_that_is_an_assertion_in_its_own_right"),
    # The payload below is a stale pre-OP-12.1 sentence ON PURPOSE - it is the thing the detector
    # must catch. Named here so this file, which is itself a live surface, states the ruling within
    # sight of the claim exactly as the rule requires of everything else.
    ("M8 a live surface says U227 is operator-reserved again",
     "control_plane/nodes/event_log.py",
     "import json",
     "# U227 is operator-reserved: no schema-valid node RECORD can name them.\nimport json",
     "tests/unit/test_u227_prose_is_not_stale.py::test_no_live_surface_claims_u227_is_still_unruled_without_naming_the_ruling"),
]

JS_MUTATION = (
    "M9 the shipped OWED block claims the node-record leg was performed",
    "apps/desktop/selfcheck/op12-acceptance-selfcheck.js",
)


def digest(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    rows = []
    for label, rel, old, new, target in MUTATIONS:
        path = ROOT / rel
        before = path.read_bytes()
        before_hash = digest(path)
        text = before.decode("utf-8")
        if old not in text:
            rows.append((label, "SKIPPED-ANCHOR-MISSING", ""))
            continue
        path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
        try:
            proc = subprocess.run(PY + [target], cwd=ROOT, capture_output=True, text=True)
            verdict = "RED" if proc.returncode != 0 else "GREEN (guard does not hold)"
        finally:
            path.write_bytes(before)
        rows.append((label, verdict, "restored" if digest(path) == before_hash else "RESTORE FAILED"))

    # the JS one, run against the desktop suite's new file
    label, rel = JS_MUTATION
    path = ROOT / rel
    before = path.read_bytes()
    before_hash = digest(path)
    text = before.decode("utf-8")
    start = text.index("  provider_node_record:")
    end = text.index("  antigravity_auth_state:")
    mutated = (text[:start]
               + '  provider_node_record:\n    "a Sovereign node record EXISTS for both providers '
                 'and the 18C legs are unblocked",\n'
               + text[end:])
    path.write_bytes(mutated.encode("utf-8"))
    try:
        proc = subprocess.run(["node", "--test", "test/op12-acceptance-owed-shipped.test.js"],
                              cwd=ROOT / "apps" / "desktop", capture_output=True, text=True)
        verdict = "RED" if proc.returncode != 0 else "GREEN (guard does not hold)"
    finally:
        path.write_bytes(before)
    rows.append((label, verdict, "restored" if digest(path) == before_hash else "RESTORE FAILED"))

    width = max(len(r[0]) for r in rows)
    for label, verdict, restore in rows:
        print(f"{label.ljust(width)}  {verdict:<26} {restore}")
    return 0 if all(r[1] == "RED" and r[2] == "restored" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
