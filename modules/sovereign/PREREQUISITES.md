# SOVEREIGN — Prerequisites

SOVEREIGN runs entirely on your machine. You need three things: Python, a running
Ollama server, and the model set below.

---

## 1. Python

- **Python 3.12** — the workspace-pinned interpreter (`py -3.12`). The `pyproject.toml` source floor is 3.10, but the workspace runs and tests on 3.12.
- Install runtime dependencies with `pip install -r requirements.txt`
  (flask, requests, chromadb, numpy, pydantic).

## 2. Ollama

- Install Ollama and make sure it is running and reachable at:
  **`http://127.0.0.1:11434`**  (the default).
- This URL is configured in `SYSTEM_MANIFEST.json` under `RUNTIME.OLLAMA_BASE_URL`.
  If your Ollama runs elsewhere, update that value.

## 3. Models to pull

The engine uses a fixed roster of local models (the SC1 slate, defined in
`SYSTEM_MANIFEST.json`). Pull each one before running a cycle — the exact tags must
match the manifest:

```
ollama pull qwen2.5:14b-instruct    # PRIMARY_REASONER
ollama pull dolphin-llama3:8b       # ADVERSARIAL_CHALLENGER
ollama pull qwen3:14b               # CRITIC
ollama pull dolphin3:8b             # SYNTHESIZER
ollama pull nomic-embed-text:latest # EMBEDDING_MODEL
```

**VRAM note:** this slate includes **two 14B models** (qwen2.5:14b-instruct and qwen3:14b),
a heavier footprint than an all-8B roster. In testing it ran on an **8 GB** card (the
models load one at a time), but expect model-swap latency on smaller cards.
`qwen2.5:14b-instruct` has the same ~9 GB footprint as the prior `deepseek-r1:14b`
reasoner, so this default carries no VRAM regression.

**Alternate profile (SC1 benchmark slate):** the prior reasoner **`deepseek-r1:14b`**
remains a documented alternate for the SC1 two-14B benchmark slate. To run it, set
`MODELS.PRIMARY_REASONER` in `SYSTEM_MANIFEST.json` and the four `deepseek-r1:14b`
roles in `synthesis/model_hierarchy.json` (ALPHA_ADVOCATE, ALPHA_RECONCILER,
CLU_ANALYZER, CLU_BENCHMARK) back to `deepseek-r1:14b`. Note SC1 does not reliably
satisfy the strict debate contract on this host (see `STATUS.md`); it is retained for
benchmark comparison, not as the shipped default.

The cycle runner performs a **startup preflight** that checks these models are present
in `ollama list` and errors before starting if any are missing. You can run the check
on its own:

```
python cycle_runner_v3.py --check
```

## 4. PowerShell (Windows) / pwsh

The engine's broker step runs a PowerShell script (`broker_v21/broker.ps1`).
On Windows this uses the built-in `powershell`. On macOS/Linux install PowerShell
(`pwsh`) if you intend to run full engine cycles. The web board (`URI/app.py`)
does **not** require PowerShell.

## 5. Node.js + npm (UI build — build-time only)

The default UI (the SOVEREIGN SPA under `ui/ui_shell/`) is built with **Node.js 18+
and npm**. This is a **build-time** prerequisite only: the package ships a prebuilt
`ui/ui_shell/dist/`, so an operator without Node can serve the prebuilt bundle and skip
the build entirely. To rebuild from source:

```
cd ui/ui_shell
npm install
npm run build      # tsc -b && vite build -> dist/
```

The Python unified service requires the runtime dependencies listed above. It
serves the prebuilt SPA and `/v1` API from the same loopback origin. The legacy
`ui/adapter_service/adapter.py` command forwards to that service and does not
have separate dependencies or configuration.

## 6. Product port

The unified product defaults to `127.0.0.1:5175`. If that port is reserved,
free it or select another loopback port with
`.\Start-Sovereign.ps1 -Port <port>`. There is no CORS configuration to keep
in sync because the built UI and API share one origin.

## 7. Publication is disabled by default

Publication is a **separate, explicit post-cycle step** — it is not run during a cycle.
It also ships **disabled**: `corpus/domain.txt` is empty, so the publication gate fails
closed with `missing_domain_score` and publishes nothing. **Publication stays disabled
until the operator defines the authorized domain corpus in `corpus/domain.txt`.**

## 8. Configuration & secrets

- No API keys, tokens, or cloud credentials are required — all inference is local.
- Runtime configuration lives in `library/config/*.json`, `constitution/*.json`,
  `synthesis/*.json`, `runtime_profile.json`, and `SYSTEM_MANIFEST.json`.
- `runtime_profile.json` contains an informational `root` path recorded when the
  system was profiled; the running code resolves its own location at runtime via
  the `.sovereign-root` marker, so you do not need to edit it.
