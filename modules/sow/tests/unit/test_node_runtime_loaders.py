"""Phase 3: config loaders are fail-closed on every defect class."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from node_runtime import LoaderError, load_node_config

VALID_PROFILE = {
    "profile_id": "p-test",
    "node_class": "worker_reasoning",
    "default_stance": "deny",
    "rules": [
        {"action_class": "fs_write", "scope": "workspace", "effect": "allow"},
        {"action_class": "network_egress", "effect": "deny"},
    ],
    "schema": "permission@1.0",
}


def make_config(tmp_path: Path, *, profile: dict | None = None, directive: str = "Do the task.", role: str = "Worker.") -> Path:
    d = tmp_path / "cfg"
    d.mkdir(exist_ok=True)
    (d / "DIRECTIVE.md").write_text(directive, encoding="utf-8")
    (d / "ROLE.md").write_text(role, encoding="utf-8")
    (d / "permission_profile.json").write_text(json.dumps(profile if profile is not None else VALID_PROFILE), encoding="utf-8")
    return d


def test_valid_config_loads_with_hashes(tmp_path: Path) -> None:
    cfg = load_node_config(make_config(tmp_path), expected_node_class="worker_reasoning")
    assert cfg.permission_profile["profile_id"] == "p-test"
    assert set(cfg.hashes) == {"DIRECTIVE.md", "ROLE.md", "permission_profile.json"}
    assert all(len(h) == 64 for h in cfg.hashes.values())


def test_missing_dir_fails(tmp_path: Path) -> None:
    with pytest.raises(LoaderError, match="does not exist"):
        load_node_config(tmp_path / "nope", expected_node_class="worker_reasoning")


@pytest.mark.parametrize("victim", ["DIRECTIVE.md", "ROLE.md", "permission_profile.json"])
def test_missing_file_fails(tmp_path: Path, victim: str) -> None:
    d = make_config(tmp_path)
    (d / victim).unlink()
    with pytest.raises(LoaderError, match="missing required"):
        load_node_config(d, expected_node_class="worker_reasoning")


def test_empty_directive_fails(tmp_path: Path) -> None:
    d = make_config(tmp_path, directive="   \n")
    with pytest.raises(LoaderError, match="empty"):
        load_node_config(d, expected_node_class="worker_reasoning")


def test_unparseable_profile_fails(tmp_path: Path) -> None:
    d = make_config(tmp_path)
    (d / "permission_profile.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(LoaderError, match="not valid JSON"):
        load_node_config(d, expected_node_class="worker_reasoning")


def test_schema_violation_fails(tmp_path: Path) -> None:
    bad = dict(VALID_PROFILE)
    del bad["rules"]
    d = make_config(tmp_path, profile=bad)
    with pytest.raises(LoaderError, match="permission@1.0"):
        load_node_config(d, expected_node_class="worker_reasoning")


def test_non_deny_default_stance_fails_via_schema(tmp_path: Path) -> None:
    bad = dict(VALID_PROFILE)
    bad["default_stance"] = "allow"
    d = make_config(tmp_path, profile=bad)
    with pytest.raises(LoaderError, match="permission@1.0"):
        load_node_config(d, expected_node_class="worker_reasoning")


def test_foreign_node_class_profile_refused(tmp_path: Path) -> None:
    d = make_config(tmp_path)
    with pytest.raises(LoaderError, match="foreign profile"):
        load_node_config(d, expected_node_class="conductor")


def test_non_utf8_config_raises_loader_error_not_codec_error(tmp_path: Path) -> None:
    """Nodes catch LoaderError as the fail-closed signal; a raw UnicodeDecodeError must
    not leak (spec-audit MINOR)."""
    d = make_config(tmp_path)
    (d / "DIRECTIVE.md").write_bytes(b"\xff\xfe invalid utf-8 \x80\x81")
    with pytest.raises(LoaderError, match="not valid UTF-8"):
        load_node_config(d, expected_node_class="worker_reasoning")
