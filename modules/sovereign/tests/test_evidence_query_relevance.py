"""Product-state queries must retrieve citeable files; ordinary questions must not."""
from __future__ import annotations

import unittest
from pathlib import Path

from sovereign_product.evidence import EvidenceBuilder

SOV = Path(__file__).resolve().parents[1]
FROZEN = (
    "Using only the supplied project evidence, state which model is configured "
    "as the primary reasoner and where runtime state is kept. Cite each fact."
)
APPROVED = (
    "SYSTEM_MANIFEST.json",
    "README_PRODUCTION.md",
    "sovereign_version.py",
    "constitution/constitution_state.json",
    "constitution/constitution_v1.md",
    "synthesis/model_hierarchy.json",
    "runtime_profile.json",
)


class FrozenQueryRetrievesProductEvidence(unittest.TestCase):
    def setUp(self) -> None:
        present = [p for p in APPROVED if (SOV / p).is_file() and (SOV / p).stat().st_size > 0]
        self.builder = EvidenceBuilder(SOV, approved_paths=present, query_relevance=True)

    def _locators(self, query: str) -> set[str]:
        packet = self.builder.build("sess", query=query)
        return {source.locator.replace("\\", "/") for source in packet.sources}

    def test_frozen_acceptance_query_includes_manifest_and_state_location(self) -> None:
        packet = self.builder.build("sess-frozen", query=FROZEN)
        locators = {source.locator.replace("\\", "/") for source in packet.sources}
        self.assertIn("SYSTEM_MANIFEST.json", locators, packet.omissions)
        self.assertIn("README_PRODUCTION.md", locators, packet.omissions)
        self.assertIn("qwen2.5:3b-instruct", packet.text)
        self.assertIn("SovereignWorkspace", packet.text)
        self.assertGreater(packet.total_bytes, 0)

    def test_which_model_is_the_synthesizer(self) -> None:
        locators = self._locators("Which model is configured as the synthesizer?")
        self.assertIn("SYSTEM_MANIFEST.json", locators)

    def test_adversarial_challenger_role_phrase(self) -> None:
        locators = self._locators("What is the adversarial challenger?")
        self.assertIn("SYSTEM_MANIFEST.json", locators)

    def test_embedding_model_role_phrase(self) -> None:
        locators = self._locators("Which embedding model is configured?")
        self.assertIn("SYSTEM_MANIFEST.json", locators)

    def test_where_runtime_state_is_stored(self) -> None:
        packet = self.builder.build(
            "sess-state", query="Where is runtime state stored?"
        )
        locators = {source.locator.replace("\\", "/") for source in packet.sources}
        self.assertIn("README_PRODUCTION.md", locators, packet.omissions)
        self.assertIn("SovereignWorkspace", packet.text)

    def test_weather_query_still_retrieves_nothing(self) -> None:
        packet = self.builder.build("sess-weather", query="What is the weather in Paris?")
        self.assertEqual(packet.sources, ())
        self.assertEqual(packet.total_bytes, 0)

    def test_ordinary_critic_story_retrieves_nothing(self) -> None:
        packet = self.builder.build(
            "sess-critic", query="Tell me a story about a critic."
        )
        self.assertEqual(packet.sources, ())
        self.assertEqual(packet.total_bytes, 0)

    def test_praxis_query_still_retrieves_the_constitution(self) -> None:
        packet = self.builder.build("sess-praxis", query="What is the Praxis Answer?")
        locators = {source.locator.replace("\\", "/") for source in packet.sources}
        self.assertIn("constitution/constitution_v1.md", locators, packet.omissions)


if __name__ == "__main__":
    unittest.main()
