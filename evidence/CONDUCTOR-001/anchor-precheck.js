"use strict";
/* SW-CONDUCTOR-001 Phase 3 pre-check: every main.js anchor the two mutation harnesses splice
 * against must exist EXACTLY ONCE in the edited main.js before the Phase 4 re-pin. Anchor strings
 * below are transcribed from the harness sources read this run:
 *   pane_input_bypass_mutations.js :327-337, :375, :401-413
 *   system_pane_write_mutations.js :436, :441, :470, :472, :489-491, :493, :501-502, :505, :512, :514
 * This script is evidence tooling, not product code; it changes nothing. */
const fs = require("node:fs");
const ROOT = "D:\\production software 3\\release-worktree\\modules\\sow";
const main = fs.readFileSync(ROOT + "\\apps\\desktop\\main.js", "utf8");
const count = (n) => main.split(n).length - 1;

const checks = [
  // ---- harness 1 (pane_input_bypass_mutations.js) ----
  ["H1 IN_HANDLER", "    return manager.write(id, data);\n  });", 1],
  ["H1 HANDLER_TOP", '  ipcMain.handle("pane:input", (_e, id, data) => {', 1],
  ["H1 AFTER_RESUME", "function makeWindow() {", 1],
  ["H1 BEFORE_INPUT", "    handleOperatorResumeInput(event, input);", 1],
  ["H1 RESUME bare (decl + the one call)", "handleOperatorResumeInput(event, input)", 2],
  ["H1 REAL_DISARM", '    conductorVoiceAuthority.disarm("electron_main_before_input_event", { key_kind: kind });', 1],
  ["H1 residue declaration (G anchor)", "function clearConductorInputResidue(why) {", 1],
  ["H1 residue name total", "clearConductorInputResidue", 4],
  ["H1 X1 pane:focus", 'ipcMain.handle("pane:focus", (_e, id) => { panes.focus(id);', 1],
  ["H1 X2 pane:maximize", 'ipcMain.handle("pane:maximize", (_e, id) => { panes.maximize(id);', 1],
  ["H1 X3 pane:resize", 'ipcMain.handle("pane:resize", (_e, id, cols, rows) => {', 1],
  ["H1 X4 pane:close", 'ipcMain.handle("pane:close", (_e, id) => {', 1],
  // ---- harness 2 (system_pane_write_mutations.js), MAIN-targeted rows only ----
  ["H2 M1", "  return (await paneWriter.writePrompt(paneId, prompt)).written;", 1],
  ["H2 M2", "  return paneWriter.notifyNode(nodeId, prompt);", 1],
  ["H2 M5", "  paneScreen: paneScreenFromWindow(readinessWindow),", 1],
  ["H2 M7", "const runConductorReadiness = createConductorReadiness({", 1],
  ["H2 M8", "  writeRefusal: (paneId) => paneWriteRefusalFor(paneId),", 1],
  ["H2 P27", 'process.on("unhandledRejection", (reason) => exitOnUnrecoverableFault("unhandledRejection", reason));\n'
    + 'process.on("uncaughtException", (error) => exitOnUnrecoverableFault("uncaughtException", error));\n', 1],
  ["H2 P28", "  for (const key of RENDERER_SPEC_ALLOWED_KEYS) {\n    if (key in source) clean[key] = source[key];\n  }", 1],
  ["H2 P29", "{ ...sanitizeRendererSpec(spec), env: scrubCredentialEnv(process.env) }", 1],
  ["H2 P30", '  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));\n', 1],
  ["H2 P31", "    event.preventDefault();\n", 1],
  // ---- graded-suite invariants my wiring must not move ----
  ["write-site counter (must stay 3)", null, 3], // regex below
  ["no new ipcMain.handle beyond 29", null, 29],
];

let bad = 0;
for (const [label, needle, expected] of checks) {
  let actual;
  if (needle === null && label.startsWith("write-site")) {
    actual = (main.match(/manager\s*\??\.\s*write\s*\(/g) || []).length;
  } else if (needle === null) {
    actual = (main.match(/ipcMain\.handle\("/g) || []).length;
  } else {
    actual = count(needle);
  }
  const ok = actual === expected;
  if (!ok) bad += 1;
  console.log(`${ok ? "OK  " : "BAD "} ${label}: ${actual} (expected ${expected})`);
}
console.log(bad === 0 ? "ALL ANCHOR CHECKS OK" : `${bad} ANCHOR CHECK(S) BAD`);
process.exit(bad === 0 ? 0 : 1);
