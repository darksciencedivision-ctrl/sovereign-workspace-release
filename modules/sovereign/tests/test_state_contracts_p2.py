"""P2 SOVEREIGN state/contract fixes: R29, R30, R33, R36.

R29: restart recovery accepted only sovereign:// recovery pointers, dropping the sovereign-state://
     pointers the service actually emits under the external-state layout.
R30: _runtime_pointer concatenated raw POSIX text, so a state file with URL-metadata characters
     ('#') produced a pointer resolve_pointer then rejected.
R33: the store admitted 1-128 char ids while the executors validate 1-96, so a long caller-provided
     session_id created a session that failed generation on every attempt.
R36: the semantic-DEEP public constructor's own default options could not pass its validator
     (num_predict pinned at 32768 next to a num_ctx recommendation capped at 32768).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.paths import (  # noqa: E402
    ROOT_MARKER, ROOT_MARKER_CONTENT, STATE_POINTER_PREFIX, ProductPaths, resolve_product_paths,
)
from sovereign_product.store import SovereignStore  # noqa: E402
from sovereign_product.server import ProductService  # noqa: E402
from sovereign_product import semantic_deep  # noqa: E402


class R33_SessionIdContract(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="r33-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.store = SovereignStore(self.tmp / "s.db")

    def test_an_id_the_executors_would_reject_is_refused_at_creation(self) -> None:
        with self.assertRaises(ValueError):
            self.store.create_session(session_id="a" * 97)

    def test_a_96_char_id_is_accepted(self) -> None:
        sid = "a" * 96
        self.assertEqual(self.store.create_session(session_id=sid)["session_id"], sid)


class R29_RecoveryAcceptsStatePointers(unittest.TestCase):
    def test_a_state_recovery_pointer_survives_restart_recovery(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="r29-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        store = SovereignStore(tmp / "s.db")
        session = store.create_session(title="New chat")["session_id"]
        job = store.admit_job(session, route="QUICK", input_text="q", user_content="q")["job"]
        store.transition_job(job["job_id"], "running", expected_status="queued")
        store.update_job_progress(job["job_id"], {
            "percent": 25, "stage": "running",
            "evidence_pointer": STATE_POINTER_PREFIX + "evidence/request.json"})
        result = store.recover_incomplete_jobs()
        self.assertIn(job["job_id"], result["interrupted"])
        recovered = store.get_job(job["job_id"])
        self.assertEqual(recovered["evidence_pointer"], STATE_POINTER_PREFIX + "evidence/request.json")
        self.assertEqual(recovered["metadata"]["recovery"]["evidence_pointer"],
                         STATE_POINTER_PREFIX + "evidence/request.json")


class _FakeService:
    def __init__(self, root, paths):
        self.root = root
        self.paths = paths
    _runtime_pointer = ProductService._runtime_pointer


class R30_RuntimePointerEncoding(unittest.TestCase):
    def test_a_state_file_with_url_metadata_round_trips(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="r30-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        root = tmp / "install"
        root.mkdir()
        (root / ROOT_MARKER).write_text(ROOT_MARKER_CONTENT, encoding="utf-8")
        (root / "SYSTEM_MANIFEST.json").write_text("{}", encoding="utf-8")
        state = tmp / "state"
        paths = resolve_product_paths(root, state_dir=state, approved_roots=(state,), create=True)
        target = state / "evidence" / "name#1.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")

        svc = _FakeService(root, paths)
        pointer = svc._runtime_pointer(target)
        self.assertTrue(pointer.startswith(STATE_POINTER_PREFIX), pointer)
        # The URL-metadata '#' is encoded, so resolve_pointer accepts it and it round-trips.
        self.assertEqual(paths.resolve_pointer(pointer, must_exist=True).resolve(), target.resolve())


class R36_SemanticDeepDefaults(unittest.TestCase):
    def test_default_options_construct_when_recommendation_equals_num_predict_cap(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="r36-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        root = tmp / "install"
        root.mkdir()
        (root / ROOT_MARKER).write_text(ROOT_MARKER_CONTENT, encoding="utf-8")
        (root / "SYSTEM_MANIFEST.json").write_text("{}", encoding="utf-8")

        class _Client:
            def generate(self, **kwargs):
                raise AssertionError("no generation in a constructor test")

        # Recommendation caps at 32768 -- the exact case that used to fail (num_ctx !> num_predict).
        with mock.patch.object(semantic_deep, "recommended_num_ctx", return_value=(32_768, 32_768)):
            ex = semantic_deep.SemanticDeepExecutor(
                root, _Client(),
                artifact_root=root / "runtime" / "evidence" / "semantic_deep",
                trusted_roots=(root,))
        self.assertGreater(ex.base_options["num_ctx"], ex.base_options["num_predict"])
        self.assertGreaterEqual(ex.base_options["num_ctx"], 4096)

    def test_explicit_base_options_still_win(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="r36b-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        root = tmp / "install"
        root.mkdir()
        (root / ROOT_MARKER).write_text(ROOT_MARKER_CONTENT, encoding="utf-8")

        class _Client:
            def generate(self, **kwargs):
                raise AssertionError("no generation in a constructor test")

        ex = semantic_deep.SemanticDeepExecutor(
            root, _Client(),
            artifact_root=root / "runtime" / "evidence" / "semantic_deep",
            trusted_roots=(root,),
            base_options={"num_ctx": 131072, "num_predict": 32768})
        self.assertEqual(ex.base_options["num_ctx"], 131072)
        self.assertEqual(ex.base_options["num_predict"], 32768)


if __name__ == "__main__":
    unittest.main(verbosity=2)
