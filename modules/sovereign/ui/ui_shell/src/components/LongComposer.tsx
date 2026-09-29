import { MAX_INPUT_CHARACTERS } from "../state/longRequest";
import type { LongInputMode, LongOptions, LongRouteInfo } from "../types/long";

interface Props {
  longRoute?: LongRouteInfo;
  options: LongOptions;
  disabled?: boolean;
  error?: string | null;
  onChange: (options: LongOptions) => void;
}

const MODES: { value: LongInputMode; label: string; hint: string }[] = [
  {
    value: "plan",
    label: "Plan steps",
    hint: "Objective only: the model plans steps, works each in a fresh session, reviews, then synthesizes.",
  },
  {
    value: "material",
    label: "Paste material",
    hint: "The material is split into chunks that fit the model's window, mapped, then reduced.",
  },
  {
    value: "inbox",
    label: "Inbox file",
    hint: "For large inputs: a file you placed in the state home's long_inputs folder.",
  },
];

/**
 * Extra fields for a LONG request. The chat input stays the objective; these choose the model
 * and what the run works through. The request text is composed on send (composeLongRequest).
 */
export function LongComposer({ longRoute, options, disabled, error, onChange }: Props) {
  const models = longRoute?.models ?? [];
  const set = (patch: Partial<LongOptions>) => onChange({ ...options, ...patch });
  const mode = MODES.find((m) => m.value === options.mode) ?? MODES[0];

  return (
    <fieldset className="long-composer" disabled={disabled} aria-label="LONG run options">
      <legend>LONG run - hours on a big model, split into fresh-context chunks</legend>
      <div className="long-row">
        <label>
          <span>Model</span>
          <select
            value={options.model}
            onChange={(e) => set({ model: e.target.value })}
            aria-label="LONG model"
          >
            <option value="">
              Default{longRoute?.defaultModel ? ` (${longRoute.defaultModel})` : ""}
            </option>
            {models.map((m) => (
              <option key={m.model} value={m.model}>
                {m.model} - {Math.round(m.context / 1024)}k context
                {m.thinking === "on" ? ", reasons before answering" : ""}
              </option>
            ))}
          </select>
        </label>
        <div className="long-modes" role="radiogroup" aria-label="What the run works through">
          {MODES.map((m) => (
            <label key={m.value} className="long-mode">
              <input
                type="radio"
                name="long-mode"
                value={m.value}
                checked={options.mode === m.value}
                onChange={() => set({ mode: m.value })}
              />
              {m.label}
            </label>
          ))}
        </div>
      </div>
      <p className="long-hint">{mode.hint}</p>
      {options.mode === "material" && (
        <label className="long-material">
          <span>
            Material ({options.material.length.toLocaleString()} of{" "}
            {MAX_INPUT_CHARACTERS.toLocaleString()} characters)
          </span>
          <textarea
            value={options.material}
            onChange={(e) => set({ material: e.target.value })}
            rows={6}
            aria-label="LONG material"
            placeholder="Paste the text to work through…"
          />
        </label>
      )}
      {options.mode === "inbox" && (
        <label className="long-inbox">
          <span>File in long_inputs</span>
          <input
            type="text"
            value={options.inboxFile}
            onChange={(e) => set({ inboxFile: e.target.value })}
            aria-label="LONG inbox file"
            placeholder="report.md"
          />
        </label>
      )}
      {error && (
        <p className="long-error" role="alert">
          {error}
        </p>
      )}
    </fieldset>
  );
}
