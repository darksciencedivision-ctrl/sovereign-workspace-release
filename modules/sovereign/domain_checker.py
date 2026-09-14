# domain_checker.py - SOVEREIGN Phase 8 (3/6)
#
# Reads <root>\corpus\domain.txt once per process, embeds it via
# Ollama embedding model from SYSTEM_MANIFEST.json, cached in memory.
# Accepts a topic string. Embeds it. Computes cosine similarity against
# the cached domain embedding. Returns an approval decision.
#
# Return schema (frozen):
#   { "approved": bool, "score": float, "topic": str }
#
# Threshold: 0.70 — topics scoring below this are rejected.
# There is no override flag for domain checking.
#
# All decisions (approved and rejected) are logged to:
#   <root>\logs\domain_check_log.txt
#
# Process-lifetime embedding cache:
#   domain.txt is embedded once and held in a module-level variable.
#   The cache is invalidated if domain.txt changes (mtime + size + content hash).
#
# UTF-8 without BOM. Windows paths. No cloud APIs. Ollama local only.

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from system_manifest import load_system_manifest, model_name, runtime_value


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PHASE8_VERSION    = "phase8-1.0"
MODULE_NAME       = "DOMAIN_CHECKER"
# Root is portable (resolved relative to this module); the manifest read is guarded so
# importing this module always reaches argument parsing, even on a relocated/misconfigured
# install. The active root is resolved via tools/sovereign_paths.py in main().
DEFAULT_ROOT      = str(Path(__file__).resolve().parent)
_MANIFEST_ERROR: Optional[str] = None
try:
    _MANIFEST         = load_system_manifest()
    OLLAMA_BASE_URL   = str(runtime_value("OLLAMA_BASE_URL", _MANIFEST)).strip()
    EMBED_MODEL       = model_name("EMBEDDING_MODEL", _MANIFEST)
except Exception as _exc:  # noqa: BLE001 - import must stay non-fatal (argparse must be reachable)
    # F-122: keep IMPORT non-fatal, but do NOT silently send EMBED_MODEL="" to Ollama (a broken
    # /api/embeddings call). Record the error and raise loudly at the point of use.
    _MANIFEST         = {}
    OLLAMA_BASE_URL   = "http://127.0.0.1:11434"
    EMBED_MODEL       = ""
    _MANIFEST_ERROR   = repr(_exc)


def _require_embed_model() -> str:
    if not EMBED_MODEL:
        raise RuntimeError(
            "DOMAIN_CHECKER cannot run: no embedding model is configured. The system manifest "
            "could not be loaded" + (f" ({_MANIFEST_ERROR})" if _MANIFEST_ERROR else "") +
            ". Resolve the SOVEREIGN root / SYSTEM_MANIFEST.json before checking domains."
        )
    return EMBED_MODEL
LOG_DIR           = "logs"
BUILD_LOG         = "corpus_build_log.txt"
DOMAIN_CHECK_LOG  = "domain_check_log.txt"
DOMAIN_FILENAME   = "domain.txt"
CORPUS_SUBDIR     = "corpus"

DOMAIN_THRESHOLD  = 0.70   # topics below this score are rejected; no override
try:
    OLLAMA_TIMEOUT    = int(runtime_value("EMBEDDING_TIMEOUT_SECONDS", _MANIFEST))
except Exception:
    OLLAMA_TIMEOUT    = 30

# Defense-in-depth: clamp topic text before embedding/logging.
TOPIC_MAX_EMBED_CHARS = 400
MAX_LOG_BYTES         = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Module-level embedding cache
# ---------------------------------------------------------------------------
# Tuple of (domain_text, mtime_ns, size_bytes, domain_sha256, embedding_vector)
# Invalidated when mtime/size change OR content hash changes.

_domain_cache: Optional[Tuple[str, int, int, str, List[float]]] = None


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _build_log_path(root: str) -> str:
    return os.path.join(root, LOG_DIR, BUILD_LOG)

def _domain_check_log_path(root: str) -> str:
    return os.path.join(root, LOG_DIR, DOMAIN_CHECK_LOG)

def _domain_txt_path(root: str) -> str:
    return os.path.join(root, CORPUS_SUBDIR, DOMAIN_FILENAME)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _ts() -> str:
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


