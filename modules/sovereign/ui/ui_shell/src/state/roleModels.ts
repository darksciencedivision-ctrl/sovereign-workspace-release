/**
 * `/v1/health` reports how each QUICK/DEEP/RESEARCH model is served (`role_models`). A model whose
 * GPU plan was refused still answers, on the slower default profile; the operator should know why
 * a route is slow. Returns a short note for the status bar, or undefined when nothing is degraded.
 */
export function roleModelsNote(value: unknown): string | undefined {
  if (typeof value !== "object" || value === null) return undefined;
  const report = value as { status?: unknown; models?: unknown };
  if (report.status !== "degraded") return undefined;
  const names: string[] = [];
  if (Array.isArray(report.models)) {
    for (const entry of report.models) {
      if (typeof entry !== "object" || entry === null) continue;
      const { model, status } = entry as { model?: unknown; status?: unknown };
      if (status === "degraded" && typeof model === "string") names.push(model);
    }
  }
  return names.length > 0
    ? `Slower default GPU profile: ${names.join(", ")}`
    : "Some models run on the slower default GPU profile";
}
