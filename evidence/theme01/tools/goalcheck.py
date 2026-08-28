#!/usr/bin/env python3
"""THEME-01 loop oracle. Read-only against the workspace; writes only its own
goalcheck-<i>.txt report. stdlib only. Run: py -3.12 -B goalcheck.py <i>"""
import hashlib, json, os, re, socket, struct, sys, time, zlib

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
T = os.path.join(WS, "evidence", "theme01")
LEDGER_PIN = "518ac84ce6a2b55b0c2d2f0bdcbd4dcd64886669012e1354432c28df6ef28085"
CSS_BEFORE = "329a52a175da7ccb37909b5fbfa009dd2f444a9f4d2a1b748ee86c2080ecb8ab"
DECISIONS_SHA = "bb911905c68b85f2c8abd5d3d2db8176cbd7a6999f8ed93fd815b4185c14869a"
KICKOFF = "OPERATOR INSTRUCTION: THEME-01 authorized per docs/OX-ALPHA-DIRECTIVE-THEME-01.md."
CLAIM = ("BUILDER CLAIM: Gate 7a and Gate 7b are CANDIDATEs for reviewer evaluation. "
         "No PASS status is asserted by the builder.")
DARK = {"--bg": "#0b0e14", "--panel": "#151b28", "--sidebar": "#0d121c", "--input": "#1b2333",
        "--border": "#232b3a", "--text": "#c7d1de", "--text-muted": "#9aa7bd",
        "--text-faint": "#3a4353", "--accent": "#7fc8e8", "--accent-dim": "#2a4a5c",
        "--ok": "#9ece6a", "--warning": "#e0af68", "--danger": "#f7768e"}
LIGHT = {"--bg": "#f4f5f7", "--panel": "#ffffff", "--sidebar": "#eceef1", "--border": "#d3d8e0",
         "--text": "#1b2027", "--text-muted": "#58616e", "--text-faint": "#8a93a1",
         "--accent": "#1f6f94", "--accent-dim": "#a8d6ea", "--ok": "#2f7a49",
         "--warning": "#8a6008", "--danger": "#c8394f"}
DARK_KEEP = {"--radius": "6px", "--font": "ui-monospace, monospace"}
# pinned §3 measurements: (label, theme, fg, bg) -> expected ratio
PINNED = [
    ("dark text/bg", "#c7d1de", "#0b0e14", 12.51), ("dark text/panel", "#c7d1de", "#151b28", 11.16),
    ("dark muted/panel", "#9aa7bd", "#151b28", 7.08), ("dark accent/bg", "#7fc8e8", "#0b0e14", 10.42),
    ("dark accent/panel", "#7fc8e8", "#151b28", 9.29), ("dark text-on-accent-dim", "#c7d1de", "#2a4a5c", 6.09),
    ("dark ok/panel", "#9ece6a", "#151b28", 9.42), ("dark warning/panel", "#e0af68", "#151b28", 8.61),
    ("dark danger/panel", "#f7768e", "#151b28", 6.51),
    ("light text/panel", "#1b2027", "#ffffff", 16.37), ("light muted/panel", "#58616e", "#ffffff", 6.27),
    ("light faint/panel", "#8a93a1", "#ffffff", 3.10), ("light accent/panel", "#1f6f94", "#ffffff", 5.59),
    ("light accent/bg", "#1f6f94", "#f4f5f7", 5.12), ("light white-on-accent", "#ffffff", "#1f6f94", 5.59),
    ("light text-on-accent-dim", "#1b2027", "#a8d6ea", 10.50), ("light ok/panel", "#2f7a49", "#ffffff", 5.25),
    ("light ok/bg", "#2f7a49", "#f4f5f7", 4.81), ("light warning/panel", "#8a6008", "#ffffff", 5.59),
    ("light warning/bg", "#8a6008", "#f4f5f7", 5.12), ("light danger/panel", "#c8394f", "#ffffff", 5.06),
    ("light danger/bg", "#c8394f", "#f4f5f7", 4.63),
]

def p(*parts):
    return os.path.join(WS, *parts)

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest()

