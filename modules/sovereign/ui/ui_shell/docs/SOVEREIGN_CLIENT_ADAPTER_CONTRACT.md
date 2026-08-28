# SOVEREIGN browser-to-service contract

Status: canonical product client contract

Transport: same-origin JSON over `/v1`
Authority: the service database, never browser storage

## Boundary and security

The SPA calls the product only through `src/services/sovereignClient.ts`.
Production builds always use same-origin `/v1`; no production stub or fallback
data source exists. `VITE_SOVEREIGN_BACKEND_URL` is honored only by the Vite
development build.

Mutating requests use JSON (`Content-Type: application/json`). The service must
bind to loopback, validate `Host` and `Origin`, reject cross-origin mutation,
reject unsupported content types, and return structured errors without secrets
or stack traces.

## Routes

| HTTP | Path | Request | Response |
|---|---|---|---|
| GET | `/v1/health` | — | Service readiness, product version, and mode |
| GET | `/v1/sessions` | — | Bare session array or `{sessions:[...]}` |
| POST | `/v1/sessions` | `{}` | Session record or `{session:{...}}` |
| GET | `/v1/sessions/{id}` | — | Full session record |
| POST | `/v1/message` | `{input,session_id,route_override}` | Direct completed result or job |
| GET | `/v1/jobs/{id}` | — | Current job snapshot |
| POST | `/v1/jobs/{id}/cancel` | `{}` | Updated job snapshot |
| GET | `/v1/models` | — | Model list or `{models:[...]}` |
| GET | `/v1/models/profile` | — | Active profile or `{profile:{...}}` |
| POST | `/v1/models/active` | `{assignments:[{role,modelId}]}` | Authoritative saved profile or structured validation error |
| GET | `/v1/settings` | — | Service-owned settings |
| PUT | `/v1/settings` | Full settings object | `{ok,error?}` |

Validation endpoints remain optional and fail honestly when absent:
`/v1/validation/status`, `/v1/validation/results`,
`/v1/validation/benchmark`, and `/v1/validation/export`.

## Routing

`route_override` is exactly one of `AUTO`, `STATUS`, `QUICK`, `DEEP`,
`RESEARCH`, or `CONTINUITY`. The response must expose the resolved `route`
for every accepted job or direct completion.

## Job lifecycle

The accepted lifecycle states are:

- Active: `accepted`, `queued`, `running`
- Successful terminal: `completed`
- Unsuccessful terminal: `rejected`, `failed`, `cancelled`, `interrupted`

A job snapshot has:

```json
{
  "job_id": "opaque-id",
  "session_id": "opaque-id",
  "status": "running",
  "route": "DEEP",
  "progress": {
    "percent": 40,
    "stage": "deliberation",
    "detail": "Round 2 of 5"
  },
  "message": null,
  "evidence_pointer": "sovereign://runtime/evidence/example.json",
  "evidence_url": "/v1/evidence?pointer=...",
  "error": null
}
```

Only `completed` may carry an accepted sovereign message. Candidate output
returned with `rejected`, `failed`, `cancelled`, or `interrupted` is not an
answer and the SPA deliberately does not render it as one.

For reload/reconnect recovery, full session records must expose either
`active_job` or `active_job_id`. `last_job` is recommended so the terminal
outcome remains visible after reload. The SPA resumes polling active jobs by
identifier.

## Sessions and messages

Sessions are durable service records:

```text
session_id, created_at, updated_at, title, messages[],
active_model_profile, orchestration_mode, active_job_id?,
active_job?, last_job?, evidence_pointer?
```

Messages use `id`, `role` (`user` or `sovereign`), `content`, and
`timestamp`. They may include `route`, `job_id`, `job_status`,
`evidence_pointer`, `evidence_url`, and `error`.

The SPA never writes sessions, messages, job IDs, model assignments, or
settings to `localStorage`. It may display a direct server response while a
follow-up session refresh reconnects, but that response is not treated as a
second persistence authority.

## Evidence

The preferred response fields are `evidence_pointer` and `evidence_url`.
Pointers are stable opaque identifiers (for example `sovereign://...`), not
machine-specific filesystem paths. If only a pointer is supplied, the SPA
links to the same-origin resolver:

```text
GET /v1/evidence?pointer=<url-encoded-pointer>
```

The compatibility alias `evidence_log_path` is accepted for older responses
but should not be emitted by the canonical product.

## Compatibility normalization

The client accepts bare objects or common one-key envelopes and accepts
`assistant` as a wire alias for the canonical `sovereign` message role.
Unknown route or job states are rejected as invalid data rather than guessed.
