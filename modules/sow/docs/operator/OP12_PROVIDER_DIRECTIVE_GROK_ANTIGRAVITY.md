# OP-12 OPERATOR DIRECTIVE — ADD GROK BUILD AND GEMINI/ANTIGRAVITY PROVIDERS
**Recorded:** 2026-07-31 by the orchestrator, verbatim from the operator's in-session paste.
**Provenance:** drafted by ChatGPT at the operator's request; adopted by the operator (Sam) with:
"let's go ahead and get this done. I have brought Grok and Gemini on board. So we should have
Claude, ChatGPT, Grok, and Gemini, all available participants along with my local models."
**Binding status:** binding for Phase 18 scope EXCEPT where AUTONOMOUS_BUILD_DIRECTIVE.md §17
records explicit supersessions (execution vehicle = the canonical autonomous loop under the
two-commit convention; the "active Phase 17C state" boundary is stale — Phase 17 is complete).
The Critical Scope Boundary, Credential Isolation, prohibition lists, and all technical
requirements below bind verbatim.

---

DIRECTIVE: ADD GROK BUILD AND GEMINI/ANTIGRAVITY PROVIDERS TO THE SOVEREIGN ORCHESTRATION WORKSPACE

Repository: `D:\multi model terminal app\sovereign-orchestration-workspace`

Objective: Add two new subscription-authenticated frontier providers to the existing Sovereign
Orchestration Workspace:

1. Grok Build — Executable: `grok` · UI name: `Grok Build` · Provider identifier: `grok_build`
2. Gemini through Antigravity CLI — Executable: `agy` · UI name: `Gemini · Antigravity` ·
   Provider identifier: `google_antigravity`

Create one new PowerShell bootstrap and diagnostic runner that installs, authenticates, probes,
and launches the existing app with these provider capabilities available.

This is an additive provider integration. It is not a redesign of the application, autonomous
loop, control plane, node runtime, model picker, subscription governor, or artifact pipeline.

## 1. Critical Scope Boundary

Do not modify: `tools\loop\run_loop.ps1`; `docs\loop\LOOP_STATE.json` [superseded: loop-state
bookkeeping proceeds normally under the loop; the runner itself must never touch it]; the active
Phase 17C state [stale — complete]; existing gate tags; existing Claude behavior; existing Codex
behavior; existing Ollama behavior; existing Parakeet behavior; canonical schemas; authority
rules; artifact-promotion semantics; debate semantics; MCP authority; current provider
credentials; Git remotes; branches; release or packaging state.

Do not create a second orchestration system. The new PowerShell runner is a bootstrap and
diagnostic surface only. The existing Sovereign node runtime must remain responsible for:
process supervision; ConPTY sessions; pane ownership; node identity; task dispatch; workspace
binding; subscription leases; artifact publication; tool authority; cleanup; recovery.

## 2. Required Reconnaissance

Before editing, inspect:

    Get-Command grok -ErrorAction SilentlyContinue
    Get-Command agy -ErrorAction SilentlyContinue
    grok version / grok --help / grok models / grok login --help / grok agent stdio --help
    agy --version / agy --help / agy models

Also inspect the repository's existing: provider registry; frontier adapters; Claude adapter;
Codex adapter; model-picker source; launch-ticket schema; supervised spawn path; terminal lease
governor; provider status model; locality badges; renderer provider-selection flow; integration
tests; desktop self-checks.

Do not assume command-line flags from memory when the locally installed CLI's `--help` can
establish them. **The installed command surface is authoritative.**

## 3. New PowerShell Runner

Create: `tools\providers\run_frontier_providers.ps1`

Parameters: `-Provider all|grok|gemini` · `-Action status|install|login|probe|launch` ·
`-RepoRoot <path>` · `-Model <optional slug>` · `-Prompt <optional probe prompt>` ·
`-InstallMissing` · `-NoLaunch`. Defaults: Provider=all, Action=status, RepoRoot=repository
root, InstallMissing=false.

The runner must be safe to execute repeatedly. It must not: edit application source during
execution; modify Git state; create commits; alter `LOOP_STATE.json`; capture authentication
tokens; print authentication tokens; write API keys; copy provider credential files; scrape
browser sessions; silently install software without `-InstallMissing`; silently launch
interactive authentication during `status`; start the autonomous build loop.

## 4. Provider Installation

4.1 Grok Build — only when Provider includes grok AND grok is missing AND `-InstallMissing` was
explicitly supplied: `npm install -g @xai-official/grok`, then resolve the actual executable
with `Get-Command grok`. Do not hardcode an npm roaming path.

