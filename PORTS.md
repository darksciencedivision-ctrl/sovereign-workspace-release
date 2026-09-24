# Sovereign Workspace — port map

All services bind to **loopback only** (`127.0.0.1`). Nothing listens on an external interface.

| Port  | Service | Module | Notes |
|------:|---------|--------|-------|
| 5180  | Shell (control plane + UI) | `shell` | The default; override with `Start-Shell.ps1 -Port <n>`. |
| 5175  | SOVEREIGN product service + UI | `sovereign` | Flask. |
| 8700  | Debate Table | `debate` | FastAPI. |
| 8765  | Token Center | `tokencenter` | Read-only telemetry; embedded in the shell UI. |
| 5184  | Distillery console | `distillery` | Health-only console (no compute on open). |
| 18080 | llama.cpp local inference router | `llamacpp` | The shared inference endpoint the workspace attaches to. |
| 11434 | Ollama | (external) | The other supported backend; started/managed by you, not the shell. |
| 1919  | FreeToken supervisor | `sovereign` (optional) | Only when the FreeToken profile is selected. |

## Inference backends (either works)

The workspace is backend-agnostic. The effective backend is resolved by
`sovereign_product/backend_selection.py`:

1. `SOVEREIGN_INFERENCE_BACKEND` (`llama.cpp` or `ollama`), if set;
2. `runtime/backend_selection.json` `default_backend`;
3. factory default: **llama.cpp**.

- **llama.cpp** → the local supervisor on **:18080**. Provisioned per machine — see
  `Provision-Workspace.ps1` and `workspace.env` (`SOVEREIGN_LLAMACPP_SERVER_EXE`).
- **Ollama** → **:11434**. Start Ollama and `ollama pull <tag>` your models.

## Port conflicts

`Start-Shell.ps1 -CheckOnly` reports whether the shell's own port is free (blocking) and whether any
module port is already held by something else (advisory — it names the module and port). A held
module port does not stop the shell; that module simply will not start until the port is free.

Change the shell port with `-Port`. Module ports are fixed in each `shell/modules/<id>.json`
(`readiness.url` / `launch.argv`); change them there if a fixed port collides on your machine.
