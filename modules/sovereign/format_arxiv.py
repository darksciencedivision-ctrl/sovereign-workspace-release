from __future__ import annotations

r"""
format_arxiv.py — SOVEREIGN Phase 9 (Deliverable 3/7)

Deterministic template formatting. No LLM call.

Input:  publication_queue\assembled\{session_id}.md
Output: publication_queue\formatted\{session_id}.tex

Parses the assembled markdown document and emits a LaTeX document structured
for arXiv submission. Sections mapped: abstract, introduction, methodology,
results, discussion, conclusion, references, provenance.

CLI: python format_arxiv.py --session SESSION_ID [--root <SOVEREIGN_ROOT>]
"""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sovereign_version import PRODUCT_VERSION

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODULE_NAME = "FORMAT_ARXIV"
SOVEREIGN_VERSION = PRODUCT_VERSION


def _role_models() -> dict[str, str]:
    """Role->model names for display, read from SYSTEM_MANIFEST.json (single source
    of truth). Defensive: never raises at format time; falls back to generic labels
    so a missing/malformed manifest cannot break document generation."""
    fallback = {
        "PRIMARY_REASONER": "(reasoner)",
        "ADVERSARIAL_CHALLENGER": "(challenger)",
        "CRITIC": "(critic)",
        "SYNTHESIZER": "(synthesizer)",
    }
    try:
        from system_manifest import load_system_manifest, model_name
        manifest = load_system_manifest()
        return {key: model_name(key, manifest) for key in fallback}
    except Exception:
        return fallback

# Known section name -> canonical key mapping
_SECTION_MAP: dict[str, str] = {
    "abstract":      "abstract",
    "introduction":  "introduction",
    "methodology":   "methodology",
    "methods":       "methodology",
    "method":        "methodology",
    "results":       "results",
    "result":        "results",
    "discussion":    "discussion",
    "conclusion":    "conclusion",
    "conclusions":   "conclusion",
    "references":    "references",
    "reference":     "references",
    "provenance":    "provenance",
}

# Section order for LaTeX output
_SECTION_ORDER = [
    "introduction",
    "methodology",
    "results",
    "discussion",
    "conclusion",
    "references",
    "provenance",
]

