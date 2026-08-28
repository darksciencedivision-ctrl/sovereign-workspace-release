# Audit A — oracle predicate classification

Classification is of the predicate, not of the underlying product goal. `SUBSTANTIVE` inspects live product/source/value/hash behavior; `STRUCTURAL` checks a multi-part shape without proving the behavior; `SELF-REFERENTIAL` accepts a builder-authored assertion as proof; `TRIVIAL` can be satisfied by a file or a few chosen words. The deciding quotations below are exact predicate fragments; the cited function range supplies their definitions.

Result against `evidence/cpm1/goalcheck-66.txt`: 32 substantive TRUE, 17 structural TRUE, 30 self-referential TRUE, 28 trivial TRUE. Thus **58 of 107 TRUE outcomes rest on TRIVIAL or SELF-REFERENTIAL predicates**. The 17 FALSE outcomes are 6 substantive, 3 structural, 1 self-referential, and 7 trivial.

| Goal | Class | Deciding predicate (quoted) | Minimum artifact that satisfies it |
|---|---|---|---|
| G1 | SUBSTANTIVE | `goalcheck.py:247-267` — `not pr` | Readable preflight whose recorded decisions hash, clean-start state, UTC, and process facts match live files/process state. |
| G2 | SUBSTANTIVE | `goalcheck.py:269-293` — `not pr` | Authorization/spend reconciliation matching live configuration and permitted provider set. |
| G3 | SUBSTANTIVE | `goalcheck.py:295-317` — `not pr` | Session-start capture satisfying the amended per-session freshness rule and live quiescence facts. |
| G4 | SUBSTANTIVE | `goalcheck.py:319-361` — `not pr` | Five valid protected-root manifests with pinned tool hash and required Token exclusion. |
| G5 | SUBSTANTIVE | `goalcheck.py:363-392` — `not pr` | Complete prerequisite evidence with live path/hash/process checks. |
| G6 | SELF-REFERENTIAL | `goalcheck.py:394-406` — `not pr` | A compilable `goalcheck.py` containing 124 `rec("G…")` calls and no duplicate goal ids. |
| G7 | STRUCTURAL | `goalcheck.py:408-420` — `not pr` | Loop ledger with required numbered rows/fields and monotonic-looking timestamps. |
| G8 | SELF-REFERENTIAL | `goalcheck.py:422-431` — `ok` | A reachability-sweep file containing every `G1`…`G124` token and `REACHABLE`/`NOT_RUN`. |
| G9 | STRUCTURAL | `goalcheck.py:433-442` — `ok` | CP map containing all named provider/runtime tokens and cited path-like strings. |
| G10 | STRUCTURAL | `goalcheck.py:444-454` — `ok` | CP map containing all twelve invariant ids and classification words. |
| G11 | TRIVIAL | `goalcheck.py:456-467` — `pd.is_file() and sr.is_file()` | Two files exist: provenance/discovery and spend reconciliation. |
| G12 | SUBSTANTIVE | `goalcheck.py:469-470` — `gate_cand("8a")` | Ledger gate 8a CANDIDATE with existing evidence whose hashes match. |
| G13 | SELF-REFERENTIAL | `goalcheck.py:473-481` — `oktxt and pf[0] and ext` | A lifecycle test transcript saying tests passed plus a fixture file and extracted-artifact file. |
| G14 | SELF-REFERENTIAL | `goalcheck.py:483-492` — `ok` | Transcript mentioning restart/resume, timestamps, and identity terms. |
| G15 | SELF-REFERENTIAL | `goalcheck.py:494-508` — `ok` | Transcript containing lifecycle verbs, failure terms, and a passed-test marker. |
| G16 | SELF-REFERENTIAL | `goalcheck.py:510-516` — `ok` | Transcript containing kill-tree/job-object wording and a passed-test marker. |
| G17 | SELF-REFERENTIAL | `goalcheck.py:518-532` — `not pr` | Adapter-parity transcript/config containing readiness, identity, stop, and expected keywords. |
| G18 | SELF-REFERENTIAL | `goalcheck.py:534-536` — `bl.is_file() and p3[0]` | Boundary-list file plus a transcript parsed as passing. |
| G19 | SUBSTANTIVE | `goalcheck.py:538-549` — `not pr` | Existing before/after test artifacts plus gate 8b hash-valid CANDIDATE. |
| G20 | SELF-REFERENTIAL | `goalcheck.py:552-554` — `es.is_file() and pf[0]` | EMPTY-session artifact exists and an associated transcript says passed. |
| G21 | TRIVIAL | `goalcheck.py:556-562` — `ok` | One text file containing four lifecycle words and three timestamp-looking strings. |
| G22 | STRUCTURAL | `goalcheck.py:564-569` — `gr[0] and (not hits)` | A grep-results artifact parsed as clean and no forbidden literal found in selected source files. |
| G23 | TRIVIAL | `goalcheck.py:571-573` — `pnd.is_file()` | One named artifact exists. |
| G24 | SUBSTANTIVE | `goalcheck.py:575-580` — `ok and sok and lc[0]` | Three specific test artifacts with expected success/failure semantics. |
| G25 | SELF-REFERENTIAL | `goalcheck.py:583-591` — `ok` | A launch evidence file containing provider/model and launch/ticket terms, or an accepted NOT_RUN marker. |
| G26 | TRIVIAL | `goalcheck.py:593-603` — `ok` | A text file containing `directive`, `response`, and a provider/model word, or a listed NOT_RUN reason; no live round-trip required. |
| G27 | SUBSTANTIVE | `goalcheck.py:605-606` — `gate_cand("8d")` | Gate 8d CANDIDATE with hash-valid evidence. |
| G28 | SUBSTANTIVE | `goalcheck.py:609-624` — `ok and pf[0]` | Registry JSON with nonempty live workers and projected fields, plus a passing test transcript. |
| G29 | TRIVIAL | `goalcheck.py:626-629` — `ok` | One fixture/text artifact containing source tokens. |
| G30 | SELF-REFERENTIAL | `goalcheck.py:631-637` — `ok` | A roster artifact naming configured providers/models and honesty wording. |
| G31 | STRUCTURAL | `goalcheck.py:639-644` — `ok` | Two evidence files with required provider-group/status words. |
| G32 | SUBSTANTIVE | `goalcheck.py:646-651` — `stated` | Gate 8e CANDIDATE with hash-valid evidence and explicit live/non-live disclosure. |
| G33 | SELF-REFERENTIAL | `goalcheck.py:654-658` — `True` | OpenCode availability artifact exists; any contents are accepted. |
| G34 | TRIVIAL | `goalcheck.py:660-668` — `direct.is_file()` | If OpenCode is present, the direct-operation file merely exists; otherwise a NOT_RUN phrase. |
| G35 | TRIVIAL | `goalcheck.py:670-678` — `dele.is_file()` | If OpenCode is present, the delegation file merely exists; otherwise a NOT_RUN phrase. |
| G36 | SUBSTANTIVE | `goalcheck.py:680-693` — `bnm.is_file() and (not mh) and (not br)` | Backend-not-model evidence exists and source scan finds neither model-hardcoding nor backend/model conflation. |
| G37 | SUBSTANTIVE | `goalcheck.py:695-696` — `gate_cand("8f")` | Gate 8f CANDIDATE with hash-valid evidence. |
| G38 | STRUCTURAL | `goalcheck.py:699-707` — `ok` | Registry dump and duplication audit containing expected keys/tokens; no proof selectors consume it. |
| G39 | STRUCTURAL | `goalcheck.py:717-728` — `all(k in rows[0] for k in required)` | First registry row carries the named fields. |
| G40 | SELF-REFERENTIAL | `goalcheck.py:730-732` — `pf[0]` | A provider-fit transcript that the parser recognizes as passed. |
| G41 | TRIVIAL | `goalcheck.py:734-739` — `'ollama' in t` | Discovery file contains `ollama`, even though the goal requires every configured discovery source. |
| G42 | TRIVIAL | `goalcheck.py:741-743` — `gs.is_file()` | One schema artifact exists. |
| G43 | SUBSTANTIVE | `goalcheck.py:745-746` — `gate_cand("8g")` | Gate 8g CANDIDATE with hash-valid evidence. |
| G44 | SELF-REFERENTIAL | `goalcheck.py:749-753` — `ok` | Install provenance file and copied module directory exist with source/copy wording. |
| G45 | STRUCTURAL | `goalcheck.py:755-767` — `okj and st.is_file() and sp.is_file()` | Valid module JSON plus start/stop evidence files; their assertions are not executed. |
| G46 | TRIVIAL | `goalcheck.py:769-777` — `not miss and nobare` | One DOM text file contains ten chosen labels and no literal `D:/`. |
| G47 | SELF-REFERENTIAL | `goalcheck.py:779-781` — `na.is_file() and pf[0]` | No-autocompute artifact plus a transcript parsed as passed; no live idle observation required by the predicate. |
| G48 | SELF-REFERENTIAL | `goalcheck.py:783-790` — `ok` | Theme/handoff artifact contains selected terms and paths. |
| G49 | SUBSTANTIVE | `goalcheck.py:792-793` — `gate_cand("8h")` | Gate 8h CANDIDATE with hash-valid evidence. |
| G50 | TRIVIAL | `goalcheck.py:796-802` — `ok` | Purpose artifact contains `read-only`, `no credential`, and usage/model/provider words. |
| G51 | SELF-REFERENTIAL | `goalcheck.py:804-809` — `ok` | Install provenance and copied module exist with source/exclusion words. |
| G52 | STRUCTURAL | `goalcheck.py:811-822` — `okj and sta.is_file() and stp.is_file()` | Module JSON has expected readiness/identity/stop shape and start/stop assertion files exist. |
| G53 | STRUCTURAL | `goalcheck.py:824-841` — `ok` | Refresh evidence contains refresh/CSRF/Origin/Host terms and either passing or accepted NOT_RUN text. |
| G54 | TRIVIAL | `goalcheck.py:843-845` — `h19.is_file()` | One contract artifact exists. |
| G55 | TRIVIAL | `goalcheck.py:847-849` — `nc.is_file()` | One no-credentials artifact exists. |
| G56 | SUBSTANTIVE | `goalcheck.py:851-852` — `gate_cand("8i")` | Gate 8i CANDIDATE with hash-valid evidence. |
| G57 | STRUCTURAL | `goalcheck.py:855-859` — `not missing` | Eight named scenario files exist, even if all live legs say NOT_RUN. |
| G58 | TRIVIAL | `goalcheck.py:861-867` — `ok` | Proof-chain file contains `Human` and either NOT_RUN/provider words; no exercised chain required. |
| G59 | SUBSTANTIVE | `goalcheck.py:869-874` — `tr[0] and bm[0] and tok` | Theme token check, build-manifest check, and expected CSS token presence. |
| G60 | SELF-REFERENTIAL | `goalcheck.py:876-878` — `lc[0]` | Line-count artifact parser accepts the builder-reported total. |
| G61 | SUBSTANTIVE | `goalcheck.py:880-886` — `ok` | Orphan/port evidence contains all required port states and no builder-owned survivors. |
| G62 | SUBSTANTIVE | `goalcheck.py:888-889` — `gate_cand("8j")` | Gate 8j CANDIDATE with hash-valid evidence. |
| G63 | STRUCTURAL | `goalcheck.py:891-902` — `ok` | Live ledger/report artifacts contain all required band/gate markers and objective terms. |
| G64 | SUBSTANTIVE | `goalcheck.py:904-906` — `ledger_old_unchanged()` | Whole gate 0–7b objects equal the saved snapshot. |
| G65 | SELF-REFERENTIAL | `goalcheck.py:908-914` — `ok` | Two dependency scan files contain expected summary words. |
| G66 | SELF-REFERENTIAL | `goalcheck.py:916-919` — `ok` | Handover-manifests artifact says all five roots have `no differences`. |
| G67 | TRIVIAL | `goalcheck.py:921-924` — `ok` | One boundary record contains addendum and boundary words. |
| G68 | STRUCTURAL | `goalcheck.py:927-939` — `ok` | Runtime inventory JSON reports a candidate and required discovery/pinning fields. |
| G69 | STRUCTURAL | `goalcheck.py:941-948` — `ok` | GGUF provenance/stage files contain URL, hash, size, and stage terms. |
| G70 | STRUCTURAL | `goalcheck.py:950-955` — `not missing` | Four A1 files exist and none contain NOT_RUN; no semantic validation beyond presence. |
| G71 | STRUCTURAL | `goalcheck.py:957-962` — `not missing` | Four A2 files exist and none contain NOT_RUN. |
| G72 | SUBSTANTIVE | `goalcheck.py:964-976` — `ok` | Llama manifest has expected live endpoint/identity/stop configuration plus start/stop artifacts. |
| G73 | TRIVIAL | `goalcheck.py:978-981` — `ok` | Import-scan file merely contains the words `zero` and `sovereign`. |
| G74 | SUBSTANTIVE | `goalcheck.py:983-984` — `gate_cand("9a")` | Gate 9a CANDIDATE with hash-valid evidence. |
| G75 | TRIVIAL | `goalcheck.py:987-992` — `ok` | Smoke file contains health/model/generate and lacks NOT_RUN. |
| G76 | TRIVIAL | `goalcheck.py:994-999` — `ok` | Capability file contains six operation names and lacks NOT_RUN. |
| G77 | TRIVIAL | `goalcheck.py:1001-1006` — `ok` | Negative-path file contains 404/bad request/refus terms and lacks NOT_RUN. |
| G78 | TRIVIAL | `goalcheck.py:1008-1011` — `ok` | One transcript contains `pytest`, `passed`, and not `failed`. |
| G79 | TRIVIAL | `goalcheck.py:1013-1018` — `ok` | Runner-only file contains words `shell`, `only`, and `llama`. |
| G80 | SUBSTANTIVE | `goalcheck.py:1020-1024` — `ok and 'no sovereign integration' in blob` | Manifest-source hash equals pinned runtime hash and file includes integration declaration. |
| G81 | SUBSTANTIVE | `goalcheck.py:1027-1036` — `ok` | Ollama adapter exposes all required operations and inheritance/contract relation. |
| G82 | SELF-REFERENTIAL | `goalcheck.py:1038-1040` — `pf[0]` | One backend-abstraction transcript parsed as passed. |
| G83 | SUBSTANTIVE | `goalcheck.py:1042-1049` — `ok` | Llama backend source contains required operation definitions and no policy imports. |
| G84 | TRIVIAL | `goalcheck.py:1051-1057` — `ok` | Parity text names backends/operations and contains PASS/UNSUPPORTED/FAIL tokens; cells need not be executed. |
| G85 | TRIVIAL | `goalcheck.py:1059-1065` — `ok` | Default-behavior text contains candidate/default/Ollama words. |
| G86 | SUBSTANTIVE | `goalcheck.py:1067-1071` — `gate_cand("9c") and ledger_old_unchanged()` | Gate 9c CANDIDATE hash-valid and old-ledger snapshot unchanged. |
| G87 | TRIVIAL | `goalcheck.py:1074-1080` — `ok` | Residency-plan file contains four state words and `VRAM`. |
| G88 | TRIVIAL | `goalcheck.py:1082-1088` — `ok` | One prose file says `no-models-autoload`, `models-max`, and `above`; source need not contain the option. |
| G89 | TRIVIAL | `goalcheck.py:1090-1096` — `ok` | One prose file contains concurrency/local/frontier/subscription words. |
| G90 | SUBSTANTIVE | `goalcheck.py:1098-1105` — `not bad and gp.is_file()` | Planner source contains no banned process-control strings and governance-path artifact exists. |
| G91 | TRIVIAL | `goalcheck.py:1107-1113` — `ok` | Adversarial file contains `latency`, `residency`, `refus`, plus pass or accepted NOT_RUN text. |
| G92 | SELF-REFERENTIAL | `goalcheck.py:1115-1118` — `p1[0] and p2[0]` | Two test transcripts parsed as passed. |
| G93 | SELF-REFERENTIAL | `goalcheck.py:1120-1124` — `ok and ok2` | Planner/backend-metrics artifact passes keyword checks and gate 9d is CANDIDATE. |
| G94 | STRUCTURAL | `goalcheck.py:1127-1140` — `ok` | Registry rows contain artifact dictionaries with required keys. |
| G95 | SELF-REFERENTIAL | `goalcheck.py:1142-1144` — `pf[0]` | One identity-separation transcript parsed as passed. |
| G96 | SUBSTANTIVE | `goalcheck.py:1146-1154` — `ok` | JSON Schema `required` set includes all named deployment-manifest fields. |
| G97 | SELF-REFERENTIAL | `goalcheck.py:1156-1158` — `pf[0]` | Ingestion-rejection transcript parsed as passed. |
| G98 | SELF-REFERENTIAL | `goalcheck.py:1160-1162` — `ta.is_file() and pf[0]` | Tag audit exists and alias test transcript parses as passed. |
| G99 | SUBSTANTIVE | `goalcheck.py:1164-1165` — `gate_cand("9e")` | Gate 9e CANDIDATE with hash-valid evidence. |
| G100 | STRUCTURAL | `goalcheck.py:1168-1177` — `all(k in row ...) and bool(validation_evidence)` | Registry first row has context fields and any nonempty validation evidence, including NOT_MEASURED. |
| G101 | TRIVIAL | `goalcheck.py:1179-1186` — `tiers >= 3 and budget` | Context-measurement text names three tier words and a budget. |
| G102 | TRIVIAL | `goalcheck.py:1188-1195` — `got >= 4 or nm` | Four measurement keywords anywhere, or merely `NOT_MEASURED`; no per-combination record required. |
| G103 | TRIVIAL | `goalcheck.py:1197-1204` — `stranded and (accepted or 'STOP' in t.upper())` | Demotion text contains stranded plus accept/STOP wording. |
| G104 | SUBSTANTIVE | `goalcheck.py:1206-1211` — `ok2 and ('validated' ... )` | Registry rows have ordered context values or null plus validation marker. |
| G105 | SUBSTANTIVE | `goalcheck.py:1214-1217` — `gp.is_file() and (not newpaths)` | Governance-path artifact exists and changed-source scan finds no new config paths. |
| G106 | TRIVIAL | `goalcheck.py:1219-1225` — `ok` | Summary text contains `min`, `max`, `median`, `failure`, and `combination`. |
| G107 | SELF-REFERENTIAL | `goalcheck.py:1227-1229` — `pf[0]` | Promotion-axis transcript parsed as passed. |
| G108 | TRIVIAL | `goalcheck.py:1231-1236` — `ok` | `app.js` contains the chosen words `vram` and `resource`/`accounting`, even in a description/comment. |
| G109 | SUBSTANTIVE | `goalcheck.py:1238-1245` — `ok` | LogRing source exposes new fields and `metrics` exists in llama backend. |
| G110 | SUBSTANTIVE | `goalcheck.py:1247-1248` — `gate_cand("9g")` | Gate 9g CANDIDATE with hash-valid evidence. |
| G111 | STRUCTURAL | `goalcheck.py:1251-1262` — `ok` | First registry row's speculative-decoding object has required keys/default values. |
| G112 | SUBSTANTIVE | `goalcheck.py:1264-1267` — `gp.is_file() and (not hits)` | Governance artifact exists and source scan finds no direct speculative-execution terms. |
| G113 | TRIVIAL | `goalcheck.py:1269-1272` — `ok` | Future-method artifact contains `MTP`, `DFlash`, and `draft model`. |
| G114 | TRIVIAL | `goalcheck.py:1274-1281` — `ok` | Adversarial text contains two mismatch keywords and pass/refusal wording. |
| G115 | SUBSTANTIVE | `goalcheck.py:1283-1284` — `gate_cand("9h")` | Gate 9h CANDIDATE with hash-valid evidence. |
| G116 | SUBSTANTIVE | `goalcheck.py:1287-1296` — `not pr` | Six invariant-reproof checks resolve to real source/evidence facts. |
| G117 | SELF-REFERENTIAL | `goalcheck.py:1298-1308` — `events0 and four and tp and clean` | Protected-manifest prose says four clean, Token clean, and fs-watch file says events zero. |
| G118 | TRIVIAL | `goalcheck.py:1310-1316` — `ok` | Restart-closure file contains restart/health/orphan and pass or accepted NOT_RUN wording. |
| G119 | SELF-REFERENTIAL | `goalcheck.py:1318-1328` — `ok` | Builder-authored adversarial review lists ten categories and the word `zero`. |
| G120 | SELF-REFERENTIAL | `goalcheck.py:1330-1336` — `ok` | Builder-authored diff classification matches regex `UNEXPECTED ... 0`; no independent diff is computed. |
| G121 | SELF-REFERENTIAL | `goalcheck.py:1338-1341` — `la[0] and lb[0]` | Two builder-authored linecount files parse below caps; baselines are not recomputed. |
| G122 | STRUCTURAL | `goalcheck.py:1343-1353` — `ok` | Final manifest JSON contains required top-level keys; assertions/tests may be self-reported. |
| G123 | SUBSTANTIVE | `goalcheck.py:1355-1361` — `ok` | Goalcheck output contains exactly 124 goal lines, no FALSE status word, and exactly 17 NOT_RUN statuses. |
| G124 | SUBSTANTIVE | `goalcheck.py:1405-1413` — `ok and partB and unchanged` | Required candidate gates hash-valid, linecount-B parser under cap, and old-ledger snapshot unchanged. |

## Headline interpretation

The oracle is not meaningless, but a TRUE is not a uniform unit. Thirty-two TRUEs inspect substantive state; seventeen verify shape; thirty are circular assertions through builder-authored evidence; and twenty-eight accept very small word/file conditions. The strongest examples of predicate/goal mismatch are G26 (a live dialogue reduced to three words in a file), G34/G35 (live OpenCode work reduced to file existence), G57 (a one-session acceptance scenario reduced to eight files existing), G84 (a parity run reduced to matrix vocabulary), G108 (resource accounting reduced to two chosen words in `app.js`), and G120/G121 (the build's own diff/linecount assertions trusted without recomputation).
