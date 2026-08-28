"""Host prerequisites for host-coupled tests (punch list 2.4, W-22).

WHAT THIS IS FOR. Roughly forty tests in this suite are host-coupled: they need
Windows, or PowerShell, or `node`, or `py -3.12`, or a live Ollama daemon. Off
this host they FAIL rather than skip, which makes a clean checkout look broken
and makes a real regression indistinguishable from a missing prerequisite.

FOUR PROPERTIES, each proved in `tests/unit/test_host_prerequisites.py`:

  1. a host-coupled test RECOGNISES an unavailable prerequisite;
  2. it becomes an explicit SKIP, never a failure;
  3. a real regression still goes RED — gating must not swallow defects;
  4. the skip reason NAMES the missing prerequisite.

Property 4 is the one the existing ad-hoc gates mostly fail. They skip with the
name of what the test proves ("Windows Node process-tree proof") rather than what
the host is missing, so a reader of a skipped run cannot tell what to install.

ENVIRONMENTAL ACCEPTANCE IS SEPARATE FROM INSTRUMENT CORRECTNESS, and this module
is only the instrument. Recorded literally, on one line so it is greppable and
cannot be softened by a re-wrap:

Linux clean-checkout acceptance: NOT VERIFIED ON THIS HOST.

No cross-platform gate claim may be made until that leg runs.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable

import pytest


@dataclass(frozen=True)
class Prerequisite:
    """One thing a host either has or does not. `detect` is called at collection time."""

    name: str
    detect: Callable[[], bool]
    install_hint: str

    def missing(self) -> bool:
        try:
            return not self.detect()
        except Exception:      # noqa: BLE001 - a detector that throws is a prerequisite absent
            return True

    @property
    def skip_reason(self) -> str:
        """NAMES the missing prerequisite, which is property 4."""
        return f"host prerequisite missing: {self.name} — {self.install_hint}"


def _py312() -> bool:
    exe = shutil.which("py") or shutil.which("python3.12")
    if exe is None:
        return False
    args = [exe, "-3.12", "--version"] if exe.endswith(("py", "py.exe")) else [exe, "--version"]
    try:
        return subprocess.run(args, capture_output=True, timeout=15,
                              check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


WINDOWS = Prerequisite(
    "Windows (os.name == 'nt')", lambda: os.name == "nt",
    "these assert Windows-specific semantics: ConPTY, Job Objects, taskkill, backslash paths")
POWERSHELL = Prerequisite(
    "powershell.exe on PATH", lambda: shutil.which("powershell") is not None,
    "install Windows PowerShell, or run on the Windows target host")
NODE = Prerequisite(
    "node on PATH", lambda: shutil.which("node") is not None,
    "install Node.js; the JS<->Python legs spawn it directly")
PY312 = Prerequisite(
    "py -3.12 on PATH", _py312,
    "install Python 3.12 and the `py` launcher; cross-language legs shell out to it")
WSL = Prerequisite(
    "wsl on PATH", lambda: shutil.which("wsl") is not None,
    "install WSL; the Parakeet voice boundary runs inside it")
OLLAMA = Prerequisite(
    "a reachable Ollama daemon", lambda: shutil.which("ollama") is not None,
    "start the local Ollama daemon; local-model legs need a live one")

#: Every prerequisite this suite knows how to name. A gate may only cite one of these, so a new
#: host coupling has to be DECLARED rather than expressed as a bare boolean nobody can read.
KNOWN: tuple[Prerequisite, ...] = (WINDOWS, POWERSHELL, NODE, PY312, WSL, OLLAMA)


def requires(*prerequisites: Prerequisite):
    """Skip this test when any named prerequisite is absent, naming the FIRST one that is.

    Deliberately NOT a try/except around the test body: a prerequisite that is present and a test
    that then fails is a REGRESSION, and it must still go red (property 3). This gates on the
    host, never on the outcome.
    """
    if not prerequisites:
        raise ValueError("requires() with no prerequisite gates nothing")
    for prereq in prerequisites:
        if prereq not in KNOWN:
            raise ValueError(f"undeclared prerequisite {prereq.name!r}; add it to KNOWN")
    missing = [p for p in prerequisites if p.missing()]
    return pytest.mark.skipif(bool(missing),
                              reason=missing[0].skip_reason if missing else "")
