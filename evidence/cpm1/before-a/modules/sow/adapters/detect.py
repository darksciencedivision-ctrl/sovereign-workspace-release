"""Host capability detection (Phase 6). Detection only — never installs or pulls anything
(build prohibition). Used to decide whether a real local backend/harness is available or a
mock stands in; the decision is recorded in evidence, never hidden.
"""
from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request

OLLAMA_HOST = "http://127.0.0.1:11434"


def ollama_available(timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=timeout):
            return True
    except (urllib.error.URLError, OSError):
        return False


def ollama_models(timeout: float = 3.0) -> list[str]:
    """Model names the local daemon reports, VALIDATED. Never raises (W-36).

    The daemon's reply is input, not truth. Two defects lived here:

    * only `URLError`/`OSError`/`JSONDecodeError` were caught, so a well-formed JSON reply whose
      entries are not dicts (`TypeError`), or lack `name` (`KeyError`), or whose top level is not an
      object at all (`AttributeError` from `.get`) raised straight past the handler. A detection
      helper answering "is a local backend available" must not be able to take its caller down.
    * whatever names it returned travelled on unvalidated, and a model name eventually reaches a
      `--model` argument. `MODEL_SLUG_RE` is the project's existing answer to what a model name may
      look like and was simply not applied — so a name carrying a flag, whitespace or a shell
      metacharacter was passed along verbatim.

    The import is local, matching `grok_executable` above: this module sits BELOW the adapter
    package in the import order, and one shared rule is worth the local import — a private regex
    here would fork a decision the project already made, and the two copies would drift.

    Scope, not overstated: the daemon is on loopback, so this is not a remote attacker. It closes a
    malformed or upgraded daemon crashing the caller, and an unconstrained string moving toward an
    argv. The separate "no argv builder validates a `--model` value" surface is W-51.
    """
    from adapters.frontier.provider_cli_common import MODEL_SLUG_RE  # noqa: PLC0415

    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        entries = data.get("models", []) if isinstance(data, dict) else []
        names = [m.get("name") for m in entries if isinstance(m, dict)]
        return [n for n in names if isinstance(n, str) and MODEL_SLUG_RE.match(n)]
    except (urllib.error.URLError, OSError, json.JSONDecodeError,
            KeyError, TypeError, AttributeError):
        return []


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
