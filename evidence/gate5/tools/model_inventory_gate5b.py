"""Fresh Ollama tag check for the Gate 5 visual re-run (read-only).

Mirrors evidence/gate5/model-inventory.txt (2026-08-21) so this run's SOVEREIGN outcome can be
interpreted against CURRENT reachability, per the Gate 5 directive B-table. Writes
evidence/gate5/model-inventory-gate5b.txt.
"""
import json
import urllib.request
from datetime import datetime, timezone
import os

WS = r"D:\Product Software\Production Workspace"
OUT = os.path.join(WS, "evidence", "gate5", "model-inventory-gate5b.txt")
manifest = json.load(open(os.path.join(WS, "modules", "sovereign", "SYSTEM_MANIFEST.json"),
                          encoding="utf-8-sig"))
required = manifest["MODELS"]
with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=10) as r:
    tags = sorted(m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", []))
lines = [
    "# utc: {}".format(datetime.now(timezone.utc).isoformat()),
    "# producer: ox-alpha GATE5B",
    "# source: modules/sovereign/SYSTEM_MANIFEST.json MODELS vs "
    "GET http://127.0.0.1:11434/api/tags (read-only)",
    "# installed_tags_count: {}".format(len(tags)),
    "",
]
present = 0
for role in ["PRIMARY_REASONER", "ADVERSARIAL_CHALLENGER", "CRITIC", "SYNTHESIZER",
             "EMBEDDING_MODEL"]:
    tag = required[role]
    ok = tag in tags
    present += 1 if ok else 0
    lines.append("{}\t{}\t{}".format(role, tag, "PRESENT" if ok else "MISSING"))
lines.append("")
lines.append("summary: {} required, {} PRESENT, {} MISSING".format(
    len(required), present, len(required) - present))
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines[-2:]))
