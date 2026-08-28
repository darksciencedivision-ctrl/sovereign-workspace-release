"""Scoped resync v3: text-scan per builder-gate-block."""
import hashlib, json, re
from pathlib import Path
LED = Path(r"D:\Product Software\Production Workspace\evidence\GATE-LEDGER.json")
WS = LED.parents[1]
KEYS = ["8a", "8b", "8c"]
MUTABLE = {"shell/BUILD-MANIFEST.txt", "evidence/cpm1/linecount-a.txt",
           "evidence/cpm1/LOOP-LEDGER.jsonl"}

def sha(b): return hashlib.sha256(b).hexdigest()
def sha_file(p):
    h = hashlib.sha256()
    with open(p,"rb") as f:
        for c in iter(lambda: f.read(65536), b""): h.update(c)
    return h.hexdigest()

raw = LED.read_bytes(); pre = sha(raw)
text = raw.decode("utf-8")
idxs = []
for k in KEYS:
    i = text.index('"%s": {' % k)
    idxs.append((k, i))
idxs.sort(key=lambda x: x[1])
spans = []
for gi,(k,i) in enumerate(idxs):
    end = idxs[gi+1][1] if gi+1 < len(idxs) else len(text)
    spans.append((k, i, end))
report = []
out_parts = []
last = 0
for (k, start, end) in spans:
    seg = text[last:start]          # untouched gap
    out_parts.append(seg); last = start
    seg = text[start:end]
    for rel in sorted(MUTABLE):
        pat = re.compile(r'("path": "'+re.escape(rel)+r'",(\s*)"sha256": ")([0-9a-f]{64})(")')
        hits = list(pat.finditer(seg))
        if len(hits) > 1: raise SystemExit("ambiguous %s in %s" % (rel,k))
        if not hits: continue
        cur = sha_file(WS / rel)
        m = hits[0]
        if m.group(3) != cur:
            seg = seg[:m.start(3)] + cur + seg[m.end(3):]
            report.append((k, rel, m.group(3)[:8], cur[:8]))
    out_parts.append(seg); last = end
out_parts.append(text[last:])
new_text = "".join(out_parts)
json.loads(new_text)
if sha(LED.read_bytes()) != pre: raise SystemExit("changed mid-run")
LED.write_bytes(new_text.encode("utf-8"))
print("resync v3 done; pre", pre[:12], "-> post", sha(new_text.encode())[:12])
for r in report: print("  refreshed:", r)