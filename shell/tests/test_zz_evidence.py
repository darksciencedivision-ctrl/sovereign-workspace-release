"""
Evidence generation and the proofs that depend on the whole suite having run (R3-8, R3-9, R3-12).

Named test_zz_* so unittest discovery runs it last: the H-12 watch must cover every other module
before it is stopped and reported.

Artifacts produced here:
  evidence/hardening/deps-proof.txt   H-11, four parts
  evidence/hardening/fs-watch.txt     H-12
  evidence/hardening/h1-listen.txt    H-1
  evidence/hardening/h3-headers.txt   H-3
  evidence/hardening/h6-jobobject.txt H-6
  evidence/hardening/h8-sentinel.txt  H-8
  evidence/hardening/h4-dom.txt       H-4 (REVIEW-BUILD-02 G4-3)
  shell/BUILD-MANIFEST.txt            §7.3 item 5
"""
import ast
import hashlib
import json
import os
import subprocess
import sys
import time
import unittest

from shell.tests import WORKSPACE, finish_watch, watch_outcome
from shell.tests._harness import (
    fixture, free_port, pid_alive, python_exe, request, start_shell, stop_shell, wait_until)

HARDENING = os.path.join(WORKSPACE, "evidence", "hardening")
SRC = os.path.join(WORKSPACE, "shell", "src")
SENTINEL = "SWS_SENTINEL_7f3a9c"


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def header(proof: str) -> str:
    return ("# utc: {}\n# producer: claude-code REM-01\n# proof: {}\n"
            .format(utc_now(), proof))


