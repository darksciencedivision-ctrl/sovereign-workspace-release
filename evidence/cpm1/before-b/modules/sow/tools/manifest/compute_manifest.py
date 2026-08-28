#!/usr/bin/env python3
"""Phase 0 freeze-manifest tool - Sovereign Orchestration Workspace.

Computes sha256 + size + encoding for every canonical document, frozen schema,
conductor file, and register; emits docs/PHASE0_FREEZE_MANIFEST.json with the
operator signature block (PENDING until the operator signs).

Deterministic: sorted paths, sorted keys, LF newline. Python 3.10+ stdlib only.
Usage: python tools/manifest/compute_manifest.py [--check]
  --check  verify the existing manifest instead of rewriting it (exit 1 on drift)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "PHASE0_FREEZE_MANIFEST.json"

# FROZEN sets: covered by freeze_integrity_sha256; the operator's signature binds these.
SETS = {
    "canonical_documents": ("docs/canonical", "*"),
    "schemas": ("schemas", "*.schema.json"),
    "conductor_files": ("conductor", "*.md"),
}
# AMENDMENT sets: schema files added AFTER the Phase-0 freeze under an explicit operator ruling.
# Recorded with the same hash discipline as the frozen set and drift-checked just as hard, but
# computed AFTER freeze_integrity_sha256 and stored OUTSIDE `contents`, so adding one cannot move
# that hash. That separation is the whole design: U222 requires the operator's signature to be
# preserved by hand rather than regenerated away, and folding an amendment into `contents` would
# change freeze_integrity_sha256 and reset the signature to PENDING - silently erasing a recorded
# operator act in order to record another one. The freeze covers what the operator signed; the
# amendment block covers what they authorized afterwards, and each is auditable on its own terms.
#   * node.schema@1.1.json - OP-12.1 (2026-08-01), the U227 resolution: the frozen node@1.0 file is
#     untouched and a successor sits beside it (AUTONOMOUS_BUILD_DIRECTIVE.md section 17.1).
# The glob deliberately does NOT match the frozen `*.schema.json` names, so no file is ever counted
# in both blocks; `test_node_schema_amendment.py` pins that disjointness.
AMENDMENT_SETS = {
    "schema_amendments": ("schemas", "*.schema@*.json"),
}
AMENDMENT_AUTHORIZATIONS = {
    "schemas/node.schema@1.1.json": "OP-12.1 (operator, 2026-08-01) - AUTONOMOUS_BUILD_DIRECTIVE.md section 17.1; U227 resolved by successor schema; node@1.0 never edited",
}
# Where a cited ruling has to actually EXIST. The 18D spec-auditor (M-3) found the attribution was
# asserted and never authenticated: the value above is free text, and nothing checked that the
# ruling it names is recorded anywhere. A future change could add a successor schema, invent
# an unrecorded ruling id here, add a NODE_SCHEMA_VERSIONS row, regenerate, and every automated
# check would stay
# green while the node vocabulary widened with no operator act behind it. Invariant 1 says the app
# never self-authorizes; an attribution nobody verifies is self-authorization with a citation.
# So the ruling id is parsed out of the front of the string and must appear in one of these files.
# It is a weak authentication - both are repo files - but it is the difference between "a name was
# typed" and "the name refers to something a reviewer can read", and it fails CLOSED.
RULING_SOURCES = ("AUTONOMOUS_BUILD_DIRECTIVE.md", "docs/registers/DECISION_REGISTER.md")
RULING_ID_RE = re.compile(r"^\s*(OP-\d+(?:\.\d+)?)\b")

# MUTABLE audit files: append-only by design, change at every gate (registers, evidence).
# Recorded for audit visibility but EXCLUDED from freeze integrity - a freeze that broke
# on every legitimate register append would make the signature meaningless (gate-validator
# finding F1, 2026-07-16).
MUTABLE_SETS = {
    "registers": ("docs/registers", "*.md"),
    "evidence_reports": ("docs/evidence", "*.md"),
}
# README.md carries current-phase status lines that change at every gate; it is
# navigational documentation, not frozen spec content (same reasoning as registers).
MUTABLE_EXTRA = ["README.md"]
EXTRA = [
    "CLAUDE.md",
    "docs/THREAT_MODEL.md",
    "docs/CONDUCTOR_FILES_WRITE_AUTHORITY.md",
    ".claude/settings.json",
    ".claude/hooks/guard.py",
    ".claude/agents/gate-validator.md",
    ".claude/agents/spec-auditor.md",
]

ROLES = {
    "Sovereign_Orchestration_Workspace_Architecture_Plan_v1.0.1_UTF8_20260716.md": "canonical-build-source",
    "Sovereign_Orchestration_Workspace_Architecture_Plan_v1.0_20260716.md": "provenance-only-do-not-build-from",
    "Sovereign_Orchestration_Workspace_Canonical_Handoff.md": "canonical-spec-v2.4",
    "Fable5_Directive_v2.4.md": "canonical-directive-extract",
    "Claude_Code_Buildout_Directive_20260716.md": "execution-authorization",
    "Sovereign_Orchestration_Canonical_Report_and_Analysis_20260716.md": "build-context-report",
    "SOVEREIGN_PROGRAM_Canonical_Analysis_and_Context_Handoff_20260716.md": "program-context-handoff",
    "Sovereign_Orchestration_Workspace_Canonical_Build_Handoff_v3.0_20260716.md": "cross-reference-chatgpt-lineage",
    "Fable5_Sovereign_Orchestration_Build_Directive_v3.0_20260716.md": "cross-reference-chatgpt-directive",
    "MANIFEST_v3.0_20260716.json": "cross-reference-chatgpt-manifest",
    "Sovereign_Orchestration_Workspace_Plan_UTF8_Repair_Report_20260716.md": "provenance-repair-report",
}


def sorted_files(directory: Path, pattern: str) -> list[Path]:
    """Every matching file, ordered by its POSIX repo-relative path as a plain STRING.

    Not `sorted(d.glob(...))`. Sorting `Path` objects is platform-dependent: `PurePath.__lt__`
    compares case-NORMALISED parts, so on Windows `SOVEREIGN_PROGRAM_...md` sorts after
    `Sovereign_Orchestration_...md` and on Linux it sorts before. Nothing about the files changes,
    but `contents.canonical_documents` is a LIST, so the order lands inside
    `freeze_integrity_sha256` - and this manifest was generated in the Linux sandbox while the
    operator's host is Windows. Regenerating here would have moved the freeze hash with no file
    edited anywhere, and the signature-preservation branch below keys on exactly that hash: the
    operator's recorded ruling would have been reset to PENDING by a platform difference. That is
    the U222 failure ("the operator signature must be preserved by hand, never regenerated away")
    arriving through the generator itself. Recorded as U293; found at the 18D amendment, which is
    the first change to touch this tool since the freeze.

    An explicit string key is deterministic on every platform and reproduces the recorded order."""
    return sorted((p for p in directory.glob(pattern) if p.is_file() and p.name != ".gitkeep"),
                  key=lambda p: p.relative_to(ROOT).as_posix())


def describe(path: Path) -> dict:
    data = path.read_bytes()
    try:
        data.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        encoding = "binary/unknown"
    rel = path.relative_to(ROOT).as_posix()
    entry = {
        "path": rel,
        "sha256": hashlib.sha256(data).hexdigest().upper(),
        "bytes": len(data),
        "encoding": encoding,
    }
    if path.name in ROLES:
        entry["role"] = ROLES[path.name]
    return entry


def attribution_for(rel_path: str) -> str:
    """The recorded authorization for an amendment file, or an `UNATTRIBUTED...` string saying why
    it does not count as one. Never raises: an unreadable ruling source narrows attribution rather
    than crashing the tool, which is the same fail-closed direction as everything else here."""
    cited = AMENDMENT_AUTHORIZATIONS.get(rel_path)
    if not cited:
        return "UNATTRIBUTED"
    match = RULING_ID_RE.match(cited)
    if not match:
        return f"UNATTRIBUTED (no operator ruling id at the front of: {cited[:60]!r})"
    ruling = match.group(1)
    for source in RULING_SOURCES:
        try:
            if ruling in (ROOT / source).read_text(encoding="utf-8", errors="replace"):
                return cited
        except OSError:
            continue
    return (f"UNATTRIBUTED (ruling {ruling} is recorded in none of "
            f"{', '.join(RULING_SOURCES)})")


def collect_amendments() -> dict:
    """Post-freeze, operator-authorized schema files. Same hash discipline as the frozen set; each
    entry carries the ruling that authorized it AND that ruling must be findable in the directive or
    the decision register (`attribution_for`), so the block cannot grow a file whose authorization
    is a sentence somebody typed."""
    out: dict = {}
    for key, (rel_dir, pattern) in AMENDMENT_SETS.items():
        d = ROOT / rel_dir
        files = sorted_files(d, pattern)
        entries = []
        for p in files:
            entry = describe(p)
            entry["authorized_by"] = attribution_for(entry["path"])
            try:
                entry["schema_id"] = json.loads(p.read_text(encoding="utf-8")).get("$id", "?")
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                entry["schema_id"] = f"UNPARSEABLE:{entry['path']}"
            entries.append(entry)
        out[key] = entries
    return out


def collect() -> dict:
    body: dict = {}
    for key, (rel_dir, pattern) in SETS.items():
        d = ROOT / rel_dir
        files = sorted_files(d, pattern)
        body[key] = [describe(p) for p in files]
    body["repo_governance_files"] = [describe(ROOT / rel) for rel in EXTRA if (ROOT / rel).is_file()]
    mutable = {}
    for key, (rel_dir, pattern) in MUTABLE_SETS.items():
        d = ROOT / rel_dir
        files = sorted_files(d, pattern)
        mutable[key] = [describe(p) for p in files]
    mutable["status_docs"] = [describe(ROOT / rel) for rel in MUTABLE_EXTRA if (ROOT / rel).is_file()]
    return body, mutable


def build_manifest() -> dict:
    body, mutable = collect()
    schema_ids = []
    for entry in body["schemas"]:
        try:
            content = json.loads((ROOT / entry["path"]).read_text(encoding="utf-8"))
            schema_ids.append(content.get("$id", "?"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # validator finding N-1: a corrupted schema must surface as readable drift
            # evidence, not a traceback; the hash comparison below still catches it.
            schema_ids.append(f"UNPARSEABLE:{entry['path']}")
    core = {
        "manifest": "PHASE0_FREEZE_MANIFEST",
        "manifest_version": "1.0",
        "project": "sovereign-orchestration-workspace",
        "directive_version": "v2.4",
        "build_source_plan_sha256": "8C9B7240AC7962948844EA7892BD63BDCCC061E3A1BA2F968F8ED935E3300022",
        "provenance_plan_sha256": "668089B57C3162DABDE62ED249778D26F554910666FF62A552FA968BE199E48F",
        "schema_versions_fixed_at": "@1.0",
        "schema_ids": sorted(schema_ids),
        "conductor_file_write_authority": "operator-only (docs/CONDUCTOR_FILES_WRITE_AUTHORITY.md)",
        "pending_operator_decisions": [
            "I-D1/I-D2 + D-COWORK-02 ratification (at this freeze)",
            "D-UI-01 (after Phase 1 spike)",
            "D-LANG-01 (provisional: Python 3.12)",
            "D-PERSIST-01 (provisional: SQLite WAL + CAS store)",
            "D-MCP-03 (at Phase 3A concurrent-writer test)",
            "D-IPC-01 (low stakes; may delegate)",
        ],
        "current_conductor": {
            "model": "fable-5",
            "reason": "operator_selected",
            "since": "2026-07-16",
            "note": "runtime selection under I-CN1; supersedes the plan's example value 'claude'",
        },
        "contents": body,
    }
    payload = json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    core["freeze_integrity_sha256"] = hashlib.sha256(payload).hexdigest().upper()
    # AFTER the freeze hash, on purpose (see AMENDMENT_SETS): an amendment must never be able to
    # move freeze_integrity_sha256, because that hash is what the operator's signature binds.
    amendments = collect_amendments()
    amendment_payload = json.dumps(amendments, sort_keys=True, separators=(",", ":")).encode("utf-8")
    core["schema_amendments"] = {
        "note": "Schema files added AFTER the Phase-0 freeze under an explicit operator ruling. NOT covered by freeze_integrity_sha256 (adding one must not invalidate the operator's signature - U222) and NOT part of the frozen @1.0 set, which is unchanged. Drift here is a HARD failure under --check, exactly as in the frozen set: NEW, CHANGED and REMOVED are all reported.",
        "amendment_integrity_sha256": hashlib.sha256(amendment_payload).hexdigest().upper(),
        **amendments,
    }
    core["mutable_audit_files"] = {
        "note": "Append-only audit surfaces (registers, evidence). Hashes recorded as of generation for visibility; NOT covered by freeze_integrity_sha256 and NOT checked for drift - they legitimately change at every gate. Canonical/schema/conductor/governance drift remains a hard failure.",
        **mutable,
    }
    core["operator_signature"] = {
        "status": "PENDING",
        "signed_by": None,
        "signed_ts": None,
        "instruction": "Operator: to sign, set status=SIGNED, signed_by, signed_ts (ISO-8601), and commit. The freeze_integrity_sha256 above covers every listed hash; any file change after signing invalidates it and requires a new manifest + register entry.",
    }
    return core


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    manifest = build_manifest()
    if args.check:
        if not OUT.exists():
            print("FAIL: manifest missing", file=sys.stderr)
            return 1
        existing = json.loads(OUT.read_text(encoding="utf-8"))
        drift = []
        info = []
        for section, entries in manifest.get("mutable_audit_files", {}).items():
            if section == "note":
                continue
            old = {e["path"]: e["sha256"] for e in existing.get("mutable_audit_files", {}).get(section, [])}
            for e in entries:
                if e["path"] not in old:
                    info.append(f"mutable new: {e['path']}")
                elif old[e["path"]] != e["sha256"]:
                    info.append(f"mutable changed (expected, append-only): {e['path']}")
        for section, entries in manifest["contents"].items():
            old = {e["path"]: e["sha256"] for e in existing.get("contents", {}).get(section, [])}
            for e in entries:
                if e["path"] not in old:
                    drift.append(f"NEW: {e['path']}")
                elif old[e["path"]] != e["sha256"]:
                    drift.append(f"CHANGED: {e['path']}")
            new_paths = {e["path"] for e in entries}
            drift += [f"REMOVED: {p}" for p in old if p not in new_paths]
        # Amendment files are drift-checked exactly as hard as frozen ones. An amendment is a
        # recorded operator act; an amendment file that changes after it was recorded is the same
        # class of event as a frozen file changing, and reads as `AMENDMENT ...` so the two are
        # never confused in the output. An UNATTRIBUTED entry is drift too: a schema successor that
        # names no authorizing ruling is exactly what this block exists to make impossible.
        for section, entries in manifest.get("schema_amendments", {}).items():
            if section in ("note", "amendment_integrity_sha256"):
                continue
            old = {e["path"]: e["sha256"]
                   for e in existing.get("schema_amendments", {}).get(section, [])}
            old_attr = {e["path"]: e.get("authorized_by", "UNATTRIBUTED")
                        for e in existing.get("schema_amendments", {}).get(section, [])}
            for e in entries:
                if e.get("authorized_by", "UNATTRIBUTED").startswith("UNATTRIBUTED"):
                    drift.append(f"AMENDMENT UNATTRIBUTED: {e['path']} - "
                                 f"{e.get('authorized_by', 'UNATTRIBUTED')}")
                if e["path"] not in old:
                    drift.append(f"AMENDMENT NEW: {e['path']}")
                elif old[e["path"]] != e["sha256"]:
                    drift.append(f"AMENDMENT CHANGED: {e['path']}")
                elif old_attr.get(e["path"]) != e.get("authorized_by"):
                    # The attribution is the operator act; the file hash is only the artifact.
                    # Re-labelling a recorded amendment under a different ruling changes no byte of
                    # the schema and was previously invisible here (spec-audit m-5).
                    drift.append(f"AMENDMENT ATTRIBUTION CHANGED: {e['path']} - recorded "
                                 f"{old_attr.get(e['path'])!r}, computed {e.get('authorized_by')!r}")
            new_paths = {e["path"] for e in entries}
            drift += [f"AMENDMENT REMOVED: {p}" for p in old if p not in new_paths]
        # The two integrity hashes the manifest publishes are now CHECKED, not merely printed.
        # Both were falsifiable in the recorded file with `--check` staying green (validator NIT-1 /
        # spec-audit m-4): the per-file comparisons above do the real work, so a tampered summary
        # hash changed nothing operationally - but a published hash nobody verifies teaches a reader
        # to trust a number that means nothing, and freeze_integrity_sha256 is the number the
        # operator's signature binds.
        if existing.get("freeze_integrity_sha256") != manifest["freeze_integrity_sha256"]:
            drift.append(f"FREEZE INTEGRITY HASH MISMATCH: recorded "
                         f"{existing.get('freeze_integrity_sha256')}, computed "
                         f"{manifest['freeze_integrity_sha256']}")
        recorded_amendment_hash = existing.get("schema_amendments", {}).get("amendment_integrity_sha256")
        computed_amendment_hash = manifest["schema_amendments"]["amendment_integrity_sha256"]
        if recorded_amendment_hash != computed_amendment_hash:
            drift.append(f"AMENDMENT INTEGRITY HASH MISMATCH: recorded {recorded_amendment_hash}, "
                         f"computed {computed_amendment_hash}")
        if drift:
            print("FREEZE DRIFT DETECTED:", file=sys.stderr)
            for d in drift:
                print(f"  {d}", file=sys.stderr)
            return 1
        for line in info:
            print(f"INFO: {line}")
        print("freeze check OK: no drift in FROZEN set against recorded manifest")
        return 0
    # Preserve a recorded (non-PENDING) signature across regenerations when the frozen
    # set is unchanged; any frozen-set change resets it to PENDING.
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            if (old.get("freeze_integrity_sha256") == manifest["freeze_integrity_sha256"]
                    and old.get("operator_signature", {}).get("status") not in (None, "PENDING")):
                manifest["operator_signature"] = old["operator_signature"]
        except (json.JSONDecodeError, OSError):
            pass
    manifest["generated_ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest["generator"] = "tools/manifest/compute_manifest.py"
    OUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"freeze_integrity_sha256 = {manifest['freeze_integrity_sha256']}")
    print(f"operator_signature.status = {manifest['operator_signature']['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
