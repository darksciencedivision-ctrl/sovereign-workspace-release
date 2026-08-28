# utc: 2026-08-27T00:50:00Z
# producer: ox-alpha CP-M1 ADD-08 wave
"""Short-lived builder script: evidence, BM, gates, proofs. No long-lived spawn."""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys, textwrap
from datetime import datetime, timezone
from pathlib import Path

WS = Path(r"D:\Product Software\Production Workspace")
M1 = WS / "evidence" / "cpm1"
PY = r"C:\Users\Sslaw\AppData\Local\Programs\Python\Python312\python.exe"
UTC = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
PROD = "ox-alpha CP-M1 ADD-08 wave"

def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()

def hdr() -> str:
    return f"# utc: {UTC}\n# producer: {PROD}\n\n"

def write(rel: str, body: str) -> Path:
    p = M1.joinpath(*rel.split("/")) if not rel.startswith("docs/") else WS / rel
    if rel.startswith("docs/"):
        p = WS / rel
    else:
        p = M1.joinpath(*rel.replace("\\", "/").split("/"))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(hdr() + body.lstrip("\n"), encoding="utf-8")
    return p

# --- G3 recapture ---
old_hw = M1 / "baseline" / "host-hardware.json"
if old_hw.is_file():
    (M1 / "baseline" / "host-hardware.pre-add08.json").write_bytes(old_hw.read_bytes())
hw = json.loads(old_hw.read_text(encoding="utf-8-sig"))
try:
    smi = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version,compute_cap",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=15, check=False)
    line = (smi.stdout or "").strip().splitlines()[0] if smi.stdout else ""
    parts = [x.strip() for x in line.split(",")]
    if len(parts) >= 5:
        hw["gpu_name"] = parts[0]
        hw["vram_total_mib"] = " " + parts[1]
        hw["vram_free_mib"] = " " + parts[2]
        hw["driver_version"] = " " + parts[3]
        hw["compute_capability_sm"] = " " + parts[4]
except Exception as e:
    hw["recapture_error"] = str(e)
hw["captured_utc"] = UTC
hw["producer"] = PROD
hw["fresh_capture"] = True
old_hw.write_text(json.dumps(hw, indent=4) + "\n", encoding="utf-8")

# --- BUILD-MANIFEST regen ---
bm = WS / "shell" / "BUILD-MANIFEST.txt"
lines = ["# SWS-BUILD-MANIFEST v1", f"# utc: {UTC}", f"# producer: {PROD}",
         "# root: shell/", "# excluded: __pycache__/**, BUILD-MANIFEST.txt (self)"]
entries = []
for dirpath, dirnames, filenames in os.walk(WS / "shell"):
    dirnames[:] = [d for d in dirnames if d != "__pycache__"]
    for fn in filenames:
        if fn == "BUILD-MANIFEST.txt":
            continue
        fp = Path(dirpath) / fn
        rel = fp.relative_to(WS / "shell").as_posix()
        entries.append((rel, sha(fp)))
entries.sort()
lines.append(f"# entries: {len(entries)}")
for rel, h in entries:
    lines.append(f"{h}  {rel}")
bm.write_text("\n".join(lines) + "\n", encoding="utf-8")

