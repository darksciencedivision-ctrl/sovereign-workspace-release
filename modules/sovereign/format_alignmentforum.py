from __future__ import annotations

r"""
format_alignmentforum.py — SOVEREIGN Phase 9 (Deliverable 4/7)

Deterministic template formatting. No LLM call.

Input:  publication_queue\assembled\{session_id}.md
Output: publication_queue\formatted\{session_id}_af.md

Applies LessWrong / Alignment Forum markdown conventions:
- AF-compatible markdown (no raw HTML, no LaTeX math)
- SOVEREIGN provenance header block
- Tag suggestions derived from topic keywords
- Score summary table in markdown
- Section structure preserved from assembled document

CLI: python format_alignmentforum.py --session SESSION_ID [--root <SOVEREIGN_ROOT>]
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

MODULE_NAME = "FORMAT_ALIGNMENTFORUM"
SOVEREIGN_VERSION = PRODUCT_VERSION


def _role_models() -> dict[str, str]:
    """Role->model names for display, read from SYSTEM_MANIFEST.json (single source
    of truth). Defensive: never raises at format time; falls back to generic labels."""
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

# AF tag candidates: map keyword -> AF tag string
# These are best-effort suggestions; human reviewer confirms before posting.
_TAG_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bcooperat\w*\b", re.I),          "Cooperation"),
    (re.compile(r"\badversar\w*\b", re.I),           "Adversarial Robustness"),
    (re.compile(r"\balignment\b", re.I),             "AI Alignment"),
    (re.compile(r"\bemerg\w*\b", re.I),              "Emergent Behavior"),
    (re.compile(r"\bmulti.?model\b", re.I),          "Multi-Agent Systems"),
    (re.compile(r"\bmulti.?agent\b", re.I),          "Multi-Agent Systems"),
    (re.compile(r"\bdebate\b", re.I),                "AI Safety via Debate"),
    (re.compile(r"\breinforcement\b", re.I),         "Reinforcement Learning"),
    (re.compile(r"\bconverg\w*\b", re.I),            "Convergence"),
    (re.compile(r"\binterpret\w*\b", re.I),          "Interpretability"),
    (re.compile(r"\btranspar\w*\b", re.I),           "Transparency"),
    (re.compile(r"\bscalab\w*\b", re.I),             "Scalable Oversight"),
    (re.compile(r"\boversight\b", re.I),             "Scalable Oversight"),
    (re.compile(r"\bmemory\b", re.I),                "AI Memory"),
    (re.compile(r"\bknowledge\b", re.I),             "Knowledge Representation"),
    (re.compile(r"\breason\w*\b", re.I),             "Reasoning"),
    (re.compile(r"\buncertain\w*\b", re.I),          "Uncertainty"),
    (re.compile(r"\bcooperat\w*\b", re.I),           "Cooperation"),
    (re.compile(r"\bgoal\b", re.I),                  "Goal-Directedness"),
    (re.compile(r"\bincentive\b", re.I),             "Incentives"),
    (re.compile(r"\bpower.?seek\w*\b", re.I),        "Power-Seeking"),
    (re.compile(r"\bdecepti\w*\b", re.I),            "Deceptive Alignment"),
    (re.compile(r"\bhonest\w*\b", re.I),             "Honesty"),
    (re.compile(r"\bvalue\b", re.I),                 "Value Alignment"),
    (re.compile(r"\brobust\w*\b", re.I),             "Robustness"),
]

# Known section names in the assembled document
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

_SECTION_ORDER = [
    "abstract",
    "introduction",
    "methodology",
    "results",
    "discussion",
    "conclusion",
    "references",
    "provenance",
]

_SECTION_DISPLAY = {
    "abstract":      "Abstract",
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
        "log_file":   root / "logs" / "format_alignmentforum_log.txt",
    }


# ---------------------------------------------------------------------------
# Manifest reading
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
# Markdown section parsing (same logic as format_arxiv.py)
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")


def _parse_sections(md_text: str, lp: Path | None) -> dict[str, str]:
    """
    Parse assembled markdown into canonical_key -> body_text.
    Special key: "_title" for the document H1.
    Unknown sections logged and preserved under sanitized key.
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
# AF markdown normalization
# ---------------------------------------------------------------------------

# LaTeX math patterns to strip/replace: $...$ and $$...$$
_INLINE_MATH_RE = re.compile(r"\$([^$\n]+?)\$")
_BLOCK_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)

