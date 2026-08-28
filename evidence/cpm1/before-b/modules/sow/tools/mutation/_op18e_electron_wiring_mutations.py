"""Mutation runner for Phase 18E `.live.electron.wiring` — the supervised worker PANE as a
registered Sovereign node.

Same contract as its siblings: apply one mutation, run one selector, record RED (a test caught it)
or GREEN (nothing did), restore the original bytes, verify the restore is BYTE-IDENTICAL by sha256.
Exit 1 if anything is GREEN or a restore diverges.

Unlike `_op18e_hardening_mutations.py`, almost nothing here RESTORES a shipped behaviour — this
sub-step added the wiring, so most rows delete or weaken something that did not exist before. That
makes the harness more important, not less: a guard added in the same commit as the code it guards
is exactly the guard nobody has watched fail.

Rows M11, M12 and M22 mutate JAVASCRIPT and run `node --test`, because the shell is where three of
the rules live and a Python-only harness would have left them unmeasured (the mistake the `main.js`
rules of 17B were found by, spec-audit MAJOR-2).

M13–M22 are the REMEDIATION rows: one per finding the gate-validator and the spec-auditor returned
on the first cut of this sub-step. They matter more than M1–M12, because a guard written in
response to a review is a guard whose only evidence of working is the review that asked for it.

  * M1  `registrar` becomes a defaulted keyword again — whether a governed session becomes a
        Sovereign node answered by this module for every caller (U283/U292(a)'s shape, third time);
  * M2  `ProviderNodeRegistrationRefused` leaves the governance-refusal tuple, so a registrar
        refusal escapes as a traceback instead of refusing the SESSION — and the durable terminal
        acquired moments earlier is never handed back (18D `.close`'s rule, inverted);
  * M3  the ticket stops closing the registrar, so the node log's cross-process lock survives the
        emitter and the shell's own next call (the attestation) is refused `node_log_locked`;
  * M4  `adopt_from_log` reads the row ROOT instead of `data` — always None, which reads as "no
        record on the log" and silently re-registers every pane as a fresh incarnation;
  * M5  `rehydrate` drops the vocabulary fence, so an adapter no node schema version admits gets
        into the live view through the reader's door;
  * M6  `rehydrate` drops the duplicate guard and overwrites the live state of a running node;
  * M7  the attestation accepts a non-positive pid — READY recorded for a process nobody saw;
  * M8  `register_pane_session` takes any duck-typed object, so a caller can assert the
        supervisor's own I-C1 attestation (18D spec-audit MEDIUM-3, on the pane surface);
  * M9  the pane record's `model_ref` becomes `None` by construction (the PROBE record's shape),
        so the node log describes a session running a model it does not name;
  * M10 the release closes the node record only when it also reclaimed a LEASE — so a session
        whose lease was already reaped leaves a node reading SPAWNING forever;
  * M11 [JS] a failed attestation tears down the live governed session instead of being recorded;
  * M12 [JS] the shell attests with the pane id it chose instead of the node id PYTHON minted;
  * M13 the attestation stops checking the pid is LIVE — "refuse to record READY for a process
        nobody observed" was the docstring while `pid > 0` was the whole check;
  * M14 the post-ticket acts stop checking the SESSION binding, so a stale record left open by a
        crashed shell can be attested READY with an unrelated process's pid;
  * M15 the same fence on the CLOSE path — a late release for session A writing TERMINATED against
        session B's live record;
  * M16 `rehydrate` stops requiring a `spawn` row, so a fabricated record can be transitioned and
        closed, putting `transition`+`exit` on the chain for a node that never spawned;
  * M17 a prior incarnation left open by a dead process is stranded again;
  * M18 …and one under a LIVE pid stops refusing the new one, so a pane node gets two live
        incarnations;
  * M19 the payloads stop naming the node log they are about, so `registered:true` under
        `SOW_NODE_EVENT_LOG` can be a claim about a file in %TEMP%;
  * M20 the refusal ticket asserts "no record exists" again instead of reporting what it measured;
  * M21 a flag-shaped value is accepted again by the release modes (`--release-session --pid 5`);
  * M22 [JS] every pane is attested again, including the local and OP-6 ones with no record.

Run from the repo root:  py -3.12 tools/mutation/_op18e_electron_wiring_mutations.py
"""
from __future__ import annotations

import hashlib
import pathlib
import signal
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PY = [sys.executable, "-m", "pytest", "-q", "-x"]
NODE = ["node", "--test"]

