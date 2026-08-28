from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypeVar

HumanAnnotatorLabel = Literal["human", "human_corrected"]
JudgmentLabel = Literal["A_better", "B_better", "equivalent", "incomparable", "contradiction"]
DimensionLabel = Literal["A", "B", "="]
ContradictionHandlingLabel = Literal["A", "B", "=", "hard_contradiction"]
JUDGMENT_VALUES: tuple[JudgmentLabel, ...] = ("A_better", "B_better", "equivalent", "incomparable", "contradiction")
DIMENSION_NAMES: tuple[str, ...] = (
    "evidence",
    "coherence",
    "contradiction_handling",
    "uncertainty_handling",
    "specificity",
)
DIMENSION_VALUES: tuple[DimensionLabel, ...] = ("A", "B", "=")
CONTRADICTION_HANDLING_VALUES: tuple[ContradictionHandlingLabel, ...] = ("A", "B", "=", "hard_contradiction")
HUMAN_ANNOTATOR_VALUES: tuple[HumanAnnotatorLabel, ...] = ("human", "human_corrected")
EXPECTED_SOURCE_CONTEXTS: tuple[str, ...] = (
    "controlled_generation",
    "adaptive_optimization",
    "long_horizon",
    "validator_alignment",
)
LOW_CONFIDENCE_DEFAULT = 0.5
ANNOTATION_PHASE = "preference_learning_human_annotation"
ANNOTATION_SCHEMA_VERSION = "preference_learning_human_annotation.v2"
T = TypeVar("T")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_text(text: str | None) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_relative_path(root: Path, path: Path) -> str:
    root = root.resolve()
    path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Refusing to use path outside allowed root: {path}") from exc
    return str(path)


def load_json(path: Path, default: T | None = None) -> T | None:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        raw_lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return rows
    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def validate_judgment(value: str | None) -> JudgmentLabel | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized not in JUDGMENT_VALUES:
        raise ValueError(f"Unsupported judgment value: {normalized}")
    return normalized  # type: ignore[return-value]


def validate_dimension_judgment(value: str | None, *, dimension_name: str) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    allowed_values = CONTRADICTION_HANDLING_VALUES if dimension_name == "contradiction_handling" else DIMENSION_VALUES
    if normalized not in allowed_values:
        raise ValueError(f"Unsupported {dimension_name} value: {normalized}")
    return normalized


def validate_annotator(value: str | None) -> HumanAnnotatorLabel | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized not in HUMAN_ANNOTATOR_VALUES:
        raise ValueError(f"Unsupported annotator value: {normalized}")
    return normalized  # type: ignore[return-value]


def coerce_confidence(value: Any, *, minimum: float = 0.0, maximum: float = 1.0) -> float | None:
    if value is None or value == "":
        return None
    confidence = float(value)
    if confidence < minimum or confidence > maximum:
        raise ValueError(f"Confidence must be between {minimum:.1f} and {maximum:.1f}.")
    return round(confidence, 4)


@dataclass
class DimensionJudgments:
    evidence: str | None = None
    coherence: str | None = None
    contradiction_handling: str | None = None
    uncertainty_handling: str | None = None
    specificity: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "DimensionJudgments":
        payload = payload or {}
        return cls(
            evidence=validate_dimension_judgment(payload.get("evidence"), dimension_name="evidence"),
            coherence=validate_dimension_judgment(payload.get("coherence"), dimension_name="coherence"),
            contradiction_handling=validate_dimension_judgment(
                payload.get("contradiction_handling"),
                dimension_name="contradiction_handling",
            ),
            uncertainty_handling=validate_dimension_judgment(
                payload.get("uncertainty_handling"),
                dimension_name="uncertainty_handling",
            ),
            specificity=validate_dimension_judgment(payload.get("specificity"), dimension_name="specificity"),
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "evidence": self.evidence,
            "coherence": self.coherence,
            "contradiction_handling": self.contradiction_handling,
            "uncertainty_handling": self.uncertainty_handling,
            "specificity": self.specificity,
        }

    def has_any_value(self) -> bool:
        return any(getattr(self, name) is not None for name in DIMENSION_NAMES)

    def has_all_values(self) -> bool:
        return all(getattr(self, name) is not None for name in DIMENSION_NAMES)


