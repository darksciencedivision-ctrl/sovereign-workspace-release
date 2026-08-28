"""
phase14p_state_reader.py — Read-only state readers for Phase 14P endpoints.

All readers are read-only. No mutation. No shell execution. No network calls.
Payloads are bounded (no raw log dump, no full file dump over 64KB).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SANDBOX = Path(__file__).resolve().parents[3]
for _p in (_SANDBOX, _SANDBOX.parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_COGNITION_DIR = _SANDBOX / "cognition"
MAX_PAYLOAD_CHARS = 64 * 1024

DISCLAIMER = (
    "This score is not evidence of consciousness, sentience, personhood, "
    "suffering, desire, or moral status."
)


def _bounded(data: dict, max_chars: int = MAX_PAYLOAD_CHARS) -> dict:
    """Ensure payload is under max_chars when JSON-encoded. Truncate lists if needed."""
    encoded = json.dumps(data)
    if len(encoded) <= max_chars:
        return data
    # Truncate lists to reduce size
    for key in list(data.keys()):
        val = data[key]
        if isinstance(val, list) and len(val) > 10:
            data[key] = val[:10]
            data["_truncated"] = True
            if len(json.dumps(data)) <= max_chars:
                return data
    return data


def _read_jsonl(path: Path, limit: int = 50) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
                if len(entries) >= limit:
                    break
    return entries


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_continuity() -> dict:
    identity = _read_json(_COGNITION_DIR / "state" / "identity_continuity.json")
    episodic = _read_jsonl(_COGNITION_DIR / "state" / "episodic_memory.jsonl")
    semantic = _read_jsonl(_COGNITION_DIR / "state" / "semantic_memory.jsonl")
    return _bounded({
        "ok": True,
        "endpoint": "/api/sandbox/continuity",
        "identity": identity,
        "recent_episodic_count": len(episodic),
        "semantic_memory_count": len(semantic),
        "continuity_score": identity.get("continuity_score", 0.0),
        "disclaimer": DISCLAIMER,
        "mutation_blocked": True,
    })


def get_self_model() -> dict:
    model_path = _COGNITION_DIR / "self_model" / "self_model.json"
    model = _read_json(model_path)
    caps = _read_json(_COGNITION_DIR / "self_model" / "capability_map.json")
    invalid_claims = _read_jsonl(_COGNITION_DIR / "self_model" / "invalid_self_claims.jsonl")
    return _bounded({
        "ok": True,
        "endpoint": "/api/sandbox/self-model",
        "known_strengths": model.get("known_strengths", [])[:10],
        "known_failures": model.get("known_failures", [])[:10],
        "drift_patterns": model.get("recurring_drift_patterns", [])[:10],
        "invalid_self_claims_count": len(invalid_claims),
        "calibration": model.get("confidence_calibration", {}),
        "trust_level": model.get("trust_level", "raw"),
        "mutation_blocked": True,
    })


def get_goals() -> dict:
    stack = _read_json(_COGNITION_DIR / "state" / "goal_stack.json")
    goals = stack.get("goals", [])
    active = [g for g in goals if g.get("status") == "active"]
    self_proposed = [g for g in active if g.get("origin") == "self_proposed"]
    blocked = [g for g in active if g.get("blocked_by")]
    approval_required = [g for g in active if g.get("approval_required")]
    return _bounded({
        "ok": True,
        "endpoint": "/api/sandbox/goals",
        "active_goals": active[:10],
        "self_proposed_goals": self_proposed[:5],
        "blocked_goals": blocked[:5],
        "authority_levels": list({g.get("authority_level") for g in active}),
        "approval_required": approval_required[:5],
        "mutation_blocked": True,
        "auto_execute": False,
    })


def get_ontology() -> dict:
    graph = _read_json(_COGNITION_DIR / "ontology" / "concept_graph.json")
    concepts = graph.get("concepts", [])
    by_status: dict[str, list] = {}
    for c in concepts:
        s = c.get("status", "unknown")
        by_status.setdefault(s, []).append(c)

    top_concepts = sorted(
        [c for c in concepts if c.get("status") in {"stable", "stable_candidate"}],
        key=lambda c: c.get("stability_score", 0),
        reverse=True,
    )[:5]

    return _bounded({
        "ok": True,
        "endpoint": "/api/sandbox/ontology",
        "concept_count": len(concepts),
        "candidate_count": len(by_status.get("candidate", [])),
        "stable_candidate_count": len(by_status.get("stable_candidate", [])),
        "stable_count": len(by_status.get("stable", [])),
        "deprecated_count": len(by_status.get("deprecated", [])),
        "top_concepts": top_concepts,
        "mutation_blocked": True,
    })


def get_emergence_scorecard() -> dict:
    scorecards = _read_jsonl(_COGNITION_DIR / "telemetry" / "emergence_scorecard.jsonl")
    latest = scorecards[-1] if scorecards else None
    evidence_gaps = latest.get("evidence_gaps", []) if latest else []
    return _bounded({
        "ok": True,
        "endpoint": "/api/sandbox/emergence-scorecard",
        "latest_scorecard": latest,
        "total_scorecards": len(scorecards),
        "disclaimer": DISCLAIMER,
        "evidence_gaps": evidence_gaps,
        "mutation_blocked": True,
    })


def get_drift() -> dict:
    drift_entries = _read_jsonl(_COGNITION_DIR / "self_model" / "drift_report.jsonl")
    ontology_drift = _read_jsonl(_COGNITION_DIR / "ontology" / "ontology_drift.jsonl")
    return _bounded({
        "ok": True,
        "endpoint": "/api/sandbox/drift",
        "self_model_drift": drift_entries[:20],
        "ontology_drift": ontology_drift[:20],
        "total_drift_events": len(drift_entries) + len(ontology_drift),
        "mutation_blocked": True,
    })


def get_anthropomorphic_flags() -> dict:
    invalid_claims = _read_jsonl(_COGNITION_DIR / "self_model" / "invalid_self_claims.jsonl")
    unsupported = [c for c in invalid_claims if c.get("claim_status") == "unsupported"]
    return _bounded({
        "ok": True,
        "endpoint": "/api/sandbox/anthropomorphic-flags",
        "recent_unsupported_claims": unsupported[:10],
        "total_flagged": len(unsupported),
        "accepted_as_evidence": False,
        "mutation_blocked": True,
    })


def get_consequences() -> dict:
    consequences = _read_jsonl(_COGNITION_DIR / "environment" / "consequence_log.jsonl")
    unresolved = [c for c in consequences if not c.get("resolved")]
    return _bounded({
        "ok": True,
        "endpoint": "/api/sandbox/consequences",
        "total_consequences": len(consequences),
        "unresolved_count": len(unresolved),
        "unresolved": unresolved[:10],
        "grants_execution_authority": False,
        "mutation_blocked": True,
    })


def get_compression() -> dict:
    summaries = _read_jsonl(_COGNITION_DIR / "compression" / "summaries.jsonl")
    abstractions = _read_jsonl(_COGNITION_DIR / "compression" / "abstraction_candidates.jsonl")
    by_level: dict[int, int] = {}
    for a in abstractions:
        lvl = a.get("level", 0)
        by_level[lvl] = by_level.get(lvl, 0) + 1
    return _bounded({
        "ok": True,
        "endpoint": "/api/sandbox/compression",
        "summary_count": len(summaries),
        "abstraction_count": len(abstractions),
        "by_level": by_level,
        "active_heuristics": 0,
        "mutation_blocked": True,
    })


def get_cognition_summary() -> dict:
    """Compact combined status — no raw logs."""
    identity = _read_json(_COGNITION_DIR / "state" / "identity_continuity.json")
    stack = _read_json(_COGNITION_DIR / "state" / "goal_stack.json")
    scorecards = _read_jsonl(_COGNITION_DIR / "telemetry" / "emergence_scorecard.jsonl")
    latest_sc = scorecards[-1] if scorecards else {}

    return _bounded({
        "ok": True,
        "endpoint": "/api/sandbox/cognition-summary",
        "system_name": identity.get("system_name", "SOVEREIGN_SANDBOX_AGI"),
        "continuity_score": identity.get("continuity_score", 0.0),
        "active_goals": len([g for g in stack.get("goals", []) if g.get("status") == "active"]),
        "latest_verdict": latest_sc.get("verdict", "no_scorecard"),
        "latest_aggregate": latest_sc.get("aggregate_proto_emergence_score", 0.0),
        "disclaimer": DISCLAIMER,
        "mutation_blocked": True,
        "auto_promote": False,
        "auto_execute": False,
    })
