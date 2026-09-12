"""R31 (F-102) — the /v1/evidence endpoint serves inert downloads, scoped to the evidence tree.

The endpoint resolved a pointer with the general resolver (both the install-root and state-root
schemes) and served the file inline with its guessed content type. Two consequences:

  * an evidence file containing HTML/SVG/JS was served inline in the app's origin and executed
    (stored XSS);
  * a well-formed pointer to the database (sovereign-state://sovereign.db) or into the install
    tree (sovereign://.venv/..., sovereign://SYSTEM_MANIFEST.json) resolved and was downloadable.

Now resolution is scoped to the evidence directory, and the response is forced to a text/plain
attachment with nosniff and a sandbox CSP.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.paths import (  # noqa: E402
    ROOT_MARKER,
    ROOT_MARKER_CONTENT,
    STATE_POINTER_PREFIX,
    UnsafeArtifactPointer,
    resolve_product_paths,
)


class EvidencePointerScoping(unittest.TestCase):
    """The paths-level contract, exercised directly."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="r31-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.root = self.tmp / "install"
        self.root.mkdir()
        (self.root / ROOT_MARKER).write_text(ROOT_MARKER_CONTENT, encoding="utf-8")
        (self.root / "SYSTEM_MANIFEST.json").write_text("{}", encoding="utf-8")
        self.state = self.tmp / "state"
        self.paths = resolve_product_paths(
            self.root, state_dir=self.state, approved_roots=(self.state,), create=True)
        # An evidence artifact, and two non-evidence files that a well-formed pointer names.
        (self.paths.evidence_dir / "status").mkdir(parents=True, exist_ok=True)
        (self.paths.evidence_dir / "status" / "job.json").write_text('{"ok":true}', encoding="utf-8")
        (self.state / "sovereign.db").write_text("not really a db", encoding="utf-8")

    def test_an_evidence_file_resolves(self) -> None:
        resolved = self.paths.resolve_evidence_pointer(
            STATE_POINTER_PREFIX + "evidence/status/job.json", must_exist=True)
        self.assertTrue(resolved.is_file())

    def test_the_database_is_refused(self) -> None:
        with self.assertRaises(UnsafeArtifactPointer):
            self.paths.resolve_evidence_pointer(
                STATE_POINTER_PREFIX + "sovereign.db", must_exist=True)

    def test_an_install_tree_file_is_refused(self) -> None:
        with self.assertRaises(UnsafeArtifactPointer):
            self.paths.resolve_evidence_pointer(
                "sovereign://SYSTEM_MANIFEST.json", must_exist=True)


class EvidenceResponsePolicy(unittest.TestCase):
    """The HTTP response policy, exercised through the real app."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="r31app-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.root = self.tmp / "install"
        self.root.mkdir()
        (self.root / ROOT_MARKER).write_text(ROOT_MARKER_CONTENT, encoding="utf-8")
        shutil.copyfile(MODULE_ROOT / "SYSTEM_MANIFEST.json", self.root / "SYSTEM_MANIFEST.json")
        self.state = self.tmp / "state"

        from sovereign_product.server import ProductService, create_app

        paths = resolve_product_paths(
            self.root, state_dir=self.state, approved_roots=(self.state,), create=True)
        self.service = ProductService(
            paths=paths,
            model_client=object(),
            quick_executor=object(),
            deep_executor=object(),
            research_executor=object(),
            evidence_builder=object(),
            start_workers=False,
        )
        ev = self.service.paths.evidence_dir
        (ev / "reports").mkdir(parents=True, exist_ok=True)
        (ev / "reports" / "x.html").write_text("<script>alert(1)</script>", encoding="utf-8")
        (ev / "reports" / "x.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            encoding="utf-8")
        self.client = create_app(service=self.service).test_client()

    def _get(self, pointer: str):
        from urllib.parse import quote
        return self.client.get(f"/v1/evidence?pointer={quote(pointer, safe='')}")

    def _assert_inert(self, resp) -> None:
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.headers["Content-Disposition"].startswith("attachment"),
                        resp.headers.get("Content-Disposition"))
        self.assertTrue(resp.headers["Content-Type"].startswith("text/plain"),
                        resp.headers.get("Content-Type"))
        self.assertIn("sandbox", resp.headers.get("Content-Security-Policy", ""))
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")

    def test_html_evidence_is_served_inert(self) -> None:
        self._assert_inert(self._get(STATE_POINTER_PREFIX + "evidence/reports/x.html"))

    def test_svg_evidence_is_served_inert(self) -> None:
        self._assert_inert(self._get(STATE_POINTER_PREFIX + "evidence/reports/x.svg"))

    def test_the_database_pointer_is_refused(self) -> None:
        resp = self._get(STATE_POINTER_PREFIX + "sovereign.db")
        self.assertEqual(resp.status_code, 400)

    def test_an_install_tree_pointer_is_refused(self) -> None:
        resp = self._get("sovereign://SYSTEM_MANIFEST.json")
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
