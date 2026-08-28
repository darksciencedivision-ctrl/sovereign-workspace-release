"""Insert gate 8a into evidence/GATE-LEDGER.json textually, byte-preserving the prefix.
Throws unless: prefix bytes identical up to insertion, result parses as JSON, and the
pre-insertion hash equals the recorded session-start value."""
import hashlib, json, sys
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
LED = WS / "evidence" / "GATE-LEDGER.json"
KNOWN_GOOD = "176429fc4012ce57c1a19558e7aaed55e7f37ca268be0fdd067996fe79b8fc77"

def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()

def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()

paths = [
    "docs/CP-MAP-01.md",
    "evidence/cpm1/session-start.txt",
    "evidence/cpm1/spend-reconciliation.txt",
    "evidence/cpm1/baseline/git-head.txt",
    "evidence/cpm1/baseline/git-status.txt",
    "evidence/cpm1/baseline/git-head-2.txt",
    "evidence/cpm1/baseline/git-status-2.txt",
    "evidence/cpm1/baseline/sow-quiescence.txt",
    "evidence/cpm1/baseline/host-hardware.json",
    "evidence/cpm1/baseline/runtime-inventory.json",
    "evidence/cpm1/baseline/runtime-inventory.supersedes.txt",
    "evidence/cpm1/baseline/ollama-version.txt",
    "evidence/cpm1/baseline/ollama-model-list.json",
    "evidence/cpm1/baseline/schema-hashes.json",
    "evidence/cpm1/baseline/ports.txt",
    "evidence/cpm1/baseline/processes.txt",
    "evidence/cpm1/baseline/port-8765-owner.txt",
    "evidence/cp01/manifests/manifest-cp01-before-token-piggy-bank.excl-data.txt",
    "evidence/cp01/manifests/SUPERSEDE-token-piggy-bank-excl-data.txt",
    "evidence/cpm1/fs-watch-adoption.txt",
    "evidence/cpm1/fs-watch-cpm1.supersedes.txt",
    "evidence/cpm1/fs-watch-incidental-stall-window.txt",
    "evidence/cpm1/single-writer.txt",
    "evidence/cpm1/g8-snapshot-1.txt",
    "evidence/cpm1/g8-snapshot-2.txt",
    "evidence/cpm1/test-run-before.txt",
    "evidence/cpm1/build-manifest-equality.txt",
    "evidence/cpm1/root-v3-check.txt",
    "evidence/cpm1/before-a/HASHES.txt",
    "evidence/cpm1/tools/goalcheck.py",
    "evidence/cpm1/tools/fswatch_driver_cpm1.py",
    "evidence/cpm1/LOOP-LEDGER.jsonl",
]
for p in paths:
    if not (WS / p).is_file():
        raise SystemExit("missing evidence path: %s" % p)

gcs = sorted((WS / "evidence" / "cpm1").glob("goalcheck-*.txt"))
if not gcs:
    raise SystemExit("no goalcheck output found")
latest = gcs[-1]
rel_latest = str(latest.relative_to(WS)).replace("\\", "/")

evidence = [{"path": p, "sha256": sha_file(WS / p)} for p in paths]
evidence.append({"path": rel_latest, "sha256": sha_file(latest)})

entry = {
    "status": "CANDIDATE",
    "claimed_by": "builder",
    "evaluated_by": None,
    "authorized_by": ("operator session instruction logged verbatim in "
                      "evidence/OPERATOR-INSTRUCTIONS.log at 2026-08-25T08:44:56.2718135Z "
                      "(ADDENDUM-03 s7)"),
    "utc": sys.argv[1],
    "basis": "docs/OX-ALPHA-DIRECTIVE-CP-M1.md Band 1 (G9-G11)",
    "evidence": evidence,
    "note": ("Band 1 read-only implementation map: docs/CP-MAP-01.md carries 34 verified "
             "FACT[path:line] citations across runtime-inventory topics; R-01..R-15 classified "
             "against this session's own disk reads; no divergence from settled facts S-1..S-12. "
             "Band 0 adopted/verified: five protected-root manifests on pinned tool sha256 "
             "64c488ed..5d22; A-1 token-piggy-bank re-capture excluding data/** with supersede "
             "note; SOW quiescence pair HEAD e6fcb899 identical >=60s; single-writer double-read "
             "0 diffs over 65s; Package-A baseline before-a/ 359 files hash-verified "
             "(node_modules/__pycache__ excluded, stated); README suite Ran 122 tests OK; "
             "shell/BUILD-MANIFEST.txt 40/40 equal live hashes; app.css tokens MATCH "
             "docs/THEME-BASELINE-v3.md both themes; fs-watch window operator-owned (C-4) over "
             "four roots incl D:\\Sov 1 since 16:30:43Z; oracle goalcheck.py covers G1-G124 under "
             "py -3.12 with per-goal read lists."),
}

raw = LED.read_bytes()
pre_hash = sha_bytes(raw)
if pre_hash != KNOWN_GOOD:
    raise SystemExit("ledger not at known-good state (%s); aborting" % pre_hash)
text = raw.decode("utf-8")
core = text.rstrip("\r\n")
idx = core.rfind("\n  }\n}")
if idx < 0:
    raise SystemExit("closing marker not found")
prefix = core[:idx]
if not prefix.endswith("    }\n"):
    raise SystemExit("unexpected prefix tail: %r" % prefix[-10:])
if sha_bytes((prefix + "\n  }\n}").encode("utf-8")) != KNOWN_GOOD:
    raise SystemExit("untouched-region reconstruction does not hash to known-good")
p2 = prefix[:-1]
body_lines = []
for i, line in enumerate(json.dumps(entry, indent=2, ensure_ascii=False).split("\n")):
    if i == 0:
        line = line.replace("{", "\"8a\": {", 1)
    body_lines.append(("    " + line) if line else "")
new_text = p2 + ",\n" + "\n".join(body_lines) + "\n\n  }\n}"
parsed = json.loads(new_text)
if parsed["gates"]["8a"]["status"] != "CANDIDATE":
    raise SystemExit("entry malformed")
if sha_bytes(raw) != KNOWN_GOOD:
    raise SystemExit("file changed mid-run")
LED.write_bytes(new_text.encode("utf-8"))
print("inserted; untouched region hash-verified against session-start known-good")
print("gates:", ", ".join(parsed["gates"].keys()))
print("8a evidence entries:", len(parsed["gates"]["8a"].get("evidence", [])))
print("ledger sha256 now:", sha_bytes(LED.read_bytes()))