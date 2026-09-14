# Debate Table — Enterprise Production Copy

This package is Debate Table **v1.2.1-hardening**, derived from the verified
v1.2 Phase 1 production copy (Git commit `d7be33579c0f986db74c0b221b5bdf06a9d280df`).
The debate engine concept, single-process architecture, prompts, personas and
frontend design are unchanged (`core_architecture_changed: false`); production
hardening changed runtime code, configuration validation, control-plane security
and diagnostics (`hardening_code_changed: true`). The frozen acceptance contract
for this release is recorded in the accompanying defect register.

## Requirements

- Windows 10 or 11 (Windows 11 was used for release verification)
- Python 3.14.6 (the tested interpreter; the project declares Python 3.10+)
- Ollama running locally at `http://127.0.0.1:11434`
- `phi4:14b` and `qwen2.5:14b-instruct` installed in Ollama
- A modern browser
- Sufficient RAM or VRAM for the selected 14B models

Model weights are not included. Install the required models yourself if needed:

```powershell
ollama pull phi4:14b
ollama pull qwen2.5:14b-instruct
```

`config.json` also names `dolphin-llama3:8b` as the extractor model, but it is not
required while the default `insight_panel` setting remains `false`.

## Installation

Open PowerShell in this extracted folder and run the verified bootstrap:

```powershell
.\scripts\bootstrap.ps1
```

The bootstrap creates `.venv`, installs the pinned Windows dependency closure from
`requirements.lock.txt`, installs pytest for the offline self-check, checks Ollama,
and reports missing required models. It does not download models or edit
`config.json`.

For a runtime-only manual installation:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

## Startup

```powershell
.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:8700`. The application deliberately binds only to localhost.
Stop it with `Ctrl+C` in the PowerShell window.

Press `C` while the Debate Table browser page has focus to open the operator drawer.

## v1.2.1-hardening security and operations

- **Local control plane**: HTTP Host must be a loopback host on the configured
  port; WebSocket handshakes with a foreign `Origin` are rejected before any
  snapshot is sent; state-changing POST routes reject cross-site browser
  invocations. Non-browser tooling (which sends no Origin) is permitted by the
  explicit `allow_originless_ws_clients` setting (default `true`); set it to
  `false` to require loopback origins even for local scripts.
- **Ollama endpoint policy**: traffic defaults to loopback only
  (`127.0.0.1`, `localhost`, `::1`). A non-loopback `ollama_url` is refused at
  startup unless you deliberately set `"allow_remote_ollama": true`; when
  enabled, warnings are logged and `/ready` reports `endpoint_class: remote`.
  Remote mode means the local-first privacy property no longer applies.
- **Private-control guard semantics**: the output guard is a best-effort
  anti-echo / output-sanitization mechanism. It is NOT a confidentiality
  boundary and cannot guarantee that a model will not paraphrase information
  included in its context. Long operator values are blocked verbatim anywhere
  in public speech; very short values are deliberately not registered.
- **Turn accounting**: every attempted turn resolves to an explicit outcome
  (`completed`, skipped by generation error / empty public response /
  interruption / protocol fault). Only completed turns advance topic rotation
  and anchor cadence; a failed or truncated stream never masquerades as a
  finished turn (EOF without Ollama's terminal `done` frame is rejected).
- **Payload limits** (backend-enforced, reflected as frontend `maxlength`
  attributes): public title 300, debate brief 20000, seat name 100, model name
  200, persona 4000, thesis 8000, interjection 4000, revision reason 2000
  characters. The inert `min_turn_chars` knob was removed in this release.
- **Health and readiness**: `GET /health` reports process liveness; `GET
  /ready` probes Ollama reachability and installed seat models (503 when
  degraded/unavailable). Neither exposes prompts or interjections.
- **Structured logs**: bounded rotating JSONL at `logs/debate.log` (override
  directory with `DEBATE_LOG_DIR`; 1 MiB x 3 backups). Turn lifecycle events
  only - prompts and interjections are never logged.
- **Single-worker invariant**: Debate Table is a single-process, single-worker
  stateful application. Do not run multiple Uvicorn workers; per-client
  WebSocket queues already isolate slow browsers without worker parallelism.

## Voice status

Local Voice / TTS is not included in this production copy.
This package represents the completed v1.2 Phase 1 text application before Voice
Phase 2.

## Package scope

Included are the current runtime, frontend, configuration, dependency declarations,
bootstrap and environment-capture scripts, snapshot provenance, restore runbook, and
the complete offline test suite. Deliberately omitted are Git metadata, virtual
environments, Python and pytest caches, historical archives, audit and soak logs,
research spikes and embedding caches, superseded directives, editor state, scratch
directories, temporary logs, and local Ollama model storage. These omissions do not
change the packaged application engine.

## Verification

First verify the ZIP with the adjacent `.zip.sha256` file. In PowerShell:

```powershell
Get-FileHash .\Debate_Table_v1.2_Phase1_Production_*.zip -Algorithm SHA256
Get-Content .\Debate_Table_v1.2_Phase1_Production_*.zip.sha256
```

After extraction, verify every packaged file against `MANIFEST-SHA256.json`:

```powershell
python -c "import hashlib,json,pathlib,sys; r=pathlib.Path('.'); m=json.loads((r/'MANIFEST-SHA256.json').read_text(encoding='utf-8')); bad=[e['path'] for e in m['files'] if not (r/e['path']).is_file() or (r/e['path']).stat().st_size != e['size'] or hashlib.sha256((r/e['path']).read_bytes()).hexdigest() != e['sha256']]; print(f'{len(m[\"files\"])} files checked; {len(bad)} mismatches'); print(*bad, sep='\n'); sys.exit(bool(bad))"
```

The manifest intentionally does not hash itself. It covers every other file in the
application folder. Paths use forward slashes and are sorted deterministically.

Check the environment and run the offline test suite:

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -m pytest tests -q -W error
```

The release baseline is the original 84 tests plus 97 hardening regression tests: `181 passed`, `0 failed`. The original 84 remain untouched in both letter and count. The tests use a local
mock Ollama service and do not invoke the installed models. See
`SNAPSHOT-RESTORE.md` for the historical baseline restore record and additional
operational detail.
