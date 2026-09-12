"""P2 shell dashboard/adapters: R17/F-019, R18/F-028, R24/F-018.

R17/F-019: preflight_toolchain marked a tool present:True whenever the process ran, ignoring the
           exit code -- so `py -3.12 --version` on a host without 3.12 (non-zero, empty stdout) was
           rendered "present".
R18/F-028: a wrongly-typed adapter raised TypeError/AttributeError that escaped load_all_adapters
           (which caught only AdapterError) and stopped the whole shell; duplicate ids silently
           overwrote; the forbidden-launcher check used substrings.
R24/F-018: the startup record asserted undeclared_writes=[] for a check that never ran.
"""
import json
import os
import sys
import unittest
from unittest import mock

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if WS not in sys.path:
    sys.path.insert(0, WS)

from shell.src import adapter as adapter_mod  # noqa: E402
from shell.src import probe as probe_mod  # noqa: E402
from shell.src import startup_test  # noqa: E402


class R17_ToolchainPresence(unittest.TestCase):
    def test_nonzero_exit_is_not_present(self) -> None:
        fake = mock.Mock(returncode=1, stdout="", stderr="No suitable Python runtime found")
        with mock.patch.object(probe_mod.subprocess, "run", return_value=fake):
            result = probe_mod.preflight_toolchain()
        self.assertFalse(result["py-3.12"]["present"])
        self.assertIn("exit 1", result["py-3.12"]["error"])

    def test_clean_exit_with_version_is_present(self) -> None:
        fake = mock.Mock(returncode=0, stdout="Python 3.12.4\n", stderr="")
        with mock.patch.object(probe_mod.subprocess, "run", return_value=fake):
            result = probe_mod.preflight_toolchain()
        self.assertTrue(result["py-3.12"]["present"])
        self.assertEqual(result["py-3.12"]["version"], "Python 3.12.4")


class R18_MalformedAdapterIsConfigError(unittest.TestCase):
    def setUp(self) -> None:
        with open(adapter_mod._SCHEMA_PATH, "r", encoding="utf-8") as f:
            self.schema = json.load(f)

    def test_a_top_level_array_is_an_adapter_error_not_a_crash(self) -> None:
        with self.assertRaises(adapter_mod.AdapterError):
            adapter_mod._validate_against_schema([1, 2, 3], self.schema)

    def test_a_string_timeout_is_an_adapter_error_not_a_typeerror(self) -> None:
        bad = {
            "id": "m", "display_name": "M", "state_class": "runnable",
            "launch": {"cwd": ".", "argv": ["x.exe"]},
            "readiness": {"kind": "http", "timeout_s": "soon", "poll_ms": 500},
            "identity": {"kind": "process_image"}, "open": {"kind": "none"},
            "stop": {"kind": "job_object", "grace_s": 5},
        }
        with self.assertRaises(adapter_mod.AdapterError):
            adapter_mod._validate_against_schema(bad, self.schema)

    def test_a_non_object_nested_field_is_an_adapter_error(self) -> None:
        bad = {
            "id": "m", "display_name": "M", "state_class": "runnable",
            "launch": {"cwd": ".", "argv": ["x.exe"]},
            "readiness": "http",  # not an object
            "identity": {"kind": "process_image"}, "open": {"kind": "none"},
            "stop": {"kind": "job_object", "grace_s": 5},
        }
        with self.assertRaises(adapter_mod.AdapterError):
            adapter_mod._validate_against_schema(bad, self.schema)

    def test_load_all_adapters_survives_a_malformed_file(self) -> None:
        import tempfile
        tmp = tempfile.mkdtemp(prefix="r18-")
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        # A schema copy and two adapters: one a JSON array (would crash), one absent-but-fine.
        with open(os.path.join(tmp, "schema.json"), "w", encoding="utf-8") as f:
            json.dump(self.schema, f)
        with open(os.path.join(tmp, "broken.json"), "w", encoding="utf-8") as f:
            json.dump([1, 2, 3], f)
        with mock.patch.object(adapter_mod, "_MODULES_DIR", tmp), \
             mock.patch.object(adapter_mod, "_SCHEMA_PATH", os.path.join(tmp, "schema.json")):
            result = adapter_mod.load_all_adapters()  # must not raise
        self.assertIn("broken.json", result)
        self.assertEqual(result["broken.json"]["error"], "CONFIG_ERROR")


class R24_UndeclaredWritesHonesty(unittest.TestCase):
    def test_undeclared_writes_is_not_performed(self) -> None:
        writes, checked = startup_test._undeclared_writes({})
        self.assertIsNone(writes, "an unperformed check must not report an empty list")
        self.assertFalse(checked)


if __name__ == "__main__":
    unittest.main(verbosity=2)
