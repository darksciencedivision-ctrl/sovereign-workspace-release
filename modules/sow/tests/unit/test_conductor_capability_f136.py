"""F-136(2) — conductor capability follows the backing runtime."""
from __future__ import annotations

from adapters.base.contract import AdapterContext
from adapters.base.mock_backend import MockReasoningBackend
from adapters.conductor.adapter import ConductorAdapter


def _ctx(**kwargs):
    values = dict(
        node_id="c1", role="conductor", project_id="p",
        permission_profile_id="pp", mcp_credential_id="mcp-ref",
        subscription_ref="sub", spawned_by_supervisor=True)
    values.update(kwargs)
    return AdapterContext(**values)


def test_default_mock_stays_frontier_fable5():
    cap = ConductorAdapter(_ctx(), mcp_client=None, backend=MockReasoningBackend()).capability()
    assert cap.adapter == "conductor_fable5"
    assert cap.locality == "frontier"
    assert cap.subscription_backed is True


def test_ollama_backend_is_local():
    class OllamaConductorBackend:
        pass
    cap = ConductorAdapter(
        _ctx(subscription_ref=""), mcp_client=None,
        backend=OllamaConductorBackend()).capability()
    assert cap.adapter == "conductor_ollama_local"
    assert cap.locality == "local"
    assert cap.subscription_backed is False
