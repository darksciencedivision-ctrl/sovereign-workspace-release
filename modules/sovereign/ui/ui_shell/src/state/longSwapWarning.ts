import type { RouteOverride } from "../types/chat";

export const LONG_SWAP_WARNING =
  "A LONG run is active; QUICK/DEEP will make the model server swap models (about 50 s) and pause the LONG run.";

/**
 * Warn when the selected route is neither LONG nor STATUS while a LONG job is active.
 * Those routes make the model server swap models and pause the LONG run.
 */
export function longSwapWarning(
  route: RouteOverride | string,
  longActiveJob: string | null | undefined,
): string | null {
  if (!longActiveJob) return null;
  if (route === "LONG" || route === "STATUS") return null;
  return LONG_SWAP_WARNING;
}
