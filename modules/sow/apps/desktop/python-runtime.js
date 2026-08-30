"use strict";

/**
 * SINGLE RESOLUTION POINT for the Python interpreter this app spawns.
 *
 * EPC-01 P0-2. Nineteen product files spawned `py -3.12` directly — the SYSTEM
 * interpreter — while SOW's runtime dependency (`jsonschema`, twelve modules) was
 * declared only in requirements-dev.txt and provisioned by nothing. On a clean machine
 * with Python 3.12 and no jsonschema, every one of those spawns died on import.
 *
 * The fix is not to change what those files DO, it is to change what they DEFAULT to.
 * Every call site already accepted `opts.python` / `opts.pythonArgs` by injection; only
 * the literal default was wrong. This module owns that default and nothing else.
 *
 * Resolution order, first hit wins:
 *   1. SOW_PYTHON            — explicit override. The installer writes this; an operator
 *                              may set it. An override that does not exist is a hard
 *                              error rather than a silent fallback, because a wrong
 *                              interpreter fails later and more confusingly than a
 *                              missing one fails now.
 *   2. <repoRoot>/.venv      — the environment install.ps1 provisions from
 *                              modules/sow/requirements.txt.
 *   3. py -3.12              — the historical behaviour, preserved so a development tree
 *                              with no venv keeps working exactly as before.
 *
 * Case 3 is why this change does not move any existing test: with no venv and no
 * override, resolve() returns precisely what the call sites hardcoded before.
 */

const fs = require("fs");
const path = require("path");

/** Repo root = modules/sow, three levels above apps/desktop. */
const REPO_ROOT = path.resolve(__dirname, "..", "..");

/** Where install.ps1 provisions the runtime closure. */
function venvPython(repoRoot) {
  const exe = process.platform === "win32"
    ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
    : path.join(repoRoot, ".venv", "bin", "python");
  return exe;
}

/**
 * Resolve the interpreter and its leading arguments.
 *
 * @param {string} [repoRoot] defaults to modules/sow
 * @returns {{python: string, pythonArgs: string[], source: string}}
 */
function resolvePython(repoRoot = REPO_ROOT) {
  const override = process.env.SOW_PYTHON;
  if (override) {
    if (!fs.existsSync(override)) {
      throw new Error(
        `SOW_PYTHON points at a missing interpreter: ${override}. ` +
        `Unset it to fall back to the workspace virtualenv or the py launcher.`
      );
    }
    return { python: override, pythonArgs: [], source: "SOW_PYTHON" };
  }

  const venv = venvPython(repoRoot);
  if (fs.existsSync(venv)) {
    return { python: venv, pythonArgs: [], source: "venv" };
  }

  return { python: "py", pythonArgs: ["-3.12"], source: "py-launcher" };
}

/** Convenience: just the executable. */
function defaultPython(repoRoot) {
  return resolvePython(repoRoot).python;
}

/** Convenience: just the leading args. */
function defaultPythonArgs(repoRoot) {
  return resolvePython(repoRoot).pythonArgs;
}

module.exports = { resolvePython, defaultPython, defaultPythonArgs, venvPython, REPO_ROOT };
