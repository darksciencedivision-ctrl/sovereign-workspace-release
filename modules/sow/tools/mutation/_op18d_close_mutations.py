"""Mutation runner for the guards the Phase 18D `.close` wiring rests on.

Same contract as its siblings: apply one mutation, run one selector, record RED (a test caught it)
or GREEN (nothing did), restore the original bytes, verify the restore is BYTE-IDENTICAL by sha256.
Exit 1 if anything is GREEN or a restore diverges. It exists because a mutation verdict asserted in
an evidence report is prose that cannot disagree with its value — run it and the verdicts reproduce.

`.amendment` opened the node vocabulary and wired nothing to it. `.close` is the wiring, so the
mutations here are aimed at the claims the wiring makes:

  * C1  the record is written under the SUCCESSOR schema. Declaring `node@1.0` instead must fail —
        the frozen enum has no member for these providers, so a record that claimed it would be
        invalid, and a validator that let it through would be validating nothing;
  * C2  the schema validation is REAL. Removing the `validate_node_record` call must fail, or the
        "validates against node@1.1" claim rests on the builder agreeing with itself;
  * C3  supervision is READ from the session, never asserted for it (I-C1);
  * C4  the record is CLOSED when the session ends — a one-shot probe leaving a node reading
        SPAWNING forever is a D-LOOP-1 leak in the one place an auditor would look for it;
  * C5  the registration failure is FATAL to the session. Swallowing it would leave a leased,
        supervised terminal with no node record — the naked-but-leased session the whole chain
        exists to prevent;
  * C6  `registrar` stays a required keyword: a default is this module deciding whether the session
        it opens is a Sovereign node;
  * C7  the log stays LAZY. An eager registrar wrote an empty `node_events.jsonl` into the
        operator's durable store for every probe refused at gate 1 (found by looking at
        `.sovereign_store/` after a suite run, not by a test — now it is a test);
  * C8  the product call site really passes a registrar — a probe engine that quietly stopped
        would leave the wiring true only in the tests that inject one;
  * C9  the record uuid derives from the INCARNATION as well as the lease key, or two rows of one
        append-only log carry the same `node_id`;
  * C10 the emitter's `ok` cannot go green on an unregistered provider;
  * C11 the receipt's verdict cannot go green when the operator's switch has been OPENED — the
        rule that stops this fail-closed receipt ever standing in for the live legs;
  * C12 the receipt's OWED block cannot claim the durable-record leg was performed (the U296 shape,
        which is exactly the defect the `.amendment` gate found in the 18C receipt).

Run from the repo root:  py -3.12 tools/mutation/_op18d_close_mutations.py
"""
from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
import _bytecode_discipline as _discipline  # CU-A1 (U534)
PY = [sys.executable, "-m", "pytest", "-q", "-x"]

REGISTRATION = "node_runtime/supervisor/provider_node_registration.py"
SESSION = "node_runtime/supervisor/provider_probe_session.py"
RECON = "tools/providers/frontier_provider_recon.py"
EMITTER = "tools/live/emit_provider_node_registration.py"

