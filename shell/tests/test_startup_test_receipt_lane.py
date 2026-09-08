"""SW-REMED-001 F-16 — SOW's startup test watches the lane its self-check actually writes to.

THE DEFECT, measured live on the operator's host 2026-09-05 through the shell's own
`/api/startup-test` route:

    readiness : FAILED(PROCESS_START_FAILED: exited before ready)
                "Receipt is stale (predates launch)", after 90.087 s
    writer    : modules/sow/.runtime/receipts/PHASE16A_SELFCHECK.json, ok:true,
                mtime 2026-09-05T08:53:53Z  <- FRESH, and written by that very run
    probe     : modules/sow/docs/evidence/receipts/PHASE16A_SELFCHECK.json,
                mtime 2026-08-28T01:47:24Z  <- the git-tracked August fossil

The self-check passed. The probe was right to reject the fossil. The DESCRIPTOR pointed the probe
at a lane the writer had not used since the receipts moved to `.runtime/` (LOCAL-01 F-6 / OD-34),
so the startup test could never reach READY no matter how well the product worked.

The repair is the one SW-REMED-001 §7 specifies: name `${state_root}/receipts` in both halves, so
the writer's override and the probe's path are the same directory by construction. These tests pin
that they cannot drift apart again, and that the guards which made the failure honest are intact.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from shell.src.adapter import load_all_adapters
from shell.src.probe import receipt_file_probe


def _sow() -> dict:
    sow = load_all_adapters()["sow"]
    assert "error" not in sow, sow.get("reason")
    return sow


def _norm(p: str) -> str:
    return str(p).replace("\\", "/").rstrip("/")


# --- the repair itself --------------------------------------------------------------------------

def test_the_writer_override_and_the_probe_path_are_the_same_directory() -> None:
    """The whole defect in one assertion: these two drifted apart and nothing noticed."""
    st = _sow()["startup_test"]
    writer_dir = _norm(st["env_set"]["SHELL_SELFCHECK_RECEIPT_DIR"])
    probe_dir = _norm(st["readiness"]["path"]).rsplit("/", 1)[0]
    assert writer_dir == probe_dir


def test_the_startup_test_lane_is_the_external_state_root_not_the_install() -> None:
    sow = _sow()
    st = sow["startup_test"]
    state_root = _norm(sow["state_root"])
    assert _norm(st["readiness"]["path"]).startswith(state_root + "/")
    assert _norm(st["env_set"]["SHELL_SELFCHECK_RECEIPT_DIR"]).startswith(state_root + "/")
    # and NOT the install tree, which is what made a self-check dirty the release candidate
    assert not _norm(st["readiness"]["path"]).startswith(_norm(sow["root"]) + "/")


def test_the_git_tracked_fossil_lane_is_no_longer_watched() -> None:
    """`docs/evidence/receipts` is history. Readiness must never be pointed back at it."""
    st = _sow()["startup_test"]
    assert "docs/evidence" not in _norm(st["readiness"]["path"])
    assert "docs/evidence" not in _norm(st["env_set"]["SHELL_SELFCHECK_RECEIPT_DIR"])


def test_the_selfcheck_flag_is_still_set() -> None:
    """The lane changed; the thing that makes it a SELF-CHECK did not."""
    assert _sow()["startup_test"]["env_set"]["SHELL_SELFCHECK"] == "1"


def test_the_normal_launch_readiness_is_untouched() -> None:
    """Only the startup-test lane moved. The module's own readiness receipt is not this finding."""
    sow = _sow()
    assert _norm(sow["readiness"]["path"]).endswith("/.runtime/receipts/SHELL-LIVE-READY.json")


def test_the_timeout_was_not_extended_as_a_substitute() -> None:
    """SW-REMED-001 §7 item 3, explicitly: the budget is not the repair."""
    st = _sow()["startup_test"]
    assert st["readiness"]["timeout_s"] == 90
    assert st["readiness"]["require"] == {"ok": True}


# --- the freshness guard, which is what made the failure honest ---------------------------------

def test_a_stale_receipt_in_the_NEW_lane_still_cannot_satisfy_the_probe() -> None:
    """Moving the lane must not buy a pass for a receipt an earlier run left behind."""
    with tempfile.TemporaryDirectory() as tmp:
        receipt = Path(tmp) / "PHASE16A_SELFCHECK.json"
        receipt.write_text(json.dumps({"ok": True}), encoding="utf-8")
        old = time.time() - 3600
        os.utime(receipt, (old, old))

        ok, _, reason = receipt_file_probe(str(receipt), timeout_s=5, poll_ms=250,
                                           require={"ok": True}, newer_than=time.time())
        assert ok is False
        assert "stale" in reason.lower()


def test_a_fresh_receipt_in_the_new_lane_satisfies_the_probe() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        receipt = Path(tmp) / "PHASE16A_SELFCHECK.json"
        launched = time.time()
        time.sleep(0.05)
        receipt.write_text(json.dumps({"ok": True}), encoding="utf-8")

        ok, _, reason = receipt_file_probe(str(receipt), timeout_s=5, poll_ms=250,
                                           require={"ok": True}, newer_than=launched)
        assert ok is True, reason


def test_a_failed_selfcheck_never_reaches_ready() -> None:
    """`ok:false` is an honest bounded failure, not a pass."""
    with tempfile.TemporaryDirectory() as tmp:
        receipt = Path(tmp) / "PHASE16A_SELFCHECK.json"
        launched = time.time()
        time.sleep(0.05)
        receipt.write_text(json.dumps({"ok": False}), encoding="utf-8")

        ok, _, reason = receipt_file_probe(str(receipt), timeout_s=3, poll_ms=250,
                                           require={"ok": True}, newer_than=launched)
        assert ok is False
        assert "satisfy" in reason.lower()


def test_a_missing_writer_produces_a_bounded_timeout_not_ready() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ok, elapsed, reason = receipt_file_probe(
            str(Path(tmp) / "never-written.json"), timeout_s=2, poll_ms=250,
            require={"ok": True}, newer_than=time.time())
        assert ok is False
        assert elapsed < 10
        assert "timeout" in reason.lower()


# --- the bounded loader change (SW-REMED-001 §7 item 2) -----------------------------------------

def test_state_root_resolves_in_startup_test_env_set_and_readiness() -> None:
    """Before this repair the loader resolved neither, so the descriptor could not name the lane."""
    st = _sow()["startup_test"]
    assert "${state_root}" not in st["readiness"]["path"]
    assert "${state_root}" not in st["env_set"]["SHELL_SELFCHECK_RECEIPT_DIR"]
    assert os.path.isabs(st["readiness"]["path"].replace("/", os.sep))


def test_a_startup_test_path_escaping_both_roots_is_refused() -> None:
    """H-5 is EXTENDED to a second named root, never widened to arbitrary paths."""
    from shell.src.adapter import AdapterError, compile_adapter

    sow_raw = json.loads(
        (Path(__file__).resolve().parents[1] / "modules" / "sow.json").read_text(encoding="utf-8"))
    sow_raw["startup_test"]["readiness"]["path"] = "${root}/../../escape/receipt.json"

    with pytest.raises(AdapterError, match="escapes both"):
        compile_adapter(sow_raw)
