#!/usr/bin/env python3
# CP-M1 oracle, part 1 of 4: framework (contract s7).
import hashlib, json, re, socket, sys, zlib
from datetime import datetime, timezone
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
M1 = WS / "evidence" / "cpm1"
AUTH_A3 = ("OPERATOR AUTHORIZATION: SWS-UI-001 ADDENDUM-03 v1.1 is issued as written; "
           "CP-01 and CP-02 are merged into one loop under docs/OX-ALPHA-DIRECTIVE-CP-M1.md, goals G1-G124; "
           "amendments A-1 through A-5 bind; gates 8a-8j and 9a-9j are authorized; the CP-01 Band 0 "
           "protected-root evidence is adopted; stage pauses waived; no provider spend authorized; "
           "llama.cpp is not promoted to production default.")
AUTH_G2 = "CP-M1 G2 resolution"
V3 = {"bg":"#0b0e14","panel":"#151b28","sidebar":"#0d121c","input":"#1b2333",
      "border":"#232b3a","text":"#c7d1de","text-muted":"#9aa7bd","text-faint":"#3a4353",
      "accent":"#7fc8e8","accent-dim":"#2a4a5c","ok":"#9ece6a","warning":"#e0af68","danger":"#f7768e"}
V3L = {"bg":"#f4f5f7","panel":"#ffffff","sidebar":"#eceef1","border":"#d3d8e0",
       "text":"#1b2027","text-muted":"#58616e","text-faint":"#8a93a1","accent":"#1f6f94",
       "accent-dim":"#a8d6ea","ok":"#2f7a49","warning":"#8a6008","danger":"#c8394f"}
STEMS = ["PROCESS_START_FAILED","PORT_UNAVAILABLE","HEALTH_CHECK_FAILED","IDENTITY_MISMATCH",
         "MODEL_UNAVAILABLE","PROVIDER_UNAVAILABLE","OPENCODE_UNAVAILABLE",
         "CONFIGURATION_FAILED","WORKER_FAILED","CONDUCTOR_COMMUNICATION_FAILED"]
CAPS_A = {"shell/src":320,"shell/static":300,"shell/modules":140,
          "sow-desktop":700,"sow-control-plane":400,"distillery":500,"tokencenter":60}
ABS_A = 1850
CAPS_B = {"sow-adapters":450,"sow-scheduler":200,"sow-control+schemas":500,
          "sow-tools+config":150,"shell":220,"llamacpp.json":45,"runtime":60}
ABS_B = 1625
REG39 = ["model_id","family","parameter_count","active_parameter_count","provider","runtime",
         "locality","capabilities","advertised_context","validated_context","production_context",
         "validation_evidence","artifacts","speculative_decoding","promotion_state",
         "discovered_by","availability","health"]

RES = []
READS = set()
CUR = [None]

def rec(g, ok, why):
    RES.append((g, bool(ok), why, sorted(READS)))
    READS.clear()

def note(p):
    if CUR[0] is not None:
        try: READS.add(str(Path(p).relative_to(WS)))
        except ValueError: READS.add(str(p))

def sha(p):
    p = Path(p); note(p)
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()

def rd(p):
    p = Path(p); note(p)
    with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()

def art(*p):
    return M1.joinpath(*p)

def piso(s):
    s = s.strip()
    if s.endswith("Z"): s = s[:-1] + "+00:00"
    try: return datetime.fromisoformat(s)
    except ValueError:
        try: return datetime.fromisoformat(s.split(".")[0] + "+00:00")
        except ValueError: return None

def ledger():
    return json.loads(rd(WS / "evidence" / "GATE-LEDGER.json"))

def gate_cand(key):
    try:
        led = ledger()
    except Exception as e:
        return False, "ledger unreadable: %s" % e
    g = led.get("gates", {}).get(key)
    if not isinstance(g, dict): return False, 'ledger key "%s" absent' % key
    if g.get("status") != "CANDIDATE": return False, "status=%s want CANDIDATE" % g.get("status")
    if g.get("claimed_by") != "builder": return False, "claimed_by != builder"
    if g.get("evaluated_by") is not None: return False, "already evaluated"
    ev = g.get("evidence") or []
    if not ev: return False, "evidence list empty"
    for e in ev:
        p = WS / e["path"]
        if not p.is_file():
            note(p); return False, "missing %s" % e["path"]
        if sha(p) != str(e.get("sha256", "")).lower(): return False, "hash mismatch %s" % e["path"]
    return True, "CANDIDATE, %d evidence entries verified" % len(ev)

def suite_ok(path, minc):
    p = WS / path
    if not p.is_file(): return False, "%s absent" % path
    t = rd(p)
    m = re.search(r"Ran (\d+) tests? in", t)
    tail = [l for l in t.strip().splitlines() if l.strip()]
    last = tail[-1].strip() if tail else ""
    if not m: return False, "no Ran-N-tests line"
    n = int(m.group(1))
    if n < minc: return False, "Ran %d < %d" % (n, minc)
    if last != "OK": return False, "last line not OK"
    return True, "Ran %d OK" % n

def bm_equal():
    p = WS / "shell" / "BUILD-MANIFEST.txt"
    if not p.is_file(): return False, "BUILD-MANIFEST.txt absent"
    bad = []; n = 0
    for line in rd(p).splitlines():
        line = line.rstrip("\r")
        if not line or line.startswith("#"): continue
        parts = line.split(None, 1)
        if len(parts) != 2: continue
        h, rel = parts[0], parts[1].strip()
        f = WS / "shell" / rel; n += 1
        if not f.is_file():
            note(f); bad.append(rel + " missing")
        elif sha(f) != h.lower(): bad.append(rel + " hash")
    if n == 0: return False, "no entries parsed"
    if bad: return False, "%d mismatched: %s" % (len(bad), "; ".join(bad[:4]))
    return True, "%d entries equal live hashes" % n

def css_blocks():
    css = rd(WS / "shell" / "static" / "app.css")
    lines = css.splitlines()
    start = next((i for i, l in enumerate(lines) if "prefers-color-scheme" in l), None)
    light = ""
    if start is not None:
        depth = 0; buf = []; opened = False
        for i in range(start, len(lines)):
            ln = lines[i]
            depth += ln.count("{")
            if depth > 0:
                opened = True
                if "@media" not in ln: buf.append(ln)
            depth -= ln.count("}")
            if opened and depth <= 0: break
        light = "\n".join(buf)
    m = re.search(r":root\s*\{(.*?)\}", css, re.S)
    dark = dict(re.findall(r"--([a-z-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;", m.group(1))) if m else {}
    ld = dict(re.findall(r"--([a-z-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;", light))
    return dark, ld

def grep_tree(relroots, needle, exclude=()):
    hits = []; rx = re.compile(re.escape(needle))
    ex = tuple(e.lower() for e in exclude)
    for rr in relroots:
        root = WS / rr
        if not root.is_dir(): continue
        for p in root.rglob("*"):
            if not p.is_file(): continue
            sp = str(p).lower()
            if any(x in sp for x in ex): continue
            if p.suffix.lower() not in (".py", ".js", ".json", ".html", ".css"): continue
            try:
                if rx.search(rd(p)): hits.append(str(p.relative_to(WS)))
            except OSError:
                pass
    return hits

def png_ok(p, minb=8000):
    p = Path(p); note(p)
    if not p.is_file(): return False, "absent"
    raw = p.read_bytes()
    if len(raw) < minb: return False, "only %d bytes" % len(raw)
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"): return False, "not PNG"
    if b"IEND" not in raw[-16:]: return False, "truncated"
    idat = bytearray(); i = 8
    while i + 8 <= len(raw):
        ln = int.from_bytes(raw[i:i+4], "big"); typ = raw[i+4:i+8]
        if typ == b"IDAT": idat += raw[i+8:i+8+ln]
        if typ == b"IEND": break
        i += 12 + ln
    if not idat or len(idat) > 60000000: return False, "no/too-large IDAT"
    try:
        out = zlib.decompress(bytes(idat))
    except zlib.error as e:
        return False, "zlib %s" % e
    if len(set(out[:200000])) < 8: return False, "near-uniform (blank?)"
    return True, "%d bytes decodes non-blank" % len(raw)

def hashes_verify(base, hashfile):
    hp = Path(hashfile); note(hp)
    if not hp.is_file(): return False, "%s absent" % hashfile, 0
    head = rd(hp).lower()
    excl_stated = ("node_modules" in head)
    bad = []; n = 0
    for l in rd(hp).splitlines():
        l = l.rstrip("\r")
        if not l.strip() or l.startswith("#"): continue
        parts = l.split(None, 1)
        if len(parts) != 2: continue
        h, rel = parts[0], parts[1].strip()
        f = base / rel; n += 1
        if not f.is_file():
            note(f); bad.append(rel + " missing")
        elif sha(f) != h.lower(): bad.append(rel + " hash")
    if n == 0: return False, "no entries", 0
    if bad: return False, "%d problems: %s" % (len(bad), "; ".join(bad[:4])), n
    msg = "%d files verified" % n
    if excl_stated: msg += "; node_modules exclusion stated"
    return True, msg, n

def tproof(band, name):
    fb = art(band, name + "-fails-before.txt")
    pa = art(band, name + "-passes-after.txt")
    if not fb.is_file():
        note(fb); return False, "%s/%s-fails-before.txt absent" % (band, name)
    if not pa.is_file():
        note(pa); return False, "%s/%s-passes-after.txt absent" % (band, name)
    ta = [l for l in rd(pa).strip().splitlines() if l.strip()]
    if not ta or ta[-1].strip() != "OK": return False, "%s passes-after not OK" % name
    return True, "fails-before + passes-after OK"

