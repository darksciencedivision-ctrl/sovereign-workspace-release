"""P2 SOW state roots: F-131 (durable ledgers honour the shell store root) and F-131f (coding
worktrees are never cut from the product's own install checkout).

F-131: terminal leases, node-event log and model-probe ledgers hard-coded an in-install
       `.sovereign_store`, so an upgrade replacing the install destroyed "never deletable" records
       and a read-only install failed the write. They now honour SOVEREIGN_STORE_ROOT /
       SOVEREIGN_WORKSPACE_STATE (the shell sets both), falling back only for a standalone dev run.
F-131f: resolve_base_repo inferred the nearest enclosing git repo of modules/sow -- the product's
        own checkout -- and cut worktrees into the shipped tree. It now refuses that checkout.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from node_runtime.supervisor import terminal_lease
from node_runtime.supervisor import provider_node_registration as pnr
from adapters.frontier import claude_model_probe
from node_runtime.supervisor import coding_worktrees as cw


class F131_StoreRootHonoursTheShell(unittest.TestCase):
    def test_terminal_lease_store_root_uses_declared_store(self) -> None:
        with mock.patch.dict(os.environ, {"SOVEREIGN_STORE_ROOT": r"X:\state\store"}, clear=False):
            root = terminal_lease._sow_store_root()
        self.assertEqual(Path(root), Path(r"X:\state\store"))

    def test_terminal_lease_store_root_falls_back_to_state_root(self) -> None:
        env = {"SOVEREIGN_WORKSPACE_STATE": r"X:\state"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("SOVEREIGN_STORE_ROOT", None)
            root = terminal_lease._sow_store_root()
        self.assertEqual(Path(root), Path(r"X:\state") / "store")

    def test_node_event_log_uses_declared_store(self) -> None:
        with mock.patch.dict(os.environ, {"SOVEREIGN_STORE_ROOT": r"X:\state\store"}, clear=False):
            os.environ.pop("SOW_NODE_EVENT_LOG", None)
            p = pnr.default_node_event_log_path(r"C:\install")
        self.assertEqual(Path(p), Path(r"X:\state\store") / "nodes" / "node_events.jsonl")

    def test_model_probe_ledger_uses_declared_store(self) -> None:
        with mock.patch.dict(os.environ, {"SOVEREIGN_STORE_ROOT": r"X:\state\store"}, clear=False):
            os.environ.pop("SOW_MODEL_PROBE_LEDGER", None)
            p = claude_model_probe.default_ledger_path()
        self.assertEqual(Path(p), Path(r"X:\state\store") / "model_probe" / "claude_code.json")


class F131f_NeverTheInstallCheckout(unittest.TestCase):
    def test_the_enclosing_install_checkout_is_refused(self) -> None:
        # modules/sow's enclosing repo IS the product checkout; it must not be used.
        self.assertIsNone(cw.resolve_base_repo(str(Path(__file__).resolve().parent)))

    def test_an_explicit_override_repo_is_honoured(self, ) -> None:
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="f131f-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        (tmp / ".git").mkdir()
        with mock.patch.dict(os.environ, {"SOW_CODING_BASE_REPO": str(tmp)}, clear=False):
            self.assertEqual(cw.resolve_base_repo(None), tmp)


if __name__ == "__main__":
    unittest.main(verbosity=2)
