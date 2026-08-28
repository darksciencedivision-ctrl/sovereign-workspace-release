"""Mutation runner for Phase 19 unit 1 — the OP-13 revert of the provider permission-mode widening.

Same contract as its siblings: apply one mutation, run one selector, record RED (a test caught it)
or GREEN (nothing did), restore the original bytes, verify the restore is BYTE-IDENTICAL by sha256.
Exit 1 if anything is GREEN or a restore diverges.

Most rows below RESTORE A SHIPPED BEHAVIOUR: the `new` string is the code that was on the tree at
`b109f02`, the last of the seven untagged post-18E commits. Four are not byte-exact restorations and
each says so at its own entry, because a blanket provenance claim would be the inference-stated-as-
evidence this unit exists to correct (gate-validator round-2 MEDIUM-2, spec-audit MINOR-4): **M2** is
signature-only and produces a state that was never shipped; **M7/M8** are single-factor mutations of
the CURRENT line (isolating one flag each) rather than the shipped line that moved two; **M9/M10**
inline literals or re-flow prose because the constants and the line structure they used are gone.
Each still reproduces the DEFECT it names. That is the point of this harness. The
operator's ruling (OP-13) is that Antigravity's own `accept-edits` mode is not operator approval,
and the requirement attached to it is a test that refuses `accept-edits` **for every execution
profile, so the carve-out cannot reappear untested**. A revert with no falsification is a diff;
these rows are what make it a guard.

  * M1  the `execution_profile` carve-out returns whole — the parameter and the
        `antigravity_execution` exemption — and `agy --mode accept-edits` is emitted again by any
        caller that passes the keyword;
  * M2  the parameter comes back ALONE, defaulted to None, with the guard still unconditional. This
        row is signature-only and says so: no behaviour changes, and it exists because a keyword a
        caller can pass is the re-arming surface, which is why the revert deleted it rather than
        defaulting it off;
  * M3  `ANTIGRAVITY_HEADLESS_MODE` goes back to `accept-edits` — the exact line OP-13 names
        (`adapters/frontier/antigravity.py:72`). With the guard unconditional this must fail LOUDLY
        at the adapter, not quietly at a comment;
  * M4  the 18A probe's `ANTIGRAVITY_PROBE_MODE` goes back to `accept-edits`, which is the same
        widening on the diagnostic path the operator runs by hand;
  * M5  `GROK_HEADLESS_PERMISSION_MODE` goes back to `default` (U327's half of the finding);
  * M6  `--no-plan` is emitted again beside the restored `plan` pin — the widening under a second
        name, since the installed capture defines that flag as "Disable plan mode";
  * M7  `--no-plan` is removed from `FORBIDDEN_PROVIDER_ARGS` again, so nothing refuses it even
        though no builder emits it. M6 is the emission; M7 is the policy. A revert that fixed only
        one of them would leave the other free to bring the widening back.

Rows M8-M11 were added after the mandatory reviewers ran on the first version of this unit and each
found residue the revert had missed (gate-validator MAJOR-1, spec-audit MAJOR-1/2/3/4, MEDIUM-6):

  * M8  `--allow` leaves the forbidden list again (U340, the policy half);
  * M9  the interactive Grok builder emits `--allow mcp__sovereign__*` again (the emission half —
        it is a separate row because with M8 unapplied the builder refuses its own argv, which is
        the fail-closed behaviour this unit restored and wants proven);
  * M10 the Antigravity launch note goes back to the hand-written `--mode accept-edits` prose. This
        is the row that did not exist when the reviewers found the defect: the argv was reverted and
        the ticket still ADVERTISED the forbidden mode, invisibly to 2262 tests;
  * M11 `.grok/config.toml` supplies `permission_mode = "default"` again — the repo's own tracked
        config handing a node-controlled default to the pin that exists to refuse one.

Note on numbering: the `MUTATIONS` list carries an M1b row (the carve-out's second half) so the
count printed at the end is one higher than the highest label.

Run from the repo root:  py -3.12 tools/mutation/_op13_permission_mode_mutations.py
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
AG = "adapters/frontier/antigravity.py"
GROK = "adapters/frontier/grok_build.py"
RECON = "tools/providers/frontier_provider_recon.py"

ADAPTERS = "tests/unit/test_op12_frontier_adapters.py"
NO_CARVE_OUT = ADAPTERS + "::TestTheGuardHasNoExecutionProfileCarveOut"
PIN = ADAPTERS + "::TestThePinnedModeSurvivedALiveTest"
PICKER = "tests/unit/test_op12_pane_picker.py"
TICKET_NOTE = "tests/unit/test_worker_ticket_honesty.py"
SPAWN = "node_runtime/supervisor/worker_pane_spawn.py"
GROK_CONFIG = ".grok/config.toml"

_GUARD_SIG = "def assert_no_forbidden_provider_args(argv: Sequence[str]) -> None:"
_GUARD_SIG_PROFILED = ("def assert_no_forbidden_provider_args(argv: Sequence[str], *, "
                       "execution_profile: str | None = None) -> None:")
_MODE_CHECK = "        if name in _MODE_FLAG_NAMES and value in FORBIDDEN_PERMISSION_MODES:"
_MODE_CHECK_CARVED = (
    '        antigravity_execution = (execution_profile == "google_antigravity" and name == "mode"\n'
    '                                 and value == "accept-edits")\n'
    "        if name in _MODE_FLAG_NAMES and value in FORBIDDEN_PERMISSION_MODES "
    "and not antigravity_execution:")

MUTATIONS = [
    ("M1  the `execution_profile` carve-out returns in full (OP-13's subject)",
     COMMON, _GUARD_SIG + "\n", _GUARD_SIG_PROFILED + "\n", NO_CARVE_OUT),
    ("M1b the carve-out's exemption returns (the half that emits accept-edits)",
     COMMON, _MODE_CHECK, _MODE_CHECK_CARVED, NO_CARVE_OUT),
    # Signature-only by design — see the module docstring. It is the re-arming surface, not a
    # behaviour change, and the test that catches it is the TypeError leg.
    ("M2  the parameter returns alone, defaulted off (signature only)",
     COMMON, _GUARD_SIG, _GUARD_SIG_PROFILED,
     NO_CARVE_OUT + "::test_the_execution_profile_keyword_no_longer_exists"),
    ("M3  ANTIGRAVITY_HEADLESS_MODE goes back to accept-edits (antigravity.py:72)",
     AG, 'ANTIGRAVITY_HEADLESS_MODE = "plan"', 'ANTIGRAVITY_HEADLESS_MODE = "accept-edits"',
     ADAPTERS),
    ("M4  the 18A probe mode goes back to accept-edits (the operator-run diagnostic)",
     RECON, 'ANTIGRAVITY_PROBE_MODE = "plan"', 'ANTIGRAVITY_PROBE_MODE = "accept-edits"',
     "tests/unit/test_frontier_provider_recon.py"),
    ("M5  GROK_HEADLESS_PERMISSION_MODE goes back to default (U327)",
     GROK, 'GROK_HEADLESS_PERMISSION_MODE = "plan"', 'GROK_HEADLESS_PERMISSION_MODE = "default"',
     PIN),
    ("M6  --no-plan is emitted again beside the pin it cancels (U327)",
     GROK,
     "    argv += [GROK_PERMISSION_MODE_FLAG, GROK_HEADLESS_PERMISSION_MODE,\n"
     "             GROK_NO_MEMORY_FLAG, GROK_MINIMAL_FLAG,",
     "    argv += [GROK_PERMISSION_MODE_FLAG, GROK_HEADLESS_PERMISSION_MODE, \"--no-plan\",\n"
     "             GROK_NO_MEMORY_FLAG, GROK_MINIMAL_FLAG,",
     PICKER),
    ("M7  --no-plan leaves the forbidden list again (the policy half)",
     COMMON,
     '    "--allow", "--allowedtools", "--tools", "--no-plan", "--plugin-dir", "--agents",',
     '    "--allow", "--allowedtools", "--tools", "--plugin-dir", "--agents",',
     PIN + "::test_no_plan_is_never_emitted_beside_the_pin_that_it_cancels"),
    ("M8  --allow leaves the forbidden list again (U340, the policy half)",
     COMMON,
     '    "--allow", "--allowedtools", "--tools", "--no-plan", "--plugin-dir", "--agents",',
     '    "--allowedtools", "--tools", "--no-plan", "--plugin-dir", "--agents",',
     NO_CARVE_OUT + "::test_no_allow_rule_survives_either_the_guard_or_any_builder"),
    ("M9  the interactive Grok builder emits an allow rule again (the emission half)",
     GROK,
     "             GROK_NO_SUBAGENTS_FLAG, GROK_DISABLE_WEB_SEARCH_FLAG]",
     '             GROK_NO_SUBAGENTS_FLAG, GROK_DISABLE_WEB_SEARCH_FLAG,\n'
     '             "--allow", "mcp__sovereign__*"]',
     PICKER),
    ("M10 the Antigravity launch note advertises accept-edits again (the reviewers' MAJOR-1)",
     SPAWN,
     'f"{describe_pinned_flags(argv, workspace=str(workspace))}; the workspace is "',
     '"--mode accept-edits, --add-dir on the authorized workspace; the workspace is "',
     TICKET_NOTE),
    ("M11 the repo's own .grok config supplies permission_mode = default again (MEDIUM-6)",
     GROK_CONFIG,
     'screen_mode = "minimal"',
     'screen_mode = "minimal"\npermission_mode = "default"',
     NO_CARVE_OUT + "::test_the_repo_config_does_not_supply_the_value_the_argv_pins"),
    # M12/M13 were added in round 2, from findings on the ROUND-1 REMEDIATION itself: the note
    # derivation could not over-claim but could silently omit, and only the Antigravity note had a
    # row. Neither is a restoration of shipped code — the deriver never shipped — and both name the
    # exact defect the reviewers demonstrated.
    ("M12 the note deriver goes back to an inclusion list that omits the mode pins (fails open)",
     SPAWN,
     "        if not tok.startswith(\"-\") or tok in _NOTE_SILENT_FLAGS:",
     "        if not tok.startswith(\"-\") or tok in _NOTE_SILENT_FLAGS "
     "or tok in (\"--permission-mode\", \"--mode\"):",
     TICKET_NOTE),
    ("M13 the GROK launch note goes back to hand-written prose (M10's missing twin)",
     SPAWN,
     'f"interactive `grok` TUI worker session (no -p, "',
     'f"interactive `grok` TUI worker session (no -p, plan disabled, "',
     TICKET_NOTE),
]

#: Files this run may have mutated, pinned at import so the signal handler can restore ALL of them
#: even if it fires between the write and the restore (the contract `pane_input_bypass_mutations.js`
#: documents: a harness that writes to product files must never be able to leave one mutated).
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
