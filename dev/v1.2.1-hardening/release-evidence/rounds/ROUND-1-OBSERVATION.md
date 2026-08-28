# ROUND-1-OBSERVATION

Round: 1
Current HEAD: 43ab217 (worktree master)
Working tree: clean
Selected defect cluster: P0-02 (malformed config fail-closed) + P0-03 (BOM-consistent parsing)
Open P0 before round: 19 (P0-02..P0-20)

## Affected files / surfaces (read, not yet modified)

1. app.py:88-94 load_config()
   - read_text(encoding="utf-8") is strict: any UTF-8 BOM makes json.loads raise.
   - On JSONDecodeError / non-dict root / OSError -> document = {} -> ENTIRE effective config becomes defaults.
   - app.py:169-170 then writes normalized defaults over the original file (atomic_write_json) because {} != normalized. Original bytes destroyed on malformed input. Direct G-05 violation; core of P0-02.
2. app.py:602,618 seat-model/thesis persistence helpers
   - Their own strict-utf8 json.loads on CONFIG_PATH; raise on parse error (different failure mode from load_config); would also fail on BOM.
3. scripts/bootstrap.ps1 inline _check_models.py (~line 137): encoding="utf-8-sig" - BOM-tolerant.
4. scripts/bootstrap.sh line 150: utf-8-sig (BOM-tolerant).
5. scripts/bootstrap.sh line 207: port probe uses STRICT utf-8 with silent "|| echo 8700" fallback - third divergent interpretation + silent fallback (the silent-fallback aspect belongs to P0-04/G-07, later round; only the encoding inconsistency is P0-03 scope).

=> Bootstrap tolerates BOM; runtime rejects it by silently nuking config to defaults; sh port probe rejects it via silent 8700 fallback. Three interpretations of one file = P0-03.

## Adjacent facts recorded (not this round's scope)

- README.md:107 documents per-key fallback ("Invalid values fall back to defaults") - that documented contract covers valid-JSON per-key coercion, NOT whole-file parse corruption. Fail-closed on unparseable file does not contradict it.
- app.py:133 seats[:4] truncation and :151-167 invented default seats = P0-17 (later round).
- _valid_number silent range-coercion = P0-18 (later round).
- state.topic_epoch already exists (line 99 test reference) - useful for Phase 4.

## Known failing evidence

None at baseline; defects are behavioral (silent destruction/divergence), exposed by contradiction tests to be written.

## Dependency surfaces

load_config is called at module import (app.py:174). Hard-failing it aborts startup - required by contract ("prevent unsafe startup"). All existing tests provision valid temp configs via CONFIG_PATH env + importlib exec_module, so they are unaffected.

## Regression surfaces

- Any test or flow relying on load_config({}) lenient behavior for MISSING file. Decision D-05: missing file stays lenient-documented? NO - grep shows no doc/test relies on absent-file defaults; but to keep radius minimal R1 treats ONLY parse-corruption as fatal; missing-file behavior unchanged this round (recorded for P0-04 canonical resolver round).

## Reason this is highest-priority next delta

Directive S37 mandates Round 1 = P0-02+P0-03. It is also the safest possible entry: no protocol/orchestration surface touched, and every later phase depends on trustworthy configuration loading.