@dataclass
class ComparisonPair:
    pair_id: str
    source_context: str
    output_a_id: str
    output_b_id: str
    output_a_text: str
    output_b_text: str
    topic: str | None = None
    artifact_source_paths: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    judgment: JudgmentLabel | None = None
    confidence: float | None = None
    reasoning: str | None = None
    dimension_judgments: DimensionJudgments = field(default_factory=DimensionJudgments)
    annotator: HumanAnnotatorLabel | None = None
    annotation_phase: str | None = None
    schema_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["output_a_text"] = normalize_text(self.output_a_text)
        payload["output_b_text"] = normalize_text(self.output_b_text)
        payload["reasoning"] = normalize_text(self.reasoning)
        payload["topic"] = normalize_text(self.topic) or None
        payload["artifact_source_paths"] = {str(key): str(value) for key, value in self.artifact_source_paths.items()}
        payload["judgment"] = validate_judgment(self.judgment)
        payload["confidence"] = coerce_confidence(self.confidence)
        payload["annotator"] = validate_annotator(self.annotator)
        payload["annotation_phase"] = normalize_text(self.annotation_phase) or None
        payload["schema_version"] = normalize_text(self.schema_version) or None
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ComparisonPair":
        return cls(
            pair_id=str(payload.get("pair_id", "")).strip(),
            source_context=str(payload.get("source_context", "")).strip(),
            output_a_id=str(payload.get("output_a_id", "")).strip(),
            output_b_id=str(payload.get("output_b_id", "")).strip(),
            output_a_text=normalize_text(payload.get("output_a_text")),
            output_b_text=normalize_text(payload.get("output_b_text")),
            topic=normalize_text(payload.get("topic")) or None,
            artifact_source_paths={str(key): str(value) for key, value in dict(payload.get("artifact_source_paths") or {}).items()},
            created_at=str(payload.get("created_at") or utc_now_iso()),
            judgment=validate_judgment(payload.get("judgment")),
            confidence=coerce_confidence(payload.get("confidence")),
            reasoning=normalize_text(payload.get("reasoning")) or None,
            dimension_judgments=DimensionJudgments.from_dict(payload.get("dimension_judgments")),
            annotator=validate_annotator(payload.get("annotator")),
            annotation_phase=normalize_text(payload.get("annotation_phase")) or None,
            schema_version=normalize_text(payload.get("schema_version")) or None,
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass
class ComparisonJudgment:
    pair_id: str
    source_context: str
    output_a_id: str
    output_b_id: str
    topic: str | None
    artifact_source_paths: dict[str, str]
    judgment: JudgmentLabel
    confidence: float
    reasoning: str
    dimension_judgments: DimensionJudgments = field(default_factory=DimensionJudgments)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasoning"] = normalize_text(self.reasoning)
        payload["topic"] = normalize_text(self.topic) or None
        payload["judgment"] = validate_judgment(self.judgment)
        payload["confidence"] = coerce_confidence(self.confidence)
        return payload

    @classmethod
    def from_pair(cls, pair: ComparisonPair) -> "ComparisonJudgment":
        if pair.judgment is None or pair.confidence is None or not normalize_text(pair.reasoning):
            raise ValueError(f"Pair {pair.pair_id} is missing required annotation fields.")
        return cls(
            pair_id=pair.pair_id,
            source_context=pair.source_context,
            output_a_id=pair.output_a_id,
            output_b_id=pair.output_b_id,
            topic=pair.topic,
            artifact_source_paths=pair.artifact_source_paths,
            judgment=pair.judgment,
            confidence=pair.confidence,
            reasoning=pair.reasoning or "",
            dimension_judgments=pair.dimension_judgments,
            created_at=utc_now_iso(),
        )


@dataclass
class SignalObservation:
    pair_id: str
    source_context: str
    output_a_id: str
    output_b_id: str
    topic: str | None
    created_at: str
    embedding_available: bool
    embedding_model: str | None
    embedding_cosine_similarity: float | None
    embedding_error: str | None
    signals: dict[str, float | int | bool | None]
    artifact_source_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["topic"] = normalize_text(self.topic) or None
        payload["artifact_source_paths"] = {str(key): str(value) for key, value in self.artifact_source_paths.items()}
        return payload


@dataclass
class AnnotationQualityReport:
    generated_at: str
    report_path: str
    total_comparisons: int
    judgment_distribution: dict[str, int]
    confidence_distribution: dict[str, int]
    low_confidence_count: int
    incomparable_rate: float
    missing_reasoning_count: int
    source_context_coverage: dict[str, int]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
