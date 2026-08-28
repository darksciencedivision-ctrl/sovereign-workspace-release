# G0 evidence chronology

`hg0-status.json` originally recorded a PASS that treated labels attached during evidence
import as if they were live operator marks. The post-audit origin review corrected that
state to `LIMITED_PENDING_LIVE_OPERATOR_MARKS` without rewriting Git history.

The limitation is now closed by two new target-harness sessions initiated after the
operator-mark directive:

```text
G0-A = PASS (live QUICK completion + operator /success)
G0-B = PASS (live controlled DEEP cancellation + operator /fail)
G0-C = PASS (preserved recovery evidence)
G0-D = PASS (preserved UNKNOWN-source fail-closed rejection)
HG-0 = PASS
```

The authoritative current state is [`hg0-status.json`](hg0-status.json). The content-free
event evidence is available as both [`hashed-event-manifest.json`](hashed-event-manifest.json)
and row-oriented [`event-manifest.jsonl`](event-manifest.jsonl). Raw prompts, responses,
and runtime payloads remain outside Git.

`status.json` remains an earlier partial-import record. The former HG-0 status and
limitation remain recoverable from repository history.
