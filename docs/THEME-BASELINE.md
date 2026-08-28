# THEME-BASELINE.md — SWS-UI-001 v1.2
# pinned: 2026-08-21
# source: SOVEREIGN 3.1.2 ui_shell/dist/assets/index-*.css
# evidence: D:\Product Software\SOVEREIGN_ENTERPRISE_PRODUCTION_20260813_142520.zip → ui/ui_shell/dist/

## Token set — verbatim from SOVEREIGN

### Dark theme (default)

| Token | Value | Usage |
|---|---|---|
| `--bg` | `#0e1116` | Page background |
| `--panel` | `#151a21` | Card, panel, surface |
| `--sidebar` | `#10141a` | Sidebar, nav |
| `--input` | `#1a2029` | Input fields, textareas |
| `--border` | `#262d38` | Borders, dividers |
| `--text` | `#e6e9ee` | Primary text |
| `--text-muted` | `#8b94a3` | Secondary text, descriptions |
| `--text-faint` | `#5c6674` | Tertiary text, placeholders |
| `--accent` | `#c9a86a` | Primary accent, links, active states |
| `--accent-dim` | `#8a744a` | Muted accent, hover states |
| `--ok` | `#6ac98a` | Success, READY, healthy |
| `--warning` | `#d0aa62` | Warning, DEGRADED |
| `--danger` | `#c96a6a` | Error, FAILED, danger |
| `--radius` | `8px` | Border radius |
| `--font` | `"Segoe UI", system-ui, -apple-system, sans-serif` | UI text |
| `--mono` | `"Cascadia Code", Consolas, monospace` | Logs, commands, code |

### Light theme (prefers-color-scheme: light)

| Token | Value |
|---|---|
| `--bg` | `#f4f5f7` |
| `--panel` | `#ffffff` |
| `--sidebar` | `#eceef1` |
| `--border` | `#d3d8e0` |
| `--text` | `#1b2027` |
| `--text-muted` | `#58616e` |
| `--text-faint` | `#8a93a1` |
| `--accent` | `#8a744a` |
| `--accent-dim` | `#a68b58` |

## Rules

1. **Tokens only, no new hues.** Every color in the shell is one of the tokens above.
2. **Dark default, honor `prefers-color-scheme: light`.** No manual theme switcher.
3. **Typography:** `--font` for UI, `--mono` for logs/commands. 14px base / 1.45 line-height.
4. **Spacing:** 4px / 8px / 12px / 16px / 24px scale.
5. **Radius:** `--radius` (8px) everywhere.
6. **Elevation:** Single level — 1px `--border` on cards. No gradients, no glow, no box-shadows beyond the border.
7. **Transitions:** ≤ 150 ms.
8. **State badges:** Use `--ok` / `--warning` / `--danger` / `--text-muted` with text + glyph. Badge format: colored dot + state label.
9. **Icon:** Copy `ui_shell/dist/icon.svg` from the SOVEREIGN zip to `shell/static/icon.svg` (permitted by §5).

## Debate Table family note

`FACT` Debate Table shares the slate/gold family (dark bg, gold accent). SOW uses a terminal palette (xterm default colors). The shell uses SOVEREIGN tokens exclusively — this is a deliberate design decision, not an oversight. Modules keep their own visual identity in their own UIs (HC-3).