MUTATIONS = [
    ("C1  the record declares the FROZEN schema version",
     REGISTRATION,
     'RECORD_SCHEMA_VERSION = "node@1.1"',
     'RECORD_SCHEMA_VERSION = "node@1.0"',
     "tests/unit/test_provider_node_registration.py::TestTheRecordIsSchemaValidAndDerived"),
    ("C2  the record is registered without being validated",
     REGISTRATION,
     "        record = build_provider_node_record(session, incarnation=incarnation)\n"
     "        validated = validate_node_record(record)",
     "        record = build_provider_node_record(session, incarnation=incarnation)\n"
     '        validated = "node@1.1"',
     "tests/unit/test_provider_node_registration.py::TestRegistrationIsRealAndAuditable::"
     "test_a_record_that_would_not_validate_is_refused_at_registration"),
    ("C3  supervision is asserted for the session instead of read from it (I-C1)",
     REGISTRATION,
     '        if getattr(session, "supervised", False) is not True:',
     "        if False:",
     "tests/unit/test_provider_node_registration.py::TestRegistrationIsRealAndAuditable::"
     "test_a_session_that_is_not_supervised_is_refused_before_anything_is_written"),
    ("C4  the node record is never closed when the session ends (D-LOOP-1)",
     SESSION,
     "        if registrar is not None and registration is not None:",
     "        if False:",
     "tests/unit/test_provider_node_registration.py::TestTheProbeSessionRegistersItsNode::"
     "test_an_opened_session_is_a_registered_node_and_says_so"),
    ("C5  a refused registration is swallowed and the session proceeds",
     SESSION,
     "        if registrar is not None:\n"
     "            registration = registrar.register_session(session)\n"
     "            session.node_registered = True",
     "        if registrar is not None:\n"
     "            try:\n"
     "                registration = registrar.register_session(session)\n"
     "            except Exception:\n"
     "                registration = None\n"
     "            session.node_registered = True",
     "tests/unit/test_provider_node_registration.py::TestTheProbeSessionRegistersItsNode::"
     "test_a_refused_registration_refuses_the_session_and_releases_the_lease"),
    ("C6  `registrar` becomes a defaulted keyword",
     SESSION,
     '    registrar: "ProviderNodeRegistrar | None",',
     '    registrar: "ProviderNodeRegistrar | None" = None,',
     "tests/unit/test_op12_probe_session.py::TestTheTwoExternallySourcedGatesCannotBeDefaulted"),
    ("C7  the registrar opens its log eagerly again",
     REGISTRATION,
     "        self._registry: NodeRegistry | None = None if log is None else NodeRegistry(log)",
     "        self._log = log if log is not None else AppendOnlyEventLog(self._log_path)\n"
     "        self._registry = NodeRegistry(self._log)",
     "tests/unit/test_provider_node_registration.py::TestRegistrationIsRealAndAuditable::"
     "test_constructing_a_registrar_writes_nothing"),
    ("C8  the probe engine stops passing a registrar",
     RECON,
     "            profile_loader=loader, registrar=default_provider_node_registrar(repo_root),",
     "            profile_loader=loader, registrar=None,",
     "tests/unit/test_frontier_provider_recon.py::TestLiveProbeGate"),
    ("C9  the record uuid ignores the incarnation",
     REGISTRATION,
     'return str(uuid.uuid5(_NODE_ID_NAMESPACE, f"{lease_key}#{int(incarnation)}"))',
     "return str(uuid.uuid5(_NODE_ID_NAMESPACE, lease_key))",
     "tests/unit/test_provider_node_registration.py"),
    ("C10 the report is ok even when a provider did not register",
     EMITTER,
     '        and all(r.get("registered") is True for r in report["registrations"].values())',
     "        and True",
     "tests/unit/test_emit_provider_node_registration.py::TestEveryOkConjunctCanGoRed::"
     "test_a_registration_that_did_not_happen_fails"),
    # ---- the review remediation, each finding with its own mutation --------------------------
    ("R1  the registrar takes any duck-typed session again (spec-audit MEDIUM-3)",
     REGISTRATION,
     "        if not isinstance(session, GovernedProbeSession):",
     "        if False:",
     "tests/unit/test_provider_node_registration.py::TestRegistrationIsRealAndAuditable::"
     "test_a_duck_typed_session_cannot_assert_i_c1_on_the_supervisors_behalf"),
    ("R2  a session holding no I-X3 terminal registers anyway (spec-audit MEDIUM-3)",
     REGISTRATION,
     '        if not (str(getattr(session, "lease_id", "") or "").strip()',
     "        if False and (",
     "tests/unit/test_provider_node_registration.py::TestRegistrationIsRealAndAuditable::"
     "test_a_session_holding_no_terminal_is_refused"),
    ("R3  the incarnation is asked of memory, not of the log (spec-audit MEDIUM-2)",
     REGISTRATION,
     "        try:\n            with self._log_path.open(\"r\", encoding=\"utf-8\") as fh:",
     "        try:\n            raise OSError('skip the log')\n            with self._log_path.open(\"r\", encoding=\"utf-8\") as fh:",
     "tests/unit/test_provider_node_registration.py::TestRegistrationIsRealAndAuditable::"
     "test_the_incarnation_comes_from_the_log_not_from_this_process"),
    ("R4  the node log is no longer held exclusively (spec-audit MEDIUM-5)",
     REGISTRATION,
     "        if self._registry is None:\n            self._acquire_lock()",
     "        if self._registry is None:\n            pass",
     "tests/unit/test_provider_node_registration.py::TestRegistrationIsRealAndAuditable::"
     "test_the_log_is_held_exclusively_while_a_registrar_owns_it"),
    ("R5  a LIVE lock holder is treated as dead and its lock stolen",
     REGISTRATION,
     "        if raw is None or not raw.isdigit():\n            return False",
     "        if raw is None or not raw.isdigit():\n            return True",
     "tests/unit/test_provider_node_registration.py::TestRegistrationIsRealAndAuditable::"
     "test_a_lock_whose_holder_is_gone_is_reclaimed_and_one_that_lives_is_not"),
    ("R6  every node exit is recorded as expected again (spec-audit MEDIUM-4)",
     SESSION,
     "        node_expected = body_error is None and (session is None or session.process_tree_clean is not False)",
     "        node_expected = True",
     "tests/unit/test_provider_node_registration.py::TestTheProbeSessionRegistersItsNode::"
     "test_a_session_that_ends_badly_is_recorded_as_an_UNEXPECTED_exit"),
    ("R7  the session stops handing the node log's lock back (D-LOOP-1)",
     SESSION,
     "            try:\n                registrar.close()",
     "            try:\n                pass",
     "tests/unit/test_provider_node_registration.py::TestTheProbeSessionRegistersItsNode::"
     "test_the_session_hands_the_log_and_its_lock_back"),
    ("R8  the registry accepts a node_record that disagrees with it (validator MEDIUM-1)",
     "control_plane/nodes/registry.py",
     '        record = meta.get("node_record")\n        if record is not None:',
     '        record = meta.get("node_record")\n        if False:',
     "tests/unit/test_provider_node_registration.py::TestRegistrationIsRealAndAuditable::"
     "test_the_registry_refuses_a_node_record_payload_that_disagrees_with_it"),
    ("R9  the report manufactures its own `cloud` profile again (spec-audit MAJOR-1)",
     EMITTER,
     "            profile_loader=profile_loader_from_host(),",
     '            profile_loader=__import__("control_plane.profiles.loader", fromlist=["x"])'
     '.ProfileLoader(__import__("control_plane.profiles.loader", fromlist=["x"])'
     '.DeploymentProfile("cloud")),',
     "tests/unit/test_emit_provider_node_registration.py::TestTheReportMeasuresTheAmendment::"
     "test_the_deployment_profile_is_the_hosts_and_an_air_gapped_host_refuses"),
    ("R10 the report stops disclosing WHICH switch file it read (validator MEDIUM-3)",
     EMITTER,
     '            "path": path, "env_override": bool(env_override), "env_var": _la._ENV_OVERRIDE,',
     "",
     "tests/unit/test_emit_provider_node_registration.py::TestTheReportMeasuresTheAmendment::"
     "test_the_report_says_which_switch_file_it_read_and_flags_an_env_override"),
    ("R11 the I-X3 allowance is displayed but no longer asserted (spec-audit MINOR-9)",
     EMITTER,
     '        and all(r.get("allowance") == 1 for r in report["registrations"].values())',
     "        and True",
     "tests/unit/test_emit_provider_node_registration.py::TestEveryOkConjunctCanGoRed::"
     "test_a_widened_ix3_allowance_fails"),
    ("R16 the supervision check accepts anything truthy (validator MINOR-1)",
     REGISTRATION,
     '        if getattr(session, "supervised", False) is not True:',
     '        if not getattr(session, "supervised", False):',
     "tests/unit/test_provider_node_registration.py::TestRegistrationIsRealAndAuditable::"
     "test_supervision_must_be_exactly_True_not_merely_truthy"),
    ("R17 the provenance is hardcoded instead of derived (validator MINOR-2)",
     REGISTRATION,
     "        admitted = adapter_version_map().get(session.provider)",
     '        admitted = "node@1.1"',
     "tests/unit/test_provider_node_registration.py::TestRegistrationIsRealAndAuditable::"
     "test_the_provenance_follows_the_vocabulary_it_reads"),
    ("R12 the durable store is measured by size again, not by content (spec-audit MINOR-8)",
     EMITTER,
     '                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}',
     '                    "sha256": None}',
     "tests/unit/test_emit_provider_node_registration.py::TestTheReportMeasuresTheAmendment::"
     "test_the_operators_durable_store_is_untouched_measured_by_CONTENT"),
]