4.2 Antigravity CLI — only when Provider includes gemini AND agy is missing AND
`-InstallMissing` was explicitly supplied: `irm https://antigravity.google/cli/install.ps1 | iex`,
then refresh command discovery and resolve `Get-Command agy`. If PATH changes require a new
terminal session, report that honestly and stop with a distinct nonzero exit code. Do not fall
back to the old `gemini` CLI for a Google AI Pro individual account.

## 5. Authentication

5.1 Grok — `-Provider grok -Action login` runs `grok login`. Let Grok open its own browser
authentication flow. Do not read or copy its credential cache. The paid Grok subscription must
be used through the provider's own authenticated client. Do not require `XAI_API_KEY`. An
API-key path may be detected and reported, but must not be enabled automatically.

5.2 Gemini/Antigravity — `-Provider gemini -Action login` starts `agy`; allow Antigravity to
invoke its own Google browser sign-in; after successful onboarding, exit the TUI cleanly. Do
not use the deprecated personal-account Gemini CLI path. Do not require `GEMINI_API_KEY`,
`GOOGLE_API_KEY`, or `GOOGLE_APPLICATION_CREDENTIALS` for the Google AI Pro subscription path.
Do not read or copy Windows Credential Manager entries or Antigravity credential storage.

## 6. Status Checks

Status must report independently per provider: provider identifier; display name; command
found; resolved executable path; version; authentication probe state; available models;
headless support; interactive support; structured-output support; subscription lease state;
application registration state. Use distinct states: AVAILABLE / NOT_INSTALLED / AUTH_REQUIRED
/ PROBE_FAILED / REGISTERED / NOT_REGISTERED / UNSUPPORTED_VERSION.

Do not infer authentication merely because the executable exists. Do not classify a provider as
unavailable because its diagnostic text mentions historical login or quota language while the
process exits successfully. Provider errors must be determined by: (1) actual process exit
code; (2) structured output where available; (3) explicit current provider error fields. **A
successful exit code must not be converted into a login or usage error by transcript keyword
matching.**

## 7. Harmless Provider Probes

7.1 Grok: one-shot, read-only prompt equivalent to
`grok --no-auto-update --cwd $RepoRoot -p "Reply with exactly: GROK_PROVIDER_OK" --output-format json`
— using the exact locally supported ordering and flag names from `grok --help`. Accept only
when: exit code zero; structured output parses; the response contains `GROK_PROVIDER_OK`; no
repository modification occurred; Git status unchanged before and after.

7.2 Antigravity: inside the repository, one-shot prompt equivalent to
`agy -p "Reply with exactly: GEMINI_PROVIDER_OK" --output-format json` — adding an explicit
read-only/restrictive sandbox flag only if confirmed by the installed `agy --help`. Same
acceptance conditions. Do not use an editing prompt as an authentication probe.

## 8. Application Provider Registration

Add both providers through the existing provider and model registry. Do not create a parallel
registry.

    Provider: grok_build            · Display: Grok Build          · Command: grok
    Provider: google_antigravity    · Display: Gemini · Antigravity · Command: agy
    Both: Locality frontier · provider-native OAuth · Interactive true · Headless true ·
    Structured output true · Default terminal allowance: 1

The model picker must obtain available models from `grok models` and `agy models` — structured
output when supported, otherwise conservative parsing that fails closed. Do not invent model
identifiers. Do not hardcode one Gemini or Grok model as the only available option. Cache model
enumeration briefly only if the existing picker architecture already caches provider inventories.

## 9. Interactive Pane Integration

Both interactive panes must launch the real TUIs (`grok` / `agy`) through the existing
supervised ConPTY path, in the node's assigned workspace, receiving: supervised node identity;
workspace binding; subscription lease; terminal ownership; lifecycle tracking; teardown
handling. Do not launch either CLI through detached `Start-Process` calls outside the existing
supervisor.

## 10. Headless Worker Integration

Through the existing frontier worker adapter contract. Grok: locally confirmed equivalent of
`grok --no-auto-update --cwd $Workspace --model $Model -p $Prompt --output-format streaming-json`
(prefer streaming structured output for live pane updates). Grok also exposes `grok agent
stdio` (ACP): use ACP only if the repository already contains a fitting client/JSON-RPC
transport — do not implement a new general ACP framework unless it is demonstrably the smallest
correct integration. Antigravity: locally confirmed equivalent of
`agy --model $Model -p $Prompt --output-format stream-json` from the assigned workspace or the
locally supported workspace flag, using the installed CLI's exact output-format spelling. Do
not invoke the retired personal-account Gemini CLI.

## 11. Tool and Permission Behavior

