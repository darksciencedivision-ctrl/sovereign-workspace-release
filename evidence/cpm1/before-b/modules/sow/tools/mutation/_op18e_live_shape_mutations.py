"""Mutation runner for Phase 18E `.live.shape` — the document-shape instrument (U305) and the two
places it is wired into the probe verdict.

Same contract as its siblings: apply one mutation, run one selector, record RED (a test caught it)
or GREEN (nothing did), restore the original bytes, verify the restore is BYTE-IDENTICAL by sha256.
Exit 1 if anything is GREEN or a restore diverges.

What this harness is guarding, and why each row is worth a mutation:

`describe_provider_document` is an INSTRUMENT — nothing refuses because of it, so nothing breaks
loudly if it lies. It exists so that `accepted:false, token_seen:false` can be told apart from
"the reader could not see the answer", and a live acceptance leg is about to make provider-level
decisions on exactly that distinction. An instrument with no guard is a comment.

  * S1  the skeleton stops preserving blank strings — this is the defect this unit CAUSED and
        caught while building it: `""` became `<str:0>`, a non-empty string, so the real Grok
        document (`"text": ""`, `stopReason: cancelled` — the CLI said nothing) produced a skeleton
        whose `text` field READ AS AN ANSWER. The skeleton's whole claim is that the reader gives
        the same answer for it as for the original, and this inverts it;
  * S2  the skeleton keeps string VALUES instead of length placeholders. Nothing fails; the shape
        is published to `docs/evidence/live/`, so this is a disclosure defect, and disclosure
        defects are silent by nature (§2.2/§13);
  * S3  the token search reports a path for a value that merely resembles the token, by matching
        case-insensitively. `token_paths` is read as "where the model put the token" and would
        start including places it did not;
  * S4  `token_visible_to_strict_reader` is computed from the best-effort reader instead of the
        strict one — U238 hole 2 re-entering through the instrument that was built to expose it.
        Every real document would report the token as visible, including the Grok one where the
        CLI said nothing;
  * S5  the describer's own precedence for `response_key_matched` diverges from the reader's, so
        the shape names a field the reader did not use;
  * S6  the depth bound stops setting `truncated`, so a partial description is published as
        a whole one — untrusted input (T2) described as if it had been fully read;
  * S7  the probe verdict stops carrying `document_shape` at all. The suite is otherwise entirely
        green: this is the row that catches the instrument being built and never wired in;
  * S8  an empty recognised field counts as a match, so `{"text": ""}` — the exact shape the live
        Grok run produced — reports a response the CLI never gave.

Rows added at the ROUND-1 REVIEW, each pinning a remediation the reviewers' findings forced. They
are listed apart because none of them guards the original design — each guards a fix:

  * S10 the key inventory escapes the walk's budget again. `top_level_keys`/`key_types` were built
        outside it, so a 50,000-key document enumerated every provider-chosen key beside
        `truncated: true` and wrote a multi-megabyte record into docs/evidence/live/ (validator
        MEDIUM-4);
  * S11 provider-controlled KEY NAMES stop being secret-scrubbed and length-bounded. Key names are
        DATA, not schema — the unit's own evidence has a model identifier in a key position — and
        they reach four published fields plus the skeleton (validator MEDIUM-5, auditor MEDIUM-1);
  * S12 the dict walk stops honouring the budget mid-map, which is S10's other half: the key
        INVENTORY being bounded while the SKELETON is not is the same defect twice.

One row was WRITTEN AND REMOVED rather than kept green, and the reason is worth more than the row:
a mutation restoring the old `"<truncated>"` marker (a non-empty string, which under a recognised
key reads as a response the CLI never gave) does not change any outcome, because S12's dict-branch
break drops the key entirely before the marker can be produced. The `return None` is a backstop
behind that break, not the primary guard, and a GREEN row asserting otherwise would have overstated
which line is doing the work.

Run from the repo root:  py -3.12 tools/mutation/_op18e_live_shape_mutations.py
"""
from __future__ import annotations

import hashlib
import pathlib
import signal
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PY = [sys.executable, "-m", "pytest", "-q", "-x"]

COMMON = "adapters/frontier/provider_cli_common.py"
RECON = "tools/providers/frontier_provider_recon.py"

SHAPE = "tests/unit/test_provider_document_shape.py"
PROBE = "tests/unit/test_frontier_provider_recon.py::TestTheProbeRecordsTheDocumentItJudged"

