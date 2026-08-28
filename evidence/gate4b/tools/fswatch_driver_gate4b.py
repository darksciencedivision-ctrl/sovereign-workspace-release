"""Gate 4b H-12 filesystem-watch driver (work order section 1; reuses the Gate 5 driver design).

Imports FsWatch from shell.tests._fswatch UNMODIFIED and runs it standalone over the three
protected roots for the whole Gate 5 session. Stops when the sentinel file fswatch.stop appears
next to this script, or on SIGINT/SIGBREAK. Produces evidence/gate4b/fs-watch-gate4b.txt with the
same field layout as FsWatch.write_report; the producer header differs because the module
hardcodes '# producer: claude-code REM-01' (_fswatch.py:220) and this session must not modify
shell/tests/** (work order 0.1(4)).
"""
import os
import signal
import sys
import time

WS = r"D:\Product Software\Production Workspace"
sys.path.insert(0, WS)

from shell.tests._fswatch import FsWatch  # noqa: E402

OUT = os.path.join(WS, "evidence", "gate4b", "fs-watch-gate4b.txt")
STOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fswatch.stop")


def write_report_like_module(w, out_path):
    """Same fields as FsWatch.write_report; correct producer header for this session."""
    d = os.path.dirname(out_path)
    if d:
        os.makedirs(d, exist_ok=True)
    mine = w.duration_s()
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# utc: {}\n".format(w.stopped_utc or w.started_utc))
        f.write("# producer: ox-alpha GATE4B\n")
        f.write("# proof: H-12 - no runtime writes outside Production Workspace\\\n")
        f.write("# watcher: ReadDirectoryChangesW via ctypes, recursive, on each root\n")
        f.write("# driver: evidence/gate5/tools/fswatch_driver.py imports "
                "shell.tests._fswatch.FsWatch unmodified; the module's own write_report()\n"
                "#         hardcodes producer 'claude-code REM-01' (_fswatch.py:220), which "
                "this session may not edit.\n")
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


if __name__ == "__main__":
    main()


