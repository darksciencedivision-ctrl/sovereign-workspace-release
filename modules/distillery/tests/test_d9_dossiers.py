from __future__ import annotations

import json
import unittest
from pathlib import Path

from distillery.common import ContractError, sha256_value
from source_admission.d9 import apply_operator_decision
from source_admission.dossier import DossierRecord, build_dossiers
from source_admission import AdmissionClass, AdmissionRegistry, SourceKey

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "registry" / "source_admission_candidates.json"


def overlay_for(teacher: str) -> dict | None:
    overlays = {
        "qwen2.5:14b-instruct": {
            "probable_upstream": "Qwen/Qwen2.5-14B-Instruct",
            "verified_upstream_repo": "Qwen/Qwen2.5-14B-Instruct",
            "official_license": "Apache-2.0 (verified on official model card)",
            "provider_terms_ref": "https://huggingface.co/Qwen/Qwen2.5-14B-Instruct",
            "output_use_language": "No output-training-use restriction located in official card or LICENSE; model-weight license does not by itself establish output-training authority",
            "recommendation": "RECOMMEND_ELIGIBLE",
            "artifact_mapping_confidence": "HIGH",
            "unresolved_ambiguities": ["provider-side terms exhaustiveness not established"],
        },
        "gemma4:26b": {
            "probable_upstream": "google/gemma-4-26B-A4B-it",
            "verified_upstream_repo": "google/gemma-4-26B-A4B-it",
            "official_license": "Apache-2.0 with supplemental Gemma 4 license document and Prohibited Use policy (ai.google.dev/gemma/docs/gemma_4_license)",
            "provider_terms_ref": "https://ai.google.dev/gemma/docs/gemma_4_license",
            "output_use_language": "Prohibited-use policy exists for model use; no explicit prohibition on training on outputs located in researched pages; determination reserved to operator review",
            "recommendation": "RECOMMEND_ELIGIBLE",
            "artifact_mapping_confidence": "HIGH",
            "unresolved_ambiguities": ["Gemma prohibited-use policy full-text operator review pending", "Ollama quantization producer chain not byte-verified against upstream revision"],
        },
    }
    return overlays.get(teacher)


class DossierTests(unittest.TestCase):
    def setUp(self) -> None:
        registry_doc = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        self.candidates = registry_doc["candidates"]

    def test_researched_candidates_get_verified_dossiers(self) -> None:
        research = {c["teacher_or_model_id"]: overlay for c in self.candidates if (overlay := overlay_for(c["teacher_or_model_id"]))}
        dossiers = build_dossiers(self.candidates, research)
        self.assertEqual(len(dossiers), len(self.candidates))
        by_teacher = {d.teacher_or_model_id: d for d in dossiers}
        qwen = by_teacher["qwen2.5:14b-instruct"]
        self.assertEqual(qwen.recommendation, "RECOMMEND_ELIGIBLE")
        self.assertEqual(qwen.artifact_mapping_confidence, "HIGH")
        self.assertEqual(qwen.verified_upstream_repo, "Qwen/Qwen2.5-14B-Instruct")
        gemma = by_teacher["gemma4:26b"]
        self.assertIn("Prohibited", gemma.official_license)
        frontier = by_teacher["UNKNOWN"]
        self.assertEqual(frontier.recommendation, "INSUFFICIENT_EVIDENCE")

    def test_every_dossier_serializes_without_authorization(self) -> None:
        research = {c["teacher_or_model_id"]: overlay for c in self.candidates if (overlay := overlay_for(c["teacher_or_model_id"]))}
        for dossier in build_dossiers(self.candidates, research):
            payload = dossier.to_dict()
            self.assertFalse(payload["authorizes_admission"])
            recomputed = sha256_value({k: v for k, v in payload.items() if k != "dossier_hash"})
            self.assertEqual(payload["dossier_hash"], recomputed)

    def test_unbound_artifact_becomes_insufficient_evidence_never_a_guess(self) -> None:
        unknown_artifact = [{"provider": "p", "teacher_or_model_id": "m", "revision": "r", "model_blob_sha256": "UNKNOWN"}]
        dossiers = build_dossiers(unknown_artifact, {})
        self.assertEqual(len(dossiers), 1)
        self.assertEqual(dossiers[0].recommendation, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(dossiers[0].artifact_mapping_confidence, "LOW")
        self.assertTrue(any("no exact local artifact digest" in note for note in dossiers[0].unresolved_ambiguities))

    def test_invalid_recommendation_and_confidence_fail(self) -> None:
        with self.assertRaises(ContractError):
            DossierRecord(
                provider="p", teacher_or_model_id="m", revision="r", local_digest_sha256="d" * 64,
                probable_upstream="u", official_license="l", provider_terms_ref="t",
                output_use_language="o", restrictions="s", recommendation="MAKE_ME_ELIGIBLE",
            )
        with self.assertRaises(ContractError):
            DossierRecord(
                provider="p", teacher_or_model_id="m", revision="r", local_digest_sha256="d" * 64,
                probable_upstream="u", official_license="l", provider_terms_ref="t",
                output_use_language="o", restrictions="s", artifact_mapping_confidence="CERTAIN",
            )

    def test_dossier_recommendation_cannot_transition_registry_state(self) -> None:
        registry = AdmissionRegistry()
        key = SourceKey("provider.example", "teacher-a", "rev-1")
        dossier = DossierRecord(
            provider=key.provider, teacher_or_model_id=key.teacher_or_model_id, revision=key.revision,
            local_digest_sha256="d" * 64, probable_upstream="u",
            verified_upstream_repo="u/ok", official_license="Apache-2.0", provider_terms_ref="t",
            output_use_language="o", restrictions="none", recommendation="RECOMMEND_ELIGIBLE",
        )
        with self.assertRaises(ContractError):
            apply_operator_decision(
                registry, key, research_finding=dossier,
                operator_decision={
                    "decision": "ELIGIBLE",
                    "decision_authority": "Samuel Lawson",
                    "decision_authority_signed": True,
                    "evidence_ref": "e",
                },
            )
        self.assertIs(registry.current(key), AdmissionClass.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
