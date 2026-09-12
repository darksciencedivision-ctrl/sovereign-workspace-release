"""F-119 (with the R35 shared contract) — evidence artifacts emit resolvable pointers.

The evidence tree lives under the STATE root (P4-4), which the install-root-only paths.pointer()
cannot express, so ResearchExecutor._artifact_reference fell back to `approved-evidence://<rel>` --
a scheme nothing resolves. A completed RESEARCH run therefore pointed at artifacts that could not
be opened and was REJECTED downstream.

ProductPaths.make_pointer is now the one producer-side contract: it chooses sovereign:// or
sovereign-state:// by which root contains the path and round-trip-validates the result, and
_artifact_reference uses it. These tests use an EXTERNAL state layout (state outside the install
root), the layout that triggered the defect.
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
    POINTER_PREFIX,
    UnsafeArtifactPointer,
    resolve_product_paths,
)
from sovereign_product.research import ResearchExecutor  # noqa: E402


class _FakeExecutor:
    """Only what _artifact_reference reads."""

    def __init__(self, paths, evidence_dir: Path) -> None:
        self.paths = paths
        self.evidence_dir = evidence_dir

    _artifact_reference = ResearchExecutor._artifact_reference


class MakePointerContract(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="f119-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.root = self.tmp / "install"
        self.root.mkdir()
        (self.root / ROOT_MARKER).write_text(ROOT_MARKER_CONTENT, encoding="utf-8")
        (self.root / "SYSTEM_MANIFEST.json").write_text("{}", encoding="utf-8")
        self.state = self.tmp / "external-state"    # deliberately OUTSIDE the install root
        self.paths = resolve_product_paths(
            self.root, state_dir=self.state, approved_roots=(self.state,), create=True)

    def test_a_state_tree_path_becomes_a_resolvable_state_pointer(self) -> None:
        target = self.paths.evidence_dir / "semantic_deep" / "run1" / "report.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
        pointer = self.paths.make_pointer(target)
        self.assertTrue(pointer.startswith(STATE_POINTER_PREFIX), pointer)
        self.assertNotIn("approved-evidence://", pointer)
        self.assertEqual(self.paths.resolve_pointer(pointer, must_exist=True).resolve(),
                         target.resolve())

    def test_an_install_tree_path_becomes_an_install_pointer(self) -> None:
        pointer = self.paths.make_pointer(self.root / "SYSTEM_MANIFEST.json")
        self.assertTrue(pointer.startswith(POINTER_PREFIX))
        self.assertFalse(pointer.startswith(STATE_POINTER_PREFIX))

    def test_a_path_under_neither_root_is_refused(self) -> None:
        with self.assertRaises(UnsafeArtifactPointer):
            self.paths.make_pointer(self.tmp / "elsewhere" / "x.json")


class ArtifactReferenceEmitsResolvablePointers(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="f119ref-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.root = self.tmp / "install"
        self.root.mkdir()
        (self.root / ROOT_MARKER).write_text(ROOT_MARKER_CONTENT, encoding="utf-8")
        (self.root / "SYSTEM_MANIFEST.json").write_text("{}", encoding="utf-8")
        self.state = self.tmp / "external-state"
        self.paths = resolve_product_paths(
            self.root, state_dir=self.state, approved_roots=(self.state,), create=True)
        self.executor = _FakeExecutor(self.paths, self.paths.evidence_dir)

    def test_report_reference_is_resolvable_not_the_dead_scheme(self) -> None:
        report = self.paths.evidence_dir / "research" / "r1" / "final_report.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("# report", encoding="utf-8")
        reference = self.executor._artifact_reference(report, self.paths.evidence_dir)
        self.assertNotIn("approved-evidence://", reference)
        self.assertTrue(reference.startswith(STATE_POINTER_PREFIX), reference)
        # The whole point of F-119: the emitted reference resolves back to the artifact.
        self.assertEqual(self.paths.resolve_pointer(reference, must_exist=True).resolve(),
                         report.resolve())


if __name__ == "__main__":
    unittest.main(verbosity=2)