#: The two JS rules, run against the desktop suite rather than pytest.
JS_MUTATIONS = [
    ("C11 the verdict passes with the operator's live switch OPEN",
     "apps/desktop/selfcheck/op18d-registration-verdict.js",
     "  if (!Array.isArray(real.op12_authorized) || real.op12_authorized.length !== 0) {",
     "  if (false) {"),
    ("C12 the shipped OWED block claims the durable node record exists",
     "apps/desktop/selfcheck/op18d-registration-selfcheck.js",
     None,   # a block replacement — see `_owed_mutation`
     None),
    ("R13 the OWED claims are no longer checked against the measurements (validator MEDIUM-2)",
     "apps/desktop/selfcheck/op18d-registration-verdict.js",
     "  } else if (after.exists === true) {",
     "  } else if (false) {"),
    ("R14 an env-overridden switch is accepted as the operator's own (validator MEDIUM-3)",
     "apps/desktop/selfcheck/op18d-registration-verdict.js",
     "  if (real.env_override === true) {",
     "  if (false) {"),
    ("R15 a report with no durable-store block passes the rule again (spec-audit MINOR-7)",
     "apps/desktop/selfcheck/op18d-registration-verdict.js",
     "  if (!report.durable_store || report.durable_store.unchanged !== true) {",
     "  if (report.durable_store && report.durable_store.unchanged !== true) {"),
]

