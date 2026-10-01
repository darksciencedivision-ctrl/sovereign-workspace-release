/**
 * A stage the server reports as a bare identifier (`exact_counting`,
 * `local_evidence_retrieval_and_planning`) reads as words; a stage that is already text
 * (`waiting for LONG job job_1a2b`, whose id must stay intact) is shown as it is.
 */
export function stageLabel(stage: string | undefined): string | undefined {
  if (stage === undefined) return undefined;
  if (!/^[a-z0-9]+(?:_[a-z0-9]+)+$/.test(stage)) return stage;
  const words = stage.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
