"""Phase 0 scaffolding: the @1.0 schemas compile, cross-resolve, and enforce their bounds.

Grounding: Architecture Plan v1.0.1 section 9; Buildout Directive Phase 0.
These tests validate the FROZEN schema set. A failure here after the freeze signature
means an unauthorized schema change.
"""
import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
NAMES = [
    "project", "node", "task", "message", "artifact", "memory",
    "evidence", "debate", "gate", "permission", "usage", "checkpoint",
]

SCHEMAS = {n: json.loads((SCHEMA_DIR / f"{n}.schema.json").read_text(encoding="utf-8")) for n in NAMES}
STORE = {s["$id"]: s for s in SCHEMAS.values()}


def validator(name: str) -> jsonschema.Draft7Validator:
    schema = SCHEMAS[name]
    resolver = jsonschema.RefResolver(base_uri=schema["$id"], referrer=schema, store=STORE)
    return jsonschema.Draft7Validator(schema, resolver=resolver)


CAP = {
    "capability": "coding",
    "requirements": {"tool_use": True, "min_context": 32000, "structured_output": True, "locality": "any", "harness_class": "coding_tui"},
    "cost_class": "local",
    "priority": 1,
}
PROV = {
    "author_node": "n-worker-1", "model": "mock", "task_id": "t-001",
    "ts": "2026-07-16T12:00:00Z", "directive_version": "v2.4",
    "source_artifacts": [], "evidence": [], "confidence": "medium",
    "reviewers": [], "gate_result": None, "supersedes": None,
}
SHA = "sha256:" + "a" * 64

VALID = {
    "project": {
        "project_id": "p-sow", "name": "sovereign-orchestration-workspace",
        "objective": "Windows-native, CLI-first, multi-model orchestration workspace under the v2.4 contract.",
        "directive_version": "v2.4", "status": "ACTIVE", "created_ts": "2026-07-16T12:00:00Z",
        "operator": "Sam",
        "active_profile": {"id": "hybrid", "network": "egress_controlled", "eligible_adapters": ["mock"], "excluded_adapters": [], "sovereign_contract_version": "v2.4"},
        "schema": "project@1.0",
    },
    "node": {
        "node_id": "3f2a6c1e-9d4b-4e8a-b0c7-1a2b3c4d5e6f", "class": "worker_coding_specialist",
        "adapter": "mock", "harness": None, "model_ref": None, "locality": "local",
        "subscription_ref": None, "capabilities": [CAP],
        "workspace": {"type": "git_worktree", "path": "worktrees/n1"},
        "permission_profile_id": "coding-default", "auth": {"mcp_credential_id": "cred-ref-1"},
        "state": "READY", "offline_profile_eligible": True, "spawned_by_supervisor": True,
        "schema": "node@1.0",
    },
    "task": {
        "task_id": "t-001", "parent": None, "deps": [], "capability_req": CAP,
        "assigned_node": None, "state": "PENDING", "artifacts": [SHA], "gate_id": "g-001",
        "budget": {"tokens": 10000, "wallclock_s": 600}, "schema": "task@1.0",
    },
    "message": {
        "msg_id": "3f2a6c1e-9d4b-4e8a-b0c7-1a2b3c4d5e60", "ts": "2026-07-16T12:00:00Z",
        "schema": "envelope@1.0", "from_node": "n-conductor", "to": ["n-worker-1"],
        "type": "task_assign", "task_id": "t-001", "payload_schema": "task@1.0",
        "payload": {"task_id": "t-001"},
        "auth": {"node_credential": "cred", "scope": "p-sow/t-001/conductor"},
        "integrity": "b" * 64,
    },
    "artifact": {
        "artifact_id": SHA, "media_type": "text/markdown", "size_bytes": 1024,
        "created_by_node": "n-worker-1", "task_id": "t-001", "ts": "2026-07-16T12:00:00Z",
        "storage": {"store": "cas", "path_hint": "artifacts/aa/aaaa"},
        "provenance_entry": "m-001", "schema": "artifact@1.0",
    },
    "memory": {
        "entry_id": "m-001", "project_id": "p-sow", "tier": "shared_project",
        "kind": "finding", "status": "CANDIDATE", "provenance": PROV,
        "content_hash": SHA, "version": 1, "prev_version_ref": None, "schema": "memory@1.0",
    },
    "evidence": {
        "evidence_id": "e-001", "kind": "test_output", "summary": "pytest run: all schema tests pass",
        "artifact_refs": [SHA], "produced_by_node": "n-build", "task_id": "t-001",
        "ts": "2026-07-16T12:00:00Z", "confidence": "high",
        "claims": [{"claim": "schemas validate", "supported": True, "source": "pytest"}],
        "schema": "evidence@1.0",
    },
    "debate": {
        "debate_id": "d-001",
        "request": {
            "caller_node": "n-worker-1", "topic": "conflicting eligibility findings",
            "artifact_refs": [SHA], "participants": [CAP], "max_rounds": 5,
            "budget": {"tokens": 20000}, "gate_id": "g-001", "early_stop_criteria": "convergence",
        },
        "result": {
            "rounds_used": 2,
            "positions": [{"node": "n-a", "position": "supported", "evidence_refs": ["e-001"]}],
            "outcome": "DISSENT_PRESERVED", "dissent": "n-b maintains the finding lacks a reproduction",
            "evidence_map": {"claim-1": ["e-001"]}, "cost_actual": {"tokens": 8000, "usage_units": 0},
        },
        "schema": "debate@1.0",
    },
    "gate": {
        "gate_id": "g-001", "kind": "stage",
        "criteria": ["artifact validates against its schema", "provenance present"],
        "verdict": "PASS", "evidence": ["e-001"], "debate_ref": "d-001",
        "decided_by": "gate_engine", "reasons": ["all criteria met"], "task_id": "t-001",
        "schema": "gate@1.0",
    },
    "permission": {
        "profile_id": "coding-default", "description": "coding worker, worktree-scoped",
        "node_class": "worker_coding_specialist", "default_stance": "deny",
        "rules": [
            {"action_class": "fs_write", "scope": "workspace/**", "effect": "allow"},
            {"action_class": "network_egress", "scope": "*", "effect": "deny"},
            {"action_class": "git", "scope": "push", "effect": "require_approval"},
        ],
        "fs": {"workspace_only": True, "extra_read_paths": []},
        "network": {"egress": "deny_all", "allowlist": []},
        "protected_actions": ["merge_to_main", "delete_branch"],
        "schema": "permission@1.0",
    },
    "usage": {
        "usage_id": "u-001", "node_id": "n-worker-1", "task_id": "t-001", "adapter": "mock",
        "ts_start": "2026-07-16T12:00:00Z", "ts_end": "2026-07-16T12:05:00Z",
        "tokens_in": 1000, "tokens_out": 2000, "usage_units": None, "wallclock_s": 300,
        "cost_class": "local", "subscription_ref": None, "notes": "", "schema": "usage@1.0",
    },
    "checkpoint": {
        "checkpoint_id": "s-001", "kind": "succession_snapshot", "ts": "2026-07-16T12:00:00Z",
        "trigger": "major_event", "tasks": "taskgraph@v3", "nodes": "registry@v5",
        "debates": ["d-001"], "gates": ["g-001"], "memory_heads": {"m-key": "m-001@1"},
        "routing": "routing@v2", "outstanding_issues": ["U9 open"], "directive_version": "v2.4",
        "conductor": {"model": "fable-5", "adapter": None, "reason": "operator_selected", "since": "2026-07-16T00:00:00Z", "directive_version": "v2.4", "subscription_ref": None},
        "integrity": SHA, "schema": "checkpoint@1.0",
    },
}


