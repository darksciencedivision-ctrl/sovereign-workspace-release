"""Host capability detection (Phase 6). Detection only — never installs or pulls anything
(build prohibition). Used to decide whether a real local backend/harness is available or a
mock stands in; the decision is recorded in evidence, never hidden.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import urllib.error
import urllib.request

OLLAMA_HOST = "http://127.0.0.1:11434"
# llama.cpp's OpenAI-compatible server.  Both endpoints are loopback-only by default and can be
# changed for a separately managed local instance without introducing a cloud fallback.
LLAMACPP_HOST = os.environ.get("SOVEREIGN_LLAMACPP_HOST", "http://127.0.0.1:5183").rstrip("/")
# F-016. Loopback Ollama only; force a direct connection past any configured proxy.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def ollama_available(timeout: float = 3.0) -> bool:
    try:
        with _NO_PROXY_OPENER.open(f"{OLLAMA_HOST}/api/tags", timeout=timeout):
            return True
    except (urllib.error.URLError, OSError):
        return False


#: What a LOCAL Ollama tag may look like. Distinct from `MODEL_SLUG_RE`, deliberately — see
#: `ollama_model_records`. Adds `/` (the namespace separator in `sam860/dolphin3-llama3.2:3b`) and
#: `_` (present in `hf.co/bartowski/THUDM_GLM-4-32B-0414-GGUF:Q4_K_M`), and is longer because a
#: namespaced tag is. It still refuses whitespace, shell metacharacters, and a leading `-`, which
#: is the property that matters: this string ends up as an argv element in `ollama run <tag>`.
OLLAMA_TAG_RE = re.compile(r"^[A-Za-z0-9][\w.:@/-]{1,120}$")


def ollama_model_records(timeout: float = 3.0) -> list[dict]:
    """The daemon's FULL `/api/tags` rows, validated. Never raises (W-36).

    `ollama_models` returns names only, which is all its callers ever needed. The operator's 8B
    ceiling (ENTRY 017) needs each model's parameter count, capability list and on-disk size to
    decide admission and to say WHY when it refuses — and `/api/tags` already carries all three
    (`details.parameter_size`, `capabilities`, `size`). Reading them here keeps
    `adapters.local.model_ceiling` a pure function over records and keeps HTTP in the one module
    that owns host detection.

    Rows are returned verbatim apart from the name validation below; classification is not this
    module's decision.
    """
    try:
        with _NO_PROXY_OPENER.open(f"{OLLAMA_HOST}/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        entries = data.get("models", []) if isinstance(data, dict) else []
        rows = []
        for m in entries:
            if not isinstance(m, dict):
                continue
            name = m.get("name")
            if isinstance(name, str) and OLLAMA_TAG_RE.match(name):
                rows.append(m)
        return rows
    except (urllib.error.URLError, OSError, json.JSONDecodeError,
            KeyError, TypeError, AttributeError):
        return []


def ollama_models(timeout: float = 3.0) -> list[str]:
    """Model names the local daemon reports, VALIDATED. Never raises (W-36).

    The daemon's reply is input, not truth. Two defects lived here:

    * only `URLError`/`OSError`/`JSONDecodeError` were caught, so a well-formed JSON reply whose
      entries are not dicts (`TypeError`), or lack `name` (`KeyError`), or whose top level is not an
      object at all (`AttributeError` from `.get`) raised straight past the handler. A detection
      helper answering "is a local backend available" must not be able to take its caller down.
    * whatever names it returned travelled on unvalidated, and a model name eventually reaches a
      `--model` argument, so the shape of the name is checked before it travels.

    WHY NOT `MODEL_SLUG_RE` (LOCAL-01 D-5). It used to apply that regex, and doing so silently
    dropped **7 of this host's 60 installed models** — every namespaced tag, because
    `^[A-Za-z0-9][A-Za-z0-9._:@\\-]{1,80}$` admits neither `/` nor `_`. One of the seven,
    `sam860/dolphin3-llama3.2:3b`, is a 3.2B model well inside the operator's ceiling that the
    picker could never offer, and nothing anywhere reported the loss — the silent absence S-19
    forbids.

    `MODEL_SLUG_RE` is a **prose defence**: it exists so that parsing a frontier CLI's free TEXT
    output cannot turn a stray `Traceback` or a help sentence into a model id (its own comment says
    so, and W-44/W-45 record exactly that failure for `agy`). Ollama answers in **structured JSON**
    where `name` is a declared field, so there is no prose to defend against, and the property that
    actually matters — this string becomes an argv element — is preserved by `OLLAMA_TAG_RE`, which
    still refuses whitespace, metacharacters and a leading `-`. Sharing the frontier regex here was
    not one decision serving two callers; it was a text-parsing rule imposed on a JSON field, and
    it cost the operator seven models.

    Scope, not overstated: the daemon is on loopback, so this is not a remote attacker. It closes a
    malformed or upgraded daemon crashing the caller, and an unconstrained string moving toward an
    argv. The separate "no argv builder validates a `--model` value" surface is W-51.
    """
    return [m["name"] for m in ollama_model_records(timeout=timeout)]


def llamacpp_model_records(timeout: float = 3.0) -> list[dict]:
    """Return model ids reported by a local llama.cpp server.

    llama-server versions expose either the OpenAI ``/v1/models`` shape or the older ``/models``
    shape.  Parse both, validate ids, and return an empty list on any transport or payload error.
    This is detection only: it never downloads a model or contacts a non-loopback endpoint unless
    the operator explicitly configured one with ``SOVEREIGN_LLAMACPP_HOST``.
    """
    for path in ("/v1/models", "/models"):
        try:
            with _NO_PROXY_OPENER.open(f"{LLAMACPP_HOST}{path}", timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            entries = data.get("data", []) if isinstance(data, dict) else []
            if not entries and isinstance(data, dict):
                entries = data.get("models", [])
            rows: list[dict] = []
            for item in entries if isinstance(entries, list) else []:
                if isinstance(item, str):
                    model_id = item
                    item = {"id": item}
                elif isinstance(item, dict):
                    model_id = item.get("id") or item.get("name")
                else:
                    continue
                if isinstance(model_id, str) and model_id.strip() and not any(c.isspace() for c in model_id):
                    rows.append({**item, "name": model_id})
            if rows or path == "/models":
                return rows
        except (urllib.error.URLError, OSError, json.JSONDecodeError,
                TypeError, AttributeError):
            continue
    return []


def llamacpp_models(timeout: float = 3.0) -> list[str]:
    return [row["name"] for row in llamacpp_model_records(timeout=timeout)]


def llamacpp_available(timeout: float = 3.0) -> bool:
    return bool(llamacpp_model_records(timeout=timeout))


def llamacpp_executable() -> str | None:
    """Resolve a locally installed llama.cpp interactive CLI, if configured or on PATH."""
    import os
    configured = os.environ.get("SOVEREIGN_LLAMACPP_CLI", "").strip()
    if configured and shutil.which(configured):
        return shutil.which(configured)
    for name in ("llama-cli", "llama-cli.exe", "llama-cli.cmd"):
        found = shutil.which(name)
        if found:
            return found
    return None


def opencode_available() -> bool:
    return shutil.which("opencode") is not None or shutil.which("opencode.ps1") is not None


def claude_code_executable() -> str | None:
    """The RESOLVED absolute path of the first-party `claude` CLI, or None.

    Phase 17A `.pty`: the shell spawns this session in a ConPTY, and ConPTY takes a file — it does
    not repeat a PATH+PATHEXT search, so a bare "claude" (which is `claude.EXE` here) is simply "File
    not found". Resolving it in the same place that GATES its presence is also the governed answer:
    the shell executes exactly the binary the gate verified, rather than re-resolving a name in a
    different process with a different PATH. Detection only — never authenticates, never touches the
    credential store (§2.2)."""
    for name in ("claude", "claude.cmd", "claude.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def claude_code_available() -> bool:
    """Detect the first-party `claude` CLI on PATH (Phase 14B live frontier). Detection only —
    never authenticates, never touches the credential store (§2.2)."""
    return claude_code_executable() is not None


def ollama_executable() -> str | None:
    """The RESOLVED absolute path of the local `ollama` runtime binary, or None.

    Same reason `claude_code_executable` exists (Phase 17A `.pty`): a ConPTY spawn takes a FILE, not
    a PATH+PATHEXT search, and the shell must run exactly the binary whose presence was gated. The
    daemon check (`ollama_available`) answers a different question — a reachable daemon with no CLI
    on PATH cannot be launched into a pane. Detection only; touches no credential (a local model has
    none)."""
    for name in ("ollama", "ollama.exe", "ollama.cmd"):
        found = shutil.which(name)
        if found:
            return found
    return None


def codex_executable() -> str | None:
    """The RESOLVED absolute path of OpenAI's first-party `codex` CLI, or None. Windows npm shims
    are `codex.CMD`. Detection only — never authenticates, never reads the OAuth credential (§2.2)."""
    for name in ("codex", "codex.cmd", "codex.exe", "codex.ps1"):
        found = shutil.which(name)
        if found:
            return found
    return None


def codex_available() -> bool:
    """Detect OpenAI's first-party `codex` CLI on PATH (Phase 15C live frontier, OP-6). Detection
    only — never authenticates, never reads/transmits the OAuth credential (§2.2). Windows npm
    shims are `codex.CMD`; shutil.which honours PATHEXT so a bare `which('codex')` finds it, but
    the explicit variants keep the check robust across shells."""
    return (shutil.which("codex") is not None or shutil.which("codex.cmd") is not None
            or shutil.which("codex.exe") is not None or shutil.which("codex.ps1") is not None)


def _resolve_provider_executable(candidates: tuple[str, ...]) -> str | None:
    """First resolvable name among a backend's own `executable_candidates`, or None."""
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    return None


