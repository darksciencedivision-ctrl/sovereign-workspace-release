# R8 — OP-6 CONCURRENCY BASIS NOTE (both live providers → allowance = 2)
Append-only dated note. Produced by autonomous loop sub-step `phase-15a.r8`, **2026-07-19Z**.
Ties the two OP-6 R8 records together and states, unambiguously, **why the subscription governor's
per-subscription allowance is 2 and not 1** — so no future reader mistakes an *operator ruling* for
a *verified concurrency finding*.

Companion records:
- `docs/evidence/R8_TOS_VERIFICATION_CLAUDE_CODE.md` (provider `claude_code`, `phase-14b.r8tos`)
- `docs/evidence/R8_TOS_VERIFICATION_OPENAI_CODEX.md` (provider `openai_codex_cli`, this sub-step)

---

## The one load-bearing distinction

| Question | Answer |
|---|---|
| Did R8 **verify** a per-account concurrent-session number for `claude_code`? | **No.** No publicly documented allowance; empirical finding = **verified-at-1** (fail-closed). |
| Did R8 **verify** a per-account concurrent-session number for `openai_codex_cli`? | **No.** No publicly documented allowance; empirical finding = **verified-at-1** (fail-closed). |
| Then why is the governor allowance **2** per subscription? | Because the **operator ordered it** (register **OP-6**, directive §11(b)) — this is operator **authority**, not an R8 verification. |

**Directive §11(b), verbatim basis:** *"I-X3 allowance is raised to **2 terminals per
subscription** by explicit operator direction (R8 note: formally verified-at-1; the raise is
operator-ordered, cap stays governor-enforced and reversible; never exceed 2 without a new
ruling)."*

So R8's own concurrency **finding remains 1** for both providers (never raised on inference or
silence — §18.3). The number the governor enforces (`2`) is a **ceiling granted by the operator**,
sitting *above* the unchanged fail-closed default of `1`. If OP-6 were rescinded, the empirical R8
finding (1) is what would remain.

## How the 2 is bounded in code (already landed — this note changes no code)

The allowance is not merely asserted in prose; it is enforced by three independent fail-closed
layers (landed at `phase-15a.liveauth` and `phase-15a.governor`, verified untouched by this
documentation sub-step):

1. **Config scope, code-pinned** — `control_plane/profiles/live_authorization.py`:
   `_MAX_TERMINALS_PER_SUBSCRIPTION = 2`, `_validate_terminals` clamps to `[1, 2]` with a bool
   guard (so `terminals: true` cannot masquerade as `1`); a present `config/live_operation.json` can
   only **match or narrow, never widen**; absence ⇒ DENIED.
2. **Governor hard cap** — `node_runtime/supervisor/subscription_governor.py`:
   `MAX_ALLOWANCE = 2`; `register_subscription(allowance > 2)` **raises and registers nothing**;
   default stays `1`; re-registration reconciles to the currently-authorized value without evicting
   a mid-generation holder.
3. **Spawn gate reads authorization, never self-grants** — `node_runtime/supervisor/frontier_spawn.py`
   gate (5): `allowance = live_auth.terminals_per_subscription` (the code-pinned OP-6 scope), not a
   hardcoded literal; gates (1)/(2) refuse a DENIED auth before the governor is even consulted.

Net: `1 ≤ effective allowance ≤ 2` structurally, per subscription, for both `claude_code` and
`openai_codex_cli`. A **third** terminal on a subscription is refused. The cap is **reversible** —
a new operator ruling (narrowing) reconciles down and binds the next supervised spawn.

## Provenance of the raise

- **Authority:** operator, register **OP-6**, 2026-07-19 (directive §11); reaffirmed by OP-7/OP-8
  ordering amendments (§12/§13), which change track order and product surface but **not** the
  allowance.
- **Not** derived from: any OpenAI/Anthropic published concurrency number, any support ticket, or
  any inference from silence. Should a provider ever confirm a specific number, that would be a new
  `[OPERATOR]`-flagged R8 update — still bounded by `MAX_ALLOWANCE = 2` until a new ruling.
- **Credential posture (§2.2, unchanged):** both adapters invoke the host's already-authenticated
  CLIs and never read, store, or transmit credentials. This note concerns a concurrency *ceiling*,
  not any credential.

## Register linkage

- **U5** (per-account concurrency): dated note appended — verified-at-1 for both providers; the
  governor's `2` is operator-ordered (OP-6), governor-capped, reversible.
- **U3** (Codex ToS/automation): RECORDED under OP-6 (`R8_TOS_VERIFICATION_OPENAI_CODEX.md`) — no
  longer "out of scope" as it was under OP-5.
- **No live call and no credential handling occurred in `phase-15a.r8`.**
