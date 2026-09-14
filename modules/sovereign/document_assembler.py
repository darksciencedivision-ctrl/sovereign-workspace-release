from __future__ import annotations

# F-125 - QUARANTINE / SUPPORT DISPOSITION: legacy Phase-9 engine, NOT on the shipped product
# route (product DEEP traffic uses sovereign_product/semantic_deep). Retained unsupported; do not
# add a product caller. See cycle_runner_v3.py for the full disposition.

r"""
document_assembler.py - SOVEREIGN Phase 9

Reads a publication queue manifest. Pulls synthesis by session tag from
praxis\logs\synthesis.txt, retrieves PRAXIS context via praxis_query.py IPC,
and assembles a publication-ready markdown document with the manifest-configured synthesis model.

CLI: python document_assembler.py --session SESSION_ID [--root <SOVEREIGN_ROOT>]
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from system_manifest import load_system_manifest, model_name, runtime_value
from sovereign_version import PRODUCT_VERSION

MODULE_NAME = "DOCUMENT_ASSEMBLER"
SOVEREIGN_VERSION = PRODUCT_VERSION

OLLAMA_TIMEOUT = 120
PRAXIS_QUERY_TIMEOUT = 60

_SYNTH_OPEN_RE = re.compile(
    r"^\[(SYNTH|RRR-SYNTH)(?:\s+session_id=([^\]\s]+)|\s+S([^\s\]]+)(?:\s+[^\]]+)?)\]\s*$",
    re.IGNORECASE,
)
_SYNTH_CLOSE_RE = re.compile(r"^\[/(SYNTH|RRR-SYNTH)\]\s*$", re.IGNORECASE)


def _log(level: str, msg: str, log_path: Optional[Path]) -> None:
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


def _info(msg: str, lp: Optional[Path]) -> None:
    _log("INFO", msg, lp)


def _warn(msg: str, lp: Optional[Path]) -> None:
    _log("WARN", msg, lp)


def _error(msg: str, lp: Optional[Path]) -> None:
    _log("ERROR", msg, lp)


def _paths(root: Path) -> dict[str, Path]:
    return {
        "manifest": root / "publication_queue",
        "assembled": root / "publication_queue" / "assembled",
        "session_graph": root / "orchestra" / "session_graph.json",
        "synthesis_log": root / "praxis" / "logs" / "synthesis.txt",
        "praxis_ipc_dir": root / "praxis",
        "praxis_query_script": root / "praxis" / "praxis_query.py",
        "log_file": root / "logs" / "document_assembler_log.txt",
    }


def _read_manifest(root: Path, session_id: str, lp: Optional[Path]) -> Optional[dict[str, Any]]:
    manifest_path = root / "publication_queue" / f"{session_id}_manifest.json"
    if not manifest_path.exists():
        _error(f"Manifest not found: {manifest_path}", lp)
        return None

    try:
        raw = manifest_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            _error(f"Manifest is not a JSON object: {manifest_path}", lp)
            return None
        return data
    except json.JSONDecodeError as exc:
        _error(f"Malformed manifest JSON: {exc} | path={manifest_path}", lp)
        return None
    except OSError as exc:
        _error(f"Cannot read manifest: {exc}", lp)
        return None


def _read_session_graph(path: Path, lp: Optional[Path]) -> list[dict[str, Any]]:
    if not path.exists():
        _warn(f"session_graph.json not found at {path}", lp)
        return []

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            _error("session_graph.json is not a JSON object", lp)
            return []
        sessions = data.get("sessions")
        if not isinstance(sessions, list):
            _error("session_graph.json missing sessions array", lp)
            return []
        return [n for n in sessions if isinstance(n, dict)]
    except json.JSONDecodeError as exc:
        _error(f"session_graph.json parse failure: {exc}", lp)
        return []
    except OSError as exc:
        _error(f"Cannot read session_graph.json: {exc}", lp)
        return []


def _find_node(graph: list[dict[str, Any]], session_id: str) -> Optional[dict[str, Any]]:
    for node in graph:
        if str(node.get("session_id", "")).strip() == session_id:
            return node
    return None


def _collect_seeded_by_chain(
    graph: list[dict[str, Any]],
    session_id: str,
    _visited: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    if _visited is None:
        _visited = set()
    if session_id in _visited:
        return []
    _visited.add(session_id)

    node = _find_node(graph, session_id)
    if node is None:
        return []

    result: list[dict[str, Any]] = []
    seeded_by = node.get("seeded_by", [])
    if not isinstance(seeded_by, list):
        return result

    for parent_id_raw in seeded_by:
        parent_id = str(parent_id_raw).strip()
        if not parent_id or parent_id in _visited:
            continue
        parent_node = _find_node(graph, parent_id)
        if parent_node:
            result.append(parent_node)
        result.extend(_collect_seeded_by_chain(graph, parent_id, _visited))
    return result


def _parse_synth_open_tag(line: str) -> Optional[tuple[str, str]]:
    m = _SYNTH_OPEN_RE.match(line.strip())
    if not m:
        return None
    tag_name = m.group(1).upper()
    sid = (m.group(2) or m.group(3) or "").strip()
    return tag_name, sid


def _take_block_at(lines: list[str], start_idx: int, tag_line: str, tag_name: str) -> tuple[str, str]:
    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        s = lines[j].strip()
        close_match = _SYNTH_CLOSE_RE.match(s)
        if close_match and close_match.group(1).upper() == tag_name:
            end_idx = j
            break
        if _parse_synth_open_tag(s):
            end_idx = j
            break
    block = "\n".join(lines[start_idx + 1 : end_idx]).strip()
    return block, tag_line


def _extract_synthesis_block(
    synthesis_path: Path,
    session_id: str,
    manifest_tag: str,
    lp: Optional[Path],
) -> tuple[str, str]:
    if not synthesis_path.exists():
        _error(f"synthesis.txt not found at {synthesis_path}", lp)
        return "", ""

    try:
        text = synthesis_path.read_text(encoding="utf-8")
    except OSError as exc:
        _error(f"Cannot read synthesis.txt: {exc}", lp)
        return "", ""

    lines = text.splitlines()
    sid = session_id.strip()
    mtag = manifest_tag.strip()

    if mtag:
        for i, line in enumerate(lines):
            if line.strip() != mtag:
                continue
            parsed = _parse_synth_open_tag(line)
            if not parsed:
                continue
            tag_name, _ = parsed
            block, tag_line = _take_block_at(lines, i, line.rstrip(), tag_name)
            if block:
                return block, tag_line
            _warn(f"Manifest synthesis_tag matched but block was empty | tag={mtag}", lp)
            return "", line.rstrip()
        _warn(
            f"Manifest synthesis_tag not found in synthesis.txt | tag={mtag} - falling back to session_id search",
            lp,
        )

    hits: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        parsed = _parse_synth_open_tag(line)
        if not parsed:
            continue
        tag_name, tag_sid = parsed
        if tag_sid == sid:
            hits.append((i, line.rstrip(), tag_name))

    if not hits:
        _warn(f"No synthesis tag found for session_id={sid}", lp)
        return "", ""

    start_idx, tag_line, tag_name = hits[-1]
    return _take_block_at(lines, start_idx, tag_line, tag_name)


def _parse_legacy_praxis_result(raw: str) -> list[dict[str, Any]]:
    raw = (raw or "").strip()
    if not raw:
        return []

    entries: list[dict[str, Any]] = []
    lines = raw.splitlines()

    current_meta: Optional[str] = None
    current_body: list[str] = []

    def _flush() -> None:
        nonlocal current_meta, current_body
        if current_meta is None and not current_body:
            return
        content = "\n".join(current_body).strip()
        if content:
            entries.append(
                {
                    "type": "legacy_context",
                    "source": current_meta or "praxis_result",
                    "response_elaboration": "?",
                    "content": content,
                }
            )
        current_meta = None
        current_body = []

    for line in lines:
        m = re.match(r"^\[MEMORY\s+\d+\]\s*(.*)$", line.strip())
        if m:
            _flush()
            current_meta = m.group(1).strip() or "memory"
            continue
        current_body.append(line)

    _flush()

    if entries:
        return entries

    return [
        {
            "type": "legacy_context",
            "source": "praxis_result",
            "response_elaboration": "?",
            "content": raw,
        }
    ]


def _praxis_query(
    query: str,
    root: Path,
    lp: Optional[Path],
    n_results: int = 5,
) -> tuple[Optional[list[dict[str, Any]]], Optional[str]]:
    praxis_dir = root / "praxis"
    query_file = praxis_dir / "query.txt"
    result_file = praxis_dir / "result.txt"
    script = root / "praxis" / "praxis_query.py"

    if not script.exists():
        return None, f"praxis_query.py not found at {script}"

    payload = json.dumps({"query": query, "n_results": n_results, "include_claims": True, "include_unresolved": True, "include_contested": True}, ensure_ascii=False)
    try:
        query_file.write_text(payload, encoding="utf-8")
    except OSError as exc:
        return None, f"Cannot write PRAXIS query file: {exc}"

    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--root", str(root)],
            capture_output=True,
            text=True,
            timeout=PRAXIS_QUERY_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None, f"praxis_query.py timed out after {PRAXIS_QUERY_TIMEOUT}s"
    except OSError as exc:
        return None, f"Cannot run praxis_query.py: {exc}"

    if proc.returncode != 0:
        stderr_tail = (proc.stderr or "").strip()[:240]
        return None, f"praxis_query.py exited {proc.returncode} | stderr={stderr_tail}"

    if not result_file.exists():
        return None, "PRAXIS result.txt not found after query"

    try:
        raw = result_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return None, f"Cannot read PRAXIS result.txt: {exc}"

    if not raw:
        return [], None

    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [e for e in data if isinstance(e, dict)], None
        return _parse_legacy_praxis_result(raw), None
    except json.JSONDecodeError:
        return _parse_legacy_praxis_result(raw), None


def _ollama_generate(prompt: str, session_id: str, ollama_base: str, assembly_model: str, lp: Optional[Path]) -> Optional[str]:
    try:
        import requests as req
    except ImportError:
        _error("requests not installed - cannot call Ollama", lp)
        return None

    seed = int(hashlib.sha256(session_id.encode()).hexdigest()[:8], 16)
    payload: dict[str, Any] = {
        "model": assembly_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "seed": seed},
    }

    try:
        resp = req.post(
            f"{ollama_base.rstrip('/')}/api/generate",
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except req.exceptions.Timeout:
        _error(f"Ollama request timed out after {OLLAMA_TIMEOUT}s", lp)
        return None
    except req.exceptions.RequestException as exc:
        _error(f"Ollama request failed: {exc}", lp)
        return None
    except Exception as exc:
        _error(f"Unexpected Ollama error: {exc}", lp)
        return None

    text = data.get("response")
    if not isinstance(text, str):
        _error(f"Ollama response missing 'response' key | keys={list(data.keys())}", lp)
        return None
    return text.strip()


def _format_praxis_entries(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "No supporting PRAXIS entries retrieved."

    parts: list[str] = []
    for i, e in enumerate(entries, start=1):
        etype = e.get("type", "unknown")
        content = str(e.get("content", "")).strip()
        confidence = e.get("response_elaboration", "?")
        topic = e.get("topic", "")
        parts.append(f"[{i}] type={etype} response_elaboration={confidence} topic={topic}\n{content}")
    return "\n\n".join(parts)


def _format_ancestor_chain(ancestors: list[dict[str, Any]]) -> str:
    if not ancestors:
        return "No ancestor sessions."

    parts: list[str] = []
    for a in ancestors:
        sid = a.get("session_id", "?")
        topic = a.get("topic", "")
        metrics = a.get("metrics") if isinstance(a.get("metrics"), dict) else {}
        conv = metrics.get("structural_completeness", "?")
        summary = a.get("final_synthesis", a.get("synthesis_summary", ""))
        parts.append(f"Session {sid} | topic={topic} | structural_completeness={conv}\n{summary}")
    return "\n\n".join(parts)


def _build_assembly_prompt(
    session_id: str,
    topic: str,
    synthesis_block: str,
    praxis_entries: list[dict[str, Any]],
    ancestors: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> str:
    conv = manifest.get("convergence_score", "?")
    conf = manifest.get("confidence_score", "?")
    seeded_by = manifest.get("seeded_by", [])

    return f"""You are an academic research document assembler for the SOVEREIGN adversarial AI debate system.

