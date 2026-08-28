"use strict";
/**
 * Picker/status-bar chrome (18B `.picker`, review round 1).
 *
 * These two functions carry authority CLAIMS the renderer used to make in un-testable template
 * literals, and both reviewers found the same two defects there:
 *   - BLOCKING-1 / M-3: a provider that enumerated NOTHING rendered the bare words "no options",
 *     with its recorded reason dropped at paint time — the silent gap operator directive §14 and
 *     decision row D-P18-3 both say cannot happen (a signed-out `grok`, an absent `agy`);
 *   - MINOR-4 / mutation E5: `PROV_LABEL` could be pointed at another provider's name with all 640
 *     desktop tests green — §14 forbids printing one provider's text under another's name.
 * Every test below goes RED on the single-line revert of the property it names.
 */
const test = require("node:test");
const assert = require("node:assert");
const { providerLabel, optionKey, providerGroupHtml, PROVIDER_LABEL } = require("../renderer/picker-chrome.js");

// the renderer's own escaper, so these tests exercise what actually paints
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const group = (over) => Object.assign(
  { provider: "grok_build", display: "Grok Build", status: { available: false, reason: "" } }, over);

test("each provider's chip is its OWN name, and all four live providers have one", () => {
  assert.strictEqual(providerLabel("claude_code"), "claude");
  assert.strictEqual(providerLabel("openai_codex_cli"), "codex");
  assert.strictEqual(providerLabel("grok_build"), "grok");
  assert.strictEqual(providerLabel("google_antigravity"), "agy");
  // …and no two providers share a label — the §14 defect is a collision, not an absence
  const labels = Object.values(PROVIDER_LABEL);
  assert.strictEqual(new Set(labels).size, labels.length, "two providers share one chip label");
});

test("an unknown provider falls back to its RAW id, never to a neighbour's label", () => {
  assert.strictEqual(providerLabel("some_future_provider"), "some_future_provider");
  assert.strictEqual(providerLabel(""), "");
  assert.strictEqual(providerLabel(undefined), "");
  // a prototype key must not resolve to a function/name from Object.prototype
  assert.strictEqual(providerLabel("constructor"), "constructor");
  assert.strictEqual(providerLabel("toString"), "toString");
});

test("separately decoded flat and grouped options join by stable provider/model identity", () => {
  const flat = { provider: "openai_codex_cli", model_slug: "gpt-5.6-sol", label: "ChatGPT 5.6 Sol" };
  const grouped = JSON.parse(JSON.stringify(flat));
  assert.notStrictEqual(grouped, flat);
  assert.strictEqual(optionKey(grouped), optionKey(flat));
  assert.notStrictEqual(optionKey({ ...flat, model_slug: "gpt-5.5" }), optionKey(flat));
});

test("a provider that enumerated NOTHING renders its reason, not the words 'no options'", () => {
  const reason = "grok CLI is signed out — run `grok login` (this shell never handles the credential)";
  const html = providerGroupHtml(group({ status: { available: false, reason } }), "", esc);
  assert.match(html, /pk-greason/);
  assert.ok(html.includes(esc(reason)), "the group's recorded reason is not painted");
  assert.ok(!html.includes("no options"), "the shape was printed where the explanation belongs");
});

test("a group whose options are all greyed still states the reason ONCE, above them", () => {
  const reason = "live operation not authorized for 'grok_build' (register OP-6)";
  const html = providerGroupHtml(group({ status: { available: false, reason } }),
    '<div class="pk-opt greyed">grok-4.5</div>', esc);
  assert.strictEqual((html.match(/pk-greason/g) || []).length, 1);
  assert.ok(html.indexOf("pk-greason") < html.indexOf("pk-opt"), "the reason must precede the rows");
  assert.match(html, /grok-4\.5/);
});

test("an AVAILABLE group states no reason — an available provider is not accused", () => {
  const html = providerGroupHtml(
    group({ status: { available: true, reason: "authorized" } }), '<div class="pk-opt">x</div>', esc);
  assert.ok(!html.includes("pk-greason"), "an available group painted a refusal line");
  assert.ok(!html.includes("no options"));
});

test("zero options and NO reason still says something, rather than rendering an empty group", () => {
  const html = providerGroupHtml(group({ status: null }), "", esc);
  assert.match(html, /no options/);
  assert.ok(!html.includes("pk-greason"), "an empty reason must not paint as an empty accusation");
});

test("the group's own text is escaped — the reason is untrusted input (invariant 29)", () => {
  const html = providerGroupHtml(
    group({ display: '<img src=x onerror="a">', status: { available: false, reason: "<b>&</b>" } }),
    "", esc);
  assert.ok(!html.includes("<img"), "an unescaped display title reached the DOM");
  assert.ok(!html.includes("<b>"), "an unescaped reason reached the DOM");
  assert.match(html, /&lt;b&gt;&amp;&lt;\/b&gt;/);
});

test("a group with no display falls back to its provider id, and never throws on a null group", () => {
  assert.match(providerGroupHtml({ provider: "grok_build" }, "", esc), /grok_build/);
  assert.match(providerGroupHtml(null, "", esc), /pk-group/);
});