def popen(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(0.4)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()

def linecount_within(path, caps, abscap):
    p = M1 / path
    if not p.is_file(): return False, "%s absent" % path
    tot = None
    for line in rd(p).splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        parts = [x.strip() for x in re.split(r"[|\t]", line) if x.strip()]
        if len(parts) < 3: continue
        area, u, c = parts[0], parts[1], parts[2]
        try:
            ui, ci = int(u), int(c)
        except ValueError:
            return False, "bad row %s" % line[:40]
        if area.upper().startswith("TOTAL"):
            tot = ui; continue
        cap = caps.get(area)
        if cap is None: continue
        if ui > cap: return False, "%s over cap %d>%d" % (area, ui, cap)
    if tot is None: return False, "no TOTAL row"
    if tot > abscap: return False, "total %d>%d" % (tot, abscap)
    return True, "within caps, total %d/%d" % (tot, abscap)
# ---------------- Band 0 ----------------
def g1():
    pr = []
    lp = WS / "evidence" / "OPERATOR-INSTRUCTIONS.log"
    if not lp.is_file(): return rec("G1", False, "operator log absent")
    logt = rd(lp)
    if AUTH_A3 not in logt: pr.append("ADDENDUM-03 s7 sentence not verbatim in op-log")
    p = art("session-start.txt")
    if not p.is_file():
        note(p); return rec("G1", False, "cpm1/session-start.txt absent")
    t = rd(p)
    if "# utc:" not in t: pr.append("no utc header")
    if "PowerShell" not in t: pr.append("shell not recorded")
    for rel in ("docs/DECISIONS.md", "AGENTS.md", "CLAUDE.md",
                "docs/SWS-UI-001-v1.2-ADDENDUM-01.md", "docs/SWS-UI-001-v1.2-ADDENDUM-02.md",
                "docs/SWS-UI-001-v1.2-ADDENDUM-03.md", "docs/OX-ALPHA-DIRECTIVE-CP-M1.md"):
        live = sha(WS / rel)
        if live not in t: pr.append("%s live hash not recorded in session-start" % rel)
    ha = re.search(r"\b([0-9a-f]{64})\s+AGENTS\.md", t)
    hc = re.search(r"\b([0-9a-f]{64})\s+CLAUDE\.md", t)
    if ha and hc and ha.group(1) != hc.group(1): pr.append("AGENTS != CLAUDE")
    rec("G1", not pr, "authorization verbatim + session-start verified" if not pr else "; ".join(pr))

def g2():
    pr = []
    p = art("spend-reconciliation.txt")
    if not p.is_file():
        note(p); return rec("G2", False, "spend-reconciliation.txt absent")
    t = rd(p)
    cfg = WS / "modules" / "sow" / "config" / "live_operation.json"
    try:
        j = json.loads(rd(cfg))
    except Exception as e:
        return rec("G2", False, "live_operation.json unparsable %s" % e)
    provs = list((j.get("scope") or {}).get("providers") or [])
    # G-oracle repair 2026-08-26: want-set re-pointed to the operator-amended envelope -
    # ADDENDUM-04 s6 amendment (claude_code added; docs/CP-M1-G26-CONFIG-AUTHORIZATION.md
    # sha256 0c7d177b224135b199879367c24465a87d1e1a9095e79c6a3b3c9d717bf90177) and
    # ADDENDUM-05 v1.1 s5/D5-11 (grok_build added; live_operation.json sha256
    # 09377c9da28d714c27d8d38f45726389402c077fffc6caef82beb9251188e998) with the
    # 25-turn total / <=10 openai_codex_cli caps.
    if provs != ["openai_codex_cli", "claude_code", "grok_build"]: pr.append("config providers=%s want [openai_codex_cli, claude_code, grok_build] per ADD-04 s6 + ADD-05 s5" % provs)
    if j.get("live_operation_authorized") is not True: pr.append("authorized flag changed unexpectedly")
    if '"openai_codex_cli"' not in t or "SUPERSEDE" not in t.upper(): pr.append("reconciliation lacks narrowed record/supersede")
    if not re.search(r"[0-9a-f]{64}", t): pr.append("no file hashes recorded")
    if "_validate_providers" not in t: pr.append("enforcement note missing (_validate_providers)")
    if AUTH_G2 not in rd(WS / "evidence" / "OPERATOR-INSTRUCTIONS.log"): pr.append("operator resolution not logged")
    rec("G2", not pr, "contradiction reconciled by narrowing; enforcement cited" if not pr else "; ".join(pr))

def g3():
    need = ["git-head.txt", "git-status.txt", "host-hardware.json", "runtime-inventory.json",
            "ollama-version.txt", "ollama-model-list.json", "schema-hashes.json", "ports.txt", "processes.txt"]
    pr = []
    for nm in need:
        f = art("baseline", nm)
        if not f.is_file():
            note(f); pr.append(nm + " absent")
    if pr: return rec("G3", False, "; ".join(pr))
    hw = json.loads(rd(art("baseline", "host-hardware.json")))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today not in str(hw.get("captured_utc", "")): pr.append("host-hardware not a fresh capture today")
    if "5060" not in str(hw.get("gpu_name", "")): pr.append("unexpected gpu %s" % hw.get("gpu_name"))
    ri = json.loads(rd(art("baseline", "runtime-inventory.json")))
    if not ri.get("git"): pr.append("runtime-inventory git field empty (C-2 regression)")
    pt = rd(art("baseline", "ports.txt"))
    for port in (5175, 8700, 8765, 5180, 5183):
        if str(port) not in pt: pr.append("ports.txt missing %d" % port)
    ov = rd(art("baseline", "ollama-version.txt"))
    if "REACHABLE" not in ov and "ollama version" not in ov: pr.append("ollama version/reachability unrecorded")
    ml = rd(art("baseline", "ollama-model-list.json"))
    if "models" not in ml and "name" not in ml: pr.append("ollama model list unparsable/empty")
    rec("G3", not pr, "host baseline complete and fresh" if not pr else "; ".join(pr))

def g4():
    tool = WS / "evidence" / "tools" / "manifest.py"
    th = sha(tool)
    pr = []
    try:
        want = ledger()["manifest_tool_sha256"].lower()
    except Exception as e:
        return rec("G4", False, "ledger unreadable %s" % e)
    if th != want: pr.append("tool %s != ledger %s" % (th[:10], want[:10]))
    names = ["product-software", "multi-model-terminal-app", "sovereign-distillery", "sov-1", "token-piggy-bank"]
    for nm in names:
        mf = WS / "evidence" / "cp01" / "manifests" / ("manifest-cp01-before-%s.txt" % nm)
        if not mf.is_file():
            note(mf); pr.append("before-%s absent" % nm); continue
        m = re.search(r"# tool-sha256:\s*([0-9a-f]{64})", rd(mf)[:800])
        if not m: pr.append(nm + " header lacks tool-sha256")
        elif m.group(1) != th: pr.append(nm + " tool-sha mismatch")
    ex = WS / "evidence" / "cp01" / "manifests" / "manifest-cp01-before-token-piggy-bank.excl-data.txt"
    if not ex.is_file():
        note(ex); pr.append("A-1 excl-data manifest absent")
    else:
        t = rd(ex)[:800]
        if "data/**" not in t: pr.append("excl-data manifest does not state data/** exclusion")
        sup = WS / "evidence" / "cp01" / "manifests" / "SUPERSEDE-token-piggy-bank-excl-data.txt"
        if not sup.is_file():
            note(sup); pr.append("supersede note absent")
        elif not re.search(r"[0-9a-f]{64}[\s\S]*[0-9a-f]{64}", rd(sup)): pr.append("supersede note lacks both hashes")
    h1 = art("baseline", "git-head.txt"); h2 = art("baseline", "git-head-2.txt")
    if not (h1.is_file() and h2.is_file()):
        note(h1); note(h2); pr.append("quiescence pair incomplete")
    else:
        t1, t2 = rd(h1), rd(h2)
        d1 = piso(re.search(r"# utc:\s*(\S+)", t1).group(1))
        d2 = piso(re.search(r"# utc:\s*(\S+)", t2).group(1))
        H1 = re.search(r"HEAD:\s*(\S+)", t1).group(1)
        H2 = re.search(r"HEAD:\s*(\S+)", t2).group(1)
        s1 = [l for l in rd(art("baseline", "git-status.txt")).splitlines() if l.strip() and not l.startswith("#")]
        s2 = [l for l in rd(art("baseline", "git-status-2.txt")).splitlines() if l.strip() and not l.startswith("#")]
        if H1 != H2: pr.append("HEAD moved between inspections")
        if s1 != s2: pr.append("porcelain bodies differ")
        if not (d1 and d2): pr.append("quiescence utc unparsable")
        elif abs((d2 - d1).total_seconds()) < 60: pr.append("<60s apart")
    rec("G4", not pr, "five manifests adopted on pinned tool; A-1 applied; SOW quiescent" if not pr else "; ".join(pr))

def g5():
    pr = []
    ok, why, _n = hashes_verify(WS, M1 / "before-a" / "HASHES.txt")
    if not ok: pr.append("before-a: " + why)
    tb = art("test-run-before.txt")
    if not tb.is_file():
        note(tb); pr.append("test-run-before.txt absent")
    else:
        ok, why = suite_ok(str(tb.relative_to(WS)), 122)
        if not ok: pr.append("before-suite: " + why)
    ok, why = bm_equal()
    if not ok: pr.append("BUILD-MANIFEST " + why)
    dark, light = css_blocks()
    if not dark: pr.append(":root unparsable")
    for k, v in V3.items():
        if dark.get(k, "").lower() != v: pr.append("css --%s=%s want %s" % (k, dark.get(k), v))
    for k, v in V3L.items():
        if light.get(k, "").lower() != v: pr.append("light --%s=%s want %s" % (k, light.get(k), v))
    ad = art("fs-watch-adoption.txt")
    if not ad.is_file():
        note(ad); pr.append("fs-watch adoption artifact absent")
    else:
        t = rd(ad)
        if "2026-08-25T16:30:43Z" not in t: pr.append("adoption artifact lacks operator started_utc")
        dl = WS / "evidence" / "cpm1" / "fs-watch-driver.log"
        lt = rd(dl) if dl.is_file() else ""
        note(dl)
        for r in ("Product Software", "multi model terminal app", "Sovereign Distillery", "Sov 1"):
            if r not in lt: pr.append("driver log missing root %s" % r)
    rec("G5", not pr, "Package-A baseline verified; watch window open (operator-owned)" if not pr else "; ".join(pr))

def g6():
    me = Path(__file__).resolve(); note(me)
    pr = []
    src = rd(me)
    try:
        compile(src, str(me), "exec")
    except SyntaxError as e:
        pr.append("oracle does not compile: %s" % e)
    ids = set(int(m) for m in re.findall(r'rec\("G(\d+)"', src))
    missing = [n for n in range(1, 125) if n not in ids]
    if missing: pr.append("no predicate emitted for G%s" % ",".join(map(str, missing[:12])))
    if sys.version_info[:2] != (3, 12): pr.append("not running under 3.12")
    rec("G6", not pr, "oracle covers G1-G124, compiles, runs under 3.12" if not pr else "; ".join(pr))

def g7():
    p = art("LOOP-LEDGER.jsonl")
    if not p.is_file():
        note(p); return rec("G7", False, "LOOP-LEDGER.jsonl absent")
    lines = [l for l in rd(p).splitlines() if l.strip()]
    pr = []; needk = {"i", "utc", "goal", "action", "changed_lines", "flipped", "notes"}
    for i, l in enumerate(lines, 1):
        try:
            o = json.loads(l)
            if not needk <= set(o): pr.append("line %d missing keys" % i)
        except Exception as e:
            pr.append("line %d unparsable %s" % (i, e))
    rec("G7", not pr, ("%d iterations recorded, all well-formed" % len(lines)) if not pr else "; ".join(pr))

def g8():
    sw = art("single-writer.txt")
    if not sw.is_file():
        note(sw); return rec("G8", False, "single-writer.txt absent")
    t = rd(sw)
    ok = ("CONCURRENT_WRITER" not in t) and ("differences: 0" in t)
    s1 = art("g8-snapshot-1.txt"); s2 = art("g8-snapshot-2.txt")
    if not (s1.is_file() and s2.is_file()):
        note(s1); note(s2); ok = False
    rec("G8", ok, "single writer confirmed across two reads" if ok else "snapshot pair incomplete or differences recorded")
# ---------------- Band 1 (Gate 8a) ----------------
def g9():
    mp = WS / "docs" / "CP-MAP-01.md"
    if not mp.is_file():
        note(mp); return rec("G9", False, "docs/CP-MAP-01.md absent")
    t = rd(mp); low = t.lower()
    topics = ["launch", "browser", "pty", "conductor", "registry", "token center", "distillery", "opencode", "runtime inventory"]
    miss = [x for x in topics if x not in low]
    nf = len(re.findall(r"FACT\[[^\]]+:[^\]]*\]", t))
    ok = (not miss) and nf >= 20
    rec("G9", ok, ("topics present, %d FACT citations" % nf) if not miss else ("missing topics: %s (%d FACT citations)" % (",".join(miss), nf)))

def g10():
    mp = WS / "docs" / "CP-MAP-01.md"
    if not mp.is_file():
        note(mp); return rec("G10", False, "map absent")
    t = rd(mp)
    need = set("R-%02d" % i for i in range(1, 16))
    have = set(re.findall(r"R-\d\d", t))
    cls = sum(t.count(c) for c in ("implemented-and-verified", "implemented-but-defective", "partial", "absent"))
    nf = len(re.findall(r"FACT\[[^\]]+:[^\]]*\]", t))
    ok = need <= have and cls >= 15 and nf >= 15
    rec("G10", ok, "R-01..R-15 classified with citations" if ok else ("rows missing: %s classifications:%d" % (",".join(sorted(need - have)), cls)))

def g11():
    mp = WS / "docs" / "CP-MAP-01.md"
    if not mp.is_file():
        note(mp); return rec("G11", False, "map absent")
    t = rd(mp)
    div = bool(re.search(r"DIVERGENCE|disagrees with", t, re.I))
    pd = art("premise-divergence.txt"); sr = WS / "docs" / "STOP-REPORT-CP-M1.md"
    if not div:
        rec("G11", True, "no divergence flagged")
    else:
        note(pd); note(sr)
        rec("G11", pd.is_file() and sr.is_file(), "divergence recorded + STOP report" if pd.is_file() and sr.is_file() else "divergence flagged but artifacts missing")

def g12():
    ok, why = gate_cand("8a"); rec("G12", ok, why)

# ---------------- Band 2 (Gate 8b) ----------------
def g13():
    cold = art("8b", "cold-start.txt")
    if not cold.is_file():
        note(cold); return rec("G13", False, "8b/cold-start.txt absent")
    t = rd(cold)
    oktxt = ("/api/state" in t) and ("serve_forever" in t or "cold start" in t.lower())
    pf = tproof("8b", "test-cold-start-starts-nothing")
    ext = ("EXTERNAL" in t) or ("8700" in t)
    rec("G13", oktxt and pf[0] and ext, "cold-start recorded; external owner documented" if (oktxt and pf[0] and ext) else "artifact:%s proof:%s external-documented:%s" % (oktxt, pf[1], ext))

def g14():
    dom = art("8b", "external-dom.txt"); h9 = art("8b", "h9-noninterference.txt")
    ok = dom.is_file() and h9.is_file()
    why = "dom:%s h9:%s" % (dom.is_file(), h9.is_file())
    if ok:
        tt = rd(dom)
        t9 = rd(h9).lower()
        ok = ("EXTERNAL" in tt) and ("<" in tt) and ("alive" in t9 or "unchanged" in t9)
        why = "EXTERNAL legible; pid unchanged after Stop" if ok else "markers insufficient"
    rec("G14", ok, why)

def g15():
    sj = WS / "shell" / "modules" / "sow.json"
    if not sj.is_file():
        note(sj); return rec("G15", False, "sow.json absent")
    try:
        a = json.loads(rd(sj))
    except Exception as e:
        return rec("G15", False, "sow.json unparsable %s" % e)
    rk = (a.get("readiness") or {}).get("kind")
    srd = art("8b", "sow-readiness.txt")
    ok = rk in ("http", "receipt_file") and srd.is_file()
    if ok:
        tt = rd(srd).lower()
        ok = ("fail" in tt) and ("success" in tt or "ready" in tt)
    rec("G15", ok, "readiness.kind=%s; probe observed failing then succeeding" % rk if ok else "kind=%s readiness-evidence insufficient" % rk)

def g16():
    st = art("8b", "stop-evidence.txt")
    if not st.is_file():
        note(st); return rec("G16", False, "stop-evidence.txt absent")
    t = rd(st).lower()
    ok = ("pid gone" in t or "pid=none" in t or "exit" in t) and ("free" in t)
    rec("G16", ok, "stop evidenced (pid gone, ports free)" if ok else "stop-evidence lacks pid/port statements")

def g17():
    h18 = WS / "evidence" / "hardening" / "h18-failure-classes.txt"
    pr = []
    if not h18.is_file():
        note(h18); pr.append("h18 absent")
    else:
        th = rd(h18).upper()
        miss = [s for s in STEMS if s not in th]
        if miss: pr.append("classes missing: %s" % ",".join(miss))
        n_ind = len(re.findall(r"(?i)induced|reproduction|produced by", th))
        if n_ind < 10: pr.append("only %d induced-condition entries" % n_ind)
    for nm in ("test_failure_classes", "test_port_conflict_is_its_own_class"):
        p2 = tproof("8b", nm)
        if not p2[0]: pr.append(nm + ": " + p2[1])
    rec("G17", not pr, "ten classes with reproductions + proofs" if not pr else "; ".join(pr))

def g18():
    bl = art("8b", "browser-lifecycle.txt"); p3 = tproof("8b", "test_browser_handle_map")
    rec("G18", bl.is_file() and p3[0], "lifecycle artifact + map-test proof" if bl.is_file() and p3[0] else "artifact:%s proof:%s" % (bl.is_file(), p3[1]))

def g19():
    ok, why = gate_cand("8b")
    pr = [] if ok else ["ledger 8b: " + why]
    tr = suite_ok("evidence/cpm1/test-run-handoff.txt", 122) if art("test-run-handoff.txt").is_file() else suite_ok("evidence/test-run.txt", 122)
    if not tr[0]: pr.append("suite " + tr[1])
    bm = bm_equal()
    if not bm[0]: pr.append("build-manifest " + bm[1])
    lc = linecount_within("linecount-a.txt", CAPS_A, ABS_A)
    if not lc[0]: pr.append("linecount-a " + lc[1])
    snap_ok, snap_why, _f19 = ledger_snapshot_ok()
    if not snap_ok: pr.append("snapshot " + snap_why)
    rec("G19", not pr, "gate 8b CANDIDATE; suite/BM/linecount clean; gates 0-7b snapshot-enforced" if not pr else "; ".join(pr))

# ---------------- Band 3 (Gate 8c) ----------------
def g20():
    es = art("8c", "empty-session.json"); pf = tproof("8c", "test_new_session_spawns_no_process")
    rec("G20", es.is_file() and pf[0], "record + proof" if es.is_file() and pf[0] else "artifact:%s proof:%s" % (es.is_file(), pf[1]))

def g21():
    sf = art("8c", "selection-flow.txt")
    ok = sf.is_file()
    if ok:
        t = rd(sf).lower()
        ok = all(k in t for k in ("create", "select", "initialize", "use")) and len(re.findall(r"\d{2}:\d{2}:\d{2}", t)) >= 3
    rec("G21", ok, "Create->Select->Initialize->Use with timestamps" if ok else "selection-flow absent/incomplete")

def g22():
    gr = tproof("8c", "test_governed_replacement")
    hits = [h for h in grep_tree(["modules/sow"], "close it before launching another model into it",
      exclude=("test", "fixture", "node_modules", "/docs/", "LOOP_STATE", "receipts"))
      if h.endswith((".js", ".py"))]
    rec("G22", gr[0] and not hits, "governed replacement; refusal string gone" if (gr[0] and not hits) else "proof:%s hits:%s" % (gr[1], hits[:3]))

def g23():
    pnd = art("8c", "powershell-not-default.txt")
    rec("G23", pnd.is_file(), "grep-proof present" if pnd.is_file() else "powershell-not-default.txt absent")

def g24():
    ok, why = gate_cand("8c")
    ss = art("8c", "sow-suite.txt")
    sok = ss.is_file() and suite_ok(str(ss.relative_to(WS)), 1)[0]
    lc = linecount_within("linecount-a.txt", CAPS_A, ABS_A)
    rec("G24", ok and sok and lc[0], "ledger 8c + SOW suite + caps" if (ok and sok and lc[0]) else "ledger:%s suite:%s caps:%s" % (why, sok, lc[1]))

# ---------------- Band 4 (Gate 8d) ----------------
def g25():
    dom = art("8d", "conductor-dom.txt"); fb = art("8d", "conductor-dom-fails-before.txt")
    if not dom.is_file():
        note(dom); note(fb); return rec("G25", False, "conductor-dom.txt absent")
    t = rd(dom).lower()
    has_input = ("<input" in t) or ("<textarea" in t) or ("contenteditable" in t)
    turns = len(re.findall(r"turn[^0-9]*\d{2}:\d{2}:\d{2}", t))
    ok = has_input and (("submit" in t) or ("send" in t)) and turns >= 2 and fb.is_file()
    rec("G25", ok, "enabled input + submit + %d timestamped turns + fails-before" % turns if ok else "input:%s turns:%d fails-before:%s" % (has_input, turns, fb.is_file()))

def g26():
    rt = art("8d", "conductor-roundtrip.txt")
    if not rt.is_file():
        note(rt); return rec("G26", False, "conductor-roundtrip.txt absent (A-6 text)")
    t = rd(rt); low = t.lower()
    nr = "NOT_RUN(NO_CONDUCTOR_MODEL_AVAILABLE)" in t
    live = ("directive" in low) and ("response" in low)
    named = bool(re.search(r"(gpt-5\.6-sol|model_id|provider)", t, re.I))
    reg_named = ("CONDUCTOR_MODEL_REGISTRY" in t) or ("gpt-5.6-sol" in t)
    ok = (live and named) or (nr and reg_named)
    rec("G26", ok, "A-6 round-trip (or truthful NOT_RUN naming registry entries)" if ok else "legs incomplete: live:%s named:%s NOT_RUN:%s" % (live, named, nr))

def g27():
    ok, why = gate_cand("8d"); rec("G27", ok, why)

# ---------------- Band 5 (Gate 8e) ----------------
def g28():
    wr = art("8e", "worker-registry.json")
    ok = False; why = "worker-registry.json absent"; workers = []
    if wr.is_file():
        try:
            data = json.loads(rd(wr))
            workers = data if isinstance(data, list) else data.get("workers", [])
            def hf(w):
                f = json.dumps(w).lower()
                return all(k in f for k in ("session_id", "provider_id", "model_id", "backend", "state", "created_utc"))
            ok = isinstance(workers, list) and len(workers) >= 2 and all(hf(w) for w in workers[:10])
            why = "%d workers, fields incl created_utc" % len(workers) if ok else "workers=%d/fields missing" % (len(workers) if isinstance(workers, list) else -1)
        except Exception as e:
            why = "registry unparsable %s" % e
    pf = tproof("8e", "test_registry_fields_projected")
    rec("G28", ok and pf[0], why + "; test:%s" % pf[0])

def g29():
    dd = art("8e", "directive-delivery.txt")
    ok = dd.is_file() and "session_id" in rd(dd)
    rec("G29", ok, "delivery with target session" if ok else "directive-delivery absent/no session_id")

def g30():
    syn = art("8e", "synthesis.txt"); rt = art("8d", "conductor-roundtrip.txt")
    ok = syn.is_file() and rt.is_file()
    if ok:
        ts = rd(syn).lower()
        ok = ("two" in ts or "2 worker" in ts) and ("model" in ts)
    rec("G30", ok, "return + synthesis naming both sources" if ok else "synthesis:%s roundtrip:%s" % (syn.is_file(), rt.is_file()))

def g31():
    wf = art("8e", "worker-failure.txt")
    owed = grep_tree(["modules/sow/control_plane", "modules/sow/apps/desktop"], "LIVE_WORKERS_OWED", exclude=("test", "node_modules"))
    mlbl = grep_tree(["modules/sow/apps/desktop/renderer"], "mock", exclude=("node_modules",))
    ok = wf.is_file() and ((not owed) or bool(mlbl))
    rec("G31", ok, "failure identified; feed honest" if ok else "wf:%s owed:%s labelled:%s" % (wf.is_file(), owed[:2], bool(mlbl)))

def g32():
    ok, why = gate_cand("8e")
    blob = json.dumps(ledger().get("gates", {}).get("8e", {}))
    note(WS / "evidence" / "GATE-LEDGER.json")
    stated = ok and (("NOT_RUN" in blob) or ("live" in blob.lower()))
    rec("G32", stated, "ledger 8e with live/NOT_RUN statement" if stated else why)

# ---------------- Band 6 (Gate 8f) ----------------
def g33():
    det = art("8f", "opencode-detect.txt")
    if not det.is_file():
        note(det); return rec("G33", False, "opencode-detect.txt absent")
    rec("G33", True, "detection result recorded (%s)" % ("absent on host" if "ABSENT" in rd(det).upper() else "present"))

def g34():
    direct = art("8f", "opencode-direct.txt"); un = art("8f", "opencode-unavailable.txt")
    det = art("8f", "opencode-detect.txt")
    ab = det.is_file() and ("ABSENT" in rd(det).upper())
    if ab:
        ok = direct.is_file() and un.is_file() and "NOT_RUN" in rd(direct).upper()
        rec("G34", ok, "truthful NOT_RUN(OPENCODE_UNAVAILABLE)" if ok else "unavailable records incomplete")
    else:
        rec("G34", direct.is_file(), "direct access recorded" if direct.is_file() else "opencode-direct.txt absent")

def g35():
    dele = art("8f", "opencode-delegation.txt")
    det = art("8f", "opencode-detect.txt")
    ab = det.is_file() and ("ABSENT" in rd(det).upper())
    if ab:
        ok = dele.is_file() and "NOT_RUN" in rd(dele).upper()
        rec("G35", ok, "delegation truthfully NOT_RUN" if ok else "delegation NOT_RUN record missing")
    else:
        rec("G35", dele.is_file(), "delegation chain recorded" if dele.is_file() else "opencode-delegation.txt absent")

def g36():
    bnm = art("8f", "backend-not-model.txt"); mh = []
    for rr in ("modules/sow/control_plane/nodes", "modules/sow/adapters"):
        root = WS / rr
        if not root.is_dir(): continue
        for p in root.rglob("*.py"):
            try:
                txt = rd(p)
            except OSError:
                continue
            for m in re.finditer(r"model_id['\"]?\s*[:=]\s*['\"]([^'\"]+)", txt):
                if "opencode" in m.group(1).lower(): mh.append(p.name + ": " + m.group(1))
    br = grep_tree(["modules/sow/control_plane", "modules/sow/adapters"], "backend ==", exclude=("test", "node_modules"))
    rec("G36", bnm.is_file() and (not mh) and (not br), "no backend/model confusion" if (bnm.is_file() and not mh and not br) else "artifact:%s rows:%s branches:%s" % (bnm.is_file(), mh[:3], br[:3]))

def g37():
    ok, why = gate_cand("8f"); rec("G37", ok, why)

# ---------------- Band 7 (Gate 8g) ----------------
def g38():
    rdj = art("8g", "registry-dump.json"); da = art("8g", "duplication-audit.txt")
    ok = rdj.is_file() and da.is_file()
    if ok:
        try:
            json.loads(rd(rdj))
        except Exception:
            ok = False
    rec("G38", ok, "registry dump + duplication audit" if ok else "dump:%s audit:%s" % (rdj.is_file(), da.is_file()))

def _reg_rows(data):
    if isinstance(data, list): return data
    for k in ("models", "rows", "entries"):
        v = data.get(k)
        if isinstance(v, list): return v
        if isinstance(v, dict): return list(v.values())
    return []

def g39():
    rdj = art("8g", "registry-dump.json")
    if not rdj.is_file():
        note(rdj); return rec("G39", False, "registry-dump.json absent")
    try:
        data = json.loads(rd(rdj))
        rows = _reg_rows(data)
        sample = json.dumps(rows[:5]) if rows else ""
        miss = [k for k in REG39 if k not in sample]
        rec("G39", bool(rows) and not miss, "%d rows carry final shape" % len(rows) if not miss else "rows=%d missing fields: %s" % (len(rows), ",".join(miss[:6])))
    except Exception as e:
        rec("G39", False, "dump unparsable %s" % e)

def g40():
    pf = tproof("8g", "test_incompatible_selection_refused")
    rec("G40", pf[0], "incompatibility refusal proven" if pf[0] else pf[1])

def g41():
    dv = art("8g", "discovery.txt")
    if not dv.is_file():
        note(dv); return rec("G41", False, "discovery.txt absent")
    t = rd(dv).lower()
    rec("G41", "ollama" in t, "per-source discovery recorded" if "ollama" in t else "no ollama source recorded")

def g42():
    gs = art("8g", "grok-status.txt")
    rec("G42", gs.is_file(), "grok status recorded either way" if gs.is_file() else "grok-status.txt absent")

def g43():
    ok, why = gate_cand("8g"); rec("G43", ok, why)

# ---------------- Band 8 (Gate 8h) ----------------
def g44():
    prov = WS / "modules" / "distillery" / "INSTALL-PROVENANCE.json"
    bc = art("8h", "distillery-baseline-clean.txt")
    ok = prov.is_file() and bc.is_file() and ("no differences" in rd(bc).lower())
    rec("G44", ok, "Option-A install + protected tree unchanged" if ok else "prov:%s baseline:%s" % (prov.is_file(), bc.is_file()))

def g45():
    dj = WS / "shell" / "modules" / "distillery.json"
    okj = False; whyj = "distillery.json absent"
    if dj.is_file():
        try:
            a = json.loads(rd(dj))
            argv0 = ((a.get("launch") or {}).get("argv") or [""])[0]
            okj = (a.get("state_class") == "runnable") and ("launch" in a) and (a.get("readiness", {}).get("kind") == "http") and (a.get("identity", {}).get("kind") == "http_json") and (a.get("stop", {}).get("kind") == "job_object") and isinstance(a.get("runtime_writes"), list) and argv0.lower().endswith(".exe")
            whyj = "real lifecycle declared (.exe chain)" if okj else "adapter incomplete"
        except Exception as e:
            whyj = "unparsable %s" % e
    st = art("8h", "distillery-start.txt"); sp = art("8h", "distillery-stop.txt")
    rec("G45", okj and st.is_file() and sp.is_file(), whyj + "; start:%s stop:%s" % (st.is_file(), sp.is_file()))

def g46():
    dom = art("8h", "distillery-dom.txt")
    if not dom.is_file():
        note(dom); return rec("G46", False, "distillery-dom.txt absent")
    t = rd(dom); tl = t.lower()
    need = ["runtime status", "student model", "pipeline state", "queue", "logs"]
    miss = [x for x in need if x not in tl]
    nobare = "D:/" not in t
    rec("G46", (not miss) and nobare, "console surfaces, no bare D:/" if ((not miss) and nobare) else "missing:%s barepath:%s" % (",".join(miss), not nobare))

def g47():
    na = art("8h", "no-autocompute.txt"); pf = tproof("8h", "test_start_invokes_no_pipeline")
    rec("G47", na.is_file() and pf[0], "no-compute window + start-path test" if na.is_file() and pf[0] else "artifact:%s proof:%s" % (na.is_file(), pf[1]))

def g48():
    h16 = WS / "evidence" / "hardening" / "h16-contrast.txt"
    if not h16.is_file():
        note(h16); return rec("G48", False, "h16-contrast.txt absent")
    t = rd(h16)
    tail = [l for l in t.strip().splitlines() if l.strip()]
    ok = tail[-1].strip().endswith("OK") or ("pass" in t.lower())
    rec("G48", ok, "contrast machinery green" if ok else "h16 does not end OK/pass")

def g49():
    ok, why = gate_cand("8h"); rec("G49", ok, why)

# ---------------- Band 9 (Gate 8i) ----------------
def g50():
    p = art("8i", "external-instance-stopped.txt")
    ok = p.is_file()
    if ok:
        t = rd(p).lower()
        ok = ("pid" in t) and (("command" in t) or ("cmdline" in t)) and ("8765" in t)
    rec("G50", ok, "port-8765 stop recorded (or already-free)" if ok else "external-instance-stopped.txt absent")

def g51():
    prov = WS / "modules" / "tokencenter" / "INSTALL-PROVENANCE.json"
    bc = art("8i", "tokenpiggy-baseline-clean.txt")
    c7 = tproof("8i", "test_tokencenter_loopback_and_csrf")
    ok = prov.is_file() and c7[0] and bc.is_file() and ("no differences" in rd(bc).lower())
    rec("G51", ok, "copy installed; original untouched; loopback+CSRF fixed in copy" if ok else "prov:%s baseline:%s c7:%s" % (prov.is_file(), bc.is_file(), c7[1]))

def g52():
    tj = WS / "shell" / "modules" / "tokencenter.json"
    okj = False; whyj = "tokencenter.json absent"
    if tj.is_file():
        try:
            a = json.loads(rd(tj)); r = a.get("readiness", {})
            okj = (r.get("kind") == "http") and str(r.get("url", "")).endswith("/healthz") and r.get("expect_status") == 200 and a.get("identity", {}).get("kind") == "http_json" and bool(a.get("identity", {}).get("required_keys")) and a.get("stop", {}).get("kind") == "job_object"
            whyj = "module like any other" if okj else "adapter incomplete"
        except Exception as e:
            whyj = "unparsable %s" % e
    sta = art("8i", "tokencenter-start.txt"); stp = art("8i", "tokencenter-stop.txt")
    rec("G52", okj and sta.is_file() and stp.is_file(), whyj + "; start:%s stop:%s" % (sta.is_file(), stp.is_file()))

def g53():
    dom = art("8i", "main-ui-dom.txt")
    pngdir = M1 / "8i"
    pngs = sorted(pngdir.glob("main-ui-*.png")) if pngdir.is_dir() else []
    th = {}
    for p in pngs:
        n = p.name.lower(); k = "dark" if "dark" in n else ("light" if "light" in n else None)
        if k:
            g, _r = png_ok(p)
            th[k] = th.get(k, False) or g
    central = False
    if dom.is_file():
        t = rd(dom).lower()
        central = ("token center" in t) and all(k in t for k in ("sovereign", "debate", "distillery"))
    else:
        note(dom)
    ok = dom.is_file() and len(th) >= 2 and all(th.values()) and central
    rec("G53", ok, "central placement + themed non-blank captures" if ok else "dom:%s themes:%s central:%s" % (dom.is_file(), sorted(th), central))

def g54():
    h19 = WS / "evidence" / "hardening" / "h19-tokencenter-contract.txt"
    rec("G54", h19.is_file(), "contract artifact present" if h19.is_file() else "h19-tokencenter-contract.txt absent")

def g55():
    nc = art("8i", "no-credentials.txt")
    rec("G55", nc.is_file(), "absence-of-credential-surface proof" if nc.is_file() else "no-credentials.txt absent")

def g56():
    ok, why = gate_cand("8i"); rec("G56", ok, why)

# ---------------- Band 10 (Gate 8j) ----------------
def g57():
    steps = ["state-after-coldstart.json", "stepB-debate.txt", "stepC-workspace.txt", "stepD-conductor.txt",
             "stepE-opencode.txt", "stepF-models.txt", "stepG-distillery.txt", "stepH-tokencenter.txt"]
    missing = [s for s in steps if not art("8j", s).is_file()]
    rec("G57", not missing, "scenario A-H artifacts present" if not missing else "missing: %s" % ",".join(missing))

def g58():
    pc = art("8j", "proof-chain.txt")
    ok = pc.is_file()
    if ok:
        t = rd(pc)
        ok = ("Human" in t) and (("NOT_RUN(NO_SPEND_AUTHORIZATION)" in t) or ("openai_codex_cli" in t))
    rec("G58", ok, "proof chain with bounded-spend handling" if ok else "proof-chain absent/incomplete")

def g59():
    tr = suite_ok("evidence/test-run.txt", 122)
    bm = bm_equal()
    dark, light = css_blocks()
    tok = all(dark.get(k, "").lower() == v for k, v in V3.items())
    rec("G59", tr[0] and bm[0] and tok, "suite+BM+:root clean" if (tr[0] and bm[0] and tok) else "suite:%s bm:%s tokens:%s" % (tr[1], bm[1], tok))

def g60():
    lc = linecount_within("linecount-a.txt", CAPS_A, ABS_A)
    rec("G60", lc[0], "difflib vs before-a within Package-A caps" if lc[0] else lc[1])

def g61():
    oc = art("8j", "orphans-after.txt")
    busy = [p for p in (5175, 8700, 5180) if popen(p)]
    e5 = popen(8765)
    octx = rd(oc).lower() if oc.is_file() else ""
    ok = oc.is_file() and (not busy) and ((not e5) or ("8765" in octx and "external" in octx))
    rec("G61", ok, "builder processes stopped; ports as found" if ok else "busy:%s oc:%s" % (busy or "none", oc.is_file()))

def g62():
    ok, why = gate_cand("8j"); rec("G62", ok, why)

def g63():
    rp = WS / "docs" / "CP-M1-REPORT.md"
    if not rp.is_file():
        note(rp); return rec("G63", False, "docs/CP-M1-REPORT.md absent")
    t = rd(rp)
    rows = set(re.findall(r"R-(?:0?[1-9]|1[0-5])\b", t))
    need = set("R-%d" % i for i in range(1, 16))
    partA = "Part A" in t
    tags = t.count("FACT[")
    cols = all(c.lower() in t.lower() for c in ("implementation location", "files changed", "behavior before", "validation performed"))
    ok = need <= rows and partA and tags >= 15 and cols
    rec("G63", ok, "Part A per requirement, tagged" if ok else "rows:%d partA:%s cols:%s tags:%d" % (len(need & rows), partA, cols, tags))
# ---------------- Band 11 (Handoff) ----------------
def g64():
    ok, why, _n = hashes_verify(WS, M1 / "before-b" / "HASHES.txt")
    rec("G64", ok, "before-b verified (%s)" % why if ok else "before-b: " + why)

def g65():
    tb = art("test-run-handoff.txt")
    if not tb.is_file():
        note(tb); return rec("G65", False, "test-run-handoff.txt absent")
    ok, why = suite_ok(str(tb.relative_to(WS)), 1)
    m = re.search(r"Ran (\d+) tests? in", rd(tb))
    rec("G65", ok, "handoff floor Ran %s OK" % (m.group(1) if m else "?") if ok else why)

def g66():
    hm = art("handoff-manifests.txt")
    ok = hm.is_file() and rd(hm).lower().count("no differences") >= 5
    rec("G66", ok, "five roots spot-checked clean" if ok else "handoff-manifests.txt incomplete")

def g67():
    hd = art("handoff.txt")
    ok = hd.is_file() and ("G64" in rd(hd)) and ("G66" in rd(hd))
    rec("G67", ok, "handoff recorded before Band 12" if ok else "handoff.txt absent/incomplete")

# ---------------- Band 12 (Gate 9a) ----------------
def g68():
    pin = art("9a", "pin.txt")
    vp = WS / "runtime" / "llama.cpp" / "current"
    ok = pin.is_file()
    if ok:
        t = rd(pin); tl = t.lower()
        need = ["sha256", "origin", "cuda", "build"]
        miss = [x for x in need if x not in tl]
        ok = (not miss) and (vp.exists())
        rec("G68", ok, "pinned install provenanced; current resolves" if ok else "pin fields missing: %s current-exists:%s" % (",".join(miss), vp.exists()))
    else:
        note(pin); note(vp)
        rec("G68", False, "pin.txt absent")

def g69():
    tm = WS / "runtime" / "llama.cpp" / "test-models"
    files = list(tm.glob("*")) if tm.is_dir() else []
    prov = art("9a", "gguf-provenance.txt")
    ok = bool(files) and prov.is_file() and ("blob" in rd(prov).lower())
    for f in files[:10]:
        sha(f)
    rec("G69", ok, "%d staged artifacts with blob provenance" % len(files) if ok else "staged:%d provenance:%s" % (len(files), prov.is_file()))

def g70():
    names = ["a1-version.txt", "a2-cpu.txt", "a3-cuda.txt", "a4-offload.txt"]
    missing = [f for f in names if not art("9a", f).is_file()]
    for f in names:
        note(art("9a", f))
    rec("G70", not missing, "A1-A4 recorded" if not missing else "missing: %s" % ",".join(missing))

def g71():
    names = ["a5-server.txt", "a6-openai-api.txt", "a7-cancel.txt", "a8-shutdown.txt"]
    missing = [f for f in names if not art("9a", f).is_file()]
    for f in names:
        note(art("9a", f))
    rec("G71", not missing, "A5-A8 recorded" if not missing else "missing: %s" % ",".join(missing))

def g72():
    rs = art("9a", "router-support.txt"); lj = WS / "shell" / "modules" / "llamacpp.json"
    okj = False; whyj = "llamacpp.json absent"
    if lj.is_file():
        try:
            a = json.loads(rd(lj)); r = a.get("readiness", {})
            okj = (r.get("kind") == "http") and (":5183/models" in str(r.get("url", ""))) and (a.get("identity", {}).get("kind") == "http_json") and (a.get("stop", {}).get("kind") == "job_object") and ((a.get("open") or {}).get("kind") == "none")
            whyj = "adapter declares router contract on 5183" if okj else "adapter incomplete"
        except Exception as e:
            whyj = "unparsable %s" % e
    spawners = grep_tree(["modules/sow"], "llama-server", exclude=("test", "node_modules"))
    ok = rs.is_file() and okj and (not spawners)
    rec("G72", ok, "router mode asserted; shell owns process" if ok else "router-support:%s adapter:%s spawners:%s" % (rs.is_file(), whyj, spawners[:2]))

def g73():
    oa = art("9a", "ollama-after.txt")
    ok = oa.is_file() and ("version" in rd(oa).lower())
    rec("G73", ok, "ollama intact after band steps" if ok else "9a/ollama-after.txt absent/incomplete")

def g74():
    ok, why = gate_cand("9a"); rec("G74", ok, why)

# ---------------- Band 13 (Gate 9b) ----------------
def g75():
    p = art("9b", "initial-state.txt")
    ok = p.is_file()
    if ok:
        t = rd(p).lower(); ok = all(s in t for s in ("loaded", "unloaded"))
    rec("G75", ok, "initial router states distinguished" if ok else "initial-state artifact absent/incomplete")

def g76():
    p = art("9b", "load-model-a.txt")
    ok = p.is_file()
    if ok:
        t = rd(p).lower(); ok = all(s in t for s in ("vram", "ram"))
    rec("G76", ok, "on-demand load measured (time/VRAM/RAM)" if ok else "load artifact absent/incomplete")

def g77():
    p = art("9b", "unload-model-a.txt")
    ok = p.is_file()
    if ok:
        t = rd(p).lower(); ok = ("vram" in t) and ("return" in t or "freed" in t or "delta" in t)
    rec("G77", ok, "explicit unload; VRAM returns" if ok else "unload artifact absent/incomplete")

def g78():
    p = art("9b", "lru-eviction.txt")
    ok = p.is_file() and ("evict" in rd(p).lower())
    rec("G78", ok, "LRU eviction observed at models-max 1" if ok else "lru-eviction.txt absent/incomplete")

def g79():
    p = art("9b", "failure-behaviour.txt")
    ok = p.is_file()
    if ok:
        t = rd(p).lower(); ok = all(s in t for s in ("invalid", "corrupt", "unsupported"))
    rec("G79", ok, "three failure modes survive router" if ok else "failure-behaviour absent/incomplete")

def g80():
    ok, why = gate_cand("9b")
    blob = json.dumps(ledger().get("gates", {}).get("9b", {})).lower()
    note(WS / "evidence" / "GATE-LEDGER.json")
    rec("G80", ok and ("no sovereign integration" in blob), "gate 9b states no integration yet" if ok else why)

# ---------------- Band 14 (Gate 9c) ----------------
def g81():
    bp = WS / "modules" / "sow" / "adapters" / "base" / "backend.py"
    if not bp.is_file():
        note(bp); return rec("G81", False, "backend.py absent")
    t = rd(bp)
    need = ["list_models", "load_model", "unload_model", "generate", "cancel", "health", "capabilities"]
    have = sum(1 for m in need if m in t)
    nr = art("9c", "no-replacement.txt")
    ok = (have == 7) and ("metrics" not in t) and nr.is_file()
    rec("G81", ok, "protocol widened to seven methods; metrics absent; no parallel abstraction" if ok else "methods:%d/7 metrics-present:%s no-replacement:%s" % (have, "metrics" in t, nr.is_file()))

def g82():
    pf = tproof("9c", "test_ollama_unsupported_honest")
    rec("G82", pf[0], "unsupported paths honest" if pf[0] else pf[1])

def g83():
    base = WS / "modules" / "sow" / "adapters"
    found = list(base.rglob("*llamacpp*.py")) if base.is_dir() else []
    fused = grep_tree(["modules/sow/adapters"], "llama.cpp/", exclude=("test",))
    for f in found[:5]:
        sha(f)
    ok = bool(found) and (not fused)
    rec("G83", ok, "LlamaCppBackend beside OllamaBackend; identity separate" if ok else "backend files:%d fused-strings:%s" % (len(found), fused[:2]))

def g84():
    pm = art("9c", "parity-matrix.txt")
    ok = pm.is_file()
    if ok:
        t = rd(pm).lower()
        ok = ("ollama" in t) and (("llamacpp" in t) or ("llama.cpp" in t)) and (("unsupported" in t) or ("fail" in t))
    rec("G84", ok, "parity matrix both backends" if ok else "parity-matrix.txt absent/incomplete")

def g85():
    em = art("9c", "error-mapping.txt")
    ok = em.is_file()
    if ok:
        t = rd(em).upper()
        ok = sum(1 for s in STEMS if s in t) >= 8
    rec("G85", ok, "errors mapped into G17 vocabulary" if ok else "error-mapping.txt absent/thin")

def g86():
    dr = art("9c", "default-runtime.txt")
    ok = dr.is_file() and ("ollama" in rd(dr).lower())
    ok2, why = gate_cand("9c")
    rec("G86", ok and ok2, "Ollama remains default; gate 9c CANDIDATE" if (ok and ok2) else "default:%s gate:%s" % (ok, why))

# ---------------- Band 15 (Gate 9d) ----------------
def g87():
    va = art("9d", "vram-authority.txt")
    ok = va.is_file()
    if ok:
        t = rd(va).lower()
        ok = ("nvidia-smi" in t) or ("nvml" in t) or ("exclusive residency" in t)
    rec("G87", ok, "one budget authority chosen and recorded" if ok else "vram-authority.txt absent/unspecific")

def g88():
    se = art("9d", "single-evictor.txt")
    ok = se.is_file()
    if ok:
        t = rd(se)
        ok = ("--no-models-autoload" in t) and bool(re.search(r"models-max\D+\d+", t))
    rec("G88", ok, "router demoted to mechanism (S-3)" if ok else "single-evictor.txt absent/unspecific")

def g89():
    sm = art("9d", "state-map.txt")
    ok = sm.is_file()
    if ok:
        t = rd(sm).upper()
        ok = all(s in t for s in ("NOT_LOADED", "RESIDENT", "EVICTED"))
    rec("G89", ok, "router states map into existing planner vocabulary" if ok else "state-map.txt absent/incomplete")

def g90():
    rp = WS / "modules" / "sow" / "scheduler" / "residency_planner" / "residency_planner.py"
    if not rp.is_file():
        note(rp); return rec("G90", False, "residency_planner.py absent")
    t = rd(rp)
    bad = [w for w in ("CreateProcess", "TerminateJobObject", "taskkill", "subprocess.Popen", "os.kill") if w in t]
    gp = art("9d", "planner-no-procctl.txt")
    rec("G90", (not bad) and gp.is_file(), "planner actuates only via backend contract" if ((not bad) and gp.is_file()) else "procctl:%s artifact:%s" % (bad, gp.is_file()))

def g91():
    rt = art("9d", "roundtrip.txt")
    ok = rt.is_file()
    if ok:
        t = rd(rt).upper()
        ok = ("RESIDENT" in t) and (("EVICTED" in t) or ("NOT_LOADED" in t)) and ("VRAM" in t)
    rec("G91", ok, "planner round-trip proved with VRAM observations" if ok else "roundtrip.txt absent/incomplete")

def g92():
    p1 = tproof("9d", "test_planner_never_evicts_generating")
    p2 = tproof("9d", "test_router_no_unrequested_transition")
    rec("G92", p1[0] and p2[0], "both mid-generation eviction guards proven" if (p1[0] and p2[0]) else "p1:%s p2:%s" % (p1[1], p2[1]))

def g93():
    fc = art("9d", "fail-closed.txt")
    ok = fc.is_file() and sum(1 for w in ("unavailable", "stale", "timeout", "eviction") if w in rd(fc).lower()) >= 3
    ok2, why = gate_cand("9d")
    rec("G93", ok and ok2, "fail-closed outcomes recorded; gate 9d CANDIDATE" if (ok and ok2) else "fail-closed:%s gate:%s" % (ok, why))

# ---------------- Band 16 (Gate 9e) ----------------
def g94():
    pop_ = art("9e", "population.txt"); rdj = art("8g", "registry-dump.json")
    ok = pop_.is_file()
    if ok:
        t = rd(pop_).lower()
        ok = ("tag" in t) and (("disposition" in t) or ("model_id" in t))
        if rdj.is_file():
            try:
                data = json.loads(rd(rdj)); rows = _reg_rows(data)
                filled = [r for r in rows[:50] if isinstance(r, dict) and r.get("artifacts")]
                ok = ok and bool(filled)
            except Exception:
                pass
    rec("G94", ok, "artifacts populated; every tag disposed" if ok else "population.txt absent/unconvincing")

def g95():
    pf = tproof("9e", "test_legacy_alias_resolution")
    rec("G95", pf[0], "legacy references resolve" if pf[0] else pf[1])

def g96():
    sd = WS / "modules" / "sow" / "schemas"
    sch = sorted(sd.glob("*manifest*")) if sd.is_dir() else []
    ok = bool(sch)
    if ok:
        t = rd(sch[0])
        need = ["artifact_id", "model_id", "source_hash", "artifact_hash", "quantization", "creation_tool", "status"]
        ok = all(x in t for x in need)
    rec("G96", ok, "deployment manifest schema canonical" if ok else "schema missing/incomplete (%d candidates)" % len(sch))

def g97():
    pf = tproof("9e", "test_ingestion_rejects")
    rec("G97", pf[0], "ingestion fail-closed proven" if pf[0] else pf[1])

def g98():
    ta = art("9e", "three-axes.txt"); pf = tproof("9e", "test_promotion_axis_orthogonal")
    rec("G98", ta.is_file() and pf[0], "promotion axis orthogonal (S-12)" if ta.is_file() and pf[0] else "artifact:%s proof:%s" % (ta.is_file(), pf[1]))

def g99():
    ok, why = gate_cand("9e"); rec("G99", ok, why)

# ---------------- Band 17 (Gate 9f) ----------------
def g100():
    rdj = art("8g", "registry-dump.json")
    if not rdj.is_file():
        note(rdj); return rec("G100", False, "registry dump absent")
    try:
        data = json.loads(rd(rdj)); rows = _reg_rows(data)
        meas = [r for r in rows[:50] if isinstance(r, dict) and (r.get("validated_context") or r.get("validation_evidence"))]
        rec("G100", bool(meas), "%d rows carry measured context values" % len(meas) if meas else "no row carries validated_context/validation_evidence")
    except Exception as e:
        rec("G100", False, "dump unparsable %s" % e)

def g101():
    cm = art("9f", "context-measurement.txt")
    if not cm.is_file():
        note(cm); return rec("G101", False, "context-measurement.txt absent")
    t = rd(cm)
    tiers = len(set(re.findall(r"(?i)(short baseline|medium|current declared production|next candidate)", t)))
    budget = "budget" in t.lower()
    rec("G101", tiers >= 3 and budget, "bounded measurement declared (%d tier labels, budget present)" % tiers if (tiers >= 3 and budget) else "tiers:%d budget:%s" % (tiers, budget))

def g102():
    cm = art("9f", "context-measurement.txt")
    if not cm.is_file():
        note(cm); return rec("G102", False, "context-measurement.txt absent")
    t = rd(cm)
    got = sum(1 for x in ("ttft", "vram", "ram", "prompt", "generation") if x in t.lower())
    nm = "NOT_MEASURED" in t
    rec("G102", got >= 4 or nm, "variables recorded or NOT_MEASURED" if (got >= 4 or nm) else "variables thin (%d/5)" % got)

def g103():
    di = art("9f", "demotion-impact.txt")
    if not di.is_file():
        note(di); return rec("G103", False, "demotion-impact.txt absent")
    t = rd(di); low = t.lower()
    accepted = ("operator accepts" in low) or ("accepted by operator" in low) or ("OPERATOR ACCEPTANCE" in t)
    stranded = ("newly fail" in low) or ("would newly" in low) or ("no request class" in low)
    rec("G103", stranded and (accepted or ("STOP" in t.upper())), "demotion impact dry-run recorded with acceptance/STOP" if stranded else "dry-run content missing")

def g104():
    rv = WS / "modules" / "sow" / "scheduler" / "resolver" / "resolver.py"
    ok2, why = gate_cand("9f")
    t = rd(rv) if rv.is_file() else ""
    note(rv)
    rec("G104", ok2 and (("validated" in t) or ("production_context" in t)), "resolver consumes truth; gate 9f CANDIDATE" if ok2 else "gate:%s resolver-read:%s" % (why, bool(t)))

# ---------------- Band 18 (Gate 9g) ----------------
def g105():
    gp = art("9g", "fallback-resolver-grep.txt")
    newpaths = grep_tree(["modules/sow/control_plane"], "role_router", exclude=("test", "node_modules"))
    rec("G105", gp.is_file() and (not newpaths), "fallback rides existing resolver" if (gp.is_file() and not newpaths) else "grep-proof:%s role_router hits:%s" % (gp.is_file(), newpaths[:2]))

def g106():
    fb = art("9g", "fallback-record.txt")
    ok = fb.is_file()
    if ok:
        t = rd(fb).lower()
        ok = all(k in t for k in ("candidate", "reason", "replacement", "timestamp"))
    rec("G106", ok, "fallback visible, never silent" if ok else "fallback-record.txt absent/incomplete")

def g107():
    pf = tproof("9g", "test_reasoning_failure_no_fallback")
    rec("G107", pf[0], "infrastructure-only fallback proven" if pf[0] else pf[1])

def g108():
    aj = WS / "shell" / "static" / "app.js"
    t = rd(aj).lower() if aj.is_file() else ""
    note(aj)
    ok = ("vram" in t) and (("resource" in t) or ("accounting" in t))
    rec("G108", ok, "resource accounting surfaced in existing UI" if ok else "app.js lacks resource-accounting surface")

def g109():
    lr = WS / "shell" / "src" / "logring.py"
    t = rd(lr) if lr.is_file() else ""
    note(lr)
    pf = tproof("9g", "test_log_fields_redacted")
    mt = grep_tree(["modules/sow/adapters"], "def metrics", exclude=("test",))
    ok = ("runtime" in t and "artifact_id" in t) and pf[0] and bool(mt)
    rec("G109", ok, "log fields extended + redaction-tested; metrics() landed" if ok else "logring-fields:%s proof:%s metrics:%s" % ("artifact_id" in t, pf[1], bool(mt)))

def g110():
    ok, why = gate_cand("9g"); rec("G110", ok, why)

# ---------------- Band 19 (Gate 9h) ----------------
def g111():
    rdj = art("8g", "registry-dump.json")
    ok = False
    if rdj.is_file():
        try:
            txt = rd(rdj)
            ok = ("speculative_decoding" in txt) and ("draft_model_id" in txt)
        except Exception:
            pass
    else:
        note(rdj)
    rec("G111", ok, "speculative metadata shape present" if ok else "speculative_decoding/draft fields absent from registry dump")

def g112():
    gp = art("9h", "no-speculative-execution.txt")
    hits = grep_tree(["modules/sow/scheduler"], "speculative", exclude=("test",))
    rec("G112", gp.is_file() and (not hits), "metadata only; no speculative execution" if (gp.is_file() and not hits) else "grep-proof:%s execution hits:%s" % (gp.is_file(), hits[:2]))

def g113():
    nv = art("9h", "nvfp4-descriptor.txt")
    ok = nv.is_file() and ("nvfp4" in rd(nv).lower())
    rec("G113", ok, "NVFP4 describable, no deploy requirement" if ok else "nvfp4-descriptor.txt absent")

def g114():
    rl = art("9h", "nvfp4-research-lane.txt")
    ok = rl.is_file()
    if ok:
        t = rd(rl).upper()
        ok = ("RESEARCH" in t) or ("NOT_RUN" in t)
        ok = ok and ("CANDIDATE" not in t.replace("NOT_REACHED", ""))
    rec("G114", ok, "research lane isolated or validly not run" if ok else "research-lane artifact absent/leaky")

def g115():
    ok, why = gate_cand("9h"); rec("G115", ok, why)

# ---------------- Band 20 (Gate 9j) ----------------
def g116():
    tr = suite_ok("evidence/test-run.txt", 1)
    bm = bm_equal()
    pr = [] if tr[0] else ["suite " + tr[1]]
    inv = art("9j", "invariants-reproved.txt")
    if not inv.is_file():
        note(inv); pr.append("9j/invariants-reproved.txt absent")
    dark, light = css_blocks()
    if any(dark.get(k, "").lower() != v for k, v in V3.items()): pr.append(":root drifted")
    rec("G116", not pr, "regression clean" if not pr else "; ".join(pr))

def g117():
    fw = art("fs-watch-cpm1.txt")
    if not fw.is_file():
        note(fw); return rec("G117", False, "replacement fs-watch artifact absent (window still open?)")
    t = rd(fw)
    events0 = "events: 0" in t
    four = all(r in t for r in ("Product Software", "multi model terminal app", "Sovereign Distillery", "Sov 1"))
    tp = "deliberately excluded" in t
    pm = art("9j", "protected-manifests-clean.txt")
    clean = pm.is_file() and rd(pm).lower().count("no differences") >= 5
    rec("G117", events0 and four and tp and clean, "window closed events:0 over four roots; five manifests clean" if (events0 and four and tp and clean) else "events0:%s four-roots:%s tb-excluded:%s manifests-clean:%s" % (events0, four, tp, clean))

def g118():
    rb = art("9j", "rollback.txt")
    ok = rb.is_file()
    if ok:
        t = rd(rb).lower()
        ok = ("ollama" in t) and (("generat" in t) or ("inference" in t) or ("response" in t))
    rec("G118", ok, "rollback demonstrated, Ollama operational" if ok else "rollback.txt absent/incomplete")

def g119():
    av = art("9j", "adversarial-review.txt")
    ok = av.is_file()
    if ok:
        t = rd(av).lower()
        cats = ["duplicate architecture", "hardcoded model", "vendor routing", "silent fallback", "fake residency",
                "fake context", "new lifecycle states", "remote-host leakage", "provider-spend leakage",
                "parallel logging", "schema drift", "ollama regression"]
        listed = sum(1 for c in cats if c in t)
        ok = listed >= 10 and ("zero" in t)
    rec("G119", ok, "adversarial review finds zero instances" if ok else "adversarial-review.txt absent/thin")

def g120():
    dc = art("9j", "diff-classification.txt")
    ok = dc.is_file()
    if ok:
        m = re.search(r"UNEXPECTED[^0-9]*(\d+)", rd(dc))
        ok = bool(m) and int(m.group(1)) == 0
    rec("G120", ok, "every changed file classified; UNEXPECTED=0" if ok else "diff-classification.txt absent/UNEXPECTED!=0")

def g121():
    la = linecount_within("linecount-a.txt", CAPS_A, ABS_A)
    lb = linecount_within("linecount-b.txt", CAPS_B, ABS_B)
    rec("G121", la[0] and lb[0], "both envelopes honoured separately" if (la[0] and lb[0]) else "A:%s B:%s" % (la[1], lb[1]))

def g122():
    fe = art("9j", "FINAL-EVIDENCE-MANIFEST.json")
    ok = fe.is_file()
    if ok:
        try:
            j = json.loads(rd(fe))
            blob = json.dumps(j)
            ok = all(k in blob for k in ("tests_executed", "tests_passed", "tests_failed", "modified_files", "known_limitations"))
        except Exception:
            ok = False
    rec("G122", ok, "final evidence manifest complete incl failed-test count" if ok else "FINAL-EVIDENCE-MANIFEST.json absent/incomplete")

def g123():
    busy = [p for p in (5175, 8700, 5180, 5183) if popen(p)]
    e5 = popen(8765)
    oc = art("9j", "closeout-ports.txt")
    doc = rd(oc).lower() if oc.is_file() else ""
    ok = (not busy) and ((not e5) or (("8765" in doc) and ("external" in doc)))
    rec("G123", ok, "nothing running; 5183 free; externals documented" if ok else "busy:%s 8765-external-doc:%s" % (busy or "none", e5))

SNAP = WS / "evidence" / "cpm1" / "ledger-snapshot-verified.json"

def ledger_snapshot_ok():
    """E-2/E-3 repair: compare the FULL gate object for all twelve historical keys
    (0,1,2,3,4,4b,4c,5,5b,6,7a,7b) against the verified post-repair snapshot -
    status, evidence set, evaluated_by, reviewer_note, utc, basis, authorized_by,
    superseded_ledger_sha256 and every other field. Returns (ok, why, fields)."""
    TWELVE = ("0", "1", "2", "3", "4", "4b", "4c", "5", "5b", "6", "7a", "7b")
    if not SNAP.is_file():
        note(SNAP)
        return False, "ledger-snapshot-verified.json absent", []
    try:
        snap = json.loads(rd(SNAP))
    except Exception as e:
        return False, "snapshot unparsable %s" % e, []
    cur_led = ledger()
    bad_fields = []
    for k in TWELVE:
        s = snap.get("gates", {}).get(k)
        c = cur_led.get("gates", {}).get(k)
        if s is None:
            bad_fields.append(k + ":missing-in-snapshot")
            continue
        if c is None:
            bad_fields.append(k + ":missing-in-ledger")
            continue
        sj = json.dumps(s, sort_keys=True, ensure_ascii=False)
        cj = json.dumps(c, sort_keys=True, ensure_ascii=False)
        if sj == cj:
            continue
        keys = sorted(set(list(s.keys()) + list(c.keys())))
        for f in keys:
            fv_s = json.dumps(s.get(f), sort_keys=True, ensure_ascii=False) if f in s else "<absent>"
            fv_c = json.dumps(c.get(f), sort_keys=True, ensure_ascii=False) if f in c else "<absent>"
            if fv_s != fv_c:
                bad_fields.append("%s.%s" % (k, f))
        if not any(b.startswith(k + ".") for b in bad_fields):
            bad_fields.append(k + ":<value-drift>")
    return (not bad_fields), ("gates 0-7b full-entry faithful to verified snapshot"
                              if not bad_fields else "; ".join(bad_fields[:8])), bad_fields


def g124():
    ok, why = gate_cand("9j")
    rp = WS / "docs" / "CP-M1-REPORT.md"
    partB = False
    if rp.is_file():
        t = rd(rp)
        partB = ("Part B" in t) and ("BUILDER CLAIM:" in t) and ("parity matrix" in t.lower())
    unchanged, why_u, _fields_u = ledger_snapshot_ok()
    rec("G124", ok and partB and unchanged, "gate 9j CANDIDATE; Part B done; gates 0-7b untouched" if (ok and partB and unchanged) else "gate:%s partB:%s early-gates-changed:%s" % (why, partB, (ledger_snapshot_ok()[2] or ['none'])))

FUNCS = [g1, g2, g3, g4, g5, g6, g7, g8, g9, g10, g11, g12, g13, g14, g15, g16, g17, g18, g19, g20,
         g21, g22, g23, g24, g25, g26, g27, g28, g29, g30, g31, g32, g33, g34, g35, g36, g37, g38,
         g39, g40, g41, g42, g43, g44, g45, g46, g47, g48, g49, g50, g51, g52, g53, g54, g55, g56,
         g57, g58, g59, g60, g61, g62, g63, g64, g65, g66, g67, g68, g69, g70, g71, g72, g73, g74,
         g75, g76, g77, g78, g79, g80, g81, g82, g83, g84, g85, g86, g87, g88, g89, g90, g91, g92,
         g93, g94, g95, g96, g97, g98, g99, g100, g101, g102, g103, g104, g105, g106, g107, g108,
         g109, g110, g111, g112, g113, g114, g115, g116, g117, g118, g119, g120, g121, g122, g123, g124]

def main():
    seq = 1
    others = list(M1.glob("goalcheck-*.txt"))
    if others:
        seq = max(int(re.findall(r"(\d+)", p.stem)[0]) for p in others) + 1
    # E-3: the ledger guard runs FIRST on every iteration, before any goal is read,
    # so a faithless ledger can never yield a TRUE anywhere.
    guard_ok, guard_why, guard_fields = ledger_snapshot_ok()
    for fn in FUNCS:
        gid = "G" + fn.__name__[1:]
        CUR[0] = gid
        READS.clear()
        try:
            fn()
        except Exception as e:
            RES.append((gid, False, "ORACLE-ERROR %s: %r" % (fn.__name__, e), sorted(READS)))
        CUR[0] = None
    nt = sum(1 for _g, o, _w, _r in RES if o)
    lines = ["# utc: " + datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
             "# producer: ox-alpha CP-M1 oracle",
             "GUARD: " + ("OK - full-entry faithful (E-2)" if guard_ok else "FAIL " + guard_why),
             "GUARD-FIELDS: " + (",".join(guard_fields) if guard_fields else "(none)"), ""]
    if not guard_ok:
        lines += ["summary: GUARD-FAIL - no goal evaluated"]
        out = art("goalcheck-%d.txt" % seq)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 3
    for g, o, w, reads in RES:
        lines.append("%s: %s  %s" % (g, "TRUE" if o else "FALSE", w))
        lines.append("read: " + (", ".join(reads) if reads else "(none)"))
    lines += ["", "summary: %d/%d TRUE" % (nt, len(RES))]
    out = art("goalcheck-%d.txt" % seq)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0

if __name__ == "__main__":
    sys.exit(main())