Your task: produce a complete, structured research document based on the provided debate synthesis, supporting memory entries, and session context. Write in formal academic prose. Do not invent facts. Do not introduce claims not supported by the provided synthesis or PRAXIS entries.

---
TOPIC:
{topic}

---
PRIMARY SYNTHESIS (from adversarial debate session {session_id}):
{synthesis_block if synthesis_block else "[No synthesis block available]"}

---
SUPPORTING PRAXIS MEMORY ENTRIES:
{_format_praxis_entries(praxis_entries)}

---
ANCESTOR SESSION CHAIN (seeded_by lineage):
{_format_ancestor_chain(ancestors)}

---
SESSION METADATA:
- Session ID: {session_id}
- Convergence score: {conv}
- Confidence score: {conf}
- Seeded by: {", ".join(seeded_by) if seeded_by else "none"}

---
DOCUMENT STRUCTURE (produce all sections in order):

# {topic}

## Abstract
A concise summary of the research question, methodology (adversarial debate), key findings, and implications. 150-250 words.

## Introduction
Context and motivation for the topic. State the research question. Explain the adversarial debate methodology briefly. 200-400 words.

## Methodology
Describe the SOVEREIGN adversarial debate process: multi-model debate (Reasoner, Challenger, Critic), RRR convergence cycles, memory retrieval from PRAXIS. Reference the session lineage where relevant. 200-350 words.

