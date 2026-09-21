# SOVEREIGN production distribution

This ZIP is a clean, run-from-folder Windows distribution of SOVEREIGN 3.1.2. It contains the current application, lifecycle scripts, runtime configuration, and prebuilt operator UI. It does not contain an installer, a Python virtual environment, operator conversations or history, runtime logs, model weights, or model caches.

## Current runtime environment

- Compatible Windows host with PowerShell and loopback networking.
- Python 3.10 or newer.
- A local inference backend. SOVEREIGN is **backend-agnostic and runs on either engine**:
  - **llama.cpp** (the default) via the bundled local supervisor on `http://127.0.0.1:18080`. Start/manage it with the `*-LlamaCppSupervisor.ps1` scripts in this directory, or let the Sovereign Workspace shell start the `llamacpp` module.
  - **Ollama** on `http://127.0.0.1:11434`.
- The pinned Python packages in `requirements.txt`: Flask 3.1.3, requests 2.34.2, ChromaDB 1.5.9, NumPy 2.5.1, and Pydantic 2.13.4.
- Node.js is not required for normal operation because the production UI bundle is included under `ui/ui_shell/dist`.

### Selecting the inference backend

The effective backend is resolved in this precedence order (see `sovereign_product/backend_selection.py`):

1. the `SOVEREIGN_INFERENCE_BACKEND` environment variable (`llama.cpp` or `ollama`), if set;
2. the `default_backend` field in `runtime/backend_selection.json`, if present;
3. the factory default, **llama.cpp**.

Model-role assignments are never remapped by backend selection; production roles stay on the selected engine unless an operator explicitly designates otherwise. Whichever backend is selected must be running and must have the assigned model tags installed before startup.

## Current default model assignments

These are the package's current defaults, not permanently hard-coded architectural model choices:

- Primary reasoner: `qwen2.5:3b-instruct`
- Adversarial challenger: `granite4.2:3b`
- Critic: `sam860/dolphin3-llama3.2:3b`
- Synthesizer: `llama3.2:3b`
- Embedding model: `nomic-embed-text:latest`

Model weights are not included. Before startup, install the exact current default tags in the local Ollama service. Startup currently checks all five assignments. Supported generation roles remain replaceable through SOVEREIGN's existing Models assignment mechanism; the selected tags must be installed in Ollama. The embedding assignment remains configuration-controlled in `SYSTEM_MANIFEST.json`.

## Prepare dependencies

Extract the ZIP, open PowerShell, and run the following from the extracted `SOVEREIGN` directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

The launcher intentionally expects the local environment at `.venv\Scripts\python.exe`. Keep the working directory set to the extracted `SOVEREIGN` directory when using the lifecycle scripts.

## Operate SOVEREIGN

Start the product:

```powershell
.\Start-Sovereign.ps1
```

The default product URL is `http://127.0.0.1:5175/`. The launcher also supports its existing `-Port`, `-Workers`, and `-NoBrowser` parameters.

Stop the product normally:

```powershell
.\Stop-Sovereign.ps1
```

Run diagnostics:

```powershell
.\Diagnose-Sovereign.ps1
```

Mutable runtime state is kept under `%LOCALAPPDATA%\SovereignWorkspace\sovereign`, outside the installation directory. `SOVEREIGN_WORKSPACE_STATE` overrides that location. The distribution itself contains no operator conversations, history, research runs, jobs, sessions, or other mutable runtime state.

SOVEREIGN binds the product service to loopback. The current deployment requires local Ollama and the assigned model tags to be available before startup. This package is a folder distribution, not an MSI/EXE installer or Windows Service.
