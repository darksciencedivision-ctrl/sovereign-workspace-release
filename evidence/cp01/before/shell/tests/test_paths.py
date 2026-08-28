"""
H-5 — canonical path containment (R3-3).

Containment must be by canonical resolution (GetFinalPathNameByHandleW, case-folded,
os.path.commonpath), never by prefix-string comparison. Each test below is a case where a
prefix comparison gives the wrong answer.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

from shell.src.adapter import AdapterError, _canonical, is_contained, reject_unc_and_device


class TestCanonicalContainment(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sws-h5-")
        self.root = os.path.join(self.tmp, "root")
        os.makedirs(os.path.join(self.root, "inside"), exist_ok=True)
        self.outside = os.path.join(self.tmp, "outside")
        os.makedirs(self.outside, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- the six required cases --------------------------------------------
    def test_dotdot_escape_rejected(self):
        """'..' that climbs out of the root is not contained."""
        escape = os.path.join(self.root, "inside", "..", "..", "outside")
        self.assertFalse(is_contained(self.root, escape))

    def test_junction_escape_rejected(self):
        """A junction inside the root pointing outside it resolves outside and is rejected.

        A prefix comparison would accept this, because the junction's own path starts with the
        root. This is the case H-5 exists for.
        """
        link = os.path.join(self.root, "jump")
        # mklink is a cmd.exe builtin, so cmd.exe is required here. This is test tooling that
        # creates a filesystem object in a temp directory; it is not a module launch vector.
        proc = subprocess.run(["cmd.exe", "/c", "mklink", "/J", link, self.outside],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            self.skipTest("mklink /J unavailable: {}".format(
                (proc.stderr or proc.stdout).strip()))
        self.assertTrue(os.path.isdir(link))

        target_file = os.path.join(self.outside, "loot.txt")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write("x")
        via_junction = os.path.join(link, "loot.txt")

        # Sanity: a naive prefix check WOULD accept it.
        self.assertTrue(via_junction.lower().startswith(self.root.lower()),
                        "precondition: the junction path is prefixed by the root")
        # Canonical containment must not.
        self.assertFalse(is_contained(self.root, via_junction))

    def test_case_variant_is_inside(self):
        """A differently-cased spelling of an inside path is still inside."""
        inside = os.path.join(self.root, "inside")
        self.assertTrue(is_contained(self.root, inside.upper()))
        self.assertTrue(is_contained(self.root.upper(), inside.lower()))

    def test_unc_rejected(self):
        with self.assertRaises(AdapterError):
            reject_unc_and_device(r"\\server\share\file.txt")
        self.assertFalse(is_contained(self.root, r"\\server\share\file.txt"))

    def test_device_path_rejected(self):
        for p in (r"\\.\PhysicalDrive0", r"\\?\D:\root\inside", "//./PhysicalDrive0", "//?/D:/x"):
            with self.subTest(path=p):
                with self.assertRaises(AdapterError):
                    reject_unc_and_device(p)
                self.assertFalse(is_contained(self.root, p))

    def test_sibling_with_shared_prefix_rejected(self):
        """D:\\root-evil is not inside D:\\root, though the string prefix matches."""
        evil = self.root + "-evil"
        os.makedirs(evil, exist_ok=True)
        self.assertTrue(evil.lower().startswith(self.root.lower()),
                        "precondition: the sibling shares a string prefix with the root")
        self.assertFalse(is_contained(self.root, evil))
        self.assertFalse(is_contained(self.root, os.path.join(evil, "f.txt")))

    # -- supporting behaviour ----------------------------------------------
    def test_root_contains_itself(self):
        self.assertTrue(is_contained(self.root, self.root))

    def test_nonexistent_path_inside_root_is_contained(self):
        """A path that does not exist yet falls back to realpath and is still resolved."""
        future = os.path.join(self.root, "not-created-yet", "file.log")
        self.assertFalse(os.path.exists(future))
        self.assertTrue(is_contained(self.root, future))

    def test_canonical_is_casefolded_and_absolute(self):
        c = _canonical(self.root)
        self.assertEqual(c, c.casefold())
        self.assertTrue(os.path.isabs(c))

    def test_canonical_strips_extended_prefix(self):
        self.assertFalse(_canonical(self.root).startswith("\\\\?\\"))

    def test_different_drive_is_not_contained(self):
        """commonpath raises across drives; that must read as 'not contained', not as a crash."""
        other = "C:\\Windows" if self.root[0].lower() != "c" else "D:\\"
        self.assertFalse(is_contained(self.root, other))


class TestAdapterContainmentEnforcement(unittest.TestCase):
    """The compiler must refuse an adapter whose declared paths escape its root."""

    def _adapter(self, **over):
        base = {
            "id": "fix",
            "display_name": "Fixture",
            "description": "test",
            "state_class": "not_started",
            "root": "D:/Product Software/Production Workspace/modules/debate",
            "runtime_writes": [],
            "open": {"kind": "none"},
        }
        base.update(over)
        return base

    def test_runtime_writes_inside_root_ok(self):
        from shell.src.adapter import compile_adapter
        a = self._adapter(runtime_writes=["${root}/logs"])
        compiled = compile_adapter(a)
        self.assertEqual(len(compiled["runtime_writes"]), 1)

    def test_runtime_writes_escaping_root_rejected(self):
        from shell.src.adapter import compile_adapter
        a = self._adapter(runtime_writes=["${root}/../../../evidence"])
        with self.assertRaises(AdapterError) as ctx:
            compile_adapter(a)
        self.assertIn("H-5", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
