"""LOOP-01 H-12 filesystem-watch driver (adapted from evidence/gate5/tools/fswatch_driver.py).

Imports FsWatch from shell.tests._fswatch UNMODIFIED and runs it standalone over the three
protected roots for the whole LOOP-01 session so the fs-watch window brackets G1 -> G4.
Stops when sentinel fswatch.stop appears next to this script, or on SIGINT/SIGBREAK.
Writes evidence/loop5/fs-watch-loop01.txt with the module's field layout; producer header
is this session's because _fswatch.py hardcodes its own (_fswatch.py:220) and shell/tests/**
may not be modified.
"""
import os
import signal
import sys
import time

WS = r"D:\Product Software\Production Workspace"
sys.path.insert(0, WS)

from shell.tests._fswatch import FsWatch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(WS, "evidence", "loop5", "fs-watch-loop01.txt")
STOP = os.path.join(HERE, "fswatch.stop")
PIDFILE = os.path.join(HERE, "fswatch-driver.pid")


def write_report_like_module(w, out_path):
    d = os.path.dirname(out_path)
    if d:
        os.makedirs(d, exist_ok=True)
    mine = w.duration_s()
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# utc: {}\n".format(w.stopped_utc or w.started_utc))
        f.write("# producer: ox-alpha LOOP-01\n")
        f.write("# proof: H-12 - no runtime writes outside Production Workspace\\\n")
        f.write("# watcher: ReadDirectoryChangesW via ctypes, recursive, on each root\n")
        f.write("# driver: evidence/loop5/tools/fswatch_driver.py imports "
                "shell.tests._fswatch.FsWatch unmodified.\n")
        f.write("# window: {} .. {}\n".format(w.started_utc, w.stopped_utc))
        for root in w.roots:
            f.write("# root: {}\n".format(root))
        f.write("# ignored under D:\\Product Software: Production Workspace\\ "
                "(this workspace's own writes)\n")
        f.write("# events: {}\n".format(len(w.events)))
        if w.errors:
            f.write("# watcher-errors: {}\n".format(len(w.errors)))
            for e in w.errors:
                f.write("# watcher-error: {}\n".format(e))
        f.write("# window-seconds: {:.0f}\n".format(mine))
        for ev in w.events:
            f.write("{}\t{}\t{}\t{}\n".format(
                ev["utc"], ev["root"], ev["action"], ev["path"]))
    return mine


def main():
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    w = FsWatch().start()
    print("FSWATCH-DRIVER started_utc={} roots={}".format(w.started_utc, w.roots), flush=True)
    stopping = {"flag": False}

    def handle(signum, frame):
        stopping["flag"] = True

    for sname in ("SIGINT", "SIGBREAK"):
        sig = getattr(signal, sname, None)
        if sig is not None:
            try:
                signal.signal(sig, handle)
            except (ValueError, OSError):
                pass

    try:
        while not stopping["flag"] and not os.path.exists(STOP):
            time.sleep(0.5)
    finally:
        events = w.stop()
        seconds = write_report_like_module(w, OUT)
        print("FSWATCH-DRIVER stopped_utc={} window_s={:.0f} events={} errors={} out={}"
              .format(w.stopped_utc, seconds, len(events), len(w.errors), OUT), flush=True)
        if os.path.exists(STOP):
            os.remove(STOP)
        try:
            os.remove(PIDFILE)
        except OSError:
            pass


if __name__ == "__main__":
    main()