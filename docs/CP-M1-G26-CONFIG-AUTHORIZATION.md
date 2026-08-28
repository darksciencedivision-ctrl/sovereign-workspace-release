# CP-M1 G26 — Operator authorization record: live_operation.json scope widening

| Field | Value |
|---|---|
| Date | 2026-08-26 |
| File | `modules/sow/config/live_operation.json` (gitignored; an authorization switch, not a credential) |
| Edited by | Reviewer, **on the operator's explicit in-session direction**, at the operator's request to perform it rather than hand-edit |
| sha256 before | `08d9d4afb15e963b4cae453995b37a3c0533a143198e81113eda16c4ab44ed69` |
| sha256 after | `dcc7f449762849b1ce721a64a55e4fe04bf7b8eff1c2ba508426effc2f8d3629` |
| Pre-edit copy | preserved at `/tmp/live_operation.before.json` on the reviewer's side; the before-hash above is the authoritative record |

## Changes — exactly two, plus a provenance comment

| Field | Before | After |
|---|---|---|
| `scope.providers` | `["openai_codex_cli"]` | `["openai_codex_cli", "claude_code"]` |
| `conductor` | `openai_codex_cli / gpt-5.6-sol` (ChatGPT 5.6 Sol) | `claude_code / fable-5` (Claude Fable 5) |

Unchanged: `live_operation_authorized: true` · `register_row: "OP-12"` · `terminals_per_subscription: 1` · `permission_profile_id: "pp-conductor-pane"` · `workspace` · `config_version: "1.1"`.

Formatting preserved: UTF-8 **no BOM**, LF line endings, 2-space indent, trailing newline. JSON re-parsed after write.

## Why

Governed Conductor communication requires the `voice_turn_boundary@1.0` hook protocol. Only `claude_code` implements it:

- `emit_conductor_launch.py:186-188` — *"Do not fabricate Claude hooks for a provider that does not implement that hook protocol."* The permission profile and `--settings` injection are applied **only** for `CLAUDE_CODE_ADAPTER`.
- `codex.py:351-352` — residual host-`config.toml` keys including declared MCP servers/hooks are a recorded live-run item (U32). Codex hooks are **host-global**, not per-launch, so no supervisor process can pin them for a session.
- `codex.py:399` — `--dangerously-bypass-hook-trust` sits inside `_FORBIDDEN_CODEX_ARGS`; the adapter structurally refuses to emit it.
- `main.js:932` sets `isClaudeHookBoundary` only for `voice_turn_boundary@1.0`; the `else` branch at `:968` starts no voice authority, so `supervisorEnforcedBoundary` (`voice/conductor-write.js:57`) can never pass for a codex conductor.

**`fable-5` is not a new choice.** `registry.py:164-166` names Claude/`fable-5` as the **recorded operator selection** from 2026-07-16 (D-COND-03). This rebinding returns the conductor to the selection already on record.

## Preconditions verified before the write

- `_PROVIDER_SCOPE_BY_ROW["OP-12"]` = `{claude_code, openai_codex_cli, grok_build, google_antigravity}` — `claude_code` is inside the code-pinned ceiling, so `_validate_providers` accepts the widened scope. The row is a ceiling; the config's list is the effective scope.
- `registry.py` — `claude_code / fable-5` is `conductor_capable=True`.
- `claude.EXE` resolves at `C:\Users\Sslaw\.local\bin\claude.EXE`, version `2.1.240`, exit 0 (`evidence/cpm1/8d/p1-claude-detect.txt`).

## Spend envelope this authorizes — and its limits

Authorized: **`openai_codex_cli` and `claude_code`**, for (a) the Conductor leg of G25/G26 and (b) the API-model leg of the G58 proof chain. **Nothing else.**

`grok_build` and `google_antigravity` remain unauthorized and record `NOT_RUN(NO_SPEND_AUTHORIZATION)`. `terminals_per_subscription` stays 1. **No worker runs on a frontier provider** — this widening covers the Conductor leg only.

## Reversion

One edit restores the prior state: `scope.providers` → `["openai_codex_cli"]`, `conductor` → `openai_codex_cli / gpt-5.6-sol` / `"ChatGPT 5.6 Sol"`. The operator may wish to revert after Band 5 closes; doing so is a deliberate act, not a cleanup.

---

*This record authorizes the config state described above and nothing further. No gate is promoted here.*
