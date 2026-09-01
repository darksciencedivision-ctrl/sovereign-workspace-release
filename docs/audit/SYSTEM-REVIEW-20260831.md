# utc: 2026-09-01T02:31:44Z
# producer: claude-code EPC-03 post-seal measurement

# System review — `release-worktree` @ `9bd60de`

**What this document is.** A BUILDER measurement of the sealed tree, taken by running commands
against it. It is not a reviewer verdict. No gate status is asserted, `evidence/GATE-LEDGER.json`
is untouched, and nothing here is a PASS. `docs/REVIEW-*.md` is the reviewer-reserved namespace
(AGENTS.md §3) and this file is deliberately not in it.

**Why it exists.** The 2026-08-31 independent review
(`SOVEREIGN_COMPLETE_SYSTEM_ANALYSIS_20260831.pdf`) was conducted on a Linux sandbox against the
three 2026-08-27 baseline ZIPs plus a pasted production log. It said so plainly. It could not see
`D:\producttion software 2\release-worktree`, and six of its findings are stale against the sealed
tree. Those corrections need to live next to the seal, or the next session quotes the sandbox PDF
as current.

**Predecessor:** `docs/audit/SYSTEM-REVIEW-20260827.md` exists and is EMPTY (one `#`, zero lines).
Recorded here rather than fixed — an empty evidence file is itself a fact about the audit trail.

---

## 1. Method and scope

Measured at commit `9bd60de`, 0 dirty tracked files, against both the working tree and the cut
distribution `sovereign-workspace-1.0.0-rc.1-source.zip`. Every figure below came from a command
run in the session that produced this file.

Not covered, and stated so absence is not read as success:

- No clean-room install (see F-8 — the builder envelope forbids the action that would close it).
- No GPU-loaded multi-module run.
- No reviewer authority of any kind.

Where a defect was looked for and NOT found, that is recorded (F-6). A finding count is only
useful if the misses are visible too.

---

## 2. What is solid

| Property | Measured |
|---|---|
| Git anchor | 106 commits, HEAD `9bd60de`, 0 dirty tracked files |
| Distribution hygiene | 1,602 files ship; 2,081 tracked files (56%) excluded |
| Installer | `npm ci --ignore-scripts`, absolute `node.exe`, never a shell, dies without a lockfile |
| Locks / SBOM | 4 lockfiles; SBOM 240 components (106 required / 134 optional); NOTICE derived from SBOM |
| Test ratio — SOW | 172 source / 184 test |
| Test ratio — shell | 13 source / 65 test |
| Artifacts | 8 cut from seal; manifest hash == measured == sidecar; 0 mismatches |

`shell/tools/install_sow.py` is the one place a supply-chain compromise would enter, and it refuses
to run without a lockfile rather than falling back to `npm install`. That is the right shape.

---

## 3. Findings

### F-1 · HIGH — the reasoning product is effectively untested

```
modules/sovereign   source 37,256 lines   tests 284 lines   (0.76%)
```

Two test files, both authored during EPC-01 for narrow guards. The five largest sources carry no
Python test:

```
3153  sovereign_product/research.py
2906  synthesis/live_orchestrator.py
2865  sovereign_product/semantic_deep.py
2593  cycle_runner_v3.py
2382  sovereign_product/server.py
```

13,899 lines of orchestration, model-role machinery and evidence handling with no automated
coverage. For contrast: SOW 1.07, Debate 2.00, tokencenter 3.00.

**This implicates the builder's own work.** Behaviour was changed in `live_orchestrator.py` (the
hardcoded `max(threshold_answer, 0.9)` floor removed in favour of the approved
`CHALLENGE_ANSWER_COSINE`) and in `semantic_deep.py` (`num_ctx` derivation, generation-token
budget, `_safe_relative` containment). Neither change was covered by a test; verification was
manual smoke runs. That is the weakest evidence in this release and it sits in the module least
able to absorb a regression.

### F-2 · MODERATE — a quarantine lane exempts bytes that actually ship

```
quarantine_lanes: ['evidence/', 'dev/', 'modules/distillery/runs/']
  evidence/ in distribution : 0 files
  dev/      in distribution : 0 files
  modules/distillery/runs/  : 99 files
```

Quarantining the first two costs nothing — they ship nothing. The third ships. The gate classifies
those files as `runtime-session-state`, a violation class, downgrades all 79 to
"quarantined-historical", and reports `violations: 0` → PASS.

They are another machine's build-session state. Direct read of the shipped bytes:

```
modules/distillery/runs/completion-loop/F00_GIT_REALITY.json  (2474 bytes)
  "ryguy-pixel/Sovereign-Distillery",  "local_path": "D:\\Sovereign-Grounded-Distillery",
```

The companion guard does not catch it either (F-3), so two gates report clean over bytes that are
not.

**Edge of the finding, stated so it is not over-read:** `ryguy-pixel/Sovereign-Distillery` also
appears in `modules/distillery/README.md` and `docs/DECISIONS.md`, where naming a module's own
upstream is legitimate provenance, not a leak. The `runs/` files are a different thing — leftover
session state that ships only because a lane exempts it.

