"""Shared fixtures/helpers for the source-only remediation regression pack (CR-001..CR-039).

This pack is a NEW, minimal, high-value regression surface added to make the punch-list
corrections executable (CR-030). It does not restore the removed historical suite.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from control_plane.policy import Identity


def verdict(allow: bool, reason: str = "denied") -> SimpleNamespace:
    return SimpleNamespace(allow=allow, reason=reason)


class StubPolicy:
    """Minimal policy double: MemoryService only consults .allow / .reason. Lets a test decide
    authorization outcomes without pulling in the full role/scope engine, so persistence-order and
    integrity behaviour can be tested in isolation."""

    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow
        self.publish_calls = 0
        self.artifact_calls = 0

    def authorize_publish(self, identity: Identity, entry: dict[str, Any]) -> SimpleNamespace:
        self.publish_calls += 1
        return verdict(self.allow)

    def authorize_put_artifact(self, identity: Identity, project_id: str) -> SimpleNamespace:
        self.artifact_calls += 1
        return verdict(self.allow)

    def authorize_transition(self, identity, current, requested_status) -> SimpleNamespace:
        return verdict(self.allow)

    def authorize_read(self, identity, kind, project_id, status) -> SimpleNamespace:
        return verdict(self.allow)

    def authorize_read_entry(self, identity, entry) -> SimpleNamespace:
        return verdict(self.allow)

    def authorize_health(self, identity) -> SimpleNamespace:
        return verdict(True)


def sample_identity() -> Identity:
    return Identity(node_id="node-a", role="worker", project_id="proj-1")


def sample_provenance(**over: Any) -> dict[str, Any]:
    prov = {
        "author_node": "node-a",
        "task_id": None,
        "ts": "2026-09-15T00:00:00+00:00",
        "directive_version": "1.0",
        "confidence": "high",
    }
    prov.update(over)
    return prov
