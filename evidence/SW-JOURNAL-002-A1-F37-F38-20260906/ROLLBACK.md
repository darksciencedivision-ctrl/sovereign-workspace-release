# utc: 2026-09-06T19:22:08.471153+00:00
# producer: Codex Step6 evidence
RECOMMENDATION: Close the application and shell; independently verify quiescence before restoring any source.

RECOMMENDATION: For every file in deployment-manifest.json, require its current SHA-256 to equal new_sha256 immediately before writing; stop on any mismatch. Restore only that file from rollback_preimage and verify old_sha256. For the two new tests, remove only the exact listed file if its current hash equals new_sha256. Do not restore unrelated prior work or use git reset/checkout.

RECOMMENDATION: Restore all listed source and mutation-baseline files as one quiescent operation, run text integrity after scripted edits, and rerun the appropriate suites before any acceptance. Preserve this evidence directory and operator log.
