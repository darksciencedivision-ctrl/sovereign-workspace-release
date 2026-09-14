"""EPC-01 P3-2 - the developer identifiers left in the distribution are a CLOSED set.

`test_no_developer_paths_ship.py` guards the seven operator-facing documents, which must
carry none at all. This guards the rest of the archive, where the answer is not zero and
saying so is the point.

What was fixed rather than disclosed:

  * `shell/config/install.json` and all five module adapters carried this machine's tree and
    interpreter. They now carry ${install_root} and ${python312} (P3-4/P3-5).
  * `shell/src/distillery.py` hardcoded two of the operator's directories in product code.
    They are environment variables with no default.
  * `SBOM.json` recorded absolute build-host paths in its lock provenance.
  * The build harness at the repository root - the agent envelopes and the three
    Start-*.ps1 launchers - no longer ships at all, nor do three uncited build records.

What remains, and why it is not a bug that can be quietly closed:

  * **Provenance records** (`INSTALL-PROVENANCE.json`, the SWS-UI-001 addenda, DISCOVERY,
    THEME-BASELINE) record where each vendored module CAME FROM. The path is the content.
    Scrubbing it would not remove information, it would make the record false.
  * **Module evidence trees.** 25 of the 28 flagged files under `modules/*/docs/evidence`
    and `modules/*/runs` are cited by something a recipient runs - `test_evidence_receipts.py`,
    `run_phase19_gate.py`, the desktop selfcheck scripts, the decision registers. Cutting
    them would trade a disclosure for a broken verification path. The three cited by nothing
    were cut.
  * **`BUILD-DIRECTIVE-SWS-UI-001.md`** is served by the shell (`server.py` doc route) and
    linked by README, so it cannot be cut. The operator granted a waiver for it (ENTRY 027),
    and it is STILL not edited here: precedence rule 1 says the contract is "amended only by
    a versioned successor the operator issues; never by chat", which names the mechanism, not
    just the authority. Deciding a contract edit is too small to need the contract's own
    amendment route is the first step of what that rule exists to prevent.

`docs/DECISIONS.md` was on this list and is not any more. The same waiver covered it, the
builder envelope's restriction on it ("read and hash only") is one the operator controls, and
the two machine paths in it were replaced with a neutral form.

So this test does not assert zero. It pins the set, so that the number can only go down
without someone editing this file and saying why.
"""
from __future__ import annotations

import io
import re
import subprocess
import tarfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PATTERNS = {
    "username": re.compile(rb"Sslaw", re.I),
    "product-software-tree": re.compile(rb"Product[ _]Software", re.I),
    "sov-1-tree": re.compile(rb"Sov 1", re.I),
    "user-home": re.compile(rb"C:\\+Users\\+[A-Za-z0-9_.-]+", re.I),
    "build-tree": re.compile(rb"producttion software", re.I),
}

#: Files allowed to carry an identifier, each with the reason it is not simply fixed.
#: A file not on this list failing the test is a REGRESSION, not a reason to extend the list.
DISCLOSED = {
    # Served by the shell and linked by README; builder may not edit it. Parked.
    "BUILD-DIRECTIVE-SWS-UI-001.md": "parked: shell serves it, builder may not edit it",
    # docs/DECISIONS.md was here. The operator granted a waiver naming it (ENTRY 027) and the
    # two machine paths were replaced with a neutral form, so it no longer needs disclosing.
    # Removed deliberately rather than left to rot - see the stale-entry test below.
    # Release integrity records, generated from the tree they describe.
    "RELEASE-MANIFEST.json": "release integrity record",
    # Provenance: the path IS the record.
    "modules/debate/INSTALL-PROVENANCE.json": "provenance",
    "modules/debate/INSTALL-PROVENANCE.previous.json": "provenance",
    "modules/distillery/INSTALL-PROVENANCE.json": "provenance",
    "modules/distillery/INSTALL-PROVENANCE.json.previous": "provenance",
    "modules/sovereign/INSTALL-PROVENANCE.json": "provenance",
    "modules/sovereign/INSTALL-PROVENANCE.previous.json": "provenance",
    # modules/sow/INSTALL-PROVENANCE.json was here; P1 Package G (F-072/F-073) regenerated it into
    # a form that no longer carries a developer identifier, so the disclosure is removed rather than
    # left to rot (the stale-entry test forbids keeping it).
    "modules/sow/.codex/config.toml": "rebased at install; absolute cwd is deliberate (P1-8)",
    "docs/DISCOVERY.md": "provenance: records where each module came from",
    "docs/THEME-BASELINE.md": "provenance",
    "docs/SWS-UI-001-v1.2-ADDENDUM-01.md": "provenance",
    "docs/SWS-UI-001-v1.2-ADDENDUM-02.md": "provenance",
    "docs/SWS-UI-001-v1.2-ADDENDUM-08.md": "provenance",
    "modules/distillery/registry/instrumentation_checksums.json": "provenance",
    "modules/debate/snapshot/PORTABILITY.md": "provenance",
    "modules/sow/docs/canonical/Claude_Code_Buildout_Directive_20260716.md": "provenance",
    # Tooling whose subject IS the old tree.
    "tools/release/rebase_adapters.py": "OLD_ROOT is the legacy prefix it rebases FROM",
    "tools/release/test_rebase_adapters.py": "fixture for the above",
    "tools/release/test_rebase_leaves_variables_alone.py": "fixture for the above",
    "tools/release/module_source_registry.json": "records each module's source of record",
    "tools/release/generate_module_provenance.py": "writes the provenance records",
    "shell/tests/_fswatch.py": "names the protected roots it exists to watch (H-12)",
    "shell/tests/test_paths.py": "asserts the protected roots are not written",
    "shell/tests/test_no_developer_paths_ship.py": "the needles ARE the test",
    "shell/tests/test_developer_identifiers_are_bounded.py": "this file",
    "modules/sow/apps/desktop/test/renderer-spec-allowlist.test.js": "fixture path in a test",
    "modules/distillery/tests/test_corpus_admission.py": "fixture path in a test",
    # SW-JOURNAL-002-A3 F-47. These two prove the journal REDACTS a user-profile path. The
    # needle has to have that exact shape to be a proof; a neutral drive path would test a
    # weaker claim than the one the redactor makes.
    "modules/sow/apps/desktop/test/journal-redaction-a3.test.js": "the redacted needle IS the test",
    "modules/sow/apps/desktop/test/workspace-journal.test.js": "the redacted needle IS the test",
    # F-22/F-23. The defect these document and test is a COLLISION BETWEEN TWO REAL TREE NAMES on
    # this operator's disk: one is a character-prefix of the other, so a `startswith` containment
    # test placed a whole product tree inside an unrelated directory. Replacing the names with
    # neutral ones would leave a comment that no longer explains anything and a test that no
    # longer reproduces the collision it exists for.
    "modules/sow/control_plane/conductor/registry.py": "the prefix collision it fixes is between two real tree names",
    "modules/sow/tests/unit/test_conductor_workspace_containment.py": "reproduces that collision",
    "modules/sow/tests/unit/test_worktree_foreign_registration.py": "reproduces that collision",
}

