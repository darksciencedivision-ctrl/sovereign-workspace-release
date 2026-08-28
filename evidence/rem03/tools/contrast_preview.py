"""REM-03 T3 pre-flight: compute H-16's six C-2 pairs for the PROPOSED v2 dark tokens
(SOW-verbatim) with the light block carried forward unchanged. READ-ONLY: app.css is NOT
modified by this tool. Same formula as shell/tests/test_render.py (_ratio/_tokens)."""
import os
import re
from datetime import datetime, timezone

WS = r"D:\Product Software\Production Workspace"
SOW_HTML = (r"D:\multi model terminal app\sovereign-orchestration-workspace"
            r"\apps\desktop\renderer\index.html")

def lum(hexstr):
    h = hexstr.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = lin(r), lin(g), lin(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)

# proposed v2 dark tokens: SOW-verbatim mapping (see extraction notes)
V2_DARK = {
    "--bg": "#0b0e14",        # SOW body background            index.html:10
    "--panel": "#151b28",     # SOW card/railcard/chip surface index.html:18
    "--sidebar": "#0d121c",   # SOW rail/statusbar             index.html:25
    "--input": "#1b2333",     # SOW button/control surface     index.html:13
    "--border": "#232b3a",    # SOW universal border           index.html:11
    "--text": "#c7d1de",      # SOW body text                  index.html:10
    "--text-muted": "#6b7687",# SOW .k/.dim/sb-label           index.html:19
    "--text-faint": "#3a4353",# SOW .rail-empty                index.html:31
    "--accent": "#bb9af7",    # SOW conductor violet           index.html:37,41
    "--accent-dim": "#3a2f57",# SOW conductor badge border     index.html:41
    "--ok": "#9ece6a",        # SOW chip/state green           index.html:20,77,91
    "--warning": "#e0af68",   # SOW amber                      index.html:93,121,186
    "--danger": "#f7768e",    # SOW red                        index.html:15,78,185
}
LIGHT = {"--bg": "#f4f5f7", "--panel": "#ffffff", "--sidebar": "#eceef1",
         "--border": "#d3d8e0", "--text": "#1b2027", "--text-muted": "#58616e",
         "--text-faint": "#8a93a1", "--accent": "#8a744a", "--accent-dim": "#a68b58"}

pairs = [("text", "bg"), ("text", "panel"), ("text-muted", "panel"),
         ("ok", "panel"), ("warning", "panel"), ("danger", "panel")]
lines = ["# utc: {}".format(datetime.now(timezone.utc).isoformat()),
         "# producer: ox-alpha REM03",
         "# READ-ONLY contrast preview of the proposed SOW-verbatim v2 dark tokens against",
         "# H-16's six C-2 pairs (shell/tests/test_render.py:322). app.css was NOT modified.",
         "# Dark theme: text-position pairs need >= 4.5:1 (--ok/--warning/--danger are",
         "# text-position in dark: app.css:266-268 has no dark override).",
         ""]
for theme, eff in (("dark", dict(V2_DARK)), ("light", {**V2_DARK, **LIGHT})):
    for a, b in pairs:
        r = ratio(eff["--" + a], eff["--" + b])
        kind = "TEXT>=4.5" if a in ("text", "text-muted") else \
               ("TEXT>=4.5(dark)" if theme == "dark" else "GLYPH>=3.0")
        flag = ""
        if kind.startswith("TEXT"):
            flag = "OK" if r >= 4.5 else "FAIL (<4.5)"
        else:
            flag = "recorded; " + ("OK" if r >= 3.0 else "<3:1 decorative-dot risk")
        lines.append("{:<5} --{:<10} on --{:<5} = {:>6.2f}:1  {:<14} {}".format(
            theme, a, b, r, kind, flag))
    lines.append("")
with open(os.path.join(WS, "evidence", "rem03", "contrast-preview.txt"), "w",
          encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))
