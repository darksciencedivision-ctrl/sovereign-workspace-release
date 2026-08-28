export type ModelSource = "local" | "api";
export type ModelStatus = "available" | "unavailable" | "unknown";

/**
 * Engine roles — VERIFIED against the engine on 2026-07-04:
 * - repos/sovereign/synthesis/model_hierarchy.json (schema 1.0)
 * - repos/sovereign/synthesis/synth_king.py (role contract 2.5G)
 * - repos/sovereign/claim_arbitrator.py (parses [ROLE Rn] dialog tags)
 * The earlier directive list (Primary/Reviewer/Critic/Verifier/Researcher/
 * Coder) does not exist in engine code and was replaced by these.
 */
export type DebateRole =
  | "KING_SYNTHESIZER"
  | "ALPHA_ADVOCATE"
  | "ALPHA_SKEPTIC"
  | "BETA_ADVOCATE"
  | "BETA_SKEPTIC"
  | "ALPHA_RECONCILER"
  | "BETA_RECONCILER"
  | "CROSS_CRITIC"
  | "CROSS_EXAMINER";

export type CluRole =
  | "CLU_ANALYZER"
  | "CLU_ARCHITECT"
  | "CLU_CODER"
  | "CLU_TESTER"
  | "CLU_AUDITOR"
  | "CLU_BENCHMARK"
  | "CLU_PROMOTER";

export type ConfigurableModelRole =
  | "PRIMARY_REASONER"
  | "ADVERSARIAL_CHALLENGER"
  | "CRITIC"
  | "SYNTHESIZER";

export type ModelRole = ConfigurableModelRole | "EMBEDDING_MODEL";

export type EngineRole = DebateRole | CluRole;

export const CORE_DEBATE_ROLES: DebateRole[] = [
  "KING_SYNTHESIZER",
  "ALPHA_ADVOCATE",
  "ALPHA_SKEPTIC",
  "BETA_ADVOCATE",
  "BETA_SKEPTIC",
];

export const ADVANCED_DEBATE_ROLES: DebateRole[] = [
  "ALPHA_RECONCILER",
  "BETA_RECONCILER",
  "CROSS_CRITIC",
  "CROSS_EXAMINER",
];

export const CLU_ROLES: CluRole[] = [
  "CLU_ANALYZER",
  "CLU_ARCHITECT",
  "CLU_CODER",
  "CLU_TESTER",
  "CLU_AUDITOR",
  "CLU_BENCHMARK",
  "CLU_PROMOTER",
];

export const ALL_ENGINE_ROLES: EngineRole[] = [
  ...CORE_DEBATE_ROLES,
  ...ADVANCED_DEBATE_ROLES,
  ...CLU_ROLES,
];

export interface ModelInfo {
  id: string;
  name: string;
  source: ModelSource;
  provider?: string; // API models only
  status: ModelStatus;
  apiKeyConfigured?: boolean; // API models only; never expose the key itself
}

export interface RoleAssignment {
  role: ModelRole;
  modelId: string;
}

export interface ModelProfile {
  name: string;
  assignments: RoleAssignment[];
  mutable?: boolean;
  editableRoles?: ConfigurableModelRole[];
  restartRequired?: boolean;
}
