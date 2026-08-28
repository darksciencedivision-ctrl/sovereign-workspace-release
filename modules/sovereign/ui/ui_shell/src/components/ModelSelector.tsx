import { useEffect, useMemo, useState } from "react";
import type {
  ConfigurableModelRole,
  ModelInfo,
  ModelProfile,
  RoleAssignment,
} from "../types/model";

interface Props {
  models: ModelInfo[];
  profile: ModelProfile | null;
  loaded: boolean;
  saving?: boolean;
  error?: string | null;
  notice?: string | null;
  onRefresh: () => void;
  onSave: (assignments: RoleAssignment[]) => Promise<boolean>;
  onClose: () => void;
}

export function ModelSelector({
  models,
  profile,
  loaded,
  saving = false,
  error,
  notice,
  onRefresh,
  onSave,
  onClose,
}: Props) {
  const local = models.filter((model) => model.source === "local");
  const api = models.filter((model) => model.source === "api");
  const availableLocal = local.filter((model) => model.status === "available");
  const editableRoles = useMemo(
    () => new Set(profile?.editableRoles ?? []),
    [profile]
  );
  const authoritativeAssignments = useMemo(
    () =>
      Object.fromEntries(
        (profile?.assignments ?? []).map(({ role, modelId }) => [role, modelId])
      ),
    [profile]
  );
  const [draft, setDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    setDraft(authoritativeAssignments);
  }, [authoritativeAssignments]);

  const changed = [...editableRoles].some(
    (role) => draft[role] !== authoritativeAssignments[role]
  );

  const apply = async () => {
    const assignments = [...editableRoles]
      .filter((role) => draft[role] !== authoritativeAssignments[role])
      .map((role) => ({
        role,
        modelId: draft[role],
      }));
    if (assignments.some((assignment) => !assignment.modelId)) return;
    await onSave(assignments);
  };

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div
        className="panel"
        role="dialog"
        aria-label="Models"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="close" onClick={onClose} aria-label="Close">
          ×
        </button>
        <h2>Models</h2>

        <div className="group">
          <div className="group-title">Active server profile</div>
          <div className="row">
            <span className="muted">
              {!loaded ? "Loading…" : profile?.name ?? "Unavailable"}
            </span>
            <button className="toggle" onClick={onRefresh}>
              Refresh
            </button>
          </div>
          {error && <div className="panel-error">{error}</div>}
          {notice && (
            <div className="panel-success" role="status">
              {notice}
            </div>
          )}
        </div>

        <div className="group">
          <div className="group-title">Configured role assignments</div>
          {profile?.assignments.length ? (
            profile.assignments.map((assignment) => {
              const editable = editableRoles.has(
                assignment.role as ConfigurableModelRole
              );
              const selected = draft[assignment.role] ?? assignment.modelId;
              const choices = availableLocal.some(
                (model) => model.id === selected
              )
                ? availableLocal
                : [
                    {
                      id: selected,
                      name: selected,
                      source: "local" as const,
                      status: "unavailable" as const,
                    },
                    ...availableLocal,
                  ];
              return (
                <div className="row assignment-row" key={assignment.role}>
                  <label htmlFor={`model-role-${assignment.role}`}>
                    {assignment.role}
                  </label>
                  {editable ? (
                    <select
                      id={`model-role-${assignment.role}`}
                      value={selected}
                      disabled={!loaded || saving || availableLocal.length === 0}
                      onChange={(event) =>
                        setDraft((current) => ({
                          ...current,
                          [assignment.role]: event.target.value,
                        }))
                      }
                    >
                      {choices.map((model) => (
                        <option
                          key={model.id}
                          value={model.id}
                          disabled={model.status !== "available"}
                        >
                          {model.name}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <>
                      <code>{assignment.modelId}</code>
                      {assignment.role === "EMBEDDING_MODEL" && (
                        <span className="assignment-note">
                          Read-only: the local registry does not report reliable
                          embedding compatibility.
                        </span>
                      )}
                    </>
                  )}
                </div>
              );
            })
          ) : (
            <div className="placeholder-note">
              No role assignments were returned by the service.
            </div>
          )}
          <button
            className="apply-models"
            disabled={!changed || saving || availableLocal.length === 0}
            onClick={() => void apply()}
          >
            {saving ? "Applying…" : "Apply Changes"}
          </button>
        </div>

        <div className="group">
          <div className="group-title">Local models</div>
          {local.length ? (
            local.map((model) => (
              <div className="row" key={model.id}>
                <span>{model.name}</span>
                <span className={`model-status model-${model.status}`}>
                  {model.status}
                </span>
              </div>
            ))
          ) : (
            <div className="placeholder-note">
              No local models were reported by the service.
            </div>
          )}
        </div>

        <div className="group">
          <div className="group-title">API models</div>
          {api.length ? (
            api.map((model) => (
              <div className="row" key={model.id}>
                <span>
                  {model.provider ? `${model.provider}: ` : ""}
                  {model.name}
                </span>
                <span className={`model-status model-${model.status}`}>
                  {model.status}
                </span>
              </div>
            ))
          ) : (
            <div className="placeholder-note">
              No API models were reported by the service.
            </div>
          )}
        </div>

        <div className="placeholder-note">
          Assignments are validated against the service-reported local inventory
          and saved to the active SOVEREIGN profile.
        </div>
      </div>
    </div>
  );
}
