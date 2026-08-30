"""Provider-specific command construction for the shared conductor lifecycle."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from adapters import detect
from adapters.frontier.claude_code import (
    CLAUDE_CODE_ADAPTER,
    build_interactive_command,
    is_credential_env_key as is_claude_credential,
    resolve_claude_model_ref,
)
from adapters.frontier.codex import (
    CODEX_ADAPTER,
    SANDBOX_READ_ONLY,
    build_interactive_codex_command,
    is_credential_env_key as is_codex_credential,
    resolve_codex_model_ref,
)
from adapters.local.ollama_session import (
    OLLAMA_LOCAL_ADAPTER,
    build_interactive_ollama_command,
)
from node_runtime.supervisor.codex_spawn import capability_for_codex
from node_runtime.supervisor.frontier_spawn import capability_for_claude_code


class ConductorProviderUnavailable(Exception):
    """The selected provider executable is not installed/resolvable."""


@dataclass(frozen=True)
class ConductorProviderCommands:
    adapter_id: str
    executable_name: str
    resolve_executable: Callable[[], str | None]
    capability: Callable[[], Any]
    resolve_model: Callable[[str | None], tuple[str | None, str]]
    build_command: Callable[[str, str | None, str], list[str]]


def _claude_command(executable: str, model: str | None, _workspace: str) -> list[str]:
    return build_interactive_command(executable, model=model)


def _codex_command(executable: str, model: str | None, workspace: str) -> list[str]:
    return [
        *build_interactive_codex_command(
            executable, model=model, sandbox=SANDBOX_READ_ONLY, workdir=workspace),
        # The Electron pane owns a long-lived governed session. A startup self-update can replace
        # the binary and exit before readiness, so centrally managed acceptance pins the documented
        # startup check off for this invocation. This does not alter model, sandbox, or approvals.
        "--config", "check_for_update_on_startup=false",
        "--ask-for-approval", "untrusted",
    ]


def _ollama_command(executable: str, model: str | None, _workspace: str) -> list[str]:
    """`ollama run <tag>` — an interactive local conductor session.

    No workspace argument: `ollama run` takes none, and the conductor's workspace binding is carried
    by the descriptor and the ConPTY's cwd rather than by argv. No prompt argument either — a
    trailing positional would make it one-shot, and the conductor pane is a session the operator
    types into.
    """
    if not model or not model.strip():
        raise ConductorProviderUnavailable(
            "a local conductor session needs a model tag — `ollama run` has no default model to "
            "fall back to, so there is nothing honest to launch (fail closed)")
    return build_interactive_ollama_command(executable, model=model)


def _resolve_local_model(requested: str | None) -> tuple[str | None, str]:
    """A local tag is carried VERBATIM and is never defaulted.

    The frontier resolvers may return `None` to mean "use the CLI's own default model, and RECORD
    that fallback". `ollama run` has no such default — it is `ollama run <tag>` or nothing — so a
    missing tag is an error here rather than a silently different model. This is the same honesty
    rule (§11 15B, never silent) reaching the opposite conclusion because the runtime differs.
    """
    tag = (requested or "").strip()
    if not tag:
        return None, ("no local model tag requested — `ollama run` has no default model, so nothing "
                      "can be launched (fail closed)")
    return tag, f"local model {tag!r} (an `ollama list` tag on this host)"


def capability_for_ollama_local() -> Any:
    """The conductor-seat capability for a local model.

    Deliberately the mirror image of `ConductorAdapter.capability()`'s frontier declaration: a local
    conductor is offline-eligible, needs no network, runs a local runtime, and is NOT
    subscription-backed. `node_class` stays `conductor` — the seat is the role, not the vendor.
    """
    from adapters.base.contract import AdapterCapability  # noqa: PLC0415

    return AdapterCapability(
        adapter=OLLAMA_LOCAL_ADAPTER, node_class="conductor", locality="local",
        offline_profile_eligible=True, requires_network=False, local_runtime=True,
        capabilities=("reasoning", "synthesis"), subscription_backed=False,
    )


_COMMANDS: dict[str, ConductorProviderCommands] = {
    CLAUDE_CODE_ADAPTER: ConductorProviderCommands(
        adapter_id=CLAUDE_CODE_ADAPTER,
        executable_name="claude",
        resolve_executable=detect.claude_code_executable,
        capability=capability_for_claude_code,
        resolve_model=resolve_claude_model_ref,
        build_command=_claude_command,
    ),
    CODEX_ADAPTER: ConductorProviderCommands(
        adapter_id=CODEX_ADAPTER,
        executable_name="codex",
        resolve_executable=detect.codex_executable,
        capability=lambda: capability_for_codex("reasoning"),
        resolve_model=resolve_codex_model_ref,
        build_command=_codex_command,
    ),
    # LOCAL-01 F-3 / ENTRY 018. The conductor seat is AGNOSTIC: this table held exactly two
    # frontier adapters, so `commands_for('ollama_local')` raised and no local model could ever
    # back the conductor. That was the hardcode D-3 identified.
    OLLAMA_LOCAL_ADAPTER: ConductorProviderCommands(
        adapter_id=OLLAMA_LOCAL_ADAPTER,
        executable_name="ollama",
        resolve_executable=detect.ollama_executable,
        capability=capability_for_ollama_local,
        resolve_model=_resolve_local_model,
        build_command=_ollama_command,
    ),
}


def commands_for(adapter_id: str) -> ConductorProviderCommands:
    try:
        return _COMMANDS[adapter_id]
    except KeyError as exc:
        raise ConductorProviderUnavailable(
            f"adapter {adapter_id!r} has no registered conductor command adapter") from exc


def credential_scrub_names() -> list[str]:
    return sorted(k for k in os.environ if is_claude_credential(k) or is_codex_credential(k))


def scrubbed_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    for name in list(env):
        if is_claude_credential(name) or is_codex_credential(name):
            env.pop(name, None)
    return env
