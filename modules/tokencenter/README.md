# Sovereign Token Center

A local, read-only dashboard that groups observed token use by calendar day, provider, and model.

It currently reads numeric usage evidence from:

- Codex local session JSONL
- Claude Code local session JSONL
- OpenCode's local SQLite message ledger
- LM Studio server timing logs
- Grok diagnostic usage metadata when the provider emits it

Installed clients without a complete numeric ledger are shown as `UNKNOWN`; they are never counted as zero. The service binds to `127.0.0.1` and does not read credential stores or expose raw prompts, responses, account identities, or source log lines.

Run `Start-SovereignTokenCenter.ps1`, or start it directly with:

```powershell
py -3.12 .\piggybank.py
```

Then open <http://127.0.0.1:8765/>.

Use `py -3.12 .\piggybank.py --once` for a sanitized JSON summary.

Run `Stop-SovereignTokenCenter.ps1` to stop the local dashboard process. The original Token Piggy Bank launchers remain as compatibility aliases.
