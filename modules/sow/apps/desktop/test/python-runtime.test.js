"use strict";

/**
 * EPC-01 P0-2 — the interpreter resolver.
 *
 * Nineteen product files used to hardcode `py -3.12`, the SYSTEM interpreter, for
 * seventeen Python entry points whose modules import `jsonschema` — a package nothing in
 * the install path provisioned. These tests pin the three properties that make the fix
 * safe rather than merely present:
 *
 *   1. With no venv and no override, resolution is BYTE-FOR-BYTE what the call sites
 *      hardcoded before. That is why this change moves no existing test.
 *   2. A provisioned venv wins over the launcher, with no leading args.
 *   3. SOW_PYTHON wins over both, and a SOW_PYTHON that does not exist is a loud error
 *      rather than a silent fallback — a wrong interpreter fails later and far more
 *      confusingly than a missing one fails now.
 */

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { resolvePython, venvPython } = require("../python-runtime");

function tmpRoot(name) {
  return fs.mkdtempSync(path.join(os.tmpdir(), `sow-pyrt-${name}-`));
}

function withoutOverride(fn) {
  const saved = process.env.SOW_PYTHON;
  delete process.env.SOW_PYTHON;
  try { return fn(); } finally {
    if (saved === undefined) delete process.env.SOW_PYTHON; else process.env.SOW_PYTHON = saved;
  }
}

test("with no venv and no override, resolution is exactly the historical py -3.12", () => {
  withoutOverride(() => {
    const root = tmpRoot("bare");
    const r = resolvePython(root);
    assert.strictEqual(r.python, "py");
    assert.deepStrictEqual(r.pythonArgs, ["-3.12"]);
    assert.strictEqual(r.source, "py-launcher");
  });
});

test("a provisioned venv wins over the py launcher and carries no leading args", () => {
  withoutOverride(() => {
    const root = tmpRoot("venv");
    const exe = venvPython(root);
    fs.mkdirSync(path.dirname(exe), { recursive: true });
    fs.writeFileSync(exe, "");
    const r = resolvePython(root);
    assert.strictEqual(r.python, exe);
    assert.deepStrictEqual(r.pythonArgs, []);
    assert.strictEqual(r.source, "venv");
  });
});

test("SOW_PYTHON outranks a present venv", () => {
  const root = tmpRoot("override");
  const exe = venvPython(root);
  fs.mkdirSync(path.dirname(exe), { recursive: true });
  fs.writeFileSync(exe, "");

  const override = path.join(root, "chosen-python.exe");
  fs.writeFileSync(override, "");

  const saved = process.env.SOW_PYTHON;
  process.env.SOW_PYTHON = override;
  try {
    const r = resolvePython(root);
    assert.strictEqual(r.python, override);
    assert.deepStrictEqual(r.pythonArgs, []);
    assert.strictEqual(r.source, "SOW_PYTHON");
  } finally {
    if (saved === undefined) delete process.env.SOW_PYTHON; else process.env.SOW_PYTHON = saved;
  }
});

test("a SOW_PYTHON that does not exist throws instead of silently falling back", () => {
  const root = tmpRoot("badoverride");
  const saved = process.env.SOW_PYTHON;
  process.env.SOW_PYTHON = path.join(root, "no-such-python.exe");
  try {
    assert.throws(() => resolvePython(root), /SOW_PYTHON points at a missing interpreter/);
  } finally {
    if (saved === undefined) delete process.env.SOW_PYTHON; else process.env.SOW_PYTHON = saved;
  }
});

test("no product file under apps/desktop hardcodes the interpreter any more", () => {
  const desktop = path.resolve(__dirname, "..");
  const skip = new Set(["node_modules", "test", "__pycache__"]);
  const offenders = [];

  (function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!skip.has(entry.name)) walk(path.join(dir, entry.name));
        continue;
      }
      if (!entry.name.endsWith(".js")) continue;
      const full = path.join(dir, entry.name);
      if (full === path.join(desktop, "python-runtime.js")) continue;
      const src = fs.readFileSync(full, "utf8");
      if (/["']py["']\s*,\s*\[\s*["']-3\.12["']/.test(src) || /\|\|\s*["']py["']/.test(src)) {
        offenders.push(path.relative(desktop, full).replace(/\\/g, "/"));
      }
    }
  })(desktop);

  assert.deepStrictEqual(
    offenders, [],
    "these files still hardcode the interpreter instead of defaulting through " +
    "python-runtime.js, so a provisioned venv would not be used:\n  " + offenders.join("\n  ")
  );
});
