import type { RouteOverride } from "../types/chat";

interface Props {
  value: RouteOverride;
  disabled?: boolean;
  onChange: (route: RouteOverride) => void;
}

const ROUTES: RouteOverride[] = [
  "AUTO",
  "STATUS",
  "QUICK",
  "DEEP",
  "RESEARCH",
  "CONTINUITY",
];

export function RouteSelector({ value, disabled, onChange }: Props) {
  return (
    <label className="route-selector">
      <span>Route</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value as RouteOverride)}
        aria-label="Execution route"
      >
        {ROUTES.map((route) => (
          <option key={route} value={route}>
            {route}
          </option>
        ))}
      </select>
    </label>
  );
}
