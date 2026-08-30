"""SWS logging: levels, a destination, and rotation.

EPC-01 P4-6. Before this, diagnostic output had two homes and neither survived anything:
the shell printed to its own stdout, and each module's stdout was captured into an in-memory
`LogRing` that the API served. Close the console and the record was gone. `docs/OPERATIONS.md`
said as much - "once a service's stdout is gone, so is the record" - which was honest and is
not a state a product should ship in, because the first thing anyone asks about a fault is
what happened just before it.

Three properties this module exists to guarantee:

**Redaction cannot be bypassed.** Module output is persisted from inside `LogRing.write`,
AFTER `redact()` has run, not by tapping the supervisor's pipe. A second path to disk that
reached around the redactor would turn an in-memory safeguard into a file full of secrets.
The sink receives lines that are already redacted, and it has no way to ask for the originals.

**Logs live outside the install root.** Under `%LOCALAPPDATA%\\SovereignWorkspace\\<module>\\logs`,
for the same reason all other state does (P4-4): an install tree the product writes into
cannot be verified against its manifest, replaced, or uninstalled cleanly.

**Rotation is bounded and dependency-free.** `logging.handlers.RotatingFileHandler` would do
for the shell, but module output does not go through `logging` - it arrives as already-decoded
lines - so the same size-and-generation policy is implemented once here and used by both.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

from shell.src.adapter import module_state_root, workspace_state_root

#: Level for the shell's own logger. Names, not numbers - an operator reads this file.
LEVEL_ENV = "SOVEREIGN_LOG_LEVEL"
DEFAULT_LEVEL = "INFO"

#: Rotation policy. Small enough that a log directory cannot fill a disk, large enough that a
#: fault's context is still present. Five generations of 2 MB is at most 10 MB per module.
MAX_BYTES = 2 * 1024 * 1024
KEEP = 5

_configure_lock = threading.Lock()
_configured = False


def resolved_level() -> int:
    """The configured level, falling back to INFO rather than failing on a typo.

    A misspelled level must not stop the shell from starting, and must not silently mean
    "log nothing" either - the fallback is announced by the caller.
    """
    name = os.environ.get(LEVEL_ENV, "").strip().upper() or DEFAULT_LEVEL
    return getattr(logging, name, logging.INFO)


def shell_log_dir() -> str:
    return f"{workspace_state_root()}/shell/logs"


def module_log_dir(module_id: str) -> str:
    return f"{module_state_root(module_id)}/logs"


class RotatingLineSink:
    """Append redacted lines to a file, rotating by size.

    Deliberately tolerant: a logging sink that raises takes down the thing it was meant to
    make diagnosable. Every filesystem error is swallowed after being counted, and
    `errors` is readable so a caller can tell that persistence is failing rather than idle.
    """

    def __init__(self, path: str, max_bytes: int = MAX_BYTES, keep: int = KEEP) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.keep = keep
        self.errors = 0
        self._lock = threading.Lock()

    def _rotate_if_needed(self) -> None:
        try:
            if os.path.getsize(self.path) < self.max_bytes:
                return
        except OSError:
            return
        # Oldest first, so no generation overwrites one that has not moved yet.
        for index in range(self.keep - 1, 0, -1):
            source = f"{self.path}.{index}"
            target = f"{self.path}.{index + 1}"
            if os.path.exists(source):
                try:
                    os.replace(source, target)
                except OSError:
                    return
        try:
            os.replace(self.path, f"{self.path}.1")
        except OSError:
            return

    def write_line(self, line: str) -> None:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                self._rotate_if_needed()
                with open(self.path, "a", encoding="utf-8", newline="\n") as handle:
                    handle.write(line + "\n")
            except OSError:
                self.errors += 1


def module_sink(module_id: str) -> RotatingLineSink:
    """The persistent destination for one module's captured output."""
    return RotatingLineSink(f"{module_log_dir(module_id)}/{module_id}.log")


def configure_shell_logging(force: bool = False) -> logging.Logger:
    """Configure the shell's own logger once: rotating file plus stderr.

    Returns the `sws` logger. Idempotent - the shell's entry point and its tests both call
    it, and configuring twice would duplicate every line.
    """
    global _configured
    logger = logging.getLogger("sws")
    with _configure_lock:
        if _configured and not force:
            return logger
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

        level = resolved_level()
        logger.setLevel(level)
        logger.propagate = False

        formatter = logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

        console = logging.StreamHandler(stream=sys.stderr)
        console.setFormatter(formatter)
        logger.addHandler(console)

        # A shell that cannot write its log file must still start and still log to the
        # console. Losing persistence is a degradation; refusing to run is an outage.
        try:
            directory = shell_log_dir()
            os.makedirs(directory, exist_ok=True)
            file_handler = RotatingFileHandler(
                f"{directory}/shell.log", maxBytes=MAX_BYTES, backupCount=KEEP,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError as exc:
            logger.warning("log file unavailable, console only: %s", exc)

        requested = os.environ.get(LEVEL_ENV, "").strip().upper()
        if requested and getattr(logging, requested, None) is None:
            logger.warning("%s=%r is not a level name; using %s",
                           LEVEL_ENV, requested, DEFAULT_LEVEL)

        _configured = True
    return logger


def get_logger(name: str = "sws") -> logging.Logger:
    """A logger under the `sws` tree, configured on first use."""
    configure_shell_logging()
    return logging.getLogger(name if name.startswith("sws") else f"sws.{name}")