Do not automatically enable: `--always-approve`, unrestricted shell access, unrestricted
filesystem writes, unsandboxed execution. Provider tool permission is subordinate to the
existing Sovereign launch ticket and workspace policy. Initial provider behavior follows the
existing frontier-worker authority model: read assigned context; reason; respond; publish
CANDIDATE output; request protected actions through existing mechanisms. If the existing
application already authorizes a controlled editing worker inside an isolated worktree, pass
only the minimum provider mode required by that existing contract. A provider CLI's own
"always approve" setting is never operator approval.

## 12. Subscription Governor

Register separate subscription resources: `grok_build_subscription` and
`google_antigravity_subscription`. Default allowance: **1 active terminal per provider
subscription**. Do not combine Grok and Google into one lease. Do not raise concurrency because
the user has a paid plan. A second active terminal for the same subscription must be refused
unless the existing governor receives a separately verified allowance amendment. Ensure lease
release on: normal exit; process failure; authentication failure; provider quota failure;
cancellation; timeout; app shutdown; conductor replacement; process-tree termination.

## 13. Credential Isolation

The application must not read, retain, serialize, log, or transmit: xAI OAuth tokens; Google
OAuth tokens; browser cookies; Windows Credential Manager secrets; provider session files;
`XAI_API_KEY`; `GEMINI_API_KEY`; `GOOGLE_API_KEY`; Google service-account files. It may:
invoke the authenticated official CLI; inspect version output; inspect model-list output;
inspect non-secret status output; consume model responses; capture exit codes and bounded
diagnostics. Scrub unrelated provider API-key variables from the child environment where the
existing frontier adapter contract already performs credential scrubbing. Do not delete or
modify the user's global environment.

## 14. UI Behavior

Selectable labels: `Grok Build` and `Gemini · Antigravity`. Each selected model visibly shows:
provider; model; frontier locality; authentication status; terminal lease status;
running/stopped state. Do not display `Gemini CLI` for the Google AI Pro path.
Provider-specific failure messages must identify the actual provider (Grok authentication
required / Grok usage limit reached / Antigravity authentication required / Google AI Pro usage
limit reached / Provider executable not installed / Provider model unavailable). Never print
one provider's error text for another provider.

## 15. PowerShell Launch Action

`-Action launch` must: perform status checks; refuse only providers that are unavailable; print
a concise provider capability table; export only non-secret command-location hints if the app
needs them (e.g. `$env:SOVEREIGN_GROK_COMMAND`, `$env:SOVEREIGN_ANTIGRAVITY_COMMAND`); invoke
the repository's existing canonical desktop launcher; pass through the application's exit code.
Prefer normal command discovery inside the app over environment variables if that is how
existing providers work. Do not hardcode a new desktop launch command without first inspecting
the repository's existing launcher.

## 16. Tests

Deterministic tests for: provider command discovery; missing executable; version parsing; model
enumeration; authentication-required classification; successful structured probe; nonzero
provider failure; **exit-zero transcript containing historical error words**; provider-specific
diagnostics; one-terminal subscription limit; lease release; model-picker registration;
interactive launch-ticket construction; headless command construction; credential
non-disclosure; repository-status preservation during probes; PowerShell parameter validation;
PowerShell syntax parsing. No network-dependent test in the default deterministic suite; live
tests explicit and opt-in.

## 17. Live Acceptance

After deterministic tests pass and both accounts are authenticated: exactly one harmless live
probe per provider (`GROK_PROVIDER_OK` / `GEMINI_PROVIDER_OK`), then one controlled application
receipt per provider: select provider in the real model picker; launch one supervised pane;
verify the exact selected provider and model; submit a harmless prompt; receive a live
response; close the pane; confirm process cleanup; confirm lease return to zero; confirm no
credential material entered logs; confirm no unrelated repository files changed. Do not attempt
simultaneous same-provider sessions.

## 18–20. Runner Commands, Verification, Final Report

Runner command surface, pre-stop verification list, and final-report requirements as specified
in the operator's original paste (§18–§20): status/install/login/probe/launch invocations;
PowerShell syntax parse, `git diff --check`, deterministic provider tests, existing desktop /
terminal / Python tests, provider-registry and model-picker verification, credential grep,
Git-status comparison; confirm no loop file changed, no provider credentials read, no API key
required, only intended files changed, existing Claude/Codex/Ollama tests green. Final report
enumerates every changed file, versions, auth results, model inventories, exact commands,
picker/governor entries, test totals, live-probe results, cleanup/lease results, credential
confirmation, `git status --short`, and the operator's next commands.

*End of preserved operator directive.*
