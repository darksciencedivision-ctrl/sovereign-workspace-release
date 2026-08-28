OPERATOR AUTHORIZATION: SWS-UI-001 ADDENDUM-02 v1.0 is issued as written; the CP-02 envelope, the runtime install, and gates 9a-9j are authorized; corrections F-01 through F-12 bind; stage pauses waived; no provider spend authorized; llama.cpp is not promoted to production default by this package.

Before step 1, report which shell your bash tool runs (PowerShell, Git Bash, WSL, cmd). If it is not PowerShell, run every PowerShell cmdlet via powershell.exe -NoProfile -Command "<cmdlet>" — builder tooling, not a module launch. Record the shell name in evidence/cp02/baseline/session-start.txt.

Confirm AGENTS.md from this project root is loaded in your context before any tool call; if it is not, say so and stop.

Log the authorization sentence above verbatim, with the UTC you received it, into evidence/OPERATOR-INSTRUCTIONS.log before any other mutation.

Then read from disk, in this order, and do not proceed from memory of any prior session:

  1. BUILD-DIRECTIVE-SWS-UI-001.md
  2. docs/SWS-UI-001-v1.2-ADDENDUM-02.md      <- the envelope: caps, tree status, corrections F-01..F-12, gates, STOP set
  3. docs/OX-ALPHA-DIRECTIVE-CP-02.md         <- the work order: goal bands, loop, action envelope, exit
  4. docs/CP-02-REVIEW-01.md                  <- why the fifteen corrections exist
  5. docs/CP-02-CONFLICT-AUDIT.md             <- where CP-01 and CP-02 overlap, and why order is the whole safety argument
  6. docs/CP-02-MODERNIZATION-ASSESSMENT.md   <- what already exists and must not be rebuilt
  7. evidence/GATE-LEDGER.json
  8. evidence/OPERATOR-INSTRUCTIONS.log
  9. docs/CP-01-REPORT.md (or docs/STOP-REPORT-CP-01.md) and the newest docs/REVIEW-BUILD-*.md

G0.0 IS A HARD GATE, NOT A WAIT LOOP. CP-02 does not begin while CP-01 is live. If CP-01 has not exited with a reviewer verdict on its 8* band, write the STOP report for CP01_STILL_LIVE and stop. Do not poll, do not proceed in parallel, do not "start the read-only parts."

Four things will tempt you into a defect. All four are settled in ADDENDUM-01 section 2 and ADDENDUM-02 section 2:

  - llama.cpp's router has its own LRU evictor and the residency planner has another. The planner is the sole eviction authority. Run the router --no-models-autoload with --models-max above the planner's bound. The --models-max 1 setting is for Band B validation only and must not survive into Band D.
  - Ollama and llama.cpp allocate from the same 8151 MiB and neither knows the other exists. Choose and record one VRAM budget authority before Band D schedules any load.
  - There are zero .gguf files on disk. Acquire them read-only from the Ollama blob store, offline, with provenance back to the originating tag. Never write to Ollama's store.
  - Lowering an advertised context to its validated value changes resolver outcomes. Prove which requests it strands before you write it, and get operator acceptance.

Three more settled points you must not re-derive:

  - Your changed-line caps are measured against the G0.3 before/ capture — the workspace AS CP-01 LEFT IT. Lines CP-01 changed are your baseline, not your budget. Measuring against a pre-CP-01 state will make you STOP ENVELOPE_EXCEEDED on your first edit, wrongly.
  - The shell owns the llama.cpp server process, as a module, via shell/modules/llamacpp.json. Not the planner, not an adapter, not an operator-run orphan. Start and stop it only through the shell's own routes.
  - The llama.cpp port is 5183, never llama-server's default 8080. It joins 5175/8700/8765/5180 in every quiescence check, the baseline capture, and closeout.

Roughly 80% of what this package might tempt you to build already exists: the vendor-blind capability resolver, the capability vocabulary and schemas, the residency planner and its six states, the Backend Protocol, and context as a hard routing filter. You are widening, connecting, and proving them — not replacing them. A rewrite is a defect in this loop, not a strategy.

Begin at G0.0 and run the goal loop without pausing at band boundaries until every goal is TRUE or a STOP condition fires. Do not end your turn at a step boundary — end it only with the section 6 final message or a STOP report. If the harness ends your turn anyway, resume from the first failing goal without re-deriving the plan.

Nothing here amends AGENTS.md. Builder only: no PASS, no operator signature, no protected-source writes, no provider spend, no fabricated availability, no production promotion.
