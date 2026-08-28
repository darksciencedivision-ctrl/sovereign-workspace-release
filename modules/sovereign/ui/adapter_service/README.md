# Legacy adapter compatibility

Status: retired compatibility surface

SOVEREIGN now has one product service:

```text
python -m sovereign_product.server
```

It serves the built UI and `/v1` API from the same loopback origin, and owns
durable sessions, jobs, settings, evidence pointers, recovery, and
cancellation. There is no independent adapter process, in-memory job registry,
adapter-side settings file, permissive CORS layer, or second response-reading
path.

## Existing commands

The legacy command remains safe:

```text
python ui/adapter_service/adapter.py
```

`adapter.py` locates the nearest valid `.sovereign-root` marker and forwards
arguments to `sovereign_product.server`. It does not read
`adapter_config.json` or any adapter-local settings. This means a legacy
shortcut cannot silently start a different implementation or target an old
machine-specific path.

For normal operation use the root-level commands:

```powershell
.\Start-Sovereign.ps1
.\Diagnose-Sovereign.ps1
.\Test-Sovereign.ps1
.\Stop-Sovereign.ps1
```

`Start-Sovereign.ps1` defaults to `127.0.0.1:5175` and passes the explicit,
marker-validated install root to the unified service. Non-loopback binding is
not supported.

## Retired files

`adapter_config.json` and `adapter_config.example.json` are tombstone metadata
for old installations and are ignored. Product settings are stored in the
durable product database. `ADAPTER2_ROUTE_CANDIDATES.md` is retained only as a
historical decision note.

## Verification

With the unified service running:

```text
python ui/adapter_service/smoke_test.py
```

The smoke test checks the current same-origin API contract. It never writes a
legacy settings file and does not start a second service.

## Security boundary

- Loopback HTTP only.
- Built UI and API share one origin.
- Mutations require JSON and reject cross-origin browser requests.
- No permissive CORS headers.
- Evidence is resolved from containment-checked `sovereign://` pointers.
- Only a completed, exactly attributed job may carry a SOVEREIGN answer.
