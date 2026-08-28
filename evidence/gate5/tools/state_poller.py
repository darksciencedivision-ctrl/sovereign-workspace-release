"""Gate 5 B-1: poll GET /api/state every 2 s, append utc/module/state/reason rows."""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

WS = r"D:\Product Software\Production Workspace"
OUT = os.path.join(WS, "evidence", "gate5", "states-timeline.txt")
STOP = os.path.join(WS, "evidence", "gate5", "tools", "poller.stop")

if not os.path.exists(OUT):
    with open(OUT, "a", encoding="utf-8", newline="\n") as f:
        f.write("# utc: {}\n".format(datetime.now(timezone.utc).isoformat()))
        f.write("# producer: ox-alpha GATE5\n")
        f.write("# source: GET http://127.0.0.1:5180/api/state every 2 s\n")
        f.write("utc\tmodule\tstate\treason\n")

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
print("poller stopped")
