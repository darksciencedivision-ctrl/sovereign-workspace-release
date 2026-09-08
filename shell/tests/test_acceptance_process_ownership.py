"""Parsed --root ownership, not substring matching. Cleanup must reap descendants."""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from ctypes import wintypes
from pathlib import Path

_K32 = ctypes.WinDLL("kernel32", use_last_error=True)
_OpenProcess = _K32.OpenProcess
_OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_OpenProcess.restype = wintypes.HANDLE
_WaitForSingleObject = _K32.WaitForSingleObject
_WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_WaitForSingleObject.restype = wintypes.DWORD
_CloseHandle = _K32.CloseHandle
_PROCESS_QUERY = 0x1000
_SYNCHRONIZE = 0x00100000
_WAIT_TIMEOUT = 258

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "tools" / "acceptance" / "process_ownership.ps1"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fixture_ownership.py"
PS = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]


def _ps(script: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        PS + ["-Command", script],
        capture_output=True, text=True, timeout=timeout)


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    handle = _OpenProcess(_PROCESS_QUERY | _SYNCHRONIZE, False, pid)
    if not handle:
        return False
    try:
        return _WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT
    finally:
        _CloseHandle(handle)


def _wait_dead(pid: int, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return not _alive(pid)


def _spawn(extra: list[str], sleep: float = 60.0) -> subprocess.Popen:
    cmd = [sys.executable, "-B", str(FIXTURE), "--sleep", str(sleep)] + extra
    return subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _read_pid_line(proc: subprocess.Popen, prefix: str, timeout: float = 8.0) -> int:
    deadline = time.time() + timeout
    assert proc.stdout is not None
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                err = proc.stderr.read() if proc.stderr else ""
                raise RuntimeError("fixture exited %s: %s" % (proc.returncode, err))
            time.sleep(0.05)
            continue
        line = line.strip()
        if line.startswith(prefix + " "):
            return int(line.split()[1])
    raise TimeoutError("no %s line from fixture" % prefix)


class OwnershipPathAndArgv(unittest.TestCase):
    def setUp(self) -> None:
        self.install = Path(tempfile.mkdtemp(prefix="sws-own-install-"))
        (self.install / "modules" / "sovereign").mkdir(parents=True)
        self.expected = str(self.install / "modules" / "sovereign")

    def tearDown(self) -> None:
        try:
            for root, dirs, files in os.walk(self.install, topdown=False):
                for name in files:
                    Path(root, name).unlink(missing_ok=True)
                for name in dirs:
                    Path(root, name).rmdir()
            self.install.rmdir()
        except OSError:
            pass

    def _eval(self, snippet: str) -> dict:
        install = str(self.install).replace("'", "''")
        expected = self.expected.replace("'", "''")
        script = (
            f". '{HELPER}'\n"
            f"$install = '{install}'\n"
            f"$expected = Get-ExpectedSovereignRoot $install\n"
            + snippet + "\n"
            "$out | ConvertTo-Json -Compress\n"
        )
        proc = _ps(script)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        line = proc.stdout.strip().splitlines()[-1]
        return json.loads(line)

    def test_forward_slash_root_matches_backslash_expected(self) -> None:
        fwd = self.expected.replace("\\", "/")
        r = self._eval(
            f"$cmd = 'python.exe -m sovereign_product.server --root {fwd} --port 5175'\n"
            "$out = @{ "
            "match = [bool](Test-CommandLineOwnsExpectedRoot -CommandLine $cmd -ExpectedRoot $expected); "
            "parsed = Get-CommandLineNamedArgument -CommandLine $cmd -Name 'root'; "
            "contains = $cmd.ToLower().Contains($install.ToLower()) }"
        )
        self.assertTrue(r["match"])
        self.assertFalse(r["contains"], "the old substring check must still fail on forward slashes")

    def test_backslash_root_matches(self) -> None:
        r = self._eval(
            f"$cmd = 'python.exe --root {self.expected} --host 127.0.0.1'\n"
            "$out = @{ match = [bool](Test-CommandLineOwnsExpectedRoot $cmd $expected) }"
        )
        self.assertTrue(r["match"])

    def test_quoted_path_with_spaces(self) -> None:
        spaced = Path(tempfile.mkdtemp(prefix="sws own spaced "))
        try:
            (spaced / "modules" / "sovereign").mkdir(parents=True)
            root = spaced / "modules" / "sovereign"
            quoted = '"' + str(root) + '"'
            install = str(spaced).replace("'", "''")
            script = (
                f". '{HELPER}'\n"
                f"$install = '{install}'\n"
                "$expected = Get-ExpectedSovereignRoot $install\n"
                f"$cmd = '\"C:\\Python\\python.exe\" -m sovereign_product.server --root {quoted}'\n"
                "$out = @{ match = [bool](Test-CommandLineOwnsExpectedRoot $cmd $expected); "
                "parsed = Get-CommandLineNamedArgument -CommandLine $cmd -Name 'root' }\n"
                "$out | ConvertTo-Json -Compress\n"
            )
            proc = _ps(script)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            r = json.loads(proc.stdout.strip().splitlines()[-1])
            self.assertTrue(r["match"], r)
        finally:
            for root, dirs, files in os.walk(spaced, topdown=False):
                for name in files:
                    Path(root, name).unlink(missing_ok=True)
                for name in dirs:
                    Path(root, name).rmdir()
            try:
                spaced.rmdir()
            except OSError:
                pass

    def test_case_insensitive_match(self) -> None:
        flipped = self.expected.swapcase()
        r = self._eval(
            f"$cmd = 'python.exe --root {flipped}'\n"
            "$out = @{ match = [bool](Test-CommandLineOwnsExpectedRoot $cmd $expected) }"
        )
        self.assertTrue(r["match"])

    def test_equals_form_of_root_flag(self) -> None:
        fwd = self.expected.replace("\\", "/")
        r = self._eval(
            f"$cmd = 'python.exe --root={fwd}'\n"
            "$out = @{ match = [bool](Test-CommandLineOwnsExpectedRoot $cmd $expected) }"
        )
        self.assertTrue(r["match"])

    def test_sibling_prefix_path_is_rejected(self) -> None:
        sibling = Path(str(self.install) + "-other")
        (sibling / "modules" / "sovereign").mkdir(parents=True)
        try:
            sib_root = str(sibling / "modules" / "sovereign")
            r = self._eval(
                f"$cmd = 'python.exe --root {sib_root}'\n"
                "$out = @{ match = [bool](Test-CommandLineOwnsExpectedRoot $cmd $expected); "
                f"contains = '{sib_root}'.ToLower().Contains($install.ToLower()) }}"
            )
            self.assertFalse(r["match"])
            self.assertTrue(r["contains"], "sibling still matches a naive prefix/contains check")
        finally:
            for root, dirs, files in os.walk(sibling, topdown=False):
                for name in files:
                    Path(root, name).unlink(missing_ok=True)
                for name in dirs:
                    Path(root, name).rmdir()
            try:
                sibling.rmdir()
            except OSError:
                pass

    def test_unrelated_argument_containing_path_is_rejected(self) -> None:
        log_path = str(Path(self.expected) / "server.log")
        r = self._eval(
            f"$cmd = 'python.exe --log {log_path} --port 5175'\n"
            "$out = @{ match = [bool](Test-CommandLineOwnsExpectedRoot $cmd $expected); "
            "parsed = Get-CommandLineNamedArgument -CommandLine $cmd -Name 'root' }"
        )
        self.assertFalse(r["match"])
        self.assertFalse(r["parsed"])


class OwnershipLive(unittest.TestCase):
    def setUp(self) -> None:
        self.install = Path(tempfile.mkdtemp(prefix="sws-own-live-"))
        (self.install / "modules" / "sovereign").mkdir(parents=True)
        self.expected = str(self.install / "modules" / "sovereign")
        self.procs: list[subprocess.Popen] = []

    def tearDown(self) -> None:
        for proc in self.procs:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        try:
            for root, dirs, files in os.walk(self.install, topdown=False):
                for name in files:
                    Path(root, name).unlink(missing_ok=True)
                for name in dirs:
                    Path(root, name).rmdir()
            self.install.rmdir()
        except OSError:
            pass

    def _track(self, proc: subprocess.Popen) -> subprocess.Popen:
        self.procs.append(proc)
        return proc

    def _resolve(self, listener_pid: int, launcher_pid: int) -> dict:
        expected = self.expected.replace("'", "''")
        script = (
            f". '{HELPER}'\n"
            f"$r = Resolve-FixtureListenerOwnership -ListenerPid {listener_pid} "
            f"-ExpectedRoot '{expected}' -LauncherPid {launcher_pid}\n"
            "$r | ConvertTo-Json -Compress\n"
        )
        proc = _ps(script)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_venv_descendant_without_own_root_is_owned(self) -> None:
        parent = self._track(_spawn([
            "--root", self.expected.replace("\\", "/"),
            "--spawn-child", "--child-no-root",
        ]))
        child_pid = _read_pid_line(parent, "child")
        parent_pid = _read_pid_line(parent, "pid")
        r = self._resolve(child_pid, parent_pid)
        self.assertTrue(r["Owned"], r)
        self.assertEqual(r["Reason"], "ancestor-root-venv-descendant")

    def test_unrelated_listener_is_rejected(self) -> None:
        other = Path(tempfile.mkdtemp(prefix="sws-own-other-"))
        (other / "modules" / "sovereign").mkdir(parents=True)
        other_root = str(other / "modules" / "sovereign")
        try:
            launcher = self._track(_spawn(["--root", self.expected.replace("\\", "/")]))
            launcher_pid = _read_pid_line(launcher, "pid")
            stranger = self._track(_spawn(["--root", other_root, "--port", "0"]))
            _read_pid_line(stranger, "port")
            stranger_pid = _read_pid_line(stranger, "pid")
            r = self._resolve(stranger_pid, launcher_pid)
            self.assertFalse(r["Owned"], r)
            self.assertIn(r["Reason"], ("root-mismatch", "not-descendant-of-launcher"))
            self.assertTrue(_alive(stranger_pid))
        finally:
            for root, dirs, files in os.walk(other, topdown=False):
                for name in files:
                    Path(root, name).unlink(missing_ok=True)
                for name in dirs:
                    Path(root, name).rmdir()
            try:
                other.rmdir()
            except OSError:
                pass

    def _run_cleanup_script(self, body: str, launcher_pid: int, extra_pid: int | None = None) -> subprocess.CompletedProcess:
        extra = ""
        if extra_pid:
            extra = f"Add-OwnedProcessInstance -Tracker $t -ProcessId {extra_pid}\n"
        script = (
            f". '{HELPER}'\n"
            "$t = New-OwnedProcessTracker\n"
            f"Add-OwnedProcessInstance -Tracker $t -ProcessId {launcher_pid}\n"
            + extra + body + "\n"
        )
        return _ps(script)

    def test_cleanup_on_early_refusal_kills_descendants(self) -> None:
        parent = self._track(_spawn([
            "--root", self.expected.replace("\\", "/"),
            "--spawn-child", "--child-no-root",
        ]))
        child_pid = _read_pid_line(parent, "child")
        parent_pid = _read_pid_line(parent, "pid")
        unrelated = self._track(_spawn(["--log", str(Path(self.expected) / "x.log")]))
        unrelated_pid = _read_pid_line(unrelated, "pid")
        body = (
            "try { Write-Output 'sovereign listener is not the fixture install'; exit 2 } "
            "finally { Stop-OwnedProcessTree -Tracker $t -LauncherPid %d }\n" % parent_pid
        )
        proc = self._run_cleanup_script(body, parent_pid)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertTrue(_wait_dead(parent_pid), "launcher survived early refusal")
        self.assertTrue(_wait_dead(child_pid), "descendant survived early refusal")
        self.assertTrue(_alive(unrelated_pid), "unrelated process was killed")

    def test_cleanup_on_exception_kills_descendants(self) -> None:
        parent = self._track(_spawn([
            "--root", self.expected.replace("\\", "/"),
            "--spawn-child",
        ]))
        child_pid = _read_pid_line(parent, "child")
        parent_pid = _read_pid_line(parent, "pid")
        body = (
            "try { throw 'boom' } catch { Write-Output $_.Exception.Message; exit 1 } "
            "finally { Stop-OwnedProcessTree -Tracker $t -LauncherPid %d }\n" % parent_pid
        )
        proc = self._run_cleanup_script(body, parent_pid)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertTrue(_wait_dead(parent_pid))
        self.assertTrue(_wait_dead(child_pid))

    def test_cleanup_on_normal_completion_kills_descendants(self) -> None:
        parent = self._track(_spawn([
            "--root", self.expected.replace("\\", "/"),
            "--spawn-child",
        ]))
        child_pid = _read_pid_line(parent, "child")
        parent_pid = _read_pid_line(parent, "pid")
        body = (
            "try { Write-Output 'ok'; exit 0 } "
            "finally { Stop-OwnedProcessTree -Tracker $t -LauncherPid %d }\n" % parent_pid
        )
        proc = self._run_cleanup_script(body, parent_pid)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(_wait_dead(parent_pid))
        self.assertTrue(_wait_dead(child_pid))

    def test_cleanup_on_cancellation_kills_descendants(self) -> None:
        parent = self._track(_spawn([
            "--root", self.expected.replace("\\", "/"),
            "--spawn-child",
        ]))
        child_pid = _read_pid_line(parent, "child")
        parent_pid = _read_pid_line(parent, "pid")
        body = (
            "try { Write-Output 'cancelled'; exit 2 } "
            "finally { Stop-OwnedProcessTree -Tracker $t -LauncherPid %d }\n" % parent_pid
        )
        proc = self._run_cleanup_script(body, parent_pid)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertTrue(_wait_dead(parent_pid))
        self.assertTrue(_wait_dead(child_pid))


if __name__ == "__main__":
    unittest.main()
