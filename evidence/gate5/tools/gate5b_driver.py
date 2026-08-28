"""Gate 5 visual re-run session driver (REM-02 section 4 step 5; work order OX-ALPHA-DIRECTIVE-GATE5).

Builder tooling only, stdlib only. Patterns are reused unmodified from the proven Gate 5 tools
(fswatch_driver.py / state_poller.py / shell_driver.py / api_client.py) with outputs retargeted to
*-gate5b* filenames so no artifact cited by the Gate 5 STOP ledger entry is overwritten.

Modes:
  fswatch        H-12 watcher over the three protected roots -> fs-watch-gate5b.txt
                 (stop via sentinel fswatch-gate5b.stop next to this script)
  poller         GET /api/state every 2 s -> states-timeline-gate5b.txt
                 (stop via sentinel poller-gate5b.stop)
  shell          start the product shell exactly as the README says, detached, new process
                 group; stop ONLY via its own shutdown path on sentinel shell-gate5b.stop
  client ...     HTTP client speaking exactly what server.py H-2 requires:
                   get <path> <out>
                   post <path> <json-body> <out>
                   startup-test <module-id> <keep|stop> <timeout-s> <out>
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

WS = r"D:\Product Software\Production Workspace"
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "http://127.0.0.1:5180"
ORIGIN = "http://127.0.0.1:5180"
HOST = "127.0.0.1:5180"


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def header_lines(producer="ox-alpha GATE5B"):
    return "# utc: {}\n# producer: {}\n".format(utcnow(), producer)


# ---------------------------------------------------------------- fswatch ----
def mode_fswatch():
    sys.path.insert(0, WS)
    from shell.tests._fswatch import FsWatch  # noqa: E402
    out_path = os.path.join(WS, "evidence", "gate5", "fs-watch-gate5b.txt")
    stop = os.path.join(HERE, "fswatch-gate5b.stop")
    w = FsWatch().start()
    print("FSWATCH-GATE5B started_utc={} roots={}".format(w.started_utc, w.roots), flush=True)
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
        while not stopping["flag"] and not os.path.exists(stop):
            time.sleep(0.5)
    finally:
        events = w.stop()
        mine = w.duration_s()
        d = os.path.dirname(out_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(header_lines())
            f.write("# proof: H-12 - no runtime writes outside Production Workspace\\\n")
            f.write("# watcher: ReadDirectoryChangesW via ctypes, recursive, on each root\n")
            f.write("# driver: evidence/gate5/tools/gate5b_driver.py imports "
                    "shell.tests._fswatch.FsWatch unmodified\n")
            f.write("# window: {} .. {}\n".format(w.started_utc, w.stopped_utc))
            for root in w.roots:
                f.write("# root: {}\n".format(root))
            f.write("# ignored under D:\\Product Software: Production Workspace\\ "
                    "(this workspace's own writes)\n")
            f.write("# events: {}\n".format(len(events)))
            if w.errors:
                f.write("# watcher-errors: {}\n".format(len(w.errors)))
                for e in w.errors:
                    f.write("# watcher-error: {}\n".format(e))
            f.write("# window-seconds: {:.0f}\n".format(mine))
            for ev in events:
                f.write("{}\t{}\t{}\t{}\n".format(
                    ev["utc"], ev["root"], ev["action"], ev["path"]))
        print("FSWATCH-GATE5B stopped_utc={} window_s={:.0f} events={} errors={} out={}"
              .format(w.stopped_utc, mine, len(events), len(w.errors), out_path), flush=True)
        if os.path.exists(stop):
            os.remove(stop)


# ----------------------------------------------------------------- poller ----
def mode_poller():
    out = os.path.join(WS, "evidence", "gate5", "states-timeline-gate5b.txt")
    stop = os.path.join(HERE, "poller-gate5b.stop")
    if not os.path.exists(out):
        with open(out, "a", encoding="utf-8", newline="\n") as f:
            f.write(header_lines())
            f.write("# source: GET http://127.0.0.1:5180/api/state every 2 s\n")
            f.write("utc\tmodule\tstate\treason\n")
    while not os.path.exists(stop):
        try:
            r = urllib.request.urlopen(urllib.request.Request(
                BASE + "/api/state", headers={"Host": HOST}), timeout=5)
            data = json.loads(r.read().decode("utf-8"))
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            rows = []
            for mid, rec in sorted(data["modules"].items()):
                rows.append("{}\t{}\t{}\t{}".format(
                    ts, mid, rec.get("state", ""), rec.get("reason", "")))
            with open(out, "a", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(rows) + "\n")
        except Exception as e:
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with open(out, "a", encoding="utf-8", newline="\n") as f:
                f.write("{}\t-\tPOLL_ERROR\t{}\n".format(ts, type(e).__name__))
        time.sleep(2)
    os.remove(stop)
    print("poller stopped")


# ------------------------------------------------------------------ shell ----
def mode_shell():
    out = os.path.join(WS, "evidence", "gate5", "shell-stdout-gate5b.txt")
    err = os.path.join(WS, "evidence", "gate5", "shell-stderr-gate5b.txt")
    stop = os.path.join(HERE, "shell-gate5b.stop")
    pidfile = os.path.join(WS, "evidence", "gate5", "shell-gate5b.pid")
    argv = ["py", "-3.12", "-B", "-m", "shell.src"]
    with open(out, "ab", buffering=0) as fo, open(err, "ab", buffering=0) as fe:
        proc = subprocess.Popen(
            argv, cwd=WS, stdout=fo, stderr=fe,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        with open(pidfile, "w") as f:
            f.write(str(proc.pid))
        print("SHELL-GATE5B started pid={} argv={}".format(proc.pid, argv), flush=True)
        stopped_by = None
        try:
            while not os.path.exists(stop):
                rc = proc.poll()
                if rc is not None:
                    stopped_by = "exited rc={}".format(rc)
                    break
                time.sleep(0.4)
        finally:
            if stopped_by is None:
                stopped_by = "stopfile"
                try:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception as e:
                    print("SHELL-GATE5B signal error: {!r}".format(e), flush=True)
            try:
                rc = proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                print("SHELL-GATE5B did not exit within 30 s of CTRL_BREAK", flush=True)
                rc = None
            print("SHELL-GATE5B stop={} exit_code={}".format(stopped_by, rc), flush=True)
            if os.path.exists(stop):
                os.remove(stop)
            try:
                os.remove(pidfile)
            except OSError:
                pass


# ----------------------------------------------------------------- client ----
def fetch_nonce():
    req = urllib.request.Request(BASE + "/", headers={"Host": HOST})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8")
    m = re.search(r'name="csrf-nonce" content="([0-9a-f]+)"', html)
    if not m:
        raise RuntimeError("csrf nonce not found in served HTML")
    return m.group(1)


def http_get(path):
    req = urllib.request.Request(BASE + path, headers={"Host": HOST})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8")


def http_post(path, body=None, timeout=180):
    nonce = fetch_nonce()
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data, method="POST",
        headers={
            "Host": HOST,
            "Origin": ORIGIN,
            "Content-Type": "application/json",
            "X-CSRF-Nonce": nonce,
        })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def write_out(out, request_line, status, text):
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(header_lines())
        f.write("# request: {} -> HTTP {}\n".format(request_line, status))
        f.write(text.rstrip("\n") + "\n")
    print("HTTP {} -> {}".format(status, out))


def mode_client(args):
    cmd = args[0]
    if cmd == "get":
        status, text = http_get(args[1])
        write_out(args[2], "GET {}".format(args[1]), status, text)
    elif cmd == "post":
        status, text = http_post(args[1], json.loads(args[2]))
        write_out(args[2], "POST {} {}".format(args[1], args[2]), status, text)
    elif cmd == "stop":
        status, text = http_post("/api/stop", {"id": args[1]})
        write_out(args[2], "POST /api/stop id={}".format(args[1]), status, text)
    elif cmd == "startup-test":
        keep = args[2] == "keep"
        status, text = http_post("/api/startup-test",
                                 {"id": args[1], "keep": keep},
                                 timeout=float(args[3]))
        write_out(args[4], "POST /api/startup-test id={} keep={}".format(args[1], keep),
                  status, text)
    else:
        raise SystemExit("unknown client command")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "fswatch":
        mode_fswatch()
    elif mode == "poller":
        mode_poller()
    elif mode == "shell":
        mode_shell()
    elif mode == "client":
        mode_client(sys.argv[2:])
    else:
        raise SystemExit("unknown mode")
