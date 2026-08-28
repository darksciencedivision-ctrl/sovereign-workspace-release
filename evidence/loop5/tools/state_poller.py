"""LOOP-01 B-1 state poller (adapted from evidence/gate5/tools/state_poller.py).

Polls GET http://127.0.0.1:5180/api/state every 2 s and appends utc/module/state/reason rows to
evidence/loop5/states-timeline.txt. Stops when sentinel poller.stop appears next to this script.
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

WS = r"D:\Product Software\Production Workspace"
OUT = os.path.join(WS, "evidence", "loop5", "states-timeline.txt")
HERE = os.path.dirname(os.path.abspath(__file__))
STOP = os.path.join(HERE, "poller.stop")
PIDFILE = os.path.join(HERE, "poller.pid")

if not os.path.exists(OUT):
    with open(OUT, "a", encoding="utf-8", newline="\n") as f:
        f.write("# utc: {}\n".format(datetime.now(timezone.utc).isoformat()))
        f.write("# producer: ox-alpha LOOP-01\n")
        f.write("# source: GET http://127.0.0.1:5180/api/state every 2 s\n")
        f.write("utc\tmodule\tstate\treason\n")

with open(PIDFILE, "w") as f:
    f.write(str(os.getpid()))

while not os.path.exists(STOP):
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            "http://127.0.0.1:5180/api/state", headers={"Host": "127.0.0.1:5180"}), timeout=5)
        data = json.loads(r.read().decode("utf-8"))
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = []
        for mid, rec in sorted(data["modules"].items()):
            rows.append("{}\t{}\t{}\t{}".format(
                ts, mid, rec.get("state", ""), rec.get("reason", "")))
        with open(OUT, "a", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(rows) + "\n")
    except Exception as e:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(OUT, "a", encoding="utf-8", newline="\n") as f:
            f.write("{}\t-\tPOLL_ERROR\t{}\n".format(ts, type(e).__name__))
    time.sleep(2)

os.remove(STOP)
try:
    os.remove(PIDFILE)
except OSError:
    pass
print("poller stopped")