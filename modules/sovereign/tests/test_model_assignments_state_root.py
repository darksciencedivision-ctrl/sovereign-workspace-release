"""F-101 — a model selection is stored in the STATE root, layered over the shipped manifest, and
the tracked SYSTEM_MANIFEST.json is never rewritten.

Selecting a model used to merge the new role into SYSTEM_MANIFEST.json and write it back. That
mutated a committed, hash-verified install artifact (breaking verify_install / F-060) and simply
failed on a read-only install. The override now lives in the store's `meta` table inside the state
root and is overlaid at read time.

These pin the property, not the wording: the manifest file's bytes must not change, the override
must take effect through `_manifest()`, and a read-only install must still accept a selection.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.server import (  # noqa: E402
    MODEL_ASSIGNMENTS_META_KEY,
    ProductService,
    ServiceConfigurationError,
)
from sovereign_product.store import SovereignStore  # noqa: E402


class _FakeService:
    """Only the attributes the F-101 methods read; the real methods are bound below."""

    def __init__(self, root: Path, store: SovereignStore) -> None:
        self.root = root
        self.store = store
        self._configuration_lock = threading.RLock()
        self._injected_deep_executor = None
        self.deep_executor = None

    # The methods under test, taken straight off ProductService.
    _manifest = ProductService._manifest
    _stored_model_overrides = ProductService._stored_model_overrides
    _store_model_overrides = ProductService._store_model_overrides
    profile = ProductService.profile
    update_model_assignments = ProductService.update_model_assignments


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ModelSelectionWritesStateNotTheManifest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="f101-"))
        self.addCleanup(self._cleanup)
        self.root = self.tmp / "install"
        self.root.mkdir()
        self.manifest = self.root / "SYSTEM_MANIFEST.json"
        shutil.copyfile(MODULE_ROOT / "SYSTEM_MANIFEST.json", self.manifest)
        self.store = SovereignStore(self.tmp / "state" / "sovereign.db")
        self.svc = _FakeService(self.root, self.store)

    def _cleanup(self) -> None:
        # Undo any read-only flag we set so the tree can be removed.
        try:
            os.chmod(self.manifest, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_storing_an_override_leaves_the_manifest_file_byte_identical(self) -> None:
        before = _digest(self.manifest)
        self.svc._store_model_overrides({"CRITIC": "qwen3:8b"})
        self.assertEqual(before, _digest(self.manifest),
                         "SYSTEM_MANIFEST.json must not be rewritten by a model selection")
        # ...and it landed in the state store instead.
        self.assertEqual(self.store.get_meta(MODEL_ASSIGNMENTS_META_KEY), {"CRITIC": "qwen3:8b"})

    def test_the_override_is_overlaid_when_the_manifest_is_read(self) -> None:
        self.assertEqual(self.svc._manifest()["MODELS"]["CRITIC"], "dolphin3:8b")  # shipped default
        self.svc._store_model_overrides({"CRITIC": "qwen3:8b"})
        self.assertEqual(self.svc._manifest()["MODELS"]["CRITIC"], "qwen3:8b")  # overlaid
        # A role that was not overridden keeps the shipped value.
        self.assertEqual(self.svc._manifest()["MODELS"]["PRIMARY_REASONER"], "ornith:9b")

    def test_profile_reports_the_state_source_once_overridden(self) -> None:
        pristine = self.svc.profile()
        self.assertEqual(pristine["source"], "sovereign://SYSTEM_MANIFEST.json")
        self.svc._store_model_overrides({"SYNTHESIZER": "ornith:9b"})
        overridden = self.svc.profile()
        self.assertEqual(overridden["source"], "sovereign-state://model-assignments")
        got = {a["role"]: a["modelId"] for a in overridden["assignments"]}
        self.assertEqual(got["SYNTHESIZER"], "ornith:9b")

    def test_overrides_merge_rather_than_replace(self) -> None:
        self.svc._store_model_overrides({"CRITIC": "qwen3:8b"})
        self.svc._store_model_overrides({"SYNTHESIZER": "ornith:9b"})
        self.assertEqual(self.store.get_meta(MODEL_ASSIGNMENTS_META_KEY),
                         {"CRITIC": "qwen3:8b", "SYNTHESIZER": "ornith:9b"})

    def test_a_read_only_install_still_accepts_a_selection(self) -> None:
        os.chmod(self.manifest, stat.S_IREAD)  # read-only, as a verified install would be
        # Prove the manifest really is not writable in this environment; otherwise the test is
        # vacuous. If the platform ignores the flag, skip rather than assert a false pass.
        try:
            with self.manifest.open("a", encoding="utf-8"):
                writable = True
        except (OSError, PermissionError):
            writable = False
        if writable:
            self.skipTest("filesystem does not honour the read-only flag; cannot prove the point")
        self.svc._store_model_overrides({"CRITIC": "qwen3:8b"})
        self.assertEqual(self.svc._manifest()["MODELS"]["CRITIC"], "qwen3:8b")

    def test_an_invalid_override_is_refused_and_nothing_is_stored(self) -> None:
        # An empty model id cannot satisfy the manifest's non-empty-string rule.
        with self.assertRaises(ServiceConfigurationError):
            self.svc._store_model_overrides({"CRITIC": ""})
        self.assertIsNone(self.store.get_meta(MODEL_ASSIGNMENTS_META_KEY))

    def test_the_full_selection_path_persists_to_state_and_swaps_the_executor(self) -> None:
        # Stub the two collaborators update_model_assignments needs, so the test exercises the
        # persistence decision (state, not manifest) without a live Ollama or a real executor.
        self.svc._self_state = lambda: {  # type: ignore[attr-defined]
            "ollama": {"installed_models": ["qwen3:8b", "dolphin3:8b"], "model_states": []}
        }
        sentinel = object()
        self.svc._deep_executor_from_manifest = lambda m: sentinel  # type: ignore[attr-defined]
        before = _digest(self.manifest)

        result = self.svc.update_model_assignments(
            {"assignments": [{"role": "CRITIC", "modelId": "qwen3:8b"}]})

        self.assertEqual(before, _digest(self.manifest), "manifest must stay byte-identical")
        self.assertEqual(self.store.get_meta(MODEL_ASSIGNMENTS_META_KEY), {"CRITIC": "qwen3:8b"})
        self.assertIs(self.svc.deep_executor, sentinel, "the deep executor must be rebuilt")
        self.assertEqual(result["source"], "sovereign-state://model-assignments")


if __name__ == "__main__":
    unittest.main(verbosity=2)