# Raw HTML tags to strip
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# LaTeX-style commands that might bleed through from assembled doc
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+\{[^}]*\}")


def _normalize_for_af(text: str) -> str:
    """
    Normalize body text for AF markdown:
    - Remove raw HTML tags
    - Replace inline LaTeX math ($...$) with backtick code spans
    - Replace block LaTeX math ($$...$$) with fenced code blocks
    - Strip stray LaTeX commands (e.g. \textbf{x} -> x)
    - Normalize line endings
    """
    # Block math first (before inline)
    def _block_math_replace(m: re.Match[str]) -> str:
        inner = m.group(1).strip()
        return f"\n```\n{inner}\n```\n"

    text = _BLOCK_MATH_RE.sub(_block_math_replace, text)

    # Inline math
    def _inline_math_replace(m: re.Match[str]) -> str:
        return f"`{m.group(1).strip()}`"

    text = _INLINE_MATH_RE.sub(_inline_math_replace, text)

    # Raw HTML
    text = _HTML_TAG_RE.sub("", text)

    # Stray LaTeX commands: \textbf{x} -> x, \emph{x} -> x, etc.
    def _latex_cmd_replace(m: re.Match[str]) -> str:
        cmd = m.group(0)
        # Extract content inside braces if present
        inner = re.search(r"\{([^}]*)\}", cmd)
        return inner.group(1) if inner else ""

    text = _LATEX_CMD_RE.sub(_latex_cmd_replace, text)

    return text


def _normalize_section_body(body: str) -> str:
    """Normalize a section body for AF, then re-level headings."""
    body = _normalize_for_af(body)

    # Re-level headings inside a section body:
    # ## -> ### (so top-level section is ##, sub-sections are ###)
    lines = body.splitlines()
    out: list[str] = []
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            depth = len(m.group(1))
            # Shift so ## becomes ###, ### becomes ####, etc.
            new_depth = min(depth + 1, 6)
            out.append("#" * new_depth + " " + m.group(2))
        else:
            out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Tag suggestion
# ---------------------------------------------------------------------------

def _suggest_tags(topic: str, sections: dict[str, str]) -> list[str]:
    """
    Derive AF tag suggestions from topic and abstract text.
    Returns deduplicated list of tag strings, max 8.
    """
    search_text = topic + " " + sections.get("abstract", "") + " " + sections.get("introduction", "")
    seen: set[str] = set()
    tags: list[str] = []
    for pattern, tag in _TAG_KEYWORDS:
        if tag not in seen and pattern.search(search_text):
            seen.add(tag)
            tags.append(tag)
        if len(tags) >= 8:
            break
    # Always include these for SOVEREIGN outputs
    for base_tag in ("AI Alignment", "Multi-Agent Systems"):
        if base_tag not in seen:
            tags.append(base_tag)
            seen.add(base_tag)
    return tags[:8]


# ---------------------------------------------------------------------------
# Score summary table (markdown)
# ---------------------------------------------------------------------------

def _score_table(manifest: dict[str, Any]) -> str:
    conv    = manifest.get("convergence_score", "N/A")
    conf    = manifest.get("confidence_score", "N/A")
    domain  = manifest.get("domain_score", "N/A")
    novelty = manifest.get("novelty_score", "N/A")

    return (
        "| Metric | Value | Threshold |\n"
        "|--------|-------|-----------|\n"
        f"| Convergence score | {conv} | ≥ 0.90 |\n"
        f"| Confidence score  | {conf} | ≥ 0.80 |\n"
        f"| Domain score      | {domain} | ≥ 0.70 |\n"
        f"| Novelty score     | {novelty} | ≥ 0.20 |\n"
    )


# ---------------------------------------------------------------------------
# SOVEREIGN provenance header
# ---------------------------------------------------------------------------

