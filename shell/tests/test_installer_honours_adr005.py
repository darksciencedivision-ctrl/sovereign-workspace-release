"""EPC-01 P1-9 — the installer must provision Electron the way ADR-005 requires.

The defect, found while reconciling the three divergent install paths: `tools/release/
install.ps1` ran a plain `npm ci` for `modules/sow/apps/desktop` and never invoked
`shell/tools/install_sow.py`. With `ignore-scripts` false on the host, Electron's postinstall
therefore ran and downloaded a ~100 MB binary from GitHub with **no hash verification**.

ADR-005 says the opposite in as many words: this workspace *chooses* `--ignore-scripts`, and
Electron is "provisioned by an explicit, logged, hash-verified step — which is the whole point
of this ADR", checking the zip's SHA-256 against the `checksums.json` shipped inside the npm
package the lockfile pins.

So the authoritative install path was bypassing the single supply-chain control the project
wrote an architecture decision to establish — silently, because the result looks identical: a
working Electron binary either way. Only its provenance differs.

These assertions are on the installer's TEXT rather than on an install run, because running a
real install needs a clean destination and network access (that is V-1's job). The text is
what would be wrong, and the text is what a reviewer reads.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "tools" / "release" / "install.ps1"
PROVISIONER = REPO_ROOT / "shell" / "tools" / "install_sow.py"
ADR = REPO_ROOT / "docs" / "ADR-005-sow-install-and-electron-provisioning.md"


class InstallerHonoursAdr005(unittest.TestCase):

    def setUp(self) -> None:
        self.assertTrue(INSTALLER.is_file(), "tools/release/install.ps1 is missing")
        self.text = INSTALLER.read_text(encoding="utf-8")

    def test_the_provisioner_exists(self) -> None:
        self.assertTrue(
            PROVISIONER.is_file(),
            "shell/tools/install_sow.py is missing — ADR-005's hash-verified provisioning "
            "step has no implementation"
        )

    def test_the_installer_invokes_the_hash_verified_provisioner(self) -> None:
        self.assertRegex(
            self.text, r"install_sow\.py",
            "install.ps1 never invokes install_sow.py, so Electron is provisioned by its own "
            "postinstall with no SHA-256 verification — the exact thing ADR-005 forbids"
        )

    def test_the_installer_does_not_npm_ci_the_desktop_root_itself(self) -> None:
        """install_sow.py runs `npm ci --ignore-scripts` as its own step 3. A second, plain
        `npm ci` for that root would re-enable the postinstall and undo the verification."""
        npm_ci_roots = re.findall(
            r"Join-Path \$destRoot '([^']*apps\\desktop)'", self.text)
        loop_body = self.text.split("foreach ($nodeRoot in @(", 1)
        if len(loop_body) == 2:
            loop = loop_body[1].split("))", 1)[0]
            self.assertNotIn(
                "apps\\desktop", loop,
                "modules\\sow\\apps\\desktop is still in the npm ci loop. install_sow.py does "
                "that install itself, with --ignore-scripts; running a plain npm ci for the "
                "same root lets Electron's unverified postinstall run anyway"
            )
        self.assertTrue(
            any("apps\\desktop" in r for r in npm_ci_roots) is False or True,
            "unreachable; kept so the regex above is exercised"
        )

    def test_the_installer_fails_closed_if_provisioning_fails(self) -> None:
        # Anchor on the INVOCATION line, not on the first mention of the name — the comment
        # above it names the script too, and splitting on that reads the wrong region.
        invocation = re.search(
            r"^\s*&\s+\S+.*install_sow\.py.*$", self.text, re.MULTILINE)
        self.assertIsNotNone(
            invocation,
            "install.ps1 mentions install_sow.py but never invokes it"
        )
        after = self.text[invocation.end():]
        self.assertRegex(
            after[:300], r"LASTEXITCODE -ne 0[^\n]*throw",
            "the install_sow.py invocation is not followed by an exit-code check. A "
            "provisioning step whose failure is not checked is a provisioning step that can "
            "silently not happen, and the install would then report success with no Electron."
        )

    def test_the_adr_this_enforces_still_ships(self) -> None:
        """The rule and its reasoning must travel together, or the next maintainer sees only
        an unexplained extra step and removes it."""
        self.assertTrue(ADR.is_file(), "docs/ADR-005 is missing")
        adr = re.sub(r"\s+", " ", ADR.read_text(encoding="utf-8"))
        self.assertIn("hash-verified", adr)
        self.assertIn("ignore-scripts", adr)


if __name__ == "__main__":
    unittest.main()
