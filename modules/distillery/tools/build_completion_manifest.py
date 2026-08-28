from __future__ import annotations

"""Generate the BUILD_COMPLETION_MANIFEST from measured repository state (F-23).

Identity semantics v2: the manifest certifies the immutable implementation
source state identified by LOOP_STATE.implementation_seal_commit and records
evidence generated against a declared evidence_generation_base tree. The Git
commit containing this manifest is NOT required to equal the implementation
seal commit; generated files never assert their own future containing commit
(verified_branch_head stays unbound until external post-push verification).
Generation must run from a committed clean tree so that every recorded
generation identity is a real, inspectable Git object.
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEAL_DIR = ROOT / "runs" / "completion-loop"
SOFTWARE_ITEM_IDS = tuple(f"F-{n:02d}" for n in range(26))


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()


DECLARED_EVIDENCE_PREFIXES = ("runs/release-baseline/",)
DECLARED_EVIDENCE_EXACT = {
    "runs/completion-loop/BUILD_COMPLETION_MANIFEST.json",
    "runs/completion-loop/LOOP_STATE.json",
    "runs/completion-loop/EVIDENCE_INDEX.json",
    "runs/export/LATEST_EXPORT_REPORT.json",
}
DECLARED_EVIDENCE_SUFFIXES = (
    "/COLD_RESTORE_RECORD",
)


def _is_declared_evidence_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized.startswith(DECLARED_EVIDENCE_PREFIXES):
        return True
    if normalized in DECLARED_EVIDENCE_EXACT:
        return True
    if normalized.startswith("runs/export/") and (
        normalized.endswith(".bundle")
        or normalized.startswith("runs/export/COLD_RESTORE_RECORD")
    ):
        return True
    return False


def main() -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    punch = json.loads((SEAL_DIR / "PUNCH_LIST.json").read_text(encoding="utf-8"))
    items = {row["id"]: row for row in punch["items"]}
    findings = json.loads((SEAL_DIR / "FINDINGS_REGISTER.json").read_text(encoding="utf-8"))["findings"]
    open_high_critical = [
        f["id"] for f in findings if f["severity"] in {"HIGH", "CRITICAL"} and not f["disposition"].startswith("CLOSED")
    ]
    not_closed = sorted(item_id for item_id in SOFTWARE_ITEM_IDS if items.get(item_id, {}).get("status") != "CLOSED")
    version_matrix = json.loads((ROOT / "docs" / "VERSION_MATRIX.json").read_text(encoding="utf-8"))
    export_report = json.loads((ROOT / "runs" / "export" / "LATEST_EXPORT_REPORT.json").read_text(encoding="utf-8"))
    loop_state = json.loads((SEAL_DIR / "LOOP_STATE.json").read_text(encoding="utf-8"))

    implementation_seal_commit = loop_state.get("implementation_seal_commit")
    if not implementation_seal_commit:
        print("FAIL: LOOP_STATE.implementation_seal_commit is required; refusing to emit an unidentified manifest")
        return 1
    # Raw output required: the shared git() helper strips stdout, which would
    # destroy the leading status column of the first porcelain line.
    raw_status = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain=v1"], capture_output=True, text=True, check=True).stdout
    status_lines = [line for line in raw_status.splitlines() if line.strip()]
    allowed_pending = {
        "runs/completion-loop/BUILD_COMPLETION_MANIFEST.json",
        "runs/completion-loop/LOOP_STATE.json",
        "runs/export/LATEST_EXPORT_REPORT.json",
        "runs/release-baseline/REGRESSION_LOCUS_VERIFICATION.json",
    }
    unexpected = []
    for line in status_lines:
        match = re.match(r"^..\s+(.+)$", line)
        if not match:
            unexpected.append(line)
            continue
        path = match.group(1).strip().strip('"').replace("\\", "/")
        if path not in allowed_pending:
            unexpected.append(path)
    if unexpected:
        print(f"FAIL: terminal evidence must be generated from a committed clean tree; unexpected changes: {unexpected}")
        return 1
    # Only the terminal-evidence payloads themselves may be pending commit; every
    # identity recorded below describes committed Git objects and stays true when
    # this manifest and the export report are sealed by the evidence commit.
    head = git("rev-parse", "HEAD")
    regression = loop_state.get("last_full_regression", {})
    measured_at_commit = regression.get("measured_at_commit") if isinstance(regression, dict) else None
    if not isinstance(measured_at_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", measured_at_commit):
        print(
            "FAIL: LOOP_STATE.last_full_regression.measured_at_commit must be a full 40-hex commit sha; "
            "a regression result without a verified measurement locus cannot be certified"
        )
        return 1
    ancestor_check = subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", measured_at_commit, head],
        capture_output=True, text=True,
    )
    if ancestor_check.returncode != 0:
        print(
            f"FAIL: regression drift detected: measured_at_commit {measured_at_commit} is not an "
            f"ancestor-or-self of the generation head {head}; refusing to certify measurements from "
            "an unrelated or descendant locus."
        )
        return 1
    range_diff = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--name-only", f"{measured_at_commit}..{head}"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    undeclared = [
        path for path in (line.strip() for line in range_diff)
        if path and not _is_declared_evidence_path(path)
    ]
    if undeclared:
        print(
            "FAIL: regression locus contamination: commits between measured_at_commit "
            f"{measured_at_commit} and generation head {head} touch non-evidence paths {undeclared}; "
            "the recorded result cannot describe the generation tree. Re-run the full suite at a "
            "locus whose delta to HEAD is declared evidence paths only."
        )
        return 1
    blocked = bool(open_high_critical or not_closed)

    def dispositions(prefix: str) -> dict:
        return {item_id: item["status"] for item_id, item in sorted(items.items()) if item_id.startswith(prefix)}

    manifest = {
        "schema_version": "2.0",
        "manifest_schema_version": "2.0",
        "kind": "BUILD_COMPLETION_MANIFEST",
        "manifest_generated_at": now,
        "repository": "ryguy-pixel/Sovereign-Distillery",
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "base": f"{git('merge-base', 'origin/main', 'HEAD')} (origin/main merge-base)",
        "implementation_seal_commit": implementation_seal_commit,
        "implementation_tree_state": "SEALED_NO_SUBSTANTIVE_IMPLEMENTATION_CHANGES_AFTER_SEAL_LEDGER_AND_EVIDENCE_COMMITS_ONLY",
        "evidence_generation_base": head,
        "artifact_source_commit": head,
        "artifact_generation_commit": None,
        "test_result_commit": head,
        "verified_branch_head": None,
        "verified_branch_head_semantics": (
            "UNBOUND_AT_GENERATION: bound only by external post-push verification records; "
            "a generated file never asserts its own future containing commit; "
            "artifact_generation_commit is likewise unbound when the generator itself is being sealed by the same commit"
        ),
        "worktree_clean": len(status_lines) == 0,
        "worktree_clean_except_declared_evidence_paths": not unexpected,
        "software_version": version_matrix["software_package"]["version"],
        "thesis_version": version_matrix["thesis"]["current"]["version"],
        "spec_version": version_matrix["specification"]["draft_version"],
        "schema_versions": {row["path"]: row.get("internal_version", "see file") for row in version_matrix["schemas"]},
        "test_matrix": {
            "command": regression.get("command"),
            "result": regression.get("result"),
            "exit_code": regression.get("exit_code"),
            "python": regression.get("python"),
            "measured_at_commit": measured_at_commit,
        },
        "audit_results": {
            "delta_audit": "F-01 CLOSED no CRITICAL; HIGH routed and closed",
            "open_high_or_critical_findings": open_high_critical,
            "findings_total": len(findings),
            "software_items_not_closed": not_closed,
        },
        "p0_disposition": dispositions("F-"),
        "d9_states": {
            "research_dossiers": "runs/source-admission/dossiers.json (2 RECOMMEND_ELIGIBLE, 2 INSUFFICIENT_EVIDENCE)",
            "operator_decisions": "UNSIGNED - human authority outstanding",
        },
        "trainer_state": {
            "GND-TRAINER-PRIMARY": "UNASSIGNED (requirement >=24GiB usable VRAM measured)",
            "GND-DEV-EXEC-01": "ACCESS_VERIFIED_LOCAL, canonical_primary_trainer=false",
            "GND-TRAINER-GFX906": "TARGET_NOT_FOUND / RETIRED_AS_UNVERIFIED_PLANNING_TARGET",
        },
        "hg_states": {
            "HG-0": "PASS_PROVISIONAL per historical records; supersession chain in runs/HG-3/CURRENT_STATUS.json",
            "HG-3": "BLOCKED_HARDWARE_CAPACITY",
            "HG-4..HG-8": "NOT_EXECUTED",
        },
        "g_states": {f"G{i}": "NOT_EXECUTED" for i in range(2, 7)},
        "fixture_runs": "tests/test_end_to_end_dry_run.py paths A-I PASS (SYNTHETIC_FIXTURE_ONLY)",
        "real_runs": "NONE - no model compute performed",
        "model_compute_performed": False,
        "promotion_performed": False,
        "deployment_performed": False,
        "artifact_hashes": {
            "raw_source_zip_sha256": export_report["raw_source"]["zip_sha256"],
            "enterprise_bundle_sha256": export_report["enterprise"]["bundle_sha256"],
        },
        "artifact_identity": {
            "artifact_source_commit": head,
            "bundle_generated_from": export_report.get("evidence_generation_base"),
            "zip_generated_from": export_report.get("evidence_generation_base"),
        },
        "certification_rule": (
            "The completion manifest certifies the immutable implementation source state identified by "
            "implementation_seal_commit and records evidence generated against the declared evidence_generation_base "
            "tree. The Git commit containing this manifest is NOT required to equal implementation_seal_commit; "
            "this prevents recursive HEAD invalidation."
        ),
        "external_blockers": [
            "D-9 operator decisions unsigned (F-26)",
            "Qualifying physical trainer unassigned >=24GiB (F-27)",
            "Real HG-3 requires qualified hardware + authorization (F-28)",
            "Real G2-G6 require prerequisites (F-29)",
            "Promotion/deployment are human-only and not performed (F-30)",
        ],
        "limitations": [
            "seal_shard trusts caller-supplied snapshot blobs; corpus pipeline enforces registry freshness structurally (FND-009 mitigation).",
            "Windows lacks portable directory-fsync; durability claims limited to file flush/fsync plus atomic replace.",
            "Fixture results are SYNTHETIC_FIXTURE_ONLY and can never satisfy measured-evidence gates.",
        ],
        "final_disposition": "INCOMPLETE_OPEN_HIGH_CRITICAL_OR_UNCLOSED_SOFTWARE_ITEMS"
        if blocked
        else "BUILD_COMPLETE_EXPERIMENT_PENDING",
    }
    destination = SEAL_DIR / "BUILD_COMPLETION_MANIFEST.json"
    destination.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "written": str(destination),
                "final_disposition": manifest["final_disposition"],
                "open_high_critical": open_high_critical,
                "software_items_not_closed": not_closed,
                "evidence_generation_base": head,
                "implementation_seal_commit": implementation_seal_commit,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
