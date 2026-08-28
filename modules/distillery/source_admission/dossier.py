from __future__ import annotations

"""D-9 primary-source research dossiers.

A dossier records researched FACTS about one source candidate and may carry a
SYSTEM_RECOMMENDATION. It can never authorize admission: authorization lives
only in source_admission.d9.apply_operator_decision with a signed human
operator decision.
"""

from dataclasses import dataclass, field
from typing import Literal

from distillery.common import ContractError, sha256_value, utc_now

RECOMMENDATIONS = (
    "RECOMMEND_ELIGIBLE",
    "RECOMMEND_INTERNAL_ONLY",
    "RECOMMEND_REJECTED",
    "INSUFFICIENT_EVIDENCE",
)
MAPPING_CONFIDENCES = ("HIGH", "MEDIUM", "LOW")


@dataclass(frozen=True)
class DossierRecord:
    provider: str
    teacher_or_model_id: str
    revision: str
    local_digest_sha256: str
    probable_upstream: str
    official_license: str
    provider_terms_ref: str
    output_use_language: str
    restrictions: str
    verified_upstream_repo: str | None = None
    verified_upstream_revision: str | None = None
    unresolved_ambiguities: tuple[str, ...] = ()
    artifact_mapping_confidence: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    recommendation: str = "INSUFFICIENT_EVIDENCE"
    evidence_timestamps: tuple[str, ...] = ()
    dossier_notes: str = ""

    def __post_init__(self) -> None:
        required = (
            self.provider,
            self.teacher_or_model_id,
            self.revision,
            self.local_digest_sha256,
            self.probable_upstream,
            self.official_license,
            self.provider_terms_ref,
            self.output_use_language,
            self.restrictions,
        )
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise ContractError("dossier requires complete identity, digest, license, and terms fields")
        if self.recommendation not in RECOMMENDATIONS:
            raise ContractError(f"invalid dossier recommendation: {self.recommendation}")
        if self.artifact_mapping_confidence not in MAPPING_CONFIDENCES:
            raise ContractError(f"invalid artifact mapping confidence: {self.artifact_mapping_confidence}")

    @property
    def lineage_id(self) -> str:
        return f"{self.provider}:{self.teacher_or_model_id}:{self.revision}"

    def to_dict(self) -> dict:
        body = {
            "kind": "D9_RESEARCH_DOSSIER",
            "lineage_id": self.lineage_id,
            "provider": self.provider,
            "teacher_or_model_id": self.teacher_or_model_id,
            "revision": self.revision,
            "local_digest_sha256": self.local_digest_sha256,
            "probable_upstream": self.probable_upstream,
            "verified_upstream_repo": self.verified_upstream_repo,
            "verified_upstream_revision": self.verified_upstream_revision,
            "official_license": self.official_license,
            "provider_terms_ref": self.provider_terms_ref,
            "output_use_language": self.output_use_language,
            "restrictions": self.restrictions,
            "unresolved_ambiguities": list(self.unresolved_ambiguities),
            "artifact_mapping_confidence": self.artifact_mapping_confidence,
            "recommendation": self.recommendation,
            "authorizes_admission": False,
            "evidence_class": "REFERENCE_RESEARCH",
            "evidence_timestamps": list(self.evidence_timestamps),
            "notes": self.dossier_notes,
            "generated_at": utc_now(),
        }
        return {**body, "dossier_hash": sha256_value(body)}


def build_dossiers(candidates: list[dict], research: dict[str, dict]) -> list[DossierRecord]:
    """Build dossiers from registry candidates plus researched overlays.

    research maps teacher_or_model_id -> overlay fields (verified_upstream_repo,
    official_license, output_use_language, ...). Candidates without an overlay
    become INSUFFICIENT_EVIDENCE dossiers rather than guesses.
    """
    dossiers: list[DossierRecord] = []
    for candidate in candidates:
        teacher = candidate["teacher_or_model_id"]
        digest = candidate.get("model_blob_sha256") or "UNKNOWN"
        overlay = research.get(teacher)
        if overlay is None:
            dossiers.append(
                DossierRecord(
                    provider=candidate["provider"],
                    teacher_or_model_id=teacher,
                    revision=candidate["revision"],
                    local_digest_sha256=digest,
                    probable_upstream=candidate.get("artifact_source", "UNRESOLVED"),
                    verified_upstream_repo=None,
                    verified_upstream_revision=None,
                    official_license=candidate.get("model_license", "UNKNOWN"),
                    provider_terms_ref="NOT_ESTABLISHED",
                    output_use_language="NOT_ESTABLISHED_BY_MODEL_WEIGHT_LICENSE",
                    restrictions="UNKNOWN",
                    unresolved_ambiguities=("no verified upstream overlay researched",),
                    artifact_mapping_confidence="LOW",
                    recommendation="INSUFFICIENT_EVIDENCE",
                )
            )
            continue
        dossiers.append(
            DossierRecord(
                provider=candidate["provider"],
                teacher_or_model_id=teacher,
                revision=candidate["revision"],
                local_digest_sha256=digest,
                probable_upstream=overlay.get("probable_upstream", candidate.get("artifact_source", "UNRESOLVED")),
                verified_upstream_repo=overlay["verified_upstream_repo"],
                verified_upstream_revision=overlay.get("verified_upstream_revision"),
                official_license=overlay["official_license"],
                provider_terms_ref=overlay["provider_terms_ref"],
                output_use_language=overlay["output_use_language"],
                restrictions=overlay.get("restrictions", "NONE_LOCATED_IN_RESEARCHED_PRIMARY_SOURCES"),
                unresolved_ambiguities=tuple(overlay.get("unresolved_ambiguities", ())),
                artifact_mapping_confidence=overlay.get("artifact_mapping_confidence", "MEDIUM"),
                recommendation=overlay["recommendation"],
                evidence_timestamps=tuple(overlay.get("evidence_timestamps", (utc_now(),))),
                dossier_notes=overlay.get("notes", ""),
            )
        )
    bound: list[DossierRecord] = []
    for dossier in dossiers:
        if dossier.local_digest_sha256 in {"", "UNKNOWN"}:
            if not any("no exact local artifact digest" in note for note in dossier.unresolved_ambiguities):
                dossier = DossierRecord(
                    provider=dossier.provider,
                    teacher_or_model_id=dossier.teacher_or_model_id,
                    revision=dossier.revision,
                    local_digest_sha256=dossier.local_digest_sha256,
                    probable_upstream=dossier.probable_upstream,
                    official_license=dossier.official_license,
                    provider_terms_ref=dossier.provider_terms_ref,
                    output_use_language=dossier.output_use_language,
                    restrictions=dossier.restrictions,
                    verified_upstream_repo=dossier.verified_upstream_repo,
                    verified_upstream_revision=dossier.verified_upstream_revision,
                    unresolved_ambiguities=dossier.unresolved_ambiguities
                    + ("no exact local artifact digest: research cannot be bound to this artifact",),
                    artifact_mapping_confidence="LOW",
                    recommendation="INSUFFICIENT_EVIDENCE",
                    evidence_timestamps=dossier.evidence_timestamps,
                    dossier_notes=dossier.dossier_notes,
                )
        bound.append(dossier)
    return bound


__all__ = ["DossierRecord", "build_dossiers", "RECOMMENDATIONS", "MAPPING_CONFIDENCES"]
