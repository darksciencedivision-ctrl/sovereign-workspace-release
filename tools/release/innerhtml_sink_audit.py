#!/usr/bin/env python
"""innerHTML sink audit scanner — SWS-REM-DIR-20260828 R2, B2-4 (M-3).

Scope (explicit, no globs):

1. Every ``.innerHTML =`` assignment in the audited file — the scanner walks
   each right-hand expression (paren/bracket/brace/string/template aware, so
   templates inside ``.map(...)`` callbacks count) and classifies every
   ``${...}`` interpolation in every template it reaches.
2. CONSTRUCTION SITES named in the ledger's ``construction_fragments`` —
   templates that do not sit inside an innerHTML RHS but whose content is
   later assigned to one (e.g. the ``interruptedNotice`` builder), and the
   row-builder templates those sinks concatenate. A template is in scope iff
   it contains one of the enumerated literal fragments.

Classification of each interpolation:

  ESCAPED       wrapped in esc(...)
  GUARANTEED    pure numeric literal or ``.length`` (language-guaranteed int)
  COMPOSITE     embeds nested template literals — leaf interpolations are
                scanned in their own right
  MUST-JUSTIFY  anything else: needs a ledger ``justifications`` entry naming
                its class (STATIC / ESCAPED-BY-CONSTRUCTION) and the
                byte-level reason it cannot inject markup

Exit codes: 0 every interpolation safe or justified; 1 unjustified
interpolations remain; 2 usage error. Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------- lexing ---

def _skip_string(src: str, i: int, quote: str) -> int:
    i += 1
    n = len(src)
    while i < n:
        if src[i] == "\\":
            i += 2
            continue
        if src[i] == quote:
            return i + 1
        i += 1
    return i


def _skip_regex(src: str, i: int) -> int:
    i += 1
    n = len(src)
    in_class = False
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            i += 1
            while i < n and src[i].isalpha():
                i += 1
            return i
        elif c == "\n":
            return i
        i += 1
    return i


REGEX_PRECEDING = set("(,=:[!&|?{};+-*%<>~^")


def _scan_template(src: str, i: int, collector: list) -> int:
    start = i
    i += 1
    n = len(src)
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            collector.append((start, i, src[start:i + 1]))
            return i + 1
        if c == "$" and i + 1 < n and src[i + 1] == "{":
            i = _skip_interp(src, i + 2, collector)
            continue
        i += 1
    collector.append((start, n, src[start:n]))
    return n


def _skip_interp(src: str, i: int, collector: list) -> int:
    depth = 1
    n = len(src)
    while i < n and depth:
        c = src[i]
        if c == "{":
            depth += 1
            i += 1
            continue
        if c == "}":
            depth -= 1
            i += 1
            continue
        if c in ("'", '"'):
            i = _skip_string(src, i, c)
            continue
        if c == "`":
            i = _scan_template(src, i, collector)
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        i += 1
    return i


def _skip_comment_or_regex(src: str, i: int, last_significant: str):
    """Returns new index, or None if no comment/regex starts here."""
    c = src[i]
    n = len(src)
    if c == "/" and i + 1 < n and src[i + 1] == "/":
        j = src.find("\n", i)
        return n if j < 0 else j
    if c == "/" and i + 1 < n and src[i + 1] == "*":
        j = src.find("*/", i + 2)
        return n if j < 0 else j + 2
    if c == "/" and last_significant in REGEX_PRECEDING:
        return _skip_regex(src, i)
    return None


def lex_templates(src: str) -> list:
    """All template literals (nested included) as (start, end_incl, text)."""
    templates = []
    i, n = 0, len(src)
    last_significant = ""
    while i < n:
        c = src[i]
        if c == "'":
            i = _skip_string(src, i, "'")
            last_significant = "'"
            continue
        if c == '"':
            i = _skip_string(src, i, '"')
            last_significant = '"'
            continue
        if c == "`":
            i = _scan_template(src, i, templates)
            last_significant = "`"
            continue
        skip = _skip_comment_or_regex(src, i, last_significant)
        if skip is not None:
            i = skip
            last_significant = "/"
            continue
        if not c.isspace():
            last_significant = c
        i += 1
    return templates


def top_level_interpolations(template_text: str) -> list:
    assert template_text.startswith("`") and template_text.endswith("`")
    body = template_text[1:-1]
    out = []
    i, n = 0, len(body)
    while i < n:
        if body[i] == "\\":
            i += 2
            continue
        if body[i] == "$" and i + 1 < n and body[i + 1] == "{":
            depth = 1
            j = i + 2
            while j < n and depth:
                cj = body[j]
                if cj == "\\":
                    j += 2
                    continue
                if cj == "{":
                    depth += 1
                elif cj == "}":
                    depth -= 1
                elif cj in ("'", '"'):
                    # quote inside the interpolation: skip its string
                    k = j + 1
                    while k < n:
                        if body[k] == "\\":
                            k += 2
                            continue
                        if body[k] == cj:
                            break
                        k += 1
                    j = k
                elif cj == "`":
                    k = j + 1
                    nd = 0
                    while k < n:
                        if body[k] == "\\":
                            k += 2
                            continue
                        if body[k] == "`" and nd == 0:
                            break
                        if body[k] == "$" and k + 1 < n and body[k + 1] == "{" and nd == 0:
                            nd += 1
                            k += 2
                            continue
                        if nd and body[k] == "}":
                            nd -= 1
                        k += 1
                    j = k
                j += 1
            out.append(body[i + 2:j - 1])
            i = j
            continue
        i += 1
    return out


# ------------------------------------------------------------- classify ---

NUM_RE = re.compile(r"^\d+(\.\d+)?$")


def classify(expr: str) -> str:
    e = " ".join(expr.split())
    if "`" in e:
        return "COMPOSITE"
    if e.startswith("esc("):
        return "ESCAPED"
    if NUM_RE.match(e) or e.endswith(".length"):
        return "GUARANTEED"
    return "MUST-JUSTIFY"


def line_of(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


# ---------------------------------------------------------------- scope ---

def innerhtml_rhs_templates(src: str, templates: list) -> set:
    """Template indices reached by any `.innerHTML =` right-hand side."""
    reached = set()
    for m in re.finditer(r"\.innerHTML\s*=", src):
        i = m.end()
        n = len(src)
        depth = 0
        end = n
        last_sig = "="
        while i < n:
            c = src[i]
            if c in "([{":
                depth += 1
                i += 1
                last_sig = c
                continue
            if c in ")]}":
                depth -= 1
                i += 1
                last_sig = c
                continue
            if depth == 0 and c == ";":
                end = i
                break
            if c in ("'", '"'):
                i = _skip_string(src, i, c)
                last_sig = c
                continue
            if c == "`":
                # template on the RHS: find its lexed span
                i = _scan_template(src, i, [])
                last_sig = "`"
                continue
            skip = _skip_comment_or_regex(src, i, last_sig)
            if skip is not None:
                i = skip
                last_sig = "/"
                continue
            if not c.isspace():
                last_sig = c
            i += 1
        for idx, (start, _, _) in enumerate(templates):
            if m.end() <= start < end:
                reached.add(idx)
    return reached


def construction_templates(src: str, templates: list, fragments: list) -> set:
    hit = set()
    for idx, (_, _, text) in enumerate(templates):
        if any(frag in text for frag in fragments):
            hit.add(idx)
    return hit


# ----------------------------------------------------------------- scan ---

def scan(src: str, ledger: dict) -> dict:
    templates = lex_templates(src)
    fragments = ledger.get("construction_fragments", [])
    justifications = ledger.get("justifications", {})
    scope = innerhtml_rhs_templates(src, templates) | \
        construction_templates(src, templates, fragments)
    # Scope closure: a template lexically nested inside an in-scope template
    # is in scope too (its interpolations reach the same sink).
    changed = True
    while changed:
        changed = False
        for idx, (start, end, _) in enumerate(templates):
            if idx in scope:
                continue
            for pidx in scope:
                pstart, pend, _ = templates[pidx]
                if pstart < start and end < pend:
                    scope.add(idx)
                    changed = True
                    break

    results = []
    for idx in sorted(scope):
        start, _, text = templates[idx]
        base_line = line_of(src, start)
        for expr in top_level_interpolations(text):
            cls = classify(expr)
            entry = {"line": base_line,
                     "expr": " ".join(expr.split())[:200],
                     "class": cls}
            if cls == "MUST-JUSTIFY":
                just = justifications.get(" ".join(expr.split()))
                if just and just.get("class") and just.get("reason"):
                    entry["class"] = just["class"]
                    entry["justification"] = just["reason"]
                else:
                    entry["unjustified"] = True
            results.append(entry)
    return {
        "gate": "innerhtml_sink_audit",
        "directive": "SWS-REM-DIR-20260828 R2 / B2-4 (M-3)",
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "templates_in_scope": len(scope),
        "interpolations": results,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="innerHTML interpolation audit")
    ap.add_argument("--file", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            src = f.read()
    except OSError as exc:
        print(f"innerhtml_sink_audit: cannot read {args.file}: {exc}",
              file=sys.stderr)
        return 2
    try:
        with open(args.ledger, "r", encoding="utf-8") as f:
            ledger = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"innerhtml_sink_audit: cannot read ledger: {exc}",
              file=sys.stderr)
        return 2

    report = scan(src, ledger)
    bad = [r for r in report["interpolations"] if r.get("unjustified")]
    report["verdict"] = "FAIL" if bad else "PASS"
    report["unjustified_count"] = len(bad)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        counts = {}
        for r in report["interpolations"]:
            counts[r["class"]] = counts.get(r["class"], 0) + 1
        print(f"innerhtml_sink_audit: {report['verdict']} "
              f"(templates_in_scope={report['templates_in_scope']}, "
              f"interpolations={len(report['interpolations'])} {counts})")
        for r in bad:
            print(f"  UNJUSTIFIED line ~{r['line']}: {r['expr']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
