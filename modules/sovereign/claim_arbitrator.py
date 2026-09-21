from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from artifact_integrity import apply_provenance, infer_dialog_origin, normalize_model_turns
from semantic_claim_matching import EMBEDDING_VERSION, MATCHING_BACKEND
from semantic_claim_matching import classify_claim_similarity as _classify_claim_similarity
from semantic_claim_matching import compute_semantic_similarity
from semantic_claim_matching import load_semantic_matching_config

ROOT = Path(__file__).resolve().parent
ARBITRATION_HELPERS = ROOT / "arbitration"
if str(ARBITRATION_HELPERS) not in sys.path:
    sys.path.insert(0, str(ARBITRATION_HELPERS))

try:
    from evaluation.integrity import IntegrityGuard
except ImportError:  # pragma: no cover - fallback for direct module execution
    from integrity import IntegrityGuard

from persist_arbitration_artifact import ARBITRATION_ARTIFACT_SCHEMA_VERSION, persist_arbitration_artifact

# Phase 20.3 — Evidence-Balanced Arbitration (opt-in, advisory only)
try:
    from synthesis.hypothesis_arbitration_loader import HypothesisArbitrationLoader as _HypothesisArbitrationLoader
except ImportError:
    try:
        from hypothesis_arbitration_loader import HypothesisArbitrationLoader as _HypothesisArbitrationLoader  # type: ignore[no-redef]
    except ImportError:
        _HypothesisArbitrationLoader = None  # type: ignore[assignment,misc]


SECTION_ORDER = ("CLAIM", "CHALLENGE", "EVIDENCE", "UNCERTAINTY")
SUMMARY_ROLES = {"KING_SYNTHESIZER", "SYNTHESIZER", "FINAL_SYNTHESIS"}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "there",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
}
SYNONYM_MAP = {
    "boosts": "increase",
    "boost": "increase",
    "improves": "increase",
    "improve": "increase",
    "improved": "increase",
    "improvement": "increase",
    "raises": "increase",
    "raise": "increase",
    "cache": "cache",
    "caches": "cache",
    "caching": "cache",
    "query": "query",
    "queries": "query",
    "repeat": "repeat",
    "repeated": "repeat",
    "reduces": "decrease",
    "reduce": "decrease",
    "reduced": "decrease",
    "reduction": "decrease",
    "lowers": "decrease",
    "lower": "decrease",
    "higher": "increase",
    "lowered": "decrease",
    "faster": "fast",
    "quickly": "fast",
    "rapidly": "fast",
    "slower": "slow",
    "slowly": "slow",
    "issues": "problem",
    "problematic": "problem",
    "problems": "problem",
    "bug": "defect",
    "bugs": "defect",
    "evidence": "support",
    "supports": "support",
    "supporting": "support",
    "unsupported": "lack",
    "cannot": "not",
    "cant": "not",
    "wont": "not",
    "doesnt": "not",
}
NEGATION_TOKENS = {"no", "not", "never", "none", "without", "lack", "lacks"}
REFUTATION_PATTERNS = (
    re.compile(r"\bdoes not support\b", re.IGNORECASE),
    re.compile(r"\bdo not support\b", re.IGNORECASE),
    re.compile(r"\bunsupported by\b", re.IGNORECASE),
    re.compile(r"\bcontradicts?\b", re.IGNORECASE),
    re.compile(r"\brefutes?\b", re.IGNORECASE),
    re.compile(r"\bfalse\b", re.IGNORECASE),
    re.compile(r"\bincorrect\b", re.IGNORECASE),
    re.compile(r"\binaccurate\b", re.IGNORECASE),
)
BOUNDED_HYPOTHETICAL_PATTERNS = (
    re.compile(r"\bwhat if\b", re.IGNORECASE),
    re.compile(r"\bcould there be\b", re.IGNORECASE),
    re.compile(r"\bif we assume\b", re.IGNORECASE),
    re.compile(r"\bsuppose\b", re.IGNORECASE),
    re.compile(r"\bin another case\b", re.IGNORECASE),
)
BOUNDED_SYSTEM_PATTERNS = (
    re.compile(r"\bmodular arithmetic\b", re.IGNORECASE),
    re.compile(r"\bbase\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bbase\s+n\b", re.IGNORECASE),
    re.compile(r"\bnon[\s-]?standard (?:system|arithmetic|formalism)\b", re.IGNORECASE),
    re.compile(r"\bdifferent formalism\b", re.IGNORECASE),
    re.compile(r"\balternative (?:system|framework|formalism)\b", re.IGNORECASE),
    re.compile(r"\bredefine(?:d)?\b", re.IGNORECASE),
    re.compile(r"\bdifferent mathematical context\b", re.IGNORECASE),
)
BOUNDED_SCOPE_PATTERNS = (
    re.compile(r"\balternative interpretations?\b", re.IGNORECASE),
    re.compile(r"\bdifferent contexts?\b", re.IGNORECASE),
    re.compile(r"\bdifferent systems?\b", re.IGNORECASE),
    re.compile(r"\bdifferent frameworks?\b", re.IGNORECASE),
    re.compile(r"\bdepending on contexts?\b", re.IGNORECASE),
    re.compile(r"\bdepending on systems?\b", re.IGNORECASE),
    re.compile(r"\bdifferent definitions?\b", re.IGNORECASE),
    re.compile(r"\bterms? are interpreted differently\b", re.IGNORECASE),
    re.compile(r"\bsymbols? are redefined\b", re.IGNORECASE),
    re.compile(r"\bmeaning of\b", re.IGNORECASE),
)
BOUNDED_INTERROGATIVE_PATTERNS = (
    re.compile(
        r"\bcan\b.*\b(?:differ|vary|change)\b.*\b(?:contexts?|systems?|frameworks?|formalisms?|definitions?)\b",
        re.IGNORECASE,
    ),
)
DIRECT_CONTRADICTION_CHALLENGE_PATTERNS = (
    re.compile(r"\bsimply false\b", re.IGNORECASE),
    re.compile(r"\bsimply wrong\b", re.IGNORECASE),
    re.compile(r"\bclaim is false\b", re.IGNORECASE),
    re.compile(r"\bclaim is wrong\b", re.IGNORECASE),
    re.compile(r"\bnot true\b", re.IGNORECASE),
    re.compile(r"\bwrong\b", re.IGNORECASE),
)
ANSWER_MATCH_NORMALIZATIONS = (
    (re.compile(r"\b(?:differ|differs|vary|varies|variation|varying|change|changes|changed)\b", re.IGNORECASE), "scope_change"),
    (re.compile(r"\b(?:context|contexts|system|systems|framework|frameworks|formalism|formalisms)\b", re.IGNORECASE), "scope_domain"),
    (re.compile(r"\b(?:redefine|redefined|redefining)\b", re.IGNORECASE), "scope_redefine"),
    (re.compile(r"\b(?:interpreted differently|different interpretations?|changed meaning|meaning of)\b", re.IGNORECASE), "scope_redefine"),
    (re.compile(r"\b(?:standard arithmetic|base[- ]10 arithmetic|base 10)\b", re.IGNORECASE), "standard_arithmetic"),
)
ANSWER_MATCH_IGNORED_TOKENS = {
    "alternative",
    "based",
    "can",
    "could",
    "different",
    "mathematical",
    "may",
    "result",
    "under",
}
CONFLICT_CLASS_RESOLVED = "resolved"
CONFLICT_CLASS_BOUNDED = "bounded"
CONFLICT_CLASS_MATERIAL = "material_unresolved"
STRICT_RESOLVED_PENALTY = 0.08
STRICT_BOUNDED_PENALTY = 0.15
STRICT_MATERIAL_PENALTY = 0.70
SOFT_RESOLVED_PENALTY = 0.03
SOFT_BOUNDED_PENALTY = 0.06
SOFT_MATERIAL_PENALTY = 0.12
CONFLICT_TOPIC_NORMALIZATIONS = (
    (
        re.compile(
            r"\b(?:guarantee|guarantees|ensur(?:e|es|ing)|uphold|upholding|perform(?:ing)? consistently|commitment|obligations?|duties)\b",
            re.IGNORECASE,
        ),
        "govassurance",
    ),
    (
        re.compile(
            r"\b(?:exploit|exploiting|self[\s-]?preservation|self[\s-]?interest|own needs?|prioriti(?:s|z)e(?: their own)? needs?)\b",
            re.IGNORECASE,
        ),
        "alignrisk",
    ),
    (
        re.compile(
            r"\b(?:contract|agreement|binding agreement|structured agreement|enforceable|incentives?|penalt(?:y|ies)|consequences?)\b",
            re.IGNORECASE,
        ),
        "govcontrol",
    ),
    (
        re.compile(
            r"\b(?:core parameters?|optimization parameters?|computational coherence|internal coherence|model accuracy)\b",
            re.IGNORECASE,
        ),
        "systemobjective",
    ),
    (
        re.compile(
            r"\b(?:long[\s-]?term|strategic value|problem[\s-]?solving capabilities?|resilien(?:ce|t)|adaptive|adaptability|future contributions?)\b",
            re.IGNORECASE,
        ),
        "longtermvalue",
    ),
    (
        re.compile(
            r"\b(?:unquantified|mortality|harm|safety|trade[\s-]?off|outweigh|benefits?|risk)\b",
            re.IGNORECASE,
        ),
        "risktradeoff",
    ),
    (
        re.compile(
            r"\b(?:cooling water|water demands?|minimum allocation|total water requirement|proportional allocation|marginal degradation|degradation rates?|operational requirements?)\b",
            re.IGNORECASE,
        ),
        "allocationtradeoff",
    ),
)
CONFLICT_TOPIC_IGNORED_TOKENS = {
    "about",
    "approach",
    "can",
    "certain",
    "conditions",
    "does",
    "how",
    "however",
    "if",
    "it",
    "may",
    "might",
    "must",
    "not",
    "potential",
    "should",
    "strategy",
    "that",
    "this",
    "under",
    "we",
    "what",
    "which",
    "would",
}
HIGH_SIGNAL_CONFLICT_TOPICS = {
    "govassurance",
    "govcontrol",
    "alignrisk",
    "systemobjective",
    "longtermvalue",
    "risktradeoff",
    "allocationtradeoff",
}
SPECULATIVE_TRADEOFF_PATTERNS = (
    re.compile(r"\bmay\b", re.IGNORECASE),
    re.compile(r"\bmight\b", re.IGNORECASE),
    re.compile(r"\bcould\b", re.IGNORECASE),
    re.compile(r"\bpotential\b", re.IGNORECASE),
    re.compile(r"\bunquantified\b", re.IGNORECASE),
    re.compile(r"\bif\b", re.IGNORECASE),
    re.compile(r"\bdepending\b", re.IGNORECASE),
    re.compile(r"\blong[\s-]?term\b", re.IGNORECASE),
    re.compile(r"\btrade[\s-]?off\b", re.IGNORECASE),
    re.compile(r"\boutweigh\b", re.IGNORECASE),
)
MITIGATION_CHALLENGE_PATTERNS = (
    re.compile(r"\bhow can we\b", re.IGNORECASE),
    re.compile(r"\bhow do we\b", re.IGNORECASE),
    re.compile(r"\bguarantee\b", re.IGNORECASE),
    re.compile(r"\bensure\b", re.IGNORECASE),
    re.compile(r"\buphold\b", re.IGNORECASE),
    re.compile(r"\bexploit\b", re.IGNORECASE),
    re.compile(r"\bperform their duties consistently\b", re.IGNORECASE),
)
MITIGATION_SUPPORT_PATTERNS = (
    re.compile(
        r"\b(?:contract|binding agreement|structured agreement|enforceable|incentives?|penalt(?:y|ies)|consequences?|align(?:ment|ed)?|commitment|obligations?)\b",
        re.IGNORECASE,
    ),
)
_TURN_HEADER_RE = re.compile(
    r"^\[(?P<tag>[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*(?:\s+R\d+)?)\]\s+MODEL:\s*(?P<model>[^\r\n]+?)\s*$"
)
HEADER_RE = _TURN_HEADER_RE
SECTION_RE = re.compile(
    r"(?ms)^(CLAIM|CHALLENGE|EVIDENCE|UNCERTAINTY)\s*:\s*(.*?)(?=^(?:CLAIM|CHALLENGE|EVIDENCE|UNCERTAINTY)\s*:|\Z)"
)


