# Sovereign Token Center — Complete AI Build Handoff

## Mission

Reconstruct and run **Sovereign Token Center**, a local-only, read-only dashboard that discovers numeric token-usage evidence left by supported AI clients, groups usage by local calendar day/provider/model, and renders an always-on browser dashboard.

The supplied ZIP is the complete application. Do not replace it with a mockup or a hosted analytics service. Preserve the privacy and accounting rules below.

## Non-negotiable behavior

1. Bind the HTTP service only to `127.0.0.1` unless the owner explicitly requests network exposure.
2. Never read API keys, credential stores, raw prompts, raw responses, or account identities.
3. Read only numeric usage metadata from supported local ledgers and logs.
4. Deduplicate records using stable provider/session/message identifiers so repeated scans never double-count usage.
5. Show unsupported or incomplete sources as `UNKNOWN`; never represent unknown usage as zero.
6. Store only sanitized aggregate events in `data/piggybank.sqlite`.
7. Keep `data/`, SQLite databases, caches, and logs out of source control or redistribution.
8. Keep the gold-drop animation bounded: one threshold per 1,000 observed tokens, no more than seven active sprites, no more than twenty queued, and each landed sprite fades within 30–60 seconds.
9. Select the Sam Altman, Elon Musk, or Dario Amodei gold sprite randomly, weighted by the observed token share associated with OpenAI/Codex, xAI/Grok-style, or Anthropic/Claude records for the current day.

## Supplied project structure

```text
Sovereign-Token-Center/
├── AI-BUILD-HANDOFF.md
├── README.md
├── .gitignore
├── piggybank.py
├── Start-SovereignTokenCenter.ps1
├── Stop-SovereignTokenCenter.ps1
├── Start-TokenPiggyBank.ps1
├── Stop-TokenPiggyBank.ps1
├── SOURCE-MANIFEST.sha256
├── static/
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── assets/
│       ├── gold-drop.png
│       ├── gold-drop-sam.png
│       ├── gold-drop-elon.png
│       └── gold-drop-dario.png
└── tests/
    └── test_piggybank.py
```

The application deliberately has no third-party Python dependencies. It uses the Python standard library and browser-native HTML/CSS/JavaScript.

## Component responsibilities

- `piggybank.py`: discovers supported local ledgers, parses numeric usage events, deduplicates and aggregates them, maintains the local SQLite database, serves the dashboard, and exposes sanitized JSON endpoints.
- `static/index.html`: accessible dashboard structure.
- `static/styles.css`: responsive always-on display styling, mascot, chart, panels, and bounded drop animations.
- `static/app.js`: dashboard rendering, polling, manual refresh, chart interaction, threshold tracking, source-weighted sprite selection, queue limits, lifecycle cleanup, and reduced-motion handling.
- `static/assets/*.png`: transparent animation sprites required by `app.js` and served by `piggybank.py`.
- `Start-SovereignTokenCenter.ps1`: Windows launcher. It resolves Python correctly even when the project path contains spaces, checks port 8765, waits for `/healthz`, and opens the browser.
- `Stop-SovereignTokenCenter.ps1`: stops only the Python process on port 8765 whose command line contains `piggybank.py`.
- `tests/test_piggybank.py`: regression coverage for key collector and accounting rules.

## Build and validation procedure for an AI agent

1. Extract the ZIP without flattening its directories.
2. Confirm that every file listed in `SOURCE-MANIFEST.sha256` exists.
3. From the extracted project root, validate the checksums:

   ```powershell
   Get-Content .\SOURCE-MANIFEST.sha256 | ForEach-Object {
       $expected, $relative = $_ -split '  ', 2
       $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $relative).Hash.ToLowerInvariant()
       if ($actual -ne $expected) { throw "Checksum mismatch: $relative" }
   }
   ```

4. Confirm Python 3.12 is installed:

   ```powershell
   py -3.12 --version
   ```

5. Compile and test before launching:

   ```powershell
   py -3.12 -m py_compile .\piggybank.py
   py -3.12 -m unittest discover -s tests -v
   ```

6. Start the application:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\Start-SovereignTokenCenter.ps1
   ```

7. Verify health and the UI:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8765/healthz
   Start-Process http://127.0.0.1:8765/
   ```

8. Stop it with:

   ```powershell
   .\Stop-SovereignTokenCenter.ps1
   ```

## Direct launch and diagnostic commands

If PowerShell launch scripts are unavailable, run:

```powershell
py -3.12 .\piggybank.py --host 127.0.0.1 --port 8765
```

Generate a one-time sanitized summary without starting the dashboard:

```powershell
py -3.12 .\piggybank.py --once
```

The first scan may take several seconds. Normal startup creates `data/piggybank.sqlite` automatically. That database belongs to the computer on which it was generated and must not be copied between users.

## Supported evidence sources

The current collectors inspect numeric usage evidence from local Codex session JSONL, Claude Code session JSONL, OpenCode's SQLite message ledger, LM Studio timing logs, and Grok diagnostic usage metadata when available. The coverage panel reports installed clients whose available local storage does not expose reliable complete numeric token totals.

Do not claim that every commercial web chat or desktop client is measurable. A provider is countable only when it leaves a reliable local numeric ledger in a recognized format.

## API surface

- `GET /`: dashboard HTML.
- `GET /app.js`, `GET /styles.css`, and the explicitly allowlisted `/assets/*.png` paths: static interface files.
- `GET /healthz`: sanitized health state.
- `GET /api/summary?days=14`: sanitized daily/provider/model aggregates.
- `POST /api/refresh`: triggers a new read-only ledger scan and returns updated sanitized state.

Do not add a broad arbitrary-file static route. Keep asset serving allowlisted.

## Privacy review before redistribution

Before creating another archive, exclude at minimum:

```text
.git/
data/
__pycache__/
*.sqlite
*.sqlite3
*.db
*.log
```

Also scan the remaining text files for API keys, authorization headers, usernames, absolute user-profile paths, prompt content, and account identifiers. None are required for this application.

## Expected acceptance checks

- All unit tests pass.
- `/healthz` returns `{ "ok": true, ... }` after startup.
- `/` and every allowlisted sprite return HTTP 200.
- The dashboard shows daily totals, provider/model rows, coverage status, and the fourteen-day chart.
- New 1,000-token thresholds create bounded gold sprites and clean them up after 30–60 seconds.
- Reduced-motion mode suppresses the animation.
- Repeated refreshes do not double-count the same underlying usage record.
- The application never exposes raw source records through its API.

## Notes for modification

Preserve the existing architecture unless a requested change requires otherwise. Any new collector needs fixture-based tests that prove numeric extraction, deduplication, day assignment, and safe behavior when fields are missing. Any new API response must remain aggregate-only. Validate Python, JavaScript syntax, unit tests, HTTP health, and every referenced asset before handing the application back.
