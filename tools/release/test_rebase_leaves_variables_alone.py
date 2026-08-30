"""EPC-01 P3-4/P3-5 - the rebase must not undo the de-hardcoding.

The shipped adapters used to name this machine: `root` was an absolute path into the build
tree, and distillery/tokencenter additionally pinned the build operator's `python.exe`.
`install.ps1` and `rebase_adapters.py` rewrote both at install time, so it was disclosure
rather than a functional break - but every recipient still received the username and the
directory layout of the machine that cut the release.

They are now expressed as `${install_root}`, `${root}` and `${python312}`, which the shell
resolves from where it actually is. That is right by construction and survives the
installation being moved.

`rebase_adapters.py` sets interpreter pointers UNCONDITIONALLY - deliberately, because the
interpreter is a fact of the destination and the earlier value-matching logic could skip it
in silence. That unconditional rule would now overwrite `${python312}` with an absolute path
at install time, putting the installing machine's interpreter back into a file that had just
been cleaned of it and re-introducing the staleness the variable removes.

These tests hold both halves: a variable-valued pointer is left alone, and a genuinely
absolute stale pointer is still rewritten.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent / "rebase_adapters.py"


class RebaseLeavesVariablesAlone(unittest.TestCase):

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="sov-rebase-vars-"))
        (self.root / "shell" / "config").mkdir(parents=True)
        (self.root / "shell" / "modules").mkdir(parents=True)
        # A destination install.json, as install.ps1 writes it: real values, not the template.
        self._write(self.root / "shell/config/install.json", {
            "modules_root": str(self.root),
            "python_312": str(Path(sys.executable)),
            "optional_adapters": ["llamacpp"],
        })

    def _write(self, path: Path, document: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2), encoding="utf-8")

    #: The tool rebases its whole declared inventory and errors on a missing member, so the
    #: fixture must supply all of them. Only the adapter under test carries interesting values.
    INVENTORY_DEFAULTS = {
        "debate": ("D:/Product Software/Production Workspace/modules/debate",
                   "${root}/.venv/Scripts/python.exe", "app.py"),
        "distillery": ("D:/Product Software/Production Workspace/modules/distillery",
                       "C:/other/python.exe", "serve.py"),
        "llamacpp": ("C:/sovereign-workspace/optional-runtimes/llama.cpp",
                     "C:/sovereign-workspace/optional-runtimes/llama.cpp/current/llama-server.exe",
                     "--host"),
        "sovereign": ("D:/Product Software/Production Workspace/modules/sovereign",
                      "${root}/.venv/Scripts/python.exe", "-m"),
        "sow": ("D:/Product Software/Production Workspace/modules/sow", "${root}/e.exe", "."),
        "tokencenter": ("D:/Product Software/Production Workspace/modules/tokencenter",
                        "C:/other/python.exe", "piggybank.py"),
    }

    def _adapter(self, name: str, root: str, argv0: str, argv1: str) -> None:
        """Write the full inventory, with `name` carrying the values under test."""
        self._write(self.root / "shell/modules/schema.json", {})
        for other, (o_root, o_argv0, o_argv1) in self.INVENTORY_DEFAULTS.items():
            if other == name:
                continue
            argv = [o_argv0, o_argv1]
            if other == "llamacpp":
                argv = [o_argv0, o_argv1, "127.0.0.1", "--port", "5183", "--models-dir",
                        "C:/sovereign-workspace/optional-runtimes/llama.cpp/test-models"]
            self._write(self.root / "shell/modules" / f"{other}.json", {
                "id": other, "root": o_root, "state_class": "runnable",
                "launch": {"cwd": "${root}", "argv": argv},
            })
        self._write(self.root / "shell/modules" / f"{name}.json", {
            "id": name,
            "root": root,
            "state_class": "runnable",
            "launch": {"cwd": "${root}", "argv": [argv0, argv1]},
        })
        # The tool refuses to rebase onto a path that does not exist - correctly, since that
        # is how a mistyped destination would otherwise produce a confidently wrong install.
        for module in self.INVENTORY_DEFAULTS:
            (self.root / "modules" / module).mkdir(parents=True, exist_ok=True)

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOL), "--root", str(self.root), *args],
            capture_output=True, text=True, timeout=300,
        )

    def test_a_variable_valued_interpreter_is_not_rewritten(self) -> None:
        self._adapter("tokencenter", "${install_root}/modules/tokencenter",
                      "${python312}", "${root}/piggybank.py")
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = json.loads(
            (self.root / "shell/modules/tokencenter.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            after["launch"]["argv"][0], "${python312}",
            "the rebase overwrote a runtime-resolved interpreter with an absolute path"
        )
        self.assertEqual(after["root"], "${install_root}/modules/tokencenter")
        self.assertIn("NO-OP", result.stdout)

    def test_a_genuinely_absolute_stale_interpreter_is_still_rewritten(self) -> None:
        """The guard must not become a way for a real stale path to survive."""
        stale = "C:/some-other-machine/Python312/python.exe"
        self._adapter("distillery", "D:/Product Software/Production Workspace/modules/distillery",
                      stale, "serve.py")
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = json.loads(
            (self.root / "shell/modules/distillery.json").read_text(encoding="utf-8")
        )
        self.assertNotEqual(
            after["launch"]["argv"][0], stale,
            "an absolute interpreter path from another machine was left in place"
        )
        self.assertEqual(after["launch"]["argv"][0], str(Path(sys.executable)))

    def test_the_shipped_template_is_refused_rather_than_resolved(self) -> None:
        """Seeing the sentinel means the installer never ran. Failing loudly beats
        resolving '<set-by-installer>' into a relative path and rebasing against it."""
        self._write(self.root / "shell/config/install.json", {
            "modules_root": "<set-by-installer>",
            "python_312": "<set-by-installer>",
            "optional_adapters": ["llamacpp"],
        })
        self._adapter("tokencenter", "${install_root}/modules/tokencenter",
                      "${python312}", "${root}/piggybank.py")
        result = self._run()
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("set-by-installer", result.stderr)


if __name__ == "__main__":
    unittest.main()