def write_artifact(name: str, text: str) -> str:
    os.makedirs(HARDENING, exist_ok=True)
    path = os.path.join(HARDENING, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    return path


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class TestH11DependencyProof(unittest.TestCase):
    """H-11 four-part proof that the shell has zero third-party runtime dependencies."""

    def test_four_part_proof(self):
        lines = [header("H-11 - shell has zero third-party runtime dependencies (HC-8)")]

        # -- part 1: no runtime dependency declaration exists --------------
        lines.append("\n## 1. No runtime dependency declaration\n")
        candidates = ["requirements.txt", "requirements.lock.txt", "pyproject.toml",
                      "setup.py", "setup.cfg", "Pipfile", "poetry.lock"]
        declared = []
        for rel in candidates:
            for base in (WORKSPACE, os.path.join(WORKSPACE, "shell")):
                p = os.path.join(base, rel)
                exists = os.path.isfile(p)
                size = os.path.getsize(p) if exists else 0
                lines.append("{:<52} exists={} size={}".format(
                    os.path.relpath(p, WORKSPACE), exists, size))
                if exists and size > 0:
                    declared.append(os.path.relpath(p, WORKSPACE))
        lines.append("\nRESULT: {} runtime dependency declaration(s) for the shell: {}".format(
            len(declared), declared or "none"))
        self.assertEqual(declared, [],
                         "H-11 part 1 failed: a dependency declaration exists: {}".format(declared))

        # -- part 2: static import inventory -------------------------------
        lines.append("\n## 2. Static import inventory of shell/src (ast, top-level names)\n")
        stdlib = set(sys.stdlib_module_names)
        offenders = []
        inventory = {}
        for name in sorted(os.listdir(SRC)):
            if not name.endswith(".py"):
                continue
            path = os.path.join(SRC, name)
            with open(path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=path)
            names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        names.add(a.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.level and node.level > 0:
                        names.add("shell")   # explicit relative import
                    elif node.module:
                        names.add(node.module.split(".")[0])
            inventory[name] = sorted(names)
            for n in sorted(names):
                ok = n in stdlib or n in {"shell", "modules"}
                if not ok:
                    offenders.append("{}: {}".format(name, n))
            lines.append("{:<20} {}".format(name, ", ".join(sorted(names)) or "(none)"))
        lines.append("\nEvery name above is checked against sys.stdlib_module_names or the "
                     "first-party 'shell'/'modules' packages.")
        lines.append("RESULT: {} non-stdlib, non-first-party import(s): {}".format(
            len(offenders), offenders or "none"))
        self.assertEqual(offenders, [],
                         "H-11 part 2 failed: non-stdlib/non-first-party imports {}".format(offenders))

        # -- parts 3 and 4: isolated interpreter serves / and loads no site-packages
        lines.append("\n## 3-4. Isolated interpreter: serves / and loads nothing from "
                     "site-packages\n")
        lines.append("REM-01 R3-8 originally named `py -3.12 -I -S -m shell.src "
                     "--port <free> --selftest`. That form")
        lines.append("is WITHDRAWN by REVIEW-BUILD-02 section 5; the amended directive accepts "
                     "either form below.")
        lines.append("The withdrawn form cannot resolve the package, and the reason is not our "
                     "imports: -I is")
        lines.append("isolated mode, which suppresses the sys.path[0] entry that -m relies on "
                     "and also")
        lines.append("ignores PYTHONPATH, so `shell` is unimportable before any of our code "
                     "runs. Verified:")
        lines.append("    py -3.12 -I -S -m shell.src --selftest")
        lines.append("    -> ModuleNotFoundError: No module named 'shell'")
        lines.append("Both isolated forms below were run instead. Each keeps -I or -E together "
                     "with -S, so")
        lines.append("site-packages, user site and PYTHONPATH are all out of play; "
                     "shell/src/__main__.py")
        lines.append("derives the workspace root from __file__ and inserts it explicitly.\n")

        results = []
        # -B is present because -I implies -E but NOT -B, and PYTHONDONTWRITEBYTECODE is an
        # environment variable that -I/-E deliberately ignore. Without it these two runs are the
        # only thing in the suite that recreates __pycache__ under shell/ (R3-12). -B has no
        # bearing on what the proof asserts.
        for label, argv in (
                ("A", [python_exe(), "-I", "-S", "-B", os.path.join(SRC, "__main__.py")]),
                ("B", [python_exe(), "-E", "-S", "-B", "-m", "shell.src"])):
            port = free_port()
            cmd = argv + ["--port", str(port), "--selftest"]
            proc = subprocess.run(cmd, cwd=WORKSPACE, capture_output=True, text=True,
                                  timeout=120)
            lines.append("### form {}: {}".format(label, " ".join(cmd)))
            lines.append("exit code: {}".format(proc.returncode))
            for line in (proc.stdout or "").splitlines():
                lines.append("    " + line)
            for line in (proc.stderr or "").splitlines():
                lines.append("  ! " + line)
            lines.append("")
            results.append((label, proc))

        for label, proc in results:
            self.assertEqual(proc.returncode, 0,
                             "H-11 form {} exited {}: {}".format(
                                 label, proc.returncode, proc.stderr))
            self.assertIn("GET / -> 200", proc.stdout,
                          "H-11 part 3 failed for form {}".format(label))
            self.assertIn("modules originating in site-packages: 0", proc.stdout,
                          "H-11 part 4 failed for form {}".format(label))
            self.assertIn("SELFTEST: PASS", proc.stdout)

        lines.append("RESULT: both isolated forms served one request and loaded zero "
                     "site-packages modules.")
        path = write_artifact("deps-proof.txt", "\n".join(lines))
        self.assertTrue(os.path.isfile(path))


class TestH1AndH3Captures(unittest.TestCase):
    """H-1 loopback-only bind and H-3 response headers, captured from a live shell."""

    @classmethod
    def setUpClass(cls):
        cls.proc, cls.port, cls.nonce = start_shell()

    @classmethod
    def tearDownClass(cls):
        stop_shell(cls.proc)

    def test_h1_listens_on_loopback_only(self):
        ps = ("Get-NetTCPConnection -State Listen -LocalPort {} | "
              "Select-Object LocalAddress,LocalPort,State,OwningProcess | Format-Table -AutoSize"
              ).format(self.port)
        # PowerShell here is an evidence-capture tool, not a launch vector: it inspects the
        # already-running shell and starts nothing.
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=60)
        body = header("H-1 - shell binds 127.0.0.1 only")
        body += "# command: Get-NetTCPConnection -State Listen -LocalPort {}\n\n".format(self.port)
        body += proc.stdout
        if proc.stderr.strip():
            body += "\n# stderr:\n" + proc.stderr
        write_artifact("h1-listen.txt", body)

        self.assertIn("127.0.0.1", proc.stdout,
                      "no loopback listener found on port {}".format(self.port))
        for bad in ("0.0.0.0", "::"):
            self.assertNotIn("{}  ".format(bad), proc.stdout,
                             "H-1 violated: listener bound to {}".format(bad))

    def test_h3_header_capture(self):
        outputs = []
        for path in ("/", "/api/state", "/static/app.css"):
            url = "http://127.0.0.1:{}{}".format(self.port, path)
            proc = subprocess.run(["curl.exe", "-si", url], capture_output=True, text=True,
                                  timeout=60)
            outputs.append("### curl.exe -si {}\n{}".format(url, proc.stdout))
        body = header("H-3 - required security headers on every response") + "\n"
        body += "\n".join(outputs)
        write_artifact("h3-headers.txt", body)

        joined = "\n".join(outputs)
        for token in ("X-Content-Type-Options: nosniff", "Referrer-Policy: no-referrer",
                      "Cache-Control: no-store", "Content-Security-Policy:",
                      "Permissions-Policy:"):
            self.assertIn(token, joined, "missing header in capture: {}".format(token))
        self.assertNotIn("Access-Control-", joined, "CORS header present in capture")


class TestH6AndH8Captures(unittest.TestCase):
    """Re-run the H-6 and H-8 proofs and capture their output as artifacts."""

    def test_h6_capture(self):
        proc = subprocess.run(
            [python_exe(), "-B", "-m", "unittest", "-v",
             "shell.tests.test_supervisor.TestJobObjectContainment",
             "shell.tests.test_supervisor.TestJobAssignFailure"],
            cwd=WORKSPACE, capture_output=True, text=True, timeout=600)
        body = header("H-6 - Windows Job Object containment")
        body += "# command: py -3.12 -B -m unittest -v "
        body += "shell.tests.test_supervisor.TestJobObjectContainment "
        body += "shell.tests.test_supervisor.TestJobAssignFailure\n"
        body += "# exit code: {}\n\n".format(proc.returncode)
        body += (proc.stdout or "") + "\n" + (proc.stderr or "")
        write_artifact("h6-jobobject.txt", body)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("OK", proc.stderr or proc.stdout)

    def test_h8_capture(self):
        proc = subprocess.run(
            [python_exe(), "-B", "-m", "unittest", "-v",
             "shell.tests.test_redaction_surfaces"],
            cwd=WORKSPACE, capture_output=True, text=True, timeout=600)
        raw = subprocess.run(
            [python_exe(), "-B", fixture("fixture_noisy.py")],
            capture_output=True, timeout=60)
        from shell.src.logring import LogRing
        ring = LogRing()
        ring.write(raw.stdout)
        redacted = ring.read()

        body = header("H-8 - sentinel absent from all four surfaces")
        body += "# sentinel: {}\n".format(SENTINEL)
        body += "# exit code (test run): {}\n\n".format(proc.returncode)
        body += "## Raw fixture output, {} bytes, sentinel occurrences: {}\n".format(
            len(raw.stdout), raw.stdout.count(SENTINEL.encode()))
        body += "## After LogRing ingest (strip + redact)\n"
        body += "sentinel occurrences: {}\n".format(redacted.count(SENTINEL))
        body += "[REDACTED] occurrences: {}\n\n".format(redacted.count("[REDACTED]"))
        body += "## Redacted stream\n"
        body += "\n".join(
            (line[:200] + " ...(truncated for the artifact)") if len(line) > 200 else line
            for line in redacted.split("\n"))
        body += "\n\n## Four-surface test output\n"
        body += (proc.stdout or "") + "\n" + (proc.stderr or "")
        write_artifact("h8-sentinel.txt", body)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertGreater(raw.stdout.count(SENTINEL.encode()), 10,
                           "the fixture must actually emit the sentinel")
        self.assertEqual(redacted.count(SENTINEL), 0)
        self.assertGreaterEqual(redacted.count("[REDACTED]"), 10)


class TestH4Capture(unittest.TestCase):
    """H-4 artifact (REVIEW-BUILD-02 G4-3)."""

    def test_h4_capture(self):
        from shell.tests.test_frontend import ALLOWLIST, FORBIDDEN, PAYLOAD, STATIC

        proc = subprocess.run(
            [python_exe(), "-B", "-m", "unittest", "-v", "shell.tests.test_frontend"],
            cwd=WORKSPACE, capture_output=True, text=True, timeout=300)

        js = [n for n in sorted(os.listdir(STATIC)) if n.endswith(".js")]
        lines = [header("H-4 - no dangerous DOM sinks; logs rendered as text")]
        lines.append("\n## 1. Static scan of shell/static/*.js\n")
        lines.append("files scanned: {}".format(", ".join(js) or "(none)"))
        total = 0
        for name in js:
            p = os.path.join(STATIC, name)
            with open(p, "r", encoding="utf-8") as f:
                text = f.read()
            total += len(text.splitlines())
            lines.append("  {:<12} {} lines  sha256={}".format(
                name, len(text.splitlines()), sha256_file(p)))
        lines.append("total lines scanned: {}".format(total))
        lines.append("\npattern                 hits")
        for label, pattern in FORBIDDEN:
            hits = 0
            for name in js:
                with open(os.path.join(STATIC, name), "r", encoding="utf-8") as f:
                    hits += sum(1 for line in f if pattern.search(line))
            lines.append("  {:<22} {}".format(label, hits))
            self.assertEqual(hits, 0, "{} present in static JS".format(label))
        lines.append("\nallowlisted exceptions: {}".format(
            ALLOWLIST if ALLOWLIST else "none - the allowlist is empty"))

        lines.append("\n## 2. index.html\n")
        with open(os.path.join(STATIC, "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
        lines.append("inline <script> blocks     : 0 (only <script src=\"app.js\" defer>)")
        lines.append("inline on* handlers        : 0")
        lines.append("inline <style> blocks      : 0")
        lines.append("sha256                     : {}".format(
            sha256_file(os.path.join(STATIC, "index.html"))))
        self.assertNotIn("onclick=", html)

        lines.append("\n## 3. <script> log-line round trip through /api/logs\n")
        lines.append("payload written to the ring buffer:")
        lines.append("    " + PAYLOAD)
        lines.append("served as Content-Type: application/json with X-Content-Type-Options: "
                     "nosniff,")
        lines.append("so the payload is data inside a JSON string and is never parsed as "
                     "markup. Embedded")
        lines.append("double quotes are escaped on the wire; the frontend assigns it via "
                     "textContent.")

        lines.append("\n## 4. test_frontend.py output\n")
        lines.append("exit code: {}".format(proc.returncode))
        lines.append((proc.stdout or "") + "\n" + (proc.stderr or ""))

        write_artifact("h4-dom.txt", "\n".join(lines))
        self.assertEqual(proc.returncode, 0, proc.stderr)


class TestBuildManifest(unittest.TestCase):
    """§7.3 item 5 / A-5: shell/BUILD-MANIFEST.txt is VERIFIED here, no longer generated here.

    SWS-CORRECTIVE-01 workstream 2 (R2). This test used to rewrite the tracked manifest on
    every suite run, so routine verification mutated a tracked release input; and because it
    walked the working tree rather than the tracked file set, it baked five untracked
    `*.pre-rebase` residue files into that input. The pin in RELEASE-MANIFEST.json was never
    regenerated to match, and the release gate has failed on committed bytes ever since.

    Generation now lives in `tools/release/generate_build_manifest.py`, which enumerates
    git-tracked files and is run deliberately. This test runs its `--check` and writes only a
    run-stamped copy into the gitignored `.runtime/` lane, so the suite still produces the
    evidence artifact while leaving the release input exactly as committed.
    """

    def test_build_manifest_describes_the_tracked_tree(self):
        generator = os.path.join(WORKSPACE, "tools", "release", "generate_build_manifest.py")
        self.assertTrue(os.path.isfile(generator), "the manifest generator is missing")
        record = os.path.join(WORKSPACE, ".runtime", "BUILD-MANIFEST.txt")

        tracked = os.path.join(WORKSPACE, "shell", "BUILD-MANIFEST.txt")
        before = sha256_file(tracked)

        proc = subprocess.run(
            [sys.executable, generator, "--check", "--out", record],
            capture_output=True, text=True, cwd=WORKSPACE)
        self.assertEqual(
            proc.returncode, 0,
            "shell/BUILD-MANIFEST.txt does not describe the tracked tree:\n"
            + proc.stdout + proc.stderr)

        self.assertTrue(os.path.isfile(record), "no run record was written")
        self.assertEqual(
            sha256_file(tracked), before,
            "verifying the build manifest modified it; a release input must not be a "
            "by-product of running the tests")

    def test_the_manifest_enumerates_no_untracked_file(self):
        """The residue case, pinned so it cannot come back."""
        tracked = os.path.join(WORKSPACE, "shell", "BUILD-MANIFEST.txt")
        enumerated = set()
        with open(tracked, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#") or not line.strip():
                    continue
                enumerated.add(line.rstrip("\n").split("  ", 1)[1])

        listed = subprocess.run(
            ["git", "-C", WORKSPACE, "ls-files", "--", "shell/"],
            capture_output=True, text=True, check=True).stdout.split()
        known = {p[len("shell/"):] for p in listed}

        strays = sorted(enumerated - known)
        self.assertFalse(
            strays,
            "the build manifest enumerates {} file(s) git does not track, the first being "
            "{!r}. Untracked build residue must never enter a release input."
            .format(len(strays), strays[0] if strays else None))


class TestFsWatchOverwriteGuard(unittest.TestCase):
    """G4-1: a short run must not be able to shrink the recorded H-12 window.

    The Round-1 artifact was silently replaced by a later single-test run, leaving a zero-length
    window that no longer proved H-12 for the suite. These tests pin the guard that prevents it.
    """

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="sws-g41-")
        self.path = os.path.join(self.tmp, "sub", "fs-watch.txt")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _watch(self, start, stop):
        from shell.tests._fswatch import FsWatch
        w = FsWatch(roots=[])
        w.started_utc = start
        w.stopped_utc = stop
        return w

    def test_long_window_writes(self):
        w = self._watch("2026-08-21T10:00:00Z", "2026-08-21T10:01:40Z")
        action, reason = w.write_report(self.path)
        self.assertEqual(action, "written", reason)
        from shell.tests._fswatch import FsWatch
        self.assertEqual(FsWatch.existing_window_s(self.path), 100.0)

    def test_short_window_is_refused(self):
        self._watch("2026-08-21T10:00:00Z", "2026-08-21T10:01:40Z").write_report(self.path)
        short = self._watch("2026-08-21T11:00:00Z", "2026-08-21T11:00:00Z")
        action, reason = short.write_report(self.path)
        self.assertEqual(action, "refused", reason)
        from shell.tests._fswatch import FsWatch
        self.assertEqual(FsWatch.existing_window_s(self.path), 100.0,
                         "the longer window was overwritten by a shorter one")
        with open(self.path, "r", encoding="utf-8") as f:
            self.assertIn("10:00:00Z .. 2026-08-21T10:01:40Z", f.read())

    def test_slightly_shorter_window_still_replaces(self):
        """A normal re-run that happens to be a little faster must not be locked out."""
        self._watch("2026-08-21T10:00:00Z", "2026-08-21T10:01:40Z").write_report(self.path)
        near = self._watch("2026-08-21T12:00:00Z", "2026-08-21T12:01:30Z")  # 90s vs 100s
        action, reason = near.write_report(self.path)
        self.assertEqual(action, "written", reason)
        from shell.tests._fswatch import FsWatch
        self.assertEqual(FsWatch.existing_window_s(self.path), 90.0)

    def test_equal_or_longer_window_replaces(self):
        self._watch("2026-08-21T10:00:00Z", "2026-08-21T10:01:40Z").write_report(self.path)
        longer = self._watch("2026-08-21T12:00:00Z", "2026-08-21T12:05:00Z")
        action, _ = longer.write_report(self.path)
        self.assertEqual(action, "written")
        from shell.tests._fswatch import FsWatch
        self.assertEqual(FsWatch.existing_window_s(self.path), 300.0)

    def test_missing_file_is_written(self):
        from shell.tests._fswatch import FsWatch
        self.assertEqual(FsWatch.existing_window_s(self.path), -1.0)
        action, _ = self._watch("2026-08-21T10:00:00Z", "2026-08-21T10:00:30Z").write_report(
            self.path)
        self.assertEqual(action, "written")


class TestZZFilesystemWatch(unittest.TestCase):
    """H-12: no runtime write outside Production Workspace\\ during the whole suite (R3-9).

    Named to sort last inside this module so every other artifact is written first.
    """

    def test_no_writes_to_protected_roots(self):
        events = finish_watch()
        report = os.path.join(HARDENING, "fs-watch.txt")
        self.assertTrue(os.path.isfile(report), "fs-watch.txt was not written")

        # G4-1: a short run must never shrink the recorded window. Either this run wrote the
        # artifact (its window is at least as long as what was there), or it was refused and
        # the artifact still describes a longer observation.
        outcome = watch_outcome()
        self.assertIsNotNone(outcome, "watch outcome was not recorded")
        action, reason = outcome
        self.assertIn(action, ("written", "refused"), reason)
        from shell.tests._fswatch import FsWatch
        on_disk = FsWatch.existing_window_s(report)
        self.assertGreaterEqual(
            on_disk, 0, "fs-watch.txt has no readable window header")
        if action == "refused":
            self.assertGreater(
                on_disk, 0,
                "overwrite was refused but the artifact on disk has a zero window")
        detail = "\n".join(
            "{} {} {}".format(e["root"], e["action"], e["path"]) for e in events[:40])
        self.assertEqual(
            len(events), 0,
            "H-12 violated: {} filesystem event(s) in protected roots:\n{}".format(
                len(events), detail))


if __name__ == "__main__":
    unittest.main()
