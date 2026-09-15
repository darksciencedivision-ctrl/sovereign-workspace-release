"use strict";
// CR-032: the renderer navigation allowlist. The window may only ever navigate to the packaged
// renderer under `rendererRoot`. A permitted target is a `file:` URL whose resolved filesystem path
// is CONTAINED by that root — this rejects remote schemes and every other local file, including
// encoded traversal (%2e%2e), sibling/parent paths, UNC/host paths, and alternate-drive paths.
const path = require("path");
const { fileURLToPath } = require("url");

function makeNavigationGuard(rendererRoot) {
  const root = path.resolve(rendererRoot);
  return function navigationIsPermitted(target) {
    let parsed;
    try {
      parsed = new URL(String(target || ""));
    } catch {
      return false;
    }
    if (parsed.protocol !== "file:") return false;
    let filePath;
    try {
      filePath = fileURLToPath(parsed); // decodes percent-escapes; UNC -> \\host\share path
    } catch {
      return false;
    }
    const resolved = path.resolve(filePath);
    const rel = path.relative(root, resolved);
    // Contained iff rel does not climb out (`..`) and did not switch drive/root (absolute rel).
    return rel !== "" && !rel.startsWith("..") && !path.isAbsolute(rel);
  };
}

module.exports = { makeNavigationGuard };