## Results
Present the substantive findings from the synthesis. Organized subsections if needed. Be specific and grounded in the synthesis text. 300-600 words.

## Discussion
Interpret the results. Address limitations, open questions, and areas of remaining uncertainty from the synthesis. 200-400 words.

## Conclusion
Summarize the key contributions and implications for AI alignment research. 100-200 words.

## References
List any specific claims, session IDs, or corpus sources referenced in the document.

---
INSTRUCTIONS:
- Write every section completely. Do not use placeholders.
- Maintain formal academic tone throughout.
- Ground all claims in the synthesis and PRAXIS entries provided.
- Do not add a PROVENANCE section - it will be appended separately.
- Output only the document text. No preamble, no meta-commentary.
"""


def _build_provenance_block(
    session_id: str,
    topic: str,
    manifest: dict[str, Any],
    ancestors: list[dict[str, Any]],
    praxis_entries: list[dict[str, Any]],
    synthesis_tag: str,
    system_manifest: dict[str, Any],
) -> str:
    seeded_by = manifest.get("seeded_by", [])
    conv = manifest.get("convergence_score", "?")
    conf = manifest.get("confidence_score", "?")

    source_docs = list(
        {
            str(e.get("source", "")).strip()
            for e in praxis_entries
            if str(e.get("source", "")).strip()
        }
    )
    source_docs_str = ", ".join(sorted(source_docs)) if source_docs else "none"

    rrr_depth = len(ancestors)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return f"""
