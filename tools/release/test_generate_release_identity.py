from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Like its siblings: under --import-mode=importlib this directory is not on sys.path, so the bare
# import below resolved only when some EARLIER test in the same run had inserted it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_release_identity as subject  # noqa: E402


class GenerateReleaseIdentityTests(unittest.TestCase):
    def test_generates_deterministic_documents_and_native_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "modules/sovereign/.venv/Lib/site-packages/demo-1.0.dist-info").mkdir(parents=True)
            (root / "modules/sovereign/.venv/Lib/site-packages/demo-1.0.dist-info/METADATA").write_text(
                "Name: demo\nVersion: 1.0\nLicense-Expression: MIT\n",
                encoding="utf-8",
            )
            (root / "modules/sovereign/WORKSPACE-RESOLVED-LOCK.txt").write_text(
                "demo==1.0\n", encoding="utf-16"
            )
            (root / "modules/debate/.venv/Lib/site-packages").mkdir(parents=True)
            (root / "modules/debate/requirements.lock.txt").write_text("other==2.0\n", encoding="utf-8")
            for _name, lock_rel in subject.NODE_LOCKS:
                path = root / lock_rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "lockfileVersion": 3,
                            "packages": {
                                "": {},
                                "node_modules/pkg": {"version": "3.0", "license": "Apache-2.0"},
                            },
                        }
                    ),
                    encoding="utf-8",
                )
            native = root / "modules/sovereign/.venv/demo.dll"
            native.write_bytes(b"native")
            (root / "RELEASE-MANIFEST.json").write_text(
                json.dumps({"modules": {"sovereign": {"version": "3.1.2"}}}),
                encoding="utf-8",
            )

            subject.generate(root, "abc123", "2026-08-29T15:30:00Z")
            first = (root / "SBOM.json").read_bytes()
            subject.generate(root, "abc123", "2026-08-29T15:30:00Z")

            self.assertEqual(first, (root / "SBOM.json").read_bytes())
            sbom = json.loads(first)
            self.assertTrue(any(item.get("name") == "demo.dll" for item in sbom["components"]))
            version = json.loads((root / "VERSION.json").read_text())
            self.assertEqual("abc123", version["source_commit"])
            self.assertIn("MIT", (root / "THIRD-PARTY-NOTICES.md").read_text())

            # CLOSEOUT-01 X-5 (A-4): the release-identity commit convention is
            # emitted, so the two identity documents can never again disagree
            # without saying which one holds what.
            self.assertEqual(
                version["seal_commit_record"],
                "release-artifacts/release-build-manifest.json")
            self.assertIn("seal commit", version["source_commit_definition"])

    def test_version_document_never_claims_to_hold_the_seal_commit(self) -> None:
        """A-4 made mechanical. VERSION.json is tracked, so it is part of the
        tree its own commit hashes over; it cannot name that commit. This test
        fails if a future seat reintroduces a field that promises otherwise."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "modules/sovereign/.venv/Lib/site-packages").mkdir(parents=True)
            (root / "modules/sovereign/WORKSPACE-RESOLVED-LOCK.txt").write_text(
                "demo==1.0\n", encoding="utf-8")
            (root / "modules/debate/.venv/Lib/site-packages").mkdir(parents=True)
            (root / "modules/debate/requirements.lock.txt").write_text(
                "other==2.0\n", encoding="utf-8")
            for _name, lock_rel in subject.NODE_LOCKS:
                path = root / lock_rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps({"lockfileVersion": 3, "packages": {"": {}}}),
                    encoding="utf-8")
            (root / "RELEASE-MANIFEST.json").write_text(
                json.dumps({"modules": {"sovereign": {"version": "3.1.2"}}}),
                encoding="utf-8")

            seal = "0" * 40
            subject.generate(root, seal, "2026-08-29T15:30:00Z")
            version = json.loads((root / "VERSION.json").read_text())

            # The generator records what it was given as the LAST TOOLING commit
            # and points elsewhere for the seal. It never invents a seal hash.
            self.assertEqual(version["source_commit"], seal)
            self.assertNotIn("seal_commit", version)
            self.assertEqual(
                version["seal_commit_record"],
                "release-artifacts/release-build-manifest.json")


    def test_hash_pinned_locks_parse_to_the_same_pins(self) -> None:
        """F-071. A pip hash-pinned lock spans lines; its pins must be read exactly as before, and a
        non-exact requirement hidden among hashed ones must still be refused."""
        digest = "a" * 64
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / "lock.txt"
            lock.write_text(
                "# header\n"
                f"demo==1.0 \\\n    --hash=sha256:{digest} \\\n    --hash=sha256:{'b' * 64}\n"
                f"Other_Pkg==2.0 \\\n    --hash=sha256:{digest}\n",
                encoding="utf-8")
            self.assertEqual([("demo", "1.0"), ("other-pkg", "2.0")], subject.parse_python_lock(lock))
            lock.write_text(f"demo>=1.0 \\\n    --hash=sha256:{digest}\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                subject.parse_python_lock(lock)

    def test_cli_refuses_without_deprecated_override(self) -> None:
        rc = subject.main(["--root", ".", "--source-commit", "abc",
                           "--generated-utc", "2026-01-01T00:00:00Z"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
