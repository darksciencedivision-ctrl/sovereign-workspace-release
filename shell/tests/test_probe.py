"""N-15 regressions for Windows npm command-shim pre-flight detection."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
from unittest import mock

from shell.src.probe import preflight_toolchain


def test_preflight_detects_npm_cmd_on_path() -> None:
    with tempfile.TemporaryDirectory() as raw_temp:
        npm = Path(raw_temp) / "npm.cmd"
        npm.write_bytes(b"@echo off\r\necho 11.22.33\r\n")
        path = raw_temp + os.pathsep + os.environ.get("PATH", "")
        with mock.patch.dict(os.environ, {"PATH": path}):
            result = preflight_toolchain()["npm"]

    assert result == {"present": True, "version": "11.22.33"}


def test_preflight_refuses_hostile_resolved_npm_path() -> None:
    hostile = r"C:\unsafe&dir\npm.cmd"
    with mock.patch("shell.src.probe.shutil.which", return_value=hostile):
        result = preflight_toolchain()["npm"]

    assert result["present"] is False
    assert "refusing .cmd-shim argv[0]" in result["error"]
    assert repr(hostile) in result["error"]
