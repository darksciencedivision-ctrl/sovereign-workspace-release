"""SW-25 (part a): one state-root resolver; no product code writes state beneath the install root.

The finding: Sovereign wrote `runtime`, `published` and `library/queues` beneath its module root, so a
read-only install, an upgrade that swaps the code tree, a backup, or a second install all collided with
state. Part (a) makes every state reader/writer resolve through `sovereign_product.paths` (the state
HOME and its runtime dir) and gives state-dir artifacts their own `sovereign-state://` pointer
namespace, so moving the state out of the install tree is a configuration change rather than a code
hunt. These tests inject the failure (state configured outside the install root, hostile overrides,
secret-path pointers) and assert the install tree is never the target.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import paths as P  # noqa: E402

STATE_ENV_KEYS = ("SOVEREIGN_STATE_HOME", "SOVEREIGN_STATE_DIR", "SOVEREIGN_WORKSPACE_STATE",
                  "SOVEREIGN_EVIDENCE_DIR", "SOVEREIGN_DB_PATH", "SOVEREIGN_ROOT")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for key in STATE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    local = tmp_path / "LocalAppData"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return local


def _install(tmp_path: Path, *, layout: str | None = None) -> Path:
    root = tmp_path / "install root"
    root.mkdir()
    (root / P.ROOT_MARKER).write_text(P.ROOT_MARKER_CONTENT, encoding="utf-8")
    (root / "SYSTEM_MANIFEST.json").write_text("{}", encoding="utf-8")
    if layout is not None:
        (root / P.STATE_LAYOUT_FILE).write_text(json.dumps({"schema": 1, "state": layout}),
                                                encoding="utf-8")
    return root


def _tree(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")}


# --- the guard: no direct state paths outside paths.py ---------------------------------------------

# Provisioned llama.cpp BINARY location (an install asset, not mutable state) - kept in the install
# tree by operator decision (SW-25 design, decision 3).
_ALLOWED = {
    ("sovereign_product/supervisor_service.py",
     'Path(base) / "runtime" / "llama.cpp" / "current" / "llama-server.exe"'),
}
_STATE_LITERAL = re.compile(r'/\s*"(runtime|published|queues)"')


def test_sw25_no_direct_state_path_literals_outside_paths_module():
    files = sorted((SOV_ROOT / "sovereign_product").glob("*.py")) + [
        SOV_ROOT / "publication_gate.py",
        SOV_ROOT / "knowledge_base" / "common.py",
        SOV_ROOT / "tools" / "sovereign_paths.py",
    ]
    offenders = []
    for path in files:
        rel = path.relative_to(SOV_ROOT).as_posix()
        if rel == "sovereign_product/paths.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if _STATE_LITERAL.search(line) and not any(
                    rel == a_rel and a_text in line for a_rel, a_text in _ALLOWED):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "state paths must resolve through sovereign_product.paths (SW-25):\n" + "\n".join(offenders))


# --- resolution -----------------------------------------------------------------------------------

def test_sw25_bare_root_keeps_legacy_layout(clean_env, tmp_path):
    root = _install(tmp_path)
    assert P.resolve_state_home(root) == root.resolve()
    assert P.resolve_runtime_dir(root) == root.resolve() / "runtime"


def test_sw25_external_layout_resolves_outside_install_tree(clean_env, tmp_path):
    root = _install(tmp_path, layout="external")
    home = clean_env.resolve() / "SovereignWorkspace" / "sovereign"
    assert P.resolve_state_home(root) == home
    assert P.resolve_runtime_dir(root) == home / "runtime"
    assert P.resolve_published_dir(root) == home / "published"
    assert P.resolve_queue_dir(root) == home / "library" / "queues"
    paths = P.resolve_product_paths(root, create=True)
    assert paths.state_dir == home / "runtime"
    assert paths.db_path == home / "runtime" / "sovereign.db"
    assert paths.evidence_dir == home / "runtime" / "evidence"
    assert _tree(root) == {".sovereign-root", "SYSTEM_MANIFEST.json", "STATE_LAYOUT.json"}


def test_sw25_workspace_state_env_relocates_external_home(clean_env, tmp_path):
    root = _install(tmp_path, layout="external")
    relocated = tmp_path / "relocated ws"
    env = {"LOCALAPPDATA": str(clean_env), "SOVEREIGN_WORKSPACE_STATE": str(relocated)}
    assert P.resolve_state_home(root, env=env) == relocated.resolve() / "sovereign"


def test_sw25_explicit_state_home_env_wins(clean_env, tmp_path):
    root = _install(tmp_path)
    home = clean_env / "SovereignWorkspace" / "sovereign"
    env = {"LOCALAPPDATA": str(clean_env), "SOVEREIGN_STATE_HOME": str(home)}
    assert P.resolve_runtime_dir(root, env=env) == home.resolve() / "runtime"


@pytest.mark.parametrize("hostile", [
    r"\\server\share\state",
    r"\\?\C:\state",
    r"\\.\PhysicalDrive0",
])
def test_sw25_unc_and_device_state_homes_are_refused(clean_env, tmp_path, hostile):
    root = _install(tmp_path)
    with pytest.raises(P.PathResolutionError):
        P.resolve_state_home(root, env={"LOCALAPPDATA": str(clean_env),
                                        "SOVEREIGN_STATE_HOME": hostile})


def test_sw25_state_home_outside_trusted_bases_is_refused(clean_env, tmp_path):
    root = _install(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    with pytest.raises(P.PathResolutionError):
        P.resolve_state_home(root, env={"LOCALAPPDATA": str(clean_env),
                                        "SOVEREIGN_STATE_HOME": str(elsewhere)})
    with pytest.raises(P.PathResolutionError):
        P.resolve_runtime_dir(root, env={"LOCALAPPDATA": str(clean_env),
                                         "SOVEREIGN_STATE_DIR": str(elsewhere)})


def test_sw25_relative_workspace_state_cannot_escape_localappdata(clean_env, tmp_path):
    with pytest.raises(P.PathResolutionError):
        P.workspace_state_bases({"LOCALAPPDATA": str(clean_env),
                                 "SOVEREIGN_WORKSPACE_STATE": r"..\..\escape"})


@pytest.mark.parametrize("body", ['{"state": "sideways"}', "not json", "[]"])
def test_sw25_malformed_layout_fails_closed(clean_env, tmp_path, body):
    root = _install(tmp_path)
    (root / P.STATE_LAYOUT_FILE).write_text(body, encoding="utf-8")
    with pytest.raises(P.PathResolutionError):
        P.resolve_state_home(root)


# --- pointers -------------------------------------------------------------------------------------

def test_sw25_state_artifacts_get_state_pointers_that_round_trip(clean_env, tmp_path):
    root = _install(tmp_path, layout="external")
    paths = P.resolve_product_paths(root, create=True)
    artifact = paths.evidence_dir / "semantic_deep" / "s1" / "request.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")
    pointer = paths.pointer(artifact)
    assert pointer == "sovereign-state://evidence/semantic_deep/s1/request.json"
    assert paths.resolve_pointer(pointer, must_exist=True) == artifact.resolve()
    # Install-tree artifacts keep the portable root namespace.
    assert paths.pointer(root / "SYSTEM_MANIFEST.json") == "sovereign://SYSTEM_MANIFEST.json"


def test_sw25_legacy_runtime_pointer_remaps_into_external_state(clean_env, tmp_path):
    root = _install(tmp_path, layout="external")
    paths = P.resolve_product_paths(root, create=True)
    artifact = paths.evidence_dir / "old.json"
    artifact.write_text("{}", encoding="utf-8")
    assert paths.resolve_pointer("sovereign://runtime/evidence/old.json",
                                 must_exist=True) == artifact.resolve()


@pytest.mark.parametrize("pointer", [
    "sovereign-state://../escape.txt",
    "sovereign-state://evidence/../../escape.txt",
    "sovereign-state:///abs",
    "sovereign-state://C:/Windows/win.ini",
])
def test_sw25_state_pointer_traversal_is_refused(clean_env, tmp_path, pointer):
    root = _install(tmp_path, layout="external")
    paths = P.resolve_product_paths(root, create=True)
    with pytest.raises(P.UnsafeArtifactPointer):
        paths.resolve_pointer(pointer)


def test_sw25_path_outside_root_and_state_gets_no_pointer(clean_env, tmp_path):
    root = _install(tmp_path, layout="external")
    paths = P.resolve_product_paths(root, create=True)
    with pytest.raises(P.UnsafeArtifactPointer):
        paths.pointer(tmp_path / "outside.txt")


@pytest.mark.parametrize("layout", [None, "external"])
@pytest.mark.parametrize("pointer", [
    "sovereign://runtime/llamacpp_supervisor/api_key",
    "sovereign-state://llamacpp_supervisor/api_key",
    "sovereign-state://freetoken_supervisor/consumer.env",
])
def test_sw25_no_pointer_resolves_into_supervisor_secrets(clean_env, tmp_path, layout, pointer):
    root = _install(tmp_path, layout=layout)
    paths = P.resolve_product_paths(root, create=True)
    for base in (paths.state_dir, root / "runtime"):
        secret = base / "llamacpp_supervisor" / "api_key"
        secret.parent.mkdir(parents=True, exist_ok=True)
        secret.write_text("SECRET", encoding="utf-8")
    with pytest.raises(P.UnsafeArtifactPointer):
        paths.resolve_pointer(pointer)


# --- consumers follow the resolver ----------------------------------------------------------------

def test_sw25_service_helpers_write_to_external_state_not_install(clean_env, tmp_path, monkeypatch):
    from sovereign_product import backend_selection, freetoken_service, gpu_occupancy
    from sovereign_product import supervisor_service

    root = _install(tmp_path, layout="external")
    runtime = clean_env.resolve() / "SovereignWorkspace" / "sovereign" / "runtime"
    assert supervisor_service.service_dir(root) == runtime / "llamacpp_supervisor"
    assert freetoken_service.service_dir(root) == runtime / "freetoken_supervisor"
    assert gpu_occupancy.occupancy_path(root) == runtime / "gpu_occupancy.json"
    assert backend_selection.selection_path(root) == runtime / "backend_selection.json"

    before = _tree(root)
    with gpu_occupancy.transition_lock(root, "llama.cpp"):
        pass
    supervisor_service.write_state(root, {"pid": 0})
    assert _tree(root) == before, "a runtime write landed inside the install tree"
    assert (runtime / "llamacpp_supervisor" / "state.json").is_file()


def test_sw25_supervisor_api_key_is_read_from_state_dir(clean_env, tmp_path, monkeypatch):
    from sovereign_product import gpu_occupancy

    monkeypatch.delenv("SOVEREIGN_LLAMA_CPP_API_KEY", raising=False)
    root = _install(tmp_path, layout="external")
    key = P.resolve_runtime_dir(root) / "llamacpp_supervisor" / "api_key"
    key.parent.mkdir(parents=True)
    key.write_text("k-external", encoding="utf-8")
    stale = root / "runtime" / "llamacpp_supervisor" / "api_key"
    stale.parent.mkdir(parents=True)
    stale.write_text("k-stale-install-tree", encoding="utf-8")
    assert gpu_occupancy.llama_cpp_api_key(root) == "k-external"


def test_sw25_publication_gate_index_lives_in_state_home(clean_env, tmp_path):
    import publication_gate

    root = _install(tmp_path, layout="external")
    home = clean_env.resolve() / "SovereignWorkspace" / "sovereign"
    gate_paths = publication_gate._paths(root)
    assert gate_paths["pub_index"] == home / "published" / "index" / "index.jsonl"
    assert gate_paths["gate_log"].parent == home / "published" / "index"


class _NoClient:
    def generate(self, *a, **k):  # pragma: no cover - never called
        raise AssertionError("no model call expected")


def test_sw25_semantic_deep_accepts_external_state_and_emits_state_refs(clean_env, tmp_path):
    from sovereign_product.semantic_deep import SemanticDeepExecutor

    root = _install(tmp_path, layout="external")
    paths = P.resolve_product_paths(root, create=True)
    executor = SemanticDeepExecutor(root, _NoClient(),
                                    artifact_root=paths.evidence_dir / "semantic_deep",
                                    state_dir=paths.state_dir)
    run_dir = executor._create_run_directory("s1", "e1")
    request = run_dir / "request.json"
    request.write_text("{}", encoding="utf-8")
    ref = executor._artifact_ref(request)
    assert ref == "sovereign-state://evidence/semantic_deep/s1/e1/request.json"
    assert paths.resolve_pointer(ref, must_exist=True) == request.resolve()
    assert not (root / "runtime").exists()


def test_sw25_semantic_deep_refuses_artifact_root_outside_root_and_state(clean_env, tmp_path):
    from sovereign_product.semantic_deep import SemanticDeepExecutor

    root = _install(tmp_path, layout="external")
    paths = P.resolve_product_paths(root, create=True)
    with pytest.raises(ValueError):
        SemanticDeepExecutor(root, _NoClient(), artifact_root=tmp_path / "rogue",
                             state_dir=paths.state_dir)
