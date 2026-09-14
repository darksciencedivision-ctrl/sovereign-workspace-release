# topic_extractor.py - SOVEREIGN Phase 8 (2/6)
#
# Accepts a file path. Reads document text. Calls the manifest-configured critic model via Ollama
# /api/generate with a structured extraction prompt. Returns a JSON array
# of 3-5 topic strings.
#
# Topic schema (frozen):
#   ["topic string 1", "topic string 2", ...]
#   - Plain string array. No wrapper objects.
#   - Each string is a specific, debatable research question or claim.
#   - Each string is <= 200 characters.
#   - 3 minimum, 5 maximum per document.
#
# Retry policy:
#   One retry on malformed output, with a stricter prompt.
#   If retry also fails: returns [] and logs. Never aborts the cycle.
#
# Determinism:
#   Seed derived from sha256(path) — same document always produces same seed.
#   Temperature 0.0 when seed is active.
#   Retries DO NOT change the seed (prompt changes only).
#
# UTF-8 without BOM. Windows paths. No cloud APIs. Ollama local only.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from system_manifest import load_system_manifest, model_name, runtime_value


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PHASE8_VERSION   = "phase8-1.0"
MODULE_NAME      = "TOPIC_EXTRACTOR"
# Root is portable (resolved relative to this module); the manifest read is guarded so
# importing this module always reaches argument parsing, even on a relocated/misconfigured
# install. The active root is resolved via tools/sovereign_paths.py in main().
DEFAULT_ROOT     = str(Path(__file__).resolve().parent)
_MANIFEST_ERROR: Optional[str] = None
try:
    _MANIFEST        = load_system_manifest()
    OLLAMA_BASE_URL  = str(runtime_value("OLLAMA_BASE_URL", _MANIFEST)).strip()
    EXTRACT_MODEL    = model_name("CRITIC", _MANIFEST)
except Exception as _exc:  # noqa: BLE001 - import must stay non-fatal (argparse must be reachable)
    # F-122: keep IMPORT non-fatal so `--help`/argument parsing still works on a misconfigured
    # install, but do NOT silently pretend a model was configured. EXTRACT_MODEL="" used to be sent
    # to Ollama verbatim, producing a silently broken /api/generate call. The error is recorded and
    # _require_extract_model() raises loudly the moment the model is actually needed.
    _MANIFEST        = {}
    OLLAMA_BASE_URL  = "http://127.0.0.1:11434"
    EXTRACT_MODEL    = ""
    _MANIFEST_ERROR  = repr(_exc)


def _require_extract_model() -> str:
    if not EXTRACT_MODEL:
        raise RuntimeError(
            "TOPIC_EXTRACTOR cannot run: no critic model is configured. The system manifest "
            "could not be loaded" + (f" ({_MANIFEST_ERROR})" if _MANIFEST_ERROR else "") +
            ". Resolve the SOVEREIGN root / SYSTEM_MANIFEST.json before extracting topics."
        )
    return EXTRACT_MODEL
LOG_DIR          = "logs"
LOG_FILENAME     = "corpus_build_log.txt"
MAX_LOG_BYTES    = 10 * 1024 * 1024

TOPIC_MIN        = 3
TOPIC_MAX        = 5
TOPIC_MAX_CHARS  = 200
OLLAMA_TIMEOUT   = 120   # seconds; generous for 8b on local hardware
MAX_DOC_CHARS    = 8000  # clamp document text before sending to model


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rotate_log_if_needed(path: str) -> None:
    try:
        if not os.path.isfile(path):
            return
        if os.path.getsize(path) <= MAX_LOG_BYTES:
            return
        backup = path + ".1"
        if os.path.exists(backup):
            os.remove(backup)
        os.replace(path, backup)
    except OSError:
        pass


