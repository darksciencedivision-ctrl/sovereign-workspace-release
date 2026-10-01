import type { RouteOverride } from "../types/chat";
import type { LongRouteInfo } from "../types/long";

interface Props {
  value: RouteOverride;
  disabled?: boolean;
  /** From /v1/health. LONG is offered only when the server can run it here. */
  longRoute?: LongRouteInfo;
  onChange: (route: RouteOverride) => void;
}

const ROUTES: RouteOverride[] = [
  "AUTO",
  "STATUS",
  "QUICK",
  "DEEP",
  "RESEARCH",
  "CONTINUITY",
  "LONG",
];

function degradedModels(longRoute: LongRouteInfo): string {
  return longRoute.models
    .filter((m) => m.status === "degraded")
    .map((m) => `${m.model}: ${m.reason ?? "degraded"}`)
    .join("; ");
}

export function longUnavailableReason(longRoute?: LongRouteInfo): string | undefined {
  if (!longRoute) return "LONG availability is unknown (the engine health did not report it).";
  if (longRoute.error) return `LONG is not configured: ${longRoute.error}`;
  if (!longRoute.ready) {
    const degraded = degradedModels(longRoute);
    if (degraded) {
      return `No LONG model is served with its GPU/RAM plan (${degraded}). Restart the ` +
        "llama.cpp supervisor when enough VRAM is free.";
    }
    return "LONG needs the llama.cpp backend and its supervisor with the planned GPU/RAM split.";
  }
  return undefined;
}

/** Set when LONG can run but some of its models cannot (their runs would fail): say which. */
export function longDegradedNote(longRoute?: LongRouteInfo): string | undefined {
  if (!longRoute?.ready || !longRoute.degraded) return undefined;
  const degraded = degradedModels(longRoute) || longRoute.detail || "a model is degraded";
  return `LONG is degraded: ${degraded}. Runs on the other models still work.`;
}

export function RouteSelector({ value, disabled, longRoute, onChange }: Props) {
  const longReason = longUnavailableReason(longRoute);
  const longNote = longDegradedNote(longRoute);
  return (
    <label className="route-selector">
      <span>Route</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value as RouteOverride)}
        aria-label="Execution route"
      >
        {ROUTES.map((route) =>
          route === "LONG" ? (
            <option
              key={route}
              value={route}
              disabled={longReason !== undefined && value !== "LONG"}
              title={longReason ?? longNote ?? "Big-model run split into fresh-context chunks"}
            >
              {longReason ? "LONG (unavailable)" : longNote ? "LONG (degraded)" : "LONG"}
            </option>
          ) : (
            <option key={route} value={route}>
              {route}
            </option>
          )
        )}
      </select>
    </label>
  );
}
