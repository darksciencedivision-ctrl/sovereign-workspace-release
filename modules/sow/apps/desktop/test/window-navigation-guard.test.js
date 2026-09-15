"use strict";
/**
 * W-30 — the two navigation escapes Electron leaves open by default.
 *
 * R-04, CONFIRMED on this host: a grep of `main.js` returned NEITHER `setWindowOpenHandler` NOR a
 * `will-navigate` listener. The review's Electron triage (section 13.3) measured what that costs and
 * what it does not:
 *
 *   - `window.open` / navigation escapes are "not reachable in normal operation, but NOT MITIGATED".
 *     There is no browsing surface (`loadFile` only, zero occurrences of `window.open` repo-wide),
 *     and the CSP is `script-src 'self'` — but `default-src` does NOT constrain top-level
 *     navigation, so the CSP is not the control people assume it is.
 *   - These two lines are the zero-cost half of the Electron exposure. The upgrade to 43.4.0 is
 *     semver-major with a node-pty ABI rebuild and stays in Tier 7; section 13.3's verdict is that
 *     the jump is "moderate, not emergency" PROVIDED the renderer-chooses-the-executable defect is
 *     fixed, which W-29 did. These close two advisory classes outright without the rebuild.
 *
 * WHAT THIS DOES NOT CLAIM. The permitted set is `file://`, which is the review's own recommended
 * shape. A navigation to some OTHER local file is therefore still permitted: the renderer stays
 * sandboxed with `contextIsolation`, so the value of that is low, and the advisory class being
 * closed is escape to REMOTE content. Recorded rather than described as total.
 *
 * EVIDENCE STRENGTH: these are SOURCE PINS, the weaker half, for the reason
 * `runtime-honesty-wiring.test.js` gives — `main.js` cannot be required in a test (U338), it pulls
 * in electron. They run against an executable-only view with comments blanked, so this file's own
 * prose cannot satisfy them. The behaviour is graded by mutation rows P30/P31, which revert each
 * guard independently and must go RED.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const MAIN = fs.readFileSync(path.resolve(__dirname, "..", "main.js"), "utf8");

const slice = (source, from, to) => {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert.ok(start > 0 && end > start, `could not locate ${from} … ${to}`);
  return source.slice(start, end);
};

const executableOnly = (region) =>
  region.replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n").filter((line) => !/^\s*\/\//.test(line)).join("\n");

const windowSetup = () => executableOnly(slice(MAIN, "function makeWindow() {", "win.loadFile("));

test("W-30 NEGATIVE: `window.open` from the renderer cannot open a window at all", () => {
  const region = windowSetup();
  assert.match(region, /setWindowOpenHandler\(/,
    "no setWindowOpenHandler: Electron's default opens a real BrowserWindow for any window.open() "
    + "the renderer calls, and this shell renders untrusted PTY output into its DOM");
  assert.match(region, /setWindowOpenHandler\(\s*\(\)\s*=>\s*\(\{\s*action:\s*"deny"\s*\}\)\s*\)/,
    "the handler must deny unconditionally — an allow-list of URLs is a browsing surface, and this "
    + "app has none");
});

test("W-30 NEGATIVE: a navigation away from the app's own document is CANCELLED", () => {
  const region = windowSetup();
  assert.match(region, /on\("will-navigate"/,
    "no will-navigate listener: the CSP's script-src does not constrain top-level navigation, so "
    + "nothing stops the renderer navigating the window to remote content");
  assert.match(region, /event\.preventDefault\(\)/,
    "a will-navigate listener that does not preventDefault() observes the escape instead of "
    + "stopping it");
  // The decision must be a REFUSAL by default: permitted is the narrow case, denial the fallthrough.
  assert.match(region, /navigationIsPermitted/,
    "the permit decision must be a named predicate, so a mutation can revert it and be graded");
});

test("W-30 POSITIVE: the packaged renderer loads and OTHER file URLs are refused (CR-032)", () => {
  // CR-032 tightened this guard from `startsWith("file://")` (which permitted ANY local file) to a
  // contained-renderer-root check, extracted into navigation-guard.js so it is exercised directly.
  const predicate = executableOnly(slice(MAIN, "const navigationIsPermitted", "\nfunction makeWindow"));
  assert.match(predicate, /makeNavigationGuard\(/,
    "the permit decision must be the extracted, mutation-gradable navigation guard");
  const { makeNavigationGuard } = require("../navigation-guard");
  const rroot = path.resolve("C:/app/renderer");
  const guard = makeNavigationGuard(rroot);
  assert.ok(guard("file:///C:/app/renderer/index.html"),
    "the app's own packaged renderer must still load");
  assert.ok(!guard("file:///C:/app/secret.txt"),
    "a sibling local file must be refused (CR-032: not any file:// URL)");
  assert.ok(!guard("https://evil.example/x"), "remote content must be refused");
});

test("W-30: a denied navigation is observable, without reproducing the URL", () => {
  const region = windowSetup();
  // Invariant 27 — a capability being refused must be visible. But a URL from a compromised
  // renderer is attacker-chosen text and may carry a token in a query string, so the SCHEME is
  // logged and the URL is not, the same way section 2.2 logs key names and never values.
  assert.ok(!/log\(`renderer navigation DENIED: \$\{url\}`\)/.test(region),
    "the full URL must not be logged — it is attacker-chosen and may carry credentials");
  assert.match(region, /navigation DENIED/,
    "a refusal nobody can see is not observable state");
});
