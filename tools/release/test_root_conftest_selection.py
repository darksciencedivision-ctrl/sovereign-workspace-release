#!/usr/bin/env python
"""The root conftest's stale-exemption check must not abort a run that selects tests by node id.

`_assert_enumeration_is_current` compared, per file, the CHECKOUT_ONLY ids it collected with the ids
listed. A run naming one test of such a file (`pytest file.py::Class::test`) collected only that id,
so every other listed id of the file looked renamed and pytest ended in INTERNALERROR with no test
run. The check itself must still fire for a genuinely stale id in a file collected whole.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("root_conftest_under_test", ROOT / "conftest.py")
root_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(root_conftest)

FILE = "tools/release/test_package_boundary_gate.py"
ONE = f"{FILE}::TestCleanedWorktree::test_archive_passes"


class RootConftestSelectionTests(unittest.TestCase):
    def test_a_node_id_selection_is_not_reported_as_a_rename(self) -> None:
        self.assertIn(ONE, root_conftest.CHECKOUT_ONLY)
        selected = root_conftest._files_selected_by_node_id([ONE])
        self.assertEqual({FILE}, selected)
        root_conftest._assert_enumeration_is_current({ONE}, selected)  # must not raise

    def test_an_absolute_node_id_path_is_normalised(self) -> None:
        selected = root_conftest._files_selected_by_node_id([str(ROOT / FILE) + "::X::y"])
        self.assertEqual({FILE}, selected)

    def test_a_whole_file_run_still_detects_a_stale_id(self) -> None:
        with self.assertRaises(RuntimeError):
            root_conftest._assert_enumeration_is_current({ONE}, root_conftest._files_selected_by_node_id([FILE]))


if __name__ == "__main__":
    unittest.main()
