"""EPC-01 P3-7 — no shipped component may carry a null version.

`modules/sovereign/ui/ui_shell/package.json` shipped as `0.0.0-private`. A component with a
null version is unresolvable in an SBOM, uncomparable across releases, and tells a consumer
nothing about what they have.

Per EPC-01 D-3 the workspace does NOT force one version across modules — the six version
numbers encode real, separate provenance. What it forbids is a version that is not a version.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Values that are placeholders rather than versions.
NULL_VERSIONS = {"0.0.0", "0.0.0-private", "0.0.0-dev", "", "0.0.0-0"}

SEMVER = re.compile(r"^\d+\.\d+\.\d+")


def _shipped_package_jsons():
    skip = {"node_modules", ".venv", "__pycache__", "evidence", "dev", "release-artifacts"}
    for path in REPO_ROOT.rglob("package.json"):
        rel = path.relative_to(REPO_ROOT)
        if skip & set(rel.parts):
            continue
        yield rel.as_posix(), json.loads(path.read_text(encoding="utf-8"))


class ShippedVersionsAreReal(unittest.TestCase):

    def test_some_package_manifests_are_actually_checked(self) -> None:
        found = list(_shipped_package_jsons())
        self.assertGreaterEqual(
            len(found), 2,
            "expected at least the SOVEREIGN UI and the SOW desktop manifests; "
            f"found {[rel for rel, _ in found]}"
        )

    def test_no_shipped_package_carries_a_null_version(self) -> None:
        offenders = [
            f"{rel} -> {doc.get('version')!r}"
            for rel, doc in _shipped_package_jsons()
            if str(doc.get("version", "")).strip() in NULL_VERSIONS
        ]
        self.assertEqual(
            offenders, [],
            "shipped components carry placeholder versions, which are unresolvable in an "
            "SBOM and uncomparable across releases:\n  " + "\n  ".join(offenders)
        )

    def test_every_shipped_version_parses_as_a_version(self) -> None:
        offenders = [
            f"{rel} -> {doc.get('version')!r}"
            for rel, doc in _shipped_package_jsons()
            if not SEMVER.match(str(doc.get("version", "")))
        ]
        self.assertEqual(
            offenders, [],
            "shipped components carry versions that do not parse:\n  " + "\n  ".join(offenders)
        )


if __name__ == "__main__":
    unittest.main()
