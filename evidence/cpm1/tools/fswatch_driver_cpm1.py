"""CP-M1 O-6 filesystem-watch driver (restarted per operator correction C-1).

Imports FsWatch from shell.tests._fswatch UNMODIFIED. Opens the replacement watch window at
CP-M1 G5(resume) and runs until the sentinel file fswatch.stop appears beside this script
(closed at G117). Writes evidence/cpm1/fs-watch-cpm1.txt.

Roots are passed EXPLICITLY: the three PROTECTED_ROOTS defaults PLUS D:\\Sov 1\\ - four of the
five protected roots. D:\\Token Piggy Bank is DELIBERATELY EXCLUDED: FsWatch has no per-root
exclusion (its _ignored() special-cases only D:\\Product Software), so that root's data/**
sqlite refresh ring would produce unavoidable events and make events: 0 unreachable by
construction. Token Piggy Bank's integrity proof is instead the A-1 manifest comparison
against evidence/cp01/manifests/manifest-cp01-before-token-piggy-bank.excl-data.txt.
"""
import os
import signal
import sys
import time

WS = r"D:\Product Software\Production Workspace"
sys.path.insert(0, WS)

from shell.tests._fswatch import FsWatch  # noqa: E402

ROOTS = [
    r"D:\Product Software",
    r"D:\multi model terminal app",
    r"D:\Sovereign Distillery",
    r"D:\Sov 1",
]

OUT = os.path.join(WS, "evidence", "cpm1", "fs-watch-cpm1.txt")
STOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fswatch.stop")


def write_report_like_module(w, out_path):
    d = os.path.dirname(out_path)
    if d:
        os.makedirs(d, exist_ok=True)
    mine = w.duration_s()
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# utc: {}\n".format(w.stopped_utc or w.started_utc))
        f.write("# producer: ox-alpha CP-M1\n")
        f.write("# proof: H-12 / CP-M1 O-6 - one fs-watch window bracketing G5(resume) .. G117\n")
        f.write("# coverage: FOUR of FIVE protected roots watched explicitly; "
                "D:\\Token Piggy Bank deliberately excluded because FsWatch has no per-root\n"
                "#           exclusion (line-84 special case covers only D:\\Product Software) and "
                "its data/** sqlite ring would make events: 0 unreachable;\n"
                "#           Token Piggy Bank integrity rides on the A-1 manifest comparison vs "
                "manifest-cp01-before-token-piggy-bank.excl-data.txt.\n")
        f.write("# watcher: ReadDirectoryChangesW via ctypes, recursive, on each root\n")
        f.write("# driver: evidence/cpm1/tools/fswatch_driver_cpm1.py imports "
                "shell.tests._fswatch.FsWatch unmodified, roots passed explicitly\n")
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
    w = FsWatch(roots=ROOTS).start()
    print("FSWATCH-CPM1 started_utc={} roots={}".format(w.started_utc, w.roots), flush=True)
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
        print("FSWATCH-CPM1 stopped_utc={} window_s={:.0f} events={} errors={} out={}"
              .format(w.stopped_utc, seconds, len(events), len(w.errors), OUT), flush=True)
        if os.path.exists(STOP):
            os.remove(STOP)


if __name__ == "__main__":
    main()
