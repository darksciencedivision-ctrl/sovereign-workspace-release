"""OP-12.1 / U227 — the node schema is amended by SUCCESSOR, and the freeze is not touched.

Operator ruling OP-12.1 (`AUTONOMOUS_BUILD_DIRECTIVE.md` §17.1, 2026-08-01) resolves U227 by
authorizing `schemas/node.schema@1.1.json` beside the frozen `@1.0` — enum = the frozen list plus
`grok_build`, `google_antigravity`, and (as its own recorded item, U254) `ollama_local`.

Four claims are load-bearing and each has a test here that fails when the claim stops being true:

1. **The freeze is untouched.** `node@1.0`'s file, `$id`, enum and `schema` const are byte-for-byte
   what the Phase-0 manifest recorded, and the frozen schema SET is still exactly twelve files.
2. **The successor is a copy with exactly five recorded deltas.** Draft-07 cannot express
   "`node@1.0` with a wider enum" (`$ref`/`allOf` can only narrow, and `additionalProperties:false`
   + the `schema` const would reject a `node@1.1` record), so `@1.1` is standalone — which means a
   duplicated document, which means drift risk. The delta test is the thing that manages it.
3. **The fence still fences.** `NodeRegistry.register` admits what a schema version admits and
   refuses everything else, auditably; the vocabulary is DERIVED from the files, not re-declared;
   and an unreadable schema narrows it rather than opening it.
4. **The manifest records the amendment without disturbing the signature.** `freeze_integrity_sha256`
   is unchanged and `operator_signature` survives regeneration (U222), while amendment drift is
   still a hard `--check` failure.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "schemas"
V10_PATH = SCHEMA_DIR / "node.schema.json"
V11_PATH = SCHEMA_DIR / "node.schema@1.1.json"
MANIFEST_PATH = ROOT / "docs" / "PHASE0_FREEZE_MANIFEST.json"

#: The three ids OP-12.1 admits, in the order the successor lists them. Written out here on purpose:
#: this file is the one place a hand-written copy of the delta is WANTED, because it is the assertion.
OP12_1_ADDITIONS = ["grok_build", "google_antigravity", "ollama_local"]

#: Every difference between `@1.0` and `@1.1` that the ruling authorizes, as JSON-pointer-ish paths.
#: Anything else differing is unrecorded drift in a duplicated document.
RECORDED_DELTAS = {"$id", "$comment", "description", "properties.adapter.enum",
                   "properties.schema.const"}

V10 = json.loads(V10_PATH.read_text(encoding="utf-8"))
V11 = json.loads(V11_PATH.read_text(encoding="utf-8"))


def _flatten(obj: object, prefix: str = "") -> dict[str, object]:
    if isinstance(obj, dict):
        out: dict[str, object] = {}
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
        return out
    if isinstance(obj, list):
        # a list is compared as a whole: reordering an enum is a change worth seeing
        return {prefix: json.dumps(obj)}
    return {prefix: obj}


def _node_record(adapter: str, schema_version: str) -> dict:
    return {
        "node_id": "3f2a6c1e-9d4b-4e8a-b0c7-1a2b3c4d5e6f", "class": "worker_reasoning",
        "adapter": adapter, "harness": None, "model_ref": None, "locality": "frontier",
        "subscription_ref": None,
        "capabilities": [{"capability": "reasoning", "requirements": {"tool_use": False}}],
        "workspace": {"type": "none"}, "permission_profile_id": "pp-probe-reasoning",
        "auth": {"mcp_credential_id": "cred-ref-1"}, "state": "SPAWNING",
        "offline_profile_eligible": False, "spawned_by_supervisor": True,
        "schema": schema_version,
    }


# ---- claim 1: the freeze is untouched --------------------------------------------------------

def test_the_frozen_node_schema_is_exactly_what_the_manifest_recorded() -> None:
    """The amendment is ADDITIVE. If this fails, `@1.0` was edited and the ruling was not followed
    — the ruling's own words are "the frozen `@1.0` files ... are NEVER edited"."""
    import hashlib
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    recorded = {e["path"]: e["sha256"] for e in manifest["contents"]["schemas"]}
    actual = hashlib.sha256(V10_PATH.read_bytes()).hexdigest().upper()
    assert recorded["schemas/node.schema.json"] == actual
    assert V10["$id"] == "https://sovereign.local/schemas/node@1.0"
    assert V10["properties"]["schema"]["const"] == "node@1.0"
    assert V10["properties"]["adapter"]["enum"] == [
        "claude_code", "openai_codex_cli", "opencode_local", "gemini_cli",
        "aider", "ollama_direct", "nvidia_parakeet", "mock"]


