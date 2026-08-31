"""EPC-02 A-4 — the conductor gets a second implementation of its own interface.

`adapters/conductor/adapter.py` opens by declaring the conductor is an INTERFACE (I-CN1).
Measured in A-1, only one implementation existed and it was the Claude Code CLI, a frontier
provider: the live spawn path raises `ClaudeCliUnavailable` without it, and a conductor built
without an explicit backend falls back to a deterministic mock. Meanwhile the registry already
DERIVED local conductor seats from the operator's model ceiling — the system offered a seat no
code path could fill.

`OllamaConductorBackend` fills it. These tests hold the properties that make it the same
interface rather than a parallel one, and they use an injected fake backend throughout: no
daemon is contacted, no model is loaded, and the suite stays deterministic.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from adapters.frontier.claude_code import ClaudeCodeConductorBackend  # noqa: E402
from adapters.local.conductor_backend import (  # noqa: E402
    LOCAL_CONDUCTOR_MAX_TOKENS,
    OllamaConductorBackend,
)

STRUCTURED = json.dumps({
    "proposed_tasks": [
        {"desc": "Read the constitution", "capability": "analysis"},
        {"desc": "Summarise the canonical boundaries", "capability": "analysis", "deps": [1]},
    ]
})


class FakeBackend:
    """Stands in for OllamaBackend. Records what it was asked, returns what it was told to."""

    def __init__(self, reply: str = STRUCTURED, reported: str | None = "qwen3:8b") -> None:
        self.name = "ollama:qwen3:8b"
        self.reply = reply
        self.last_reported_model = reported
        self.prompts: list[str] = []
        self.max_tokens: list[int] = []

    def generate(self, prompt: str, max_tokens: int = 256) -> str:
        self.prompts.append(prompt)
        self.max_tokens.append(max_tokens)
        return self.reply


class ItImplementsTheConductorInterface(unittest.TestCase):

    def test_it_exposes_exactly_what_the_adapter_binds(self) -> None:
        """The ConductorAdapter reads these three. A missing one is a broken interface, not a
        missing feature."""
        backend = OllamaConductorBackend("qwen3:8b", backend=FakeBackend())
        for attribute in ("model_name", "calls", "propose_plan", "wrapped_backend"):
            self.assertTrue(hasattr(backend, attribute), attribute)

    def test_its_decision_has_the_same_keys_as_the_frontier_binding(self) -> None:
        """Two implementations of one interface must produce the same decision shape, or the
        conductor behaves differently depending on which model backs it — the exact thing an
        interface exists to prevent."""
        local = OllamaConductorBackend("qwen3:8b", backend=FakeBackend())
        frontier = ClaudeCodeConductorBackend(FakeBackend(), model_name="claude:test")
        files = {"ROLE.md": "ref-1", "IDENTITY.md": "ref-2"}
        self.assertEqual(
            set(local.propose_plan("objective", files, 1)),
            set(frontier.propose_plan("objective", files, 1)),
        )

    def test_it_counts_its_calls(self) -> None:
        backend = OllamaConductorBackend("qwen3:8b", backend=FakeBackend())
        self.assertEqual(backend.calls, 0)
        backend.propose_plan("o", {}, 1)
        backend.propose_plan("o", {}, 2)
        self.assertEqual(backend.calls, 2)


class ItParsesFailClosed(unittest.TestCase):

    def test_a_structured_reply_yields_the_tasks_the_model_proposed(self) -> None:
        backend = OllamaConductorBackend("qwen3:8b", backend=FakeBackend(STRUCTURED))
        decision = backend.propose_plan("Summarise the boundaries", {"ROLE.md": "r"}, 3)
        self.assertEqual(decision["parse_mode"], "structured")
        self.assertEqual(len(decision["proposed_tasks"]), 2)
        self.assertEqual(decision["cycle"], 3)
        self.assertEqual(decision["files_considered"], ["ROLE.md"])

    def test_prose_yields_NO_tasks_rather_than_invented_ones(self) -> None:
        """A conductor decision never fabricates a decomposition the model did not produce.
        Zero tasks and an honest `unstructured` beats a plausible guess."""
        backend = OllamaConductorBackend("qwen3:8b",
                                         backend=FakeBackend("1. do a thing\n2. do another"))
        decision = backend.propose_plan("o", {}, 1)
        self.assertEqual(decision["parse_mode"], "unstructured")
        self.assertEqual(decision["proposed_tasks"], [])

    def test_the_operator_still_sees_what_the_model_said(self) -> None:
        """The raw excerpt is what makes an unstructured refusal actionable rather than opaque."""
        backend = OllamaConductorBackend("qwen3:8b", backend=FakeBackend("mumble mumble"))
        self.assertIn("mumble", backend.propose_plan("o", {}, 1)["raw_excerpt"])


class ItReportsTheExecutingModelHonestly(unittest.TestCase):

    def test_it_records_the_model_the_daemon_says_it_ran(self) -> None:
        backend = OllamaConductorBackend("qwen3:8b",
                                         backend=FakeBackend(reported="qwen3:8b"))
        decision = backend.propose_plan("o", {}, 1)
        self.assertTrue(decision["model_verified"])
        self.assertEqual(decision["model"], "qwen3:8b")

    def test_an_unreported_model_is_NOT_claimed_as_verified(self) -> None:
        """A CANDIDATE must never read as a confirmed checkpoint. With nothing reported, the
        decision falls back to the SELECTION label and says so."""
        backend = OllamaConductorBackend("qwen3:8b", backend=FakeBackend(reported=None))
        decision = backend.propose_plan("o", {}, 1)
        self.assertFalse(decision["model_verified"])
        self.assertEqual(decision["model"], decision["model_selection"])

    def test_the_selection_label_is_always_present(self) -> None:
        backend = OllamaConductorBackend("qwen3:8b", backend=FakeBackend(reported=None))
        self.assertEqual(backend.propose_plan("o", {}, 1)["model_selection"], "ollama:qwen3:8b")


class ItHoldsNoAuthorityAndNoCredential(unittest.TestCase):

    def test_it_asks_for_a_budget_large_enough_to_finish_a_plan(self) -> None:
        """A truncated plan is the failure that discarded six minutes of DEEP deliberation
        elsewhere in this programme (ENTRY 034). Here it would silently produce short plans."""
        fake = FakeBackend()
        OllamaConductorBackend("qwen3:8b", backend=fake).propose_plan("o", {}, 1)
        self.assertEqual(fake.max_tokens, [LOCAL_CONDUCTOR_MAX_TOKENS])
        self.assertGreaterEqual(LOCAL_CONDUCTOR_MAX_TOKENS, 1024)

    def test_it_refuses_to_be_built_without_a_model(self) -> None:
        for bad in ("", "   ", None):
            with self.assertRaises(ValueError):
                OllamaConductorBackend(bad)  # type: ignore[arg-type]

    def test_it_carries_no_credential_attribute(self) -> None:
        """Ollama is loopback-local and unauthenticated; a credential here would be a claim to
        authority the local path does not have and does not need."""
        backend = OllamaConductorBackend("qwen3:8b", backend=FakeBackend())
        for forbidden in ("credential", "api_key", "token", "subscription"):
            self.assertFalse(hasattr(backend, forbidden), forbidden)

    def test_it_proposes_and_does_not_promote(self) -> None:
        """Invariant 16. The decision is a proposal; nothing here accepts or promotes it."""
        decision = OllamaConductorBackend("qwen3:8b",
                                          backend=FakeBackend()).propose_plan("o", {}, 1)
        for verb in ("accepted", "promoted", "approved", "status"):
            self.assertNotIn(verb, decision)


if __name__ == "__main__":
    unittest.main()
