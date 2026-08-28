"""LOOP-01 goalcheck oracle (docs/OX-ALPHA-DIRECTIVE-LOOP-01.md section 3).

py -3.12, stdlib only. Reads the workspace from disk and evaluates goals G0..G7 as
machine-checkable predicates. Writes evidence/loop5/goalcheck-<i>.txt. Read-only against
the workspace apart from its own goalcheck report file.

usage: py -3.12 evidence/loop5/tools/goalcheck.py <iteration-number-or-tag>
"""
import ctypes
import hashlib
import json
import os
import re
import socket
import struct
import sys
import zlib
from datetime import datetime, timezone

WS = r"D:\Product Software\Production Workspace"
EV = os.path.join(WS, "evidence")
L5 = os.path.join(EV, "loop5")
DEC = "bb911905c68b85f2c8abd5d3d2db8176cbd7a6999f8ed93fd815b4185c14869a"
CSS_V2 = "329a52a175da7ccb37909b5fbfa009dd2f444a9f4d2a1b748ee86c2080ecb8ab"
BLANK_PNG = "f7744eb44a77e0401b85dd4dc07a9cc48860d79f2ad6ff908ba2839bd0669271"
CLAIM = ("BUILDER CLAIM: Gate 4c and Gate 5b are CANDIDATEs for reviewer evaluation. "
         "No PASS status is asserted by the builder.")
KICKOFF_MARK = "STOP-REPORT-SOW-TREE-ACTIVITY option 2 is selected"
KICKOFF_UTC = "2026-08-24T06:42:39"
ORIG_MANIFEST_SHA = {
    "product-software": "a3335e702d7a97232b8799e695d27e0d7889ff12b9099ae3e798e40bf6fbf21d",
    "sow": "4b0c2b9610c14a6ff6954b2e6780b4f392e407aa30613fb4a18d53be58a84545",
    "distillery": "cdbe99323a98a19752623e6399ed0570a61483f3487dfc41d48eef0fe5f4428f",
}
ORIG_SOWGIT_BODY_SHA = "b9ed2c0b2fc6a4f2bc75ad3d11b06af6f266df8f09e3ad6c4b33ceed8c9a08da"
REVIEWER_KEYS = ["0", "1", "2", "3", "4", "4b", "5", "6"]
G3_REQUIRED = [
    "docs/THEME-BASELINE-v2.md",
    "shell/static/app.css",
    "evidence/rem03/linecount.txt",
    "evidence/rem03/contrast-preview.txt",
    "evidence/hardening/h16-contrast.txt",
    "evidence/test-run.txt",
    "shell/BUILD-MANIFEST.txt",
]
G6_REQUIRED = G3_REQUIRED + [
    "evidence/rem03/sow-git-rem03-before.body",
    "evidence/rem03/sow-git-rem03-before.meta.json",
    "evidence/manifests/manifest-rem03-before-product-software.txt",
    "evidence/manifests/manifest-rem03-before-sow.txt",
    "evidence/manifests/manifest-rem03-before-distillery.txt",
    "evidence/rem03/quiescence-inspect-1.txt",
    "evidence/rem03/quiescence-inspect-2.txt",
    "evidence/loop5/fs-watch-loop01.txt",
    "evidence/loop5/orphans-after-loop01.txt",
    "evidence/loop5/states-timeline.txt",
    "evidence/loop5/screenshots/b7-dom.txt",
    "evidence/loop5/ollama-tags-fresh.txt",
]
G4_SHOTS = [
    "shell-grid-initial.png",
    "card-sovereign-READY.png",
    "card-debate-READY.png",
    "card-sow-STOPPED.png",
    "card-distillery-NOT_STARTED.png",
]


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def rd(p):
    with open(p, "r", encoding="utf-8-sig") as f:
        return f.read()


def rdb(p):
    with open(p, "rb") as f:
        return f.read()


def exists(p):
    return os.path.isfile(p)


