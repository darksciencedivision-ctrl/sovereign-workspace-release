"""EPC-02 B-1 — the model picker was empty because `_self_state()` raised.

Reproduced live, not inferred. With SOVEREIGN running, `/v1/models` returned:

    {"error": "Artifact path escapes the SOVEREIGN root:
      C:\\Users\\<account>\\SovereignWorkspace\\sovereign\\runtime\\sovereign.db", "ok": false}

and so did `/v1/self-state`. The operator saw four role slots with nothing to put in them.

The cause is a regression from EPC-01 P4-4. That change moved runtime state OUT of the
install root so an installation can be verified against its manifest, upgraded and
uninstalled cleanly — and the database moved with it. But `_self_state()` still asked
`artifact_pointer` to express the database path relative to the INSTALL root, which it
cannot do, and `artifact_pointer` raises rather than returning anything. The exception
propagated out of `_self_state()`, which is the foundation of `/v1/models`.

The pointer's job at that site is to keep an absolute host path out of the state summary.
That purpose is served for either location, so both are now expressed relative to a NAMED
base under distinct schemes.

These tests pin the property, not the wording: the summary must never carry an absolute host
path, and `_self_state()` must not raise merely because state lives where P4-4 put it.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.paths import (  # noqa: E402
    POINTER_PREFIX,
    ProductPaths,
    UnsafeArtifactPointer,
    artifact_pointer,
)
from sovereign_product.paths import STATE_POINTER_PREFIX  # noqa: E402


class _FakeService:
    """Only the two attributes `_database_descriptor` reads."""

    def __init__(self, root: Path, state_dir: Path, db_path: Path) -> None:
        self.root = root
        self.paths = ProductPaths(root, state_dir, db_path, state_dir / "evidence")

    _database_descriptor = None  # bound below


from sovereign_product.server import ProductService  # noqa: E402

_FakeService._database_descriptor = ProductService._database_descriptor
# The general resolver every runtime pointer site now shares. Bound too, because the
# database descriptor is a thin caller of it and the fix that matters lives here.
_FakeService._runtime_pointer = ProductService._runtime_pointer


class TheDatabaseDescriptor(unittest.TestCase):

    def setUp(self) -> None:
        self.root = MODULE_ROOT
        self.state = Path("C:/Users/somebody/AppData/Local/SovereignWorkspace/sovereign")

    def test_a_database_outside_the_install_root_no_longer_raises(self) -> None:
        """The regression itself. Before the fix this raised and took /v1/models with it."""
        service = _FakeService(self.root, self.state, self.state / "runtime" / "sovereign.db")
        descriptor = service._database_descriptor()
        self.assertTrue(descriptor.startswith(STATE_POINTER_PREFIX), descriptor)

    def test_it_leaks_no_absolute_host_path(self) -> None:
        """The whole point of pointerising here. A descriptor naming C:\\Users\\<name> would
        put the operator's account into the state summary — the P3-2 class of defect."""
        service = _FakeService(self.root, self.state, self.state / "runtime" / "sovereign.db")
        descriptor = service._database_descriptor()
        for needle in ("C:", "Users", "somebody", "\\"):
            self.assertNotIn(needle, descriptor, f"{descriptor!r} leaks {needle!r}")

    def test_it_still_names_the_file_it_describes(self) -> None:
        service = _FakeService(self.root, self.state, self.state / "runtime" / "sovereign.db")
        self.assertIn("runtime/sovereign.db", service._database_descriptor())

    def test_a_database_inside_the_install_root_keeps_the_original_scheme(self) -> None:
        """The pre-P4-4 layout must not change behaviour — a consumer resolving
        `sovereign://` pointers still gets one."""
        inside = self.root / "runtime" / "sovereign.db"
        service = _FakeService(self.root, self.root / "runtime", inside)
        descriptor = service._database_descriptor()
        self.assertTrue(descriptor.startswith(POINTER_PREFIX), descriptor)
        self.assertFalse(descriptor.startswith(STATE_POINTER_PREFIX))

    def test_the_two_schemes_are_distinguishable(self) -> None:
        """A consumer that can only resolve install-root pointers must be able to TELL that
        it has been handed something else, rather than resolving it wrongly."""
        self.assertNotEqual(POINTER_PREFIX, STATE_POINTER_PREFIX)
        self.assertFalse(STATE_POINTER_PREFIX.startswith(POINTER_PREFIX))

    def test_a_path_under_neither_root_is_reported_as_such(self) -> None:
        """Never guessed at, never silently dropped."""
        service = _FakeService(self.root, self.state, Path("D:/somewhere/else/x.db"))
        descriptor = service._database_descriptor()
        self.assertIn("outside both", descriptor)
        self.assertNotIn("somewhere", descriptor)

    def test_the_underlying_helper_still_refuses_an_escape(self) -> None:
        """The fix must not have loosened `artifact_pointer` itself — the tolerance lives at
        the call site, and the guard it tolerates is still armed."""
        with self.assertRaises(UnsafeArtifactPointer):
            artifact_pointer(Path("D:/elsewhere/x.db"), root=self.root)


