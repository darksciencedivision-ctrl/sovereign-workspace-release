"""EPC-01 P3-6 — a module whose runtime is absent must say so, and the shell already does.

A CORRECTION IS RECORDED HERE, against the punch list rather than against the code.

Punch List V7 listed P3-6 as: *"llamacpp.json declares state_class: runnable against a
placeholder path that exists on no machine, and the schema offers no third state for 'present
but not installed'."* Both halves of that sentence are true of the JSON read on its own, and
the conclusion drawn from them — that the shell offers an uninstallable module as startable —
is false.

The shell already resolves this at runtime, and better than a third enum value would:

  * `states.py:361` computes `runtime_present` from the declared runtime path;
  * `states.py:337` refuses a start with `Runtime not installed: <path>`, naming the path;
  * `app.js:559` renders the card with that reason instead of a bare state;
  * `test_module_visibility.py::test_absent_optional_runtime_is_present_and_unavailable`
    already pins the whole behaviour — present, honestly unavailable, path named.

`state_class` declares what KIND of module this is, not whether it happens to be installed on
this host. That separation is correct: installability is a property of the machine and has to
be evaluated there, not frozen into a JSON file that ships to every machine.

An earlier pass of this work "fixed" P3-6 by making the loader report a missing root as
CONFIG_ERROR. It broke three existing tests, and rightly: it replaced a card that says
"Runtime not installed: C:/..." with a generic configuration error, losing the path the
operator needs. It was reverted. The item is closed as a correction, and this file guards the
behaviour that was already right so a future change cannot quietly take it away.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shell.src import adapter as adapter_module  # noqa: E402
from shell.src import states as states_module  # noqa: E402


class AbsentRuntimeIsDeclaredHonestly(unittest.TestCase):

    def test_the_shell_can_tell_whether_a_declared_runtime_is_present(self) -> None:
        """The capability the punch list said was missing. It is not."""
        self.assertTrue(
            hasattr(states_module.ModuleRunner, "runtime_present"),
            "the shell has no runtime_present concept, so an absent runtime would be "
            "indistinguishable from a stopped one"
        )

    def test_a_start_refusal_names_the_missing_path(self) -> None:
        """A refusal that does not say WHICH path is missing sends the operator to the source."""
        source = (REPO_ROOT / "shell" / "src" / "states.py").read_text(encoding="utf-8")
        self.assertIn(
            "Runtime not installed", source,
            "the start refusal no longer says the runtime is not installed"
        )
        self.assertRegex(
            source, r"Runtime not installed:\s*\{self\.runtime_path\}",
            "the refusal no longer interpolates the missing path, so the operator is told "
            "something is missing without being told what"
        )

    def test_the_card_renders_the_reason_rather_than_a_bare_state(self) -> None:
        app_js = (REPO_ROOT / "shell" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("runtime_present === false", app_js)
        self.assertIn("Runtime not installed", app_js)

    def test_every_adapter_still_loads_without_error(self) -> None:
        """The regression the reverted 'fix' caused: adapters must not be turned into
        CONFIG_ERROR merely because their runtime is not installed on this host."""
        adapters = adapter_module.load_all_adapters()
        errored = {
            name: entry.get("reason")
            for name, entry in adapters.items()
            if entry.get("error")
        }
        self.assertEqual(
            errored, {},
            "adapters failed to load. An absent optional runtime is NOT a configuration "
            "error — it is a present module that is honestly unavailable:\n  "
            + "\n  ".join(f"{k}: {v}" for k, v in errored.items())
        )

    def test_the_optional_adapter_is_declared_optional_where_that_matters(self) -> None:
        """llamacpp's root is a placeholder by design; the install configuration is where
        that is declared, and rebase_adapters honours it with SKIPPED-WITH-RECORD."""
        install = json.loads(
            (REPO_ROOT / "shell" / "config" / "install.json").read_text(encoding="utf-8")
        )
        self.assertIn(
            "llamacpp", install.get("optional_adapters", []),
            "llamacpp declares a placeholder runtime path, so it must be listed as an "
            "optional adapter or the installer will treat its absence as fatal"
        )

    def test_the_placeholder_is_still_a_placeholder(self) -> None:
        """If someone points llamacpp at a real path, this test should notice and be updated
        along with the reasoning above — the correction rests on it being a placeholder."""
        declared = json.loads(
            (REPO_ROOT / "shell" / "modules" / "llamacpp.json").read_text(encoding="utf-8")
        )
        root = declared.get("root", "")
        if os.path.isdir(root):
            self.skipTest(f"llamacpp is genuinely installed at {root} on this host")
        self.assertIn(
            "PLACEHOLDER", declared.get("description", "").upper(),
            "llamacpp's root does not exist and its description no longer says the path is a "
            "placeholder — one of the two must change"
        )


if __name__ == "__main__":
    unittest.main()