### F-3 · MODERATE — the developer-identifier guard cannot generalise

`shell/tests/test_developer_identifiers_are_bounded.py` matches five patterns — `Sslaw`,
`Product[ _]Software`, `Sov 1`, `C:\Users\…`, `producttion software` — all scoped to this
operator's disk. 49 shipped files match them, covered by 29 disclosed allowlist entries.

It caught a build-host path during Phase R because that path was one of the five it knows. A path
from any other build host passes, which is exactly what F-2 demonstrates.

### F-4 · LOW-MODERATE — 13 backup files tracked in git

Four sit beside the identity documents, and every one DIFFERS from the live file:

```
DIFFERS  VERSION.json           vs  VERSION.json.pre-CONVERGE01
DIFFERS  RELEASE-MANIFEST.json  vs  RELEASE-MANIFEST.json.pre-CONVERGE01
DIFFERS  shell/modules/sow.json        vs  sow.json.pre-rebase
DIFFERS  shell/modules/sovereign.json  vs  sovereign.json.pre-rebase
```

They do NOT ship — verified 0 in the distribution — so this is a stale-read hazard for a human or
a script working in the tree, not a recipient hazard. Severity is contained by that.

### F-5 · LOW — one genuinely dead module

`modules/sow/control_plane/canonical_registry.py`, 169 lines, 53 models × 18 fields, zero
references anywhere in the tree, no `__main__`. Confirms the independent review's B-16. The other
three unreferenced files are operator-invoked entry points and are correctly not dead.

A model registry nobody reads will drift, and will be treated as authority the first time someone
searches for "models".

### F-6 · INFORMATIONAL — 119 undocumented silent excepts, and the honest result of chasing them

64 of them in SOVEREIGN. A fail-open GATE was hypothesised as the most serious thing this review
could find, so all six instances in `publication_gate.py` and `evaluation/integrity.py` were read.

All six are justified: log rotation, log write, temp cleanup after an already-reported error, temp
cleanup inside a handler that then re-`raise`s, `FileNotFoundError` during a tree walk, and
`ValueError` from `relative_to` used as a subpath test.

**So the count is not a defect count and is not reported as one.** The detector measured absence of
comment, not absence of justification. The real cost is that triaging the other 113 requires
reading each one, in the module least able to afford that. This number belongs in no punch list.

### F-7 · INFORMATIONAL — the manifest/runtime context divergence

```
SYSTEM_MANIFEST declares    CONTEXT_WINDOW = 131072   (validated by system_manifest.py)
DEEP path actually requests num_ctx        =  20480   (8151 MiB VRAM, nvidia-smi)
```

6× apart inside one product. The code path that caused the measured 23.2 GB spill was fixed; the
declaration still advertises the number that caused it. Which number is true is an operator
decision, not a repair — and the EPC-03 VRAM table records that 16384 already spilled on this
card, so "make the DEEP path request 131072" is not the direction.

### F-8 · STRUCTURAL — the clean-room gap cannot be closed by the builder

No clean-room install has succeeded. The distribution ships 0 venvs and 0 node packages by design.
The lane's clean-room stages are opt-in and were SKIPPED.

`AGENTS.md` §7 forbids `pip`, `npm install/ci` and `install_sow.py`. The one action that would
close the highest-value remaining gap is the one the builder may not take. This is not a complaint
about the rule — it is a note that the gap stays open until the operator runs it, and no amount of
lane work moves it.

---

## 4. Corrections to the 2026-08-31 independent review

Verified against this tree. The PDF was explicit that it ran on a sandbox without it; these are
corrections of scope, not of care.

| PDF finding | Status at `9bd60de` |
|---|---|
| B-01 no git commit anchors the workspace | 106 commits, 0 dirty. Remains true of the Aug-27 Production Workspace snapshot. |
| B-02 provenance names the Distillery ZIP hash | Already corrected — `150e518e…ec51` |
| B-05 port 8765 served from the old copy | Served from `release-worktree/modules/tokencenter/piggybank.py` |
| B-09 Electron 31.7.7 unsupported | Locked at **43.4.1** |
| Layers 3–6 in no attached ZIP | All ten modules present in `sow-0.1.0-src.zip` |
| "the lane's last word is running" | Finished: 4,000 passed / 1 failed / 4 skipped |

**B-14 stands and has worsened.** This tree runs `qwen3:8b / granite4.2:8b / dolphin3:8b /
deepseek-r1:8b` — a third slate, different from both the package defaults and the baseline the PDF
read, with no adjacent operator decision record. Same class of drift as F-7.

Live at measurement time: shell `:5180` up, Token Center `:8765` up, Ollama `:11434` up;
SOVEREIGN, Debate, Distillery and llama.cpp down.

---

## 5. Unchanged and still decisive

`evidence/GATE-LEDGER.json`: 29 entries — 9 PASS (reviewer), 1 STOP (operator), **19 CANDIDATE
carrying `evaluated_by: null`.** No candidate gate has been evaluated by any reviewer at any point.

4,000 passing tests do not evaluate a gate. Ratification is that number, and nothing in this
document moves it.

---

BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.
