"""W-33 — MCP tool arguments are validated against the DECLARED inputSchema before dispatch.

R-11, CONFIRMED live on this host: ``spawn_worker {"bogus":"x","cmd":"rm -rf /"}`` was forwarded
verbatim to the application with ``isError: false``. Every tool already publishes an ``inputSchema``
carrying ``required`` and ``additionalProperties: false`` — the contract was declared to every
client and enforced against none of them.

WHY THIS IS NOT AUTHORIZATION LOGIC (invariant 7: MCP is access, not authority). Nothing here
decides WHO may call WHAT. It checks that the arguments match the shape this server already
advertises, and refuses the call otherwise. The schemas are already in this module; the defect was
that they were documentation rather than a gate.

WHY IT MUST BE BEFORE DISPATCH. A handler that receives an unvalidated dict defends itself with
``args.get(name, default)``, and a DEFAULT is the dangerous half: ``publish_progress`` without a
``status`` must be REFUSED, not quietly given one, because a defaulted lifecycle transition is a
state change nobody requested. These tests therefore assert through ``handle_request`` — the real
JSON-RPC entry point — so a refusal that happened after the handler already acted would fail.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcp_server.sovereign_tools import TOOLS, SovereignToolRuntime, handle_request


class _RecordingApp:
    """Stands in for the Electron application surface, and RECORDS whether it was reached.

    The point of the unit is that a malformed call never gets this far, so the assertion is on
    ``calls`` being empty rather than only on the returned error.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def identity_details(self) -> dict[str, str]:
        return {"node_id": "cond-1", "role": "conductor", "project_id": "proj"}

    def call(self, operation: str, arguments: dict[str, Any] | None = None) -> Any:
        self.calls.append((operation, dict(arguments or {})))
        return {"ok": True}


@pytest.fixture()
def runtime(tmp_path: Path):
    from control_plane.policy import SovereignPolicy

    rt = SovereignToolRuntime(_RecordingApp(), tmp_path, policy=SovereignPolicy())
    yield rt
    rt.close()


def _call(rt: SovereignToolRuntime, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return handle_request(rt, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })


def test_spawn_worker_refuses_an_undeclared_argument(runtime: SovereignToolRuntime) -> None:
    """NEGATIVE, R-11 exactly as measured: the reviewer's payload, refused."""
    res = _call(runtime, "spawn_worker", {"bogus": "x", "cmd": "rm -rf /"})
    assert res["result"]["isError"] is True, "an undeclared argument must not reach the application"
    assert runtime.app.calls == [], "the application was called with unvalidated arguments"


def test_publish_progress_without_status_is_REFUSED_not_defaulted(runtime: SovereignToolRuntime) -> None:
    """NEGATIVE: a missing required field must refuse, never acquire a default.

    ``status`` drives the task lifecycle. Defaulting it would move a shared task to a state no
    caller asked for, which is a durable record of something that did not happen.
    """
    res = _call(runtime, "publish_progress", {"task_id": "t-1"})
    assert res["result"]["isError"] is True
    text = str(res["result"])
    assert "status" in text, "the refusal must NAME the missing field, not fail opaquely"


def test_a_declared_enum_is_enforced(runtime: SovereignToolRuntime) -> None:
    """NEGATIVE: the schema publishes the legal lifecycle values; an illegal one is refused."""
    res = _call(runtime, "publish_progress", {"task_id": "t-1", "status": "TOTALLY_DONE"})
    assert res["result"]["isError"] is True


def test_a_declared_type_is_enforced(runtime: SovereignToolRuntime) -> None:
    """NEGATIVE: `worker_node_ids` is an array of strings, not a string."""
    res = _call(runtime, "assign_task", {"objective": "x", "worker_node_ids": "not-an-array"})
    assert res["result"]["isError"] is True
    assert runtime.app.calls == []


def test_a_well_formed_call_still_reaches_the_application(runtime: SovereignToolRuntime) -> None:
    """POSITIVE: validation must not become a wall. A valid spawn_worker still dispatches.

    This runs and passes BEFORE the repair too, which is the point: it is regression cover for the
    working path, not a new claim.
    """
    res = _call(runtime, "spawn_worker",
                {"provider": "ollama", "model_id": "qwen3:8b", "role": "reasoning"})
    assert res["result"]["isError"] is False
    assert runtime.app.calls and runtime.app.calls[0][0] == "spawn_worker"


def test_every_declared_tool_has_a_schema_this_validator_can_read() -> None:
    """A validator that silently skips a shape it does not understand is worse than none.

    Rather than trusting that the hand-written subset covers today's schemas, this walks every
    declared tool and fails on any construct the validator does not implement — so a future schema
    using a new keyword fails HERE rather than being waved through at runtime.
    """
    from mcp_server.sovereign_tools import _UNDERSTOOD_SCHEMA_KEYWORDS, _walk_schema_keywords

    unknown: dict[str, set[str]] = {}
    for tool in TOOLS:
        used = _walk_schema_keywords(tool["inputSchema"])
        extra = used - _UNDERSTOOD_SCHEMA_KEYWORDS
        if extra:
            unknown[tool["name"]] = extra
    assert not unknown, f"schema keywords no validator implements: {unknown}"
