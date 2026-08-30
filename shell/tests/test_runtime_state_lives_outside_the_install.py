"""EPC-01 P4-4 — runtime state must not live inside the install root.

This is the root cause of two further defects, which is why it is worth its own guard:

  * **P0-5** — `uninstall.ps1` compares the whole install tree against its manifest and
    refuses if anything was added. The product's own runtime state is an addition, so
    uninstall worked only on an installation that had never been used.
  * **P1-1** — `install.ps1` refuses a non-empty destination, so an upgrade cannot reuse a
    destination that holds live state.

State that lives inside the thing being replaced cannot survive replacing it. Both defects
dissolve once state has a home of its own.

`${state_root}` resolves to `%LOCALAPPDATA%\\SovereignWorkspace\\<module-id>` — one directory
per module, never shared, so a declaration cannot reach another module's state.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shell.src import adapter as adapter_module  # noqa: E402

#: debate's config.json is a SEEDED document the application rewrites in place, not pure
#: runtime state. Relocating it requires the installer to place a copy in the state root
#: first, so it is deliberately still declared under ${root} and recorded here rather than
#: half-moved. Every other declared write must be outside the install tree.
SEEDED_DOCUMENTS = {"config.json"}


def _compiled():
    return {
        name: entry
        for name, entry in adapter_module.load_all_adapters().items()
        if not entry.get("error")
    }


class RuntimeStateLivesOutsideTheInstall(unittest.TestCase):

    def test_adapters_actually_load(self) -> None:
        """Without this the assertions below could pass on an empty set."""
        self.assertGreaterEqual(len(_compiled()), 4, "too few adapters loaded to be checked")

    def test_the_state_root_is_under_localappdata(self) -> None:
        root = adapter_module.workspace_state_root()
        self.assertIn(
            adapter_module.STATE_ROOT_DIRNAME, root,
            f"the workspace state root is not the declared directory: {root}"
        )
        self.assertNotIn(
            str(REPO_ROOT).replace("\\", "/").lower(), root.lower(),
            "the state root resolves inside the install tree, which is the defect"
        )

    def test_each_module_has_its_own_state_root(self) -> None:
        roots = {name: entry["state_root"] for name, entry in _compiled().items()}
        self.assertEqual(
            len(set(roots.values())), len(roots),
            f"two modules share a state root, so one can reach the other's state: {roots}"
        )
        for name, root in roots.items():
            with self.subTest(module=name):
                self.assertTrue(
                    root.rstrip("/").endswith("/" + name),
                    f"{name}'s state root is not named for it: {root}"
                )

    def test_no_declared_write_lands_inside_the_install_root(self) -> None:
        install_root = str(REPO_ROOT).replace("\\", "/").lower().rstrip("/")
        offenders = []
        for name, entry in _compiled().items():
            for target in entry.get("runtime_writes", []):
                if Path(target).name in SEEDED_DOCUMENTS:
                    continue
                if target.replace("\\", "/").lower().startswith(install_root + "/"):
                    offenders.append(f"{name}: {target}")
        self.assertEqual(
            offenders, [],
            "these modules still write inside the install tree, which is what blocks "
            "uninstall (P0-5) and upgrade (P1-1):\n  " + "\n  ".join(offenders)
        )

    def test_every_module_is_told_where_its_state_root_is(self) -> None:
        """A module that reads the variable must not depend on someone having remembered to
        declare it in that adapter."""
        for name, entry in _compiled().items():
            launch = entry.get("launch")
            if not launch:
                continue
            with self.subTest(module=name):
                self.assertEqual(
                    launch["env_set"].get(adapter_module.STATE_ROOT_ENV),
                    entry["state_root"],
                    f"{name} is not told its own state root"
                )

    def test_a_write_escaping_both_roots_is_still_refused(self) -> None:
        """H-5 is EXTENDED to a second named root, not relaxed. A path outside both must
        still be a configuration error."""
        escaping = {
            "id": "probe",
            "display_name": "Probe",
            "description": "escape probe",
            "state_class": "not_started",
            "root": str(REPO_ROOT).replace("\\", "/"),
            "runtime_writes": ["${root}/../escaped"],
        }
        with self.assertRaises(adapter_module.AdapterError) as caught:
            adapter_module.compile_adapter(escaping)
        self.assertIn("H-5", str(caught.exception))

    def test_a_write_into_another_modules_state_root_is_refused(self) -> None:
        """One module must not declare a write into another's state."""
        other = adapter_module.module_state_root("sovereign")
        trespassing = {
            "id": "probe",
            "display_name": "Probe",
            "description": "trespass probe",
            "state_class": "not_started",
            "root": str(REPO_ROOT).replace("\\", "/"),
            "runtime_writes": [other + "/runtime"],
        }
        with self.assertRaises(adapter_module.AdapterError):
            adapter_module.compile_adapter(trespassing)


if __name__ == "__main__":
    unittest.main()
