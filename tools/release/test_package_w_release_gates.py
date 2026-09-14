"""Package W remaining clauses: F-070 reason persistence, F-075 notice/projection."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import generate_model_projection as gmp  # noqa: E402
import generate_notice as gn  # noqa: E402
import sync_release_manifest as srm  # noqa: E402


class RepinReasonTests(unittest.TestCase):
    def test_empty_reason_refused(self) -> None:
        args = argparse.Namespace(repin=["docs/x.md"], reason="  ")
        self.assertEqual(srm.repin(args), 2)

    def test_trivial_reason_refused(self) -> None:
        args = argparse.Namespace(repin=["docs/x.md"], reason="update")
        self.assertEqual(srm.repin(args), 2)

    def test_reason_is_persisted_with_old_and_new_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "docs" / "x.md"
            target.parent.mkdir()
            target.write_text("hello-reviewed", encoding="utf-8")
            measured = hashlib.sha256(target.read_bytes()).hexdigest()
            old = "0" * 64
            manifest = {
                "generated_artifacts": {"paths": []},
                "modules": {"sovereign": {"locks": [{"path": "docs/x.md", "sha256": old}]}},
            }
            (root / "RELEASE-MANIFEST.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            args = argparse.Namespace(
                repin=["docs/x.md"],
                reason="reviewed launcher rewrite after F-070")
            with patch.object(srm, "repo_root", return_value=root):
                self.assertEqual(srm.repin(args), 0)
            written = json.loads((root / "RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
            item = written["modules"]["sovereign"]["locks"][0]
            self.assertEqual(item["sha256"], measured)
            self.assertEqual(item["repin_reason"], args.reason)
            self.assertTrue(item.get("repin_utc"))
            history = written["repin_history"]
            self.assertEqual(history[-1]["was"], old)
            self.assertEqual(history[-1]["now"], measured)
            self.assertEqual(history[-1]["reason"], args.reason)


class NoticeUnresolvedTests(unittest.TestCase):
    def test_unresolved_licence_does_not_write_notice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sbom = Path(tmp) / "SBOM.json"
            notice = Path(tmp) / "NOTICE"
            notice.write_text("prior-complete-notice\n", encoding="utf-8")
            sbom.write_text(json.dumps({
                "components": [{
                    "type": "library", "name": "mystery", "version": "1",
                    "licenses": [{"license": {"id": "UNRESOLVED"}}],
                }]
            }), encoding="utf-8")
            with patch.object(sys, "argv", ["generate_notice.py", "--sbom", str(sbom),
                                            "--out", str(notice)]):
                rc = gn.main()
            self.assertEqual(rc, 1)
            self.assertEqual(notice.read_text(encoding="utf-8"), "prior-complete-notice\n")


class ProjectionWriteTests(unittest.TestCase):
    def test_write_after_correction_exits_nonzero(self) -> None:
        with patch.object(gmp, "project_readme", return_value=["drift"]):
            with patch.object(gmp, "load_models", return_value={}):
                with patch.object(gmp, "repo_root", return_value=Path(HERE)):
                    rc = gmp.main(["--write"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
