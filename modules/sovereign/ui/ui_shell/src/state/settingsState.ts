import { useCallback, useEffect, useRef, useState } from "react";
import { sovereignClient } from "../services/sovereignClient";
import { DEFAULT_SETTINGS, type Settings } from "../types/settings";

/**
 * Settings are owned by the product service. Defaults exist only to make the
 * disconnected shell render safely; they are never written to browser storage.
 */
export function useSettingsState() {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsAvailable, setSettingsAvailable] = useState(false);
  const latestSettings = useRef(settings);
  const lastAuthoritative = useRef(settings);
  const updateSequence = useRef(0);

  useEffect(() => {
    latestSettings.current = settings;
    document.documentElement.dataset.theme = settings.theme;
  }, [settings]);

  const refreshSettings = useCallback(async () => {
    const serverSettings = await sovereignClient.getSettings();
    if (serverSettings) {
      const authoritative = {
        ...DEFAULT_SETTINGS,
        ...serverSettings,
      };
      lastAuthoritative.current = authoritative;
      setSettings(authoritative);
      setSettingsAvailable(true);
      setSettingsError(null);
      return;
    }
    setSettingsAvailable(false);
    setSettingsError(
      "Service settings are unavailable; non-authoritative defaults are shown."
    );
  }, []);

  useEffect(() => {
    void refreshSettings();
  }, [refreshSettings]);

  const updateSettings = useCallback(
    (patch: Partial<Settings>) => {
      if (!settingsAvailable) return;
      const next = { ...latestSettings.current, ...patch };
      latestSettings.current = next;
      setSettings(next);
      setSettingsError(null);
      const sequence = ++updateSequence.current;
      void sovereignClient.updateSettings(next).then((result) => {
        if (sequence !== updateSequence.current) return;
        if (!result.ok) {
          setSettings(lastAuthoritative.current);
          setSettingsAvailable(false);
          setSettingsError(
            result.error ?? "The service did not accept the settings update."
          );
          return;
        }
        lastAuthoritative.current = next;
      });
    },
    [settingsAvailable]
  );

  return {
    settings,
    settingsAvailable,
    settingsError,
    updateSettings,
    refreshSettings,
  };
}