---
PROVENANCE
Session ID:          {session_id}
Topic:               {topic}
Seeded by sessions:  {", ".join(seeded_by) if seeded_by else "none"}
Corpus sources:      {source_docs_str}
Convergence score:   {conv}
Confidence score:    {conf}
RRR depth:           {rrr_depth}
Synthesis tag:       {synthesis_tag}
Models used:         {model_name("PRIMARY_REASONER", system_manifest)} (Reasoner), {model_name("ADVERSARIAL_CHALLENGER", system_manifest)} (Challenger),
                     {model_name("CRITIC", system_manifest)} (Critic), {model_name("SYNTHESIZER", system_manifest)} (Synthesis + Assembly)
SOVEREIGN version:   {SOVEREIGN_VERSION}
Generated:           {ts}
---
"""


def _write_assembled(dest_path: Path, content: str, lp: Optional[Path]) -> bool:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[Path] = None
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
        _error(f"Failed to write assembled document {dest_path}: {exc}", lp)
        try:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return False


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SOVEREIGN Phase 9 - Document Assembler")
    parser.add_argument("--session", required=True, help="Session ID to assemble")
    parser.add_argument(
        "--root",
        default=None,
        help="SOVEREIGN root (default: auto-detect via .sovereign-root marker)",
    )
    parser.add_argument("--ollama", default="", help="Ollama base URL")
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
    root = _resolve_root(args.root)
    args.root = str(root)
    session_id = str(args.session).strip()
    system_manifest = load_system_manifest(root)
    ollama_base = str(args.ollama).strip() or str(runtime_value("OLLAMA_BASE_URL", system_manifest)).strip()
    assembly_model = model_name("SYNTHESIZER", system_manifest)

    p = _paths(root)
    lp = p["log_file"]

    _info(f"=== Document Assembler starting | session_id={session_id} | root={root} ===", lp)

    manifest = _read_manifest(root, session_id, lp)
    if manifest is None:
        return 1

    if not manifest.get("gate_passed", False):
        _error(f"Manifest for session_id={session_id} has gate_passed=False - refusing to assemble", lp)
        return 1

    topic = str(manifest.get("topic", "")).strip()
    if not topic:
        _error(f"Manifest missing topic for session_id={session_id}", lp)
        return 1

    _info(f"Manifest loaded | topic={topic}", lp)

    dest_path = p["assembled"] / f"{session_id}.md"
    if dest_path.exists():
        _warn(f"Assembled document already exists: {dest_path} - skipping (append-only policy)", lp)
        return 0

    manifest_tag = str(manifest.get("synthesis_tag", "")).strip()
    synthesis_block, synthesis_tag = _extract_synthesis_block(
        p["synthesis_log"], session_id, manifest_tag, lp
    )
    if not synthesis_block:
        _error(f"No synthesis block found for session_id={session_id} - cannot assemble", lp)
        return 1

    _info(f"Synthesis block extracted | tag={synthesis_tag}", lp)

    praxis_entries, praxis_error = _praxis_query(topic, root, lp, n_results=8)
    if praxis_error is not None:
        _error(f"PRAXIS query failed - assembly aborted: {praxis_error}", lp)
        return 1
    if praxis_entries is None:
        _error("PRAXIS query returned no usable result - assembly aborted", lp)
        return 1

    _info(f"PRAXIS entries retrieved: {len(praxis_entries)}", lp)

    graph = _read_session_graph(p["session_graph"], lp)
    ancestors = _collect_seeded_by_chain(graph, session_id)
    _info(f"Ancestor sessions collected: {len(ancestors)}", lp)

    prompt = _build_assembly_prompt(
        session_id=session_id,
        topic=topic,
        synthesis_block=synthesis_block,
        praxis_entries=praxis_entries,
        ancestors=ancestors,
        manifest=manifest,
    )

    _info(f"Calling {assembly_model} for document assembly...", lp)
    draft = _ollama_generate(prompt, session_id, ollama_base, assembly_model, lp)
    if draft is None:
        _error("Ollama generation failed - cannot assemble document", lp)
        return 1
    if not draft.strip():
        _error("Ollama returned empty draft - cannot assemble document", lp)
        return 1

    _info(f"Draft received | chars={len(draft)}", lp)

    provenance = _build_provenance_block(
        session_id=session_id,
        topic=topic,
        manifest=manifest,
        ancestors=ancestors,
        praxis_entries=praxis_entries,
        synthesis_tag=synthesis_tag,
        system_manifest=system_manifest,
    )
    full_document = draft + provenance

    ok = _write_assembled(dest_path, full_document, lp)
    if not ok:
        return 1

    _info(f"Assembled document written: {dest_path}", lp)
    _info(f"=== Document Assembler complete | session_id={session_id} ===", lp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