def _append_log_line(path: str, line: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _rotate_log_if_needed(path)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _log(root: str, msg: str, level: Optional[str] = None) -> None:
    lvl = (level or "").upper().strip()
    if lvl not in {"INFO", "WARN", "ERROR"}:
        lowered = (msg or "").strip().lower()
        if lowered.startswith("error"):
            lvl = "ERROR"
        elif lowered.startswith("warning"):
            lvl = "WARN"
        else:
            lvl = "INFO"

    line = f"[{_ts()}] [{MODULE_NAME}] [{lvl}] {msg}"
    lp = _build_log_path(root)
    try:
        _append_log_line(lp, line)
    except OSError as exc:
        print(f"[{MODULE_NAME}] [WARN] build log write failed: {exc}", file=sys.stderr)
    print(line)


def _safe_one_line(s: str) -> str:
    """Prevent multi-line log injection and keep logs readable."""
    return " ".join((s or "").splitlines()).strip()


def _log_decision(root: str, topic: str, score: float, approved: bool) -> None:
    """
    Append one decision record to domain_check_log.txt.
    Log is append-only and human-readable.
    """
    verdict = "APPROVED" if approved else "REJECTED"
    topic_1 = _safe_one_line(topic)
    line = f"[{_ts()}] [{MODULE_NAME}] [INFO] decision={verdict} score={score:.4f} topic={topic_1}"
    lp = _domain_check_log_path(root)
    try:
        _append_log_line(lp, line)
    except OSError as exc:
        print(f"[{MODULE_NAME}] [WARN] domain check log write failed: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Ollama embedding call
# ---------------------------------------------------------------------------

def _ollama_embed(text: str, root: str, base_url: str, timeout_sec: int) -> Optional[List[float]]:
    """
    Call Ollama /api/embeddings with the manifest-configured embedding model.
    Returns a float list (the embedding vector), or None on any error.
    """
    payload = {
        "model":  _require_embed_model(),
        "prompt": text,
    }

    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        return None

    url = base_url.rstrip("/") + "/api/embeddings"

    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError) as exc:
        err = f"{type(exc).__name__}: {exc}"
        _log(root, f"embedding request to {url} failed: {err}", "WARN")
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        _log(root, f"embedding response JSON decode failed: {type(exc).__name__}: {exc}", "WARN")
        return None

    if not isinstance(data, dict):
        return None

    embedding = data.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        return None

    try:
        return [float(v) for v in embedding]
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Compute cosine similarity between two equal-length float vectors.
    Returns 0.0 if either vector is zero-magnitude or lengths differ.
    Result is clamped to [-1.0, 1.0] to guard against floating-point drift.
    """
    if len(a) != len(b) or not a:
        return 0.0

    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))

    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0

    raw = dot / (mag_a * mag_b)
    return max(-1.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# Domain embedding — load + cache
# ---------------------------------------------------------------------------

def _sha256_text(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()

def _load_domain_text(root: str) -> Optional[str]:
    """Read domain.txt. Returns None on IO error or missing/empty file."""
    path = _domain_txt_path(root)
    if not os.path.isfile(path):
        _log(root, f"domain.txt not found at {path}", "ERROR")
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read().strip()
        if not text:
            _log(root, f"domain.txt exists but is empty at {path}", "ERROR")
            return None
        return text
    except OSError as exc:
        _log(root, f"could not read domain.txt at {path}: {exc}", "ERROR")
        return None

def _domain_file_stat(root: str) -> Tuple[int, int]:
    """Return (mtime_ns, size_bytes) for domain.txt, or (0, 0) on error."""
    path = _domain_txt_path(root)
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)

def _get_domain_embedding(
    root:        str,
    base_url:    str,
    timeout_sec: int,
) -> Optional[List[float]]:
    """
    Return the domain embedding, using the module-level cache when valid.

    Cache is considered valid when:
      - It exists
      - domain.txt mtime_ns and size_bytes are unchanged since last embed
      - domain.txt content hash (sha256) is unchanged

    If domain.txt has changed (or was never embedded), re-embeds and updates
    the cache.
    """
    global _domain_cache

    mtime_ns, size_bytes = _domain_file_stat(root)

    # Quick cache hit check (mtime/size)
    if (
        _domain_cache is not None
        and _domain_cache[1] == mtime_ns
        and _domain_cache[2] == size_bytes
    ):
        return _domain_cache[4]

    # Load current domain text
    domain_text = _load_domain_text(root)
    if not domain_text:
        return None

    domain_hash = _sha256_text(domain_text)

    # Strong cache hit check (content hash)
    if (
        _domain_cache is not None
        and _domain_cache[3] == domain_hash
    ):
        # Even if mtime/size changed weirdly, content is identical: reuse embedding.
        _domain_cache = (domain_text, mtime_ns, size_bytes, domain_hash, _domain_cache[4])
        return _domain_cache[4]

    _log(root, f"Embedding domain.txt ({len(domain_text)} chars)...")
    embedding = _ollama_embed(domain_text, root, base_url, timeout_sec)

    if embedding is None:
        _log(root, "Ollama embedding call failed for domain.txt.", "ERROR")
        return None

    _domain_cache = (domain_text, mtime_ns, size_bytes, domain_hash, embedding)
    _log(root, f"Domain embedding cached. Vector length: {len(embedding)}.")
    return embedding


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_topic(
    topic:       str,
    root:        str = DEFAULT_ROOT,
    base_url:    str = OLLAMA_BASE_URL,
    timeout_sec: int = OLLAMA_TIMEOUT,
) -> Dict:
    """
    Check whether a topic string is within the research domain.

    Returns:
        { "approved": bool, "score": float, "topic": str }

    On any Ollama failure, returns approved=False, score=0.0 and logs.
    Never raises.
    """
    topic = (topic or "").strip()

    if not topic:
        _log(root, "check_topic called with empty topic string.", "WARN")
        result = {"approved": False, "score": 0.0, "topic": topic}
        _log_decision(root, topic, 0.0, False)
        return result

    # Clamp the text used for embedding/logging to avoid pathological input
    topic_for_embed = topic
    if len(topic_for_embed) > TOPIC_MAX_EMBED_CHARS:
        topic_for_embed = topic_for_embed[:TOPIC_MAX_EMBED_CHARS].rstrip() + "\u2026"

    # Step 1: domain embedding
    domain_vec = _get_domain_embedding(root, base_url, timeout_sec)
    if domain_vec is None:
        _log(root, f"REJECTED (domain embedding unavailable): {_safe_one_line(topic_for_embed)[:120]}")
        result = {"approved": False, "score": 0.0, "topic": topic}
        _log_decision(root, topic_for_embed, 0.0, False)
        return result

    # Step 2: topic embedding
    topic_vec = _ollama_embed(topic_for_embed, root, base_url, timeout_sec)
    if topic_vec is None:
        _log(root, f"REJECTED (topic embedding failed): {_safe_one_line(topic_for_embed)[:120]}")
        result = {"approved": False, "score": 0.0, "topic": topic}
        _log_decision(root, topic_for_embed, 0.0, False)
        return result

    # Step 3: similarity
    if len(domain_vec) != len(topic_vec):
        _log(root, f"REJECTED (embedding length mismatch) "
                   f"domain={len(domain_vec)} topic={len(topic_vec)}: {_safe_one_line(topic_for_embed)[:120]}")
        result = {"approved": False, "score": 0.0, "topic": topic}
        _log_decision(root, topic_for_embed, 0.0, False)
        return result

    score = _cosine_similarity(domain_vec, topic_vec)
    score = round(score, 6)

    # Step 4: decision
    approved = score >= DOMAIN_THRESHOLD

    # Step 5: logging
    verdict = "APPROVED" if approved else "REJECTED"
    _log(root, f"{verdict} score={score:.4f} threshold={DOMAIN_THRESHOLD}: {_safe_one_line(topic_for_embed)[:120]}")
    _log_decision(root, topic_for_embed, score, approved)

    return {"approved": approved, "score": score, "topic": topic}


def check_topics_batch(
    topics:      List[str],
    root:        str = DEFAULT_ROOT,
    base_url:    str = OLLAMA_BASE_URL,
    timeout_sec: int = OLLAMA_TIMEOUT,
) -> List[Dict]:
    """
    Check a list of topics against the domain.
    Returns a list of result dicts in the same order as the input.
    Domain embedding is loaded once and reused for all topics in the batch.
    """
    return [
        check_topic(t, root=root, base_url=base_url, timeout_sec=timeout_sec)
        for t in topics
    ]


def invalidate_domain_cache() -> None:
    """Force re-embedding of domain.txt on next check_topic call."""
    global _domain_cache
    _domain_cache = None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args():
    import argparse
    ap = argparse.ArgumentParser(
        description="SOVEREIGN Phase 8 — domain_checker.py: check topics against domain.txt."
    )
    ap.add_argument(
        "topics", nargs="*",
        help="Topic string(s) to check. If omitted, reads one per line from stdin."
    )
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
        help=f"Ollama timeout in seconds (default: {OLLAMA_TIMEOUT})"
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

    # Collect topics
    if args.topics:
        topics = args.topics
    else:
        topics = [line.rstrip("\n") for line in sys.stdin if line.strip()]

    if not topics:
        print(f"[{MODULE_NAME}] [ERROR] No topics provided.", file=sys.stderr)
        return 1

    results = []
    for topic in topics:
        r = check_topic(
            topic,
            root        = args.root,
            base_url    = args.ollama_url,
            timeout_sec = args.timeout,
        )
        results.append(r)

    print(json.dumps(results, ensure_ascii=False, indent=2))

    approved = sum(1 for r in results if r["approved"])
    print(
        f"\n{approved}/{len(results)} approved at threshold={DOMAIN_THRESHOLD}.",
        file=sys.stderr
    )

    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main())



