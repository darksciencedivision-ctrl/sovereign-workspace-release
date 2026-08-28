# SOVEREIGN — Broker v2.1
## Three-Model Adversarial Debate + Dolphin3 Synthesis
### Fixes applied from GPT readiness review

---

## What Changed from v2.0

| Fix | Problem | Solution |
|-----|---------|----------|
| FIX-1 | Synthesis ran with missing/mismatched final positions | Synthesis gated — all three must succeed in final round |
| FIX-2 | Mid-debate STOP used `exit`, bypassing clean shutdown | Replaced with `break` + clean flag |
| FIX-3 | Temperature set but no seed = not actually deterministic | Added `seed`, `top_p`, `top_k`, `repeat_penalty` |
| FIX-4 | Schema "enforcement" was just a polite suggestion | Regex validator + single retry per turn |
| FIX-5 | No drift control between rounds | Critic generates compact LEDGER after each round |
| FIX-6 | `$priorTurns` grew forever, could blow context window | Rolling window cap (`MaxPriorTurnChars`) |
| FIX-7 | Interject only fed to Model A | All three models see interject this round |
| FIX-8 | Log format broke on multiline, hard to parse | Block-delimited entries with `<<BEGIN>>` / `<<END>>` |
| FIX-9 | Synthesis only saw last turns, lost earlier concessions | Synthesis receives last turns + full ledger history |

---

## Quick Start

```powershell
# Run from broker directory
.\broker.ps1

# Custom config
.\broker.ps1 -DebateRounds 3 -MaxTokensPerTurn 768 -OllamaSeed 99
```

## Drop a Topic
```powershell
"What are the fundamental limits of transformer architecture?" | Out-File inbox\topic.txt
```

## Steer Mid-Session (all three models see it this round)
```powershell
"Focus on attention mechanism bottlenecks" | Out-File inbox\interject.txt
```

## Stop Cleanly
```powershell
New-Item STOP
```

---

## Flow Per Session

```
Topic received
    ↓
Round 1:
  A (Reasoner) → B (Challenger) → C (Critic)
  → C generates ROUND LEDGER (accepted/rejected/unresolved)
Round 2:
  A → B → C (each sees prior turns + ledger)
  → C generates ROUND LEDGER
    ↓
[GATE] All three succeeded in final round?
  NO  → Skip synthesis, log warning
  YES → Synthesis
    ↓
Dolphin3 receives:
  - Final positions from A, B, C
  - Full ledger history from all rounds
    ↓
Output: RESOLUTION / CONFLICTS / CONCLUSION / GAPS
    ↓
Reset, wait for next topic
```

---

## Directory Structure

```
broker/
├── broker.ps1
├── inbox/
│   ├── topic.txt        # drop topic here
│   └── interject.txt    # one-shot steering (all models see it)
├── logs/
│   ├── dialog.txt       # full debate (block-delimited)
│   ├── synthesis.txt    # synthesis outputs only
│   └── system.txt       # events, errors
└── STOP                 # create to shutdown cleanly
```

---

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| DebateRounds | 2 | Full A→B→C cycles before synthesis |
| TurnDelayMs | 1200 | Delay between calls (ms) |
| MaxTokensPerTurn | 512 | Token cap per debate turn |
| MaxTokensSynth | 1024 | Token cap for synthesis |
| MaxTokensLedger | 256 | Token cap for round ledger |
| MaxPriorTurnChars | 6000 | Rolling window cap on prior turns |
| DebateTemp | 0.7 | Debate temperature |
| SynthTemp | 0.6 | Synthesis temperature |
| OllamaSeed | 42 | Seed for reproducibility |
| TopP | 0.9 | Nucleus sampling |
| TopK | 40 | Top-K sampling |
| RepeatPenalty | 1.1 | Repetition penalty |

---

## Models

| Role | Model | Purpose |
|------|-------|---------|
| A — Reasoner | deepseek-r1:8b | Primary reasoning, chain-of-thought |
| B — Challenger | dolphin-llama3:8b | Adversarial attack, assumption testing |
| C — Critic + Ledger | qwen3:8b | Cold critique + round ledger generation |
| S — Synthesis | dolphin3:8b | Uncensored evidence-weighted synthesis |

---

## Log Format (v2.1)

All dialog entries are block-delimited for clean parsing:

```
<<BEGIN speaker=A turn=3 session=1 round=1 ts=2025-01-01T12:00:00>>
CLAIM: ...
CHALLENGE: ...
EVIDENCE: ...
UNCERTAINTY: ...
<<END speaker=A turn=3>>

<<LEDGER round=1>>
ACCEPTED: ...
REJECTED: ...
UNRESOLVED: ...
<<END LEDGER>>

<<BEGIN SYNTHESIS session=1 ts=2025-01-01T12:05:00>>
RESOLUTION: ...
CONFLICTS: ...
CONCLUSION: ...
GAPS: ...
<<END SYNTHESIS session=1>>
```

---

## Versioning

| Version | Description |
|---------|-------------|
| v1.x | 2-model A/B debate (original) |
| v2.0 | 3-model A/B/C + Dolphin3 synthesis |
| v2.1 | All GPT audit fixes applied (this) |
| v2.2 | + PRAXIS read-only memory retrieval (next) |
| v3.0 | + RRR cycles + specialist routing |

---

## Rehydrate in New Chat

Paste this README + broker.ps1 and say:
> "This is SOVEREIGN Broker v2.1. Continue development from this specification."
