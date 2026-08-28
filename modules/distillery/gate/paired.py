from __future__ import annotations

import random
import statistics
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from math import sqrt
from statistics import NormalDist

from distillery.common import ContractError, sha256_value


TAIL_TWO_SIDED = "two-sided"
TAIL_LOWER_ONE_SIDED = "lower-one-sided"
SUPPORTED_TAILS = {TAIL_TWO_SIDED, TAIL_LOWER_ONE_SIDED}


def _utc_timestamp(value: str | None, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be a parseable timezone-aware UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ContractError(f"{field} must be a timezone-aware UTC timestamp")
    return parsed.astimezone(UTC)


def _validate_tail(tail: str) -> None:
    if tail not in SUPPORTED_TAILS:
        raise ContractError(f"tail must be one of {sorted(SUPPORTED_TAILS)}")


@dataclass(frozen=True)
class GateMargins:
    minimum_target_gain: float
    max_parent_regression: float
    max_best_regression: float
    margins_declared_at: str | None
    margin_authority: str

    def __post_init__(self) -> None:
        if min(self.minimum_target_gain, self.max_parent_regression, self.max_best_regression) < 0:
            raise ContractError("M/T/D policy margins must be non-negative")
        _utc_timestamp(self.margins_declared_at, "margins_declared_at")
        if not self.margin_authority:
            raise ContractError("M/T/D margin_authority is required")


@dataclass(frozen=True)
class EvaluationRun:
    eval_run_id: str
    eval_started_at: str | None
    suite_version: str
    suite_hash: str

    def __post_init__(self) -> None:
        if not self.eval_run_id or not self.suite_version:
            raise ContractError("eval_run_id and suite_version are required")
        _utc_timestamp(self.eval_started_at, "eval_started_at")
        if len(self.suite_hash) != 64 or any(character not in "0123456789abcdef" for character in self.suite_hash.lower()):
            raise ContractError("suite_hash must be a SHA-256 hex digest")


def _assert_predeclared(margins: GateMargins, eval_run: EvaluationRun) -> dict:
    declared = _utc_timestamp(margins.margins_declared_at, "margins_declared_at")
    started = _utc_timestamp(eval_run.eval_started_at, "eval_started_at")
    if declared >= started:
        raise ContractError("M/T/D margins must be declared strictly before evaluation starts")
    evidence = {
        "eval_run_id": eval_run.eval_run_id,
        "eval_started_at": eval_run.eval_started_at,
        "margins_declared_at": margins.margins_declared_at,
        "margin_authority": margins.margin_authority,
        "suite_version": eval_run.suite_version,
        "suite_hash": eval_run.suite_hash.lower(),
    }
    return {**evidence, "predeclaration_evidence_hash": sha256_value(evidence)}


def paired_mean_ci(
    deltas: list[float],
    *,
    tail: str,
    confidence: float = 0.95,
    resamples: int = 4000,
    seed: int = 0,
) -> dict:
    if not deltas or not 0 < confidence < 1 or resamples < 100:
        raise ContractError("invalid paired CI input")
    _validate_tail(tail)
    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(statistics.fmean(deltas[rng.randrange(n)] for _ in range(n)) for _ in range(resamples))
    alpha = 1.0 - confidence
    lower_probability = alpha / 2 if tail == TAIL_TWO_SIDED else alpha
    lower_index = max(0, min(resamples - 1, int(lower_probability * resamples)))
    upper_index = min(resamples - 1, max(0, int((1 - alpha / 2) * resamples) - 1)) if tail == TAIL_TWO_SIDED else None
    return {
        "n": n,
        "mean": statistics.fmean(deltas),
        "lcb": means[lower_index],
        "ucb": means[upper_index] if upper_index is not None else None,
        "confidence": confidence,
        "tail": tail,
        "lcb_one_sided_equivalent_confidence": 1 - lower_probability,
        "method": "paired_bootstrap_percentile",
        "resamples": resamples,
        "seed": seed,
    }


def paired_gate(
    item_ids: list[str],
    candidate: list[float],
    target_reference: list[float],
    parent: list[float],
    historical_best: list[float],
    margins: GateMargins,
    eval_run: EvaluationRun,
    *,
    tail: str,
    confidence: float = 0.95,
    hard_bands: dict[str, bool] | None = None,
) -> dict:
    predeclaration = _assert_predeclared(margins, eval_run)
    _validate_tail(tail)
    if len({len(item_ids), len(candidate), len(target_reference), len(parent), len(historical_best)}) != 1 or not item_ids or len(set(item_ids)) != len(item_ids):
        raise ContractError("unpaired evaluation path rejected")
    hard_bands = hard_bands or {"A": True, "B": True, "C_HERMETIC": True, "C_FLOOR": True}
    required = {"A", "B", "C_HERMETIC", "C_FLOOR"}
    if not required.issubset(hard_bands):
        raise ContractError("all hard bands require explicit results")
    comparisons = {
        "target": paired_mean_ci([c - r for c, r in zip(candidate, target_reference, strict=True)], tail=tail, confidence=confidence, seed=11),
        "parent": paired_mean_ci([c - r for c, r in zip(candidate, parent, strict=True)], tail=tail, confidence=confidence, seed=12),
        "historical_best": paired_mean_ci([c - r for c, r in zip(candidate, historical_best, strict=True)], tail=tail, confidence=confidence, seed=13),
    }
    rules = {
        "target": comparisons["target"]["lcb"] >= margins.minimum_target_gain,
        "parent": comparisons["parent"]["lcb"] >= -margins.max_parent_regression,
        "historical_best": comparisons["historical_best"]["lcb"] >= -margins.max_best_regression,
        "hard_bands": all(hard_bands[name] for name in required),
    }
    return {
        "passed": all(rules.values()),
        "rules": rules,
        "comparisons": comparisons,
        "margins": asdict(margins),
        "evaluation_run": asdict(eval_run),
        "predeclaration": predeclaration,
        "confidence_policy": {
            "confidence": confidence,
            "tail": tail,
            "interpretation": "two-sided 95% interval; LCB equals a 97.5% one-sided lower bound" if tail == TAIL_TWO_SIDED and confidence == 0.95 else "explicit tail policy recorded in comparison metadata",
        },
        "band_d_advisory_only": True,
    }


def power_report(
    differences: list[float],
    *,
    policy_margins: GateMargins,
    tail: str,
    confidence: float = 0.95,
) -> dict:
    if len(differences) < 2:
        raise ContractError("power report requires at least two paired observations")
    _validate_tail(tail)
    alpha = 1.0 - confidence
    quantile = 1 - alpha / 2 if tail == TAIL_TWO_SIDED else confidence
    z_value = NormalDist().inv_cdf(quantile)
    dispersion = statistics.stdev(differences)
    return {
        "n": len(differences),
        "paired_dispersion": dispersion,
        "detectable_effect_floor": z_value * dispersion / sqrt(len(differences)),
        "confidence": confidence,
        "tail": tail,
        "z_value": z_value,
        "policy_margins": asdict(policy_margins),
        "margins_selected_from_power": False,
    }
