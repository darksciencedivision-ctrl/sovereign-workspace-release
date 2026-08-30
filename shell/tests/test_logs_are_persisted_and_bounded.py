"""EPC-01 P4-6 - diagnostic output must survive the process that produced it.

Before this, the shell printed to its own stdout and each module's output went into an
in-memory ring the API served. `docs/OPERATIONS.md` stated the consequence plainly: once a
service's stdout is gone, so is the record. That is an honest description of a product you
cannot diagnose after the fact, and the first question anyone asks about a fault is what
happened just before it.

The tests here hold the four properties that make the fix worth having, in the order they
matter:

  1. Persistence cannot bypass redaction. This is a security property, not a logging one:
     the sink is attached inside `LogRing.write` AFTER `redact()` runs, so a secret that the
     in-memory ring hides cannot appear in the file. A sink tapped off the supervisor's raw
     pipe would have been simpler and would have written credentials to disk.
  2. Logs live outside the install root, like all other runtime state (P4-4).
  3. Rotation is bounded, so a chatty module cannot fill a disk.
  4. A sink that cannot write does not take down the thing it exists to make diagnosable.
"""
from __future__ import annotations

import logging
import os
import tempfile
import unittest
from pathlib import Path

from shell.src.adapter import STATE_ROOT_ENV
from shell.src.logring import LogRing
from shell.src.logs import (
    LEVEL_ENV,
    MAX_BYTES,
    RotatingLineSink,
    configure_shell_logging,
    module_log_dir,
    module_sink,
    resolved_level,
    shell_log_dir,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class _EnvSandbox(unittest.TestCase):
    """Every test here relocates the state root; none may leak that to its neighbours."""

    def setUp(self) -> None:
        self._saved = {k: os.environ.get(k) for k in (STATE_ROOT_ENV, LEVEL_ENV)}
        self.state = tempfile.mkdtemp(prefix="sov-logs-")
        os.environ[STATE_ROOT_ENV] = self.state

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class PersistenceCannotBypassRedaction(_EnvSandbox):

    def test_a_secret_redacted_in_memory_is_redacted_on_disk(self) -> None:
        """The property the placement of the sink exists to guarantee."""
        sink = module_sink("debate")
        ring = LogRing(sink=sink)
        ring.write(b"Authorization: Bearer sk-live-abcdefghijklmnopqrstuvwxyz0123\n")

        in_memory = ring.read()
        on_disk = Path(sink.path).read_text(encoding="utf-8")

        self.assertNotIn("sk-live-abcdefghijklmnopqrstuvwxyz0123", in_memory,
                         "the ring itself failed to redact; this test proves nothing")
        self.assertNotIn(
            "sk-live-abcdefghijklmnopqrstuvwxyz0123", on_disk,
            "a secret the in-memory ring redacts was written to disk in the clear"
        )

    def test_the_file_holds_exactly_what_the_ring_holds(self) -> None:
        """Two records that could disagree would make the file useless as evidence."""
        sink = module_sink("sow")
        ring = LogRing(sink=sink)
        for line in (b"first line\n", b"second line\n", b"third line\n"):
            ring.write(line)
        on_disk = [ln for ln in
                   Path(sink.path).read_text(encoding="utf-8").split("\n") if ln]
        self.assertEqual(on_disk, [ln for ln in ring.read().split("\n") if ln])

    def test_control_characters_are_stripped_on_disk_too(self) -> None:
        sink = module_sink("sovereign")
        ring = LogRing(sink=sink)
        ring.write(b"\x1b[31mred\x1b[0m and \x00nul\n")
        on_disk = Path(sink.path).read_text(encoding="utf-8")
        self.assertNotIn("\x1b", on_disk)
        self.assertNotIn("\x00", on_disk)
        self.assertIn("red", on_disk)


class LogsLiveOutsideTheInstall(_EnvSandbox):

    def test_module_logs_are_under_that_module_state_root(self) -> None:
        path = Path(module_sink("tokencenter").path).resolve()
        self.assertTrue(
            str(path).startswith(str(Path(self.state).resolve())),
            f"module log {path} is not under the configured state root"
        )
        self.assertFalse(
            str(path).startswith(str(REPO_ROOT.resolve())),
            "module logs are being written inside the install root"
        )

    def test_each_module_gets_its_own_directory(self) -> None:
        """One module must not be able to read or clobber another's log."""
        self.assertNotEqual(module_log_dir("debate"), module_log_dir("sow"))

    def test_the_shell_log_is_under_the_state_root_too(self) -> None:
        self.assertTrue(
            Path(shell_log_dir()).resolve().is_relative_to(Path(self.state).resolve()))


class RotationIsBounded(_EnvSandbox):

    def test_the_file_rotates_instead_of_growing_without_limit(self) -> None:
        path = os.path.join(self.state, "rot", "test.log")
        sink = RotatingLineSink(path, max_bytes=2048, keep=3)
        for index in range(400):
            sink.write_line(f"{index:04d} " + "x" * 100)

        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.exists(path + ".1"), "nothing rotated")
        self.assertLessEqual(
            os.path.getsize(path), 2048 + 200,
            "the live file grew past its rotation threshold"
        )

    def test_it_keeps_no_more_generations_than_it_declares(self) -> None:
        path = os.path.join(self.state, "rot2", "test.log")
        sink = RotatingLineSink(path, max_bytes=1024, keep=3)
        for index in range(600):
            sink.write_line(f"{index:04d} " + "y" * 100)
        generations = [p for p in os.listdir(os.path.dirname(path))]
        self.assertLessEqual(
            len(generations), 4,
            f"keep=3 should leave at most the live file plus 3: {sorted(generations)}"
        )

    def test_the_newest_content_is_the_one_kept_live(self) -> None:
        path = os.path.join(self.state, "rot3", "test.log")
        sink = RotatingLineSink(path, max_bytes=1024, keep=2)
        for index in range(300):
            sink.write_line(f"{index:04d} " + "z" * 100)
        sink.write_line("FINAL-MARKER")
        self.assertIn("FINAL-MARKER", Path(path).read_text(encoding="utf-8"))


