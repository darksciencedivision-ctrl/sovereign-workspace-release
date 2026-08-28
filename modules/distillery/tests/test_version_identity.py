from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from distillery.common import ContractError
from distillery.identity import (
    load_version_matrix,
    resolve_identity,
    software_version,
    validate_snapshot_identity,
)

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs/VERSION_MATRIX.json"


class VersionIdentityTests(unittest.TestCase):
    def test_matrix_loads_with_required_sections(self) -> None:
        matrix = load_version_matrix(ROOT)
        for section in ("software_package", "thesis", "specification", "schemas", "snapshot_identity"):
            self.assertIn(section, matrix)

    def test_software_version_matches_pyproject(self) -> None:
        declared = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE).group(1)
        self.assertEqual(software_version(ROOT), declared)
        self.assertTrue(re.match(r"^\d+\.\d+\.\d+", declared), declared)

    def test_exactly_one_current_thesis_and_historical_documents_exist(self) -> None:
        matrix = load_version_matrix(ROOT)
        current_document = ROOT / matrix["thesis"]["current"]["document"]
        self.assertTrue(current_document.is_file())
        header = current_document.read_text(encoding="utf-8")
        self.assertIn(matrix["thesis"]["current"]["status_line"], header)
        self.assertIn(matrix["thesis"]["current"]["version"], header)
        historical_versions = {row["version"] for row in matrix["thesis"]["historical"]}
        self.assertNotIn(matrix["thesis"]["current"]["version"], historical_versions)
        for row in matrix["thesis"]["historical"]:
            path = ROOT / row["document"]
            with self.subTest(document=row["document"]):
                self.assertTrue(path.is_file())
                self.assertIn(row["version"], path.read_text(encoding="utf-8"))

    def test_specification_identity_declared_and_present(self) -> None:
        matrix = load_version_matrix(ROOT)
        spec = ROOT / matrix["specification"]["draft_document"]
        self.assertTrue(spec.is_file())
        self.assertIn(matrix["specification"]["draft_version"], spec.read_text(encoding="utf-8"))

    def test_schema_files_match_matrix_ids(self) -> None:
        matrix = load_version_matrix(ROOT)
        listed = {row["path"]: row["id"] for row in matrix["schemas"]}
        on_disk = {path.relative_to(ROOT).as_posix(): json.loads(path.read_text(encoding="utf-8")).get("$id") for path in (ROOT / "schema").glob("*.json")}
        self.assertEqual(listed, on_disk)

    def test_registry_schema_versions_match_files(self) -> None:
        matrix = load_version_matrix(ROOT)
        for relative, version in matrix["registry_schema_versions"].items():
            with self.subTest(registry=relative):
                document = json.loads((ROOT / relative).read_text(encoding="utf-8"))
                self.assertEqual(document.get("schema_version"), version)

    def test_resolve_identity_verifies_bundle_and_evidence_paths(self) -> None:
        identity = resolve_identity(ROOT)
        self.assertRegex(identity["git_head"], r"^[0-9a-f]{40}$")
        self.assertTrue(identity["snapshot"]["bundle_digest_verified"])

    def test_malformed_snapshot_identities_rejected(self) -> None:
        for snapshot, bundle in (("zz", "a" * 64), ("a" * 40, "short"), (None, "a" * 64)):
            with self.subTest(snapshot=snapshot, bundle=bundle):
                with self.assertRaises(ContractError):
                    validate_snapshot_identity(snapshot, bundle)

    def test_missing_matrix_fails_closed(self) -> None:
        with self.assertRaises(ContractError):
            load_version_matrix(Path(ROOT.parent))

    def test_cli_version_command_exposes_identity(self) -> None:
        from grounded.cli import main

        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = main(["version"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["software_version"], software_version(ROOT))
        self.assertIn("git_head", payload)


if __name__ == "__main__":
    unittest.main()