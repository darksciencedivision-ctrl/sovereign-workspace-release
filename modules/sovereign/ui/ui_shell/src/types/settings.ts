export type Theme = "dark" | "light";
export type PrivacyMode = "local-only" | "api-enabled";
export type ApprovalMode = "manual" | "auto";

export interface Settings {
  theme: Theme;
  defaultWorkspace: string;
  startupBehavior: "new-chat" | "restore-last";
  orchestrationProfile: string;
  approvalMode: ApprovalMode;
  evidenceLogsEnabled: boolean;
  memoryEnabled: boolean;
  auditTrailEnabled: boolean;
  privacyMode: PrivacyMode;
}

export const DEFAULT_SETTINGS: Settings = {
  theme: "dark",
  defaultWorkspace: "",
  startupBehavior: "restore-last",
  orchestrationProfile: "default",
  approvalMode: "manual",
  evidenceLogsEnabled: true,
  memoryEnabled: true,
  auditTrailEnabled: true,
  privacyMode: "local-only",
};
