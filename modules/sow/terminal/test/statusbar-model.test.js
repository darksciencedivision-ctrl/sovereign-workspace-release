"use strict";
/**
 * Status-bar view-model tests (phase-15a.statusbar) — the PURE fold from a governor status() dict
 * to the n/2 rows the shell status bar renders. Headless (no Electron, no subprocess): this is the
 * testable heart the 14A substitution pattern requires, the drawn bar being an operator-run metric.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const {
  LIVE_PROVIDERS, SUBSCRIPTION_CAP, PROVIDER_ALLOWANCE, buildStatusBarModel, summarizeStatusBar,
} = require("../statusbar/statusbar-model");

const row = (model, provider) => model.rows.find((r) => r.provider === provider);

test("every live provider is surfaced with ITS OWN cap visible, even fully idle", () => {
  const m = buildStatusBarModel({ status: {} }); // governor read, nothing registered
  assert.equal(m.readable, true);
  assert.equal(m.cap, SUBSCRIPTION_CAP);
  assert.deepEqual(m.providers, LIVE_PROVIDERS);
  for (const p of LIVE_PROVIDERS) {
    const r = row(m, p);
    assert.ok(r, `${p} row present`);
    assert.equal(r.inUse, 0);
    // U255: the ceiling is PER PROVIDER. The OP-6 pair is 2; the OP-12 pair is 1 each and never
    // merged (operator directive §12), so a global 2 here would advertise a terminal the governor
    // will refuse — overstating the operator's concurrency in the surface §14 governs.
    assert.equal(r.allowance, PROVIDER_ALLOWANCE[p]);
    assert.equal(r.label, `0/${PROVIDER_ALLOWANCE[p]}`);
    assert.equal(r.state, "idle"); // read-and-empty is an honest zero, not unknown
  }
  assert.deepEqual(PROVIDER_ALLOWANCE, {
    claude_code: 2, openai_codex_cli: 2, grok_build: 1, google_antigravity: 1,
  });
});

test("a real 1/2 count folds to an active row; the cap is the governor's own allowance", () => {
  const status = {
    "sub-anthropic": { provider: "claude_code", allowance: 2, active: ["frontier-A"], in_use: 1 },
    "sub-openai": { provider: "openai_codex_cli", allowance: 2, active: [], in_use: 0 },
  };
  const m = buildStatusBarModel({ status });
  assert.equal(m.readable, true);
  const a = row(m, "claude_code");
  assert.equal(a.label, "1/2");
  assert.equal(a.inUse, 1);
  assert.equal(a.state, "active");
  assert.equal(a.subscriptionRef, "sub-anthropic");
  assert.equal(row(m, "openai_codex_cli").state, "idle");
});

test("in_use == allowance reads at-capacity (no further spawn permitted)", () => {
  const status = { "sub-a": { provider: "claude_code", allowance: 2, active: ["x", "y"], in_use: 2 } };
  const m = buildStatusBarModel({ status });
  const a = row(m, "claude_code");
  assert.equal(a.label, "2/2");
  assert.equal(a.state, "at-capacity");
});

test("FAIL-CLOSED: an unreadable governor (null) yields unknown rows with an em-dash — never 0/2", () => {
  const m = buildStatusBarModel({ status: null });
  assert.equal(m.readable, false);
  for (const p of LIVE_PROVIDERS) {
    const r = row(m, p);
    assert.equal(r.state, "unknown");
    assert.equal(r.inUse, null, "no fabricated count when unread");
    assert.equal(r.label, `—/${PROVIDER_ALLOWANCE[p]}`);
    assert.notEqual(r.label, `0/${PROVIDER_ALLOWANCE[p]}`, "must NOT claim zero when unread");
  }
});

test("FAIL-CLOSED: a non-object status is treated as unreadable, not coerced", () => {
  for (const bad of ["nope", 42, ["a"], undefined]) {
    const m = buildStatusBarModel({ status: bad });
    assert.equal(m.readable, false);
    assert.ok(m.rows.every((r) => r.state === "unknown" && r.inUse === null));
  }
});

test("FAIL-CLOSED: one malformed subscription record is unknown on its OWN row, not fabricated", () => {
  const status = {
    "sub-good": { provider: "claude_code", allowance: 2, active: [], in_use: 1 },
    "sub-bad": { provider: "openai_codex_cli", allowance: 2, in_use: "lots" }, // in_use not an int
  };
  const m = buildStatusBarModel({ status });
  assert.equal(m.readable, true, "the readable model still renders; one bad row does not poison it");
  assert.equal(row(m, "claude_code").label, "1/2");
  const bad = row(m, "openai_codex_cli");
  assert.equal(bad.state, "unknown");
  assert.equal(bad.inUse, null);
  assert.equal(bad.label, `—/${SUBSCRIPTION_CAP}`);
});

test("a negative in_use is rejected as malformed (fail-closed), not shown as a count", () => {
  const status = { "s": { provider: "claude_code", allowance: 2, in_use: -1 } };
  const m = buildStatusBarModel({ status });
  assert.equal(row(m, "claude_code").state, "unknown");
});

test("a subscription on an unsurfaced provider is still shown, never silently dropped (inv 27)", () => {
  const status = { "s-other": { provider: "some_future_provider", allowance: 1, active: ["z"], in_use: 1 } };
  const m = buildStatusBarModel({ status });
  const r = row(m, "some_future_provider");
  assert.ok(r, "the extra provider row is present");
  assert.equal(r.label, "1/1");
  // and the two OP-6 providers are still surfaced as idle
  assert.equal(row(m, "claude_code").state, "idle");
});

test("ordering is deterministic: providers in declared order, then extras", () => {
  const status = {
    "z-sub": { provider: "openai_codex_cli", allowance: 2, active: [], in_use: 0 },
    "a-sub": { provider: "claude_code", allowance: 2, active: [], in_use: 0 },
    "m-extra": { provider: "zzz", allowance: 1, active: [], in_use: 0 },
  };
  const m = buildStatusBarModel({ status });
  // Declared order first (all four live providers — the OP-12 pair appearing as idle rows because
  // this status registered no subscription for them), then providers outside the surfaced set.
  assert.deepEqual(m.rows.map((r) => r.provider),
    ["claude_code", "openai_codex_cli", "grok_build", "google_antigravity", "zzz"]);
});

test("summarizeStatusBar totals only the readable counts", () => {
  const status = {
    "s1": { provider: "claude_code", allowance: 2, active: ["a"], in_use: 1 },
    "s2": { provider: "openai_codex_cli", allowance: 2, active: ["b", "c"], in_use: 2 },
  };
  const s = summarizeStatusBar(buildStatusBarModel({ status }));
  assert.equal(s.readable, true);
  assert.equal(s.totalInUse, 3);           // 1 + 2; the two idle OP-12 rows contribute nothing
  assert.equal(s.subscriptionCount, 4);    // two registered + two idle-at-zero rows
  assert.equal(s.atCapacityCount, 1);      // codex 2/2; grok/agy are 0/1, idle not at capacity
  assert.equal(s.unknownCount, 0);
});

test("summarizeStatusBar on an unreadable model reports unknowns, contributes no count", () => {
  const s = summarizeStatusBar(buildStatusBarModel({ status: null }));
  assert.equal(s.readable, false);
  assert.equal(s.totalInUse, 0);
  assert.equal(s.subscriptionCount, 0);
  assert.equal(s.unknownCount, LIVE_PROVIDERS.length);
});

// ---- the ceiling follows the FEED, not only the code-pinned map (spec-audit Md-4) ---------------
// U255 asked for a per-provider display ceiling SOURCED FROM THE FEED; the `.picker` sub-step closed
// it with a second hand-maintained JS map while `allowance_by_provider` — what the emitter computes
// from the operator's own live authorization — was dropped on the floor. An operator who narrows
// `terminals_per_subscription` was then shown a ceiling their config does not authorize.

test("an idle row uses the FEED's allowance for that provider, not the pinned cap", () => {
  const m = buildStatusBarModel({ status: {}, allowanceByProvider: { claude_code: 1 } });
  const claude = m.rows.find((r) => r.provider === "claude_code");
  assert.equal(claude.allowance, 1, "the operator narrowed this subscription to 1");
  assert.equal(claude.label, "0/1");
  // …and a provider the feed does not mention keeps its pinned cap rather than inheriting another's
  const codex = m.rows.find((r) => r.provider === "openai_codex_cli");
  assert.equal(codex.allowance, PROVIDER_ALLOWANCE.openai_codex_cli);
});

test("an UNREADABLE governor still narrows to the feed's allowance when one was read", () => {
  const m = buildStatusBarModel({ status: null, allowanceByProvider: { grok_build: 1, claude_code: 1 } });
  assert.equal(m.readable, false);
  assert.equal(m.rows.find((r) => r.provider === "claude_code").label, "—/1");
  assert.equal(m.rows.find((r) => r.provider === "grok_build").label, "—/1");
});

test("a malformed or absent feed allowance falls back to the pinned cap, never to zero", () => {
  for (const bad of [null, undefined, "2", { claude_code: "2" }, { claude_code: -1 },
    { claude_code: 2.5 }]) {
    const m = buildStatusBarModel({ status: {}, allowanceByProvider: bad });
    for (const p of LIVE_PROVIDERS) {
      const row = m.rows.find((r) => r.provider === p);
      assert.equal(row.allowance, PROVIDER_ALLOWANCE[p],
        `a malformed feed allowance (${JSON.stringify(bad)}) must not move ${p}'s ceiling`);
    }
  }
});

test("the feed NARROWS a ceiling and is clamped when it would raise one", () => {
  // RECORDED REVERSAL (U277, 18B close, spec-audit MINOR-1). This test previously asserted the
  // opposite for the upward direction — `grok_build: 5` displayed as `0/5` — on the reasoning that
  // "the FEED is authoritative about the operator's authorization". That is right downward and
  // wrong upward: the feed is `auth.terminals_for(p)` = min(config, code cap), and the CODE cap is
  // what the governor actually enforces, so a feed number above it cannot be authorization — it can
  // only be a fault or a forgery, and rendering it advertises concurrency every other surface will
  // refuse (invariant 21 / I-X3, and invariant 27's "visible" means visibly TRUE). The comment
  // above `PROVIDER_ALLOWANCE` claimed the pinned map "cannot drift upward"; until this close that
  // was a property of the map and not of the function that read past it.
  const m = buildStatusBarModel({ status: {}, allowanceByProvider: { grok_build: 5 } });
  const grok = m.rows.find((r) => r.provider === "grok_build");
  assert.equal(grok.allowance, PROVIDER_ALLOWANCE.grok_build, "clamped to the enforced cap");
  assert.equal(grok.label, "0/1");

  // …and narrowing is still honoured in full, which is what U255 asked for.
  const narrowed = buildStatusBarModel({ status: {}, allowanceByProvider: { claude_code: 1 } });
  assert.equal(narrowed.rows.find((r) => r.provider === "claude_code").label, "0/1");
});
