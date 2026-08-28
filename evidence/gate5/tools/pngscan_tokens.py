"""Token-presence scan: count pixels within tolerance of THEME-BASELINE tokens."""
import sys
sys.path.insert(0, r"D:\Product Software\Production Workspace\evidence\gate5\tools")
from pngprobe import load

TOKENS = {
    "bg-light-f4f5f7": (244, 245, 247),
    "bg-dark-0e1116": (14, 17, 22),
    "panel-white-ffffff": (255, 255, 255),
    "sidebar-ecEEf1": (236, 238, 241),
    "border-d3d8e0": (211, 216, 224),
    "text-1b2027": (27, 32, 39),
    "accent-8a744a": (138, 116, 74),
    "accent-dim-a68b58": (166, 139, 88),
    "ok-6ac98a": (106, 201, 138),
    "warning-d0aa62": (208, 170, 98),
    "danger-c96a6a": (201, 106, 106),
}
TOL = 3
for path in sys.argv[1:]:
    w, h, bpp, buf = load(path)
    counts = {k: 0 for k in TOKENS}
    for i in range(0, len(buf), bpp):
        r, g, b = buf[i], buf[i+1], buf[i+2]
        for k, (tr, tg, tb) in TOKENS.items():
            if abs(r-tr) <= TOL and abs(g-tg) <= TOL and abs(b-tb) <= TOL:
                counts[k] += 1
    print(path.split("\\")[-1])
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print("  %-22s %8d" % (k, v))