class FailureToLogIsNotAnOutage(_EnvSandbox):

    def test_an_unwritable_sink_does_not_raise(self) -> None:
        """A logging path that throws takes down the thing it was meant to make
        diagnosable. It must degrade, and it must be possible to tell that it did."""
        blocker = os.path.join(self.state, "blocker")
        Path(blocker).write_text("I am a file, not a directory", encoding="utf-8")
        sink = RotatingLineSink(os.path.join(blocker, "nested", "test.log"))
        sink.write_line("this cannot be written anywhere")
        self.assertGreater(sink.errors, 0, "a failed write was not counted")

    def test_a_ring_with_a_failing_sink_still_serves_its_lines(self) -> None:
        blocker = os.path.join(self.state, "blocker2")
        Path(blocker).write_text("also a file", encoding="utf-8")
        ring = LogRing(sink=RotatingLineSink(os.path.join(blocker, "x", "y.log")))
        ring.write(b"the API must still see this\n")
        self.assertIn("the API must still see this", ring.read())


class LevelsAreConfigurable(_EnvSandbox):

    def test_the_level_comes_from_the_environment(self) -> None:
        os.environ[LEVEL_ENV] = "DEBUG"
        self.assertEqual(resolved_level(), logging.DEBUG)
        os.environ[LEVEL_ENV] = "ERROR"
        self.assertEqual(resolved_level(), logging.ERROR)

    def test_a_misspelled_level_falls_back_rather_than_failing(self) -> None:
        """A typo in an environment variable must not stop the shell from starting, and
        must not silently mean "log nothing" either."""
        os.environ[LEVEL_ENV] = "VERBOSE"
        self.assertEqual(resolved_level(), logging.INFO)

    def test_configuring_twice_does_not_duplicate_handlers(self) -> None:
        first = configure_shell_logging(force=True)
        count = len(first.handlers)
        again = configure_shell_logging()
        self.assertEqual(len(again.handlers), count)

    def test_the_shell_logger_writes_a_file(self) -> None:
        logger = configure_shell_logging(force=True)
        logger.info("a line that must reach disk")
        for handler in logger.handlers:
            handler.flush()
        log_file = Path(shell_log_dir()) / "shell.log"
        self.assertTrue(log_file.is_file(), "the shell log file was never created")
        self.assertIn("a line that must reach disk", log_file.read_text(encoding="utf-8"))

    def test_the_default_is_not_silence(self) -> None:
        os.environ.pop(LEVEL_ENV, None)
        self.assertLessEqual(resolved_level(), logging.INFO)

    def test_the_declared_rotation_size_is_bounded(self) -> None:
        """Five generations of this size per module is the disk budget an operator inherits."""
        self.assertLessEqual(MAX_BYTES, 8 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
