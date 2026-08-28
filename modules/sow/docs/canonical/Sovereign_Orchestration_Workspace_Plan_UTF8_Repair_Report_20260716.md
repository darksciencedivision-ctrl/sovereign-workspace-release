# UTF-8 REPAIR REPORT — Sovereign Orchestration Workspace Architecture Plan
**Date:** 2026-07-16 · **Performed by:** Research Validator (encoding-only repair; no semantic change) · **Method:** `ftfy.fix_encoding` (deterministic mojibake/encoding repair; no text normalization applied)

## Artifacts

| Field | Value |
|---|---|
| **Original filename** | `Sovereign_Orchestration_Workspace_Architecture_Plan_v1.0_20260716.md` |
| **Original SHA-256** | `668089B57C3162DABDE62ED249778D26F554910666FF62A552FA968BE199E48F` |
| **Original size** | 70,547 bytes |
| **Corrected filename** | `Sovereign_Orchestration_Workspace_Architecture_Plan_v1.0.1_UTF8_20260716.md` |
| **Corrected SHA-256** | `8C9B7240AC7962948844EA7892BD63BDCCC061E3A1BA2F968F8ED935E3300022` |
| **Corrected size** | 64,726 bytes |
| **Repaired lines** | 179 (of 561) |
| **Diff artifact** | `Sovereign_Orchestration_Workspace_Plan_UTF8_repair.diff` (deterministic unified diff, 676 lines) |

## Character classes repaired (26 distinct codepoints)
All repaired characters are punctuation, symbols, or diagram glyphs. **No alphanumeric, word, identifier, hash, or code content was in the repaired set.**

- **Box-drawing** (architecture/repo diagrams): `─ │ ├ ┬ ┴ └ ┘ ┌ ┐` (U+2500, 2502, 251C, 252C, 2534, 2514, 2518, 250C, 2510)
- **Arrows:** `→ ↔ ⇒` (U+2192 ×106, U+2194 ×9, U+21D2 ×13)
- **Dashes:** `—` em (U+2014 ×69), `–` en (U+2013 ×22)
- **Section sign:** `§` (U+00A7 ×77)
- **Math/relational:** `≥ ≤ ≠ ≈ × √ ⌈ ⌉` (U+2265, 2264, 2260, 2248, 00D7, 221A, 2308, 2309)
- **Other:** `·` middle dot (U+00B7 ×21), `▼` (U+25BC ×9), `ç` (U+00E7 ×1, "façade")

Root cause: double-encoded UTF-8 (text encoded UTF-8, its bytes re-interpreted as Windows-1252, then re-encoded as UTF-8), e.g. `—` → `â€"`, `§` → `Â§`, `│` → mojibake. This was baked into the file at authoring, which is why the original's SHA-256 verified against the reported value — the corruption was part of the verified bytes.

## Semantic-change check — PASS
- **ASCII skeleton byte-identical:** stripping all non-ASCII characters from both files yields **identical** byte streams. Every word, section number, invariant ID (I-*), decision ID (D-*), unresolved ID (U*), embedded hash, JSON, and code fence is unchanged.
- **Line count preserved:** 561 = 561 (no line splitting or merging).
- **Residual mojibake markers:** 0.
- **Change set:** limited to the 26 non-ASCII symbol/diagram codepoints listed above.
- **Conclusion:** the transform is provably **encoding-only**. No content, structure, or meaning was altered.

## Diff result
179 lines changed. Every change is a non-ASCII glyph repair (mojibake → correct character); no ASCII bytes differ. Full deterministic unified diff preserved as `Sovereign_Orchestration_Workspace_Plan_UTF8_repair.diff`.

## Provenance & promotion
- **Original:** PRESERVED unchanged as the verified source/provenance artifact (SHA-256 `668089B5…E48F`). Not overwritten, not modified.
- **Corrected (v1.0.1_UTF8):** PROMOTED as the canonical **operator-review candidate**. New SHA-256 recorded above.
- **Authorization status:** unchanged — this is a readability repair only. Implementation remains **unauthorized**; the plan still stops at operator review before Phase 0.