JS_TEST = "test/op18d-registration-verdict.test.js"


def digest(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _owed_mutation(text: str) -> str:
    """Replace the OWED durable-record entry with a claim that the leg was performed."""
    start = text.index("  durable_node_record_for_a_live_session:")
    end = text.index("  antigravity_auth_state:")
    return (text[:start]
            + '  durable_node_record_for_a_live_session:\n'
              '    "a Sovereign node record exists on the operator\'s own durable node log for a '
              'live session of each provider — nothing is owed here",\n'
            + text[end:])


def run_one(rel: str, mutate, target_cmd: list[str], cwd: pathlib.Path) -> tuple[str, str]:
    path = ROOT / rel
    before = path.read_bytes()
    before_hash = digest(path)
    text = before.decode("utf-8")
    try:
        mutated = mutate(text)
    except ValueError:
        return "SKIPPED-ANCHOR-MISSING", "unchanged"
    if mutated == text:
        return "SKIPPED-ANCHOR-MISSING", "unchanged"
    path.write_bytes(mutated.encode("utf-8"))
    _discipline.invalidate_for(path)
    try:
        proc = subprocess.run(target_cmd, cwd=cwd, capture_output=True, text=True, env=_discipline.child_env())
        verdict = "RED" if proc.returncode != 0 else "GREEN (guard does not hold)"
    finally:
        path.write_bytes(before)
    _discipline.invalidate_for(path)
    return verdict, ("restored" if digest(path) == before_hash else "RESTORE FAILED")


def main() -> int:
    rows = []
    for label, rel, old, new, target in MUTATIONS:
        verdict, restore = run_one(
            rel, lambda t, o=old, n=new: t.replace(o, n, 1) if o in t else t,
            PY + [target], ROOT)
        rows.append((label, verdict, restore))

    desktop = ROOT / "apps" / "desktop"
    for label, rel, old, new in JS_MUTATIONS:
        mutate = (_owed_mutation if old is None
                  else (lambda t, o=old, n=new: t.replace(o, n, 1) if o in t else t))
        verdict, restore = run_one(rel, mutate, ["node", "--test", JS_TEST], desktop)
        rows.append((label, verdict, restore))

    width = max(len(r[0]) for r in rows)
    for label, verdict, restore in rows:
        print(f"{label.ljust(width)}  {verdict:<26} {restore}")
    ok = all(r[1] == "RED" and r[2] == "restored" for r in rows)
    failed = [r[0] for r in rows if r[2] == "RESTORE FAILED"]
    # A missing anchor and a failed restore are different failures and used to print the same
    # sentence, which is how "A RESTORE FAILED" got reported for a mutation that never ran.
    print(f"\n{sum(1 for r in rows if r[1] == 'RED')}/{len(rows)} RED, "
          + ("all restores byte-identical" if not failed
             else "RESTORE FAILED: " + "; ".join(failed)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
