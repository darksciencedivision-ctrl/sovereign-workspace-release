import { useCallback, useEffect, useState } from "react";
import { sovereignClient } from "../services/sovereignClient";
import type {
  ModelInfo,
  ModelProfile,
  RoleAssignment,
} from "../types/model";

export function useModelState() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [profile, setProfile] = useState<ModelProfile | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoaded(false);
    setNotice(null);
    const [serverModels, serverProfile] = await Promise.all([
      sovereignClient.getModels(),
      sovereignClient.getModelProfile(),
    ]);
    setModels(serverModels);
    setProfile(serverProfile);
    setError(
      serverProfile.name === "unavailable"
        ? "The service model profile is unavailable."
        : null
    );
    setLoaded(true);
  }, []);

  const saveAssignments = useCallback(
    async (assignments: RoleAssignment[]): Promise<boolean> => {
      setSaving(true);
      setError(null);
      setNotice(null);
      const result = await sovereignClient.setModelAssignments(assignments);
      if (!result.ok || !result.profile) {
        setError(result.error ?? "SOVEREIGN rejected the model assignments.");
        setSaving(false);
        return false;
      }
      setProfile(result.profile);
      setNotice(
        result.profile.restartRequired
          ? "Saved — restart required"
          : "Saved — assignments are active"
      );
      setSaving(false);
      return true;
    },
    []
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    models,
    profile,
    loaded,
    saving,
    error,
    notice,
    refresh,
    saveAssignments,
  };
}