def _provenance_header(
    session_id: str,
    topic: str,
    manifest: dict[str, Any],
    tags: list[str],
    generated_ts: str,
) -> str:
    seeded_by = manifest.get("seeded_by", [])
    if not isinstance(seeded_by, list):
        seeded_by = []
    gate_ts       = str(manifest.get("gate_timestamp", "")).strip()
    gate_passed   = manifest.get("gate_passed", False)
    synthesis_tag = str(manifest.get("synthesis_tag", "")).strip()

    seeded_str = ", ".join(str(s) for s in seeded_by) if seeded_by else "none"
    tags_str   = ", ".join(tags) if tags else "none"

    _roles = _role_models()
    _reasoner   = _roles["PRIMARY_REASONER"]
    _challenger = _roles["ADVERSARIAL_CHALLENGER"]
    _critic     = _roles["CRITIC"]
    _synth      = _roles["SYNTHESIZER"]

    return (
        f"> **SOVEREIGN v{SOVEREIGN_VERSION} — Automated Research Output**\n"
        ">\n"
        "> This post was generated by the SOVEREIGN multi-model adversarial AI debate system.\n"
        "> It has passed automated quality gates but **requires human review before acting on its claims**.\n"
        ">\n"
        "> | Field | Value |\n"
        "> |-------|-------|\n"
        f"> | Session ID | `{session_id}` |\n"
        f"> | Topic | {topic} |\n"
        f"> | Gate passed | {gate_passed} |\n"
        f"> | Gate timestamp | {gate_ts} |\n"
        f"> | Seeded by | {seeded_str} |\n"
        f"> | Synthesis tag | `{synthesis_tag}` |\n"
        f"> | Generated | {generated_ts} |\n"
        ">\n"
        f"> **Suggested tags:** {tags_str}\n"
        ">\n"
        f"> *Models: {_reasoner} (Reasoner) · {_challenger} (Challenger) · "
        f"{_critic} (Critic) · {_synth} (Synthesis)*\n"
    )


# ---------------------------------------------------------------------------
# Document assembly
# ---------------------------------------------------------------------------

def _build_af_document(
    session_id: str,
    sections: dict[str, str],
    manifest: dict[str, Any],
    lp: Path | None,
) -> str:
    topic = sections.get("_title", "").strip()
    if not topic:
        topic = str(manifest.get("topic", "")).strip()
    if not topic:
        topic = f"SOVEREIGN Research — Session {session_id}"

    generated_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tags = _suggest_tags(topic, sections)

    parts: list[str] = []

    # Document title
    parts.append(f"# {topic}\n")

    # Provenance header block
    parts.append(_provenance_header(session_id, topic, manifest, tags, generated_ts))
    parts.append("")

    # Score table
    parts.append("## Publication Gate Scores\n")
    parts.append(_score_table(manifest))
    parts.append("")

    # Body sections
    for key in _SECTION_ORDER:
        body = sections.get(key, "")
        if not body:
            if key not in ("discussion", "provenance"):
                _warn(f"Section '{key}' missing — skipping", lp)
            continue

        display = _SECTION_DISPLAY.get(key, key.capitalize())

        if key == "provenance":
            # Render provenance as a collapsed blockquote detail block
            # AF supports HTML details/summary; we use a blockquote fallback
            # since raw HTML is stripped. Emit as a clearly marked section.
            parts.append(f"## {display}\n")
            prov_lines = body.splitlines()
            prov_quoted = "\n".join("> " + ln if ln.strip() else ">" for ln in prov_lines)
            parts.append(prov_quoted)
            parts.append("")
        else:
            normalized = _normalize_section_body(body)
            parts.append(f"## {display}\n")
            parts.append(normalized)
            parts.append("")

    # Unknown sections (preserve, append at end)
    known_keys = set(_SECTION_ORDER) | {"_title", "preamble", "__after_title__"}
    for key, body in sections.items():
        if key in known_keys or key.startswith("_"):
            continue
        _warn(f"Appending unknown section '{key}' at end of document", lp)
        parts.append(f"## {key.replace('_', ' ').capitalize()}\n")
        parts.append(_normalize_section_body(body))
        parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def _write_md(dest_path: Path, content: str, lp: Path | None) -> bool:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        fd, tmp = tempfile.mkstemp(dir=str(dest_path.parent), suffix=".tmp")
        tmp_path = Path(tmp)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            if not content.endswith("\n"):
                fh.write("\n")
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
        description="SOVEREIGN Phase 9 — Alignment Forum markdown formatter"
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

    _info(f"=== format_alignmentforum starting | session_id={session_id} | root={root} ===", lp)

    input_path = p["assembled"] / f"{session_id}.md"
    if not input_path.exists():
        _error(f"Assembled document not found: {input_path}", lp)
        return 1

    dest_path = p["formatted"] / f"{session_id}_af.md"
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

    af_doc = _build_af_document(session_id, sections, manifest, lp)

    ok = _write_md(dest_path, af_doc, lp)
    if not ok:
        return 1

    _info(f"AF document written: {dest_path}", lp)
    _info(f"=== format_alignmentforum complete | session_id={session_id} ===", lp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
