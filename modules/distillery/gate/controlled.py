from __future__ import annotations

from typing import Callable

from distillery.common import ContractError
from gate.paired import EvaluationRun, GateMargins, paired_gate


FIXED_FIELDS = {"prompt", "tools", "retrieval", "memory", "sandbox", "serving_policy", "eval_suite"}


def controlled_model_effect(baseline_config: dict, candidate_config: dict, evaluator: Callable[[dict], tuple[list[str], list[float]]], *, target_reference: list[float], historical_best: list[float], margins: GateMargins, eval_run: EvaluationRun, tail: str) -> dict:
    missing = FIXED_FIELDS - baseline_config.keys() | FIXED_FIELDS - candidate_config.keys()
    if missing:
        raise ContractError(f"controlled evaluation missing fixed fields: {sorted(missing)}")
    differences = {key for key in set(baseline_config) | set(candidate_config) if baseline_config.get(key) != candidate_config.get(key)}
    if differences != {"model_intervention"}:
        raise ContractError(f"controlled evaluation changed forbidden fields: {sorted(differences - {'model_intervention'})}")
    base_ids, base_scores = evaluator(baseline_config)
    candidate_ids, candidate_scores = evaluator(candidate_config)
    if base_ids != candidate_ids:
        raise ContractError("controlled evaluator returned unpaired item IDs")
    return {"config_diff": ["model_intervention"], "gate": paired_gate(candidate_ids, candidate_scores, target_reference, base_scores, historical_best, margins, eval_run, tail=tail)}
