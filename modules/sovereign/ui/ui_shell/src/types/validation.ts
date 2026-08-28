/**
 * Validation Lab types — Phase UI-7.
 * The validation module does not exist engine-side yet; these types define
 * what the UI will accept when it does. No fake results are ever rendered.
 */
export interface ValidationStatus {
  connected: boolean;
  detail?: string;
}

export interface ValidationResult {
  id: string;
  created_at: string;
  kind: "benchmark" | "comparison";
  topic: string;
  summary: string;
  evidence_path?: string;
}
