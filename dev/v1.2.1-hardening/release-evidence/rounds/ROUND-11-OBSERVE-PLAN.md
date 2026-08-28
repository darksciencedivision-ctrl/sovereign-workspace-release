# ROUND-11 OBSERVE+PLAN (Phase 6c - P1-logs)

HEAD: cbf8dc3 | Cluster: S16.3 structured rotating logs

## Observations
- No runtime logging today (uvicorn warnings only); turn outcomes/metrics live only on WS events.
- Contract requires: timestamp, event, topic_epoch, turn, seat, model, outcome, exception class, latency, TTFT, completion state - bounded rotation - no raw secret-bearing prompts.

## Plan
### Change surface
app.py: logging RotatingFileHandler (JSON lines, 1 MiB x 3 backups) at DEBATE_LOG_DIR env override else ROOT/logs; log_event(event, **fields) helper (json.dumps with default=str, never logs prompts/interjections); wired at: run_turn success (outcome/completion_state/ttft/latency/word_count), _emit_skip_turn (reason as outcome), orchestrator interruption, ConfigurationError startup fatal, lifespan start/shutdown.
### Tests (tests/test_v1_2_1_logging.py)
T1 JSONL records parse with required keys after a completed run_turn; T2 skip path logs reason; T3 rotation bounds configured (maxBytes/backups inspected); T4 no prompt content leak assertion (interject value absent from log text).
### Acceptance: T1-T4 green; full suite green; lifecycle PASS.
This delta closes the last selected P1 (P1-logs), completing Phase 6.