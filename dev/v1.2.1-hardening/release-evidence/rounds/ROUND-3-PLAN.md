# ROUND-3-PLAN

## Problem
Effective configuration is derived independently by runtime, ps1 bootstrap, and sh bootstrap (divergent defaults/fallbacks), and the Ollama URL accepts any host including remote without opt-in.

## Root cause
Resolution logic has no canonical home; endpoint class was never modeled.

## Change surface
- NEW debate/config_policy.py: ConfigurationError; _read_config_text/_parse_config_document; classify_ollama_endpoint(url); resolve_ollama_base(config_url, env_url, allow_remote, config_path) enforcing policy; LOOPBACK_HOSTS constant.
- app.py: import/re-export from policy module (delete local duplicates of the three functions); DEFAULTS["allow_remote_ollama"]=False + bool coercion; OLLAMA assignment routed through resolve_ollama_base with warning+snapshot diagnostic when remote.
- scripts/effective_config.py (new CLI): prints JSON {config_path, ollama_url, endpoint_class, port, allow_remote_ollama}; exit 5 BADCONFIG-style codes compatible with bootstrap expectations; enforces same policy.
- scripts/bootstrap.ps1 + .sh: replace inline url/port derivation calls with effective_config.py invocations (ps1 checker keeps model presence logic but sources url from CLI output).
- tests/test_v1_2_1_config_policy.py (new).

## Non-change surface
Stream/guard/orchestration/hub; seat schema; limits; UI markup beyond nothing; ps1/sh model-check messaging semantics preserved.

## Tests first
T1 loopback urls accepted (127.0.0.1, localhost, ::1 bracketed)
T2 remote url rejected at startup without opt-in (SystemExit 2, message mentions allow_remote_ollama)
T3 remote accepted WITH allow_remote_ollama=true; snapshot/diagnostic exposes endpoint_class=remote (module attr check sufficient this round)
T4 env OLLAMA_URL remote override cannot bypass policy while config disallows (startup fails)
T5 bootstrap/runtime equivalence: effective_config.py JSON matches module-resolved values for same config incl. BOM file
T6 sh/ps1 no longer contain independent json.loads of config for url/port (source scan assertion)

## Failure modes
ps1/sh quoting regressions on paths with spaces (mitigated: equivalence test runs through real script invocation on Windows); IPv6 bracket parsing.

## Rollback
Single commit revert; new module is additive.

## Acceptance
T1..T6 green; full suite green; both bootstraps still function (ps1 dry-run of check section via direct python invocation of helper).

This delta moves the Distillery Module closer to completion by closing P0-04 and P0-05 and adding regression tests for loopback acceptance, remote rejection/opt-in, env-override enforcement, bootstrap-runtime equivalence, and removal of divergent parsers.
