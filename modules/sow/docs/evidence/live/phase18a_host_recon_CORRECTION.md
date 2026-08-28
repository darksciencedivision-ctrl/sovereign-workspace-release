# CORRECTION — two statements in `phase18a_host_recon.json` are stale or false

**Recorded 2026-08-01, fourth review round, Phase 18A (OP-12).**
The capture it names is **not rewritten**. `docs/evidence/live/phase18a_host_recon.json` is the
artifact operator directive §2 makes *authoritative* for every flag decision in this phase, and it
is published evidence: it stands as recorded, wrong parts included, corrected beside it and never
in place (invariant 12). Both items below were found by the round-4 spec-auditor (findings 2 and 5)
and are the same defect shape: a round-3 fix that reached the **code** and stopped short of the
**artifact the finding was about**.

## 1. FALSE — `grok login` described as hidden from the Commands list

`docs/evidence/live/phase18a_host_recon.json:139`:

```json
"installed": "present (hidden from the Commands list; `--oauth` / `--device-auth` modes)",
```

### The falsifying data, from the same file

The captured `grok --help` at `:209` (`/command_surface/0/surface/1/stdout`) lists it plainly:

```
Commands:
  agent        Run Grok without the interactive UI
  ...
  login        Sign in to Grok
  logout       Sign out and clear cached credentials
```

`grok login` is a normal, listed subcommand of this build (`grok 0.2.118`). What *is* true, and
what the delta was presumably reaching for, is that `grok login --help` documents `--oauth` and
`--device-auth` modes — captured in the same file as its own `grok login --help` entry.

### Where it is already corrected

In the code, at `6baa3e2` (round-3 spec-audit MINOR-11 / gate-validator A-2):
`tools/providers/frontier_provider_recon.py` `RECORDED_FLAG_DELTAS` now reads *"present and listed
in `grok --help`"*. The committed capture kept the old sentence and, until this note, had no
sibling correcting it. Nothing in the runner's behaviour depended on the false half: the login
argv is `grok login` either way, and it is exercised only under `-Action login`.

## 2. STALE — the recorded credential policy is the pre-round-3 half of the policy

`docs/evidence/live/phase18a_host_recon.json:167-181` records `reads_credentials`, the nine exact
`scrubbed_env_keys`, and a one-line note. That was the whole of the emitted policy on the day the
capture was taken. It is no longer the whole of the actual policy, in two directions:

* **Round-3 MINOR-13** established that recording only the nine exact keys understates the
  classifier, which also drops five key *prefixes* and eight *substrings*, and — the substance of
  round-2's N-1 — **preserves** an allowlist of non-secret config pointers (`GROK_SANDBOX`, the
  grok CLI's only filesystem/network containment lever, plus `GROK_CONFIG_DIR`, `GROK_HOME`,
  `ANTIGRAVITY_HOME`, `ANTIGRAVITY_CONFIG_DIR`). `build_report()` has emitted
  `scrubbed_key_prefixes`, `scrubbed_key_substrings` and `preserved_non_secret_config_keys` since
  `6baa3e2`, pinned by `test_the_recorded_credential_policy_is_the_whole_policy`.
* **Round-4 finding 9** retired the key `reads_credentials` itself. As a per-run boolean it was a
  constant asserted against itself — it could not go false if the run misbehaved. It is now
  `reads_credentials_by_design` plus a `claim_basis` naming the tests that structurally enforce
  it, and the test asserts those named tests **exist**, so the claim cannot outlive its evidence.

**Therefore: a report regenerated today will not have the same `credential_policy` shape as the
committed capture.** That is the intended direction of change, and this note is the join between
them. The capture's *substantive* claim — that this build reads, stores, prints and transmits no
token — is unchanged and still holds; only its completeness and its self-description were wrong.

## Not regenerated, deliberately

The obvious move is to re-run the capture and commit a `_r3.json`. It is not done here, because a
regenerated capture would re-execute `grok --help` / `agy --help` / `grok models` / `agy models`
against the live CLIs (`grok models` and `agy models` are authenticated vendor calls — U236) to
fix two sentences that are already fixed in the code that produces them. The capture's *provider
facts* — versions, flags, model inventories, states — were verified byte-identically by the
round-1 and round-4 gate-validators and are not in question. If 18B or 18C needs a fresh capture
for its own reasons, it supersedes this one with a sibling, exactly as the runner receipt did.