def _log(root: str, msg: str, level: str = "INFO") -> None:
    lvl = (level or "INFO").upper()
    line = f"[{_utc_iso()}] [{MODULE_NAME}] [{lvl}] {msg}"
    lp = os.path.join(root, LOG_DIR, LOG_FILENAME)
    try:
        os.makedirs(os.path.dirname(lp), exist_ok=True)
        _rotate_log_if_needed(lp)
        with open(lp, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        print(f"[{MODULE_NAME}] [WARN] log write failed: {exc}", file=sys.stderr)
    print(line)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
            if not content.endswith("\n"):
                fh.write("\n")
        os.replace(str(tmp_path), str(path))
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        raise


# ---------------------------------------------------------------------------
# Seed derivation
# ---------------------------------------------------------------------------

def _path_seed(path: str) -> int:
    """
    Deterministic Ollama seed from the file path.
    Positive 32-bit integer (1..2147483647).
    """
    h = hashlib.sha256(path.encode("utf-8")).digest()
    raw = int.from_bytes(h[:4], "big")
    return (raw % 0x7FFFFFFF) + 1


# ---------------------------------------------------------------------------
# Document reading
# ---------------------------------------------------------------------------

def _read_document(path: str) -> Optional[str]:
    """
    Read document text. Returns None on IO error.
    Clamps to MAX_DOC_CHARS to keep the prompt manageable.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read(MAX_DOC_CHARS + 1)
        if len(text) > MAX_DOC_CHARS:
            text = text[:MAX_DOC_CHARS] + "\n[DOCUMENT TRUNCATED]"
        return text
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Ollama call
# ---------------------------------------------------------------------------

def _ollama_generate(
    prompt:      str,
    seed:        int,
    base_url:    str = OLLAMA_BASE_URL,
    timeout_sec: int = OLLAMA_TIMEOUT,
) -> Optional[str]:
    """
    Call Ollama /api/generate with the manifest-configured critic model.
    Returns the model response string, or None on any error.
    Temperature 0.0 (deterministic via seed).
    """
    payload = {
        "model":  _require_extract_model(),
        "prompt": prompt,
        "stream": False,
        "options": {
            "seed":        int(seed),
            "temperature": 0.0,
            "num_predict": 512,
        },
    }

    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        return None

    url = base_url.rstrip("/") + "/api/generate"

    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError):
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    response = data.get("response")
    if not isinstance(response, str):
        return None

    return response.strip()


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM = (
    "You are a research topic extractor. "
    "Given a document, identify the most important, specific, and debatable "
    "research claims or questions it raises. "
    "Return ONLY a JSON array of strings. "
    "No preamble. No explanation. No markdown fences. No trailing text. "
    "Each string must be a complete, standalone topic suitable for adversarial debate. "
    f"Minimum {TOPIC_MIN} topics. Maximum {TOPIC_MAX} topics. "
    f"Each topic must be {TOPIC_MAX_CHARS} characters or fewer."
)

def _build_prompt(doc_text: str) -> str:
    return (
        f"{_EXTRACTION_SYSTEM}\n\n"
        f"DOCUMENT:\n{doc_text}\n\n"
        f"OUTPUT (JSON array only):"
    )

def _build_retry_prompt(doc_text: str, bad_output: str) -> str:
    return (
        f"{_EXTRACTION_SYSTEM}\n\n"
        f"DOCUMENT:\n{doc_text}\n\n"
        f"PREVIOUS ATTEMPT (invalid — do not repeat this format):\n{bad_output[:300]}\n\n"
        f"You MUST return ONLY a JSON array of strings and nothing else. "
        f"Example of correct output: "
        f'["Topic one here.", "Topic two here.", "Topic three here."]\n\n'
        f"OUTPUT (JSON array only):"
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks produced by reasoning models."""
    return re.sub(r"(?s)<think>.*?</think>", "", text).strip()

def _extract_json_array(text: str) -> Optional[list]:
    """
    Attempt to extract a JSON array from model output.
    Handles:
      - Clean output: just the array.
      - Output wrapped in ```json ... ``` or ``` ... ``` fences.
      - Array embedded in surrounding prose.
    Returns list or None.
    """
    if not text:
        return None

    text = _strip_think_tags(text)

    # 1) parse full output
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return obj
    except json.JSONDecodeError:
        pass

    # 2) strip markdown fences and retry
    fenced = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    fenced = re.sub(r"\s*```$", "", fenced.strip())
    try:
        obj = json.loads(fenced)
        if isinstance(obj, list):
            return obj
    except json.JSONDecodeError:
        pass

    # 3) locate the first bracketed JSON-ish array
    match = re.search(r"(\[[\s\S]*?\])", text)
    if match:
        try:
            obj = json.loads(match.group(1))
            if isinstance(obj, list):
                return obj
        except json.JSONDecodeError:
            pass

    return None

def _validate_and_clean(raw_topics: list, root: str, path: str) -> List[str]:
    """
    Validate and clean extracted topics:
      - Must be strings.
      - Strip whitespace.
      - Enforce TOPIC_MAX_CHARS (truncate with ellipsis, log warning).
      - Skip empty strings.
      - Deduplicate (case-insensitive) while preserving order.
      - Enforce TOPIC_MIN / TOPIC_MAX count strictly:
          if < TOPIC_MIN => return []
    """
    cleaned: List[str] = []
    seen = set()

    for item in raw_topics:
        if not isinstance(item, str):
            _log(root, f"non-string topic entry for {path}: {repr(item)!r}", "WARN")
            continue

        s = item.strip()
        if not s:
            continue

        key = s.lower()
        if key in seen:
            continue

        if len(s) > TOPIC_MAX_CHARS:
            _log(root, f"topic truncated to {TOPIC_MAX_CHARS} chars for {path}: {s[:60]}...", "WARN")
            s = s[:TOPIC_MAX_CHARS - 1] + "\u2026"

        seen.add(key)
        cleaned.append(s)

        if len(cleaned) >= TOPIC_MAX:
            break

    if len(cleaned) < TOPIC_MIN:
        _log(root, f"only {len(cleaned)} valid topic(s) extracted from {path} (minimum {TOPIC_MIN}). Returning [].", "ERROR")
        return []

    return cleaned


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_topics(
    path:        str,
    root:        str        = DEFAULT_ROOT,
    base_url:    str        = OLLAMA_BASE_URL,
    timeout_sec: int        = OLLAMA_TIMEOUT,
) -> List[str]:
    """
    Extract 3-5 debate topics from the document at `path`.
    Never raises; failures return [] and log.
    """
    fname = os.path.basename(path)
    seed  = _path_seed(path)

    _log(root, f"Extracting topics from: {path} (seed={seed})")

    doc_text = _read_document(path)
    if doc_text is None:
        _log(root, f"could not read document: {path}. Returning [].", "ERROR")
        return []
    if not doc_text.strip():
        _log(root, f"document is empty: {path}. Returning [].", "WARN")
        return []

    # Attempt 1
    prompt   = _build_prompt(doc_text)
    response = _ollama_generate(prompt, seed, base_url, timeout_sec)
    if response is None:
        _log(root, f"Ollama call failed for {fname}. Returning [].", "ERROR")
        return []

    topics_raw = _extract_json_array(response)

    # Retry once on malformed output — same seed, stricter prompt
    if topics_raw is None:
        _log(root, f"Parse failed (attempt 1) for {fname}. Response was: {response[:200]!r}", "WARN")
        retry_prompt   = _build_retry_prompt(doc_text, response)
        retry_response = _ollama_generate(retry_prompt, seed, base_url, timeout_sec)

        if retry_response is None:
            _log(root, f"Ollama call failed on retry for {fname}. Returning [].", "ERROR")
            return []

        topics_raw = _extract_json_array(retry_response)
        if topics_raw is None:
            _log(root, f"parse failed after retry for {fname}. Retry response: {retry_response[:200]!r}. Returning [].", "ERROR")
            return []

    topics = _validate_and_clean(topics_raw, root, path)
    if not topics:
        return []

    _log(root, f"Extracted {len(topics)} topic(s) from {fname}: "
               + " | ".join(f'"{t[:60]}"' for t in topics))

    return topics


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="SOVEREIGN Phase 8 — topic_extractor.py: extract debate topics from a corpus document."
    )
    ap.add_argument("path", help="Absolute path to the corpus document.")
    ap.add_argument(
        "--root", default=None,
        help="SOVEREIGN root (default: auto-detect via .sovereign-root marker)"
    )
    ap.add_argument(
        "--ollama-url", default=OLLAMA_BASE_URL,
        help=f"Ollama base URL (default: {OLLAMA_BASE_URL})"
    )
    ap.add_argument(
        "--timeout", type=int, default=OLLAMA_TIMEOUT,
        help=f"Ollama request timeout in seconds (default: {OLLAMA_TIMEOUT})"
    )
    ap.add_argument(
        "--out", default="",
        help="Write extracted topics as JSON array to this file."
    )
    return ap.parse_args()

def _resolve_root(cli_root):
    """Resolve SOVEREIGN root via the single authority (tools/sovereign_paths.py)."""
    repo = Path(__file__).resolve().parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from tools.sovereign_paths import get_repo_root, configure_root
    return str(configure_root(str(cli_root)) if cli_root else get_repo_root())


def main() -> int:
    args = _parse_args()
    args.root = _resolve_root(args.root)

    if not os.path.isfile(args.path):
        print(f"[{MODULE_NAME}] [ERROR] file not found: {args.path}", file=sys.stderr)
        return 1

    topics = extract_topics(
        path=args.path,
        root=args.root,
        base_url=args.ollama_url,
        timeout_sec=args.timeout,
    )

    output = json.dumps(topics, ensure_ascii=False, indent=2)
    print(output)

    if args.out:
        out_path = Path(args.out)
        _write_text_atomic(out_path, output)
        print(f"Topics written to: {args.out}", file=sys.stderr)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())