#: Evidence trees whose contents are cited by things a recipient runs. Disclosed wholesale,
#: with the reason, rather than enumerated file by file - the list would be noise.
DISCLOSED_TREES = (
    "modules/sow/docs/evidence/",
    "modules/sow/docs/loop/",
    "modules/sow/docs/registers/",
    "modules/sow/tools/soak/results/",
    "modules/distillery/runs/",
)


def _distribution() -> dict[str, bytes]:
    """Exactly what `git archive` ships, which is not what the working tree holds."""
    blob = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "archive", "--format=tar", "HEAD"],
        capture_output=True, check=True,
    ).stdout
    contents: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            stream = archive.extractfile(member)
            if stream is not None:
                contents[member.name] = stream.read()
    return contents


class DeveloperIdentifiersAreBounded(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.files = _distribution()

    def test_the_archive_was_actually_read(self) -> None:
        """A silent pass over an empty archive would make everything below worthless."""
        self.assertGreater(len(self.files), 1000, "the distribution looks empty")

    def _offenders(self) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        for name, data in self.files.items():
            if name in DISCLOSED or name.startswith(DISCLOSED_TREES):
                continue
            labels = [label for label, pattern in PATTERNS.items() if pattern.search(data)]
            if labels:
                found[name] = labels
        return found

    def test_no_undisclosed_file_carries_a_developer_identifier(self) -> None:
        offenders = self._offenders()
        self.assertEqual(
            offenders, {},
            "files in the distribution carry a developer identifier and are not on the "
            "disclosed list. Fix the file - do NOT add it here unless you can say, in the "
            "entry itself, why it cannot be fixed:\n  "
            + "\n  ".join(f"{k}: {', '.join(v)}" for k, v in sorted(offenders.items()))
        )

    def test_the_build_harness_does_not_ship(self) -> None:
        """X-6. These are the builder's running instructions, not a recipient's documents."""
        for name in ("AGENTS.md", "CLAUDE.md", "Start-OpenCode.ps1",
                     "Start-OpenCode-FullAccess.ps1", "Start-Loop-Resume.ps1",
                     "docs/GATE5-REPORT.md", "docs/SOVEREIGN_CANONICAL_HANDOFF_20260827.md"):
            self.assertNotIn(name, self.files, f"{name} is build-harness and must not ship")

    def test_the_product_code_that_was_fixed_stays_fixed(self) -> None:
        """The four files P3-2/P3-4/P3-5 actually repaired. A regression here is a
        regression in the product, not in the disclosure."""
        for name in ("shell/config/install.json", "shell/src/distillery.py",
                     "shell/modules/sovereign.json", "shell/modules/tokencenter.json",
                     "shell/modules/distillery.json", "shell/modules/debate.json",
                     "shell/modules/sow.json", "SBOM.json"):
            self.assertIn(name, self.files, f"{name} unexpectedly absent from the archive")
            data = self.files[name]
            hits = [label for label, pattern in PATTERNS.items() if pattern.search(data)]
            self.assertEqual(hits, [], f"{name} has regressed and names the build machine: {hits}")

    def test_every_disclosed_entry_still_exists_and_still_needs_disclosing(self) -> None:
        """A disclosure list that outlives its entries stops describing anything. An entry
        for a file that no longer carries an identifier is a fix nobody recorded."""
        stale = []
        for name in DISCLOSED:
            if name not in self.files:
                continue  # not shipped (e.g. this test file's own tree) - covered elsewhere
            data = self.files[name]
            if not any(pattern.search(data) for pattern in PATTERNS.values()):
                stale.append(name)
        self.assertEqual(
            stale, [],
            "these files no longer carry an identifier and should be removed from the "
            f"disclosed list: {stale}"
        )


if __name__ == "__main__":
    unittest.main()
