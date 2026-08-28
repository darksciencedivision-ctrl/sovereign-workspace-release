"""v1.2.1 hardening regression tests: canonical resolver + endpoint policy (P0-04, P0-05)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "app.py"
CLI_PATH = ROOT / "scripts" / "effective_config.py"

_SEATS = [
    {"name": "Neo", "model": "mock-a:latest", "color": "#4fd1ff", "persona": "B", "thesis": "T"},
    {"name": "Clue", "model": "mock-b:latest", "color": "#7dffa0", "persona": "C", "thesis": "T"},
]


def _doc(ollama_url="http://127.0.0.1:9", **extra):
    doc = {
        "ollama_url": ollama_url,
        "port": 18931,
        "seats": _SEATS,
        "insight_panel": False,
    }
    doc.update(extra)
    return doc


def _exec_module(config_path: Path, module_name: str, extra_env=None):
    old = {k: os.environ.get(k) for k in ("CONFIG_PATH", "OLLAMA_URL")}
    os.environ["CONFIG_PATH"] = str(config_path)
    if extra_env:
        os.environ.update(extra_env)
    spec = importlib.util.spec_from_file_location(module_name, APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        assert spec.loader is not None
        spec.loader.exec_module(module)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


def _fatal_stderr(tmp_path, document, extra_env=None):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(document) + "\n", encoding="utf-8")
    probe = (
        "import os, sys, runpy\n"
        f"os.environ['CONFIG_PATH'] = r'{cfg}'\n"
        + (
            "".join(f"os.environ[{k!r}] = {v!r}\n" for k, v in extra_env.items())
            if extra_env
            else ""
        )
        + "sys.argv=['app.py']\n"
        "runpy.run_path(r'" + str(APP_PATH) + "', run_name='policy_probe')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 2, result.stderr[-400:]
    return result.stderr


_CTR = {"n": 0}


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434",
        "http://localhost:11434",
        "http://[::1]:11434",
    ],
)
def test_loopback_endpoints_accepted(url, tmp_path):
    _CTR["n"] += 1
    name = f"debate_table_v1_2_1_loop_{_CTR['n']}"
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(_doc(ollama_url=url)) + "\n", encoding="utf-8")
    old = os.environ.get("OLLAMA_URL")
    os.environ.pop("OLLAMA_URL", None)
    try:
        module = _exec_module(cfg, name)
        assert module.OLLAMA_ENDPOINT_CLASS == "loopback"
    finally:
        sys.modules.pop(name, None)
        if old is None:
            os.environ.pop("OLLAMA_URL", None)
        else:
            os.environ["OLLAMA_URL"] = old


def test_remote_endpoint_rejected_without_opt_in(tmp_path):
    stderr = _fatal_stderr(
        tmp_path, _doc(ollama_url="http://192.168.1.50:11434")
    )
    assert "allow_remote_ollama" in stderr
    assert "non-loopback" in stderr


def test_remote_endpoint_accepted_with_explicit_opt_in(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps(
            _doc(ollama_url="http://192.168.1.50:11434", allow_remote_ollama=True)
        )
        + "\n",
        encoding="utf-8",
    )
    old = os.environ.get("OLLAMA_URL")
    os.environ.pop("OLLAMA_URL", None)
    name = "debate_table_v1_2_1_remote_ok"
    try:
        module = _exec_module(cfg, name)
        assert module.OLLAMA_ENDPOINT_CLASS == "remote"
        assert module.OLLAMA.startswith("http://192.168.1.50:11434")
    finally:
        sys.modules.pop(name, None)
        if old is None:
            os.environ.pop("OLLAMA_URL", None)
        else:
            os.environ["OLLAMA_URL"] = old


def test_env_override_cannot_bypass_loopback_policy(tmp_path):
    stderr = _fatal_stderr(
        tmp_path,
        _doc(),
        extra_env={"OLLAMA_URL": "http://10.9.8.7:11434"},
    )
    assert "OLLAMA_URL environment" in stderr
    assert "allow_remote_ollama" in stderr


def test_bootstrap_runtime_endpoint_equivalence(tmp_path):
    doc = _doc(ollama_url="http://127.0.0.1:18999", port=18932)
    bom_cfg = tmp_path / "config.json"
    bom_cfg.write_text(json.dumps(doc) + "\n", encoding="utf-8-sig")

    result = subprocess.run(
        [sys.executable, str(CLI_PATH), str(bom_cfg)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr[-300:]
    summary = json.loads(result.stdout.strip().splitlines()[-1])
    assert summary["endpoint_class"] == "loopback"
    assert summary["ollama_url"] == "http://127.0.0.1:18999"
    assert summary["port"] == 18932

    old = os.environ.get("OLLAMA_URL")
    os.environ.pop("OLLAMA_URL", None)
    name = "debate_table_v1_2_1_equiv"
    try:
        module = _exec_module(bom_cfg, name)
        assert module.OLLAMA == summary["ollama_url"]
        assert module.CONFIG["port"] == summary["port"]
        assert module.CONFIG_PATH.name == "config.json"
    finally:
        sys.modules.pop(name, None)
        if old is None:
            os.environ.pop("OLLAMA_URL", None)
        else:
            os.environ["OLLAMA_URL"] = old


def test_bootstrap_scripts_use_canonical_resolver():
    sh_src = (ROOT / "scripts" / "bootstrap.sh").read_text(encoding="utf-8")
    ps1_src = (ROOT / "scripts" / "bootstrap.ps1").read_text(encoding="utf-8")
    assert "effective_config.py" in sh_src
    assert "effective_config.py" in ps1_src
    assert "|| echo 8700" not in sh_src