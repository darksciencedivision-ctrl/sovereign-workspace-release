(function exposeModuleState(root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SWSModuleState = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function moduleStateFactory() {
  "use strict";

  function firstString() {
    for (const value of arguments) {
      if (typeof value === "string" && value) return value;
    }
    return "";
  }

  function projectModuleState(record, previous, stateMeta, urlForPort) {
    const current = record && typeof record === "object" ? record : {};
    const prior = previous && typeof previous === "object" ? previous : {};
    let state = String(current.state || current.status || "").toUpperCase();
    if (!stateMeta[state] && !state) state = "";
    const meta = stateMeta[state] || { cls: "badge-muted", label: state || "Unknown" };

    let reasonText = firstString(current.reason_code, current.reason, current.detail);
    if (current.runtime_present === false && !reasonText) {
      reasonText = "Runtime not installed: "
        + firstString(current.runtime_path, "path not declared");
    }
    const failedWithReason = (state === "FAILED" || state === "CONFIG_ERROR") && reasonText;
    const hideReason = (state === "READY" || state === "NOT_STARTED")
      && current.runtime_present !== false;
    const url = firstString(current.url, current.href);
    const port = current.port !== undefined && current.port !== null ? String(current.port) : "";
    const resolvedUrl = url || (port ? urlForPort(port) : prior._url || "");
    const endpointText = url || (port ? "port " + port : prior._endpointText || "—");
    return {
      state,
      meta,
      stateText: failedWithReason ? meta.label + ": " + reasonText : meta.label,
      reasonText: failedWithReason || hideReason ? "" : reasonText,
      resolvedUrl,
      endpointText,
      shouldCloseBrowser: (prior.state === "READY" || prior.state === "EXTERNAL")
        && state !== "READY" && state !== "EXTERNAL",
      stored: Object.assign({}, prior, current, {
        state: state || prior.state || "NOT_STARTED",
        _url: resolvedUrl,
        _endpointText: url || (port ? "port " + port : ""),
      }),
    };
  }

  return { projectModuleState };
}));
