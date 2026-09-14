"""
SWS-CORRECTIVE-01 workstream 3.1 - one launcher, one preflight, and claims that are true (C1).

Before this: `Sovereign Workspace.bat` ran the inner launcher directly so the outer preflight
never executed and no argument could reach either; `Start-Sovereign.ps1` carried a second
preflight that told the operator "Start-Shell.ps1 refuses in light mode" when that script only
printed advice; `-CheckOnly` exited 0 after reporting a missing interpreter; readiness accepted
any listener on the port; and `GIT_OPTIONAL_LOCKS` was unconditionally deleted.

The external launchers live OUTSIDE the product tree, beside it, so these tests locate them
relative to the repository root and skip with a clear reason if the deployment layout differs.
`-CheckOnly` is exercised for real: it is the one preflight path that starts nothing.
"""
from __future__ import annotations

import os
import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INNER = REPO_ROOT / "Start-Shell.ps1"
CUSTODY_ROOT = REPO_ROOT.parent
OUTER = CUSTODY_ROOT / "Start-Sovereign.ps1"
BATCH = CUSTODY_ROOT / "Sovereign Workspace.bat"


def _run(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          env=env, cwd=str(CUSTODY_ROOT))


def _ps(script: Path, *args: str) -> subprocess.CompletedProcess:
    return _run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(script), *args])


NEWLINE = chr(10)


def _executable_lines(path: Path) -> list[str]:
    """The lines a shell actually runs: block comments, `#` and `rem` lines removed.

    A file is allowed - and expected - to describe the defect it fixed. What must not survive
    is the CLAIM in executable code, so the checks below read only what executes.
    """
    out = []
    in_block = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if in_block:
            if "#>" in line:
                in_block = False
            continue
        if line.startswith("<#"):
            in_block = "#>" not in line
            continue
        if line.startswith("#") or line.lower().startswith("rem "):
            continue
        # A trailing comment on an executable line is still not executable.
        out.append(line.split("#", 1)[0] if not line.startswith('"') else line)
    return out


