# SOVEREIGN client packaging

`npm run build` runs strict TypeScript validation and emits the production SPA
to `dist/`. The canonical product service serves that directory and `/v1` from
one loopback origin.

Production behavior is fixed:

- API requests are same-origin.
- No stub transport is bundled or selected.
- Sessions, messages, jobs, settings, and model state come from the service.
- Product version is displayed from `/v1/health`; the SPA does not embed a
  competing version constant.
- Evidence links remain same-origin and use stable evidence pointers.

For separate Vite development only, `VITE_SOVEREIGN_BACKEND_URL` may point at
the loopback service. This variable is ignored in a production bundle.

The static files are not a standalone product. Packaging must include the
service, launcher, durable state migration, diagnostics, and containment
controls; opening `dist/index.html` directly is unsupported.
