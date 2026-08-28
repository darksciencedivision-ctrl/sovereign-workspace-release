"""CP-M1 changed-line counter v2. difflib added+removed vs before-<pkg>/, tests excluded."""
import difflib, sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
PKG = sys.argv[1] if len(sys.argv) > 1 else "a"
BASE = WS / "evidence" / "cpm1" / ("before-" + PKG)
OUT = WS / "evidence" / "cpm1" / ("linecount-" + PKG + ".txt")

def area(name, cap, base_sub, live_paths, exclude_parts=()):
    return {"name": name, "cap": cap,
            "base": BASE / base_sub if base_sub else None,
            "live": [Path(p) for p in live_paths],
            "excl": exclude_parts}

AREAS = ([area("shell/src", 320, "shell/src", [WS/"shell"/"src"]),
          area("shell/static", 300, "shell/static", [WS/"shell"/"static"]),
          area("shell/modules", 140, "shell/modules", [WS/"shell"/"modules"]),
          area("sow-desktop", 700, "modules/sow/apps/desktop",
               [WS/"modules"/"sow"/"apps"/"desktop"], ("test",)),
          area("sow-control-plane", 400, None,
               [WS/"modules"/"sow"/"control_plane", WS/"modules"/"sow"/"adapters",
                WS/"modules"/"sow"/"node_runtime", WS/"modules"/"sow"/"mcp_server",
                WS/"modules"/"sow"/"schemas"]),
          area("distillery", 500, None, [WS/"modules"/"distillery"]),
          area("tokencenter", 60, None, [WS/"modules"/"tokencenter"])]
         if PKG == "a" else
         [area("sow-adapters", 450, "modules/sow/adapters", [WS/"modules"/"sow"/"adapters"]),
          area("sow-scheduler", 200, "modules/sow/scheduler", [WS/"modules"/"sow"/"scheduler"]),
          area("sow-control+schemas", 500, None,
               [WS/"modules"/"sow"/"control_plane", WS/"modules"/"sow"/"schemas"]),
          area("sow-tools+config", 150, None,
               [WS/"modules"/"sow"/"tools", WS/"modules"/"sow"/"config"]),
          area("shell", 220, "shell", [WS/"shell"]),
          area("llamacpp.json", 45, None, []),
          area("runtime", 60, None, [WS/"runtime"])])
ABS_CAP = 1850 if PKG == "a" else 1625

def nlines(p):
    try:
        with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []

def is_test(p, exclude_parts):
    parts = {x.lower() for x in p.parts}
    if "tests" in parts or "__pycache__" in parts or "node_modules" in parts:
        return True
    if any(x in parts for x in exclude_parts):
        return True
    return any(x.endswith(".test.js") for x in p.parts)

def spend(ar):
    base_files = {}
    if ar["base"] and ar["base"].is_dir():
        for f in ar["base"].rglob("*"):
            if f.is_file() and f.name != "HASHES.txt" and not is_test(f, ar["excl"]):
                base_files[f.relative_to(ar["base"]).as_posix()] = f
    matched = set()
    total = 0
    per_file = []
    for ld in ar["live"]:
        if not ld.is_dir():
            continue
        for f in ld.rglob("*"):
            if not f.is_file() or is_test(f, ar["excl"]) or "__pycache__" in f.parts:
                continue
            rel_posix = None
            if ar["base"]:
                try:
                    rel_posix = f.relative_to(ld).as_posix()
                except ValueError:
                    continue
                bp = ar["base"] / rel_posix
            else:
                bp = None
            live_lines = nlines(f)
            n = 0
            if bp is not None and bp.is_file():
                d = difflib.unified_diff(nlines(bp), live_lines, lineterm="")
                n = sum(1 for l in d if (l.startswith("+") and not l.startswith("+++"))
                        or (l.startswith("-") and not l.startswith("---")))
                matched.add(rel_posix)
            elif ar["name"] != "distillery" and ar["name"] != "tokencenter" and ar["name"] != "runtime" and ar["name"] != "llamacpp.json":
                n = 0 if bp is None else len(live_lines)
                if bp is None:
                    n = 0
            else:
                n = len(live_lines)
            if n:
                per_file.append((str(f.relative_to(WS)).replace("\\", "/"), n))
            total += n
    for rp, bf in sorted(base_files.items()):
        if rp in matched:
            continue
        total += len(nlines(bf))
    return total, sorted(per_file)
rows, grand = [], 0
for ar in AREAS:
    n, pf = spend(ar)
    grand += n
    rows.append((ar["name"], n, ar["cap"], pf))
lines = ["# utc: " + datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
         "# producer: ox-alpha CP-M1 linecount-%s (difflib vs before-%s/, tests excluded)" % (PKG, PKG), ""]
for name, n, cap, pf in rows:
    lines.append("%s | %d | %d" % (name, n, cap))
    for f, k in pf:
        lines.append("#   %s: %d" % (f, k))
lines.append(("TOTAL-A | %d | %d" if PKG == "a" else "TOTAL-B | %d | %d") % (grand, ABS_CAP))
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))