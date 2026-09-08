"""Frozen operator query must retrieve citeable product files, not an empty packet."""
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

    def test_frozen_acceptance_query_includes_manifest_and_state_location(self) -> None:
        packet = self.builder.build("sess-frozen", query=FROZEN)
        locators = {source.locator.replace("\\", "/") for source in packet.sources}
        self.assertIn("SYSTEM_MANIFEST.json", locators, packet.omissions)
        self.assertIn("README_PRODUCTION.md", locators, packet.omissions)
        self.assertIn("qwen2.5:3b-instruct", packet.text)
        self.assertIn("SovereignWorkspace", packet.text)
        self.assertGreater(packet.total_bytes, 0)

    def test_weather_query_still_retrieves_nothing(self) -> None:
        packet = self.builder.build("sess-weather", query="What is the weather in Paris?")
        self.assertEqual(packet.sources, ())
        self.assertEqual(packet.total_bytes, 0)

    def test_praxis_query_still_retrieves_the_constitution(self) -> None:
        packet = self.builder.build("sess-praxis", query="What is the Praxis Answer?")
        locators = {source.locator.replace("\\", "/") for source in packet.sources}
        self.assertIn("constitution/constitution_v1.md", locators, packet.omissions)


if __name__ == "__main__":
    unittest.main()
