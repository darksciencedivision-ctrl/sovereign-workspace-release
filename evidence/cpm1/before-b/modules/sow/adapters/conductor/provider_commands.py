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
        # G26 Option 0 (operator, 2026-08-26T00:46Z): codex 0.149's FLAG parser rejects
        # "never" but the CONFIG channel still carries the same policy. Transport
        # change only - the governed policy is unchanged.
        "--config", "approval_policy=never",
    ]


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
