"""SW-25 (part c): model assignment never writes the shipped SYSTEM_MANIFEST.json.

The finding: `_write_manifest` rewrote the tracked, shipped manifest in the install tree whenever the
operator assigned a model, so a read-only install could not assign models, an upgrade silently threw
the choices away, and a release file changed at runtime. Now operator choices live in
`<state home>/config/manifest.overrides.json` and are layered over the immutable shipped manifest
wherever it is loaded. Failure injection: a read-only shipped manifest, hostile/malformed override
files, an assignment that would invalidate the effective manifest, and a pre-SW-25 in-place edit that
must survive an upgrade.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SOV_ROOT = RELEASE_ROOT / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

import system_manifest as SM  # noqa: E402
from sovereign_product import manifest_overrides as MO  # noqa: E402
from sovereign_product import paths as P  # noqa: E402
from sovereign_product import state_migration as M  # noqa: E402

STATE_ENV_KEYS = ("SOVEREIGN_STATE_HOME", "SOVEREIGN_STATE_DIR", "SOVEREIGN_WORKSPACE_STATE",
                  "SOVEREIGN_EVIDENCE_DIR", "SOVEREIGN_DB_PATH", "SOVEREIGN_ROOT")
SHIPPED_BYTES = (SOV_ROOT / "SYSTEM_MANIFEST.json").read_bytes()


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for key in STATE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    local = tmp_path / "LocalAppData"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return local


def _install(tmp_path: Path, *, manifest: bytes = SHIPPED_BYTES, digest: str | None = None) -> Path:
    root = tmp_path / "install root"
    root.mkdir()
    (root / P.ROOT_MARKER).write_text(P.ROOT_MARKER_CONTENT, encoding="utf-8")
    layout = {"schema": 1, "state": "external"}
    if digest is not None:
        layout["shipped_manifest_sha256"] = digest
    (root / P.STATE_LAYOUT_FILE).write_text(json.dumps(layout), encoding="utf-8")
    (root / "SYSTEM_MANIFEST.json").write_bytes(manifest)
    return root


def _shipped_models() -> dict:
    return json.loads(SHIPPED_BYTES.decode("utf-8-sig"))["MODELS"]


def _assign(root: Path, updates: dict) -> None:
    from sovereign_product.server import ProductService

    ProductService._write_model_overrides(SimpleNamespace(root=root), updates)


# --- the shipped manifest is never written --------------------------------------------------------

def test_sw25c_assignment_writes_overrides_not_the_shipped_manifest(clean_env, tmp_path):
    root = _install(tmp_path)
    manifest = root / "SYSTEM_MANIFEST.json"
    os.chmod(manifest, stat.S_IREAD)  # a read-only install
    try:
        _assign(root, {"PRIMARY_REASONER": "operator-choice:1b"})
        assert manifest.read_bytes() == SHIPPED_BYTES, "the shipped manifest was modified"
        effective = SM.load_system_manifest(manifest_path=manifest)
        assert effective["MODELS"]["PRIMARY_REASONER"] == "operator-choice:1b"
        shipped = SM.load_shipped_manifest(manifest_path=manifest)
        assert shipped["MODELS"]["PRIMARY_REASONER"] == _shipped_models()["PRIMARY_REASONER"]
        overrides = json.loads(MO.overrides_path(root).read_text(encoding="utf-8"))
        assert overrides["MODELS"] == {"PRIMARY_REASONER": "operator-choice:1b"}
        assert MO.overrides_path(root).is_relative_to(P.resolve_state_home(root))
    finally:
        os.chmod(manifest, stat.S_IREAD | stat.S_IWRITE)


def test_sw25c_resetting_a_role_to_its_shipped_value_drops_the_override(clean_env, tmp_path):
    root = _install(tmp_path)
    shipped_value = _shipped_models()["CRITIC"]
    _assign(root, {"CRITIC": "other:7b", "SYNTHESIZER": "syn:14b"})
    _assign(root, {"CRITIC": shipped_value})
    overrides = json.loads(MO.overrides_path(root).read_text(encoding="utf-8"))
    assert overrides["MODELS"] == {"SYNTHESIZER": "syn:14b"}


def test_sw25c_effective_manifest_survives_replacing_the_install_tree(clean_env, tmp_path):
    root = _install(tmp_path)
    _assign(root, {"PRIMARY_REASONER": "kept:1b"})
    # Upgrade: the install tree is replaced wholesale with a fresh copy of the release.
    (root / "SYSTEM_MANIFEST.json").write_bytes(SHIPPED_BYTES)
    effective = SM.load_system_manifest(manifest_path=root / "SYSTEM_MANIFEST.json")
    assert effective["MODELS"]["PRIMARY_REASONER"] == "kept:1b"


# --- the override file cannot do more than assign models ------------------------------------------

@pytest.mark.parametrize("payload", [
    {"schema": 1, "RUNTIME": {"OLLAMA_BASE_URL": "http://evil.example:80"}},
    {"schema": 1, "THRESHOLDS": {"CLAIM_AGREE_COSINE": 5}},
    {"schema": 1, "MODELS": {"NOT_A_ROLE": "x"}},
    {"schema": 1, "MODELS": {"CRITIC": ""}},
    {"schema": 1, "MODELS": {"CRITIC": 7}},
    {"schema": 2, "MODELS": {}},
    {"schema": 1, "MODELS": [], },
    ["not", "an", "object"],
])
def test_sw25c_hostile_or_malformed_overrides_fail_closed(clean_env, tmp_path, payload):
    root = _install(tmp_path)
    path = MO.overrides_path(root)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SM.ManifestConfigError):
        SM.load_system_manifest(manifest_path=root / "SYSTEM_MANIFEST.json")


def test_sw25c_unreadable_overrides_fail_closed(clean_env, tmp_path):
    root = _install(tmp_path)
    path = MO.overrides_path(root)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SM.ManifestConfigError):
        SM.load_system_manifest(manifest_path=root / "SYSTEM_MANIFEST.json")


def test_sw25c_invalid_assignment_is_refused_and_nothing_is_written(clean_env, tmp_path):
    from sovereign_product.server import ServiceConfigurationError

    root = _install(tmp_path)
    with pytest.raises(ServiceConfigurationError):
        _assign(root, {"NOT_A_ROLE": "x"})
    assert not MO.overrides_path(root).exists()
    assert (root / "SYSTEM_MANIFEST.json").read_bytes() == SHIPPED_BYTES


def test_sw25c_a_manifest_outside_an_install_root_gets_no_overrides(clean_env, tmp_path):
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "SYSTEM_MANIFEST.json").write_bytes(SHIPPED_BYTES)
    loaded = SM.load_system_manifest(manifest_path=loose / "SYSTEM_MANIFEST.json")
    assert loaded["MODELS"] == SM.load_shipped_manifest(
        manifest_path=loose / "SYSTEM_MANIFEST.json")["MODELS"]


# --- introspection reports the effective configuration --------------------------------------------

def test_sw25c_introspection_reports_effective_roles_and_the_override_file(clean_env, tmp_path):
    from sovereign_product.introspection import collect_self_state

    root = _install(tmp_path)
    _assign(root, {"PRIMARY_REASONER": "effective:1b"})

    def offline(url, timeout):
        raise OSError("offline")

    state = collect_self_state(root, http_get=offline, timeout=0.01)
    manifest = state["manifest"]
    assert manifest["configured_models_by_role"]["PRIMARY_REASONER"] == "effective:1b"
    assert manifest["overrides"] == "config/manifest.overrides.json"
    assert manifest["overrides_error"] is None
    assert len(manifest["effective_sha256"]) == 64


# --- pre-SW-25 in-place edits are carried into the overrides once ---------------------------------

def test_sw25c_shipped_layout_records_the_shipped_manifest_digest():
    layout = json.loads((SOV_ROOT / P.STATE_LAYOUT_FILE).read_text(encoding="utf-8"))
    assert layout["shipped_manifest_sha256"] == hashlib.sha256(SHIPPED_BYTES).hexdigest(), (
        "SYSTEM_MANIFEST.json changed: update STATE_LAYOUT.json shipped_manifest_sha256")


def test_sw25c_in_place_edited_manifest_is_captured_into_overrides(clean_env, tmp_path):
    edited = json.loads(SHIPPED_BYTES.decode("utf-8-sig"))
    edited["MODELS"]["PRIMARY_REASONER"] = "legacy-edit:3b"
    root = _install(tmp_path, manifest=json.dumps(edited).encode("utf-8"),
                    digest=hashlib.sha256(SHIPPED_BYTES).hexdigest())
    M.ensure_state_home(root)
    captured = json.loads(MO.overrides_path(root).read_text(encoding="utf-8"))
    assert captured["MODELS"]["PRIMARY_REASONER"] == "legacy-edit:3b"
    assert "pre-SW-25" in captured["source"]
    # The upgrade then restores the pristine manifest; the operator's choice survives.
    (root / "SYSTEM_MANIFEST.json").write_bytes(SHIPPED_BYTES)
    effective = SM.load_system_manifest(manifest_path=root / "SYSTEM_MANIFEST.json")
    assert effective["MODELS"]["PRIMARY_REASONER"] == "legacy-edit:3b"


def test_sw25c_pristine_manifest_captures_nothing(clean_env, tmp_path):
    root = _install(tmp_path, digest=hashlib.sha256(SHIPPED_BYTES).hexdigest())
    M.ensure_state_home(root)
    assert not MO.overrides_path(root).exists()


def test_sw25c_capture_never_replaces_existing_overrides(clean_env, tmp_path):
    edited = json.loads(SHIPPED_BYTES.decode("utf-8-sig"))
    edited["MODELS"]["PRIMARY_REASONER"] = "legacy-edit:3b"
    root = _install(tmp_path, manifest=json.dumps(edited).encode("utf-8"),
                    digest=hashlib.sha256(SHIPPED_BYTES).hexdigest())
    path = MO.overrides_path(root)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema": 1, "MODELS": {"CRITIC": "mine:1b"}}), encoding="utf-8")
    M.ensure_state_home(root)
    assert json.loads(path.read_text(encoding="utf-8"))["MODELS"] == {"CRITIC": "mine:1b"}


def test_sw25c_server_has_no_shipped_manifest_writer():
    source = (SOV_ROOT / "sovereign_product" / "server.py").read_text(encoding="utf-8")
    assert "def _write_manifest" not in source
    assert '"utf-8-sig", newline' not in source, "a manifest-style writer is back in server.py"
