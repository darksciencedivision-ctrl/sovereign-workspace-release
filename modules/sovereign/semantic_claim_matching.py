from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

from embedding_client import EmbeddingClient, build_manifest_embedding_client, cosine_similarity
from system_manifest import load_system_manifest, threshold_value


MATCHING_BACKEND = "semantic_claim_matching_v1"
EMBEDDING_VERSION = "cosine-v1"
FeatureFactory = Callable[[str, str], dict[str, float]]
ContradictionDetector = Callable[[str, str], tuple[bool, str]]


def load_semantic_matching_config(root: str | Path | None = None, manifest: dict[str, Any] | None = None) -> dict[str, float]:
    cfg = manifest or load_system_manifest(root)
    return {
        "threshold_agree": threshold_value("CLAIM_AGREE_COSINE", cfg),
        "threshold_variance_low": threshold_value("CLAIM_VARIANCE_COSINE", cfg),
        "threshold_answer": threshold_value("CHALLENGE_ANSWER_COSINE", cfg),
    }


def load_claim_similarity_config(root: str | Path | None = None, manifest: dict[str, Any] | None = None) -> dict[str, float]:
    config = load_semantic_matching_config(root=root, manifest=manifest)
    return {
        "threshold_agree": config["threshold_agree"],
        "threshold_variance_low": config["threshold_variance_low"],
    }


def compute_semantic_similarity(
    left: str,
    right: str,
    embedding_client: EmbeddingClient | Any | None = None,
    manifest: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    client = embedding_client or build_manifest_embedding_client(str(root) if root is not None else None, manifest)
    left_embedding = client.embed(left)
    right_embedding = client.embed(right)
    if not getattr(left_embedding, "ok", False):
        return {
            "cosine": None,
            "embedding_error": getattr(left_embedding, "error_code", "EMBED_LEFT_FAILED"),
            "embedding_error_message": getattr(left_embedding, "error_message", "embedding failed for left input"),
            "embedding_model": getattr(left_embedding, "model", ""),
        }
    if not getattr(right_embedding, "ok", False):
        return {
            "cosine": None,
            "embedding_error": getattr(right_embedding, "error_code", "EMBED_RIGHT_FAILED"),
            "embedding_error_message": getattr(right_embedding, "error_message", "embedding failed for right input"),
            "embedding_model": getattr(right_embedding, "model", ""),
        }
    cosine = cosine_similarity(getattr(left_embedding, "vector", None), getattr(right_embedding, "vector", None))
    if cosine is None:
        return {
            "cosine": None,
            "embedding_error": "DIMENSION_MISMATCH",
            "embedding_error_message": "Embedding vectors are incompatible for cosine similarity.",
            "embedding_model": str(getattr(left_embedding, "model", "")) or str(getattr(right_embedding, "model", "")),
        }
    return {
        "cosine": round(cosine, 6),
        "embedding_error": "",
        "embedding_error_message": "",
        "embedding_model": str(getattr(left_embedding, "model", "")) or str(getattr(right_embedding, "model", "")),
    }


def compute_claim_cosine(
    left: str,
    right: str,
    embedding_client: EmbeddingClient | Any | None = None,
    manifest: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    return compute_semantic_similarity(left, right, embedding_client=embedding_client, manifest=manifest, root=root)


def classify_claim_similarity(
    left: str,
    right: str,
    *,
    embedding_client: EmbeddingClient | Any | None = None,
    manifest: dict[str, Any] | None = None,
    root: str | Path | None = None,
    lexical_feature_factory: FeatureFactory,
    contradiction_detector: ContradictionDetector,
    normalizer: Callable[[str], str],
) -> tuple[str, dict[str, Any]]:
    config = load_semantic_matching_config(root=root, manifest=manifest)
    contradicted, contradiction_reason = contradiction_detector(left, right)
    cosine_details = compute_semantic_similarity(left, right, embedding_client=embedding_client, manifest=manifest, root=root)
    cosine = cosine_details.get("cosine")
    lexical_features = lexical_feature_factory(left, right)
    sequence = SequenceMatcher(None, normalizer(left), normalizer(right)).ratio()

    if contradicted:
        classification = "CONTRADICTION"
        compatibility_label = "CONTRADICTION"
    elif cosine is None:
        classification = "DISAGREED_UNRESOLVED"
        compatibility_label = "DISAGREED_UNRESOLVED"
    elif cosine >= config["threshold_agree"]:
        classification = "AGREED"
        compatibility_label = "AGREED"
    elif cosine >= config["threshold_variance_low"]:
        classification = "SEMANTIC_VARIANCE"
        compatibility_label = "DISAGREED_UNRESOLVED"
    else:
        classification = "UNRELATED_OR_DISTANT"
        compatibility_label = "DISAGREED_UNRESOLVED"

    features = dict(lexical_features)
    features.update(
        {
            "sequence": round(sequence, 4),
            "cosine": cosine,
            "classification": classification,
            "compatibility_label": compatibility_label,
            "contradiction_reason": contradiction_reason,
            "embedding_error": cosine_details.get("embedding_error", ""),
            "embedding_error_message": cosine_details.get("embedding_error_message", ""),
            "embedding_model": cosine_details.get("embedding_model", ""),
            "threshold_agree": round(config["threshold_agree"], 4),
            "threshold_variance_low": round(config["threshold_variance_low"], 4),
            "matching_backend": MATCHING_BACKEND,
            "embedding_version": EMBEDDING_VERSION,
        }
    )
    return classification, features