MUTATIONS = [
    ("S1  the skeleton stops preserving blank strings (the defect this unit caused)",
     COMMON,
     "            if not value.strip():",
     "            if False:",
     SHAPE + "::TestItReportsStructureAndNeverValues::test_the_skeleton_replays_the_strict_reader_faithfully"),
    ("S2  the skeleton keeps string VALUES instead of length placeholders (disclosure)",
     COMMON,
     '            return f"<str:{len(value)}>"',
     "            return value",
     SHAPE + "::TestItReportsStructureAndNeverValues::test_no_string_value_survives_into_the_shape"),
    ("S3  the token search matches case-insensitively, so lookalikes get paths",
     COMMON,
     "            if token and token in value:",
     "            if token and token.casefold() in value.casefold():",
     SHAPE + "::TestTheShapesU305WasOpenedFor::test_token_paths_means_the_EXACT_token_not_a_lookalike"),
    ("S4  visibility is computed from the BEST-EFFORT reader (U238 hole 2, via the instrument)",
     COMMON,
     "    response = extract_provider_response_field(s)\n    # The key inventory",
     "    response = extract_provider_text(s)\n    # The key inventory",
     SHAPE + "::TestU305AnsweredByMeasurement"),
    ("S5  the describer invents its own response-key precedence",
     COMMON,
     "        for key in PROVIDER_RESPONSE_KEYS:\n"
     "            val = doc.get(key)\n"
     "            if isinstance(val, str) and val.strip():\n"
     "                matched = key\n"
     "                break",
     "        for key in reversed(PROVIDER_RESPONSE_KEYS):\n"
     "            val = doc.get(key)\n"
     "            if isinstance(val, str) and val.strip():\n"
     "                matched = key\n"
     "                break",
     SHAPE + "::TestTheDescriberAgreesWithTheReaderItDescribes::test_the_match_follows_the_readers_own_precedence"),
    ("S6  the bound stops flagging `truncated` (a partial description published as whole)",
     COMMON,
     "        if budget[\"nodes\"] > max_nodes or depth > max_depth:\n"
     "            budget[\"truncated\"] = True",
     "        if budget[\"nodes\"] > max_nodes or depth > max_depth:\n"
     "            budget[\"truncated\"] = False",
     SHAPE + "::TestItFailsClosedOnDocumentsItCannotRead::test_depth_is_bounded"),
    ("S12 the dict walk stops honouring the budget, so a truncated map is described in full",
     COMMON,
     "                if budget[\"nodes\"] > max_nodes:\n"
     "                    budget[\"truncated\"] = True\n"
     "                    break\n",
     "",
     SHAPE + "::TestItFailsClosedOnDocumentsItCannotRead::test_the_KEY_INVENTORY_is_bounded_by_the_same_budget_as_the_walk"),
    ("S7  the probe verdict stops carrying the shape (the instrument never wired in)",
     RECON,
     '            "document_shape": describe_probe_document(out, token=spec.probe_token).as_dict(),\n',
     "",
     PROBE + "::test_an_accepted_probe_records_the_flat_shape_that_earned_it"),
    ("S10 the key inventory escapes the budget again (50,000 provider keys beside truncated:true)",
     COMMON,
     "    keys = [key_name(k) for k in doc][:max_nodes] if isinstance(doc, dict) else []",
     "    keys = [key_name(k) for k in doc] if isinstance(doc, dict) else []",
     SHAPE + "::TestItFailsClosedOnDocumentsItCannotRead::test_the_KEY_INVENTORY_is_bounded_by_the_same_budget_as_the_walk"),
    ("S11 provider-controlled KEY NAMES stop being secret-scrubbed and bounded",
     COMMON,
     "        return redact_diagnostics(str(key), limit=_SHAPE_MAX_KEY_CHARS)",
     "        return str(key)",
     SHAPE + "::TestItReportsStructureAndNeverValues::test_a_secret_shaped_KEY_is_scrubbed_and_a_long_one_is_bounded"),
    ("S8  an empty recognised field counts as a match (the live Grok `\"text\": \"\"` shape)",
     COMMON,
     "            if isinstance(val, str) and val.strip():\n"
     "                matched = key",
     "            if isinstance(val, str):\n"
     "                matched = key",
     SHAPE + "::TestTheDescriberAgreesWithTheReaderItDescribes::test_an_empty_recognised_field_is_not_a_match"),
]

#: Files this run may have mutated, pinned at import so the signal handler can restore ALL of them
#: even if it fires between the write and the restore (the contract U292(b) named).
_PINNED: dict[pathlib.Path, bytes] = {}
_LOCK = ROOT / ".mutation-lock"


def digest(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _restore_all(*_a: object) -> None:
    for path, original in _PINNED.items():
        try:
            path.write_bytes(original)
        except OSError:                                  # pragma: no cover - best effort teardown
            pass
    _LOCK.unlink(missing_ok=True)


def run_one(rel: str, old: str, new: str, target: str) -> tuple[str, str]:
    path = ROOT / rel
    before = _PINNED[path]
    before_hash = digest(path)
    text = before.decode("utf-8")
    if old not in text:
        return "SKIPPED-ANCHOR-MISSING", "unchanged"
    mutated = text.replace(old, new, 1)
    if mutated == text:
        return "SKIPPED-ANCHOR-MISSING", "unchanged"
    path.write_bytes(mutated.encode("utf-8"))
    try:
        proc = subprocess.run(PY + [target], cwd=ROOT, capture_output=True, text=True)
        verdict = "RED" if proc.returncode != 0 else "GREEN (guard does not hold)"
    finally:
        path.write_bytes(before)
    return verdict, ("restored" if digest(path) == before_hash else "RESTORE FAILED")


def main() -> int:
    if _LOCK.exists():
        print(f"another mutation run holds {_LOCK} - refusing to mutate product files concurrently")
        return 1
    _LOCK.write_text(str(__file__), encoding="utf-8")
    for _, rel, _o, _n, _t in MUTATIONS:
        _PINNED.setdefault(ROOT / rel, (ROOT / rel).read_bytes())
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_a: (_restore_all(), sys.exit(130)))

    rows = []
    try:
        for label, rel, old, new, target in MUTATIONS:
            verdict, restore = run_one(rel, old, new, target)
            rows.append((label, verdict, restore))
    finally:
        _restore_all()

    width = max(len(r[0]) for r in rows)
    for label, verdict, restore in rows:
        print(f"{label.ljust(width)}  {verdict:<26} {restore}")
    ok = all(r[1] == "RED" and r[2] == "restored" for r in rows)
    failed = [r[0] for r in rows if r[2] == "RESTORE FAILED"]
    print(f"\n{sum(1 for r in rows if r[1] == 'RED')}/{len(rows)} RED, "
          + ("all restores byte-identical" if not failed
             else "RESTORE FAILED: " + "; ".join(failed)))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