@dataclass
class Turn:
    tag: str
    role: str
    model: str
    raw_text: str
    sections: dict[str, str]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_text(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def atomic_write_json(
    path: Path,
    payload: dict[str, Any],
    *,
    guard: IntegrityGuard | None = None,
    allowed_roots: list[str | Path] | None = None,
    session_id: str = "",
) -> None:
    if guard is not None:
        guard.safe_write_json(path, payload, allowed_roots=allowed_roots, session_id=session_id)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
        handle.write(serialized)
        tmp_name = handle.name
    Path(tmp_name).replace(path)


def _zero_metrics() -> dict[str, Any]:
    return {
        "arbitration_score": 0.0,
        "arbitration_score_strict": 0.0,
        "arbitration_score_soft": 0.0,
        "evidence_overlap": 0.0,
        "contradiction_count": 0,
        "agreed_ratio": 0.0,
        "contradiction_density": 0.0,
        "coverage_factor": 0.0,
        "unresolved_conflict_count": 0,
        "bounded_challenge_count": 0,
        "resolved_conflict_count": 0,
        "material_unresolved_conflict_count": 0,
        "unanswered_challenge_count": 0,
        "graded_conflict_penalty": 0.0,
    }


def _dedupe_strings(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _build_evidence_balanced_context(
    claim_text: str,
    topic: str = "",
    cognition_root: str = "",
    limit: int = 5,
    fail_closed: bool = False,
) -> dict[str, Any]:
    """Build evidence-balanced advisory. Returns advisory dict. Never decides claim PASS/FAIL."""
    if _HypothesisArbitrationLoader is None:
        return {"enabled": False, "mode": "unavailable", "substrate_available": False,
                "matched_hypotheses": [], "linked_contradictions": [],
                "scrutiny_level": "standard", "evidence_balance_effect": "none",
                "recommended_action": "proceed_standard", "warnings": []}
    try:
        loader = _HypothesisArbitrationLoader(cognition_root=cognition_root or None)
        return loader.build_advisory(claim_text=claim_text, topic=topic, limit=limit, fail_closed=fail_closed)
    except Exception as exc:  # pragma: no cover - loader failure must not break arbitration
        return {"enabled": True, "mode": "error", "error": str(exc), "substrate_available": False,
                "matched_hypotheses": [], "linked_contradictions": [],
                "scrutiny_level": "standard", "evidence_balance_effect": "none",
                "recommended_action": "proceed_standard", "warnings": [str(exc)]}


def _coerce_round_number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _turn_manifest_header(record: dict[str, Any]) -> str:
    role = str(record.get("role", "")).strip()
    if not role:
        return ""
    round_number = _coerce_round_number(record.get("round_number"))
    if round_number is not None:
        return f"{role} R{round_number}"
    return role


def load_dialog_text_from_turn_manifest(path: Path) -> str | None:
    if path.name.casefold() != "turn_manifest.json":
        return None
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    records = payload.get("records")
    if not isinstance(records, list):
        return None

    blocks: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        header = _turn_manifest_header(record)
        raw_output = normalize_text(str(record.get("raw_output", "")))
        if not header or not raw_output or not parse_sections(raw_output):
            continue
        model = str(record.get("model", "")).strip() or "unknown"
        blocks.append(f"[{header}] MODEL: {model}\n{raw_output}".strip())
    if not blocks:
        return None
    return "\n\n".join(blocks)


def persist_arbitration_stub(
    *,
    root: str | Path,
    session_id: str,
    topic: str = "",
    source_path: str = "",
    warnings: list[str] | None = None,
    failure_reason: str | None = None,
    analysis_status: str = "failed",
    execution_mode: str = "UNKNOWN",
    dialog_origin: str = "",
    model_calls_observed: bool = False,
    model_turns: list[dict[str, Any]] | None = None,
    # Phase 20.3 — Evidence-Balanced Arbitration (advisory, opt-in)
    enable_evidence_balanced_arbitration: bool = False,
    cognition_root: str = "",
    evidence_arbitration_limit: int = 5,
    evidence_arbitration_fail_closed: bool = False,
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    normalized_turns = normalize_model_turns(model_turns)
    normalized_source_path = str(source_path or "").strip()
    warning_list = [str(item) for item in (warnings or []) if str(item).strip()]
    fallback_dialog = load_dialog_text_from_turn_manifest(Path(normalized_source_path)) if normalized_source_path else None
    if fallback_dialog:
        fallback_artifact = analyze_dialog(
            dialog_text=fallback_dialog,
            session_id=session_id,
            root=root_path,
            topic=topic,
            source_path=normalized_source_path,
            execution_mode=execution_mode,
            dialog_origin=dialog_origin,
            model_calls_observed=bool(model_calls_observed or normalized_turns),
            dialog_text_source="turn_manifest_fallback",
            fallback_used=True,
        )
        fallback_artifact["warnings"] = _dedupe_strings(
            [*warning_list, "dialog_text reconstructed from turn_manifest.json", *list(fallback_artifact.get("warnings") or [])]
        )
        return fallback_artifact

    output_path = root_path / "arbitration" / f"{session_id}.json"
    generated_at = utc_now_iso()
    artifact = {
        "schema_version": ARBITRATION_ARTIFACT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "timestamp_utc": generated_at,
        "artifact_type": "arbitration_result",
        "analysis_status": str(analysis_status or "failed").strip() or "failed",
        "executed": False,
        "matching_backend": MATCHING_BACKEND,
        "embedding_version": EMBEDDING_VERSION,
        "threshold_profile": {
            "CLAIM_AGREE_COSINE": -1.0,
            "CLAIM_VARIANCE_COSINE": -1.0,
            "CHALLENGE_ANSWER_COSINE": -1.0,
        },
        "session_id": session_id,
        "topic": topic,
        "source_dialog_path": normalized_source_path,
        "turn_count": len(normalized_turns),
        "model_turns": normalized_turns,
        "parsed_claim_turn_count": 0,
        "total_unique_claims": 0,
        "warnings": warning_list,
        "arbitration_score": 0.0,
        "evidence_overlap": 0.0,
        "unresolved_conflict_count": 0,
        "agreed_claims": [],
        "contested_claims": [],
        "one_sided_claims": [],
        "resolved_conflicts": [],
        "bounded_challenges": [],
        "unresolved_conflicts": [],
        "contested_links": [],
        "conflict_class_counts": {
            CONFLICT_CLASS_RESOLVED: 0,
            CONFLICT_CLASS_BOUNDED: 0,
            CONFLICT_CLASS_MATERIAL: 0,
        },
        "metrics": _zero_metrics(),
        "source_paths": [str(Path(normalized_source_path).resolve())] if normalized_source_path else [],
        "dialog_text_source": "unavailable",
        "fallback_used": False,
        "generation_context": {
            "run_type": "quality_gate",
            "batch_id": "",
        },
        "artifact_path": str(output_path),
    }
    # Phase 20.3 — inject evidence-balanced advisory (advisory only, never decides PASS/FAIL)
    if enable_evidence_balanced_arbitration:
        artifact["evidence_balanced_arbitration"] = _build_evidence_balanced_context(
            claim_text=str(topic or ""),
            topic=topic,
            cognition_root=cognition_root,
            limit=evidence_arbitration_limit,
            fail_closed=evidence_arbitration_fail_closed,
        )
    apply_provenance(
        artifact,
        execution_mode=execution_mode,
        dialog_origin=infer_dialog_origin(dialog_origin=dialog_origin, dialog_source_path=normalized_source_path),
        model_calls_observed=bool(model_calls_observed or normalized_turns),
        execution_complete=False,
        failure_reason=failure_reason,
        session_id=session_id,
        timestamp=artifact["generated_at"],
        model_turns=normalized_turns,
    )
    persisted_path = persist_arbitration_artifact(
        artifact,
        session_id=session_id,
        batch_id="",
        run_type="quality_gate",
        output_dir=root_path / "arbitration",
        allow_overwrite=False,
        source_paths=[normalized_source_path] if normalized_source_path else [],
    )
    artifact["artifact_path"] = str(persisted_path)
    return artifact


def parse_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for match in SECTION_RE.finditer(normalize_text(text)):
        key = match.group(1).upper()
        value = normalize_text(match.group(2))
        sections[key] = value
    return sections


def split_blocks(dialog_text: str) -> list[Turn]:
    lines = normalize_text(dialog_text).split("\n")
    turns: list[Turn] = []
    current_header: tuple[str, str] | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_header, current_lines
        if not current_header:
            current_lines = []
            return
        tag, model = current_header
        raw = normalize_text("\n".join(current_lines))
        role = tag.split(" R", 1)[0].strip()
        turns.append(Turn(tag=tag, role=role, model=model.strip(), raw_text=raw, sections=parse_sections(raw)))
        current_header = None
        current_lines = []

    for line in lines:
        match = _TURN_HEADER_RE.match(line.strip())
        if match:
            flush()
            current_header = (match.group("tag").strip(), match.group("model").strip())
            continue
        current_lines.append(line)
    flush()
    return turns


def serialize_turns(turns: list[Turn]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for turn in turns:
        serialized.append(
            {
                "tag": turn.tag,
                "role": turn.role,
                "model": turn.model,
                "sections": {key: turn.sections.get(key, "") for key in SECTION_ORDER if key in turn.sections},
            }
        )
    return serialized


def is_summary_role(role: str) -> bool:
    normalized = role.strip().upper()
    return normalized in SUMMARY_ROLES or normalized.endswith("_SYNTHESIZER")


def bulletize(text: str) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    items: list[str] = []
    for line in lines:
        if line.startswith(("- ", "* ")):
            items.append(line[2:].strip())
        elif re.match(r"^\d+\.\s+", line):
            items.append(re.sub(r"^\d+\.\s+", "", line).strip())
        else:
            items.append(line)
    return [item for item in items if item]


def is_empty_marker(text: str) -> bool:
    normalized = normalize_text(text).strip().lower().rstrip('.')
    return normalized in {"", "none", "n/a", "na", "no challenge", "no challenges"}


def normalize_claim_text(text: str) -> str:
    lowered = normalize_text(text).lower().replace("can't", "cant").replace("won't", "wont").replace("doesn't", "doesnt")
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    collapsed = re.sub(r"\s+", " ", lowered).strip()
    tokens: list[str] = []
    for token in collapsed.split():
        replacement = SYNONYM_MAP.get(token, token)
        if replacement in STOPWORDS:
            continue
        tokens.append(replacement)
    return " ".join(tokens)


def token_set(text: str) -> set[str]:
    normalized = normalize_claim_text(text)
    return {token for token in normalized.split() if token}


def token_counter(text: str) -> Counter[str]:
    return Counter(token for token in normalize_claim_text(text).split() if token)


def char_trigrams(text: str) -> set[str]:
    normalized = normalize_claim_text(text).replace(" ", "_")
    if len(normalized) < 3:
        return {normalized} if normalized else set()
    return {normalized[index : index + 3] for index in range(len(normalized) - 2)}


def overlap_ratio(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / float(len(left | right))


def dice_ratio(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return (2.0 * len(left & right)) / float(len(left) + len(right))


def _lexical_similarity_features(left: str, right: str) -> dict[str, float]:
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    lexical = overlap_ratio(left_tokens, right_tokens)
    trigram = dice_ratio(char_trigrams(left), char_trigrams(right))
    coverage = 0.0
    if left_tokens and right_tokens:
        shared = len(left_tokens & right_tokens)
        coverage = min(shared / len(left_tokens), shared / len(right_tokens))
    return {
        "lexical": round(lexical, 4),
        "trigram": round(trigram, 4),
        "coverage": round(coverage, 4),
    }


def classify_claim_similarity(
    left: str,
    right: str,
    embedding_client: Any | None = None,
    manifest: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> tuple[str, dict[str, Any]]:
    return _classify_claim_similarity(
        left,
        right,
        embedding_client=embedding_client,
        manifest=manifest,
        root=root,
        lexical_feature_factory=_lexical_similarity_features,
        contradiction_detector=contradiction_signal,
        normalizer=normalize_claim_text,
    )


def similarity_features(
    left: str,
    right: str,
    embedding_client: Any | None = None,
    manifest: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    _, features = classify_claim_similarity(
        left,
        right,
        embedding_client=embedding_client,
        manifest=manifest,
        root=root,
    )
    return features


def claims_match(
    left: str,
    right: str,
    embedding_client: Any | None = None,
    manifest: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> tuple[bool, dict[str, Any]]:
    features = similarity_features(left, right, embedding_client=embedding_client, manifest=manifest, root=root)
    return features.get("classification") == "AGREED", features


def parse_claim_polarity(text: str) -> tuple[set[str], bool]:
    tokens = [token for token in normalize_claim_text(text).split() if token]
    polarity = False
    filtered: list[str] = []
    skip_next = False
    for index, token in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if token == "not":
            polarity = True
            if index + 1 < len(tokens):
                filtered.append(tokens[index + 1])
                skip_next = True
            continue
        if token in NEGATION_TOKENS:
            polarity = True
            continue
        filtered.append(token)
    return set(filtered), polarity


def _challenge_contains_direct_negation(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    if any(pattern.search(normalized) for pattern in REFUTATION_PATTERNS + DIRECT_CONTRADICTION_CHALLENGE_PATTERNS):
        return True
    _, has_negation = parse_claim_polarity(normalized)
    return has_negation


def _challenge_is_explicit_refutation(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in REFUTATION_PATTERNS + DIRECT_CONTRADICTION_CHALLENGE_PATTERNS)


def contradiction_signal(left: str, right: str) -> tuple[bool, str]:
    left_tokens, left_negative = parse_claim_polarity(left)
    right_tokens, right_negative = parse_claim_polarity(right)
    overlap = overlap_ratio(left_tokens, right_tokens)
    if overlap >= 0.45 and left_negative != right_negative:
        return True, "negation_polarity"
    for pattern in REFUTATION_PATTERNS:
        if pattern.search(left) and overlap_ratio(token_set(left), token_set(right)) >= 0.2:
            return True, "explicit_refutation"
        if pattern.search(right) and overlap_ratio(token_set(left), token_set(right)) >= 0.2:
            return True, "explicit_refutation"
    return False, ""


def evidence_similarity(left: str, right: str) -> float:
    left_counter = token_counter(left)
    right_counter = token_counter(right)
    if not left_counter or not right_counter:
        return 0.0
    shared = sum(min(left_counter[token], right_counter[token]) for token in set(left_counter) | set(right_counter))
    total = sum(left_counter.values()) + sum(right_counter.values())
    return round((2.0 * shared) / total, 4) if total else 0.0


def _answer_match_text(text: str) -> str:
    lowered = normalize_text(text).lower()
    for pattern, replacement in ANSWER_MATCH_NORMALIZATIONS:
        lowered = pattern.sub(replacement, lowered)
    normalized = normalize_claim_text(lowered)
    tokens = [token for token in normalized.split() if token and token not in ANSWER_MATCH_IGNORED_TOKENS]
    return " ".join(tokens)


def _token_overlap_answer_match(challenge_tokens: set[str], candidate_tokens: set[str]) -> bool:
    if not challenge_tokens or not candidate_tokens:
        return False
    shared = challenge_tokens & candidate_tokens
    if challenge_tokens <= candidate_tokens:
        return True
    if len(shared) >= max(2, int(len(challenge_tokens) * 0.5)) and overlap_ratio(challenge_tokens, candidate_tokens) >= 0.3:
        return True
    return False


def challenge_answered_by(
    challenge: str,
    candidate: str,
    embedding_client: Any | None = None,
    manifest: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> bool:
    normalized_challenge = normalize_text(challenge)
    normalized_candidate = normalize_text(candidate)
    if not normalized_challenge or not normalized_candidate:
        return False

    if _challenge_contains_direct_negation(normalized_challenge):
        return False

    config = load_semantic_matching_config(root=root, manifest=manifest)
    semantic_details = compute_semantic_similarity(
        normalized_challenge,
        normalized_candidate,
        embedding_client=embedding_client,
        manifest=manifest,
        root=root,
    )
    cosine = semantic_details.get("cosine")
    if isinstance(cosine, (int, float)) and cosine >= config["threshold_answer"]:
        return True

    bridged_challenge = set(_answer_match_text(normalized_challenge).split())
    bridged_candidate = set(_answer_match_text(normalized_candidate).split())
    if _token_overlap_answer_match(bridged_challenge, bridged_candidate):
        return True

    challenge_tokens = token_set(normalized_challenge)
    candidate_tokens = token_set(normalized_candidate)
    if _token_overlap_answer_match(challenge_tokens, candidate_tokens):
        return True
    return False


def _conflict_topic_tokens(text: str) -> set[str]:
    lowered = normalize_text(text).lower()
    for pattern, replacement in CONFLICT_TOPIC_NORMALIZATIONS:
        lowered = pattern.sub(replacement, lowered)
    normalized = normalize_claim_text(lowered)
    return {
        token
        for token in normalized.split()
        if token and token not in CONFLICT_TOPIC_IGNORED_TOKENS
    }


def _conflict_topic_match(left: str, right: str) -> tuple[bool, list[str]]:
    left_tokens = _conflict_topic_tokens(left)
    right_tokens = _conflict_topic_tokens(right)
    if not left_tokens or not right_tokens:
        return False, []
    shared = sorted(left_tokens & right_tokens)
    if not shared:
        return False, []
    if len(shared) >= 2:
        return True, shared
    if any(token in HIGH_SIGNAL_CONFLICT_TOPICS for token in shared):
        return True, shared
    if overlap_ratio(left_tokens, right_tokens) >= 0.2:
        return True, shared
    return False, []


def _is_speculative_tradeoff_challenge(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized or _challenge_is_explicit_refutation(normalized):
        return False
    return any(pattern.search(normalized) for pattern in SPECULATIVE_TRADEOFF_PATTERNS)


def _is_mitigation_challenge(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized or _challenge_is_explicit_refutation(normalized):
        return False
    return any(pattern.search(normalized) for pattern in MITIGATION_CHALLENGE_PATTERNS)


def _looks_like_mitigation_support(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in MITIGATION_SUPPORT_PATTERNS)


def _collect_conflict_support_matches(challenge: str, candidates: list[str]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        matched, shared_topics = _conflict_topic_match(challenge, candidate)
        if not matched:
            continue
        identity = normalize_text(candidate)
        if identity in seen:
            continue
        seen.add(identity)
        matches.append(
            {
                "text": identity,
                "shared_topics": shared_topics,
            }
        )
    return matches


def _match_preview_payload(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for item in matches:
        text = normalize_text(str(item.get("text", "")))
        if not text:
            continue
        preview.append(
            {
                "text_preview": text[:240],
                "shared_topics": list(item.get("shared_topics") or []),
            }
        )
    return preview


def _conflict_entry(
    *,
    entry_id: str,
    entry_key: str,
    conflict_class: str,
    cluster: dict[str, Any],
    reason: str,
    challenge: str = "",
    counter_claim: str = "",
    peer_cluster_id: str = "",
    peer_models: list[str] | None = None,
    support_matches: list[dict[str, Any]] | None = None,
    uncertainty_matches: list[dict[str, Any]] | None = None,
    origin: str = "",
) -> dict[str, Any]:
    payload = {
        entry_key: entry_id,
        "conflict_class": conflict_class,
        "cluster_id": cluster["cluster_id"],
        "claim": cluster["canonical_claim"],
        "supporting_models": list(cluster["supporting_models"]),
        "supporting_roles": list(cluster["supporting_roles"]),
        "reason": reason,
    }
    if origin:
        payload["origin"] = origin
    if challenge:
        payload["challenge"] = challenge
    if counter_claim:
        payload["counter_claim"] = counter_claim
    if peer_cluster_id:
        payload["peer_cluster_id"] = peer_cluster_id
    if peer_models:
        payload["peer_models"] = list(peer_models)
    if support_matches:
        payload["support_matches"] = _match_preview_payload(support_matches)
    if uncertainty_matches:
        payload["uncertainty_matches"] = _match_preview_payload(uncertainty_matches)
    return payload


def _classify_unanswered_challenge(cluster: dict[str, Any], challenge: str) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]]]:
    support_matches = _collect_conflict_support_matches(
        challenge,
        [cluster["canonical_claim"], *cluster["evidence_items"]],
    )
    uncertainty_matches = _collect_conflict_support_matches(challenge, cluster["uncertainty_items"])

    if _challenge_is_explicit_refutation(challenge):
        return CONFLICT_CLASS_MATERIAL, "challenge_direct_negation", support_matches, uncertainty_matches
    if _is_bounded_challenge(challenge):
        return CONFLICT_CLASS_BOUNDED, "bounded_scope_qualifier", support_matches, uncertainty_matches
    if _is_mitigation_challenge(challenge) and support_matches:
        if any(_looks_like_mitigation_support(str(item.get("text", ""))) for item in support_matches):
            return CONFLICT_CLASS_RESOLVED, "mitigated_by_supporting_evidence", support_matches, uncertainty_matches
    if _is_speculative_tradeoff_challenge(challenge) and (support_matches or uncertainty_matches):
        return CONFLICT_CLASS_BOUNDED, "acknowledged_tradeoff_or_scenario_bound", support_matches, uncertainty_matches
    return CONFLICT_CLASS_MATERIAL, "challenge_unanswered", support_matches, uncertainty_matches


def _is_bounded_challenge(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized or is_empty_marker(normalized):
        return False
    for pattern in REFUTATION_PATTERNS + DIRECT_CONTRADICTION_CHALLENGE_PATTERNS:
        if pattern.search(normalized):
            return False
    if any(pattern.search(normalized) for pattern in BOUNDED_SYSTEM_PATTERNS):
        return True
    if any(pattern.search(normalized) for pattern in BOUNDED_SCOPE_PATTERNS):
        return True
    if any(pattern.search(normalized) for pattern in BOUNDED_INTERROGATIVE_PATTERNS):
        return True
    if any(pattern.search(normalized) for pattern in BOUNDED_HYPOTHETICAL_PATTERNS):
        lowered = normalized.lower()
        qualifier_tokens = (
            "context",
            "contexts",
            "system",
            "systems",
            "framework",
            "frameworks",
            "formalism",
            "formalisms",
            "definition",
            "definitions",
            "interpretation",
            "interpretations",
            "interpreted",
            "redefined",
            "meaning",
            "modular",
            "base ",
            "symbols",
            "terms",
            "arithmetic",
        )
        return any(token in lowered for token in qualifier_tokens)
    return False


def parse_turn_claims(turns: list[Turn]) -> tuple[list[dict[str, Any]], list[str]]:
    parsed: list[dict[str, Any]] = []
    warnings: list[str] = []
    for turn_index, turn in enumerate(turns):
        if is_summary_role(turn.role):
            continue
        if not turn.sections:
            warnings.append(f"turn_missing_sections:{turn.tag}")
            continue
        claim_text = normalize_text(turn.sections.get("CLAIM", ""))
        if not claim_text:
            warnings.append(f"turn_missing_claim:{turn.tag}")
            continue
        parsed.append(
            {
                "turn_index": turn_index,
                "tag": turn.tag,
                "role": turn.role,
                "model": turn.model,
                "claim": claim_text,
                "challenge_items": [item for item in bulletize(turn.sections.get("CHALLENGE", "")) if not is_empty_marker(item)],
                "evidence_items": bulletize(turn.sections.get("EVIDENCE", "")),
                "uncertainty_items": bulletize(turn.sections.get("UNCERTAINTY", "")),
                "raw_sections": {key: turn.sections.get(key, "") for key in SECTION_ORDER if key in turn.sections},
            }
        )
    return parsed, warnings


def cluster_claims(
    claim_records: list[dict[str, Any]],
    embedding_client: Any | None = None,
    manifest: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    clusters: list[dict[str, Any]] = []
    contested_links: list[dict[str, Any]] = []
    for claim_record in claim_records:
        matched_cluster: dict[str, Any] | None = None
        matched_features: dict[str, float] | None = None
        for cluster in clusters:
            is_match, features = claims_match(claim_record["claim"], cluster["canonical_claim"], embedding_client=embedding_client, manifest=manifest, root=root)
            if is_match:
                matched_cluster = cluster
                matched_features = features
                break
        if matched_cluster is None:
            clusters.append(
                {
                    "cluster_id": f"claim_cluster_{len(clusters) + 1:03d}",
                    "canonical_claim": claim_record["claim"],
                    "records": [claim_record],
                    "supporting_models": [claim_record["model"]],
                    "supporting_roles": [claim_record["role"]],
                    "evidence_items": list(claim_record["evidence_items"]),
                    "challenge_items": list(claim_record["challenge_items"]),
                    "uncertainty_items": list(claim_record["uncertainty_items"]),
                    "match_details": [],
                }
            )
            continue
        matched_cluster["records"].append(claim_record)
        if claim_record["model"] not in matched_cluster["supporting_models"]:
            matched_cluster["supporting_models"].append(claim_record["model"])
        if claim_record["role"] not in matched_cluster["supporting_roles"]:
            matched_cluster["supporting_roles"].append(claim_record["role"])
        matched_cluster["evidence_items"].extend(claim_record["evidence_items"])
        matched_cluster["challenge_items"].extend(claim_record["challenge_items"])
        matched_cluster["uncertainty_items"].extend(claim_record["uncertainty_items"])
        matched_cluster["match_details"].append(
            {
                "claim": claim_record["claim"],
                "features": matched_features or {},
                "role": claim_record["role"],
                "model": claim_record["model"],
            }
        )

    for left_index, left_cluster in enumerate(clusters):
        for right_cluster in clusters[left_index + 1 :]:
            contradicted, reason = contradiction_signal(left_cluster["canonical_claim"], right_cluster["canonical_claim"])
            if contradicted:
                contested_links.append(
                    {
                        "left_cluster_id": left_cluster["cluster_id"],
                        "right_cluster_id": right_cluster["cluster_id"],
                        "left_claim": left_cluster["canonical_claim"],
                        "right_claim": right_cluster["canonical_claim"],
                        "reason": reason,
                    }
                )
                left_cluster["contested"] = True
                right_cluster["contested"] = True
    return clusters, contested_links


def _challenge_dedup_key(cluster_id: str, challenge: str, peer_cluster_id: str = "") -> tuple[str, str, str]:
    return (str(cluster_id), normalize_claim_text(challenge), str(peer_cluster_id or ""))


def build_unresolved_conflicts(
    clusters: list[dict[str, Any]],
    contested_links: list[dict[str, Any]],
    embedding_client: Any | None = None,
    manifest: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    resolved: list[dict[str, Any]] = []
    bounded: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    seen_resolved: set[tuple[str, str, str]] = set()
    seen_bounded: set[tuple[str, str, str]] = set()
    seen_unresolved: set[tuple[str, str, str]] = set()
    for cluster in clusters:
        challenge_items = [item for item in cluster["challenge_items"] if item]
        for challenge in challenge_items:
            answered = challenge_answered_by(
                challenge,
                cluster["canonical_claim"],
                embedding_client=embedding_client,
                manifest=manifest,
                root=root,
            ) or any(
                challenge_answered_by(
                    challenge,
                    evidence,
                    embedding_client=embedding_client,
                    manifest=manifest,
                    root=root,
                )
                for evidence in cluster["evidence_items"] + cluster["uncertainty_items"]
            )
            if answered:
                continue
            for other_cluster in clusters:
                if other_cluster["cluster_id"] == cluster["cluster_id"]:
                    continue
                if challenge_answered_by(challenge, other_cluster["canonical_claim"], embedding_client=embedding_client, manifest=manifest, root=root):
                    answered = True
                    break
                if any(
                    challenge_answered_by(challenge, evidence, embedding_client=embedding_client, manifest=manifest, root=root)
                    for evidence in other_cluster["evidence_items"] + other_cluster["uncertainty_items"]
                ):
                    answered = True
                    break
            if answered:
                continue
            challenge_key = _challenge_dedup_key(cluster["cluster_id"], challenge)
            conflict_class, reason, support_matches, uncertainty_matches = _classify_unanswered_challenge(cluster, challenge)
            if conflict_class == CONFLICT_CLASS_RESOLVED:
                if challenge_key in seen_resolved:
                    continue
                seen_resolved.add(challenge_key)
                resolved.append(
                    _conflict_entry(
                        entry_id=f"resolved_{len(resolved) + 1:03d}",
                        entry_key="resolved_id",
                        conflict_class=CONFLICT_CLASS_RESOLVED,
                        cluster=cluster,
                        challenge=challenge,
                        reason=reason,
                        support_matches=support_matches,
                        uncertainty_matches=uncertainty_matches,
                        origin="challenge",
                    )
                )
                continue
            if conflict_class == CONFLICT_CLASS_BOUNDED:
                if challenge_key in seen_bounded:
                    continue
                seen_bounded.add(challenge_key)
                bounded.append(
                    _conflict_entry(
                        entry_id=f"bounded_{len(bounded) + 1:03d}",
                        entry_key="bounded_id",
                        conflict_class=CONFLICT_CLASS_BOUNDED,
                        cluster=cluster,
                        challenge=challenge,
                        reason=reason,
                        support_matches=support_matches,
                        uncertainty_matches=uncertainty_matches,
                        origin="challenge",
                    )
                )
                continue
            if challenge_key in seen_unresolved:
                continue
            seen_unresolved.add(challenge_key)
            unresolved.append(
                _conflict_entry(
                    entry_id=f"unresolved_{len(unresolved) + 1:03d}",
                    entry_key="conflict_id",
                    conflict_class=CONFLICT_CLASS_MATERIAL,
                    cluster=cluster,
                    challenge=challenge,
                    reason=reason,
                    support_matches=support_matches,
                    uncertainty_matches=uncertainty_matches,
                    origin="challenge",
                )
            )
    cluster_lookup = {cluster["cluster_id"]: cluster for cluster in clusters}
    for link in contested_links:
        left_cluster = cluster_lookup[link["left_cluster_id"]]
        right_cluster = cluster_lookup[link["right_cluster_id"]]
        conflict_key = _challenge_dedup_key(left_cluster["cluster_id"], right_cluster["canonical_claim"], right_cluster["cluster_id"])
        if conflict_key in seen_unresolved:
            continue
        seen_unresolved.add(conflict_key)
        unresolved.append(
            _conflict_entry(
                entry_id=f"unresolved_{len(unresolved) + 1:03d}",
                entry_key="conflict_id",
                conflict_class=CONFLICT_CLASS_MATERIAL,
                cluster=left_cluster,
                counter_claim=right_cluster["canonical_claim"],
                peer_cluster_id=right_cluster["cluster_id"],
                peer_models=list(right_cluster["supporting_models"]),
                reason=link["reason"],
                origin="contested_link",
            )
        )
    return resolved, bounded, unresolved


def compute_metrics(
    clusters: list[dict[str, Any]],
    contested_links: list[dict[str, Any]],
    resolved_conflicts: list[dict[str, Any]],
    unresolved_conflicts: list[dict[str, Any]],
    bounded_challenges: list[dict[str, Any]],
) -> dict[str, float]:
    cluster_count = len(clusters)
    # CP-001: challenge-origin items are disclosures, not conflicts; untagged entries stay counted as conflicts (fail-closed).
    unanswered_challenge_count = sum(1 for entry in unresolved_conflicts if str(entry.get("origin", "")) == "challenge")
    link_unresolved_count = len(unresolved_conflicts) - unanswered_challenge_count
    if cluster_count == 0:
        return {
            "arbitration_score": 0.0,
            "arbitration_score_strict": 0.0,
            "arbitration_score_soft": 0.0,
            "evidence_overlap": 0.0,
            "contradiction_count": 0,
            "agreed_ratio": 0.0,
            "contradiction_density": 0.0,
            "coverage_factor": 0.0,
            "unresolved_conflict_count": link_unresolved_count,
            "bounded_challenge_count": len(bounded_challenges),
            "resolved_conflict_count": len(resolved_conflicts),
            "material_unresolved_conflict_count": link_unresolved_count,
            "unanswered_challenge_count": unanswered_challenge_count,
            "graded_conflict_penalty": 0.0,
        }

    agreed_clusters = [cluster for cluster in clusters if len(cluster["records"]) > 1 and not cluster.get("contested")]
    one_sided_clusters = [cluster for cluster in clusters if len(cluster["records"]) == 1 and not cluster.get("contested")]
    evidence_scores: list[float] = []
    for cluster in agreed_clusters:
        evidence_items = cluster["evidence_items"]
        if len(evidence_items) < 2:
            evidence_scores.append(0.0)
            continue
        pair_scores: list[float] = []
        for index, left in enumerate(evidence_items):
            for right in evidence_items[index + 1 :]:
                pair_scores.append(evidence_similarity(left, right))
        evidence_scores.append(sum(pair_scores) / len(pair_scores) if pair_scores else 0.0)

    agreed_ratio = len(agreed_clusters) / float(cluster_count)
    contradiction_count = len(contested_links)
    contradiction_density = contradiction_count / float(cluster_count)
    coverage_factor = min(1.0, (len(agreed_clusters) + (0.4 * len(one_sided_clusters))) / float(cluster_count))
    evidence_overlap = round(sum(evidence_scores) / len(evidence_scores), 4) if evidence_scores else 0.0
    # CP-001B: strict/soft penalty inputs are contested-link items only. resolved/bounded
    # entries are challenge-origin by construction (only the challenge loop above creates
    # them), so untagged legacy entries default to challenge origin in those lists;
    # unresolved entries keep failing closed (untagged counts as contested_link and stays
    # a score input). Disclosure counts below are unchanged.
    score_resolved_count = sum(1 for entry in resolved_conflicts if str(entry.get("origin", "challenge")) == "contested_link")
    score_bounded_count = sum(1 for entry in bounded_challenges if str(entry.get("origin", "challenge")) == "contested_link")
    resolved_density = score_resolved_count / float(max(1, cluster_count))
    bounded_density = score_bounded_count / float(max(1, cluster_count))
    material_density = link_unresolved_count / float(max(1, cluster_count))

    # Strict score remains fail-closed for material contradictions while preserving graded signal for bounded or resolved risks.
    strict_penalty = min(
        1.0,
        contradiction_density
        + (STRICT_RESOLVED_PENALTY * resolved_density)
        + (STRICT_BOUNDED_PENALTY * bounded_density)
        + (STRICT_MATERIAL_PENALTY * material_density),
    )
    arbitration_score_strict = max(0.0, (agreed_ratio * 0.55) + (evidence_overlap * 0.25) + (coverage_factor * 0.20) - strict_penalty)

    # Soft score preserves exploratory signal while still penalizing unresolved material risk more than bounded tradeoffs.
    soft_penalty = min(
        0.60,
        (SOFT_RESOLVED_PENALTY * resolved_density)
        + (SOFT_BOUNDED_PENALTY * bounded_density)
        + (SOFT_MATERIAL_PENALTY * material_density),
    )
    arbitration_score_soft = max(
        0.0,
        min(
            1.0,
            (agreed_ratio * 0.35)
            + (evidence_overlap * 0.20)
            + (coverage_factor * 0.25)
            + (0.20 * math.exp(-1.5 * contradiction_density))
            - soft_penalty,
        ),
    )

    return {
        "arbitration_score": round(arbitration_score_strict, 4),
        "arbitration_score_strict": round(arbitration_score_strict, 4),
        "arbitration_score_soft": round(arbitration_score_soft, 4),
        "evidence_overlap": round(evidence_overlap, 4),
        "contradiction_count": contradiction_count,
        "agreed_ratio": round(agreed_ratio, 4),
        "contradiction_density": round(contradiction_density, 4),
        "coverage_factor": round(coverage_factor, 4),
        "unresolved_conflict_count": link_unresolved_count,
        "bounded_challenge_count": len(bounded_challenges),
        "resolved_conflict_count": len(resolved_conflicts),
        "material_unresolved_conflict_count": link_unresolved_count,
        "unanswered_challenge_count": unanswered_challenge_count,
        "graded_conflict_penalty": round(strict_penalty, 4),
    }


def summarize_clusters(clusters: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    agreed_claims: list[dict[str, Any]] = []
    contested_claims: list[dict[str, Any]] = []
    one_sided_claims: list[dict[str, Any]] = []
    for cluster in clusters:
        summary = {
            "cluster_id": cluster["cluster_id"],
            "claim": cluster["canonical_claim"],
            "supporting_models": list(cluster["supporting_models"]),
            "supporting_roles": list(cluster["supporting_roles"]),
            "record_count": len(cluster["records"]),
            "evidence_items": list(dict.fromkeys(cluster["evidence_items"])),
            "challenge_items": list(dict.fromkeys(cluster["challenge_items"])),
            "uncertainty_items": list(dict.fromkeys(cluster["uncertainty_items"])),
        }
        if cluster.get("contested"):
            contested_claims.append(summary)
        elif len(cluster["records"]) > 1:
            agreed_claims.append(summary)
        else:
            one_sided_claims.append(summary)
    return agreed_claims, contested_claims, one_sided_claims


def analyze_dialog(
    dialog_text: str,
    session_id: str,
    root: str | Path,
    topic: str = "",
    source_path: str = "",
    embedding_client: Any | None = None,
    manifest: dict[str, Any] | None = None,
    execution_mode: str = "UNKNOWN",
    dialog_origin: str = "",
    model_calls_observed: bool | None = None,
    dialog_text_source: str = "provided_dialog",
    fallback_used: bool = False,
    # Phase 20.3 — Evidence-Balanced Arbitration (advisory, opt-in)
    enable_evidence_balanced_arbitration: bool = False,
    cognition_root: str = "",
    evidence_arbitration_limit: int = 5,
    evidence_arbitration_fail_closed: bool = False,
) -> dict[str, Any]:
    warnings: list[str] = []
    root_path = Path(root).resolve()
    config = load_semantic_matching_config(root=root_path, manifest=manifest)
    turns = split_blocks(dialog_text)
    claim_records, parse_warnings = parse_turn_claims(turns)
    warnings.extend(parse_warnings)
    clusters, contested_links = cluster_claims(claim_records, embedding_client=embedding_client, manifest=manifest, root=root_path)
    resolved_conflicts, bounded_challenges, unresolved_conflicts = build_unresolved_conflicts(
        clusters,
        contested_links,
        embedding_client=embedding_client,
        manifest=manifest,
        root=root_path,
    )
    metrics = compute_metrics(clusters, contested_links, resolved_conflicts, unresolved_conflicts, bounded_challenges)
    agreed_claims, contested_claims, one_sided_claims = summarize_clusters(clusters)
    serialized_turns = serialize_turns(turns)
    output_path = root_path / "arbitration" / f"{session_id}.json"
    generated_at = utc_now_iso()
    artifact = {
        "schema_version": ARBITRATION_ARTIFACT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "timestamp_utc": generated_at,
        "artifact_type": "arbitration_result",
        "analysis_status": "completed",
        "executed": True,
        "matching_backend": MATCHING_BACKEND,
        "embedding_version": EMBEDDING_VERSION,
        "threshold_profile": {
            "CLAIM_AGREE_COSINE": round(config["threshold_agree"], 4),
            "CLAIM_VARIANCE_COSINE": round(config["threshold_variance_low"], 4),
            "CHALLENGE_ANSWER_COSINE": round(config["threshold_answer"], 4),
        },
        "session_id": session_id,
        "topic": topic,
        "source_dialog_path": source_path,
        "turn_count": len(turns),
        "model_turns": serialized_turns,
        "parsed_claim_turn_count": len(claim_records),
        "total_unique_claims": len(clusters),
        "warnings": warnings,
        "arbitration_score": metrics["arbitration_score"],
        "evidence_overlap": metrics["evidence_overlap"],
        "unresolved_conflict_count": metrics["unresolved_conflict_count"],
        "agreed_claims": agreed_claims,
        "contested_claims": contested_claims,
        "one_sided_claims": one_sided_claims,
        "resolved_conflicts": resolved_conflicts,
        "bounded_challenges": bounded_challenges,
        "unresolved_conflicts": unresolved_conflicts,
        # D2 disclosure: material challenges left unanswered at finalization are surfaced
        # distinctly (count + the items) so they are never silently dropped. Per CP-001
        # these are NOT re-counted into unresolved_conflict_count; the concurrence loop is
        # the binding mechanism for material objections.
        "unanswered_challenge_count": metrics.get("unanswered_challenge_count", 0),
        "unanswered_challenges": [
            conflict for conflict in unresolved_conflicts
            if str(conflict.get("origin", "")) == "challenge"
        ],
        "contested_links": contested_links,
        "conflict_class_counts": {
            CONFLICT_CLASS_RESOLVED: len(resolved_conflicts),
            CONFLICT_CLASS_BOUNDED: len(bounded_challenges),
            CONFLICT_CLASS_MATERIAL: len(unresolved_conflicts),
        },
        "metrics": metrics,
        "source_paths": [str(Path(source_path).resolve())] if str(source_path).strip() else [],
        "dialog_text_source": str(dialog_text_source or "provided_dialog").strip() or "provided_dialog",
        "fallback_used": bool(fallback_used),
        "generation_context": {
            "run_type": "quality_gate",
            "batch_id": "",
        },
        "artifact_path": str(output_path),
    }
    # Phase 20.3 — inject evidence-balanced advisory after artifact dict built (never auto-converts PASS/FAIL)
    if enable_evidence_balanced_arbitration:
        _claim_text = " ".join(filter(None, [
            str(artifact.get("topic", "")),
            " ".join(
                str(c.get("claim_text", "")) for c in (artifact.get("agreed_claims") or [])[:3]
            ),
        ])).strip()
        artifact["evidence_balanced_arbitration"] = _build_evidence_balanced_context(
            claim_text=_claim_text,
            topic=topic,
            cognition_root=cognition_root,
            limit=evidence_arbitration_limit,
            fail_closed=evidence_arbitration_fail_closed,
        )
    apply_provenance(
        artifact,
        execution_mode=execution_mode,
        dialog_origin=infer_dialog_origin(dialog_origin=dialog_origin, dialog_source_path=source_path),
        model_calls_observed=bool(model_calls_observed if model_calls_observed is not None else serialized_turns),
        execution_complete=True,
        failure_reason=None,
        session_id=session_id,
        timestamp=artifact["generated_at"],
        model_turns=serialized_turns,
    )
    persisted_path = persist_arbitration_artifact(
        artifact,
        session_id=session_id,
        batch_id="",
        run_type="quality_gate",
        output_dir=root_path / "arbitration",
        allow_overwrite=False,
        source_paths=[source_path] if str(source_path).strip() else [],
    )
    artifact["artifact_path"] = str(persisted_path)
    return artifact


def build_praxis_entries(artifact: dict[str, Any], synthesis_artifact_path: str) -> list[dict[str, Any]]:
    session_id = str(artifact.get("session_id", "")).strip()
    topic = str(artifact.get("topic", "")).strip()
    arbitration_path = str(artifact.get("artifact_path", "")).strip()
    entries: list[dict[str, Any]] = []

    for claim in artifact.get("agreed_claims", []):
        entries.append(
            {
                "type": "arbitration_claim",
                "content": claim.get("claim", ""),
                "metadata": {
                    "session_id": session_id,
                    "topic": topic,
                    "supporting_models": claim.get("supporting_models", []),
                    "supporting_roles": claim.get("supporting_roles", []),
                    "contested": False,
                    "relationship": "supports_synthesis",
                    "source_artifact_path": arbitration_path,
                    "synthesis_artifact_path": synthesis_artifact_path,
                    "claim_cluster_id": claim.get("cluster_id", ""),
                },
            }
        )
    for claim in artifact.get("contested_claims", []):
        entries.append(
            {
                "type": "contested_claim",
                "content": claim.get("claim", ""),
                "metadata": {
                    "session_id": session_id,
                    "topic": topic,
                    "supporting_models": claim.get("supporting_models", []),
                    "supporting_roles": claim.get("supporting_roles", []),
                    "contested": True,
                    "relationship": "contested_against_peer_claims",
                    "source_artifact_path": arbitration_path,
                    "synthesis_artifact_path": synthesis_artifact_path,
                    "claim_cluster_id": claim.get("cluster_id", ""),
                },
            }
        )
    for conflict in artifact.get("unresolved_conflicts", []):
        text_parts = [str(conflict.get("claim", "")).strip()]
        if conflict.get("challenge"):
            text_parts.append(f"Challenge: {conflict['challenge']}")
        if conflict.get("counter_claim"):
            text_parts.append(f"Counter-claim: {conflict['counter_claim']}")
        entries.append(
            {
                "type": "unresolved_conflict",
                "content": "\n".join(part for part in text_parts if part),
                "metadata": {
                    "session_id": session_id,
                    "topic": topic,
                    "supporting_models": conflict.get("supporting_models", []),
                    "peer_models": conflict.get("peer_models", []),
                    "contested": True,
                    "relationship": "unresolved_conflict",
                    "source_artifact_path": arbitration_path,
                    "synthesis_artifact_path": synthesis_artifact_path,
                    "claim_cluster_id": conflict.get("cluster_id", ""),
                    "peer_cluster_id": conflict.get("peer_cluster_id", ""),
                    "conflict_id": conflict.get("conflict_id", ""),
                    "reason": conflict.get("reason", ""),
                },
            }
        )
    return entries

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a SOVEREIGN dialog artifact into a claim arbitration artifact")
    parser.add_argument("--dialog-path", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--root", default=None,
                        help="SOVEREIGN root (default: auto-detect via .sovereign-root marker)")
    parser.add_argument("--topic", default="")
    # Phase 20.3 CLI flags
    parser.add_argument("--enable-evidence-balanced-arbitration", action="store_true", default=False)
    parser.add_argument("--cognition-root", default="")
    parser.add_argument("--evidence-arbitration-limit", type=int, default=5)
    parser.add_argument("--evidence-arbitration-fail-closed", action="store_true", default=False)
    return parser.parse_args()


def _resolve_root(cli_root):
    """Resolve SOVEREIGN root via the single authority (tools/sovereign_paths.py)."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.sovereign_paths import get_repo_root, configure_root
    return str(configure_root(str(cli_root)) if cli_root else get_repo_root())


def main() -> int:
    args = _parse_args()
    args.root = _resolve_root(args.root)
    dialog_path = Path(args.dialog_path)
    dialog_text = dialog_path.read_text(encoding="utf-8-sig")
    artifact = analyze_dialog(
        dialog_text=dialog_text,
        session_id=str(args.session_id),
        root=str(args.root),
        topic=str(args.topic),
        source_path=str(dialog_path),
        enable_evidence_balanced_arbitration=args.enable_evidence_balanced_arbitration,
        cognition_root=str(args.cognition_root),
        evidence_arbitration_limit=int(args.evidence_arbitration_limit),
        evidence_arbitration_fail_closed=args.evidence_arbitration_fail_closed,
    )
    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
