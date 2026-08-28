# ROUND-2-OBSERVATION

Round: 2
Current HEAD: bccb029 (.gitignore) / hardening head 586936e
Working tree: clean
Selected defect cluster: P0-16 payload bounds + P0-17 seat identity schema + P0-18 numeric cross-field validation
Open P0 before round: 17

## Affected surfaces (read only)

1. app.py:249-250 PUBLIC_TITLE_MAX_CHARS=300 / DEBATE_BRIEF_MAX_CHARS=20000 exist as isolated constants; no central limits table.
2. app.py:1363-1380 pydantic inputs: TextIn(text), SeatModelIn(seat,model), BriefIn(public_title,debate_brief), SeatThesisIn(seat,thesis,reason="") - no length constraints at model layer.
3. app.py:1535+ api_interject: NO length bound; arbitrary-size text stored into state.interject.
4. api_seat_thesis region (~1544-1576 in current numbering): thesis/reason unbounded at API.
5. load_config seat normalization (app.py ~171-212 post-R1): silently truncates seats[:4], skips non-dict entries, invents two default seats when <2 valid, no uniqueness check, no color/persona/thesis/name bounds -> G-07 violations, P0-17 core.
6. Numeric coercion _valid_number maps out-of-range to per-key defaults (documented README behavior); NO relational checks anywhere -> turn_word_min>turn_word_max accepted, producing "1000-20 words" prompt ranges (P0-18).
7. static/index.html: zero maxlength attributes; JS stores titleMaxChars/briefMaxChars from snapshot but never applies them; thesis textarea (line ~443) unbounded.

## Existing coverage to preserve

test_v1_1_regressions: topic >300 rejected; brief >20000 rejected + valid values never truncated (uses PUBLIC_TITLE_MAX_CHARS/DEBATE_BRIEF_MAX_CHARS module attrs - keep names working).
Endpoint-call convention: asyncio.run(app.api_x(pydantic_body)) returning JSONResponse; assert status_code/body.

## Dependency/regression surfaces

load_config strictness now affects every test fixture config (all use valid 2-seat configs). Frontend edits must not alter visual design (G-03): maxlength attributes are behavioral, not aesthetic.

## Reason highest-priority

Phase 1 exit gate requires these three closed before control-plane/stream work; they also shrink later attack surface (unbounded operator payloads reach prompts).
