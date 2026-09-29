import { useEffect, useState } from "react";
import { ChatInput } from "./components/ChatInput";
import { ChatWindow } from "./components/ChatWindow";
import { LongComposer } from "./components/LongComposer";
import { ModelSelector } from "./components/ModelSelector";
import { RouteSelector } from "./components/RouteSelector";
import { RunStatus } from "./components/RunStatus";
import { SettingsMenu } from "./components/SettingsMenu";
import { Sidebar } from "./components/Sidebar";
import { StatusBar } from "./components/StatusBar";
import { sovereignClient } from "./services/sovereignClient";
import { useChatState } from "./state/chatState";
import { composeLongRequest, EMPTY_LONG_OPTIONS } from "./state/longRequest";
import { longSwapWarning } from "./state/longSwapWarning";
import { useModelState } from "./state/modelState";
import { useSettingsState } from "./state/settingsState";
import type { EngineHealth } from "./types/api";
import { isActiveJobStatus } from "./types/chat";
import type { LongOptions } from "./types/long";

type Panel = "none" | "models" | "settings";

export default function App() {
  const {
    sessions,
    active,
    activeJob,
    routeOverride,
    loading,
    creating,
    submitting,
    cancelling,
    error,
    pollError,
    createChat,
    selectChat,
    sendMessage,
    cancelActiveJob,
    setRouteOverride,
    reloadSessions,
  } = useChatState();
  const {
    settings,
    settingsAvailable,
    settingsError,
    updateSettings,
    refreshSettings,
  } = useSettingsState();
  const {
    models,
    profile,
    loaded: modelsLoaded,
    saving: modelsSaving,
    error: modelsError,
    notice: modelsNotice,
    refresh: refreshModels,
    saveAssignments,
  } = useModelState();
  const [panel, setPanel] = useState<Panel>("none");
  const [engineHealth, setEngineHealth] = useState<EngineHealth | null>(null);
  const [longOptions, setLongOptions] = useState<LongOptions>(EMPTY_LONG_OPTIONS);
  const [longError, setLongError] = useState<string | null>(null);

  const jobActive =
    activeJob !== null && isActiveJobStatus(activeJob.status);
  const inputDisabled = submitting || jobActive || !active;
  const swapWarning = longSwapWarning(
    routeOverride,
    engineHealth?.longActiveJob,
  );

  useEffect(() => {
    let cancelled = false;
    const updateHealth = async () => {
      const health = await sovereignClient.health();
      if (!cancelled) setEngineHealth(health);
    };
    void updateHealth();
    const timer = window.setInterval(updateHealth, 10_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  // LONG: the chat input is the objective; the composer adds the model and the material, and
  // the request text the server parses is built here (never typed by the operator).
  const send = (text: string): boolean => {
    if (routeOverride !== "LONG") {
      void sendMessage(text);
      return true;
    }
    const composed = composeLongRequest(text, longOptions);
    if (!composed.ok) {
      setLongError(composed.error);
      return false; // keep the objective in the box
    }
    setLongError(null);
    void sendMessage(composed.text);
    setLongOptions({ ...longOptions, material: "" });
    return true;
  };

  const composer = (
    <div className="composer-stack">
      <RouteSelector
        value={routeOverride}
        disabled={inputDisabled}
        longRoute={engineHealth?.longRoute}
        onChange={setRouteOverride}
      />
      {swapWarning && (
        <div className="composer-warning" role="status">
          {swapWarning}
        </div>
      )}
      {routeOverride === "LONG" && (
        <LongComposer
          longRoute={engineHealth?.longRoute}
          options={longOptions}
          disabled={inputDisabled}
          error={longError}
          onChange={(next) => {
            setLongOptions(next);
            setLongError(null);
          }}
        />
      )}
      <ChatInput
        onSend={send}
        placeholder={
          routeOverride === "LONG" ? "Objective for the LONG run..." : undefined
        }
        disabled={inputDisabled}
        autoFocus={!active?.messages.length}
      />
      {jobActive && (
        <div className="composer-note">
          This session has an active run. Cancel it or wait for completion
          before sending another message.
        </div>
      )}
    </div>
  );

  return (
    <div className="app">
      <Sidebar
        sessions={sessions}
        activeId={active?.session_id ?? ""}
        onNewChat={() => void createChat()}
        onSelect={(id) => void selectChat(id)}
      />

      <main className="workspace">
        <div className="topbar">
          <button onClick={() => setPanel("models")}>Models</button>
          <button onClick={() => setPanel("settings")} aria-label="Settings">
            Settings
          </button>
        </div>

        {loading ? (
          <div className="idle-center">
            <div className="brand">SOVEREIGN</div>
            <div className="loading-note" role="status">
              Loading durable sessions…
            </div>
          </div>
        ) : !active ? (
          <div className="idle-center">
            <div className="brand">SOVEREIGN</div>
            <div className="connection-error" role="alert">
              {error ?? "No server session is available."}
            </div>
            <button
              className="retry-button"
              onClick={() => void reloadSessions()}
            >
              Reconnect
            </button>
          </div>
        ) : active.messages.length === 0 && !activeJob ? (
          <div className="idle-center">
            <div className="brand">SOVEREIGN</div>
            {error && (
              <div className="connection-error" role="alert">
                {error}
              </div>
            )}
            {composer}
          </div>
        ) : (
          <>
            <ChatWindow messages={active.messages} />
            <div className="run-dock">
              {error && (
                <div className="connection-error" role="alert">
                  {error}
                </div>
              )}
              <RunStatus
                job={activeJob}
                pollError={pollError}
                cancelling={cancelling}
                onCancel={() => void cancelActiveJob()}
              />
            </div>
            <div className="input-dock">{composer}</div>
          </>
        )}

        <StatusBar
          privacyMode={settings.privacyMode}
          settingsAvailable={settingsAvailable}
          engineHealth={engineHealth}
          routeOverride={routeOverride}
        />

        {panel === "models" && (
          <ModelSelector
            models={models}
            profile={profile}
            loaded={modelsLoaded}
            saving={modelsSaving}
            error={modelsError}
            notice={modelsNotice}
            onRefresh={() => void refreshModels()}
            onSave={saveAssignments}
            onClose={() => setPanel("none")}
          />
        )}
        {panel === "settings" && (
          <SettingsMenu
            settings={settings}
            productVersion={engineHealth?.engineVersion}
            settingsAvailable={settingsAvailable}
            settingsError={settingsError}
            onUpdate={updateSettings}
            onRefresh={() => void refreshSettings()}
            onClose={() => setPanel("none")}
          />
        )}
      </main>

      <span className="sr-only" aria-live="polite">
        {creating ? "Creating session" : ""}
        {submitting ? "Submitting message" : ""}
      </span>
    </div>
  );
}