EMITTER = "tools/live/emit_worker_launch.py"
REGISTRATION = "node_runtime/supervisor/provider_node_registration.py"
REGISTRY = "control_plane/nodes/registry.py"
SPAWN_JS = "apps/desktop/picker/worker-spawn.js"

T = "tests/unit/test_worker_pane_node_registration.py"
JS_T = "apps/desktop/test/worker-spawn.test.js"

MUTATIONS = [
    ("M1  `registrar` becomes a defaulted keyword again",
     EMITTER,
     "    registrar: Any,\n    workspace: str = WORKER_WORKSPACE,",
     "    registrar: Any = None,\n    workspace: str = WORKER_WORKSPACE,",
     T + "::TestTheTicketRegistersThePanesNode::test_the_registrar_is_a_required_keyword"),
    ("M2  a registrar refusal escapes instead of refusing the session (the lease is never returned)",
     EMITTER,
     "    ProviderNodeRegistrationRefused,\n    RegistrationRefused,\n)",
     ")",
     T + "::TestTheTicketRegistersThePanesNode"
       + "::test_a_registration_refusal_refuses_the_session_and_hands_the_terminal_back"),
    ("M3  the ticket stops releasing the node log's cross-process lock",
     EMITTER,
     "        if registrar is not None:\n"
     "            try:\n"
     "                registrar.close()\n"
     "            except Exception:      # noqa: BLE001 — a close that fails must not mask the ticket\n"
     "                pass",
     "        pass",
     T + "::TestTheAttestationAndReleaseModes"
       + "::test_the_attestation_moves_the_record_to_ready_with_the_pid"),
    ("M4  `adopt_from_log` reads the row ROOT instead of its `data` block",
     REGISTRATION,
     '                    data = row.get("data") if isinstance(row.get("data"), dict) else {}',
     "                    data = row",
     T + "::TestTheLifecycleIsWrittenAtTheThreeMomentsItBecomesTrue"
       + "::test_a_fresh_process_adopts_the_record_from_the_log_and_attests_the_spawn"),
    ("M5  `rehydrate` drops the vocabulary fence",
     REGISTRY,
     "        admitted = adapter_version_map().get(record.adapter)\n"
     "        if admitted is None and record.adapter not in ADAPTER_EXEMPTIONS:",
     "        admitted = adapter_version_map().get(record.adapter)\n"
     "        if False:",
     T + "::TestRehydrateRestoresTheCacheWithoutWritingAnything"
       + "::test_rehydrating_an_adapter_no_schema_version_admits_is_refused"),
    ("M6  `rehydrate` drops the duplicate guard and overwrites a live node",
     REGISTRY,
     "            key = (record.node_id, record.incarnation)\n"
     "            if key in self._nodes:",
     "            key = (record.node_id, record.incarnation)\n"
     "            if False:",
     T + "::TestRehydrateRestoresTheCacheWithoutWritingAnything"
       + "::test_rehydrating_over_a_live_key_is_refused"),
    ("M7  the attestation accepts a non-positive pid",
     REGISTRATION,
     "        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:",
     "        if False:",
     T + "::TestTheAttestationAndReleaseModes::test_a_non_positive_pid_is_refused"),
    ("M8  `register_pane_session` accepts any duck-typed object",
     REGISTRATION,
     "        if not isinstance(session, WorkerPaneSession):",
     "        if False:",
     T + "::TestTheRegistrarRefusesWhatItCannotVouchFor::test_a_duck_typed_session_is_refused"),
    ("M9  the pane record's `model_ref` becomes null by construction (the probe record's shape)",
     REGISTRATION,
     '        "model_ref": slug if isinstance(slug, str) and slug.strip() else None,',
     '        "model_ref": None,',
     T + "::TestThePaneRecordIsSchemaValidAndDerived"
       + "::test_the_record_names_the_model_the_pane_will_actually_run"),
    ("M10 the release closes the node record only when it also reclaimed a lease",
     EMITTER,
     '    if registrar is not None:\n'
     '        # A ledger fault above must not stop the record from being closed',
     '    if registrar is not None and out["released"]:\n'
     '        # A ledger fault above must not stop the record from being closed',
     T + "::TestTheAttestationAndReleaseModes"
       + "::test_the_release_closes_the_record_even_when_no_lease_remains"),
    # ---- the shell's two rules, measured where they live ----------------------------------------
    ("M11 [JS] a failed attestation tears down the live governed session",
     SPAWN_JS,
     "      } catch (e) {\n"
     "        attestation = { ok: false, attested: false, error: `${e.name || \"Error\"}: "
     "${e.message}` };\n"
     "      }",
     "      } catch (e) {\n"
     "        throw e;\n"
     "      }",
     JS_T),
    ("M12 [JS] the shell attests with the pane id it chose, not the node id python minted",
     SPAWN_JS,
     "        attestation = await attestSpawn(rec.nodeId, sessionId, rec.pid,",
     "        attestation = await attestSpawn(pid, sessionId, rec.pid,",
     JS_T),
    # ---- the remediation rows: every fence the two reviewers' findings produced ------------------
    ("M13 the attestation stops checking that the pid is a LIVE process (spec-audit MAJOR-1)",
     REGISTRATION,
     "        if not alive:",
     "        if False:",
     T + "::TestTheSessionBindingBothReviewersFound"
       + "::test_a_dead_pid_is_refused_rather_than_recorded_as_ready"),
    ("M14 post-ticket acts stop checking the SESSION binding (validator MAJOR-1/audit MAJOR-2)",
     REGISTRATION,
     '        if registration.record.get("node_id") != expected:',
     "        if False:",
     T + "::TestTheSessionBindingBothReviewersFound::test_another_sessions_record_is_never_attested"),
    ("M15 the close stops checking the session binding (the other half of the same fence)",
     REGISTRATION,
     '        expected = node_record_uuid(f"{node_key}#{sid}", registration.incarnation)',
     '        expected = registration.record.get("node_id")',
     T + "::TestTheSessionBindingBothReviewersFound::test_another_sessions_record_is_never_closed"),
    ("M16 `rehydrate` stops requiring a `spawn` row on the log (spec-audit MINOR-8)",
     REGISTRY,
     "        if not self._log_carries_spawn(record.node_id, record.incarnation):",
     "        if False:",
     T + "::TestRehydrateRestoresTheCacheWithoutWritingAnything"
       + "::test_rehydrating_a_record_the_log_does_not_carry_is_refused"),
    ("M17 a prior incarnation left open by a dead process is stranded again (audit MEDIUM-4)",
     REGISTRATION,
     "        self._reap_stale_incarnation(node_key, incarnation)",
     "        pass",
     T + "::TestTheStaleIncarnationReap"
       + "::test_a_prior_incarnation_left_open_by_a_dead_process_is_closed_not_stranded"),
    ("M18 a prior incarnation under a LIVE pid no longer refuses the new one",
     REGISTRATION,
     "                if pid_is_alive(pid):",
     "                if False:",
     T + "::TestTheStaleIncarnationReap"
       + "::test_a_prior_incarnation_under_a_LIVE_pid_refuses_the_new_one"),
    ("M19 the payloads stop naming the node log they are about (spec-audit MEDIUM-3)",
     EMITTER,
     '            "log_path": log_path,\n'
     '            "adapter_admitted_by": out.adapter_schema_version, "reason": None}',
     '            "adapter_admitted_by": out.adapter_schema_version, "reason": None}',
     T + "::TestEveryPayloadNamesTheLogItIsAbout"
       + "::test_the_ticket_the_attestation_and_the_release_all_name_the_path"),
    ("M20 the refusal ticket asserts `no record exists` again instead of reporting what it measured",
     EMITTER,
     '        ticket = _refusal(f"{type(exc).__name__}: {exc}", gates=gates, '
     'refused_by=_gate_id(exc),\n'
     "                          node_registration=node_registration)",
     '        ticket = _refusal(f"{type(exc).__name__}: {exc}", gates=gates, '
     'refused_by=_gate_id(exc))',
     T + "::TestTheTicketRegistersThePanesNode"
       + "::test_a_registration_refusal_after_the_record_was_written_closes_it"),
    ("M21 a flag-shaped value is accepted again by the release modes (validator MINOR-2)",
     EMITTER,
     '    if value is None or value.startswith("-"):',
     "    if value is None:",
     T + "::TestTheCliContract::test_the_attestation_mode_refuses_a_missing_node_key_with_no_json"),
    ("M22 [JS] every pane is attested again, including the ones with no record of their own",
     SPAWN_JS,
     "    if (!registration || registration.registered !== true) {",
     "    if (false) {",
     JS_T),
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
        if target.endswith(".test.js"):
            cmd, cwd = [*NODE, pathlib.Path(target).name], ROOT / "apps" / "desktop" / "test"
        else:
            cmd, cwd = [*PY, target], ROOT
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
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
