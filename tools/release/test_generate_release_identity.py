from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import generate_release_identity as subject


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
            self.assertEqual("abc123", json.loads((root / "VERSION.json").read_text())["source_commit"])
            self.assertIn("MIT", (root / "THIRD-PARTY-NOTICES.md").read_text())


if __name__ == "__main__":
    unittest.main()