class TheSharedRuntimeResolver(unittest.TestCase):
    """EPC-02 B-1b. Fixing only the database site left three more raising for the same reason,
    and the operator hit the next one within minutes: a run stalled at 25% because the EVIDENCE
    path could not be expressed. All four sites now share this resolver."""

    def setUp(self) -> None:
        self.root = MODULE_ROOT
        self.state = Path("C:/Users/somebody/AppData/Local/SovereignWorkspace/sovereign")
        self.service = _FakeService(self.root, self.state, self.state / "runtime" / "x.db")

    def test_the_evidence_path_that_stalled_a_run_now_resolves(self) -> None:
        """The exact shape from the operator's screenshot."""
        evidence = (self.state / "runtime" / "evidence" / "status"
                    / "session_67c99a1cf7824684b9927f9f3e3d2444"
                    / "job_700f0ad52e7a4038aa73bee827061b69.json")
        descriptor = self.service._runtime_pointer(evidence)
        self.assertTrue(descriptor.startswith(STATE_POINTER_PREFIX), descriptor)
        self.assertIn("evidence/status", descriptor)

    def test_no_runtime_descriptor_leaks_a_host_path(self) -> None:
        for path in (self.state / "runtime" / "x.db",
                     self.state / "runtime" / "evidence" / "a.json",
                     self.root / "runtime" / "inside.json"):
            descriptor = self.service._runtime_pointer(path)
            for needle in ("C:", "somebody", "\\"):
                self.assertNotIn(needle, descriptor, f"{descriptor!r} leaks {needle!r}")


class TheStateSchemeRoundTrips(unittest.TestCase):
    """EPC-02 B-1c. A scheme that is emitted but not resolvable is half a fix.

    Measured before this: /v1/evidence?pointer=sovereign-state://... returned
    "Artifact pointer must use the sovereign:// scheme". The descriptor named a real file that
    nothing could then open.
    """

    def setUp(self) -> None:
        import tempfile
        self.state = Path(tempfile.mkdtemp(prefix="sov-state-"))
        (self.state / "evidence" / "status").mkdir(parents=True)
        self.target = self.state / "evidence" / "status" / "job.json"
        self.target.write_text('{"ok": true}', encoding="utf-8")
        self.paths = ProductPaths(MODULE_ROOT, self.state,
                                  self.state / "x.db", self.state / "evidence")

    def test_a_state_pointer_resolves_back_to_the_file_it_names(self) -> None:
        pointer = STATE_POINTER_PREFIX + "evidence/status/job.json"
        self.assertEqual(self.paths.resolve_pointer(pointer, must_exist=True).resolve(),
                         self.target.resolve())

    def test_a_state_pointer_cannot_walk_out_of_the_state_root(self) -> None:
        """The containment property, which is the whole reason a pointer scheme exists."""
        for payload in ("../escaped.json", "evidence/../../escaped.json"):
            with self.assertRaises(UnsafeArtifactPointer, msg=payload):
                self.paths.resolve_pointer(STATE_POINTER_PREFIX + payload)

    def test_a_missing_file_is_refused_when_existence_is_required(self) -> None:
        with self.assertRaises(UnsafeArtifactPointer):
            self.paths.resolve_pointer(STATE_POINTER_PREFIX + "evidence/nope.json",
                                       must_exist=True)

    def test_an_install_root_pointer_still_resolves_through_the_same_method(self) -> None:
        """Adding the second scheme must not have broken the first."""
        pointer = POINTER_PREFIX + "sovereign_product/paths.py"
        self.assertTrue(self.paths.resolve_pointer(pointer, must_exist=True).is_file())


if __name__ == "__main__":
    unittest.main()
