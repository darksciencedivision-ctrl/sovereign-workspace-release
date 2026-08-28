"""Mutation runner for Phase 18E `.live.electron` — the LIVE OP-12 acceptance leg.

Same contract as its siblings: apply one mutation, run one selector, record RED (a test caught it)
or GREEN (nothing did), restore the original bytes, verify the restore is BYTE-IDENTICAL by sha256.
Exit 1 if anything is GREEN or a restore diverges.

EVERY row here mutates JAVASCRIPT and runs `node --test`, which is unusual for this family and is
the point: the rules that decide whether a LIVE receipt may be written live in the shell's verdict
module, and the 18D gate found that rules running only at in-Electron emit time cannot be falsified
by any suite at all (U296). A verdict module whose weakening leaves every test green is a verdict
module that is not deciding anything.

The receipt these rules govern is the one most likely to be read as "both providers work". The
distance between that reading and "a terminal echoed" is entirely in the rows below.

  * M1  `worldIsLiveOpen` stops reading the switch's own `authorized` flag, so a DENIED world whose
        provider list is populated by the code-pinned scope reads as live;
  * M2  …and stops requiring BOTH providers, so a partial world is reported as full acceptance;
  * M3  an unreadable authorization defaults to live instead of failing closed;
  * M4  the model check compares nothing — a pane running a different model than the operator
        selected passes as "exact provider+model verified" (§17);
  * M5  a missing model id is accepted, so an UNPINNED live call certifies a model;
  * M6  the binary that was actually spawned is no longer compared to the adapter's allowlist, so
        one provider's pane can be verified as the other's;
  * M7  the observed node-pty spawn is no longer matched to THIS pane, so the cwd/env evidence can
        be about a different session;
  * M8  the child-environment scrub check accepts a surviving credential NAME (§2.2);
  * M9  …and an EMPTY scrub list, so "the name is absent" stops measuring a removal;
  * M10 `liveAnswerIsHonest` accepts a run where nothing ever answered — the U310 shape, in which a
        CLI exits zero having said nothing and the receipt calls it a live response;
  * M11 …and one where the answer token was already on screen before the prompt was sent;
  * M12 …and one where the keystrokes never arrived, collapsing two independent failures into one;
  * M13 the node lifecycle stops requiring the spawn row to belong to THIS session (U315's binding);
  * M14 …stops checking the READY transition carries the supervised pid;
  * M15 …stops requiring the record to be CLOSED, so a live receipt can be written over a record
        that still reads open on an append-only log (D-LOOP-1);
  * M16 the append-only chain check stops linking rows, so an EDITED history passes as appended-to;
  * M17 the shell drops the ticket's `node_registration`, so nothing can bind the pane to a row on
        the operator's durable node log;
  * M18 the release drops the node-record outcome, so nothing can say whether the record was closed;
  * M19 a provider's directory-trust modal reads as an ordinary pane, so the receipt goes back to
        reporting a session that is alive and waiting for a human as a dead terminal;
  * M20 …and the opposite error: one phrase is enough, so a model that merely SAID "yes, proceed"
        is reported as a modal and a real live answer is thrown away as a gate;
  * M21 the `none` guard is dropped, so a CLI that is signing ITSELF in is reported as waiting on
        the operator — an owed step that is not owed;
  * M22 a consent-gated leg may be reported as PASSED, i.e. a gate counts as an answer;
  * M23 …may be typed into after the gate was already seen, spending live budget on a prompt that
        reaches no model;
  * M24 …need not name the one-time operator step, so an owed leg reads as a product failure;
  * M25 …may report an ANSWER, which a modal waiting on the operator did not produce;
  * M26 …may be blamed for a leg whose prompt ECHOED, which is how a session that took the
        keystrokes and said nothing (U310) gets re-labelled a consent skip and disappears;
  * M27 `worldIsLiveOpen` reads a MISSING `authorized` key as consent, i.e. fails open on the one
        gate that decides whether paid live sessions may start;
  * M28 the node lifecycle stops requiring READY to come FROM SPAWNING, so half the life the
        receipt describes goes unverified.

Added at `.close`, from the two mandatory reviewers' findings on the gate composition:

  * M29 a late gate may explain a leg that TYPED into the pane — the other half of M26. Round 2
        keyed this on SUBMISSION, and the spec-auditor showed submission cannot happen without an
        echo in this check, so the residual route stayed open AND was pinned green by a test; TYPING
        is the act that creates the ambiguity (gate-validator MEDIUM-2, spec-audit round-2 MEDIUM-1);
  * M30 a skip may cite a gate id no provider signature can produce (MINOR-2);
  * M31 `repoUnchangedByTheRun` goes back to comparing the two readings, so two DIRTY measurements
        agree with each other and the field calls itself unchanged (MEDIUM-4);
  * M32 the credential scan drops the operator's durable NODE LOG — one of the two stores this run
        writes into through children that inherit its environment (spec-audit M-2);
  * M33 the OWED citation rule stops being word-anchored, so "MENU42" cites something (MINOR-3);
  * M34 a credential name the HOST already sets is captured and overwritten again - §2.2 and
        OP-12 §13 forbid READING one, not only storing it (spec-audit round-2 MEDIUM-5).

Run from the repo root:  py -3.12 tools/mutation/_op18e_live_acceptance_mutations.py
"""
from __future__ import annotations

