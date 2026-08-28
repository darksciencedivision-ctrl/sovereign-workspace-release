import type { EngineHealth } from "../types/api";
import type { RouteOverride } from "../types/chat";
import type { PrivacyMode } from "../types/settings";

interface Props {
  privacyMode: PrivacyMode;
  settingsAvailable: boolean;
  engineHealth: EngineHealth | null;
  routeOverride: RouteOverride;
}

function engineText(health: EngineHealth | null): string {
  if (health === null) return "Engine checking…";
  if (!health.reachable) return "Engine not reachable";
  const degraded =
    health.status && health.status !== "ok" ? ` (${health.status})` : "";
  // The product version stays in this segment: it is the only place the
  // operator can read which engine actually answered.
  return health.engineVersion
    ? `Engine connected · ${health.engineVersion}${degraded}`
    : `Engine connected${degraded}`;
}

function privacyText(
  privacyMode: PrivacyMode,
  settingsAvailable: boolean,
): string {
  if (!settingsAvailable) return "Privacy state unavailable";
  return privacyMode === "local-only" ? "Local-only" : "API-enabled";
}

export function StatusBar({
  privacyMode,
  settingsAvailable,
  engineHealth,
  routeOverride,
}: Props) {
  const segments = [
    engineText(engineHealth),
    privacyText(privacyMode, settingsAvailable),
    engineHealth?.orchestrationMode ?? null,
    routeOverride,
  ].filter((segment): segment is string => Boolean(segment));

  return (
    <div className="statusbar" aria-label="Product status">
      {segments.map((segment) => (
        <span className="status-segment" key={segment}>
          {segment}
        </span>
      ))}
    </div>
  );
}
