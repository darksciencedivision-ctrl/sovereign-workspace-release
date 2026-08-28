"""U53 discharge — a closed conductor cannot act (`phase-15d.gate`).

`phase-15d.succession`'s central claim is that the predecessor is GONE. The gate-validator found
that claim rested on the runner's discipline rather than on construction: `run_cycle` refused once
closed, but the two other MCP-touching methods beside it — `read_accepted` and
`publish_acceptance_packet` — did not. A corpse could still read project state and publish an
acceptance packet over MCP.

These tests pin the refusal at the adapter, which is where the fix belongs: every caller of a
closed conductor now fails closed, not just the callers that remembered to check.

RESIDUAL, not closed here and recorded in the register: `McpClient.call` auto-reconnects, so a
closed conductor's *client* can still re-establish a session. The refusal above is the adapter
declining to act; it is not the transport making action impossible.
"""
from __future__ import annotations

import pytest

from adapters.base.contract import AdapterContext
from adapters.conductor.adapter import CONDUCTOR_FILE_ORDER, ConductorAdapter, ConductorNotReady


class _RecordingMcp:
    """Answers the conductor file loads; records every call so a leak is visible, not inferred."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def call(self, op: str, **kw):
        self.calls.append(op)
        if op == "get_content":
            return {"content_b64": "eA=="}          # b"x"
        if op == "read_status":
            return [{"entry_id": "m-1", "status": "ACCEPTED"}]
        if op == "publish":
            return {"entry_id": "m-2"}
        raise AssertionError(f"unexpected op {op}")


def _adapter() -> tuple[ConductorAdapter, _RecordingMcp]:
    mcp = _RecordingMcp()
    ctx = AdapterContext(node_id="conductor-1", role="conductor", project_id="proj",
                         permission_profile_id="pp-conductor", mcp_credential_id="cred-1",
                         spawned_by_supervisor=True)
    adapter = ConductorAdapter(ctx, mcp,
                               conductor_file_refs={f: f"m-{f}" for f in CONDUCTOR_FILE_ORDER})
    return adapter, mcp


def test_a_live_conductor_can_read_and_publish():
    """The refusal must be about being CLOSED, not about being broken."""
    adapter, _ = _adapter()
    adapter.start()
    assert adapter.read_accepted() == [{"entry_id": "m-1", "status": "ACCEPTED"}]
    assert adapter.publish_acceptance_packet({"schema": "acceptance_packet@1.0"}) == "m-2"


def test_a_closed_conductor_cannot_read_project_state():
    adapter, mcp = _adapter()
    adapter.start()
    adapter.close()
    before = len(mcp.calls)
    with pytest.raises(ConductorNotReady):
        adapter.read_accepted()
    assert len(mcp.calls) == before, "the refusal must happen BEFORE the MCP call, not after"


def test_a_closed_conductor_cannot_publish_an_acceptance_packet():
    adapter, mcp = _adapter()
    adapter.start()
    adapter.close()
    before = len(mcp.calls)
    with pytest.raises(ConductorNotReady):
        adapter.publish_acceptance_packet({"schema": "acceptance_packet@1.0"})
    assert len(mcp.calls) == before, "nothing may reach MCP from a closed conductor"


def test_a_never_started_conductor_cannot_act_either():
    """`close()` is not the only way to be inactive — a conductor that never started never loaded
    its 12 governing files, so acting would bypass the conductor-file precondition entirely."""
    adapter, _ = _adapter()
    with pytest.raises(ConductorNotReady):
        adapter.read_accepted()
    with pytest.raises(ConductorNotReady):
        adapter.publish_acceptance_packet({"schema": "acceptance_packet@1.0"})


def test_is_active_and_the_refusal_agree():
    """`is_active` is what `phase-15d.succession` records as death evidence. If it and the refusal
    could disagree, the recorded evidence would describe a different conductor than the one the
    code is enforcing against."""
    adapter, _ = _adapter()
    adapter.start()
    assert adapter.is_active is True
    adapter.close()
    assert adapter.is_active is False
    with pytest.raises(ConductorNotReady):
        adapter.read_accepted()
