# SOVEREIGN — Run Guide

> **v3.1.2 — boot-verified end-to-end (BOOT_PROOF_03) with a UI-driven cycle proven (BOOT_PROOF_UI_01). See STATUS.md.**

SOVEREIGN is a local, multi-model reasoning engine with a web operator board.
Everything runs on your own machine; nothing is sent to the cloud except calls to
your local Ollama server.

See `PREREQUISITES.md` first for Python, Ollama, and the models you need.

---

## 1. Install

From this folder (the one containing this file):

```
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

Python 3.10 or newer is required.

## 2. Start the product

The operator UI and `/v1` API are served by one local process and one origin.
The service owns durable sessions, jobs, settings, evidence, cancellation, and
restart recovery. It binds **loopback only**.

**Prerequisite:** Node.js + npm are required only to *build* the SPA (see
`PREREQUISITES.md`). A prebuilt `ui/ui_shell/dist/` ships in the package, so an operator
without Node can skip the build and serve the prebuilt bundle directly.

From PowerShell in this folder:

```powershell
.\Start-Sovereign.ps1
```

Then open **http://127.0.0.1:5175**. Use `-NoBrowser` to skip automatic
browser launch, `-Port` to select another loopback port, or `-Workers` to set
the bounded job-worker count.

Other operator commands:

```powershell
.\Diagnose-Sovereign.ps1
.\Test-Sovereign.ps1
.\Stop-Sovereign.ps1
```

To rebuild the SPA from source (requires Node/npm):

```text
cd ui/ui_shell
npm install
npm run build
```

`python ui/adapter_service/adapter.py` is retained only as a compatibility
handoff to the same unified service. It does not start an adapter
implementation or read adapter-local configuration. `URI/app.py` is historical
code and is not a supported second product entry point.

## 3. Run a reasoning cycle (engine)

Make sure Ollama is running and the SC1 models in `PREREQUISITES.md` are pulled.
Optionally verify the models first (this also runs automatically at cycle start):

```
python cycle_runner_v3.py --check
```

Then run a cycle:

```
python cycle_runner_v3.py --topic "your research question here"
```

`cycle_runner_v3.py` is the canonical engine entrypoint. It drives the broker,
runs the multi-model debate/synthesis, arbitrates claims, and applies the **quality
gate** (plus the concurrence loop). Run `python cycle_runner_v3.py --help` to see all
options (session id, timeouts, model overrides, concurrence rounds, etc.).

**Publication is NOT part of a cycle.** `publication_gate.py` is a separate, explicit
post-cycle step you run yourself; the cycle runner never invokes it. Publication also
ships **disabled** — `corpus/domain.txt` is empty, so the gate fails closed with
`missing_domain_score` and publishes nothing until you define an authorized domain
corpus in `corpus/domain.txt`.

The engine shells out to PowerShell for the broker step (`broker_v21/broker.ps1`),
so a working `powershell`/`pwsh` is required on the host.

### What the gate scores mean (disclosure)

The gate reports `structural_completeness` and `response_elaboration`. These measure
**output form** (structure, length, bullet counts), **not truth**. Acceptance authority
rests on the **arbitration and concurrence** result. No independent truth-validation is
claimed. Any unanswered material challenges at finalization are surfaced in the
arbitration artifact (`unanswered_challenge_count` + `unanswered_challenges`), never
silently dropped.

## 4. What lives where

| Path | Purpose |
|------|---------|
| `cycle_runner_v3.py` | Engine entrypoint (runs a cycle) |
| `ui/ui_shell/` | SOVEREIGN SPA (React) — default UI; source + prebuilt `dist/` |
| `sovereign_product/server.py` | Unified loopback product service, durable API, and SPA host |
| `ui/adapter_service/` | Retired-command compatibility handoff and migration notes |
| `Start-Sovereign.ps1`, `Stop-Sovereign.ps1` | Canonical operator lifecycle |
| `synthesis/` | Live orchestrator + synthesis/voice modules |
| `broker_v21/` | Broker scripts that coordinate the debate |
| `claim_arbitrator.py`, `quality_gate.py`, `publication_gate.py` | Arbitration & gates |
| `library/config/` | Runtime configuration (policies, classifiers, thresholds) |
| `constitution/` | Constitutional rules / promotion / risk policy |
| `SYSTEM_MANIFEST.json` | Model roster and runtime thresholds |

Durable product state is stored root-relative under `runtime/`; evidence uses
portable `sovereign://` pointers. Engine artifacts continue to use their
component-owned root-relative output folders.

## 5. Deployment model

SOVEREIGN is a **run-from-folder source application**, not a pip-installable library.
To deploy: **extract this ZIP and run from the folder** as above. The included
`pyproject.toml` builds a wheel for tooling/inspection only — **the wheel is not the
deployment artifact and is not a runnable release.** Install dependencies from the
pinned `requirements.txt` (see Install above) so two operators get the same stack.
