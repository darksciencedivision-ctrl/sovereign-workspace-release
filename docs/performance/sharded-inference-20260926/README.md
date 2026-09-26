## 2026-09-26 directive progress

Source of truth: `D:\production software 4\PUNCH-LIST-DIRECTIVE-20260926-SHARDED-INFERENCE.md`.
Verified product HEAD: `3e0a2de`, pushed on feature/sharded-inference.
Item 1 isolates map prompts and ledger updates, preserves output checkpoints and chunk sizing,
and leaves plan-step ledger carry unchanged. Four new tests pass with the fix and fail with
only the three product files stashed (exit 1); the injected leak returned 20 instead of 10.
Full suite: 504 passed, exit 0. UI: typecheck, 16 Vitest tests and build passed, exit 0.
Native PowerShell 5.1 clean-room -Live gate on 3e0a2de: PASS, exit 0; 1347 files unchanged.

Historical 2026-09-25 65k run at 9e0caf2: 64 minutes, 12 calls, two splits, no lost parts
or coverage gaps. Its answer 58 was wrong (ground truth 124); cross-map ledger facts polluted
a later map. Splitting is live-verified; isolation is unit-verified, awaiting item 3 live runs.
Items 3 (65k plus prose re-verification) and 4 (MoE qualification refresh) are pending.
Stop at item 5 for operator decisions; do not perform items 5, 7 or 8. No PR opened.

Custody PR body, live addendum and operator memory updated with this evidence.
