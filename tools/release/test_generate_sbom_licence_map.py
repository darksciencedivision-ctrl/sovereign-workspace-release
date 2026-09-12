#!/usr/bin/env python
"""F-072 tests — the SBOM is a pure function of TRACKED inputs, independent of module .venvs.

The SBOM's --check used to differ between the build host (module venvs present) and CI (no venvs),
because Python licences were resolved from those venvs at build/check time. Licences now come from
a committed map (tools/release/python_licences.json); the build and --check never read a .venv.

These prove: building with the venvs "removed" (the licence resolver stubbed to find nothing)
produces a byte-identical document; the committed SBOM matches its sources; and a package absent
from the map is surfaced as UNRESOLVED and fails, rather than being filled from the host.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import generate_sbom as sbom  # noqa: E402


class SbomIsVenvIndependent(unittest.TestCase):
    def test_build_does_not_depend_on_module_venvs(self) -> None:
        # Build once normally, then again with the ONLY venv/host-reading helpers neutered
        # (as if no module .venv and no host packages existed). The documents must be identical,
        # proving the build path reads the committed map, not the environment.
        baseline, _ = sbom.build()
        with mock.patch.object(sbom, "_site_packages_for", return_value=[]), \
             mock.patch.object(sbom, "licence_from_installed",
                               side_effect=AssertionError("build must not resolve from host")):
            without_venvs, unresolved = sbom.build()
        self.assertEqual(baseline, without_venvs,
                         "SBOM build differs when venvs/host are unavailable")
        self.assertEqual(unresolved, [], f"unexpected unresolved licences: {unresolved}")

    def test_committed_sbom_matches_its_sources(self) -> None:
        # The equivalent of `generate_sbom.py --check` succeeding, exercised in-process.
        document, unresolved = sbom.build()
        rendered = json.loads(json.dumps(document))  # normalise
        committed = json.loads((sbom.REPO_ROOT / "SBOM.json").read_text(encoding="utf-8"))
        for doc in (rendered, committed):
            for prop in doc.get("metadata", {}).get("component", {}).get("properties", []):
                if prop.get("name") == "sovereign:source-commit":
                    prop["value"] = "<ignored>"
        self.assertEqual(rendered, committed, "committed SBOM.json no longer matches its sources")
        self.assertEqual(unresolved, [])

    def test_a_package_absent_from_the_map_is_unresolved_not_host_filled(self) -> None:
        with mock.patch.object(sbom, "load_licence_map", return_value={}):
            document, unresolved = sbom.build()
        self.assertTrue(unresolved, "a missing map entry must be reported UNRESOLVED")
        pypi = [c for c in document["components"] if c["purl"].startswith("pkg:pypi/")]
        self.assertTrue(pypi)
        for component in pypi:
            self.assertEqual(component["licenses"], [{"license": {"name": "UNRESOLVED"}}],
                             f"{component['purl']} was filled from somewhere other than the map")

    def test_sources_no_longer_record_a_host_venv_path(self) -> None:
        document, _ = sbom.build()
        for source in document["sovereign:sources"]:
            resolved_from = source.get("licences_resolved_from", "")
            self.assertNotIn(".venv", resolved_from)
            self.assertNotIn(":", resolved_from.replace("://", ""))  # no drive-letter host path


if __name__ == "__main__":
    unittest.main(verbosity=2)