def grok_executable() -> str | None:
    """The RESOLVED absolute path of xAI's first-party `grok` CLI, or None (OP-12, 18B).

    Same contract as `claude_code_executable`: a ConPTY spawn takes a FILE, not a PATH+PATHEXT
    search, so the presence gate resolves the binary the shell will actually run. The candidate
    NAMES are read from `GrokCliBackend.executable_candidates` rather than re-spelled here — one
    list, so a Windows shim form added for the headless backend cannot be missing from the
    interactive presence gate (the U254 lesson applied to a second surface). The import is local
    because this module sits below the adapter package in the import order. Detection only: it
    never authenticates and never reads the xAI OAuth store (§13 / §2.2)."""
    from adapters.frontier.grok_build import GrokCliBackend  # noqa: PLC0415

    return _resolve_provider_executable(GrokCliBackend.executable_candidates)


def grok_available() -> bool:
    """Is the `grok` CLI on PATH? Presence ONLY — never an authentication claim (§6: the operator
    directive forbids inferring auth from the executable existing)."""
    return grok_executable() is not None


def antigravity_executable() -> str | None:
    """The RESOLVED absolute path of the Antigravity `agy` CLI, or None (OP-12, 18B). Detection
    only — never authenticates, never reads Google OAuth material or Credential Manager (§13)."""
    from adapters.frontier.antigravity import AntigravityCliBackend  # noqa: PLC0415

    return _resolve_provider_executable(AntigravityCliBackend.executable_candidates)


def antigravity_available() -> bool:
    """Is the `agy` CLI on PATH? Presence ONLY. This CLI has no offline auth surface at all, so
    presence is especially far from "signed in" — only a live probe can answer that (§6)."""
    return antigravity_executable() is not None


def pick_model(models: list[str], candidates: tuple[str, ...]) -> str | None:
    """Return the best available candidate. EXACT (family:tag) matches win over family-prefix
    matches, so a small-tier candidate is preferred and we don't silently bind an oversized
    same-family model when the requested tier is absent (spec-audit F2; I-22 8-14B tier)."""
    for want in candidates:                       # pass 1: exact tag match, in preference order
        if want in models:
            return want
    for want in candidates:                       # pass 2: family-prefix fallback (tier may differ)
        for have in models:
            if have.split(":")[0] == want.split(":")[0]:
                return have
    return None
