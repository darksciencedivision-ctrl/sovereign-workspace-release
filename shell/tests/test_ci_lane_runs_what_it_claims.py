"""EPC-01 P1-6 - the CI lane must invoke the same script a developer runs.

There was no continuous integration of any kind. The obvious fix is a workflow file listing
the steps, and it is the wrong one: a lane that inlines its own list drifts from what anyone
runs locally, and the drift is discovered when the lane goes green on a tree that is broken.

So `tools/ci/run_ci.ps1` holds every stage, `.github/workflows/windows.yml` invokes it and
does almost nothing else, and these tests hold that arrangement in place. They check the
lane's WIRING - that it calls the script, on Windows, with history the gates need. They do not
re-run the suite; the script's own local execution is the evidence that the stages pass.
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "ci" / "run_ci.ps1"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "windows.yml"


class CiLaneRunsWhatItClaims(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.script = SCRIPT.read_text(encoding="utf-8") if SCRIPT.is_file() else ""
        cls.workflow = WORKFLOW.read_text(encoding="utf-8") if WORKFLOW.is_file() else ""

    def test_both_files_exist(self) -> None:
        self.assertTrue(SCRIPT.is_file(), "tools/ci/run_ci.ps1 is missing")
        self.assertTrue(WORKFLOW.is_file(), ".github/workflows/windows.yml is missing")

    def test_the_lane_invokes_the_script_rather_than_repeating_it(self) -> None:
        """The whole design. If the workflow grows its own gate list, this fails."""
        self.assertIn("tools/ci/run_ci.ps1", self.workflow,
                      "the workflow does not invoke tools/ci/run_ci.ps1")

    def test_the_lane_does_not_reimplement_the_gates(self) -> None:
        """A gate named directly in the workflow is a gate that can drift out of the script."""
        strays = [
            name for name in (
                "release_manifest_check.py", "check_model_consistency.py",
                "check_governance_bom.py", "package_boundary_gate.py",
            )
            if name in self.workflow
        ]
        self.assertEqual(
            strays, [],
            f"the workflow calls these directly instead of through run_ci.ps1: {strays}"
        )

    def test_the_script_runs_every_release_gate(self) -> None:
        missing = [
            name for name in (
                "release_manifest_check.py", "check_model_consistency.py",
                "check_governance_bom.py", "check_node_advisories.py",
                "package_boundary_gate.py", "generate_sbom.py", "generate_notice.py",
            )
            if name not in self.script
        ]
        self.assertEqual(missing, [], f"run_ci.ps1 does not run: {missing}")

    def test_the_script_runs_the_whole_product_suite_from_the_repo_root(self) -> None:
        """Several defects appear ONLY in the whole-product run, because that is the only
        invocation where the modules share a process and a PYTHONPATH."""
        self.assertRegex(self.script, r"Push-Location \$repoRoot")
        self.assertIn("'-m', 'pytest'", self.script)

    def test_the_boundary_gate_scans_the_distribution_not_the_working_tree(self) -> None:
        """Scanning a working tree full of .venv and node_modules produced 20,093 meaningless
        violations. --from-commit is what makes the number mean something."""
        self.assertIn("'--from-commit', 'HEAD'", self.script)

    def test_the_script_runs_both_node_suites_and_the_typecheck(self) -> None:
        for fragment in ("modules\\sow\\apps\\desktop", "modules\\sovereign\\ui\\ui_shell",
                         "typecheck"):
            self.assertIn(fragment, self.script, f"run_ci.ps1 omits {fragment}")

    def test_the_clean_room_is_defined_even_though_it_is_opt_in(self) -> None:
        """V-1. It installs packages, so it is off by default - but it must exist in the
        script rather than living only in someone's memory."""
        self.assertIn("IncludeCleanRoom", self.script)
        self.assertIn("install.ps1", self.script)
        self.assertIn("verify_install.ps1", self.script)

    def test_a_skipped_stage_is_reported_not_silent(self) -> None:
        """A suite that quietly does less than it claims is worse than one that does less
        loudly - a green run would otherwise vouch for stages that never executed."""
        self.assertIn("SKIPPED-WITH-RECORD", self.script)

    def test_a_failing_stage_fails_the_run(self) -> None:
        self.assertIn("exit 1", self.script)

    def test_it_does_not_stop_at_the_first_failure(self) -> None:
        """Stopping early hides the other stages, and the first failure is rarely the only
        one worth seeing in a CI report."""
        self.assertIn("$ErrorActionPreference = 'Continue'", self.script)

    def test_the_lane_runs_on_windows(self) -> None:
        """The product is Windows-only and several guarantees are Windows-specific: Job
        Object containment, ConPTY, GetFinalPathNameByHandleW. A Linux runner would exercise
        none of them."""
        self.assertIn("runs-on: windows-latest", self.workflow)
        self.assertNotIn("ubuntu-latest", self.workflow)

    def test_the_lane_checks_out_enough_history_for_the_gates(self) -> None:
        """package_boundary_gate --from-commit and the archive-reading guards need real
        history. A shallow checkout would make them pass by reading nothing."""
        self.assertIn("fetch-depth: 0", self.workflow)

    def test_the_lane_installs_python_dependencies_from_the_locks(self) -> None:
        """The SBOM is generated from these same files. A lane that resolved freshly would
        be testing a different dependency set than the release describes."""
        self.assertIn("requirements.txt", self.workflow)
        self.assertIn("npm ci", self.workflow)

    def test_the_script_is_ascii_and_parses(self) -> None:
        """PowerShell 5.1 reads a BOM-less .ps1 as ANSI, so one non-ASCII character in a
        string is a parse failure at a misleading line number."""
        raw = SCRIPT.read_bytes()
        self.assertTrue(all(b < 128 for b in raw), "run_ci.ps1 contains non-ASCII bytes")
        probe = (
            "$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
            f"'{SCRIPT}',[ref]$null,[ref]$e); if($e){{exit 1}}; exit 0"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", probe],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0, "run_ci.ps1 does not parse:\n" + result.stdout)


if __name__ == "__main__":
    unittest.main()
