import type { Settings } from "../types/settings";
import { DOCS_PATH } from "../version";
import { ValidationLab } from "./ValidationLab";

interface Props {
  settings: Settings;
  productVersion?: string;
  settingsAvailable: boolean;
  settingsError?: string | null;
  onUpdate: (patch: Partial<Settings>) => void;
  onRefresh: () => void;
  onClose: () => void;
}

export function SettingsMenu({
  settings,
  productVersion,
  settingsAvailable,
  settingsError,
  onUpdate,
  onRefresh,
  onClose,
}: Props) {
  return (
    <div className="panel-overlay" onClick={onClose}>
      <div
        className="panel"
        role="dialog"
        aria-label="Settings"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="close" onClick={onClose} aria-label="Close">
          ×
        </button>
        <h2>Settings</h2>

        {settingsError && (
          <div className="panel-error" role="alert">
            {settingsError}
            <button className="retry-inline" onClick={onRefresh}>
              Retry
            </button>
          </div>
        )}

        <div className="group">
          <div className="group-title">General</div>
          <div className="row">
            <label htmlFor="theme-setting">Theme</label>
            <select
              id="theme-setting"
              value={settings.theme}
              disabled={!settingsAvailable}
              onChange={(event) =>
                onUpdate({
                  theme: event.target.value as Settings["theme"],
                })
              }
            >
              <option value="dark">Dark</option>
              <option value="light">Light</option>
            </select>
          </div>
          <div className="row">
            <span>Session continuity</span>
            <span className="muted">Durable · restored from service</span>
          </div>
        </div>

        <div className="group">
          <div className="group-title">Orchestration</div>
          <div className="row">
            <span>Profile</span>
            <span className="muted">
              {settings.orchestrationProfile}
            </span>
          </div>
          <div className="row">
            <span>Promotion approval</span>
            <span className="muted">Human/operator only · fixed</span>
          </div>
          <div className="row">
            <span>Evidence logs</span>
            <span className="muted">Enabled · mandatory</span>
          </div>
          <div className="row">
            <span>Memory</span>
            <span className="muted">Enabled · durable service state</span>
          </div>
          <div className="row">
            <span>Audit trail</span>
            <span className="muted">
              Enabled · corruption-evident event chain
            </span>
          </div>
        </div>

        <div className="group">
          <div className="group-title">Privacy</div>
          <div className="row">
            <span>Mode</span>
            <span className="muted">Local-only · loopback fixed</span>
          </div>
        </div>

        <div className="group">
          <div className="group-title">Product</div>
          <div className="row">
            <span>Version</span>
            <span className="muted">
              {productVersion ?? "Unavailable from service health"}
            </span>
          </div>
          <div className="row">
            <span>Client contract</span>
            <span className="muted">{DOCS_PATH}</span>
          </div>
        </div>

        <ValidationLab />

        <div className="placeholder-note">
          Theme changes are persisted by the Sovereign service. Integrity,
          continuity, containment, and promotion controls are fixed product
          policies rather than decorative toggles.
        </div>
      </div>
    </div>
  );
}
