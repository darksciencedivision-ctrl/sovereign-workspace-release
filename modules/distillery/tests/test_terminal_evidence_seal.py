from __future__ import annotations

"""Terminal evidence-seal contract tests.

Mechanically enforce that reconciliation findings R-01..R-04 stay closed:
exact F-item coverage with terminal dispositions, substantive F-23 closure,
complete EVIDENCE_INDEX coverage for every CLOSED software item (fail closed
on missing references), coherent LOOP_STATE terminal identity semantics that
never self-assert future containing commits, and BUILD_COMPLETION_MANIFEST
certification rules (strict identity block once schema v2 is present).
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEAL_DIR = ROOT / "runs" / "completion-loop"
IMPLEMENTATION_SEAL_COMMIT = "cb26214128d61c0d52e3d00d9067bc90ebc4cb47"
SOFTWARE_IDS = [f"F-{n:02d}" for n in range(26)]
EXTERNAL_IDS = [f"F-{n:02d}" for n in range(26, 31)]
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _load(name: str) -> dict:
    return json.loads((SEAL_DIR / name).read_text(encoding="utf-8"))


class PunchListTerminalMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.punch = _load("PUNCH_LIST.json")

    def test_exact_id_coverage_no_missing_no_duplicates(self) -> None:
        ids = [row["id"] for row in self.punch["items"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate punch ids present")
        self.assertEqual(set(ids), set(SOFTWARE_IDS) | set(EXTERNAL_IDS))

    def test_software_items_all_closed(self) -> None:
        status = {row["id"]: row["status"] for row in self.punch["items"]}
        self.assertEqual({k: status[k] for k in SOFTWARE_IDS}, {k: "CLOSED" for k in SOFTWARE_IDS})

    def test_external_items_deferred(self) -> None:
        status = {row["id"]: row["status"] for row in self.punch["items"]}
        self.assertEqual({k: status[k] for k in EXTERNAL_IDS}, {k: "DEFERRED_EXTERNAL" for k in EXTERNAL_IDS})

    def test_terminal_items_carry_substantive_records(self) -> None:
        for row in self.punch["items"]:
            with self.subTest(item=row["id"]):
                if row["id"] in SOFTWARE_IDS:
                    self.assertEqual(row["status"], "CLOSED")
                    self.assertTrue(row.get("disposition"), "closed item missing disposition")
                    self.assertTrue(
                        row.get("implementation_commits") or row.get("evidence_refs"),
                        "closed item lacks implementation/evidence reference",
                    )
                else:
                    self.assertEqual(row["status"], "DEFERRED_EXTERNAL")
                    self.assertFalse(row.get("blockers"), "external blocker item must be unblocked locally")

    def test_f23_closure_is_substantive_not_status_only(self) -> None:
        row = next(row for row in self.punch["items"] if row["id"] == "F-23")
        self.assertEqual(row["status"], "CLOSED")
        self.assertIn("1a02c06", row.get("implementation_commits", []))
        self.assertIn("runs/completion-loop/BUILD_COMPLETION_MANIFEST.json", row.get("evidence_refs", []))
        self.assertTrue((ROOT / "tools" / "build_completion_manifest.py").is_file())
        self.assertTrue((SEAL_DIR / "BUILD_COMPLETION_MANIFEST.json").is_file())


class EvidenceIndexCoverageTests(unittest.TestCase):
    @staticmethod
    def _references(entry: dict) -> list:
        refs = []
        for key in ("code", "tests", "reports", "hashes", "commits", "commands"):
            refs.extend(entry.get(key) or [])
        return refs

    def test_every_closed_software_item_has_references(self) -> None:
        requirements = _load("EVIDENCE_INDEX.json")["requirements"]
        for item_id in SOFTWARE_IDS:
            with self.subTest(item=item_id):
                self.assertIn(item_id, requirements, "missing evidence-index entry")
                self.assertTrue(self._references(requirements[item_id]), "empty evidence record")

    def test_local_path_references_resolve(self) -> None:
        requirements = _load("EVIDENCE_INDEX.json")["requirements"]
        for item_id, entry in requirements.items():
            for key in ("code", "tests", "reports"):
                for target in entry.get(key) or []:
                    looks_remote_or_command = (
                        "://" in target
                        or target.startswith(("python", "git ", "gh ", "cold ", "python -m"))
                    )
                    if not looks_remote_or_command and (target.endswith(".py") or target.startswith(("runs/", "docs/", "schema/"))):
                        with self.subTest(item=item_id, target=target):
                            self.assertTrue((ROOT / target).is_file(), "reference does not resolve")


class LoopStateTerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.state = _load("LOOP_STATE.json")

    def test_phase_and_terminal_counters(self) -> None:
        self.assertEqual(self.state["current_phase"], "TERMINAL")
        self.assertIsNone(self.state["current_work_item"])
        self.assertEqual(self.state["last_successful_item"], "F-25")
        self.assertEqual(self.state["terminal_disposition"], "BUILD_COMPLETE_EXPERIMENT_PENDING")
        self.assertEqual(self.state["open_critical_findings"], 0)
        self.assertEqual(self.state["open_high_findings"], 0)
        self.assertEqual(self.state["authority_conflicts_open"], 0)

    def test_identity_semantics_never_self_assert_future_commits(self) -> None:
        self.assertEqual(self.state["implementation_seal_commit"], IMPLEMENTATION_SEAL_COMMIT)
        for key in ("evidence_commit", "verified_branch_head"):
            value = self.state.get(key)
            self.assertTrue(value is None or HEX40.match(value), f"{key} must be unbound or a real sha")
        semantics_blob = json.dumps(self.state).upper()
        self.assertIn("UNBOUND", semantics_blob)

    def test_external_blockers_recorded(self) -> None:
        blockers = " | ".join(str(b) for b in self.state.get("external_blockers", [])).lower()
        for token in ("d-9", "trainer", "hg-3", "g2-g6", "promotion"):
            self.assertIn(token, blockers, f"missing external blocker token: {token}")

    def test_last_full_regression_shape(self) -> None:
        regression = self.state["last_full_regression"]
        self.assertEqual(regression["exit_code"], 0)
        self.assertRegex(regression["result"], r"^\d+ passed, \d+ subtests passed$")
        self.assertIsNotNone(regression.get("measured_at_commit"))
        self.assertTrue(HEX40.match(regression["measured_at_commit"] or ""), "measurement locus must be a full 40-hex sha")


class ManifestCertificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = _load("BUILD_COMPLETION_MANIFEST.json")

    def test_common_invariants_hold_for_any_schema_generation(self) -> None:
        m = self.manifest
        self.assertEqual(m["kind"], "BUILD_COMPLETION_MANIFEST")
        self.assertEqual(m["final_disposition"], "BUILD_COMPLETE_EXPERIMENT_PENDING")
        self.assertFalse(m["model_compute_performed"])
        self.assertFalse(m["promotion_performed"])
        self.assertFalse(m["deployment_performed"])
        self.assertGreaterEqual(len(m["external_blockers"]), 5)
        self.assertTrue(all(state == "NOT_EXECUTED" for state in m["g_states"].values()))
        self.assertEqual(m["hg_states"]["HG-3"], "BLOCKED_HARDWARE_CAPACITY")

    def test_v2_identity_block_strict(self) -> None:
        m = self.manifest
        if m.get("manifest_schema_version") != "2.0":
            self.skipTest("manifest not yet regenerated under schema v2")
        self.assertEqual(m["implementation_seal_commit"], IMPLEMENTATION_SEAL_COMMIT)
        self.assertIsNone(m["artifact_generation_commit"])
        for key in ("evidence_generation_base", "artifact_source_commit", "test_result_commit"):
            self.assertTrue(HEX40.match(m[key] or ""), f"{key} must be a real commit sha on a clean tree")
        self.assertIsNone(m["verified_branch_head"])
        self.assertIn("NOT required to equal", m["certification_rule"])
        self.assertRegex(
            m["test_matrix"]["measured_at_commit"] or "", r"^[0-9a-f]{40}$",
            "measurement locus must be a real commit sha",
        )
        self.assertEqual(m["audit_results"]["software_items_not_closed"], [])
        for value in m["artifact_hashes"].values():
            self.assertTrue(value is None or HEX64.match(value), f"artifact hash malformed: {value}")
        parsed = datetime.fromisoformat(m["manifest_generated_at"].replace("Z", "+00:00"))
        self.assertIsNotNone(parsed.tzinfo)

    def _locus_git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)

    def test_regression_locus_is_ancestor_of_head_with_evidence_only_delta(self) -> None:
        from tools.build_completion_manifest import _is_declared_evidence_path

        measured = self.manifest["test_matrix"]["measured_at_commit"]
        self.assertTrue(HEX40.match(measured))
        ancestor = self._locus_git("merge-base", "--is-ancestor", measured, "HEAD")
        self.assertEqual(ancestor.returncode, 0, f"{measured} is not an ancestor-or-self of HEAD")
        delta = self._locus_git("diff", "--name-only", f"{measured}..HEAD").stdout.splitlines()
        undeclared = [path for path in (line.strip() for line in delta) if path and not _is_declared_evidence_path(path)]
        self.assertEqual(undeclared, [], f"non-evidence paths inside the certified range: {undeclared}")

    def test_regression_locus_verification_record_never_contradicts(self) -> None:
        """Lifecycle rule: the verification record is born right after the
        evidence commit it proves, so absence is legal only pre-verification;
        once present it must assert PASS with observed equal to recorded -
        and it can then never silently rot."""
        record_path = ROOT / "runs" / "release-baseline" / "REGRESSION_LOCUS_VERIFICATION.json"
        if not record_path.is_file():
            return
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["verdict"], "PASS")
        self.assertEqual(
            record["observed"]["result"],
            record["recorded"]["result"],
            "verified result must equal the recorded result verbatim",
        )
        self.assertEqual(
            record["observed"]["exit_code"],
            record["recorded"]["exit_code"],
            "verified exit code must equal the recorded exit code",
        )
        self.assertRegex(
            record["recorded"]["measured_at_commit"], r"^[0-9a-f]{40}$",
            "verification must name a full 40-hex locus",
        )

class RegressionDriftRefusalTests(unittest.TestCase):
    """SD-RBR-v1.0 W-2: the manifest generator must refuse any regression
    record whose measured_at_commit differs from the generation head.

    Each case builds a hermetic throwaway git repository containing the real
    generator plus minimal ledger fixtures, so refusal is demonstrated by an
    actual non-zero process exit with no manifest written - never by mocking.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.generator_source = ROOT / "tools" / "build_completion_manifest.py"

    def _sandbox(self, measured_at_commit: str) -> tuple[Path, str]:
        sandbox = Path(tempfile.mkdtemp(prefix="sd_drift_sandbox_"))
        self.addCleanup(shutil.rmtree, sandbox, ignore_errors=True)
        (sandbox / "tools").mkdir()
        shutil.copyfile(self.generator_source, sandbox / "tools" / "build_completion_manifest.py")
        seal = sandbox / "runs" / "completion-loop"
        seal.mkdir(parents=True)
        (sandbox / "docs").mkdir()
        export_dir = sandbox / "runs" / "export"
        export_dir.mkdir(parents=True)
        punch = {
            "schema_version": "1.0",
            "recorded_at": "2026-08-23T00:00:00Z",
            "items": [
                {"id": item_id, "title": item_id, "priority": "P0", "status": "CLOSED"}
                for item_id in SOFTWARE_IDS
            ],
        }
        loop_state = {
            "implementation_seal_commit": IMPLEMENTATION_SEAL_COMMIT,
            "last_full_regression": {
                "command": "python -m pytest -q -p no:cacheprovider",
                "result": "200 passed, 375 subtests passed",
                "exit_code": 0,
                "python": "3.14.6",
                "measured_at_commit": measured_at_commit,
            },
        }
        version_matrix = {
            "software_package": {"version": "1.1.0rc3"},
            "thesis": {"current": {"version": "v1.2"}},
            "specification": {"draft_version": "v1.1"},
            "schemas": [],
        }
        export_report = {
            "raw_source": {"zip_sha256": "0" * 64},
            "enterprise": {"bundle_sha256": "0" * 64},
        }
        (seal / "PUNCH_LIST.json").write_text(json.dumps(punch), encoding="utf-8")
        (seal / "FINDINGS_REGISTER.json").write_text(json.dumps({"findings": []}), encoding="utf-8")
        (seal / "LOOP_STATE.json").write_text(json.dumps(loop_state), encoding="utf-8")
        (sandbox / "docs" / "VERSION_MATRIX.json").write_text(json.dumps(version_matrix), encoding="utf-8")
        (export_dir / "LATEST_EXPORT_REPORT.json").write_text(json.dumps(export_report), encoding="utf-8")

        def git(*args: str) -> None:
            subprocess.run(["git", "-C", str(sandbox), *args], check=True, capture_output=True)

        git("init")
        git("config", "user.email", "drift-test@example.invalid")
        git("config", "user.name", "Drift Test")
        git("add", "-A")
        git("commit", "-m", "sandbox base state")
        git("branch", "origin/main", "HEAD")
        head = subprocess.run(
            ["git", "-C", str(sandbox), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        return sandbox, head

    def _run_generator(self, sandbox: Path):
        return subprocess.run(
            [sys.executable, str(sandbox / "tools" / "build_completion_manifest.py")],
            cwd=str(sandbox), capture_output=True, text=True,
        )

    def test_generator_refuses_stale_measurement_locus(self) -> None:
        stale = "b" * 40
        sandbox, head = self._sandbox(stale)
        self.assertNotEqual(stale, head, "sandbox head must differ from the stale locus")
        completed = self._run_generator(sandbox)
        manifest_path = sandbox / "runs" / "completion-loop" / "BUILD_COMPLETION_MANIFEST.json"
        self.assertNotEqual(completed.returncode, 0, "generator must exit non-zero on drift")
        self.assertFalse(manifest_path.exists(), "no manifest may be written on drift")
        combined = completed.stdout + completed.stderr
        self.assertIn("regression drift detected", combined)
        self.assertIn(stale, combined)

    def test_generator_accepts_matching_locus_and_binds_recorded_value(self) -> None:
        sandbox, head = self._sandbox("a" * 40)
        loop_state_path = sandbox / "runs" / "completion-loop" / "LOOP_STATE.json"
        loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
        loop_state["last_full_regression"]["measured_at_commit"] = head
        loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8", newline="\n")
        completed = self._run_generator(sandbox)
        manifest_path = sandbox / "runs" / "completion-loop" / "BUILD_COMPLETION_MANIFEST.json"
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertTrue(manifest_path.exists())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["test_matrix"]["measured_at_commit"], head)
        self.assertEqual(manifest["evidence_generation_base"], head)

class RegressionLocusVerifierGateTests(unittest.TestCase):
    """R-1 negative test #2 and its positive twin, against the real verifier.

    A record naming a REAL ancestor commit but carrying a WRONG result string
    must be rejected with a non-zero exit - the case the old equality guard
    could never see. The twin proves an honest record settles to PASS.
    """

    MEASURED_COMMAND_RESULT = "201 passed, 377 subtests passed"

    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier_source = ROOT / "tools" / "verify_regression_locus.py"

    def _sandbox(self, recorded_result: str) -> tuple[Path, str]:
        sandbox = Path(tempfile.mkdtemp(prefix="sd_locus_sandbox_"))
        self.addCleanup(shutil.rmtree, sandbox, ignore_errors=True)
        (sandbox / "tools").mkdir()
        shutil.copyfile(self.verifier_source, sandbox / "tools" / "verify_regression_locus.py")
        seal = sandbox / "runs" / "completion-loop"
        seal.mkdir(parents=True)
        command = 'python -c "print(\'' + self.MEASURED_COMMAND_RESULT + '\')"'
        loop_state = {
            "implementation_seal_commit": IMPLEMENTATION_SEAL_COMMIT,
            "last_full_regression": {
                "command": command,
                "result": recorded_result,
                "exit_code": 0,
                "python": "3.14.6",
                "measured_at_commit": None,
            },
        }
        (seal / "LOOP_STATE.json").write_text(json.dumps(loop_state), encoding="utf-8")

        def git(*args: str) -> None:
            subprocess.run(["git", "-C", str(sandbox), *args], check=True, capture_output=True)

        git("init")
        git("config", "user.email", "locus-test@example.invalid")
        git("config", "user.name", "Locus Test")
        git("add", "-A")
        git("commit", "-m", "sandbox base")
        head = subprocess.run(
            ["git", "-C", str(sandbox), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        loop_state["last_full_regression"]["measured_at_commit"] = head
        (seal / "LOOP_STATE.json").write_text(json.dumps(loop_state), encoding="utf-8", newline="\n")
        return sandbox, head

    def _run_verifier(self, sandbox: Path):
        return subprocess.run(
            [sys.executable, str(sandbox / "tools" / "verify_regression_locus.py")],
            cwd=str(sandbox), capture_output=True, text=True,
        )

    def test_wrong_result_string_on_real_ancestor_is_refused(self) -> None:
        sandbox, _head = self._sandbox("199 passed, 375 subtests passed")
        completed = self._run_verifier(sandbox)
        record = json.loads(
            (sandbox / "runs" / "release-baseline" / "REGRESSION_LOCUS_VERIFICATION.json").read_text(encoding="utf-8")
        )
        self.assertNotEqual(completed.returncode, 0, "wrong result string must refuse")
        self.assertEqual(record["verdict"], "FAIL")
        self.assertEqual(record["recorded"]["result"], "199 passed, 375 subtests passed")
        self.assertNotEqual(record["observed"]["result"], record["recorded"]["result"])

    def test_matching_result_string_on_real_ancestor_settles_to_pass(self) -> None:
        sandbox, head = self._sandbox(self.MEASURED_COMMAND_RESULT)
        completed = self._run_verifier(sandbox)
        record = json.loads(
            (sandbox / "runs" / "release-baseline" / "REGRESSION_LOCUS_VERIFICATION.json").read_text(encoding="utf-8")
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(record["verdict"], "PASS")
        self.assertEqual(record["recorded"]["measured_at_commit"], head)
        self.assertTrue(record["is_ancestor_or_self_of_head"])
        self.assertTrue(record["worktree_cleaned_up"])


if __name__ == "__main__":

    unittest.main()