@pytest.mark.parametrize("name", NAMES)
def test_schema_is_valid_draft7(name):
    jsonschema.Draft7Validator.check_schema(SCHEMAS[name])


@pytest.mark.parametrize("name", NAMES)
def test_valid_instance_passes(name):
    validator(name).validate(VALID[name])


@pytest.mark.parametrize(
    "name,mutation",
    [
        ("debate", lambda o: o["request"].__setitem__("max_rounds", 6)),          # bound: <=5 rounds (invariant 14)
        ("memory", lambda o: o.__setitem__("status", "SELF_ACCEPTED")),           # lifecycle enum closed (I-M6)
        ("node", lambda o: o.__setitem__("state", "RUNNING")),                    # state machine closed
        ("message", lambda o: o.pop("integrity")),                                # unsigned envelope rejected (TB-2)
        ("permission", lambda o: o.__setitem__("default_stance", "allow")),       # deny-by-default is const
        ("task", lambda o: o["artifacts"].__setitem__(0, "md5:abc")),             # CAS refs are sha256 only
        ("memory", lambda o: o["provenance"].pop("author_node")),                 # provenance mandatory (I-M5)
        ("checkpoint", lambda o: o["conductor"].__setitem__("reason", "self_promoted")),  # succession reasons closed
    ],
)
def test_invalid_instance_rejected(name, mutation):
    import copy
    obj = copy.deepcopy(VALID[name])
    mutation(obj)
    with pytest.raises(jsonschema.ValidationError):
        validator(name).validate(obj)


def test_cross_schema_refs_resolve():
    """task/debate/project reference node@1.0 definitions across files."""
    validator("task").validate(VALID["task"])
    validator("debate").validate(VALID["debate"])
    validator("project").validate(VALID["project"])


def test_frozen_schema_count_is_exactly_twelve():
    files = sorted(p.name for p in SCHEMA_DIR.glob("*.schema.json"))
    assert len(files) == 12, f"schema set is frozen at 12, found {files}"
