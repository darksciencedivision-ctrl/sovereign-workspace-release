"""Concurrence loop support: unresolved-items ledger, deterministic claim map,
severity classification, patch-mode assembly, and exit evaluation.

Authority: PHASE2/concurrence/DESIGN.md v1.2 + VALIDATOR_GATE_DECISIONS_CP001_MAPPING
Decisions 1-3 + CLAUDE_CODE_DIRECTIVE_V5_0 standing approval 3. The controller in
cycle_runner_v3.py is the only caller. Everything here is deterministic: no model
calls, no embeddings — claim-map derivation, fingerprinting, severity, and patch
assembly are pure text/hash arithmetic over preserved artifacts, reproducible from
archives (mapping gate Decision 2).

Fail-closed rules (DESIGN S2): ambiguous load-bearing classification -> load_bearing
True; an objection that cannot be mapped to a claim -> CRITICAL; unmapped at
finalization -> CONCURRENCE_NOT_REACHED. A CRITICAL item never exits via IRREDUCIBLE.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

LEDGER_SCHEMA_VERSION = "concurrence_ledger_v1"
CLASSIFIER_RELATIVE_PATH = Path("library") / "config" / "concurrence_classifier.json"

SECTIONS = ("claim", "evidence", "counterarguments", "uncertainties", "final_synthesis")

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have if in into is it its of on or "
    "that the their this to was were will with not no can could should would may "
    "might must do does did done than then so such very more most other own same".split()
)


def normalize_claim_text(text: str) -> str:
    return " ".join(_WORD_RE.findall(str(text or "").lower()))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def claim_key(claim_text: str) -> str:
    return "clm_" + _sha(normalize_claim_text(claim_text))[:12]


def fingerprint(claim_id: str, issue_type: str, subject_text: str) -> str:
    return "fp_" + _sha(f"{claim_id}|{issue_type}|{normalize_claim_text(subject_text)}")[:16]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def ledger_hash(ledger: dict[str, Any]) -> str:
    return _sha(canonical_json(ledger))


def load_classifier(root: Path) -> dict[str, Any]:
    """Versioned classifier config (DESIGN S2: 'the classifier rule ships in config').
    Fail-closed: missing/invalid config raises."""
    path = Path(root) / CLASSIFIER_RELATIVE_PATH
    config = json.loads(path.read_text(encoding="utf-8"))
    if str(config.get("version", "")).strip() != "v1":
        raise ValueError(f"concurrence_classifier.json version must be v1: {path}")
    return config


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(str(text or "").lower()) if t not in _STOPWORDS and len(t) > 2}


# ---------------------------------------------------------------- claim map

def derive_claim_map(
    artifact: dict[str, Any],
    canonical_answer: dict[str, Any],
    classifier: dict[str, Any],
    *,
    round_number: int,
) -> dict[str, Any]:
    """Deterministic claim map (DESIGN S2, gate Decision 2). Built ONLY from the
    preserved arbitration artifact + the king's canonical answer; never model-emitted.
    claim_id is a hash of the normalized claim text, so identity is stable across
    rounds even though arbitration cluster_ids restart every round."""
    upper = float(classifier["load_bearing_overlap_upper"])
    lower = float(classifier["load_bearing_overlap_lower"])
    verdict_text = " ".join(
        [
            str(canonical_answer.get("claim", "")),
            str(canonical_answer.get("final_synthesis", "")),
        ]
    )
    verdict_tokens = _tokens(verdict_text)

    summaries: list[tuple[dict[str, Any], str]] = []
    summaries.extend((s, "agreed") for s in artifact.get("agreed_claims") or [])
    summaries.extend((s, "one_sided") for s in artifact.get("one_sided_claims") or [])
    summaries.extend((s, "contested") for s in artifact.get("contested_claims") or [])

    claims: list[dict[str, Any]] = []
    by_cluster: dict[str, str] = {}
    for summary, claim_type in summaries:
        claim_text = str(summary.get("claim", ""))
        cid = claim_key(claim_text)
        cluster_id = str(summary.get("cluster_id", ""))
        by_cluster[cluster_id] = cid
        ct = _tokens(claim_text)
        overlap = (len(ct & verdict_tokens) / len(ct)) if ct else 0.0
        if overlap >= upper:
            load_bearing, ambiguous = True, False
        elif overlap <= lower:
            load_bearing, ambiguous = False, False
        else:
            load_bearing, ambiguous = True, True  # fail-closed: ambiguous -> load-bearing
        claims.append(
            {
                "claim_id": cid,
                "cluster_id": cluster_id,
                "claim_text": claim_text,
                "claim_type": claim_type,
                "evidence_ids": ["ev_" + _sha(normalize_claim_text(e))[:12] for e in summary.get("evidence_items") or []],
                "supports_primary_verdict": load_bearing,
                "load_bearing": load_bearing,
                "ambiguous_fail_closed": ambiguous,
                "verdict_token_overlap": round(overlap, 4),
                "dependencies": [],
            }
        )
    for link in artifact.get("contested_links") or []:
        left = by_cluster.get(str(link.get("left_cluster_id", "")))
        right = by_cluster.get(str(link.get("right_cluster_id", "")))
        for claim in claims:
            if claim["claim_id"] == left and right and right not in claim["dependencies"]:
                claim["dependencies"].append(right)
            if claim["claim_id"] == right and left and left not in claim["dependencies"]:
                claim["dependencies"].append(left)
    return {
        "schema_version": "concurrence_claim_map_v1",
        "classifier_version": classifier["version"],
        "round_number": round_number,
        "source_artifact": str(artifact.get("artifact_path", "")),
        "claims": claims,
    }


def _map_lookup(claim_map: dict[str, Any], claim_id: str) -> dict[str, Any] | None:
    for claim in claim_map.get("claims") or []:
        if claim["claim_id"] == claim_id:
            return claim
    return None


# ---------------------------------------------------------------- severity

def classify_severity(item: dict[str, Any], claim_map: dict[str, Any]) -> tuple[str, str]:
    """DESIGN S2 deterministic rule: CRITICAL iff the item attacks (a) a load_bearing
    claim, (b) evidence required by such a claim, (c) a dependency supporting it, or
    (d) alleges an internal contradiction changing the primary verdict. Unmapped
    objection -> CRITICAL (fail-closed)."""
    entry = _map_lookup(claim_map, item.get("claim_id", ""))
    if entry is None:
        return "CRITICAL", "unmapped_objection_fail_closed"
    if entry["load_bearing"]:
        return "CRITICAL", "attacks_load_bearing_claim"
    if item.get("issue_type") == "contradiction":
        peer = _map_lookup(claim_map, str(item.get("peer_claim_id", "")))
        if peer is not None and peer["load_bearing"]:
            return "CRITICAL", "contradiction_with_load_bearing_claim"
        for dep_id in entry.get("dependencies") or []:
            dep = _map_lookup(claim_map, dep_id)
            if dep is not None and dep["load_bearing"]:
                return "CRITICAL", "contradiction_in_dependency_of_load_bearing_claim"
    return "NON_CRITICAL", "no_load_bearing_attack"


# ---------------------------------------------------------------- ledger build/refresh

def new_ledger(session_id: str, classifier: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "session_id": session_id,
        "claim_map_version": classifier["version"],
        "items": [],
        "rounds": [],
        "exit": None,
        "rounds_used": 0,
    }


def _issue_type_for_entry(entry: dict[str, Any], classifier: dict[str, Any]) -> tuple[str, str]:
    reason = str(entry.get("reason", ""))
    if str(entry.get("origin", "")) == "contested_link" or entry.get("peer_cluster_id"):
        return "contradiction", reason
    if "negation" in reason.lower():
        return "logic", reason
    return "evidence-insufficiency", reason


def items_from_artifact(
    artifact: dict[str, Any],
    claim_map: dict[str, Any],
    classifier: dict[str, Any],
    round_number: int,
) -> list[dict[str, Any]]:
    """Initial/refresh population from CP-001A/B-tagged unresolved entries (mapping S2)."""
    items: list[dict[str, Any]] = []
    for entry in artifact.get("unresolved_conflicts") or []:
        claim_text = str(entry.get("claim", ""))
        cid = claim_key(claim_text)
        issue_type, source = _issue_type_for_entry(entry, classifier)
        subject = str(entry.get("challenge") or entry.get("counter_claim") or "")
        fp = fingerprint(cid, issue_type, subject)
        item = {
            "issue_id": fp,
            "claim_id": cid,
            "claim_text": claim_text,
            "issue_type": issue_type,
            "issue_type_source": source,
            "disputed_evidence_ids": [
                "ev_" + _sha(normalize_claim_text(str(m.get("text", m))))[:12]
                for m in (entry.get("support_matches") or []) + (entry.get("uncertainty_matches") or [])
            ],
            "fingerprint": fp,
            "issue": subject,
            # arbitration entries do not record the raising turn; supporting_roles is the
            # disclosed-imprecise fallback (mapping S2 gap; raised_by_roles field NOT added
            # to claim_arbitrator in this change - not in the standing approvals).
            "raised_by": {"roles": list(entry.get("supporting_roles") or []), "precision": "cluster_supporting_roles_fallback"},
            "first_raised_round": round_number,
            "parent_issue": None,
            "severity": None,
            "severity_reason": None,
            "status": "OPEN",
            "evidence_needed": "an answer, qualification, or claim revision that the arbitration matcher accepts for this challenge"
            if issue_type != "contradiction"
            else "revision or qualification of one side of the contradictory claim pair",
            "resolution": None,
        }
        if entry.get("peer_cluster_id"):
            item["peer_claim_id"] = ""  # filled below if resolvable
        items.append(item)
    # resolve peer claim ids for contradictions via the artifact's own link table
    by_cluster: dict[str, str] = {}
    for group in ("agreed_claims", "one_sided_claims", "contested_claims"):
        for summary in artifact.get(group) or []:
            by_cluster[str(summary.get("cluster_id", ""))] = claim_key(str(summary.get("claim", "")))
    for entry, item in zip(list(artifact.get("unresolved_conflicts") or []), items):
        peer_cluster = str(entry.get("peer_cluster_id", ""))
        if peer_cluster:
            item["peer_claim_id"] = by_cluster.get(peer_cluster, "")
    for item in items:
        severity, reason = classify_severity(item, claim_map)
        item["severity"] = severity
        item["severity_reason"] = reason
    return items


def merge_new_items(ledger: dict[str, Any], candidates: list[dict[str, Any]]) -> list[str]:
    """Fingerprint-stable merge (DESIGN S2 identity rule): existing fingerprint keeps
    its issue_id/status/history; new fingerprints open new items."""
    known = {item["fingerprint"]: item for item in ledger["items"]}
    opened: list[str] = []
    for cand in candidates:
        existing = known.get(cand["fingerprint"])
        if existing is None:
            ledger["items"].append(cand)
            known[cand["fingerprint"]] = cand
            opened.append(cand["issue_id"])
        else:
            # identity survives paraphrase: refresh severity against the current map
            existing["severity"] = cand["severity"]
            existing["severity_reason"] = cand["severity_reason"]
    return opened


def refresh_statuses(
    ledger: dict[str, Any],
    artifact: dict[str, Any],
    claim_map: dict[str, Any],
    classifier: dict[str, Any],
    round_number: int,
) -> list[str]:
    """Disposition update after a re-round (mapping S2 round-2+ refresh):
    - fingerprint still among unresolved entries -> stays OPEN;
    - claim persists, challenge still raised somewhere but no longer unresolved ->
      RESOLVED (arbitration's own matcher accepted an answer);
    - claim persists, challenge no longer raised -> WITHDRAWN;
    - claim gone from the round's clusters -> RESOLVED (claim removed/qualified;
      the re-derived claim map + re-run classifier make declassification visible)."""
    current_fps: set[str] = set()
    for entry in artifact.get("unresolved_conflicts") or []:
        cid = claim_key(str(entry.get("claim", "")))
        issue_type, _ = _issue_type_for_entry(entry, classifier)
        subject = str(entry.get("challenge") or entry.get("counter_claim") or "")
        current_fps.add(fingerprint(cid, issue_type, subject))
    claims_present: set[str] = set()
    challenges_present: set[str] = set()
    for group in ("agreed_claims", "one_sided_claims", "contested_claims"):
        for summary in artifact.get(group) or []:
            claims_present.add(claim_key(str(summary.get("claim", ""))))
            for challenge in summary.get("challenge_items") or []:
                challenges_present.add(normalize_claim_text(str(challenge)))

    closed: list[str] = []
    for item in ledger["items"]:
        if item["status"] != "OPEN":
            continue
        if item["fingerprint"] in current_fps:
            continue  # still open this round
        if item["claim_id"] not in claims_present:
            item["status"] = "RESOLVED"
            item["resolution"] = f"claim removed or qualified in round {round_number} re-synthesis"
        elif item["issue_type"] != "contradiction" and normalize_claim_text(item["issue"]) in challenges_present:
            item["status"] = "RESOLVED"
            item["resolution"] = f"challenge answered in round {round_number} (arbitration matcher accepted an answer)"
        else:
            item["status"] = "WITHDRAWN"
            item["resolution"] = f"no longer raised in round {round_number} (recorded as withdrawn, not silently dropped)"
        closed.append(item["issue_id"])
    return closed


def open_critical_items(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    return [i for i in ledger["items"] if i["status"] == "OPEN" and i["severity"] == "CRITICAL"]


def open_items(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    return [i for i in ledger["items"] if i["status"] == "OPEN"]


# ---------------------------------------------------------------- exits

def evaluate_exit(ledger: dict[str, Any], *, gate_passed: bool, at_cap: bool) -> tuple[str | None, str]:
    """DESIGN S4 cap exits, evaluated in order. FINALIZE/FINALIZE_WITH_DISCLOSURE
    additionally require the accepting round's quality gate to have passed
    (DESIGN S3 condition 3). A CRITICAL item never exits via IRREDUCIBLE."""
    critical_open = open_critical_items(ledger)
    non_critical_open = [i for i in open_items(ledger) if i["severity"] != "CRITICAL"]
    if gate_passed and not critical_open:
        if not non_critical_open:
            return "FINALIZE", "all critical items resolved or withdrawn; validation passed"
        # remaining OPEN non-critical items exit as per-item IRREDUCIBLE with
        # individual justification (anti-gaming: each carries its own reason +
        # evidence_needed; disclosure is verbatim in the run record)
        for item in non_critical_open:
            item["status"] = "IRREDUCIBLE"
            item["resolution"] = (
                "unresolved within the global round budget; non-critical (severity_reason="
                f"{item['severity_reason']}); would be resolved by: {item['evidence_needed']}"
            )
        return "FINALIZE_WITH_DISCLOSURE", f"{len(non_critical_open)} non-critical item(s) disclosed as irreducible"
    if at_cap:
        if critical_open:
            return "CONCURRENCE_NOT_REACHED", f"{len(critical_open)} load-bearing critical dispute(s) remain at the cap"
        return "CONCURRENCE_NOT_REACHED", "validation did not pass at the cap"
    return None, "continue"


# ---------------------------------------------------------------- agenda

def agenda_payload(items: list[dict[str, Any]], round_number: int) -> dict[str, Any]:
    return {
        "schema_version": "concurrence_agenda_v1",
        "round_number": round_number,
        "issue_ids": [i["issue_id"] for i in items],
        "items": [
            {
                "issue_id": i["issue_id"],
                "claim_text": i["claim_text"],
                "issue_type": i["issue_type"],
                "issue": i["issue"],
                "severity": i["severity"],
                "evidence_needed": i["evidence_needed"],
            }
            for i in items
        ],
    }


def agenda_topic_block(topic: str, payload: dict[str, Any]) -> str:
    """Targeted-round task payload (DESIGN S4: feed the specific OPEN CRITICAL items
    back as the round's agenda). Rides in the topic payload; prompt templates are
    untouched (DESIGN S6)."""
    lines = [
        topic.strip(),
        "",
        "CONCURRENCE ROUND AGENDA - this round's ONLY task is to settle the specific",
        "open items below. Argue exactly these items; answer, qualify, or withdraw each",
        "disputed claim. Do not re-litigate settled points.",
    ]
    for index, item in enumerate(payload["items"], 1):
        lines.append(
            f"{index}. [{item['issue_type']}] Disputed claim: {item['claim_text']} | "
            f"Open objection: {item['issue']} | Resolution requires: {item['evidence_needed']}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------- patch assembly

def sections_of(answer: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim": str(answer.get("claim", "")).strip(),
        "evidence": [str(x).strip() for x in answer.get("evidence") or [] if str(x).strip()],
        "counterarguments": [str(x).strip() for x in answer.get("counterarguments") or [] if str(x).strip()],
        "uncertainties": [str(x).strip() for x in answer.get("uncertainties") or [] if str(x).strip()],
        "final_synthesis": str(answer.get("final_synthesis", "")).strip(),
    }


def section_hashes(sections: dict[str, Any]) -> dict[str, str]:
    return {name: _sha(canonical_json(sections[name])) for name in SECTIONS}


def permitted_sections(agenda_items: list[dict[str, Any]], classifier: dict[str, Any]) -> set[str]:
    """Gate Decision 3 dependency-aware patch scope, versioned in config."""
    permitted: set[str] = set()
    section_map = classifier["patch_sections_by_issue_type"]
    for item in agenda_items:
        permitted.update(section_map.get(item["issue_type"], list(SECTIONS)))
    return permitted


def assemble_patch(
    prior_sections: dict[str, Any],
    new_sections: dict[str, Any],
    permitted: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Patch-mode re-synthesis assembly (gate Decision 3 controls): pre-patch hashes,
    permitted-section list, post-patch hashes, changed-section list, unapproved
    changes REJECTED (prior content carried verbatim, event recorded). A missing or
    empty permitted section in the new output carries the prior content verbatim, so
    a format failure in round n destroys at most the round's delta (mapping S3.2)."""
    pre = section_hashes(prior_sections)
    assembled: dict[str, Any] = {}
    changed: list[str] = []
    rejected: list[str] = []
    carried_on_empty: list[str] = []
    for name in SECTIONS:
        prior_value = prior_sections[name]
        new_value = new_sections[name]
        new_empty = (not new_value) if isinstance(new_value, str) else (len(new_value) == 0)
        differs = canonical_json(new_value) != canonical_json(prior_value)
        if name in permitted:
            if new_empty:
                assembled[name] = prior_value
                if differs:
                    carried_on_empty.append(name)
            else:
                assembled[name] = new_value
                if differs:
                    changed.append(name)
        else:
            assembled[name] = prior_value
            if differs:
                rejected.append(name)
    post = section_hashes(assembled)
    report = {
        "pre_patch_hashes": pre,
        "post_patch_hashes": post,
        "permitted_sections": sorted(permitted),
        "changed_sections": changed,
        "unapproved_changes_rejected": rejected,
        "carried_forward_on_empty": carried_on_empty,
        "non_permitted_preserved": all(pre[n] == post[n] for n in SECTIONS if n not in permitted),
    }
    return assembled, report


def render_synthesis_text(sections: dict[str, Any], session_id: str) -> str:
    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "- none stated"

    return (
        f"[SYNTH session_id={session_id}]\n"
        f"CLAIM:\n{sections['claim']}\n\n"
        f"EVIDENCE:\n{bullets(sections['evidence'])}\n\n"
        f"COUNTERARGUMENTS:\n{bullets(sections['counterarguments'])}\n\n"
        f"UNCERTAINTIES:\n{bullets(sections['uncertainties'])}\n\n"
        f"FINAL_SYNTHESIS:\n{sections['final_synthesis']}\n"
        f"[/SYNTH]\n"
    )
