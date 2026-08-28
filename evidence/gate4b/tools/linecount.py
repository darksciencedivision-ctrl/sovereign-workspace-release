"""Gate 4b line counting (REM-02 envelope): unified_diff added+removed per touched file,
against the rolling prev/ snapshot (this defect's increment) and the frozen before/
(cumulative envelope usage). Appends a dated block to evidence/gate4b/linecount.txt.

Usage: py -3.12 linecount.py <DEFECT-ID> <relfile> [<relfile> ...]
relfile is workspace-relative, e.g. shell/static/index.html
"""
import difflib
import os
import sys
from datetime import datetime, timezone

WS = r"D:\Product Software\Production Workspace"
OUT = os.path.join(WS, "evidence", "gate4b", "linecount.txt")
BEFORE = os.path.join(WS, "evidence", "gate4b", "before")
PREV = os.path.join(WS, "evidence", "gate4b", "prev")


def counts(old, new):
    a = open(old, encoding="utf-8-sig").read().splitlines(keepends=True)
    b = open(new, encoding="utf-8-sig").read().splitlines(keepends=True)
    d = list(difflib.unified_diff(a, b, fromfile=old, tofile=new))
    add = sum(1 for l in d if l.startswith("+") and not l.startswith("+++"))
    rem = sum(1 for l in d if l.startswith("-") and not l.startswith("---"))
    return add, rem


def read_existing_total():
    if not os.path.exists(OUT):
        return 0
    total = 0
    with open(OUT, encoding="utf-8-sig") as f:
        for line in f:
            if line.startswith("# cumulative-total:"):
                total = int(line.rsplit(":", 1)[1].strip())
    return total


def main():
    defect = sys.argv[1]
    rels = sys.argv[2:]
    prev_total = read_existing_total()
    stamp = datetime.now(timezone.utc).isoformat()
    blocks = []
    grand_inc = 0
    if not os.path.exists(OUT):
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            f.write("# utc: {}\n".format(stamp))
            f.write("# producer: ox-alpha GATE4B\n")
            f.write("# method: difflib.unified_diff over before/(frozen baseline) and "
                    "prev/(rolling); changed = added + removed\n")
    else:
        blocks.append("")
        blocks.append("----")
        blocks.append("# utc: {}".format(stamp))
    blocks.append("# defect: {}".format(defect))
    for rel in rels:
        name = os.path.basename(rel)
        live = os.path.join(WS, rel)
        p_old = os.path.join(PREV, name)
        b_old = os.path.join(BEFORE, name)
        ia, ir = counts(p_old, live)
        ca, cr = counts(b_old, live)
        grand_inc += ia + ir
        blocks.append("{}: increment +{}/-{} = {}; cumulative-vs-before +{}/-{} = {} "
                      "(envelope cap 80)".format(rel, ia, ir, ia + ir, ca, cr, ca + cr))
        import shutil
        shutil.copyfile(live, os.path.join(PREV, name))
    total = prev_total + grand_inc
    blocks.append("# cumulative-total: {}".format(total))
    with open(OUT, "a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(blocks) + "\n")
    print("defect {} increment={} total={}".format(defect, grand_inc, total))
    if total > 80:
        print("ENVELOPE BREACH")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