def parse_iso(s):
    s = s.strip().rstrip("Z")
    if "." in s:
        frac = s.split(".")[1]
        s = s.split(".")[0] + "." + frac[:6].ljust(6, "0")
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
        return datetime.strptime(s.split("+")[0].split("Z")[0], "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
    return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def port_free(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        s.close()
        return False
    except OSError:
        return True


def pid_alive(pid):
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, int(pid))
    if not h:
        return False
    code = ctypes.c_ulong(0)
    ok = k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    return bool(ok) and code.value == 259


def png_info(path):
    """Minimal stdlib PNG decode; returns (w, h, getpx(x,y)->(r,g,b)) or None."""
    try:
        data = rdb(path)
    except OSError:
        return None
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos = 8
    idat = b""
    w = h = height = 0
    bitd, color, interlace = 8, 6, 0
    height, bitd, color, interlace = 0, 8, 6, 0
    while pos + 8 <= len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, height, bitd, color, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
        pos += 12 + ln
    if not idat or w < 1 or height < 1 or bitd != 8 or interlace != 0:
        return None
    ch = {0: 1, 2: 3, 4: 2, 6: 4}.get(color)
    if ch is None:
        return None
    raw = zlib.decompress(idat)
    stride = w * ch
    out = bytearray(height * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(height):
        if p >= len(raw):
            return None
        ft = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if len(line) < stride:
            return None
        if ft == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 0xFF
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line

    def getpx(x, y):
        o = y * stride + x * ch
        px = out[o:o + ch]
        if ch == 1:
            return (px[0], px[0], px[0])
        if ch == 2:
            return (px[0], px[1], px[0])
        return (px[0], px[1], px[2])

    return w, height, getpx


def luminance(px):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = px
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def sample_pixels(path, n=36):
    info = png_info(path)
    if info is None:
        return None
    w, h, getpx = info
    cols, rows = 6, 6
    pts = []
    for j in range(rows):
        for i in range(cols):
            x = int((i + 0.5) * w / cols)
            y = int((j + 0.5) * h / rows)
            pts.append(getpx(min(x, w - 1), min(y, h - 1)))
    return w, h, pts


def shot_ok(path):
    """Non-blank decodable screenshot: != blank sentinel hash and >=8 distinct colours
    across a dense pixel walk (sparse grids under-sample a dark low-chroma UI)."""
    if not exists(path):
        return False, "missing"
    if sha256_file(path) == BLANK_PNG:
        return False, "blank sentinel hash"
    info = png_info(path)
    if info is None:
        return False, "undecodable PNG"
    w, h, getpx = info
    if w < 800 or h < 600:
        return False, "too small {}x{}".format(w, h)
    sx = max(1, w // 160)
    sy = max(1, h // 120)
    seen = set()
    for y in range(0, h, sy):
        for x in range(0, w, sx):
            seen.add(getpx(x, y))
            if len(seen) >= 8:
                break
        if len(seen) >= 8:
            break
    if len(seen) < 8:
        return False, "uniform-ish ({} distinct colours)".format(len(seen))
    pts = [getpx(min(int((i + .5) * w / 6), w - 1), min(int((j + .5) * h / 6), h - 1))
           for j in range(6) for i in range(6)]
    lums = sorted(luminance(p) for p in pts)
    med = lums[len(lums) // 2]
    return True, "{}x{} distinct>=8 median_lum={:.3f}".format(w, h, med)


def bg_is_light(path):
    s = sample_pixels(path)
    if s is None:
        return False, "undecodable"
    w, h, pts = s
    lums = sorted(luminance(p) for p in pts)
    med = lums[len(lums) // 2]
    return med > 0.55, "median_lum={:.3f}".format(med)


def ledger_parts():
    p = os.path.join(EV, "GATE-LEDGER.json")
    return p, rdb(p).decode("utf-8")


def ledger_others_equal(cur_raw, snap_raw, keys_to_ignore):
    i_c, i_s = cur_raw.find('"4c"'), snap_raw.find('"4c"')
    if i_c < 0 or i_s < 0:
        return False, ["marker 4c missing"]
    pre_ok = cur_raw[:i_c] == snap_raw[:i_s]
    e_c = cur_raw.find("\n  }\n}", i_c)
    e_s = snap_raw.find("\n  }\n}", i_s)
    suf_ok = e_c >= 0 and e_s >= 0 and cur_raw[e_c:] == snap_raw[e_s:]
    try:
        cj, sj = json.loads(cur_raw), json.loads(snap_raw)
    except ValueError as ex:
        return False, ["json parse error: {}".format(ex)]
    cg = dict(cj.get("gates", {}))
    sg = dict(sj.get("gates", {}))
    for k in keys_to_ignore:
        cg.pop(k, None)
        sg.pop(k, None)
    sem_ok = cg == sg
    return pre_ok and suf_ok and sem_ok, [
        "prefix_byte_identical={}".format(pre_ok),
        "suffix_byte_identical={}".format(suf_ok),
        "other_entries_semantically_identical={}".format(sem_ok),
    ]


def valid_evidence_list(entry, required, root=WS):
    det = []
    ok = entry.get("status") == "CANDIDATE"
    det.append("status==CANDIDATE: {}".format(ok))
    items = entry.get("evidence", [])
    seen = set()
    hexre = re.compile(r"^[0-9a-f]{64}$")
    all_hex = True
    all_match = True
    for it in items:
        h = str(it.get("sha256", ""))
        if not hexre.match(h):
            all_hex = False
        fp = os.path.join(root, it.get("path", "").replace("/", os.sep))
        if not exists(fp):
            all_match = False
            continue
        if sha256_file(fp) != h:
            all_match = False
        seen.add(it.get("path"))
    missing = [r for r in required if r not in seen]
    ok = ok and items and all_hex and all_match and not missing
    det.append("entries={} all_lowercase_64hex={} hashes_match_disk={} required_missing={}"
               .format(len(items), all_hex, all_match, missing))
    return ok, det


def g0():
    det = []
    ss = os.path.join(L5, "session-start.txt")
    ok = exists(ss)
    det.append("session-start.txt exists={}".format(ok))
    if ok:
        t = rd(ss)
        ok = ok and DEC in t and "PORTS_5175_8700_5180: FREE" in t
        det.append("capture content ok={}".format(DEC in t and "PORTS_5175_8700_5180: FREE" in t))
    rv = os.path.join(L5, "session-start-reverify.txt")
    det.append("post-reset reverify exists={}".format(exists(rv)))
    ok = ok and exists(rv)
    logp = os.path.join(EV, "OPERATOR-INSTRUCTIONS.log")
    logok = exists(logp) and KICKOFF_MARK in rd(logp) and KICKOFF_UTC in rd(logp)
    det.append("kickoff logged verbatim={}".format(logok))
    ok = ok and logok
    dp = os.path.join(WS, "docs", "DECISIONS.md")
    dhash = sha256_file(dp) if exists(dp) else "?"
    det.append("DECISIONS.md sha match={}".format(dhash == DEC))
    ok = ok and dhash == DEC
    free = {p: port_free(p) for p in (5175, 8700, 5180)}
    det.append("ports free now: {}".format(free))
    # G0 is the session PRECONDITION (directive section 2): helpers ran detached
    # through the working loop; G5 legitimately stops them before exit, so the
    # final all-goals check evaluates the persisted record of detached operation,
    # not liveness at check time.
    fw_txt = os.path.join(L5, "fs-watch-loop01.txt")
    fw_ok = exists(fw_txt) and "# events:" in rd(fw_txt) and "# window:" in rd(fw_txt)
    det.append("watcher ran detached (fs-watch artifact)={}".format(fw_ok))
    tl = os.path.join(L5, "states-timeline.txt")
    tl_ok = exists(tl) and len(rd(tl).splitlines()) > 1000
    det.append("poller ran detached (states-timeline rows>1000)={}".format(tl_ok))
    so = os.path.join(L5, "shell-stdout.txt")
    sh_ok = exists(so) and ("listening on http://127.0.0.1:5180" in rd(so))
    det.append("shell ran detached (stdout listening line)={}".format(sh_ok))
    p5180_ok = free[5180] or sh_ok
    det.append("5180 ok (free now, or was held by detached shell)={}".format(p5180_ok))
    ok = ok and free[5175] and free[8700] and p5180_ok \
        and fw_ok and tl_ok and sh_ok
    return ok, det


def g1():
    det = []
    q1 = os.path.join(EV, "rem03", "quiescence-inspect-1.txt")
    q2 = os.path.join(EV, "rem03", "quiescence-inspect-2.txt")
    okq = exists(q1) and exists(q2)
    gap_ok = identical = False
    if okq:
        t1, t2 = rd(q1), rd(q2)
        u1 = re.search(r"# utc: (\S+)", t1)
        u2 = re.search(r"# utc: (\S+)", t2)
        if u1 and u2:
            dt = (parse_iso(u2.group(1)) - parse_iso(u1.group(1))).total_seconds()
            gap_ok = dt >= 60
            det.append("inspection gap seconds={:.0f} (>=60: {})".format(dt, gap_ok))
        body1 = "\n".join(l for l in t1.splitlines() if not l.startswith("# utc:") and not l.startswith("# captured:"))
        body2 = "\n".join(l for l in t2.splitlines() if not l.startswith("# utc:") and not l.startswith("# captured:"))
        identical = body1 == body2 and body1.strip() != ""
        det.append("inspections byte-identical(non-header)={}".format(identical))
    okq = okq and gap_ok and identical
    man_ok = True
    for root, want in ORIG_MANIFEST_SHA.items():
        mp = os.path.join(EV, "manifests", "manifest-rem03-before-{}.txt".format(root))
        e = exists(mp)
        named = e and "supersedes" in rd(mp).lower() and want in rd(mp)
        man_ok = man_ok and e and named
        det.append("manifest-rem03-before-{}: exists={} names_original_and_hash={}".format(root, e, named))
    gb = os.path.join(EV, "rem03", "sow-git-rem03-before.body")
    gm = os.path.join(EV, "rem03", "sow-git-rem03-before.meta.json")
    gok = exists(gb) and exists(gm)
    foursec = gok and rd(gb).count("\n### ") == 4
    meta_names = gok and "supersedes" in rd(gm).lower()
    det.append("sow-git-rem03-before.body exists={} four_sections={} meta_names_superseded={}"
               .format(gok, foursec, meta_names))
    orig_ok = True
    for root, want in ORIG_MANIFEST_SHA.items():
        fp = os.path.join(EV, "manifests", "manifest-before-{}.txt".format(root))
        m = exists(fp) and sha256_file(fp) == want
        orig_ok = orig_ok and m
        det.append("original manifest-before-{} untouched={}".format(root, m))
    ob = os.path.join(EV, "sow-git-before.body")
    om = exists(ob) and sha256_file(ob) == ORIG_SOWGIT_BODY_SHA
    det.append("original sow-git-before.body untouched={}".format(om))
    ok = okq and man_ok and gok and foursec and meta_names and orig_ok and om
    return ok, det


def g2():
    det = []
    tr = os.path.join(EV, "test-run.txt")
    ok = exists(tr)
    ran_n = end_ok = after_g1 = bm_ok = css_ok = False
    if ok:
        t = rd(tr)
        m = re.search(r"Ran (\d+) tests", t)
        ran_n = bool(m) and int(m.group(1)) >= 121
        lines = [l.strip() for l in t.strip().splitlines() if l.strip()]
        end_ok = lines[-1] == "OK" or lines[-1].startswith("OK")
        q2u = re.search(r"# utc: (\S+)", rd(os.path.join(EV, "rem03", "quiescence-inspect-2.txt"))) \
            if exists(os.path.join(EV, "rem03", "quiescence-inspect-2.txt")) else None
        mt = datetime.fromtimestamp(os.path.getmtime(tr), tz=timezone.utc)
        after_g1 = q2u is not None and mt > parse_iso(q2u.group(1))
        det.append("test-run.txt: ran_{}_ge121={} ends_OK={} mtime_after_G1={}"
                   .format(m.group(1) if m else "?", ran_n, end_ok, after_g1))
    ok = ok and ran_n and end_ok and after_g1
    bmp = os.path.join(WS, "shell", "BUILD-MANIFEST.txt")
    n_ent = bad = 0
    if exists(bmp):
        for line in rd(bmp).splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split("  ", 1)
            if len(parts) != 2 or not re.match(r"^[0-9a-f]{64}$", parts[0]):
                continue
            n_ent += 1
            fp = os.path.join(WS, "shell", parts[1].replace("/", os.sep))
            if not exists(fp) or sha256_file(fp) != parts[0]:
                bad += 1
    bm_ok = n_ent > 0 and bad == 0
    det.append("BUILD-MANIFEST entries={} mismatched={} ".format(n_ent, bad))
    ok = ok and bm_ok
    cp = os.path.join(WS, "shell", "static", "app.css")
    css_ok = exists(cp) and sha256_file(cp) == CSS_V2
    det.append("app.css == v2 pinned hash: {}".format(css_ok))
    ok = ok and css_ok
    return ok, det


def g3():
    det = []
    p, cur = ledger_parts()
    snap_p = os.path.join(L5, "ledger-snap-pre4c.json")
    ok = exists(snap_p)
    det.append("snapshot pre4c exists={}".format(ok))
    if not ok:
        return False, det
    # ignore builder-written keys: 5b is authored later in the same loop than
    # this pre-4c snapshot; reviewer-evaluated entries must stay identical.
    eq, edet = ledger_others_equal(cur, rd(snap_p), ["4c", "5b"])
    det.extend(edet)
    j = json.loads(cur)
    entry = j.get("gates", {}).get("4c", {})
    vok, vdet = valid_evidence_list(entry, G3_REQUIRED)
    det.extend(vdet)
    return ok and eq and vok, det


def g4():
    det = []
    shots = os.path.join(L5, "screenshots")
    ok = True
    states = {}
    cap_path = os.path.join(L5, "g4-captures.jsonl")
    caps = []
    if exists(cap_path):
        for line in rd(cap_path).splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                try:
                    caps.append(json.loads(line))
                except ValueError:
                    pass
    for fn in G4_SHOTS:
        good, why = shot_ok(os.path.join(shots, fn))
        ok = ok and good
        m = re.match(r"card-([a-z]+)-([A-Z_]+)\.png$", fn)
        if m and good:
            row = next((c for c in caps if c.get("file") == fn), None)
            stmatch = row is not None and row.get("api_state") == m.group(2)
            states[fn] = "state_record_match={}".format(stmatch)
            ok = ok and stmatch
        det.append("{}: {}".format(fn, why if not good else good and (states.get(fn) or why)))
    pair = ["side-by-side-sovereign-shell.png", "side-by-side-sovereign-module.png"]
    for fn in pair:
        good, why = shot_ok(os.path.join(shots, fn))
        ok = ok and good
        det.append("{}: {}".format(fn, why))
    lm = os.path.join(shots, "shell-light-mode.png")
    light, lwhy = bg_is_light(lm) if exists(lm) else (False, "missing")
    ok = ok and light
    det.append("shell-light-mode.png light_bg={} ({})".format(light, lwhy))
    b7 = os.path.join(shots, "b7-dom.txt")
    bok = exists(b7)
    if bok:
        t = rd(b7).lower()
        ids = all(i in t for i in ("sovereign", "sow", "debate", "distillery"))
        dis = t.count("disabled") >= 3
        acts = all(a in t for a in ("start", "stop", "restart", "open", "test", "logs"))
        bok = ids and dis and acts
        det.append("b7-dom.txt ids={} disabled>=3={} six_actions={}".format(ids, dis, acts))
    ok = ok and bok
    ol = os.path.join(L5, "ollama-tags-fresh.txt")
    olok = exists(ol)
    before_sov = False
    sovcap = next((c for c in caps if c.get("file") == "card-sovereign-READY.png"), None)
    if olok and sovcap:
        ou = re.search(r"# utc: (\S+)", rd(ol))
        before_sov = ou is not None and parse_iso(ou.group(1)) <= parse_iso(sovcap["utc"])
    ok = ok and olok and before_sov
    det.append("ollama-tags-fresh precedes sovereign capture={}".format(before_sov))
    kr = []
    for mid in ("debate", "sovereign"):
        kp = os.path.join(L5, "startup-{}-keeprun.json".format(mid))
        k = exists(kp) and '"keep": true' in rd(kp) and '"READY"' in rd(kp)
        kr.append((mid, k))
        ok = ok and k
    det.append("keep-run records READY: {}".format(kr))
    tl = os.path.join(L5, "states-timeline.txt")
    sow_never = sov_stopped_after = False
    if exists(tl) and sovcap:
        rows = [l for l in rd(tl).splitlines() if re.match(r"\d{4}-", l)]
        sow_bad = [r for r in rows if re.search(r"\tsow\t(STARTING|READY|DEGRADED)\t", r)]
        sow_never = not sow_bad
        cutoff = sovcap["utc"][:19]
        sov_stopped_after = any(r.split("\t")[0] >= cutoff and "\tsovereign\tSTOPPED\t" in r for r in rows)
        det.append("timeline: sow never launched={} sovereign STOPPED after capture={}"
                   .format(sow_never, sov_stopped_after))
    ok = ok and sow_never and sov_stopped_after
    return ok, det


def g5():
    det = []
    fw = os.path.join(L5, "fs-watch-loop01.txt")
    ok = exists(fw)
    bracket = zeroev = False
    if ok:
        t = rd(fw)
        m = re.search(r"# events: (\d+)", t)
        zeroev = bool(m) and int(m.group(1)) == 0
        mw = re.search(r"# window: (\S+) \.\. (\S+)", t)
        q1 = os.path.join(EV, "rem03", "quiescence-inspect-1.txt")
        cap_path = os.path.join(L5, "g4-captures.jsonl")
        last_cap = None
        if exists(cap_path):
            for line in rd(cap_path).splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        u = json.loads(line).get("utc")
                        if u and (last_cap is None or u > last_cap):
                            last_cap = u
                    except ValueError:
                        pass
        if mw and exists(q1) and last_cap:
            a, b = parse_iso(mw.group(1)), parse_iso(mw.group(2))
            bracket = a <= parse_iso(re.search(r"# utc: (\S+)", rd(q1)).group(1)) and b >= parse_iso(last_cap)
        det.append("fs-watch events_zero={} brackets_G1_to_G4={}".format(zeroev, bracket))
    ok = ok and zeroev and bracket
    op = os.path.join(L5, "orphans-after-loop01.txt")
    ook = exists(op)
    if ook:
        t = rd(op)
        ook = ("MODULE_PROCESSES: NONE" in t) and ("PORT 5175: FREE" in t) \
            and ("PORT 8700: FREE" in t) and ("PORT 5180: FREE" in t)
    det.append("orphans-after-loop01.txt clean={}".format(ook))
    ok = ok and ook
    stopped = port_free(5180) and not exists(os.path.join(L5, "shell.pid")) \
        and not exists(os.path.join(L5, "tools", "poller.pid")) \
        and not exists(os.path.join(L5, "tools", "fswatch-driver.pid"))
    det.append("shell stopped via own path, pid sentinels cleared={}".format(stopped))
    ok = ok and stopped
    return ok, det


def g6():
    det = []
    p, cur = ledger_parts()
    snap_p = os.path.join(L5, "ledger-snap-pre5c.json")
    ok = exists(snap_p)
    det.append("snapshot pre5c exists={}".format(ok))
    if not ok:
        return False, det
    eq, edet = ledger_others_equal(cur, rd(snap_p), ["4c", "5b"])
    det.extend(edet)
    j = json.loads(cur)
    entry = j.get("gates", {}).get("5b", {})
    vok, vdet = valid_evidence_list(entry, G6_REQUIRED)
    det.extend(vdet)
    c4c = j.get("gates", {}).get("4c", {}).get("status") == "CANDIDATE"
    det.append("4c still CANDIDATE={}".format(c4c))
    return ok and eq and vok and c4c, det


def g7():
    det = []
    rp = os.path.join(WS, "docs", "REM-03-REPORT.md")
    ok = exists(rp)
    if ok:
        t = rd(rp)
        lines = [l for l in t.splitlines() if l.strip()]
        head = "# producer: ox-alpha LOOP-01" in t
        claim_ok = lines[-1].strip() == CLAIM
        covers = ("4c" in t and "5b" in t)
        tagged = t.count("FACT[") >= 10
        ok = head and claim_ok and covers and tagged and len(t) > 2000
        det.append("report: producer_header={} final_line_is_claim={} covers_4c_5b={} tagged={} len={}"
                   .format(head, claim_ok, covers, tagged, len(t)))
    else:
        det.append("report missing")
    return ok, det


GOALS = [("G0", g0), ("G1", g1), ("G2", g2), ("G3", g3),
         ("G4", g4), ("G5", g5), ("G6", g6), ("G7", g7)]


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "adhoc"
    results = []
    for name, fn in GOALS:
        try:
            ok, det = fn()
        except Exception as ex:
            ok, det = False, ["goalcheck error: {}: {}".format(type(ex).__name__, ex)]
        results.append((name, ok, det))
    all_true = all(r[1] for r in results)
    utc = datetime.now(timezone.utc).isoformat()
    out = os.path.join(L5, "goalcheck-{}.txt".format(tag))
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("# utc: {}\n".format(utc))
        f.write("# producer: ox-alpha LOOP-01\n")
        f.write("# oracle: evidence/loop5/tools/goalcheck.py read-only evaluation\n")
        f.write("ALL_TRUE: {}\n".format(all_true))
        for name, okv, det in results:
            f.write("\n{}: {}\n".format(name, "TRUE" if okv else "FALSE"))
            for d in det:
                f.write("  - {}\n".format(d))
    print("ALL_TRUE={}".format(all_true))
    failing = [r[0] for r in results if not r[1]]
    print("FIRST_FAILING={}".format(failing[0] if failing else "none"))
    print("REPORT={}".format(out))


if __name__ == "__main__":
    main()
