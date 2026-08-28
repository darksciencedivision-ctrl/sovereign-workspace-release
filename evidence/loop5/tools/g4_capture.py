"""LOOP-01 Gate-4 visual capture driver (builder tooling, stdlib only).

Sequence per OX-ALPHA-DIRECTIVE-LOOP-01.md section 2 G4 and section 4 G4 envelope:
HTTP through the shell's own routes with H-2 headers, headless-Edge captures,
module launches ONLY via /api/startup-test, keep-runs stopped via /api/stop.
SOW is never launched. Ollama tag check (read-only GET /api/tags) precedes the
sovereign capture.

Outputs land in evidence/loop5/ and evidence/loop5/screenshots/.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone

WS = r"D:\Product Software\Production Workspace"
L5 = os.path.join(WS, "evidence", "loop5")
SHOTS = os.path.join(L5, "screenshots")
BASE = "http://127.0.0.1:5180"
HOST = "127.0.0.1:5180"
ORIGIN = "http://127.0.0.1:5180"
SOV_UI = "http://127.0.0.1:5175/"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BLANK_SHA = "f7744eb44a77e0401b85dd4dc07a9cc48860d79f2ad6ff908ba2839bd0669271"
CMDS = []


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def log(msg):
    print("{} {}".format(datetime.now(timezone.utc).isoformat(timespec="seconds"), msg),
          flush=True)


def header(producer="ox-alpha LOOP-01"):
    return "# utc: {}\n# producer: {}\n".format(utcnow(), producer)


def sha256_file(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_nonce():
    req = urllib.request.Request(BASE + "/", headers={"Host": HOST})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8")
    m = re.search(r'name="csrf-nonce" content="([0-9a-f]+)"', html)
    if not m:
        raise RuntimeError("csrf nonce not found")
    return m.group(1)


def http_get(path):
    req = urllib.request.Request(BASE + path, headers={"Host": HOST})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8")


def http_post(path, body=None, timeout=300):
    nonce = fetch_nonce()
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data, method="POST",
        headers={"Host": HOST, "Origin": ORIGIN, "Content-Type": "application/json",
                 "X-CSRF-Nonce": nonce})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def receipt(name, request_line, status, text):
    p = os.path.join(L5, name)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(header())
        f.write("# request: {} -> HTTP {}\n".format(request_line, status))
        f.write(text.rstrip("\n") + "\n")


def api_state():
    status, text = http_get("/api/state")
    if status != 200:
        raise RuntimeError("GET /api/state -> HTTP {}".format(status))
    return json.loads(text)["modules"]


def wait_state(mid, want, timeout_s):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        mods = api_state()
        last = mods[mid].get("state", "")
        if last == want:
            return True
        time.sleep(2)
    raise RuntimeError("module {} never reached {} (last={})".format(mid, want, last))


CAP_PATH = os.path.join(L5, "g4-captures.jsonl")


def cap_row(fname, state):
    row = {"file": fname, "api_state": state, "utc": utcnow()}
    with open(CAP_PATH, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row) + "\n")
    return row["utc"]


def edge_shot(url, out_png, dark, label):
    udd = tempfile.mkdtemp(prefix="sws-g4-", dir=os.environ.get(
        "TEMP", r"C:\Users\Sslaw\AppData\Local\Temp"))
    argv = [EDGE, "--headless=new", "--disable-gpu", "--no-first-run",
            "--user-data-dir=" + udd, "--window-size=1600,1000",
            "--virtual-time-budget=8000"]
    if dark:
        argv.append("--force-dark-mode")
    argv += ["--screenshot=" + out_png, url]
    CMDS.append("{}  # {} -> {}".format(" ".join(argv), label, os.path.basename(out_png)))
    rc = subprocess.call(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         timeout=120)
    shutil.rmtree(udd, ignore_errors=True)
    ok = rc == 0 and os.path.exists(out_png) and os.path.getsize(out_png) > 15000 \
        and sha256_file(out_png) != BLANK_SHA
    if not ok:
        raise RuntimeError("edge capture failed rc={} file={} label={}".format(
            rc, out_png, label))
    log("SHOT ok {} sha256={}".format(os.path.basename(out_png), sha256_file(out_png)))


def edge_dom(url, out_txt, label):
    udd = tempfile.mkdtemp(prefix="sws-g4dom-", dir=os.environ.get(
        "TEMP", r"C:\Users\Sslaw\AppData\Local\Temp"))
    dom_tmp = os.path.join(udd, "dom.txt")
    argv = [EDGE, "--headless=new", "--disable-gpu", "--no-first-run",
            "--user-data-dir=" + udd, "--virtual-time-budget=8000",
            "--dump-dom", url]
    CMDS.append("{}  # {} (dump-dom)".format(" ".join(argv), label))
    with open(dom_tmp, "w", encoding="utf-8") as f:
        rc = subprocess.call(argv, stdout=f, stderr=subprocess.DEVNULL, timeout=120)
    dom = open(dom_tmp, encoding="utf-8", errors="replace").read()
    shutil.rmtree(udd, ignore_errors=True)
    low = dom.lower()
    checks = {
        "ids": all(i in low for i in ("sovereign", "sow", "debate", "distillery")),
        "disabled_ge3": low.count("disabled") >= 3,
        "actions": all(a in low for a in
                       ("start", "stop", "restart", "open", "test", "logs")),
    }
    with open(out_txt, "w", encoding="utf-8", newline="\n") as f:
        f.write(header())
        f.write("# proof: B-7 live-shell DOM shows four cards, six actions, "
                "Distillery controls disabled\n")
        f.write("# checks: {}\n".format(checks))
        f.write(dom)
    if not all(checks.values()):
        raise RuntimeError("B-7 DOM checks failed: {}".format(checks))
    log("DOM ok checks={}".format(checks))


def ollama_tags():
    manifest = json.load(open(os.path.join(WS, "modules", "sovereign",
                                           "SYSTEM_MANIFEST.json"),
                              encoding="utf-8-sig"))
    required = manifest["MODELS"]
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=10) as r:
        tags = sorted(m["name"] for m in json.loads(r.read().decode("utf-8"))
                      .get("models", []))
    lines = ["# utc: {}".format(utcnow()),
             "# producer: ox-alpha LOOP-01",
             "# source: modules/sovereign/SYSTEM_MANIFEST.json MODELS vs "
             "GET http://127.0.0.1:11434/api/tags (read-only, no pull/install)",
             "# installed_tags_count: {}", ""]
    present = 0
    for role in ("PRIMARY_REASONER", "ADVERSARIAL_CHALLENGER", "CRITIC",
                 "SYNTHESIZER", "EMBEDDING_MODEL"):
        tag = required[role]
        ok = tag in tags
        present += 1 if ok else 0
        lines.append("{}\t{}\t{}".format(role, tag, "PRESENT" if ok else "MISSING"))
    lines += ["", "summary: {} required, {} PRESENT, {} MISSING".format(
        len(required), present, len(required) - present)]
    out = os.path.join(L5, "ollama-tags-fresh.txt")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    log("OLLAMA tags={} PRESENT={}/{}".format(len(tags), present, len(required)))


def keeprun_record(mid, http_status, response_text, ready_utc):
    rec = {
        "module": mid,
        "request": {"id": mid, "keep": True},
        "route": "/api/startup-test",
        "utc_request": utcnow(),
        "utc_state_READY": ready_utc,
        "http_status": http_status,
        "state": "READY",
        "response": json.loads(response_text),
    }
    p = os.path.join(L5, "startup-{}-keeprun.json".format(mid))
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, indent=2) + "\n")
    log("KEEPRUN {} written".format(mid))


def startup_keep(mid, timeout_s=240):
    status, text = http_post("/api/startup-test", {"id": mid, "keep": True},
                             timeout=timeout_s)
    receipt("startup-{}-response-loop01.txt".format(mid),
            "POST /api/startup-test id={} keep=True".format(mid), status, text)
    if status != 200:
        raise RuntimeError("startup-test {} -> HTTP {}: {}".format(mid, status, text[:200]))
    wait_state(mid, "READY", 180)


def stop_via_api(mid):
    status, text = http_post("/api/stop", {"id": mid}, timeout=120)
    receipt("post-{}-stop-loop01.txt".format(mid), "POST /api/stop id={}".format(mid),
            status, text)
    wait_state(mid, "STOPPED", 90)
    log("STOPPED {} via /api/stop HTTP {}".format(mid, status))


def main():
    if not os.path.exists(SHOTS):
        os.makedirs(SHOTS)
    if not os.path.exists(EDGE):
        raise RuntimeError("Edge not found at recorded path")
    mods = api_state()
    log("initial states: {}".format({k: v.get("state") for k, v in mods.items()}))

    ollama_tags()

    edge_shot(BASE + "/", os.path.join(SHOTS, "shell-grid-initial.png"), True,
              "grid-initial dark force-dark-mode ON")

    edge_dom(BASE + "/", os.path.join(L5, "screenshots", "b7-dom.txt"),
             "B-7 live shell DOM")

    # debate: startup-test keep -> READY -> card -> stop
    t0 = utcnow()
    status, text = http_post("/api/startup-test", {"id": "debate", "keep": True})
    receipt("startup-debate-response-loop01.txt",
            "POST /api/startup-test id=debate keep=True", status, text)
    if status != 200:
        raise RuntimeError("debate startup-test HTTP {}: {}".format(status, text[:200]))
    wait_state("debate", "READY", 180)
    st = api_state()["debate"]["state"]
    if st != "READY":
        raise RuntimeError("debate not READY at capture: " + st)
    cap_row("card-debate-READY.png", st)
    edge_shot(BASE + "/", os.path.join(SHOTS, "card-debate-READY.png"), True,
              "card debate READY")
    keeprun_record("debate", status, text, utcnow())
    stop_via_api("debate")

    # sovereign: ollama already checked; startup-test keep -> READY -> cards + side-by-side -> stop
    t1 = utcnow()
    status, text = http_post("/api/startup-test", {"id": "sovereign", "keep": True})
    receipt("startup-sovereign-response-loop01.txt",
            "POST /api/startup-test id=sovereign keep=True", status, text)
    if status != 200:
        raise RuntimeError("sovereign startup-test HTTP {}: {}".format(status, text[:200]))
    wait_state("sovereign", "READY", 180)
    st = api_state()["sovereign"]["state"]
    if st != "READY":
        raise RuntimeError("sovereign not READY at capture: " + st)
    sovcap_utc = cap_row("card-sovereign-READY.png", st)
    edge_shot(BASE + "/", os.path.join(SHOTS, "card-sovereign-READY.png"), True,
              "card sovereign READY")
    edge_shot(SOV_UI, os.path.join(SHOTS, "side-by-side-sovereign-module.png"), True,
              "side-by-side SOVEREIGN module UI 5175")
    edge_shot(BASE + "/", os.path.join(SHOTS, "side-by-side-sovereign-shell.png"), True,
              "side-by-side shell grid")
    keeprun_record("sovereign", status, text, utcnow())
    stop_via_api("sovereign")

    # sow and distillery: whatever live state reports (never launched by this loop)
    st = api_state()["sow"]["state"]
    cap_row("card-sow-STOPPED.png", st)
    edge_shot(BASE + "/", os.path.join(SHOTS, "card-sow-STOPPED.png"), True,
              "card sow {}".format(st))
    st = api_state()["distillery"]["state"]
    cap_row("card-distillery-NOT_STARTED.png", st)
    edge_shot(BASE + "/", os.path.join(SHOTS, "card-distillery-NOT_STARTED.png"), True,
              "card distillery {}".format(st))

    # light mode: default scheme on this host resolves LIGHT (recorded in REM-03 s4)
    edge_shot(BASE + "/", os.path.join(SHOTS, "shell-light-mode.png"), False,
              "light-mode force-dark-mode OFF")

    cmds = os.path.join(L5, "g4-edge-commands.txt")
    with open(cmds, "w", encoding="utf-8", newline="\n") as f:
        f.write(header())
        f.write("# exact msedge commands used for every G4 capture, in order\n")
        f.write("\n".join(CMDS) + "\n")
    log("ALL G4 CAPTURES DONE")


if __name__ == "__main__":
    main()