def test_the_frozen_schema_set_is_still_exactly_twelve_files() -> None:
    """The successor must not join the frozen set — that set is what the operator signed, and its
    membership is pinned by the manifest glob `*.schema.json`. The successor's name deliberately
    does not match it, so the two blocks are disjoint."""
    frozen = sorted(p.name for p in SCHEMA_DIR.glob("*.schema.json"))
    assert len(frozen) == 12, frozen
    assert "node.schema@1.1.json" not in frozen
    amendments = sorted(p.name for p in SCHEMA_DIR.glob("*.schema@*.json"))
    assert amendments == ["node.schema@1.1.json"]
    assert not set(frozen) & set(amendments)


# ---- claim 2: the successor is a copy with exactly the recorded deltas ------------------------

def test_the_successor_differs_from_the_frozen_schema_in_exactly_the_recorded_places() -> None:
    """`@1.1` is a standalone duplicate of a frozen document (draft-07 leaves no alternative — see
    the module docstring). A duplicate drifts unless something compares it, so this is that
    something: every key that differs must be one the ruling authorized, and no key may be added
    or dropped."""
    a, b = _flatten(V10), _flatten(V11)
    added, removed = sorted(set(b) - set(a)), sorted(set(a) - set(b))
    assert added == ["$comment"], added
    assert removed == [], removed
    differing = {k for k in set(a) & set(b) if a[k] != b[k]}
    assert differing | {"$comment"} == RECORDED_DELTAS, sorted(differing)


def test_the_successor_definitions_are_a_verbatim_copy_and_do_not_claim_canonicity() -> None:
    """`capability_descriptor` / `deployment_profile` are referenced by task@1.0, debate@1.0 and
    project@1.0 through the node@1.0 URI. The successor copies them so it can validate standalone;
    it must not have re-pointed anything, or two schemas would each believe they own the
    definition."""
    assert V11["definitions"] == V10["definitions"]
    assert "node@1.0#/definitions/capability_descriptor" in \
        V11["definitions"]["capability_descriptor"]["$comment"]


def test_the_successor_adapter_enum_is_the_frozen_list_plus_exactly_the_three_admitted_ids() -> None:
    assert V11["$id"] == "https://sovereign.local/schemas/node@1.1"
    assert V11["properties"]["schema"]["const"] == "node@1.1"
    assert V11["properties"]["adapter"]["enum"] == \
        V10["properties"]["adapter"]["enum"] + OP12_1_ADDITIONS


def test_both_schema_versions_compile_and_the_successor_is_a_superset() -> None:
    """Every record valid under `@1.0` stays valid under `@1.1` once re-tagged — a successor that
    quietly TIGHTENED something would be a breaking change wearing an additive label."""
    jsonschema.Draft7Validator.check_schema(V10)
    jsonschema.Draft7Validator.check_schema(V11)
    for adapter in V10["properties"]["adapter"]["enum"]:
        record = _node_record(adapter, "node@1.0")
        jsonschema.Draft7Validator(V10).validate(record)
        jsonschema.Draft7Validator(V11).validate({**record, "schema": "node@1.1"})


