# SOVEREIGN production distribution

This ZIP is a clean, run-from-folder Windows distribution of SOVEREIGN 3.1.2. It contains the current application, lifecycle scripts, runtime configuration, and prebuilt operator UI. It does not contain an installer, a Python virtual environment, operator conversations or history, runtime logs, model weights, or model caches.

## Current runtime environment

- Compatible Windows host with PowerShell and loopback networking.
- Python 3.10 or newer.
- A local Ollama service reachable at `http://127.0.0.1:11434`, as currently configured in `SYSTEM_MANIFEST.json`.
- The pinned Python packages in `requirements.txt`: Flask 3.1.3, requests 2.34.2, ChromaDB 1.5.9, NumPy 2.5.1, and Pydantic 2.13.4.
- Node.js is not required for normal operation because the production UI bundle is included under `ui/ui_shell/dist`.

## Current default model assignments

These are the package's current defaults, not permanently hard-coded architectural model choices:

- Primary reasoner: `qwen3:14b`
- Adversarial challenger: `qwen3:32b`
- Critic: `qwen3:8b`
- Synthesizer: `qwen2.5:14b-instruct`
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

Mutable state is initialized under the extracted package's root-relative `runtime` directory, including `runtime/sovereign.db`, evidence, service state, and runtime logs. No operator conversation, history, research run, job, session, or other mutable runtime state is included in this distribution.

SOVEREIGN binds the product service to loopback. The current deployment requires local Ollama and the assigned model tags to be available before startup. This package is a folder distribution, not an MSI/EXE installer or Windows Service.
