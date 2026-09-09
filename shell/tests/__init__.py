"""
SWS test package.

Importing this package starts the H-12 filesystem watch on the three protected roots (R3-9). It
runs for the whole suite; test_zz_evidence.py stops it, writes .runtime/hardening/fs-watch.txt,
and fails if any event was recorded. An atexit hook is registered as a backstop so the report is
written even if the suite is interrupted before that module runs. Tracked evidence/hardening
files are historical snapshots and must not be rewritten by verification.
"""
import atexit
import os

from shell.tests._fswatch import FsWatch

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FS_WATCH_REPORT = os.path.join(WORKSPACE, ".runtime", "hardening", "fs-watch.txt")

WATCH = FsWatch()
WATCH.start()

_reported = {"done": False, "outcome": None}


def finish_watch():
    """Stop the watch and write its report. Safe to call more than once."""
    if _reported["done"]:
        return WATCH.events
    _reported["done"] = True
    events = WATCH.stop()
    _reported["outcome"] = WATCH.write_report(FS_WATCH_REPORT)
    return events


def watch_outcome():
    """('written'|'refused', reason) from the last finish_watch(), or None."""
    return _reported["outcome"]


atexit.register(finish_watch)
