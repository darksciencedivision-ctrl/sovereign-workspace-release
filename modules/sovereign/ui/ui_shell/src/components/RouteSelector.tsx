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

export function longUnavailableReason(longRoute?: LongRouteInfo): string | undefined {
  if (!longRoute) return "LONG availability is unknown (the engine health did not report it).";
  if (longRoute.error) return `LONG is not configured: ${longRoute.error}`;
  if (!longRoute.ready) {
    return "LONG needs the llama.cpp backend and its supervisor with the planned GPU/RAM split.";
  }
  return undefined;
}

export function RouteSelector({ value, disabled, longRoute, onChange }: Props) {
  const longReason = longUnavailableReason(longRoute);
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
              title={longReason ?? "Big-model run split into fresh-context chunks"}
            >
              {longReason ? "LONG (unavailable)" : "LONG"}
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