import hashlib
import pathlib
import signal
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
NODE = ["node", "--test"]

VERDICT = "apps/desktop/selfcheck/op12-live-acceptance-verdict.js"
SPAWN_JS = "apps/desktop/picker/worker-spawn.js"
SOURCE_JS = "apps/desktop/picker/launch-source.js"

T = "apps/desktop/test/op12-live-acceptance-verdict.test.js"
SPAWN_T = "apps/desktop/test/worker-spawn.test.js"
SOURCE_T = "apps/desktop/test/worker-launch-source.test.js"

MUTATIONS = [
    ("M1  `worldIsLiveOpen` ignores the switch's own authorized flag",
     VERDICT,
     "  const switched = auth.authorized === true;",
     "  const switched = true;",
     T),
    ("M2  a PARTIAL world is reported as live",
     VERDICT,
     "    live: no.length === 0, op12_authorized: yes, op12_denied: no,",
     "    live: true, op12_authorized: yes, op12_denied: no,",
     T),
    ("M3  an unreadable authorization defaults to live",
     VERDICT,
     "      live: false, op12_authorized: [], op12_denied: OP12_PROVIDERS.slice(),",
     "      live: true, op12_authorized: OP12_PROVIDERS.slice(), op12_denied: [],",
     T),
    ("M4  the launched model is no longer compared to the operator's selection",
     VERDICT,
     "  } else if (slug !== option.model_slug) {",
     "  } else if (false) {",
     T),
    ("M5  a missing model id is accepted (an unpinned live call certifies a model)",
     VERDICT,
     "  if (!nonEmpty(slug)) {",
     "  if (false) {",
     T),
    ("M6  the spawned binary is no longer checked against the adapter's allowlist",
     VERDICT,
     "  if (executableBasename(record.executable) !== expectedBinary) {",
     "  if (false) {",
     T),
    ("M7  the observed node-pty spawn is no longer matched to THIS pane",
     VERDICT,
     "  if (!samePath(spawned.file, record.executable)) {",
     "  if (false) {",
     T),
    ("M8  a surviving credential NAME in the child environment is accepted (§2.2)",
     VERDICT,
     "  for (const name of credentialNames) {\n    if (lower.has(String(name).toLowerCase())) {",
     "  for (const name of []) {\n    if (lower.has(String(name).toLowerCase())) {",
     T),
    ("M9  an EMPTY scrub list is accepted, so absence stops measuring a removal",
     VERDICT,
     "  if (!scrubNames.length) {",
     "  if (false) {",
     T),
    ("M10 a run where nothing ever answered is accepted as a live response (U310)",
     VERDICT,
     "  if (answer.seen !== true) {",
     "  if (false) {",
     T),
    ("M11 an answer token already on screen before submission is accepted",
     VERDICT,
     "  if (o.absentBefore !== true) {",
     "  if (false) {",
     T),
    ("M12 keystrokes that never arrived stop failing on their own",
     VERDICT,
     "  if (o.echoed !== true) {",
     "  if (false) {",
     T),
    ("M13 the spawn row is no longer bound to THIS session (U315)",
     VERDICT,
     '  const spawns = mine.filter((r) => r.kind === "spawn"\n'
     "    && r.data && r.data.session_id === sessionId);",
     '  const spawns = mine.filter((r) => r.kind === "spawn");',
     T),
    ("M14 the READY transition's pid is no longer checked",
     VERDICT,
     "    if (Number.isInteger(pid) && ready.data.pid !== pid) {",
     "    if (false) {",
     T),
    ("M15 a record left OPEN passes the lifecycle (D-LOOP-1)",
     VERDICT,
     "  if (!terminated) {",
     "  if (false) {",
     T),
    ("M16 the append-only chain stops linking rows, so an edited history passes",
     VERDICT,
     "    if (row.prev_hash !== expectedPrev) {",
     "    if (false) {",
     T),
    ("M17 [shell] the ticket's node registration is dropped instead of kept",
     SPAWN_JS,
     "      nodeRegistration: (ticket.node_registration && typeof ticket.node_registration === \"object\")\n"
     "        ? ticket.node_registration : null,",
     "      nodeRegistration: null,",
     SPAWN_T),
    ("M18 [shell] the release drops the node-record outcome it was handed",
     SOURCE_JS,
     "      nodeRecord: (r.node_record && typeof r.node_record === \"object\") ? r.node_record : null,",
     "      nodeRecord: null,",
     SOURCE_T),
    ("M19 a provider consent modal reads as an ordinary pane",
     VERDICT,
     "    if (!sig.all.every((re) => re.test(flat))) continue;",
     "    continue;",
     T),
    ("M20 ONE phrase is enough, so a model that SAID 'yes, proceed' reads as a modal",
     VERDICT,
     "    if (!sig.all.every((re) => re.test(flat))) continue;",
     "    if (!sig.all.some((re) => re.test(flat))) continue;",
     T),
    ("M21 the `none` guard is dropped, so a CLI signing itself in reads as awaiting the operator",
     VERDICT,
     "    if ((sig.none || []).some((re) => re.test(flat))) continue;",
     "    if (false) continue;",
     T),
    ("M22 a consent-GATED leg is allowed to be reported as PASSED",
     VERDICT,
     "  if (o.ok === true) {\n    reasons.push(\"a leg blocked on a provider consent gate is reported as PASSED",
     "  if (false) {\n    reasons.push(\"a leg blocked on a provider consent gate is reported as PASSED",
     T),
    ("M23 a gated leg may be typed into after the gate was ALREADY seen (live budget for nothing)",
     VERDICT,
     "  if (o.detected_before_typing === true && (o.typed === true || o.submitted === true)) {",
     "  if (false) {",
     T),
    ("M24 a gated leg need not name the one-time operator step",
     VERDICT,
     "  if (!nonEmpty(o.operator_step)) {\n    reasons.push(\"the gated leg names no operator step",
     "  if (false) {\n    reasons.push(\"the gated leg names no operator step",
     T),
    ("M25 a gated leg may report an ANSWER — a modal that produced one",
     VERDICT,
     "  if (o.answer_seen === true) {\n    reasons.push(\"a gated leg reports an answer",
     "  if (false) {\n    reasons.push(\"a gated leg reports an answer",
     T),
    ("M26 a gate found after an ECHOED prompt may stand, burying a U310 as a consent skip",
     VERDICT,
     "  if (o.detected_before_typing !== true && o.echoed === true) {",
     "  if (false) {",
     T),
    ("M27 a switch with no `authorized` key reads as consent (fail-open on an unreadable world)",
     VERDICT,
     "  const switched = auth.authorized === true;",
     "  const switched = auth.authorized !== false;",
     T),
    ("M28 the READY transition need not come FROM SPAWNING",
     VERDICT,
     "    if (ready.data.frm !== \"SPAWNING\") {",
     "    if (false) {",
     T),
    ("M29 a late gate may explain a leg that TYPED into the pane, which is how a U310 hides where "
     "the prompt never echoed",
     VERDICT,
     "  if (o.detected_before_typing !== true && (o.typed || o.submitted)) {",
     "  if (false) {",
     T),
    ("M30 a skip may be explained by a gate id no provider signature can produce",
     VERDICT,
     "  if (!KNOWN_CONSENT_GATE_IDS.has(o.gate)) {",
     "  if (false) {",
     T),
    ("M31 `repo unchanged by the run` goes back to comparing two readings, so two DIRTY ones agree",
     VERDICT,
     "    ok: b.tracked_product_tree_clean === true && a.tracked_product_tree_clean === true",
     "    ok: b.tracked_product_tree_clean === a.tracked_product_tree_clean",
     T),
    ("M32 the credential scan drops the operator's durable NODE LOG, one of the two stores this "
     "run writes into",
     VERDICT,
     "  sinks[`${nonEmpty(p.nodeLogPath) ? p.nodeLogPath : \"the node log (path unknown)\"} `\n"
     "    + \"(the operator's durable node log)\"] = p.nodeLogText ?? null;",
     "  // the operator's durable node log is no longer a sink",
     T),
    ("M33 an OWED marker's citation rule stops being word-anchored, so `MENU42` cites something",
     VERDICT,
     "const OWED_REFERENCE = /(\\bU\\d{1,3}\\b|",
     "const OWED_REFERENCE = /(U\\d{1,3}|",
     T),
    ("M34 a credential name the HOST already sets is captured and overwritten again (§2.2 forbids "
     "READING one, not only storing it)",
     VERDICT,
     "    if (Object.prototype.hasOwnProperty.call(source, name)) { skipped.push(name); continue; }",
     "    if (false) { skipped.push(name); continue; }",
     T),
]

#: Files this run may have mutated, pinned at import so the signal handler can restore ALL of them
#: even if it fires between the write and the restore.
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
        cmd = [*NODE, pathlib.Path(target).name]
        proc = subprocess.run(cmd, cwd=ROOT / "apps" / "desktop" / "test",
                              capture_output=True, text=True)
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
        try:
            signal.signal(sig, lambda *_a: (_restore_all(), sys.exit(130)))
        except (ValueError, OSError):                    # pragma: no cover - non-main thread
            pass
    failures = 0
    try:
        for label, rel, old, new, target in MUTATIONS:
            verdict, restore = run_one(rel, old, new, target)
            print(f"{verdict:32} {restore:16} {label}")
            if verdict != "RED" or restore != "restored":
                failures += 1
    finally:
        _restore_all()
    print(f"\n{len(MUTATIONS) - failures}/{len(MUTATIONS)} RED with byte-identical restores")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