@pytest.mark.parametrize("adapter", OP12_1_ADDITIONS)
def test_the_admitted_ids_validate_under_the_successor_and_not_under_the_freeze(adapter) -> None:
    """The exact boundary the amendment moves, in both directions. `@1.0` still refuses these ids,
    which is what makes "the freeze is untouched" a measurement rather than a promise."""
    jsonschema.Draft7Validator(V11).validate(_node_record(adapter, "node@1.1"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft7Validator(V10).validate(_node_record(adapter, "node@1.0"))


def test_an_unadmitted_adapter_id_validates_under_neither_version() -> None:
    for schema, version in ((V10, "node@1.0"), (V11, "node@1.1")):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft7Validator(schema).validate(_node_record("kimi_k3", version))


def test_the_successor_widens_the_vocabulary_and_nothing_else() -> None:
    """A frontier adapter admitted into the enum is still subject to every other gate. The schema
    is where the vocabulary lives, not where authorization lives — so the successor must not have
    grown a field that could be read as permission (invariant 7's shape: access, not authority)."""
    assert V11["required"] == V10["required"]
    assert V11["additionalProperties"] is False
    assert sorted(V11["properties"]) == sorted(V10["properties"])


# ---- claim 3: the fence still fences ----------------------------------------------------------

def _registry(tmp_path: Path):
    from control_plane.nodes.event_log import AppendOnlyEventLog
    from control_plane.nodes.registry import NodeRegistry
    return NodeRegistry(AppendOnlyEventLog(tmp_path / "events.jsonl"))


def _events(tmp_path: Path) -> list[dict]:
    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    return [json.loads(ln) for ln in text.splitlines() if ln.strip()]


def _data(event: dict) -> dict:
    """`AppendOnlyEventLog` nests the caller's kwargs under `data`; the envelope carries seq/hash."""
    return event["data"]


@pytest.mark.parametrize("adapter", ["grok_build", "google_antigravity"])
def test_the_op12_providers_now_register_and_the_record_names_the_admitting_version(
        adapter, tmp_path: Path) -> None:
    """The 18B fence refused these ids and was RIGHT to: the ruling had not been made. It has now,
    so they register — and the append-only spawn event carries WHICH version admitted them, because
    a `node@1.1` node and a `node@1.0` node are different provenance claims and the log is the
    record (invariant 12)."""
    reg = _registry(tmp_path)
    rec = reg.register(f"n-{adapter}", "worker_reasoning", adapter, spawned_by_supervisor=True)
    assert rec.adapter == adapter
    spawn = [e for e in _events(tmp_path) if e.get("kind") == "spawn"]
    assert len(spawn) == 1 and _data(spawn[0])["adapter_schema_version"] == "node@1.1", spawn


def test_a_frozen_enum_member_is_still_attributed_to_the_frozen_version(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.register("n-cc", "conductor", "claude_code", spawned_by_supervisor=True)
    spawn = [e for e in _events(tmp_path) if e.get("kind") == "spawn"]
    assert _data(spawn[0])["adapter_schema_version"] == "node@1.0"


def test_ollama_local_is_now_admitted_by_the_schema_not_by_a_grandfather_clause(
        tmp_path: Path) -> None:
    """U254 was a product-layer id no schema admitted, kept alive by an exemption list. OP-12.1
    folded it into `node@1.1`, so the exemption list is empty and the vocabulary has no exceptions
    at all."""
    from control_plane.nodes.registry import ADAPTER_EXEMPTIONS
    assert ADAPTER_EXEMPTIONS == frozenset()
    reg = _registry(tmp_path)
    reg.register("n-ol", "worker_reasoning", "ollama_local", spawned_by_supervisor=True)
    spawn = [e for e in _events(tmp_path) if e.get("kind") == "spawn"]
    assert _data(spawn[0])["adapter_schema_version"] == "node@1.1"


def test_an_id_in_neither_version_is_still_refused_and_still_logged(tmp_path: Path) -> None:
    """The fence's job did not end with the ruling — it moved. `kimi_k3` is the live example: the
    operator has NOT authorized it (it stays OWED-pending-operator per directive §17), so it must
    refuse exactly as the OP-12 ids used to."""
    from control_plane.nodes.registry import RegistrationRefused
    reg = _registry(tmp_path)
    with pytest.raises(RegistrationRefused) as exc:
        reg.register("n-k", "worker_reasoning", "kimi_k3", spawned_by_supervisor=True)
    assert "U227" in str(exc.value)
    assert "node@1.0" in str(exc.value) and "node@1.1" in str(exc.value)
    refusals = [e for e in _events(tmp_path) if e.get("kind") == "registration_refused"]
    assert len(refusals) == 1 and "kimi_k3" in _data(refusals[0])["reason"]


def test_the_i_c1_refusal_still_precedes_the_vocabulary_check(tmp_path: Path) -> None:
    """Widening the vocabulary must not have reordered the gates: a naked session naming a now-legal
    adapter is still refused for being naked (invariant 2)."""
    from control_plane.nodes.registry import RegistrationRefused
    reg = _registry(tmp_path)
    with pytest.raises(RegistrationRefused, match="I-C1"):
        reg.register("n-g", "worker_reasoning", "grok_build", spawned_by_supervisor=False)
    assert not [e for e in _events(tmp_path) if e.get("kind") == "spawn"]


def test_the_vocabulary_is_read_from_the_schema_files_not_re_declared() -> None:
    """A second hand-written copy of an enum is the drift this guard exists to catch, so the guard
    must not contain one. Derived independently here from the files themselves.

    Asserted on `adapter_version_map()` — the function `register()` itself calls. It used to assert
    on a `_schema_adapter_enum()` wrapper, which the 18D validator showed could be widened with the
    FENCE unaffected (MINOR-2); the wrapper is gone and this reads the real source.

    The re-declaration check covers EVERY member of both versions, not the four it started with
    (validator MINOR-4): a literal `claude_code` or `ollama_direct` would have slipped through, and
    those are exactly the ids a well-meaning refactor hardcodes. It is a check on the PARSED source,
    not a substring grep, because the four original members were chosen precisely for never
    appearing in prose — and the module's docstring discusses `ollama_local` and `ollama_direct` by
    name, correctly, at length. A comment naming an id is documentation; a string constant naming
    one is a second vocabulary."""
    import ast
    from control_plane.nodes.registry import adapter_version_map
    from_files = set(V10["properties"]["adapter"]["enum"]) | set(V11["properties"]["adapter"]["enum"])
    assert set(adapter_version_map()) == from_files
    source = (ROOT / "control_plane" / "nodes" / "registry.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = [
        f"line {node.lineno}: {node.value!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.value in from_files
    ]
    assert not offenders, (
        "registry.py declares adapter enum members as string constants — read them from the "
        "schema files instead:\n  " + "\n  ".join(offenders))


def test_the_exemption_list_is_empty_and_that_is_an_assertion_in_its_own_right() -> None:
    """`ADAPTER_EXEMPTIONS` is the one path that widens the node vocabulary with NO operator ruling
    and NO manifest trace — `registry.py` is in neither the frozen nor the amendment hash set, so a
    one-line edit here produces no drift report anywhere (spec-audit m-7). It was previously
    asserted only incidentally, inside a test about `ollama_local`. Under invariant 1 that deserves
    its own name: OP-12.1 demonstrated the schema route works, so the honest bar for populating
    this set is higher than it has ever been, and a populated set must be a deliberate, reviewed
    act that fails this test first."""
    from control_plane.nodes.registry import ADAPTER_EXEMPTIONS
    assert ADAPTER_EXEMPTIONS == frozenset(), (
        "an adapter id is registerable without belonging to any node schema version; that is a "
        "vocabulary widening outside the freeze/amendment discipline and needs an operator ruling")


def test_every_declared_schema_version_exists_and_is_covered_by_the_manifest() -> None:
    """`NODE_SCHEMA_VERSIONS` naming a file that nobody hashes would be a vocabulary source outside
    the freeze/amendment discipline entirely."""
    from control_plane.nodes.registry import NODE_SCHEMA_VERSIONS
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    recorded = {e["path"] for e in manifest["contents"]["schemas"]}
    recorded |= {e["path"] for e in manifest["schema_amendments"]["schema_amendments"]}
    for _version, filename in NODE_SCHEMA_VERSIONS:
        assert (SCHEMA_DIR / filename).is_file(), filename
        assert f"schemas/{filename}" in recorded, filename


def test_an_unreadable_schema_narrows_the_vocabulary_it_never_opens_it(
        tmp_path: Path, monkeypatch) -> None:
    """Fail closed, measured rather than asserted: point the registry at a directory holding a
    corrupt `@1.1` and the OP-12 ids must go back to being refused, not default open."""
    from control_plane.nodes import registry as reg_mod
    fake = tmp_path / "schemas"
    fake.mkdir()
    shutil.copyfile(V10_PATH, fake / "node.schema.json")
    (fake / "node.schema@1.1.json").write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(reg_mod, "_SCHEMA_DIR", fake)
    assert set(reg_mod.adapter_version_map()) == set(V10["properties"]["adapter"]["enum"])
    reg = _registry(tmp_path)
    with pytest.raises(reg_mod.RegistrationRefused):
        reg.register("n-g", "worker_reasoning", "grok_build", spawned_by_supervisor=True)


def test_a_missing_schema_directory_refuses_everything(tmp_path: Path, monkeypatch) -> None:
    from control_plane.nodes import registry as reg_mod
    monkeypatch.setattr(reg_mod, "_SCHEMA_DIR", tmp_path / "nope")
    assert set(reg_mod.adapter_version_map()) == set()
    reg = _registry(tmp_path)
    with pytest.raises(reg_mod.RegistrationRefused):
        reg.register("n-m", "worker_reasoning", "mock", spawned_by_supervisor=True)


def test_a_non_string_enum_contributes_nothing(tmp_path: Path, monkeypatch) -> None:
    """`frozenset([...])` over a malformed enum would happily admit `1` or `None` as an adapter id;
    the type check is what stops a corrupted file from widening anything at all."""
    from control_plane.nodes import registry as reg_mod
    fake = tmp_path / "schemas"
    fake.mkdir()
    shutil.copyfile(V10_PATH, fake / "node.schema.json")
    (fake / "node.schema@1.1.json").write_text(
        json.dumps({"properties": {"adapter": {"enum": ["grok_build", 7]}}}), encoding="utf-8")
    monkeypatch.setattr(reg_mod, "_SCHEMA_DIR", fake)
    assert set(reg_mod.adapter_version_map()) == set(V10["properties"]["adapter"]["enum"])


def test_caller_metadata_cannot_overwrite_the_recorded_schema_version(tmp_path: Path) -> None:
    """The provenance field is the registry's own claim. A caller passing
    `adapter_schema_version="node@1.0"` for a `@1.1` adapter must not be able to launder it."""
    reg = _registry(tmp_path)
    reg.register("n-g", "worker_reasoning", "grok_build", spawned_by_supervisor=True,
                 adapter_schema_version="node@1.0")
    spawn = [e for e in _events(tmp_path) if e.get("kind") == "spawn"]
    assert _data(spawn[0])["adapter_schema_version"] == "node@1.1"


# ---- claim 4: the manifest records it without disturbing the signature ------------------------

def test_the_amendment_is_recorded_with_its_authorizing_ruling() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = manifest["schema_amendments"]["schema_amendments"]
    assert [e["path"] for e in entries] == ["schemas/node.schema@1.1.json"]
    entry = entries[0]
    assert entry["schema_id"] == "https://sovereign.local/schemas/node@1.1"
    assert "OP-12.1" in entry["authorized_by"]
    import hashlib
    assert entry["sha256"] == hashlib.sha256(V11_PATH.read_bytes()).hexdigest().upper()


def test_recording_the_amendment_did_not_move_the_freeze_hash_or_the_signature() -> None:
    """U222, enforced. The signed value is the one Phase 0 recorded; the amendment block is
    computed after it and stored outside `contents`, so it cannot reach it."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["freeze_integrity_sha256"] == \
        "B1A16B223B8D1197593C7EF658C7C6D875C152EB68207E3F846DFBC479F8B667"
    # U496/U498: two authorized section-7.1 edits (CLAUDE.md retractions) moved the freeze
    # hash and reset the signature to PENDING; re-signing is an operator act queued once.
    # This pin takes the new recorded value DELIBERATELY - the next legitimate move of
    # either fact must update this pin again, saying why.
    assert manifest["operator_signature"]["status"] == "PENDING"
    assert manifest["schema_versions_fixed_at"] == "@1.0"
    assert "https://sovereign.local/schemas/node@1.1" not in manifest["schema_ids"]


def test_the_manifest_is_reproducible_on_this_host() -> None:
    """The generator ordering fix (U293), measured: regenerating on Windows must reproduce the
    Linux-generated freeze hash exactly. Runs `build_manifest()` in-process — no file is written."""
    sys.path.insert(0, str(ROOT / "tools" / "manifest"))
    try:
        import compute_manifest  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    built = compute_manifest.build_manifest()
    assert built["freeze_integrity_sha256"] == \
        "B1A16B223B8D1197593C7EF658C7C6D875C152EB68207E3F846DFBC479F8B667"
    recorded = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert built["contents"] == recorded["contents"]
    assert built["schema_amendments"] == recorded["schema_amendments"]


def test_the_ordering_key_is_platform_independent() -> None:
    """The defect itself, pinned: `sorted(Path)` case-normalises on Windows. The recorded order is
    the case-SENSITIVE one, and `sorted_files` must reproduce it on either platform."""
    sys.path.insert(0, str(ROOT / "tools" / "manifest"))
    try:
        import compute_manifest  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    names = [p.name for p in compute_manifest.sorted_files(ROOT / "docs" / "canonical", "*")]
    assert names == sorted(names), "must be plain case-sensitive string order"
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert [Path(e["path"]).name for e in manifest["contents"]["canonical_documents"]] == names


def _sandbox_repo(tmp_path: Path) -> tuple[Path, "callable"]:
    """A COPY of the parts of the repo the manifest tool reads, plus a `--check` runner over it.

    Every end-to-end manifest test runs here rather than against the real tree: `--check` is a
    whole-repo operation and the alternative is mutating the operator's actual frozen set inside a
    test. `AUTONOMOUS_BUILD_DIRECTIVE.md` is carried because attribution now authenticates against
    it (spec-audit M-3) — without it every amendment would read UNATTRIBUTED and the drift tests
    would pass for the wrong reason. The governance EXTRA files are carried for the same class of
    reason: `--check` now verifies `freeze_integrity_sha256` itself, and a sandbox missing them
    computes a different (and perfectly correct) hash for a different tree. That list is READ FROM
    THE TOOL rather than re-typed here, so a file added to `EXTRA` is carried automatically."""
    sys.path.insert(0, str(ROOT / "tools" / "manifest"))
    try:
        import compute_manifest  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    sandbox = tmp_path / "repo"
    (sandbox / "docs").mkdir(parents=True)
    (sandbox / "tools" / "manifest").mkdir(parents=True)
    for rel in ("schemas", "conductor", "docs/canonical", "docs/registers", "docs/evidence"):
        src = ROOT / rel
        if src.is_dir():
            shutil.copytree(src, sandbox / rel)
    for rel in list(compute_manifest.EXTRA) + list(compute_manifest.MUTABLE_EXTRA):
        src = ROOT / rel
        if src.is_file():
            (sandbox / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, sandbox / rel)
    shutil.copyfile(ROOT / "tools" / "manifest" / "compute_manifest.py",
                    sandbox / "tools" / "manifest" / "compute_manifest.py")
    shutil.copyfile(ROOT / "AUTONOMOUS_BUILD_DIRECTIVE.md", sandbox / "AUTONOMOUS_BUILD_DIRECTIVE.md")
    shutil.copyfile(MANIFEST_PATH, sandbox / "docs" / "PHASE0_FREEZE_MANIFEST.json")
    tool = str(sandbox / "tools" / "manifest" / "compute_manifest.py")

    def check() -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, tool, "--check"], capture_output=True, text=True)

    return sandbox, check


def test_manifest_check_reports_amendment_drift_as_hard_failure(tmp_path: Path) -> None:
    """An amendment file changing after it was recorded is the same class of event as a frozen file
    changing. Exercised end to end against a COPY of the repo tree so the real one is untouched."""
    sandbox, check = _sandbox_repo(tmp_path)

    # baseline: the sandbox now carries every file the freeze hash covers, so a clean `--check` here
    # is the same statement it is in the real tree — including the freeze hash itself.
    before = check()
    # The DRIFT markers, not the bare word. `--check` also prints an INFO line naming the mutable
    # docs it does not cover, and the moment `docs/evidence/PHASE18D_AMENDMENT_CHECKPOINT.md`
    # landed — in the very evidence commit of the unit that wrote this test — that INFO line
    # contained the substring "AMENDMENT" and this baseline went red on a clean tree. U298: a test
    # whose assertion matches a FILENAME rather than an outcome is a test that fails for reasons
    # its subject has nothing to do with.
    for marker in ("AMENDMENT NEW", "AMENDMENT CHANGED", "AMENDMENT REMOVED"):
        assert marker not in before.stdout + before.stderr, before.stderr

    target = sandbox / "schemas" / "node.schema@1.1.json"
    target.write_text(target.read_text(encoding="utf-8").replace(
        '"grok_build"', '"grok_build_TAMPERED"'), encoding="utf-8")
    after = check()
    assert after.returncode == 1
    assert "AMENDMENT CHANGED: schemas/node.schema@1.1.json" in after.stderr, after.stderr

    target.unlink()
    removed = check()
    assert removed.returncode == 1
    assert "AMENDMENT REMOVED: schemas/node.schema@1.1.json" in removed.stderr, removed.stderr


def test_an_unattributed_amendment_file_is_itself_drift(tmp_path: Path) -> None:
    """A schema successor naming no operator ruling is exactly what the block exists to prevent —
    it must not be possible to add one quietly and have `--check` stay green.

    **This test used to assert only that today's entries are attributed** (spec-audit m-9): it never
    planted a file and never ran `--check`, while the neighbouring test did exactly that for
    CHANGED/REMOVED. The docstring's claim and the assertions were different claims. Now it plants
    one."""
    sys.path.insert(0, str(ROOT / "tools" / "manifest"))
    try:
        import compute_manifest  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    entries = compute_manifest.build_manifest()["schema_amendments"]["schema_amendments"]
    assert all(not e["authorized_by"].startswith("UNATTRIBUTED") for e in entries)
    assert set(compute_manifest.AMENDMENT_AUTHORIZATIONS) == {e["path"] for e in entries}

    sandbox, check = _sandbox_repo(tmp_path)
    assert check().returncode == 0
    (sandbox / "schemas" / "node.schema@1.2.json").write_text(
        json.dumps({"$id": "https://sovereign.local/schemas/node@1.2"}), encoding="utf-8")
    after = check()
    assert after.returncode == 1
    assert "AMENDMENT UNATTRIBUTED: schemas/node.schema@1.2.json" in after.stderr, after.stderr
    assert "AMENDMENT NEW: schemas/node.schema@1.2.json" in after.stderr, after.stderr


def test_an_amendment_citing_a_ruling_nobody_recorded_is_unattributed(tmp_path: Path) -> None:
    """Attribution is AUTHENTICATED, not merely present (spec-audit M-3).

    The failure this closes: add a successor schema, add a `NODE_SCHEMA_VERSIONS` row, and type an
    invented ruling id into `AMENDMENT_AUTHORIZATIONS`. Before this, every automated check stayed
    green and the canonical node vocabulary had widened with no operator act behind it — invariant 1
    inverted, with a citation. The authentication is deliberately weak (both sources are repo files
    a builder can edit) and that is stated rather than dressed up: it is the difference between a
    name being TYPED and a name REFERRING to something a reviewer can go read, and it fails closed
    in the direction of UNATTRIBUTED."""
    sandbox, check = _sandbox_repo(tmp_path)
    assert check().returncode == 0

    invented_ruling = "OP-999999.999999"
    ruling_sources = [sandbox / "AUTONOMOUS_BUILD_DIRECTIVE.md",
                      sandbox / "docs" / "registers" / "DECISION_REGISTER.md"]
    assert all(invented_ruling not in source.read_text(encoding="utf-8")
               for source in ruling_sources), "negative control must cite an unrecorded ruling"

    successor = sandbox / "schemas" / "node.schema@1.2.json"
    successor.write_text(json.dumps({"$id": "https://sovereign.local/schemas/node@1.2"}),
                         encoding="utf-8")
    tool_path = sandbox / "tools" / "manifest" / "compute_manifest.py"
    tool_path.write_text(tool_path.read_text(encoding="utf-8").replace(
        'AMENDMENT_AUTHORIZATIONS = {',
        'AMENDMENT_AUTHORIZATIONS = {\n    "schemas/node.schema@1.2.json": '
        f'"{invented_ruling} (operator, 2099-09-09) - an amendment nobody ruled",'),
        encoding="utf-8")

    invented = check()
    assert invented.returncode == 1
    assert "AMENDMENT UNATTRIBUTED: schemas/node.schema@1.2.json" in invented.stderr, invented.stderr
    assert invented_ruling in invented.stderr, invented.stderr

    # and the control: a REAL ruling id, recorded in the directive, authenticates.
    tool_path.write_text(tool_path.read_text(encoding="utf-8").replace(
        f"{invented_ruling} (operator, 2099-09-09) - an amendment nobody ruled",
        "OP-12.1 (operator, 2026-08-01) - the ruling that IS recorded"), encoding="utf-8")
    real = check()
    assert "AMENDMENT UNATTRIBUTED" not in real.stderr, real.stderr
    assert "AMENDMENT NEW: schemas/node.schema@1.2.json" in real.stderr, real.stderr


def test_check_verifies_the_two_integrity_hashes_it_publishes(tmp_path: Path) -> None:
    """Both were falsifiable with `--check` staying green (validator NIT-1 / spec-audit m-4). The
    per-file hashes did the real work, so nothing operational turned on them — but
    `freeze_integrity_sha256` is the value the operator's signature binds, and a published number
    nobody verifies teaches a reader to trust a number that means nothing."""
    sandbox, check = _sandbox_repo(tmp_path)
    manifest_path = sandbox / "docs" / "PHASE0_FREEZE_MANIFEST.json"
    pristine = manifest_path.read_text(encoding="utf-8")
    assert check().returncode == 0

    doc = json.loads(pristine)
    doc["freeze_integrity_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    freeze = check()
    assert freeze.returncode == 1 and "FREEZE INTEGRITY HASH MISMATCH" in freeze.stderr, freeze.stderr

    doc = json.loads(pristine)
    doc["schema_amendments"]["amendment_integrity_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    amendment = check()
    assert amendment.returncode == 1, amendment.stdout
    assert "AMENDMENT INTEGRITY HASH MISMATCH" in amendment.stderr, amendment.stderr


def test_relabelling_a_recorded_amendment_under_another_ruling_is_drift(tmp_path: Path) -> None:
    """The attribution is the operator act; the file hash is only the artifact. Re-labelling a
    recorded amendment changes no byte of the schema and was invisible to `--check` (spec-audit
    m-5)."""
    sandbox, check = _sandbox_repo(tmp_path)
    manifest_path = sandbox / "docs" / "PHASE0_FREEZE_MANIFEST.json"
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = doc["schema_amendments"]["schema_amendments"][0]
    entry["authorized_by"] = entry["authorized_by"].replace("OP-12.1", "OP-6")
    manifest_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    relabelled = check()
    assert relabelled.returncode == 1
    assert "AMENDMENT ATTRIBUTION CHANGED" in relabelled.stderr, relabelled.stderr


def test_every_glob_collection_site_uses_the_platform_independent_key() -> None:
    """U293's fix applied at ONE of three call sites would leave two live (validator MINOR-1): the
    `MUTABLE_SETS` and `AMENDMENT_SETS` collections had no red-able test, because a reversion there
    only shows up as manifest churn on a platform whose case ordering differs. Checked on the parsed
    source instead, so it goes red on either platform: no `sorted(...)` may wrap a `.glob(...)`, and
    every collection loop must go through `sorted_files`."""
    import ast
    source = (ROOT / "tools" / "manifest" / "compute_manifest.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "sorted" and node.args):
            continue
        inner = node.args[0]
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) \
                and inner.func.attr == "glob":
            offenders.append(f"line {node.lineno}: sorted() over a .glob() — use sorted_files()")
    assert not offenders, "\n".join(offenders)
    assert source.count("sorted_files(") >= 4, (
        "expected the definition plus one call per collection site (SETS, MUTABLE_SETS, "
        "AMENDMENT_SETS); a site that stopped calling it is the U293 reversion")