def rd(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

def lum(hx):
    r, g, b = (int(hx[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = lin(r), lin(g), lin(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def ratio(fg, bg):
    a, b = lum(fg), lum(bg)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)

def tokens(block):
    raw = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block))
    out = {}
    for k, v in raw.items():
        v = v.strip()
        m = re.fullmatch(r"#([0-9a-fA-F]{6})", v)
        out[k] = ("#" + m.group(1).lower()) if m else v
    return out

def css_parts():
    css = rd(p("shell", "static", "app.css"))
    root = re.search(r"(?ms)^:root\s*\{(.*?)^\}", css)
    media = re.search(r"@media\s*\(prefers-color-scheme:\s*light\)\s*\{(.*?)\n\}", css, re.S)
    return css, (root.group(1) if root else None), (media.group(1) if media else None)

def png_info(path):
    """Decode PNG (8-bit, interlace 0). Returns (w, h, sampled[(r,g,b)...])."""
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, idat, plte, meta = 8, bytearray(), None, None
    while pos + 8 <= len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            meta = struct.unpack(">IIBBBBB", chunk)
        elif typ == b"PLTE":
            plte = chunk
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
        pos += 12 + ln
    w, hgt, depth, ct, _c, _f, inter = meta
    if depth != 8 or inter != 0 or ct not in (0, 2, 3, 4, 6):
        return None
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    raw = zlib.decompress(bytes(idat))
    stride = w * ch
    out = bytearray(hgt * stride)
    prev = bytearray(stride)
    q = 0
    for y in range(hgt):
        ftype = raw[q]; q += 1
        line = bytearray(raw[q:q + stride]); q += stride
        if ftype == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 255
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ftype == 3:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif ftype == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b2 = prev[i]; c = prev[i - ch] if i >= ch else 0
                pp = a + b2 - c
                pa, pb, pc = abs(pp - a), abs(pp - b2), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b2 if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    samples = []
    total = w * hgt
    k = max(1, total // 30000)
    buf = bytes(out)
    for idx in range(0, total, k):
        o = idx * ch
        if ct == 2:
            px = (buf[o], buf[o + 1], buf[o + 2])
        elif ct == 6:
            px = (buf[o], buf[o + 1], buf[o + 2])
        elif ct == 0:
            px = (buf[o],) * 3
        elif ct == 4:
            px = (buf[o],) * 3
        else:
            i3 = buf[o] * 3
            px = (plte[i3], plte[i3 + 1], plte[i3 + 2]) if plte else (0, 0, 0)
        samples.append(px)
    return w, hgt, samples

def med_lum(samples):
    ls = sorted(0.2126 * (r / 255) ** 2.2 + 0.7152 * (g / 255) ** 2.2 + 0.0722 * (b / 255) ** 2.2
                for r, g, b in samples)
    return ls[len(ls) // 2]

def has_color(samples, target, tol=48):
    tr, tg, tb = target
    for r, g, b in samples:
        if abs(r - tr) <= tol and abs(g - tg) <= tol and abs(b - tb) <= tol:
            return True
    return False

def port_state(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.6)
    try:
        s.connect(("127.0.0.1", port))
        return "in use"
    except OSError:
        return "free"
    finally:
        s.close()

def ledger_identity(res):
    """Every-iteration protected-ledger assertion vs snap-g0."""
    snap_b = open(p("evidence", "theme01", "ledger-snap-g0.json"), "rb").read()
    cur_b = open(p("evidence", "GATE-LEDGER.json"), "rb").read()
    try:
        snap = json.loads(snap_b.decode("utf-8"))
        cur = json.loads(cur_b.decode("utf-8"))
    except ValueError as e:
        res.append("PROTECTED_LEDGER_CHANGED: ledger does not parse ({})".format(e))
        return
    prot = [k for k in snap["gates"] if k not in ("7a", "7b")]
    for k in prot:
        if json.dumps(snap["gates"][k], sort_keys=True) != json.dumps(cur["gates"].get(k), sort_keys=True):
            res.append("PROTECTED_LEDGER_CHANGED: gate key {!r} differs from G0 snapshot".format(k))
    for k in ("directive", "version", "manifest_tool_sha256"):
        if snap.get(k) != cur.get(k):
            res.append("PROTECTED_LEDGER_CHANGED: top-level {!r} differs".format(k))

def main():
    it = sys.argv[1] if len(sys.argv) > 1 else "x"
    lines = []
    res = []          # human-readable failure notes
    stop = []         # STOP-condition markers
    def check(goal, ok, note=""):
        lines.append("GOAL {}: {}".format(goal, "TRUE" if ok else "FALSE"))
        if note:
            lines.append("   " + note)
        if not ok:
            res.append("{} FALSE: {}".format(goal, note or "predicate unmet"))
        return ok

    # ---- shared reads -----------------------------------------------------
    live_ledger_sha = sha(p("evidence", "GATE-LEDGER.json"))
    ss_path = p("evidence", "theme01", "session-start.txt")
    ss = rd(ss_path) if os.path.isfile(ss_path) else ""
    log = rd(p("evidence", "OPERATOR-INSTRUCTIONS.log")) if os.path.isfile(p("evidence", "OPERATOR-INSTRUCTIONS.log")) else ""
    css, root_body, light_body = css_parts()
    root_tok = tokens(root_body) if root_body else {}
    inner_light = ""
    light_extra = ""
    if light_body:
        m = re.search(r":root\s*\{(.*?)\}", light_body, re.S)
        inner_light = m.group(1) if m else ""
        light_extra = light_body[:m.start()] + light_body[m.end():] if m else light_body
        light_extra = re.sub(r"/\*.*?\*/", "", light_extra, flags=re.S).strip()
    light_tok = tokens(inner_light) if inner_light else {}
    v3_path = p("docs", "THEME-BASELINE-v3.md")
    v3 = rd(v3_path) if os.path.isfile(v3_path) else ""

    # ---- G0 ---------------------------------------------------------------
    g0 = True
    g0 &= KICKOFF in log
    g0 &= DECISIONS_SHA in ss and LEDGER_PIN in ss

    def append_only_from(snap_file):
        """True when the live ledger is the snapshot with entries appended only."""
        try:
            s0 = open(snap_file, "rb").read()
            c0 = open(p("evidence", "GATE-LEDGER.json"), "rb").read()
            anch = b"\n  }\n}"
            if s0.count(anch) != 1:
                return False
            pre = s0[:s0.index(anch)]
            if not c0.startswith(pre):
                return False
            sj = json.loads(s0.decode("utf-8"))
            cj = json.loads(c0.decode("utf-8"))
            for k, v in sj["gates"].items():
                if json.dumps(v, sort_keys=True) != json.dumps(cj["gates"].get(k), sort_keys=True):
                    return False
            return True
        except (ValueError, OSError):
            return False

    # session-start pinned hash, or the same bytes grown only by appended entries
    g0 &= live_ledger_sha == LEDGER_PIN or append_only_from(p("evidence", "theme01", "ledger-snap-g0.json"))
    g0 &= "ports at session start" in ss
    g0 &= os.path.isfile(p("evidence", "theme01", "tools", "goalcheck.py"))
    check("G0", bool(g0), "ledger sha live={} pin={}".format(live_ledger_sha[:12], LEDGER_PIN[:12]))

    # ---- G1 ---------------------------------------------------------------
    snap_css = p("evidence", "theme01", "before", "app.css.snapshot")
    base = rd(p("evidence", "theme01", "baseline.txt")) if os.path.isfile(p("evidence", "theme01", "baseline.txt")) else ""
    g1 = True
    g1 &= os.path.isfile(snap_css) and sha(snap_css) == CSS_BEFORE
    g1 &= "BUILD-MANIFEST" in base and "40/40" in base
    g1 &= "suite-count-before" in base
    for d in ("D1", "D2", "D3", "D4"):
        g1 &= re.search(r"^{} verdict: (CONFIRMED|NOT_REPRODUCED)".format(d), base, re.M) is not None
    for shot in ("grid-dark.png", "grid-light.png"):
        sp = p("evidence", "theme01", "before", shot)
        ok = False
        if os.path.isfile(sp):
            info = png_info(sp)
            ok = info is not None and info[0] > 100 and len(set(info[2])) > 20
        g1 &= ok
    check("G1", bool(g1), "pre-change baseline pinned under evidence/theme01/before/")

    # ---- G2 ---------------------------------------------------------------
    g2 = bool(v3)
    g2 &= v3.startswith("# utc:") and "# producer:" in v3.splitlines()[1]
    v2sha = sha(p("docs", "THEME-BASELINE-v2.md"))
    g2 &= "THEME-BASELINE-v2.md" in v3 and v2sha in v3
    for tokname, val in list(DARK.items()) + list(LIGHT.items()):
        g2 &= tokname in v3 and val.lower() in v3.lower()
    g2 &= "custom-property overrides only" in v3
    g2 &= "text-faint" in v3 and "out of scope" in v3
    check("G2", bool(g2), "v2 superseded-by hash={}".format(v2sha[:12]))

    # ---- G3 ---------------------------------------------------------------
    g3 = all(root_tok.get(k) == v for k, v in DARK.items())
    g3 &= root_tok.get("--radius") == "6px"
    g3 &= "--font" in root_tok and "ui-monospace" in root_tok.get("--font", "")
    check("G3", bool(g3), ":root vs §3.1 mismatches={}".format(
        {k: (root_tok.get(k), v) for k, v in DARK.items() if root_tok.get(k) != v} or "none"))

    # ---- G4 ---------------------------------------------------------------
    g4 = bool(light_body)
    g4 &= all(light_tok.get(k) == v for k, v in LIGHT.items())
    extras = [ln for ln in light_extra.splitlines() if ln.strip()]
    justified = "justified-rules:" in v3
    g4 &= (not extras) or justified
    if extras and justified:
        for ln in extras:
            sel = ln.split("{")[0].strip()
            g4 &= sel in v3
    check("G4", bool(g4), "light block extra rules={!r} tokens-missing={}".format(
        extras[:3], [k for k, v in LIGHT.items() if light_tok.get(k) != v] or "none"))

    # ---- pinned ratio recomputation (STOP on disagreement) -----------------
    bad = [(lab, round(ratio(a, b), 2), exp) for lab, a, b, exp in PINNED
           if abs(round(ratio(a, b), 2) - exp) > 0.02]
    if bad:
        stop.append("CONTRAST_UNREACHABLE: pinned §3 values disagree: {}".format(bad))
    lines.append("PINNED-RATIOS: {} checked, {} disagree".format(len(PINNED), len(bad)))

    # ---- G5 ---------------------------------------------------------------
    h16p = p("evidence", "hardening", "h16-contrast.txt")
    h16 = rd(h16p) if os.path.isfile(h16p) else ""
    g5 = "# producer: ox-alpha THEME01" in h16
    g5 &= h16.count("TEXT  OK") >= 12 and h16.count("TEXT  FAIL") == 0
    g5 &= re.search(r"GLYPH\s*\(", h16) is None
    g5 &= "text-faint" in h16 and "accent-dim" in h16 and "RECORDED" in h16
    g5 &= os.path.isfile(p("evidence", "theme01", "h16-fails-before.txt"))
    src = rd(p("shell", "tests", "test_render.py"))
    g5 &= "asserted_all_text_pairs" in src or "status_pairs" in src or 'always' in src
    check("G5", bool(g5), "h16 rows TEXT OK={} FAIL={}".format(h16.count("TEXT  OK"), h16.count("TEXT  FAIL")))

    # ---- G6 ---------------------------------------------------------------
    srv = rd(p("shell", "src", "server.py"))
    h14p = p("evidence", "hardening", "h14-doclinks.txt")
    h14 = rd(h14p) if os.path.isfile(h14p) else ""
    g6 = '"theme-baseline": os.path.join("docs", "THEME-BASELINE-v3.md")' in srv
    g6 &= "/doc/theme-baseline" in h14 and "200" in h14 and "v3" in h14.lower()
    check("G6", bool(g6), "/doc/theme-baseline maps to v3 and H-14 artifact regenerated")

    # ---- G7 ---------------------------------------------------------------
    pf_before = os.path.isfile(p("evidence", "theme01", "g7-preflight-fails-before.txt"))
    ids = ["ollama", "py312", "node", "npm", "port_5175", "port_8700", "port_5180"]
    tsrc = src + rd(p("shell", "tests", "test_shell.py"))
    newtest = "/api/preflight" in tsrc and all(i in tsrc for i in ids) and "unknown" in tsrc
    after_json = p("evidence", "theme01", "after", "preflight-live.json")
    g7 = pf_before and newtest and os.path.isfile(after_json)
    summary_note = ""
    if os.path.isfile(after_json):
        payload = json.loads(rd(after_json))
        checks = {c.get("id"): c for c in payload.get("checks", [])}
        definite = [i for i in ids if checks.get(i, {}).get("status") in ("ok", "bad")
                    and str(checks.get(i, {}).get("detail", "")).strip()]
        g7 &= len(definite) == 7
        dom = p("evidence", "theme01", "after", "preflight-dom.txt")
        dtxt = rd(dom) if os.path.isfile(dom) else ""
        m = re.search(r"(\d)/7 available", dtxt)
        if m:
            n = int(m.group(1))
            if n < 7:
                g7 &= bool(re.search(r"named-absent:\s*\S+", dtxt, re.M))
            summary_note = "{} available".format(m.group(0))
    check("G7", bool(g7), "end-to-end preflight contract; live capture " + (summary_note or "(pending)"))

    # ---- G8 ---------------------------------------------------------------
    tr_path = p("evidence", "test-run.txt")
    tr = rd(tr_path) if os.path.isfile(tr_path) else ""
    mcount = re.search(r"Ran (\d+) tests", tr)
    mbefore = re.search(r"suite-count-before:\s*(\d+)", base)
    manifest_ok = False
    bm = p("shell", "BUILD-MANIFEST.txt")
    if os.path.isfile(bm):
        tot = okn = 0
        for line in rd(bm).splitlines():
            if not line or line.startswith("#"):
                continue
            tot += 1
            hh, _, rel = line.partition("  ")
            fp = p("shell", rel.strip())
            if os.path.isfile(fp) and sha(fp) == hh.strip().lower():
                okn += 1
        manifest_ok = tot > 0 and okn == tot
    fresh = os.path.isfile(tr_path) and os.path.getmtime(tr_path) > max(
        os.path.getmtime(p("shell", "static", "app.css")),
        os.path.getmtime(p("shell", "src", "probe.py")))
    g8 = tr.rstrip().endswith("OK") and mcount and mbefore and int(mcount.group(1)) >= int(mbefore.group(1)) and manifest_ok and fresh
    check("G8", bool(g8), "suite Ran {} vs before {}; manifest_ok={} fresh={}".format(
        mcount.group(1) if mcount else "?", mbefore.group(1) if mbefore else "?", manifest_ok, fresh))

    # ---- G9 ---------------------------------------------------------------
    cmds = rd(p("evidence", "theme01", "after", "edge-commands.txt")) if os.path.isfile(p("evidence", "theme01", "after", "edge-commands.txt")) else ""
    g9 = bool(cmds.strip())
    det = []
    for shot, target, lo, hi in (("grid-dark.png", (0x7f, 0xc8, 0xe8), 0.0, 0.06),
                                 ("grid-light.png", (0x1f, 0x6f, 0x94), 0.75, 1.0)):
        sp = p("evidence", "theme01", "after", shot)
        ok = False
        if os.path.isfile(sp):
            info = png_info(sp)
            if info:
                ml = med_lum(info[2])
                ok = info[0] > 100 and lo <= ml <= hi and has_color(info[2], target)
                det.append("{} median-lum={:.3f} accent={}".format(shot, ml, has_color(info[2], target)))
        g9 &= ok
    check("G9", bool(g9), "; ".join(det))

    # ---- G10 --------------------------------------------------------------
    snap_b = open(p("evidence", "theme01", "ledger-snap-g0.json"), "rb").read()
    cur_b = open(p("evidence", "GATE-LEDGER.json"), "rb").read()
    anchor = b"\n  }\n}"
    g10 = live_ledger_sha != LEDGER_PIN  # the file must actually have been rewritten
    try:
        cur = json.loads(cur_b.decode("utf-8"))
        for k in ("7a", "7b"):
            g10 &= k in cur["gates"] and cur["gates"][k].get("status") == "CANDIDATE"
            for ev in cur["gates"].get(k, {}).get("evidence", []):
                g10 &= re.fullmatch(r"[0-9a-f]{64}", str(ev.get("sha256", ""))) is not None
        if snap_b.count(anchor) == 1:
            prefix = snap_b[:snap_b.index(anchor)]
            g10 &= cur_b.startswith(prefix)
        else:
            g10 &= False
            res.append("G10: snapshot anchor ambiguous")
    except ValueError:
        g10 = False
    check("G10", bool(g10), "ledger 7a/7b CANDIDATE appended; prefix byte-identical")

    # ---- G11 --------------------------------------------------------------
    rep = rd(p("docs", "REM-04-REPORT.md")) if os.path.isfile(p("docs", "REM-04-REPORT.md")) else ""
    orph = rd(p("evidence", "theme01", "orphans-after.txt")) if os.path.isfile(p("evidence", "theme01", "orphans-after.txt")) else ""
    st5175, st5180, st8700 = port_state(5175), port_state(5180), port_state(8700)
    g11 = bool(rep) and CLAIM in rep
    g11 &= st5175 == "free" and st5180 == "free"
    g11 &= "no workspace module processes" in orph
    check("G11", bool(g11), "report+claim present; 5175={} 5180={} 8700={} (8700 informational: operator-side)".format(st5175, st5180, st8700))

    ledger_identity(res)

    all_true = not res and not stop
    first_fail = next((ln.split()[1] for ln in lines if ln.startswith("GOAL ") and ln.endswith("FALSE")), "none")
    out = ["# utc: " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "# producer: ox-alpha THEME01 goalcheck i={}".format(it)] + lines + \
          ["ALL_GOALS_TRUE: {}".format("yes" if all_true else "no"),
           "FIRST_FAILING: {}".format(first_fail),
           "STOP_MARKERS: {}".format(stop if stop else "none")]
    report = "\n".join(out) + "\n"
    with open(os.path.join(T, "goalcheck-{}.txt".format(it)), "w", encoding="utf-8", newline="\n") as f:
        f.write(report)
    print(report)
    print("RESULT: {}".format("ALL_TRUE" if all_true else ("STOP:" + ";".join(stop) if stop else "FAILING:" + first_fail)))

if __name__ == "__main__":
    main()