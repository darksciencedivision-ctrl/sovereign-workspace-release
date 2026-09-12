"""R35 — DEEP artifact references are typed pointers that resolve under the external-state layout.

The DEEP producer emitted bare relative paths and the server recognised only sovereign:// typed
pointers, so under the external-state layout (runtime state outside the install root) a DEEP run's
evidence references could fail to resolve and the grounded answer was rejected or served with
unreachable evidence.

Now the producer emits typed, round-trip-validated pointers through the one shared contract
(ProductPaths.make_pointer), and the server resolves both schemes through the same contract. These
tests use a 14-reference fixture under an EXTERNAL state root and assert every pointer resolves.
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
    resolve_product_paths,
)
from sovereign_product.semantic_deep import SemanticDeepExecutor  # noqa: E402
from sovereign_product.server import ProductService  # noqa: E402

# The reference keys a real DEEP run populates in context.artifacts (>= 14 under a multi-turn run).
FIXTURE_KEYS = (
    "request", "evidence", "transcript", "result",
    "turn_01", "turn_02", "turn_03",
    "critique", "verification_1", "verification_2",
    "accepted", "accepted_text", "run_record", "raw",
)


def _external_paths(tmp: Path):
    root = tmp / "install"
    root.mkdir()
    (root / ROOT_MARKER).write_text(ROOT_MARKER_CONTENT, encoding="utf-8")
    (root / "SYSTEM_MANIFEST.json").write_text("{}", encoding="utf-8")
    state = tmp / "external-state"          # OUTSIDE the install root
    paths = resolve_product_paths(
        root, state_dir=state, approved_roots=(state,), create=True)
    return root, paths


class ProducerEmitsResolvableTypedPointers(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="r35prod-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.root, self.paths = _external_paths(self.tmp)
        self.executor = SemanticDeepExecutor(
            self.root,
            object(),                       # client: unused, we never run a generation
            artifact_root=self.paths.evidence_dir / "semantic_deep",
            trusted_roots=(self.paths.state_dir,),
            base_options={"num_ctx": 131072, "num_predict": 32768},
            pointer_factory=self.paths.make_pointer,
        )

    def test_fourteen_references_are_typed_and_resolve(self) -> None:
        run_dir = self.executor.artifact_root / "session_x" / "run_y"
        run_dir.mkdir(parents=True, exist_ok=True)
        refs = {}
        for i, key in enumerate(FIXTURE_KEYS):
            artifact = run_dir / f"{key}.json"
            artifact.write_text(f'{{"n": {i}}}', encoding="utf-8")
            refs[key] = self.executor._artifact_ref(artifact)
        self.assertEqual(len(refs), 14)
        for key, ref in refs.items():
            self.assertTrue(ref.startswith(STATE_POINTER_PREFIX),
                            f"{key} is not a state pointer: {ref}")
            resolved = self.paths.resolve_pointer(ref, must_exist=True)
            self.assertEqual(resolved.resolve(), (run_dir / f"{key}.json").resolve(),
                             f"{key} pointer did not round-trip: {ref}")


class _FakeService:
    def __init__(self, paths, root) -> None:
        self.paths = paths
        self.root = root

    _artifact_pointers = ProductService._artifact_pointers
    _runtime_pointer = ProductService._runtime_pointer


class ServerResolvesEveryPointerOfTheFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="r35srv-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.root, self.paths = _external_paths(self.tmp)
        self.svc = _FakeService(self.paths, self.root)

    def test_a_full_fixture_of_state_pointers_is_kept(self) -> None:
        run_dir = self.paths.evidence_dir / "semantic_deep" / "s" / "r"
        run_dir.mkdir(parents=True, exist_ok=True)
        artifacts = {}
        for i, key in enumerate(FIXTURE_KEYS):
            f = run_dir / f"{key}.json"
            f.write_text(f'{{"n": {i}}}', encoding="utf-8")
            artifacts[key] = self.paths.make_pointer(f)

        class _Ex:
            artifact_root = run_dir

        resolved = self.svc._artifact_pointers(artifacts, executor=_Ex())
        # Every one of the 14 typed pointers survived resolution (none silently dropped).
        self.assertEqual(set(resolved), set(FIXTURE_KEYS))
        for key, pointer in resolved.items():
            self.assertTrue(pointer.startswith(STATE_POINTER_PREFIX), f"{key}: {pointer}")

    def test_an_unresolvable_pointer_is_dropped(self) -> None:
        run_dir = self.paths.evidence_dir / "gone"
        run_dir.mkdir(parents=True, exist_ok=True)
        present = run_dir / "there.json"
        present.write_text("{}", encoding="utf-8")

        class _Ex:
            artifact_root = run_dir

        artifacts = {
            "there": self.paths.make_pointer(present),
            "missing": STATE_POINTER_PREFIX + "gone/not-written.json",
        }
        resolved = self.svc._artifact_pointers(artifacts, executor=_Ex())
        self.assertIn("there", resolved)
        self.assertNotIn("missing", resolved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
