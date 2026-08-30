"use strict";
/**
 * Where an in-Electron self-check writes its receipt (18B `.picker`, review round 1).
 *
 * WHY THIS EXISTS: the `.picker` unit re-ran the 16B and 16D self-checks as regressions, and each
 * one OVERWROTE the receipt of its own CLOSED gate in place — the first modification either file had
 * seen since the gate commit that recorded it. `PHASE16B_SELFCHECK.json` stopped describing the 16B
 * run at all (49 options became 61, the badge text changed). Directive §2.6: registers and evidence
 * reports are append-only (spec-audit/validator MEDIUM-2). Both receipts have been restored to their
 * gate-commit content.
 *
 * A regression run is still worth doing — it is how a closed gate's surface is kept honest — so the
 * fix is a path, not a prohibition: set `SHELL_SELFCHECK_RECEIPT_DIR` and the run writes its receipt
 * THERE instead, leaving the gate artifact untouched. Unset (the gate-run default) behaves exactly
 * as before.
 */
const path = require("path");

// LOCAL-01 F-6 (OD-34, the N-29 defect). This used to resolve to
// `<sow>/docs/evidence/receipts`, which is GIT-TRACKED - so writing a receipt dirtied the release
// candidate, and every builder BOOT after anyone used the product found a dirty tree. That is the
// N-16 defect class in a fourth lane, and OD-34 rules that it takes the N-16 remedy: runtime
// receipts move to the gitignored `.runtime/` lane.
//
// The move is also the right fix for the reason this file already existed: a re-run used to
// OVERWRITE a closed gate's receipt in place (MEDIUM-2). Now the default writes beside the run,
// and the gate artifacts under docs/evidence/receipts stay exactly as their gate commits left them
// - history, kept, never rewritten. `SHELL_SELFCHECK_RECEIPT_DIR` still overrides.
//
// `.runtime/` is gitignored (.gitignore:64) AND is a rejected runtime lane in
// tools/release/package_boundary_gate.py, so a receipt can neither be committed nor packaged.
const DEFAULT_DIR = path.resolve(__dirname, "..", "..", "..", ".runtime", "receipts");

/**
 * @param {string} name  the receipt's file name, e.g. "PHASE18B_PICKER_SELFCHECK.json"
 * @returns {string} the absolute path to write it to
 */
function receiptPath(name) {
  const override = String(process.env.SHELL_SELFCHECK_RECEIPT_DIR || "").trim();
  return path.resolve(override || DEFAULT_DIR, name);
}

module.exports = { receiptPath, DEFAULT_RECEIPT_DIR: DEFAULT_DIR };
