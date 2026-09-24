"""SW-25 (part b): the shipped install opts in to the external state home, and legacy state migrates.

Part (a) made every state path resolve through one resolver. Part (b) turns it on:
`modules/sovereign/STATE_LAYOUT.json` declares the external layout; the shell adapters hand SOVEREIGN
(and the llama.cpp supervisor, which shares SOVEREIGN's runtime dir) the per-user state root instead of
`${root}/runtime`; `Start-Shell.ps1` and the SOVEREIGN scripts locate state through a PowerShell twin of
the resolver; and the first process that needs state COPIES legacy install-tree state across once
(operator decision: copy, never move, so a rollback still finds its own state).

Failure injection: a non-empty destination, an interrupted earlier migration, a held/stale lock, a
module trying to declare writes into another module's state, and Python/PowerShell resolver drift.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SOV_ROOT = RELEASE_ROOT / "modules" / "sovereign"
SHELL_SRC = RELEASE_ROOT / "shell" / "src"
for _p in (str(SOV_ROOT), str(RELEASE_ROOT), str(SHELL_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import adapter as adapter_mod  # noqa: E402
from sovereign_product import paths as P  # noqa: E402
from sovereign_product import state_migration as M  # noqa: E402

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


def _install(tmp_path: Path, *, layout: str | None = "external") -> Path:
    root = tmp_path / "install root"
    root.mkdir()
    (root / P.ROOT_MARKER).write_text(P.ROOT_MARKER_CONTENT, encoding="utf-8")
    if layout is not None:
        (root / P.STATE_LAYOUT_FILE).write_text(json.dumps({"schema": 1, "state": layout}),
                                                encoding="utf-8")
    return root


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _legacy_state(root: Path) -> None:
    _write(root / "runtime" / "sovereign.db", "DB")
    _write(root / "runtime" / "evidence" / "quick" / "a.json", "{}")
    _write(root / "runtime" / "llamacpp_supervisor" / "state.json", '{"pid": 1}')
    _write(root / "runtime" / "llama.cpp" / "current" / "llama-server.exe", "BINARY")
    _write(root / "published" / "index" / "index.jsonl", "{}\n")
    _write(root / "library" / "queues" / "deletion_queue.jsonl", "{}\n")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


# --- the shipped layout and adapters --------------------------------------------------------------

def test_sw25b_shipped_install_declares_external_state(clean_env):
    assert P.read_state_layout(SOV_ROOT) == "external"
    assert P.resolve_state_home(SOV_ROOT) == clean_env.resolve() / "SovereignWorkspace" / "sovereign"


def _compile(name: str) -> dict:
    raw = adapter_mod._load_json(str(RELEASE_ROOT / "shell" / "modules" / name))
    return adapter_mod.compile_adapter(raw)


def test_sw25b_sovereign_adapter_writes_only_to_its_state_root(clean_env):
    compiled = _compile("sovereign.json")
    state_root = compiled["state_root"]
    root = compiled["root"]
    assert state_root.endswith("/SovereignWorkspace/sovereign")
    for write in compiled["runtime_writes"]:
        assert write["path"].startswith(state_root + "/"), write
        assert not write["path"].startswith(root + "/"), f"install-tree write: {write}"
    env = compiled["launch"]["env_set"]
    assert env["SOVEREIGN_STATE_HOME"] == state_root
    assert env["SOVEREIGN_STATE_DIR"] == state_root + "/runtime"
    assert env["SOVEREIGN_EVIDENCE_DIR"] == state_root + "/runtime/evidence"


def test_sw25b_llamacpp_adapter_shares_sovereigns_state_home(clean_env):
    sovereign = _compile("sovereign.json")
    llama = _compile("llamacpp.json")
    assert llama["launch"]["env_set"]["SOVEREIGN_STATE_HOME"] == sovereign["state_root"]


def test_sw25b_workspace_state_root_grants_no_cross_module_write(clean_env):
    raw = adapter_mod._load_json(str(RELEASE_ROOT / "shell" / "modules" / "llamacpp.json"))
    raw["runtime_writes"] = ["${workspace_state_root}/sovereign/runtime"]
    with pytest.raises(adapter_mod.AdapterError):
        adapter_mod.compile_adapter(raw)


def test_sw25b_workspace_state_root_is_unavailable_outside_state_contexts(clean_env):
    raw = adapter_mod._load_json(str(RELEASE_ROOT / "shell" / "modules" / "llamacpp.json"))
    raw["launch"]["argv"] = raw["launch"]["argv"] + ["${workspace_state_root}"]
    with pytest.raises(adapter_mod.AdapterError):
        adapter_mod.compile_adapter(raw)


# --- migration ------------------------------------------------------------------------------------

def test_sw25b_migration_copies_legacy_state_and_leaves_it_for_rollback(clean_env, tmp_path):
    root = _install(tmp_path)
    _legacy_state(root)
    before = _snapshot(root)
    result = M.ensure_state_home(root)
    home = P.resolve_state_home(root)
    assert result["migrated"] is True
    assert (home / "runtime" / "sovereign.db").read_text(encoding="utf-8") == "DB"
    assert (home / "runtime" / "evidence" / "quick" / "a.json").is_file()
    assert (home / "runtime" / "llamacpp_supervisor" / "state.json").is_file()
    assert (home / "published" / "index" / "index.jsonl").is_file()
    assert (home / "library" / "queues" / "deletion_queue.jsonl").is_file()
    assert not (home / "runtime" / "llama.cpp").exists(), "a provisioned binary was copied as state"
    assert _snapshot(root) == before, "migration must copy, never move or edit, legacy state"
    receipt = json.loads((home / M.MIGRATION_RECEIPT).read_text(encoding="utf-8"))
    assert receipt["mode"] == "copy" and receipt["pieces"]["runtime"]["status"] == "copied"
    assert not (home / M.STAGING_DIRNAME).exists()
    assert not (home / M.LOCK_FILENAME).exists()


def test_sw25b_migration_runs_once(clean_env, tmp_path):
    root = _install(tmp_path)
    _legacy_state(root)
    M.ensure_state_home(root)
    home = P.resolve_state_home(root)
    (home / "runtime" / "sovereign.db").write_text("NEWER", encoding="utf-8")
    again = M.ensure_state_home(root)
    assert again["migrated"] is False
    assert (home / "runtime" / "sovereign.db").read_text(encoding="utf-8") == "NEWER"


def test_sw25b_migration_never_overwrites_existing_external_state(clean_env, tmp_path):
    root = _install(tmp_path)
    _legacy_state(root)
    home = P.resolve_state_home(root)
    _write(home / "runtime" / "sovereign.db", "ALREADY-HERE")
    result = M.ensure_state_home(root)
    assert result["receipt"]["pieces"]["runtime"]["status"] == "skipped_destination_not_empty"
    assert (home / "runtime" / "sovereign.db").read_text(encoding="utf-8") == "ALREADY-HERE"
    assert result["receipt"]["pieces"]["published"]["status"] == "copied"


def test_sw25b_empty_placeholder_destinations_do_not_block_migration(clean_env, tmp_path):
    # The shell creates declared runtime_writes directories (empty) before the module launches.
    root = _install(tmp_path)
    _legacy_state(root)
    home = P.resolve_state_home(root)
    for piece in ("runtime", "published", "library/queues", "logs"):
        (home / piece).mkdir(parents=True)
    result = M.ensure_state_home(root)
    assert result["receipt"]["pieces"]["runtime"]["status"] == "copied"
    assert (home / "runtime" / "sovereign.db").is_file()


def test_sw25b_interrupted_migration_is_redone_from_source(clean_env, tmp_path):
    root = _install(tmp_path)
    _legacy_state(root)
    home = P.resolve_state_home(root)
    _write(home / M.STAGING_DIRNAME / "runtime" / "half-copied.tmp", "partial")
    result = M.ensure_state_home(root)
    assert result["migrated"] is True
    assert not (home / M.STAGING_DIRNAME).exists()
    assert not (home / "runtime" / "half-copied.tmp").exists()
    assert (home / "runtime" / "sovereign.db").is_file()


def test_sw25b_held_lock_blocks_then_times_out(clean_env, tmp_path, monkeypatch):
    root = _install(tmp_path)
    _legacy_state(root)
    home = P.resolve_state_home(root)
    _write(home / M.LOCK_FILENAME, "4242")
    monkeypatch.setattr(M, "LOCK_WAIT_SECONDS", 0.3)
    with pytest.raises(TimeoutError):
        M.ensure_state_home(root)
    assert not (home / "runtime" / "sovereign.db").exists()


def test_sw25b_stale_lock_from_a_crashed_migrator_is_reclaimed(clean_env, tmp_path):
    root = _install(tmp_path)
    _legacy_state(root)
    home = P.resolve_state_home(root)
    lock = _write(home / M.LOCK_FILENAME, "4242")
    old = time.time() - (M.LOCK_STALE_SECONDS + 60)
    os.utime(lock, (old, old))
    assert M.ensure_state_home(root)["migrated"] is True


def test_sw25b_legacy_layout_migration_is_a_noop(clean_env, tmp_path):
    root = _install(tmp_path, layout=None)
    _legacy_state(root)
    result = M.ensure_state_home(root)
    assert result == {"state_home": str(root.resolve()), "external": False, "migrated": False,
                      "receipt": None}
    assert not (clean_env / "SovereignWorkspace").exists()


def test_sw25b_migration_cli(clean_env, tmp_path):
    root = _install(tmp_path)
    _legacy_state(root)
    env = {**os.environ, "PYTHONPATH": str(SOV_ROOT)}
    proc = subprocess.run([sys.executable, "-m", "sovereign_product.state_migration",
                           "--root", str(root)], cwd=str(SOV_ROOT), env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["migrated"] is True


# --- PowerShell twin of the resolver --------------------------------------------------------------

PS_RESOLVER = SOV_ROOT / "SovereignStatePaths.ps1"


def _ps(root: Path, env: dict[str, str]) -> dict[str, str]:
    script = (
        f". '{PS_RESOLVER}'; "
        f"$h = Get-SovereignStateHome -Root '{root}'; "
        f"$r = Get-SovereignRuntimeDir -Root '{root}'; "
        "Write-Output ($h + '|' + $r)"
    )
    run_env = {k: v for k, v in os.environ.items() if k not in STATE_ENV_KEYS}
    run_env.update(env)
    proc = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                           script], env=run_env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    home, runtime = proc.stdout.strip().splitlines()[-1].split("|")
    return {"home": home, "runtime": runtime}


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell resolver is Windows-only")
@pytest.mark.parametrize("layout", ["external", None])
@pytest.mark.parametrize("case", ["default", "workspace", "home", "state_dir"])
def test_sw25b_powershell_resolver_matches_python(clean_env, tmp_path, layout, case):
    root = _install(tmp_path, layout=layout)
    env = {"LOCALAPPDATA": str(clean_env)}
    if case == "workspace":
        env["SOVEREIGN_WORKSPACE_STATE"] = str(tmp_path / "ws elsewhere")
    elif case == "home":
        env["SOVEREIGN_STATE_HOME"] = str(clean_env / "SovereignWorkspace" / "sovereign-alt")
    elif case == "state_dir":
        env["SOVEREIGN_STATE_DIR"] = str(clean_env / "SovereignWorkspace" / "rt")
    ps = _ps(root, env)
    assert Path(ps["home"]) == P.resolve_state_home(root, env=env)
    assert Path(ps["runtime"]) == P.resolve_runtime_dir(root, env=env)


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell resolver is Windows-only")
def test_sw25b_powershell_reads_fall_back_to_legacy_only_before_migration(clean_env, tmp_path):
    root = _install(tmp_path)
    _write(root / "runtime" / "backend_selection.json", "{}")
    script = (f". '{PS_RESOLVER}'; Resolve-SovereignRuntimeFile -Root '{root}' "
              "-RelativePath 'backend_selection.json'")
    env = {**{k: v for k, v in os.environ.items() if k not in STATE_ENV_KEYS},
           "LOCALAPPDATA": str(clean_env)}
    run = lambda: subprocess.run(  # noqa: E731
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        env=env, capture_output=True, text=True, timeout=60).stdout.strip()
    assert Path(run()) == root / "runtime" / "backend_selection.json"
    M.ensure_state_home(root)
    assert Path(run()) == P.resolve_runtime_dir(root) / "backend_selection.json"


# --- no launcher/script still hardcodes install-tree state ----------------------------------------

def test_sw25b_scripts_do_not_hardcode_install_tree_state():
    scripts = [RELEASE_ROOT / "Start-Shell.ps1", *sorted(SOV_ROOT.glob("*.ps1"))]
    offenders = []
    for script in scripts:
        for lineno, line in enumerate(script.read_text(encoding="utf-8-sig").splitlines(), 1):
            text = line.strip()
            if text.startswith("#") or "runtime\\" not in text:
                continue
            # Provisioned binary location (an install asset, decision 3) is allowed.
            if "runtime\\llama.cpp\\current" in text:
                continue
            offenders.append(f"{script.name}:{lineno}: {text}")
    assert not offenders, "install-tree state paths in scripts (SW-25):\n" + "\n".join(offenders)


def test_sw25b_new_powershell_is_ascii():
    for script in (PS_RESOLVER,):
        data = script.read_bytes()
        assert all(b < 128 for b in data), f"{script.name} has non-ASCII bytes"
