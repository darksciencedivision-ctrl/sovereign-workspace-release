import type { RouteOverride } from "../types/chat";

export const LONG_SWAP_WARNING =
  "A LONG run is active and keeps the model to itself: QUICK, CONTINUITY, DEEP and RESEARCH questions wait in the queue and will run after the LONG job finishes. STATUS answers at once.";

/**
 * Warn when the selected route is neither LONG nor STATUS while a LONG job is active.
 * Those routes queue behind the LONG job (it runs uninterrupted) and start when it ends.
 */
export function longSwapWarning(
  route: RouteOverride | string,
  longActiveJob: string | null | undefined,
): string | null {
  if (!longActiveJob) return null;
  if (route === "LONG" || route === "STATUS") return null;
  return LONG_SWAP_WARNING;
}
