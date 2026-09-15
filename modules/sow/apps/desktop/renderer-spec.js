"use strict";
// CR-039: protocol validation for renderer-supplied pane specs, split out of main.js into an
// independently testable module. Pure: given a spec and the allow-list, returns the allow-listed
// subset (`clean`) and the names of any refused keys (`refused`). Logging of refusals stays in
// main.js so this core carries no side effects.
function sanitizeRendererSpec(spec, allowedKeys) {
  const source = spec && typeof spec === "object" ? spec : {};
  const clean = {};
  for (const key of allowedKeys) {
    if (key in source) clean[key] = source[key];
  }
  const refused = Object.keys(source).filter((k) => !allowedKeys.includes(k));
  return { clean, refused };
}

module.exports = { sanitizeRendererSpec };
