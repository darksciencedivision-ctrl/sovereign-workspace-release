"""Gate 5 shell-API client (builder inspection tool, stdlib only).

Sends requests exactly as the product requires them (server.py H-2: Host and Origin exact,
application/json body, per-instance CSRF nonce taken from the served HTML). Used only to drive
and record the shell's own routes; it is not part of the product.
"""
import json
import re
import sys
import urllib.request

BASE = "http://127.0.0.1:5180"
ORIGIN = "http://127.0.0.1:5180"


def fetch_nonce():
    req = urllib.request.Request(BASE + "/", headers={"Host": "127.0.0.1:5180"})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8")
    m = re.search(r'name="csrf-nonce" content="([0-9a-f]+)"', html)
    if not m:
        raise RuntimeError("csrf nonce not found in served HTML")
    return m.group(1)


def get(path):
    req = urllib.request.Request(BASE + path, headers={"Host": "127.0.0.1:5180"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8")


def post(path, body=None, timeout=180):
    nonce = fetch_nonce()
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data, method="POST",
        headers={
            "Host": "127.0.0.1:5180",
            "Origin": ORIGIN,
            "Content-Type": "application/json",
            "X-CSRF-Nonce": nonce,
        })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def main():
    cmd = sys.argv[1]
    out = sys.argv[-1]
    if cmd == "get":
        status, text = get(sys.argv[2])
    elif cmd == "startup-test":
        status, text = post("/api/startup-test", {"id": sys.argv[2]}, timeout=float(sys.argv[3]))
    elif cmd == "post":
        status, text = post(sys.argv[2], json.loads(sys.argv[3]), timeout=30)
    else:
        raise SystemExit("unknown command")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("# utc: {}\n".format(__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat()))
        f.write("# producer: ox-alpha GATE5\n")
        f.write("# request: {} -> HTTP {}\n".format(cmd, status))
        f.write(text.rstrip("\n") + "\n")
    print("HTTP {} -> {}".format(status, out))
    return 0 if status < 400 else 1


if __name__ == "__main__":
    sys.exit(main())
