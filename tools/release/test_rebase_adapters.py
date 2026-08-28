from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("rebase_adapters.py")
OLD_ROOT = "D:/Product Software/Production Workspace"
OLD_PYTHON = "C:/Users/Sslaw/AppData/Local/Programs/Python/Python312/python.exe"


class RebaseAdaptersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.modules_root = self.root / "candidate"
        self.python = self.root / "python.exe"
        self.python.touch()
        (self.root / "shell/config").mkdir(parents=True)
        (self.root / "shell/modules").mkdir(parents=True)
        install = {"modules_root": str(self.modules_root), "python_312": str(self.python)}
        self._write(self.root / "shell/config/install.json", install)
        documents = {
            "debate.json": {"root": f"{OLD_ROOT}/modules/debate"},
            "distillery.json": {"root": f"{OLD_ROOT}/modules/distillery", "launch": {"argv": [OLD_PYTHON, f"{OLD_ROOT}/modules/distillery/serve.py"]}},
            "llamacpp.json": {"root": f"{OLD_ROOT}/runtime/llama.cpp", "launch": {"argv": [f"{OLD_ROOT}/runtime/llama.cpp/current/llama-server.exe", "--host", "127.0.0.1", "--port", "5183", "--models-dir", f"{OLD_ROOT}/runtime/llama.cpp/test-models"]}},
            "schema.json": {},
            "sovereign.json": {"root": f"{OLD_ROOT}/modules/sovereign"},
            "sow.json": {"root": f"{OLD_ROOT}/modules/sow"},
            "tokencenter.json": {"root": f"{OLD_ROOT}/modules/tokencenter", "launch": {"argv": [OLD_PYTHON, f"{OLD_ROOT}/modules/tokencenter/piggybank.py"]}},
        }
        for name, document in documents.items():
            self._write(self.root / "shell/modules" / name, document)
        for path in (
            self.modules_root / "modules/debate",
            self.modules_root / "modules/distillery",
            self.modules_root / "modules/sovereign",
            self.modules_root / "modules/sow",
            self.modules_root / "modules/tokencenter",
            self.modules_root / "runtime/llama.cpp/current",
            self.modules_root / "runtime/llama.cpp/test-models",
        ):
            path.mkdir(parents=True, exist_ok=True)
        (self.modules_root / "modules/distillery/serve.py").touch()
        (self.modules_root / "modules/tokencenter/piggybank.py").touch()
        (self.modules_root / "runtime/llama.cpp/current/llama-server.exe").touch()

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write(path: Path, value: object) -> None:
        path.write_text(json.dumps(value) + "\n", encoding="utf-8", newline="\n")

    def _run(self, *extra: str) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--root", str(self.root), *extra],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def test_mapping_and_backup_creation(self) -> None:
        original = (self.root / "shell/modules/distillery.json").read_bytes()
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads((self.root / "shell/modules/distillery.json").read_text(encoding="utf-8"))
        self.assertEqual(document["root"], str(self.modules_root / "modules/distillery"))
        self.assertEqual(document["launch"]["argv"][0], str(self.python))
        self.assertEqual((self.root / "shell/modules/distillery.json.pre-rebase").read_bytes(), original)

    def test_second_run_is_no_op(self) -> None:
        self.assertEqual(self._run().returncode, 0)
        result = self._run()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "NO-OP\n")

    def test_refusal_makes_no_writes(self) -> None:
        (self.modules_root / "runtime/llama.cpp/current/llama-server.exe").unlink()
        before = (self.root / "shell/modules/distillery.json").read_bytes()
        result = self._run("--dry-run")
        self.assertEqual(result.returncode, 2)
        self.assertIn("target path does not exist", result.stderr)
        self.assertEqual((self.root / "shell/modules/distillery.json").read_bytes(), before)
        self.assertFalse((self.root / "shell/modules/distillery.json.pre-rebase").exists())


if __name__ == "__main__":
    unittest.main()