class LauncherContract(unittest.TestCase):

    def setUp(self) -> None:
        self.assertTrue(INNER.is_file(), "the supported launcher is missing")

    # -- one implementation --------------------------------------------------
    def test_the_outer_launcher_delegates_rather_than_reimplementing_preflight(self) -> None:
        if not OUTER.is_file():
            self.skipTest(f"external launcher not deployed at {OUTER}")
        body = NEWLINE.join(_executable_lines(OUTER))
        self.assertIn("Start-Shell.ps1", body, "the outer launcher does not delegate")
        # The markers of a second preflight implementation.
        for marker, what in (
            ("nvidia-smi", "a duplicated GPU census"),
            ("Get-NetTCPConnection", "a duplicated port census"),
            ("AppsUseLightTheme", "a duplicated theme check"),
        ):
            self.assertNotIn(
                marker, body,
                f"the outer launcher still carries {what}; preflight must live in one file")

    def test_the_batch_file_goes_through_the_outer_launcher(self) -> None:
        if not BATCH.is_file():
            self.skipTest(f"batch launcher not deployed at {BATCH}")
        body = NEWLINE.join(_executable_lines(BATCH))
        self.assertIn("Start-Sovereign.ps1", body,
                      "the batch file still bypasses the outer launcher")
        self.assertNotIn("Start-Shell.ps1", body,
                         "the batch file still invokes the inner launcher directly")

    def test_the_batch_file_forwards_its_arguments(self) -> None:
        if not BATCH.is_file():
            self.skipTest(f"batch launcher not deployed at {BATCH}")
        text = NEWLINE.join(_executable_lines(BATCH))
        self.assertIn("%*", text,
                      "the batch file forwards no arguments, so -Port/-NoBrowser/-CheckOnly "
                      "cannot be reached through it")
        self.assertIn('"%~dp0Start-Sovereign.ps1"', text,
                      "the forwarded script path is unquoted; a folder with a space breaks it")

    def test_the_batch_file_propagates_the_exit_code(self) -> None:
        if not BATCH.is_file():
            self.skipTest(f"batch launcher not deployed at {BATCH}")
        text = NEWLINE.join(_executable_lines(BATCH))
        self.assertIn("ERRORLEVEL", text)
        self.assertIn("exit /b", text.lower())

    # -- claims that must be true --------------------------------------------
    def test_no_launcher_claims_light_mode_blocks_startup(self) -> None:
        """The recorded C1 falsehood: the outer preflight said the inner one refuses."""
        for path in (INNER, OUTER):
            if not path.is_file():
                continue
            for line in _executable_lines(path):
                if "light" not in line.lower():
                    continue
                self.assertNotRegex(
                    line.lower(), r"refus|will not start|cannot start|blocks",
                    f"{path.name} still claims light mode blocks startup: {line.strip()!r}")

    def test_no_launcher_writes_the_windows_theme(self) -> None:
        for path in (INNER, OUTER):
            if not path.is_file():
                continue
            self.assertNotIn(
                "Set-ItemProperty -Path $themeKey", path.read_text(encoding="utf-8"),
                f"{path.name} modifies the operator's Windows theme")

    def test_the_caller_environment_is_restored_not_deleted(self) -> None:
        """GIT_OPTIONAL_LOCKS must survive a launcher that set it."""
        text = INNER.read_text(encoding="utf-8")
        self.assertIn("priorOptionalLocks", text,
                      "the launcher does not preserve a pre-existing GIT_OPTIONAL_LOCKS")

    def test_readiness_checks_service_identity_not_a_listener(self) -> None:
        text = INNER.read_text(encoding="utf-8")
        self.assertIn("/api/shell-info", text,
                      "the launcher still treats any listener on the port as the shell")
        self.assertIn("SWS-UI-001", text,
                      "the launcher does not check the expected service identity")

    def test_readiness_window_message_matches_the_loop(self) -> None:
        text = INNER.read_text(encoding="utf-8")
        self.assertIn("for ($i = 0; $i -lt 40; $i++)", text)
        self.assertIn("TimeoutSec 2", text)
        self.assertIn("Start-Sleep -Milliseconds 250", text)
        self.assertIn("~90s", text)
        self.assertNotRegex(text, r"within 10s")

    def test_pythondontwritebytecode_is_restored(self) -> None:
        text = INNER.read_text(encoding="utf-8")
        self.assertIn("prevDontWriteBytecode", text)
        self.assertIn("Remove-Item Env:PYTHONDONTWRITEBYTECODE", text)

    def test_stray_scan_sees_commandline_not_only_image_path(self) -> None:
        text = INNER.read_text(encoding="utf-8")
        self.assertIn("Win32_Process", text)
        self.assertIn("CommandLine", text)
        self.assertIn("-m\\s+shell\\.src", text)

    # -- CheckOnly, executed for real ----------------------------------------
    def test_check_only_starts_nothing_and_reports_accurately(self) -> None:
        before = self._shell_processes()
        result = _ps(INNER, "-CheckOnly")
        out = result.stdout + result.stderr
        self.assertIn("nothing started", out.lower(), out[-2000:])
        self.assertEqual(result.returncode, 0, out[-2000:])
        self.assertEqual(self._shell_processes(), before,
                         "-CheckOnly started a module process")

    def test_check_only_exits_non_zero_when_something_blocks(self) -> None:
        """A blocking finding must reach the exit code, not only the transcript.

        The port is occupied deliberately, with a listener this test owns and closes.
        """
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            port = sock.getsockname()[1]
            result = _ps(INNER, "-CheckOnly", "-Port", str(port))
            out = result.stdout + result.stderr
            self.assertEqual(
                result.returncode, 1,
                "-CheckOnly reported a blocking problem and still exited 0:\n" + out[-2000:])
            self.assertIn("BLOCKED", out)
        finally:
            sock.close()

    def test_check_only_reaches_through_the_outer_launcher(self) -> None:
        if not OUTER.is_file():
            self.skipTest(f"external launcher not deployed at {OUTER}")
        result = _ps(OUTER, "-CheckOnly")
        out = result.stdout + result.stderr
        self.assertIn("nothing started", out.lower(), out[-2000:])
        self.assertEqual(result.returncode, 0, out[-2000:])

    def test_a_blocking_result_propagates_through_the_outer_launcher(self) -> None:
        if not OUTER.is_file():
            self.skipTest(f"external launcher not deployed at {OUTER}")
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            port = sock.getsockname()[1]
            result = _ps(OUTER, "-CheckOnly", "-Port", str(port))
            self.assertEqual(
                result.returncode, 1,
                "the outer launcher swallowed a blocking exit code:\n"
                + (result.stdout + result.stderr)[-2000:])
        finally:
            sock.close()

    def test_the_launcher_states_which_layouts_it_supports(self) -> None:
        text = INNER.read_text(encoding="utf-8")
        self.assertIn("source checkout", text)
        self.assertIn("installed artifact", text)

    @staticmethod
    def _shell_processes() -> set:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "(Get-Process python,pythonw -ErrorAction SilentlyContinue | "
             "Select-Object -ExpandProperty Id) -join ','"],
            capture_output=True, text=True, timeout=60)
        return set(filter(None, result.stdout.strip().split(",")))


if __name__ == "__main__":
    unittest.main()