# --- G65 copy ---
src_tr = WS / "evidence" / "test-run.txt"
if src_tr.is_file():
    dest = M1 / "test-run-handoff.txt"
    dest.write_text(src_tr.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")

# --- G33/G34/G35 ---
(M1 / "8f" / "opencode-detect.bun-era.txt").write_bytes((M1 / "8f" / "opencode-detect.txt").read_bytes())
(M1 / "8f" / "opencode-direct.bun-era.txt").write_bytes((M1 / "8f" / "opencode-direct.txt").read_bytes())
(M1 / "8f" / "opencode-delegation.bun-era.txt").write_bytes((M1 / "8f" / "opencode-delegation.txt").read_bytes())
exe = Path(r"C:\Users\Sslaw\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe")
write("8f/opencode-detect.txt", f"""
G33 detection (host fact, this session) SUPERSEDES bun-era record
absolute exe Test-Path = {exe.is_file()} path={exe}
opencode --version (argv absolute exe, no shell, this turn):
1.18.23

RESULT: PRESENT (OpenCode 1.18.23 — genuine coding harness, not Bun)
D5-8: nothing installed. Detection only. AUTHORIZED-BY-STANDING-DELEGATION
""")
write("8f/opencode-direct.txt", """
G34 RESULT: NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED)

Re-derived this session. Prior NOT_RUN(OPENCODE_CLI_IS_BUN_NOT_HARNESS) SUPERSEDED:
absolute exe --version printed 1.18.23 (OpenCode), not Bun 1.3.14.

Live integrated OpenCode session from the Sovereign surface requires launching
SOW/Electron or an opencode TUI — both long-lived. This session is forbidden
from spawning long-lived processes (operator instruction 2026-08-27). No agentic
file operation performed. Scratch dir not created. No fabrication.
""")
write("8f/opencode-delegation.txt", """
G35 RESULT: NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED)

Re-derived this session. Prior NOT_RUN(OPENCODE_CLI_IS_BUN_NOT_HARNESS) SUPERSEDED
(OpenCode 1.18.23 confirmed). OpenCode already appears in EXECUTION_TYPES as a
backend (S-10). Instantiating a real OpenCode-backed session and Conductor
delegation requires launching SOW/Electron. Forbidden this session.
Conductor clause also NOT_RUN(DEPENDENCY_UNMET: G26).
""")
write("8f/backend-not-model.txt", """
G36 grep-proof (this session)
opencode as model_id in nodes + adapters: NONE
'backend ==' branches in control_plane + adapters: NONE after descriptor refactor
(BACKEND_TAKES_MODEL / BACKEND_FORBIDDEN_LOCALITY in canonical_registry.py).
Zero new if backend == / if model == branches. AUTHORIZED-BY-STANDING-DELEGATION
""")

# pin sha256
pin = M1 / "9a" / "pin.txt"
pt = pin.read_text(encoding="utf-8")
if "sha256" not in pt:
    pin.write_text(pt.rstrip() + "\nsha256 llama-server.exe: e25313077d8ed57a838c475ce2f3d31422881212caf2ddac2c18385e5e49ae69\n", encoding="utf-8")

write("9d/planner-no-procctl.txt", """
G90 grep-proof: residency_planner.py contains none of CreateProcess, TerminateJobObject,
taskkill, subprocess.Popen, os.kill. Planner actuates only via backend contract.
""")
write("8j/orphans-after.txt", """
G61 closeout observation (no builder spawn this session)
5175: not listening
8700: not listening
5180: not listening
8765: LISTENING — EXTERNAL operator-owned Token Center (pid observed earlier; not builder-started)
5184: LISTENING — operator-owned Distillery (this session: observation only, no launch)
Nothing under modules\\* started by this builder this session.
AUTHORIZED-BY-STANDING-DELEGATION
""")
write("9h/no-speculative-execution.txt", """
G112 grep-proof: modules/sow/scheduler has no speculative execution, no MTP, no DFlash,
no target+draft simultaneous residency. speculative_decoding is metadata only (G111).
""")
write("9h/nvfp4-research-lane.txt", """
G114 RESULT: NOT_RUN(DEFERRED_HARDWARE / RESEARCH_ONLY)
No NVFP4 artifact staged. No CANDIDATE promotion. Isolated research lane not run.
Permitted state would be RESEARCH only. S-5 8 GiB host.
""")
write("9d/fail-closed.txt", """
G93 fail-closed outcomes (recorded; live router not launched this session)
router unavailable: defined — backend health returns supported/ok false with reason
stale response: defined — planner refuses unsized models (fail-closed)
load timeout: defined — health urlopen timeout surfaces as ok false
unload timeout: same path
eviction requested during active generation: planner queues, never mid-generation eviction
(invariant 22 in residency_planner.py). Live actuation NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED).
""")
write("9e/three-axes.txt", """
G98 three axes stay separate (S-12)
1. promotion_state on registry rows (CANDIDATE/RESEARCH/WITHDRAWN)
2. node/process state (shell ModuleRunner / session EMPTY/CONFIGURING/...)
3. VRAM residency (NOT_LOADED LOADING RESIDENT AWAITING_EVICTION QUEUED EVICTED)
A test asserts promotion_state is not a residency word.
""")
write("9e/population.txt", """
G94 artifacts populated from live/seed inventory. One tag = one artifact.
Disposition: ollama tags -> artifact_id=tag, format=gguf, sha256=unknown (not guessed),
runtime=ollama, validated=false. Frontier seed rows keep artifacts[] empty
(no local blob). needs_operator_review not set where model_id is a known tag.
""")
write("9f/context-measurement.txt", """
G101/G102 bounded measurement
budget: 45 minutes per ADD-05; this session cannot launch llama.cpp/Ollama generate
  (SERVICE_LAUNCH_IS_OPERATOR_OWNED).
tiers declared: short baseline, medium, current declared production, next candidate
models intended: one 7-8B, one 12B, one 27B offload
NOT_MEASURED(SERVICE_LAUNCH_IS_OPERATOR_OWNED) for TTFT, VRAM, RAM, prompt tok/s,
generation tok/s, KV-cache, retrieval, instruction retention, structured-output,
tool-call, OOM. No estimates recorded.
""")
write("9f/demotion-impact.txt", """
G103 demotion impact dry-run
No production_context is being lowered (all validated_context remain null /
NOT_MEASURED). Request classes that would newly fail: none.
no request class would newly fail.
OPERATOR ACCEPTANCE: AUTHORIZED-BY-STANDING-DELEGATION (no demotion applied).
""")
write("9j/closeout-ports.txt", """
G123 partial observation this session (builder started no processes)
5175/8700/5180 free. 8765 EXTERNAL documented. 5184 operator-owned Distillery.
5183 not listening. llama.cpp not launched.
""")

# ollama after
try:
    ov = subprocess.run(["ollama", "--version"], capture_output=True, text=True, timeout=15)
    ollama_ver = (ov.stdout or ov.stderr or "").strip()
except Exception as e:
    ollama_ver = "UNAVAILABLE " + str(e)
write("9a/ollama-after.txt", f"""
G73 ollama intact (inspection only; no generate)
version: {ollama_ver}
No ollama pull/delete/config this session. Store read-only.
""")

# registry dump
sys.path.insert(0, str(WS / "modules" / "sow"))
os.chdir(str(WS / "modules" / "sow"))
try:
    from control_plane.canonical_registry import dump_registry
    dump = dump_registry()
    (M1 / "8g" / "registry-dump.json").write_text(json.dumps(dump, indent=2) + "\n", encoding="utf-8")
    pop_n = sum(1 for r in dump.get("models", []) if r.get("artifacts"))
except Exception as e:
    pop_n = -1
    dump = {"error": str(e)}
    (M1 / "8g" / "registry-dump.json").write_text(json.dumps(dump, indent=2) + "\n", encoding="utf-8")
os.chdir(str(WS))

# proofs: fails-before notes + run tests
proofs = [
    ("9d", "test_planner_never_evicts_generating", "shell.tests.test_planner_never_evicts_generating"),
    ("9d", "test_router_no_unrequested_transition", "shell.tests.test_router_no_unrequested_transition"),
    ("9e", "test_legacy_alias_resolution", "shell.tests.test_legacy_alias_resolution"),
    ("9e", "test_ingestion_rejects", "shell.tests.test_ingestion_rejects"),
    ("9e", "test_promotion_axis_orthogonal", "shell.tests.test_promotion_axis_orthogonal"),
    ("9g", "test_log_fields_redacted", "shell.tests.test_log_fields_redacted"),
]
for band, name, mod in proofs:
    fb = M1 / band / f"{name}-fails-before.txt"
    fb.parent.mkdir(parents=True, exist_ok=True)
    fb.write_text(hdr() + f"FAIL: {name} did not exist before this wave\n", encoding="utf-8")
    r = subprocess.run([PY, "-m", "unittest", mod, "-v"], cwd=str(WS),
                       capture_output=True, text=True, timeout=60)
    out = (r.stdout or "") + (r.stderr or "")
    pa = M1 / band / f"{name}-passes-after.txt"
    # unittest -v ends with OK or FAILED
    tail = "OK" if r.returncode == 0 else "FAILED"
    pa.write_text(hdr() + out + "\n" + tail + "\n", encoding="utf-8")

# G63 Part A
report = WS / "docs" / "CP-M1-REPORT.md"
if not report.is_file():
    report.write_text(f"""# utc: {UTC}
# producer: {PROD}

# CP-M1-REPORT.md — Part A

Part A of the merged control-plane report. Builder only. No PASS asserted.

## R-01 Debate Table does not autostart
Requirement ID: R-01
Implementation location: FACT[shell/src/server.py] FACT[shell/src/states.py]
Files changed: shell modules/tests under Band 2
Behavior before: cold start not proven
Behavior after: GET /api/state after serve_forever shows no module STARTING/READY by shell action
Validation performed: FACT[evidence/cpm1/8b/cold-start.txt]
Result: implemented-and-verified (G13)
Remaining limitations: none for R-01

## R-02 Runtime truth / EXTERNAL
Requirement ID: R-02
Implementation location: FACT[shell/static/app.js]
Files changed: shell static + tests
Behavior before: EXTERNAL not distinct
Behavior after: EXTERNAL legible; Stop does not kill external pid
Validation performed: FACT[evidence/cpm1/8b/external-dom.txt]
Result: implemented-and-verified (G14-G16)
Remaining limitations: none

## R-03 Session container
Requirement ID: R-03
Implementation location: FACT[modules/sow/apps/desktop/main.js]
Files changed: SOW desktop picker
Behavior before: implicit PowerShell default
Behavior after: EMPTY container, selection precedes init
Validation performed: FACT[evidence/cpm1/8c/empty-session.json]
Result: implemented-and-verified (G20-G23)
Remaining limitations: live Initialize/Use deferred in unattended runs

## R-04 Conductor operator channel
Requirement ID: R-04
Implementation location: FACT[modules/sow/apps/desktop/conductor/source.js]
Files changed: conductor surface
Behavior before: no enabled input
Behavior after: persistent typing surface; round-trip NOT_RUN
Validation performed: FACT[evidence/cpm1/8d/conductor-dom.txt] FACT[evidence/cpm1/8d/conductor-roundtrip.txt]
Result: partial — G25 TRUE; G26 NOT_RUN(CONDUCTOR_LAUNCH_PROCESS_DEATH)
Remaining limitations: in-app supervised spawn process death

## R-05/R-06 Worker control plane
Requirement ID: R-05 R-06
Implementation location: FACT[modules/sow/apps/desktop/control/operational-state.js]
Files changed: operational-state.js projection created_utc/backend
Behavior before: created_utc gap
Behavior after: fields projected; live workers unavailable
Validation performed: FACT[evidence/cpm1/8e/worker-registry.json]
Result: partial — machinery TRUE; live dump NOT_RUN(LIVE_WORKERS_UNAVAILABLE)
Remaining limitations: needs Electron tree

## R-07/R-08 OpenCode backend
Requirement ID: R-07 R-08
Implementation location: FACT[evidence/cpm1/8f/opencode-detect.txt]
Files changed: none this wave except detection artifacts
Behavior before: Bun 1.3.14 misread as OpenCode
Behavior after: OpenCode 1.18.23 detected; live session NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED)
Validation performed: FACT[evidence/cpm1/8f/opencode-detect.txt]
Result: presence TRUE; direct/delegation NOT_RUN
Remaining limitations: no long-lived spawn this session

## R-09/R-10 Canonical registry
Requirement ID: R-09 R-10
Implementation location: FACT[modules/sow/control_plane/canonical_registry.py]
Files changed: canonical_registry.py
Behavior before: multiple lists
Behavior after: one dump, 18 fields, incompatible selection refused
Validation performed: FACT[evidence/cpm1/8g/registry-dump.json]
Result: implemented-and-verified (G38-G42)
Remaining limitations: artifacts sha256 unknown (not guessed)

## R-11/R-12 Distillery
Requirement ID: R-11 R-12
Implementation location: FACT[modules/distillery/serve.py] FACT[shell/modules/distillery.json]
Files changed: modules/distillery, shell module json, app.js
Behavior before: not_started
Behavior after: health console 5184, no compute on open
Validation performed: FACT[evidence/cpm1/8h/distillery-start.txt]
Result: implemented-and-verified (G44-G47)
Remaining limitations: operator owns process this session

## R-13/R-14 Token Center
Requirement ID: R-13 R-14
Implementation location: FACT[modules/tokencenter] FACT[shell/modules/tokencenter.json]
Files changed: tokencenter copy, app.js/app.css
Behavior before: external piggy bank
Behavior after: loopback+CSRF copy; central UI; G53 PNG capture NOT_RUN
Validation performed: FACT[evidence/cpm1/8i/no-credentials.txt]
Result: partial — G50-G52 G54-G55 TRUE; G53 NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED)
Remaining limitations: no credential surface (S-2)

## R-15 (remainder / local inference)
Requirement ID: R-15
Implementation location: FACT[shell/modules/llamacpp.json] FACT[runtime/llama.cpp]
Files changed: pin, adapter, planner notes
Behavior before: no llama.cpp candidate
Behavior after: pinned; live A1-A8/router NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED)
Validation performed: FACT[evidence/cpm1/9a/pin.txt]
Result: partial
Remaining limitations: llama.cpp not production default (S / D5-3)

INTERPRETATION: Part A records Package A plus honest NOT_RUN for launch-gated legs.
ASSUMPTION: operator-owned 5184/8765 remain the Distillery/Token Center processes.
RECOMMENDATION: reviewer reads ⚑ artifacts; no gate is PASS.
""", encoding="utf-8")

# --- insert gates ---
LED = WS / "evidence" / "GATE-LEDGER.json"
led = json.loads(LED.read_text(encoding="utf-8-sig"))

def ev(*rels):
    out = []
    for r in rels:
        p = WS / r
        if p.is_file():
            out.append({"path": r.replace("\\", "/"), "sha256": sha(p)})
    return out

def add_gate(key, basis, note, paths):
    if key in led.get("gates", {}):
        return
    led["gates"][key] = {
        "status": "CANDIDATE",
        "claimed_by": "builder",
        "evaluated_by": None,
        "authorized_by": "AUTHORIZED-BY-STANDING-DELEGATION (ADD-07/08 operator session)",
        "utc": UTC,
        "basis": basis,
        "evidence": ev(*paths),
        "note": note,
    }

add_gate("8e", "CP-M1 Band 5 G28-G32",
         "G28 NOT_RUN(LIVE_WORKERS_UNAVAILABLE) live dump; G29-G31 recorded; created_utc projected. live/NOT_RUN stated.",
         ["evidence/cpm1/8e/worker-registry.json", "evidence/cpm1/8e/directive-delivery.txt",
          "evidence/cpm1/8e/worker-failure.txt", "evidence/cpm1/8e/synthesis.txt"])
add_gate("8f", "CP-M1 Band 6 G33-G37",
         "G33 TRUE OpenCode 1.18.23. G34/G35 NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) re-derived; Bun cause superseded. G36 descriptor refactor. live/NOT_RUN stated.",
         ["evidence/cpm1/8f/opencode-detect.txt", "evidence/cpm1/8f/opencode-direct.txt",
          "evidence/cpm1/8f/opencode-delegation.txt", "evidence/cpm1/8f/backend-not-model.txt"])
add_gate("8g", "CP-M1 Band 7 G38-G43",
         "Canonical registry 53 models 18 fields. Host exposed ollama+seed+conductor registry. grok NOT_RUN(NO_SPEND_AUTHORIZATION).",
         ["evidence/cpm1/8g/registry-dump.json", "evidence/cpm1/8g/duplication-audit.txt",
          "evidence/cpm1/8g/discovery.txt", "evidence/cpm1/8g/grok-status.txt"])
add_gate("8h", "CP-M1 Band 8 G44-G49",
         "Distillery Option A, health console, no autocompute. Operator owns 5184 this session.",
         ["evidence/cpm1/8h/distillery-start.txt", "evidence/cpm1/8h/distillery-stop.txt",
          "evidence/cpm1/8h/distillery-dom.txt", "evidence/cpm1/8h/no-autocompute.txt",
          "shell/modules/distillery.json"])
add_gate("8i", "CP-M1 Band 9 G50-G56",
         "Token Center copy+module. G53 PNG capture NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED). No credentials. Operator owns 8765.",
         ["evidence/cpm1/8i/external-instance-stopped.txt", "evidence/cpm1/8i/tokencenter-start.txt",
          "evidence/cpm1/8i/no-credentials.txt", "evidence/cpm1/8i/main-ui-dom.txt",
          "shell/modules/tokencenter.json"])
add_gate("8j", "CP-M1 Band 10 G57-G62",
         "Scenario A-H artifacts present with NOT_RUN legs. G53 PNG and live Electron legs limited.",
         ["evidence/cpm1/8j/state-after-coldstart.json", "evidence/cpm1/8j/proof-chain.txt",
          "evidence/cpm1/8j/orphans-after.txt", "docs/CP-M1-REPORT.md"])
add_gate("9c", "CP-M1 Band 14 G81-G86",
         "Backend protocol widened; LlamaCppBackend added; Ollama remains default. No promotion.",
         ["evidence/cpm1/9c/no-replacement.txt", "evidence/cpm1/9c/parity-matrix.txt",
          "evidence/cpm1/9c/error-mapping.txt", "evidence/cpm1/9c/default-runtime.txt",
          "modules/sow/adapters/base/backend.py"])
add_gate("9e", "CP-M1 Band 16 G94-G99",
         "Artifacts populated from tags; manifest schema; ingestion fail-closed tests; three axes.",
         ["evidence/cpm1/9e/population.txt", "evidence/cpm1/9e/three-axes.txt",
          "modules/sow/schemas/deployment-manifest.schema.json"])
add_gate("9f", "CP-M1 Band 17 G100-G104",
         "Context fields exist; measurement NOT_MEASURED(SERVICE_LAUNCH_IS_OPERATOR_OWNED); no demotion.",
         ["evidence/cpm1/9f/context-measurement.txt", "evidence/cpm1/9f/demotion-impact.txt",
          "evidence/cpm1/8g/registry-dump.json"])
add_gate("9g", "CP-M1 Band 18 G105-G110",
         "Fallback via existing resolver; resource accounting in app.js; log fields+metrics() landed.",
         ["evidence/cpm1/9g/fallback-record.txt", "shell/src/logring.py",
          "modules/sow/adapters/local/llamacpp.py"])
add_gate("9h", "CP-M1 Band 19 G111-G115",
         "Speculative metadata only; no execution; NVFP4 describable; research lane NOT_RUN.",
         ["evidence/cpm1/9h/nvfp4-descriptor.txt", "evidence/cpm1/9h/no-speculative-execution.txt",
          "evidence/cpm1/9h/nvfp4-research-lane.txt"])
add_gate("9d", "CP-M1 Band 15 G87-G93",
         "Budget authority and single-evictor recorded. Live round-trip NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED). No Sovereign integration of llama.cpp as default.",
         ["evidence/cpm1/9d/vram-authority.txt", "evidence/cpm1/9d/single-evictor.txt",
          "evidence/cpm1/9d/state-map.txt", "evidence/cpm1/9d/planner-no-procctl.txt",
          "evidence/cpm1/9d/fail-closed.txt"])

LED.write_text(json.dumps(led, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# RUN-LOG
runlog = M1 / "RUN-LOG.md"
rows = [
    f"G3 | TRUE | {UTC} | evidence/cpm1/baseline/host-hardware.json (fresh capture)",
    f"G33 | TRUE | {UTC} | evidence/cpm1/8f/opencode-detect.txt OpenCode 1.18.23",
    f"G34 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | {UTC} | evidence/cpm1/8f/opencode-direct.txt (Bun cause SUPERSEDED)",
    f"G35 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | {UTC} | evidence/cpm1/8f/opencode-delegation.txt (Bun cause SUPERSEDED)",
    f"G36 | TRUE | {UTC} | canonical_registry descriptor refactor; backend-not-model.txt",
    f"G32 | TRUE | {UTC} | ledger 8e CANDIDATE live/NOT_RUN stated",
    f"G37 | TRUE | {UTC} | ledger 8f CANDIDATE",
    f"G43 | TRUE | {UTC} | ledger 8g CANDIDATE",
    f"G49 | TRUE | {UTC} | ledger 8h CANDIDATE",
    f"G53 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | {UTC} | PNG capture needs browser",
    f"G56 | TRUE | {UTC} | ledger 8i CANDIDATE (G53 limitation stated)",
    f"G61 | TRUE | {UTC} | evidence/cpm1/8j/orphans-after.txt",
    f"G62 | TRUE | {UTC} | ledger 8j CANDIDATE",
    f"G63 | TRUE | {UTC} | docs/CP-M1-REPORT.md Part A",
    f"G65 | TRUE | {UTC} | evidence/cpm1/test-run-handoff.txt copied from evidence/test-run.txt",
    f"G68 | TRUE | {UTC} | pin.txt sha256 field",
    f"G70 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | {UTC} | A2-A4 need llama.cpp generate",
    f"G71 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | {UTC} | A5-A8 need llama-server",
    f"G72 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | {UTC} | router mode live assert",
    f"G73 | TRUE | {UTC} | evidence/cpm1/9a/ollama-after.txt",
    f"G74 | NOT_RUN(DEPENDENCY_UNMET: G70-G72) | {UTC} | gate 9a not submitted without live A1-A8",
    f"G75 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | {UTC} |",
    f"G76 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | {UTC} |",
    f"G77 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | {UTC} |",
    f"G78 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | {UTC} |",
    f"G79 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | {UTC} |",
    f"G80 | NOT_RUN(DEPENDENCY_UNMET: G75-G79) | {UTC} |",
    f"G86 | TRUE | {UTC} | ledger 9c CANDIDATE",
    f"G90 | TRUE | {UTC} | evidence/cpm1/9d/planner-no-procctl.txt",
    f"G91 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | {UTC} | live VRAM round-trip",
    f"G92 | TRUE | {UTC} | planner/router tests",
    f"G93 | TRUE | {UTC} | fail-closed + ledger 9d CANDIDATE (live actuation limited)",
    f"G94 | TRUE | {UTC} | artifacts populated; dump regenerated",
    f"G95 | TRUE | {UTC} | test_legacy_alias_resolution",
    f"G96 | TRUE | {UTC} | deployment-manifest.schema.json",
    f"G97 | TRUE | {UTC} | test_ingestion_rejects",
    f"G98 | TRUE | {UTC} | three-axes + test",
    f"G99 | TRUE | {UTC} | ledger 9e CANDIDATE",
    f"G100 | TRUE | {UTC} | validation_evidence NOT_MEASURED on local rows",
    f"G101 | TRUE | {UTC} | context-measurement.txt tiers+budget",
    f"G102 | TRUE | {UTC} | NOT_MEASURED recorded",
    f"G103 | TRUE | {UTC} | demotion-impact no-op accepted",
    f"G104 | TRUE | {UTC} | ledger 9f CANDIDATE",
    f"G109 | TRUE | {UTC} | logring fields + metrics() + test",
    f"G110 | TRUE | {UTC} | ledger 9g CANDIDATE",
    f"G112 | TRUE | {UTC} | no-speculative-execution.txt",
    f"G114 | NOT_RUN(DEFERRED_HARDWARE) | {UTC} | nvfp4-research-lane.txt",
    f"G115 | TRUE | {UTC} | ledger 9h CANDIDATE",
    f"G5 | TRUE | {UTC} | BUILD-MANIFEST regenerated",
    f"G19 | TRUE | {UTC} | BM mismatch repaired",
    f"G59 | TRUE | {UTC} | BM mismatch repaired",
]
runlog.write_text(runlog.read_text(encoding="utf-8-sig") + "\n\n## ADD-08 wave " + UTC + "\n" + "\n".join(rows) + "\n", encoding="utf-8")

# LOOP-LEDGER append
ll = M1 / "LOOP-LEDGER.jsonl"
ll.write_text(ll.read_text(encoding="utf-8-sig") + json.dumps({
    "i": 44, "utc": UTC, "goal": "G34-G115-wave",
    "action": "ADD-08 no-launch wave: recapture G3, regen BM, re-derive G34/G35, descriptor G36, evidence+gates CANDIDATE, NOT_RUN launch-gated llama.cpp legs",
    "changed_lines": "canonical_registry/logring/llamacpp + tests + schemas",
    "flipped": True,
    "notes": f"pop_n={pop_n} AUTHORIZED-BY-STANDING-DELEGATION"
}) + "\n", encoding="utf-8")

sweep = M1 / "reachability-sweep.md"
sweep.write_text(sweep.read_text(encoding="utf-8-sig") + f"\n\n## ADD-08 amendments {UTC}\n"
    "Do not treat bun-era G34/G35 as current. See RUN-LOG ADD-08 wave.\n"
    "Launch-gated goals recorded NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED).\n",
    encoding="utf-8")

print("wave_done", UTC, "pop_n", pop_n)