_SECTION_TITLES = {
    "introduction":  "Introduction",
    "methodology":   "Methodology",
    "results":       "Results",
    "discussion":    "Discussion",
    "conclusion":    "Conclusion",
    "references":    "References",
    "provenance":    "Provenance",
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(level: str, msg: str, log_path: Path | None) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    line = f"[{ts}] [{MODULE_NAME}] [{level}] {msg}"
    print(line, flush=True)
    if log_path is not None:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


def _info(msg: str, lp: Path | None) -> None:
    _log("INFO", msg, lp)


def _warn(msg: str, lp: Path | None) -> None:
    _log("WARN", msg, lp)


def _error(msg: str, lp: Path | None) -> None:
    _log("ERROR", msg, lp)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _paths(root: Path) -> dict[str, Path]:
    return {
        "assembled":  root / "publication_queue" / "assembled",
        "formatted":  root / "publication_queue" / "formatted",
        "log_file":   root / "logs" / "format_arxiv_log.txt",
    }


# ---------------------------------------------------------------------------
# Manifest reading (for metadata)
# ---------------------------------------------------------------------------

def _read_manifest(root: Path, session_id: str, lp: Path | None) -> dict[str, Any]:
    manifest_path = root / "publication_queue" / f"{session_id}_manifest.json"
    if not manifest_path.exists():
        _warn(f"Manifest not found: {manifest_path} — metadata will be minimal", lp)
        return {}
    try:
        raw = manifest_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        _warn(f"Cannot read manifest: {exc}", lp)
        return {}


# ---------------------------------------------------------------------------
# Markdown section parsing
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")


def _parse_sections(md_text: str, lp: Path | None) -> dict[str, str]:
    """
    Parse assembled markdown into canonical_key -> body_text.
    Special key: "_title" (document title from leading H1).
    Text before the first heading is stored under "preamble".
    Unknown section names are logged and stored under sanitized key.
    """
    lines = md_text.splitlines()
    sections: dict[str, str] = {}
    title: str = ""
    current_key: str = "preamble"
    current_lines: list[str] = []

    def _flush(key: str, body: list[str]) -> None:
        text = "\n".join(body).strip()
        if not text:
            return
        if key in sections:
            sections[key] = sections[key] + "\n\n" + text
        else:
            sections[key] = text

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            hashes = m.group(1)
            heading = m.group(2).strip()
            heading_lower = heading.lower()

            # Top-level H1 with no section mapping = document title
            if len(hashes) == 1 and heading_lower not in _SECTION_MAP:
                _flush(current_key, current_lines)
                current_lines = []
                title = heading
                current_key = "__after_title__"
                continue

            canonical = _SECTION_MAP.get(heading_lower)
            if canonical is None:
                canonical = re.sub(r"[^a-z0-9]+", "_", heading_lower).strip("_")
                _warn(f"Unknown section heading '{heading}' — stored as '{canonical}'", lp)

            _flush(current_key, current_lines)
            current_lines = []
            current_key = canonical
        else:
            current_lines.append(line)

    _flush(current_key, current_lines)
    sections["_title"] = title
    return sections


# ---------------------------------------------------------------------------
# LaTeX escaping
# ---------------------------------------------------------------------------

# Backslash must be escaped first to avoid double-escaping subsequent replacements.
_LATEX_ESCAPE_ORDER = ["\\", "{", "}", "&", "%", "$", "#", "_", "~", "^"]
_LATEX_ESCAPE_MAP: dict[str, str] = {
    "\\": r"\textbackslash{}",
    "{":  r"\{",
    "}":  r"\}",
    "&":  r"\&",
    "%":  r"\%",
    "$":  r"\$",
    "#":  r"\#",
    "_":  r"\_",
    "~":  r"\textasciitilde{}",
    "^":  r"\textasciicircum{}",
}


def _escape_latex(text: str) -> str:
    """Escape all LaTeX special characters in plain text."""
    for ch in _LATEX_ESCAPE_ORDER:
        text = text.replace(ch, _LATEX_ESCAPE_MAP[ch])
    return text


# ---------------------------------------------------------------------------
# Inline markdown -> LaTeX
# ---------------------------------------------------------------------------

# Matches bold (**x** / __x__), italic (*x* / _x_), inline code (`x`).
# Groups: 1=**bold**, 2=__bold__, 3=*italic*, 4=_italic_, 5=`code`
_INLINE_SPAN_RE = re.compile(
    r"\*\*(.+?)\*\*"
    r"|__(.+?)__"
    r"|\*(.+?)\*"
    r"|_(.+?)_"
    r"|`(.+?)`",
    re.DOTALL,
)


def _inline(text: str) -> str:
    """
    Convert inline markdown to LaTeX.
    Plain text segments are escaped via _escape_latex() before wrapping.
    This ensures _ { } \\ in prose never break the document.
    """
    result: list[str] = []
    last = 0
    for m in _INLINE_SPAN_RE.finditer(text):
        result.append(_escape_latex(text[last:m.start()]))
        if m.group(1) is not None:       # **bold**
            result.append(r"\textbf{" + _escape_latex(m.group(1)) + r"}")
        elif m.group(2) is not None:     # __bold__
            result.append(r"\textbf{" + _escape_latex(m.group(2)) + r"}")
        elif m.group(3) is not None:     # *italic*
            result.append(r"\textit{" + _escape_latex(m.group(3)) + r"}")
        elif m.group(4) is not None:     # _italic_
            result.append(r"\textit{" + _escape_latex(m.group(4)) + r"}")
        elif m.group(5) is not None:     # `code`
            result.append(r"\texttt{" + _escape_latex(m.group(5)) + r"}")
        last = m.end()
    result.append(_escape_latex(text[last:]))
    return "".join(result)


# ---------------------------------------------------------------------------
# Markdown body -> LaTeX body
# ---------------------------------------------------------------------------

_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_ENUM_RE = re.compile(r"^\s*\d+\.\s+(.*)$")
_CODE_FENCE_RE = re.compile(r"^```")
_BLOCKQUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_TABLE_ROW_RE = re.compile(r"^\s*\|")   # any line starting with |


def _md_to_latex_body(md: str) -> str:
    """
    Convert markdown body text to LaTeX.

    Handles:
    - Paragraphs (blank-line separated)
    - Bullet and numbered lists
    - Bold, italic, inline code (via _inline())
    - Blockquotes (consecutive > lines merged into one environment)
    - Code fences (verbatim)
    - Markdown tables (wrapped in verbatim — no table parser)
    - Sub-headings (## / ###) as \\subsection*
    """
    lines = md.splitlines()
    out: list[str] = []
    in_itemize = False
    in_enumerate = False
    in_verbatim = False
    in_table = False
    in_blockquote = False
    blockquote_lines: list[str] = []

    def _close_lists() -> None:
        nonlocal in_itemize, in_enumerate
        if in_itemize:
            out.append(r"\end{itemize}")
            in_itemize = False
        if in_enumerate:
            out.append(r"\end{enumerate}")
            in_enumerate = False

    def _close_blockquote() -> None:
        nonlocal in_blockquote, blockquote_lines
        if in_blockquote:
            out.append(r"\begin{quote}")
            for bql in blockquote_lines:
                out.append(_inline(bql))
            out.append(r"\end{quote}")
            in_blockquote = False
            blockquote_lines = []

    def _close_table() -> None:
        nonlocal in_table
        if in_table:
            out.append(r"\end{verbatim}")
            in_table = False

    for line in lines:
        # Code fence
        if _CODE_FENCE_RE.match(line):
            _close_lists()
            _close_blockquote()
            _close_table()
            if in_verbatim:
                out.append(r"\end{verbatim}")
                in_verbatim = False
            else:
                out.append(r"\begin{verbatim}")
                in_verbatim = True
            continue

        if in_verbatim:
            out.append(line)
            continue

        # Markdown table row — emit raw inside verbatim
        if _TABLE_ROW_RE.match(line):
            _close_lists()
            _close_blockquote()
            if not in_table:
                out.append(r"\begin{verbatim}")
                in_table = True
            out.append(line)
            continue
        else:
            _close_table()

        # Blockquote — collect consecutive lines, flush on break
        bq = _BLOCKQUOTE_RE.match(line)
        if bq:
            _close_lists()
            in_blockquote = True
            blockquote_lines.append(bq.group(1).strip())
            continue
        else:
            _close_blockquote()

        # Bullet list
        bm = _BULLET_RE.match(line)
        if bm:
            if in_enumerate:
                out.append(r"\end{enumerate}")
                in_enumerate = False
            if not in_itemize:
                out.append(r"\begin{itemize}")
                in_itemize = True
            out.append(r"\item " + _inline(bm.group(1).strip()))
            continue

        # Numbered list
        em = _ENUM_RE.match(line)
        if em:
            if in_itemize:
                out.append(r"\end{itemize}")
                in_itemize = False
            if not in_enumerate:
                out.append(r"\begin{enumerate}")
                in_enumerate = True
            out.append(r"\item " + _inline(em.group(1).strip()))
            continue

        # Sub-heading inside section body
        hm = re.match(r"^#{2,3}\s+(.+)$", line)
        if hm:
            _close_lists()
            out.append(r"\subsection*{" + _escape_latex(hm.group(1).strip()) + r"}")
            continue

        # Blank line = paragraph break
        if not line.strip():
            _close_lists()
            out.append("")
            continue

        # Regular prose
        out.append(_inline(line))

    # Close any open environments
    _close_lists()
    _close_blockquote()
    _close_table()
    if in_verbatim:
        out.append(r"\end{verbatim}")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Provenance section for LaTeX
# ---------------------------------------------------------------------------

def _format_provenance_latex(provenance_md: str) -> str:
    """Render the provenance block as a LaTeX description list."""
    if not provenance_md:
        return r"\textit{No provenance data available.}"

    lines = provenance_md.splitlines()
    items: list[tuple[str, str]] = []

    for line in lines:
        line = line.strip()
        if not line or line == "---":
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            items.append((key.strip(), val.strip()))
        else:
            items.append(("", line))

    if not items:
        return _escape_latex(provenance_md)

    parts = [r"\begin{description}"]
    for key, val in items:
        if key and val:
            parts.append(
                r"\item[\texttt{" + _escape_latex(key) + r"}] "
                + _escape_latex(val)
            )
        elif key:
            parts.append(r"\item[\texttt{" + _escape_latex(key) + r"}] ~")
        else:
            parts.append(r"\item[] " + _escape_latex(val))
    parts.append(r"\end{description}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LaTeX document assembly
# ---------------------------------------------------------------------------

def _build_latex(
    session_id: str,
    sections: dict[str, str],
    manifest: dict[str, Any],
    lp: Path | None,
) -> str:
    _roles = _role_models()
    reasoner = _roles["PRIMARY_REASONER"]
    challenger = _roles["ADVERSARIAL_CHALLENGER"]
    critic = _roles["CRITIC"]
    synth = _roles["SYNTHESIZER"]
    # Title: markdown H1 > manifest topic > fallback
    title = sections.get("_title", "").strip()
    if not title:
        title = str(manifest.get("topic", "")).strip()
    if not title:
        title = f"SOVEREIGN Research — Session {session_id}"

    topic        = str(manifest.get("topic", title)).strip()
    conv         = manifest.get("convergence_score", "N/A")
    conf         = manifest.get("confidence_score", "N/A")
    domain       = manifest.get("domain_score", "N/A")
    novelty      = manifest.get("novelty_score", "N/A")
    seeded_by    = manifest.get("seeded_by", [])
    if not isinstance(seeded_by, list):
        seeded_by = []
    gate_ts      = str(manifest.get("gate_timestamp", "")).strip()
    generated_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Abstract
    abstract_md = sections.get("abstract", "")
    if not abstract_md:
        _warn("No abstract section found in assembled document", lp)
        abstract_latex = r"\textit{Abstract not available.}"
    else:
        abstract_latex = _md_to_latex_body(abstract_md)

    # Body sections
    section_parts: list[str] = []
    for key in _SECTION_ORDER:
        if key == "provenance":
            body = _format_provenance_latex(sections.get("provenance", ""))
        elif key == "references":
            refs_md = sections.get("references", "")
            body = _md_to_latex_body(refs_md) if refs_md else r"\textit{No references listed.}"
        else:
            md = sections.get(key, "")
            if not md:
                if key not in ("discussion",):
                    _warn(f"Section '{key}' missing from assembled document", lp)
                continue
            body = _md_to_latex_body(md)

        title_str = _SECTION_TITLES.get(key, key.capitalize())
        section_parts.append(
            f"\\section{{{_escape_latex(title_str)}}}\n{body}"
        )

    sections_latex = "\n\n".join(section_parts)
    seeded_by_str = ", ".join(str(s) for s in seeded_by) if seeded_by else "none"

    doc = rf"""\documentclass[12pt,a4paper]{{article}}

% ---------------------------------------------------------------------------
% Packages
% ---------------------------------------------------------------------------
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage{{lmodern}}
\usepackage{{microtype}}
\usepackage{{hyperref}}
\usepackage{{geometry}}
\usepackage{{booktabs}}
\usepackage{{amsmath}}
\usepackage{{amssymb}}
\usepackage{{graphicx}}

\geometry{{
  a4paper,
  margin=2.5cm,
}}

% ---------------------------------------------------------------------------
% Metadata
% ---------------------------------------------------------------------------
\hypersetup{{
  pdftitle={{{_escape_latex(title)}}},
  pdfauthor={{SOVEREIGN {SOVEREIGN_VERSION}}},
  pdfsubject={{{_escape_latex(topic)}}},
  pdfkeywords={{AI alignment, adversarial debate, SOVEREIGN}},
  colorlinks=true,
  linkcolor=blue,
  urlcolor=blue,
  citecolor=blue,
}}

% ---------------------------------------------------------------------------
% Document
% ---------------------------------------------------------------------------
\begin{{document}}

\title{{\large\textbf{{{_escape_latex(title)}}}\\[0.5em]
  \normalsize\textit{{Generated by SOVEREIGN {SOVEREIGN_VERSION} adversarial AI research pipeline}}}}
\author{{%
  SOVEREIGN Multi-Model Adversarial Debate System\\
  \texttt{{{reasoner}}} (Reasoner) $\cdot$
  \texttt{{{challenger}}} (Challenger) $\cdot$
  \texttt{{{critic}}} (Critic) $\cdot$
  \texttt{{{synth}}} (Synthesis)
}}
\date{{%
  Session: \texttt{{{_escape_latex(session_id)}}}\\
  Generated: {_escape_latex(generated_ts)}%
}}

\maketitle

% ---------------------------------------------------------------------------
% Score table
% ---------------------------------------------------------------------------
\begin{{table}}[h!]
\centering
\begin{{tabular}}{{lll}}
\toprule
\textbf{{Metric}} & \textbf{{Value}} & \textbf{{Threshold}} \\
\midrule
Convergence score  & {_escape_latex(str(conv))}    & $\geq 0.90$ \\
Confidence score   & {_escape_latex(str(conf))}    & $\geq 0.80$ \\
Domain score       & {_escape_latex(str(domain))}  & $\geq 0.70$ \\
Novelty score      & {_escape_latex(str(novelty))} & $\geq 0.20$ \\
\bottomrule
\end{{tabular}}
\caption{{Publication gate scores — session \texttt{{{_escape_latex(session_id)}}}.}}
\end{{table}}

\noindent\textbf{{Seeded by:}} \texttt{{{_escape_latex(seeded_by_str)}}}\\
\noindent\textbf{{Gate timestamp:}} \texttt{{{_escape_latex(gate_ts)}}}

\vspace{{1em}}
\hrule
\vspace{{1em}}

% ---------------------------------------------------------------------------
% Abstract
% ---------------------------------------------------------------------------
\begin{{abstract}}
{abstract_latex}
\end{{abstract}}

\tableofcontents
\newpage

% ---------------------------------------------------------------------------
% Body sections
% ---------------------------------------------------------------------------
{sections_latex}

\end{{document}}
"""
    return doc


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def _write_tex(dest_path: Path, content: str, lp: Path | None) -> bool:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        fd, tmp = tempfile.mkstemp(dir=str(dest_path.parent), suffix=".tmp")
        tmp_path = Path(tmp)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(str(tmp_path), str(dest_path))
        return True
    except OSError as exc:
        _error(f"Failed to write {dest_path}: {exc}", lp)
        try:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SOVEREIGN Phase 9 — arXiv LaTeX formatter"
    )
    parser.add_argument(
        "--session",
        required=True,
        help="Session ID to format",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="SOVEREIGN root (default: auto-detect via .sovereign-root marker)",
    )
    return parser.parse_args()


def _resolve_root(cli_root) -> Path:
    """Resolve SOVEREIGN root via the single authority (tools/sovereign_paths.py)."""
    repo = Path(__file__).resolve().parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from tools.sovereign_paths import get_repo_root, configure_root
    return configure_root(str(cli_root)) if cli_root else get_repo_root()


def main() -> int:
    args = _parse_args()
    root: Path = _resolve_root(args.root)
    session_id: str = str(args.session).strip()

    p = _paths(root)
    lp = p["log_file"]

    _info(f"=== format_arxiv starting | session_id={session_id} | root={root} ===", lp)

    input_path = p["assembled"] / f"{session_id}.md"
    if not input_path.exists():
        _error(f"Assembled document not found: {input_path}", lp)
        return 1

    dest_path = p["formatted"] / f"{session_id}.tex"
    if dest_path.exists():
        _warn(f"Output already exists: {dest_path} — skipping (append-only policy)", lp)
        return 0

    try:
        md_text = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        _error(f"Cannot read assembled document: {exc}", lp)
        return 1

    if not md_text.strip():
        _error(f"Assembled document is empty: {input_path}", lp)
        return 1

    _info(f"Assembled document read | chars={len(md_text)}", lp)

    manifest = _read_manifest(root, session_id, lp)
    sections = _parse_sections(md_text, lp)
    _info(f"Sections parsed: {[k for k in sections if not k.startswith('_')]}", lp)

    latex = _build_latex(session_id, sections, manifest, lp)

    ok = _write_tex(dest_path, latex, lp)
    if not ok:
        return 1

    _info(f"LaTeX written: {dest_path}", lp)
    _info(f"=== format_arxiv complete | session_id={session_id} ===", lp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
