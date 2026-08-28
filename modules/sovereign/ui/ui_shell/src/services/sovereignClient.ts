/**
 * The sole browser-to-product boundary. Production always uses the live
 * same-origin `/v1` service; there is no runtime stub selection.
 *
 * `VITE_SOVEREIGN_BACKEND_URL` is retained only as an explicit development
 * override for running Vite separately from the loopback product service.
 */
import { createHttpTransport } from "./httpTransport";
import type { SovereignTransport } from "./transport";

export type BackendMode = "live";
export type {
  JobResult,
  ModelAssignmentResult,
  OkResult,
  SessionResult,
  SessionsResult,
  SubmissionResult,
} from "./transport";

const developmentOverride =
  import.meta.env.DEV && import.meta.env.VITE_SOVEREIGN_BACKEND_URL
    ? String(import.meta.env.VITE_SOVEREIGN_BACKEND_URL)
    : "";

const transport: SovereignTransport =
  createHttpTransport(developmentOverride.replace(/\/+$/, ""));

export const sovereignClient: SovereignTransport & {
  getBackendMode(): BackendMode;
} = {
  getBackendMode: () => "live",
  sendMessage: (input, sessionId, routeOverride) =>
    transport.sendMessage(input, sessionId, routeOverride),
  getJob: (jobId) => transport.getJob(jobId),
  cancelJob: (jobId) => transport.cancelJob(jobId),
  createSession: () => transport.createSession(),
  getChatHistory: () => transport.getChatHistory(),
  loadSession: (sessionId) => transport.loadSession(sessionId),
  getModels: () => transport.getModels(),
  getModelProfile: () => transport.getModelProfile(),
  setModelAssignments: (assignments) =>
    transport.setModelAssignments(assignments),
  getSettings: () => transport.getSettings(),
  updateSettings: (settings) => transport.updateSettings(settings),
  health: () => transport.health(),
  getValidationStatus: () => transport.getValidationStatus(),
  runBenchmark: (topic, kind) => transport.runBenchmark(topic, kind),
  getValidationResults: () => transport.getValidationResults(),
  exportEvidence: () => transport.exportEvidence(),
};
