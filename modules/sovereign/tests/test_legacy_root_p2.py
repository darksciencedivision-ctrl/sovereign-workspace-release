"""F-122 - the legacy SOVEREIGN pipeline no longer crashes on the untracked URI/ directory, no
longer resolves the repo root by a directory-name heuristic, and no longer silently sends an empty
model name to Ollama when the system manifest cannot be loaded.

The shipped product (sovereign_product) does not use these legacy resolvers, so these tests target
the legacy modules directly. They exercise the three concrete defects the finding names.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))


class RootValidationDoesNotRequireUri(unittest.TestCase):
    def test_marked_root_without_uri_validates(self):
        # A checkout/install has the tracked .sovereign-root marker and sandbox_agi/ but NOT URI/
        # (nothing under URI/ is tracked). Root validation must succeed anyway.
        from tools import sovereign_paths as sp

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / sp.ROOT_MARKER_NAME).write_text(sp.ROOT_MARKER_CONTENT, encoding="utf-8")
            (root / "sandbox_agi").mkdir()
            # deliberately do NOT create URI/
            resolved = sp._validate_repo_root(root, require_marker=True)
            self.assertEqual(resolved, root.resolve())

    def test_missing_sandbox_agi_still_refused(self):
        from tools import sovereign_paths as sp

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / sp.ROOT_MARKER_NAME).write_text(sp.ROOT_MARKER_CONTENT, encoding="utf-8")
            with self.assertRaises(sp.RootResolutionError):
                sp._validate_repo_root(root, require_marker=True)


class DetectRepoRootRequiresMarker(unittest.TestCase):
    def test_directory_named_sovereign_is_not_a_root_without_the_marker(self):
        from knowledge_base import common

        with tempfile.TemporaryDirectory() as d:
            # A directory merely NAMED "SOVEREIGN" with no marker must NOT be accepted as the root.
            fake = Path(d) / "SOVEREIGN" / "nested"
            fake.mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                common.detect_repo_root(fake)

    def test_marked_root_is_found(self):
        from knowledge_base import common

        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "anything"
            (root).mkdir()
            (root / ".sovereign-root").write_text("SOVEREIGN_ROOT_MARKER=1", encoding="utf-8")
            child = root / "a" / "b"
            child.mkdir(parents=True)
            self.assertEqual(common.detect_repo_root(child), root.resolve())


class EmptyModelFailsLoudly(unittest.TestCase):
    def test_topic_extractor_refuses_empty_model(self):
        import topic_extractor as te

        saved = te.EXTRACT_MODEL
        try:
            te.EXTRACT_MODEL = ""
            with self.assertRaises(RuntimeError):
                te._require_extract_model()
        finally:
            te.EXTRACT_MODEL = saved

    def test_domain_checker_refuses_empty_model(self):
        import domain_checker as dc

        saved = dc.EMBED_MODEL
        try:
            dc.EMBED_MODEL = ""
            with self.assertRaises(RuntimeError):
                dc._require_embed_model()
        finally:
            dc.EMBED_MODEL = saved


if __name__ == "__main__":
    unittest.main()
