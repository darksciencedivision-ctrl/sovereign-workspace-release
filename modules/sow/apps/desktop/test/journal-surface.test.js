"use strict";
/** F-29 SOURCE PINS: weaker than a rendered/live acceptance; there is no DOM harness. */
const {test}=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const renderer=fs.readFileSync(path.resolve(__dirname,"../renderer/renderer.js"),"utf8");
const html=fs.readFileSync(path.resolve(__dirname,"../renderer/index.html"),"utf8");
const executable=s=>s.replace(/\/\*[\s\S]*?\*\//g,"").split("\n").filter(l=>!/^\s*\/\//.test(l)).join("\n");
function honesty(source) {
  const s=executable(source);
  assert.match(s,/d\.candidate\.self_published === false/);
  assert.match(s,/d\.candidate\.source/);
  assert.match(s,/self_published: false/);
  assert.match(s,/U58 OWED/);
}
test("F-29 source pins: results use the conductor transcript in normal document flow",()=>{
  const css=html.match(/#conductor-bar\s*\{([^}]+)\}/)[1];
  assert.doesNotMatch(css,/fixed|absolute/);assert.match(css,/flex:\s*none/);
  assert.doesNotMatch(html,/id="conductor-delegations"/);
  assert.match(executable(renderer),/barResize\.observe\(conductorBar\)/);
  assert.match(executable(renderer),/for \(const \{ fit \} of terms\.values\(\)\)/);
  assert.match(executable(renderer),/delegationTurns\.push/);
  assert.match(executable(renderer),/if \(turn\.row\) \{ list\.appendChild\(turn\.row\)/);
});
test("F-29 source pins: later transcript pushes retain capped observed results",()=>{
  const s=executable(renderer);
  assert.match(s,/\[\.\.\.turns, \.\.\.delegationTurns\]/);
  assert.match(s,/delegationTurns\.length > 200/);
  assert.match(s,/render\(lastTranscriptTurns\)/);
});
test("F-29 source pins: honesty, refusal, redaction and truncation remain visible",()=>{
  honesty(renderer);
  const s=executable(renderer);
  for(const r of [/res && res\.reason/,/d\.refused\.reason/,/d\.delivered !== true/,
    /d\.answered !== true/,/d\.candidate\.truncated/,/TRUNCATED observed pane output/,
    /d\.candidate\.redaction_kinds/,/d\.journal_error/]) assert.match(s,r);
});
test("F-29 source pins: attachment rule and availability reason remain readable",()=>{
  assert.match(html,/id="conductor-view-rule"/);assert.match(html,/\/workspace/);
  assert.match(html,/#conductor-delegate-why\s*\{[^}]*overflow-wrap:\s*anywhere/);
  assert.match(html,/#conductor-form\s*\{[^}]*flex-wrap:\s*wrap/);
  assert.match(html,/placeholder="Message the Conductor/);
  assert.doesNotMatch(executable(renderer),/delegateBtn\.disabled\s*=/);
});
test("F-29 mutation control: removing the self_published branch fails the honesty source pin",()=>{
  honesty(renderer);
  const changed=renderer.replace("d.candidate.self_published === false","true");
  assert.notEqual(changed,renderer);assert.throws(()=>honesty(changed));
});

// SW-JOURNAL-001-A1 F-31 SOURCE PINS. These do not replace the operator's rendered acceptance.
const region = (source, from, to) => {
  const start = source.indexOf(from), end = source.indexOf(to, start);
  assert.ok(start >= 0 && end > start, `missing source region: ${from}`);
  return executable(source.slice(start, end));
};
function toggleRefitPin(source) {
  const toggle = region(source, "  function setTranscriptCollapsed(", "  transcriptToggle.addEventListener");
  assert.match(toggle, /list\.hidden = collapsed/);
  assert.match(toggle, /refitConductorTerminals\(\);/);
  assert.doesNotMatch(toggle, /if\s*\(/, "the refit must apply to both toggle directions");
  const fit = region(source, "  function refitConductorTerminals()", "  const conductorBar =");
  assert.match(fit, /requestAnimationFrame\(/);
  assert.match(fit, /for \(const \{ fit \} of terms\.values\(\)\)/);
  assert.match(fit, /fit\.fit\(\)/);
}
test("F-31 source pins: native keyboard toggle controls an initially hidden transcript", () => {
  assert.match(html, /<button id="conductor-transcript-toggle" type="button" aria-controls="conductor-transcript"\s+aria-expanded="false"/);
  assert.match(html, /<div id="conductor-transcript"[^>]* hidden>/);
  assert.match(executable(renderer), /let transcriptCollapsed = true/);
  assert.match(executable(renderer), /if \(!input \|\| !sendBtn \|\| !list \|\| !transcriptToggle\)/);
  assert.match(executable(renderer), /transcriptToggle\.addEventListener\("click", \(\) => \{\s+setTranscriptCollapsed\(!transcriptCollapsed\)/);
  assert.match(executable(renderer), /transcriptToggle\.setAttribute\("aria-expanded", String\(!collapsed\)\)/);
  assert.match(html, /#conductor-transcript-toggle:focus-visible\s*\{[^}]*outline:/);
});
test("F-31 source pins: both toggle directions and bar resizes refit existing terminals", () => {
  toggleRefitPin(renderer);
  assert.match(executable(renderer), /new ResizeObserver\(refitConductorTerminals\)/);
});
test("F-31 source pins: collapsed summary reports received results, refusals, notices and more markers", () => {
  const summary = region(renderer, "  function updateTranscriptSummary()", "  function setTranscriptCollapsed(");
  for (const pin of [/transcriptResults\} results/, /transcriptRefusals \+ transcriptChatRefusals\} refused/,
    /transcriptNotices \+ transcriptChatNotices\} notices/, /transcriptLines\} lines/, /Expand: more details \+ markers/]) assert.match(summary, pin);
  assert.match(executable(renderer), /transcriptResults \+= \(res && res\.delegations \|\| \[\]\)\.filter\(d => d\.answered === true\)\.length/);
  assert.match(executable(renderer), /if \(refused\) transcriptRefusals \+= 1/);
  assert.match(executable(renderer), /if \(cls === "warn" \|\| cls === "bad"\) transcriptNotices \+= 1/);
  assert.match(executable(renderer), /transcriptLines = combined\.length;\s+updateTranscriptSummary\(\)/);
});
test("F-31 source pins: every governed refusal path feeds the collapsed refusal count", () => {
  const s = executable(renderer);
  for (const pin of [/not dispatched[^\n]+, true\)/, /pane write REFUSED[^\n]+, true\)/,
    /not delivered[^\n]+, true\)/, /delegate unavailable[^\n]+, true\)/,
    /Delegate \(it reads the same box as Send\)"\, true\)/,
    /delegation channel refused[^\n]+, true\)/]) assert.match(s, pin);
});
test("F-31 source pins: collapse only hides retained details and preserves provenance and reasons", () => {
  honesty(renderer);
  const toggle = region(renderer, "  function setTranscriptCollapsed(", "  transcriptToggle.addEventListener");
  assert.doesNotMatch(toggle, /remove|replaceChildren|textContent|innerHTML|render\(/);
  assert.match(toggle, /list\.hidden = collapsed/);
  for (const pin of [/d\.refused\.reason/, /TRUNCATED observed pane output/, /d\.journal_error/,
    /source: observed_pane_output; self_published: false; U58 OWED/]) assert.match(executable(renderer), pin);
});
test("F-31 source pins: collapsed control is one line and expanded details remain bounded and scrollable", () => {
  assert.match(html, /#conductor-transcript-toggle\s*\{[^}]*white-space:\s*nowrap/);
  assert.match(html, /#conductor-transcript\[hidden\]\s*\{\s*display:\s*none/);
  assert.match(html, /#conductor-transcript\s*\{[^}]*max-height:\s*25vh;[^}]*overflow-y:\s*auto/);
});
test("F-31 source pins: remembered choice is optional with a collapsed fallback and no new IPC", () => {
  const state = region(renderer, "  let transcriptCollapsed = true;", "  let lastTranscriptTurns = [];");
  assert.match(state, /try \{ transcriptCollapsed = localStorage\.getItem\("conductor-transcript-state"\) !== "expanded"; \}\s+catch/);
  assert.match(state, /try \{ localStorage\.setItem\("conductor-transcript-state", transcriptCollapsed \? "collapsed" : "expanded"\); \}\s+catch/);
  assert.doesNotMatch(state, /ipcRenderer|S\.|invoke\(/);
});
test("F-31 mutation control: removing the toggle refit call fails its source pin", () => {
  toggleRefitPin(renderer);
  const anchor = "    updateTranscriptSummary();\n    refitConductorTerminals();";
  assert.equal(renderer.split(anchor).length - 1, 1);
  const mutant = renderer.replace(anchor, "    updateTranscriptSummary();");
  assert.throws(() => toggleRefitPin(mutant));
  assert.equal(fs.readFileSync(path.resolve(__dirname,"../renderer/renderer.js"),"utf8"), renderer);
});

test("F-31 source pins: conductor send refusals and system notices also feed the collapsed summary", () => {
  assert.match(executable(renderer), /transcriptChatRefusals = turns\.filter\(t => t\.dir === "out" && t\.error && t\.submitted !== true\)\.length/);
  assert.match(executable(renderer), /transcriptChatNotices = turns\.filter\(t => t\.dir === "sys"\)\.length/);
});
