"""
FIXUP-01 F-3 / S-17 — the Open control follows what the module can actually do.

N-23. `states.can_open()` tested READY-or-EXTERNAL and nothing else, and `app.js` did not even
consult it — it recomputed enablement from the state string. So `sow.json`, which declared
`open.kind: none`, reported `can_open: true` the moment SOW reached READY and the operator was
handed an enabled button wired to `open.url` == "". Every gate passed: the schema admits `none`,
so the adapter is valid, and nothing anywhere asked whether an enabled control maps to an action
the shell can perform.

The three properties pinned here are the ones that were missing:

  * a module declaring `open.kind: none` is NOT openable, even in READY  (the honest half)
  * `focus_window` is a first-class kind the schema and the compiler accept (the capable half)
  * an adapter cannot declare a capability it has not supplied — `browser` without a url, or a
    url on a kind that cannot use one, is refused at adapter-load time rather than
    surfacing as a dead button later.

The live half of F-3 — clicking Open on a running SOW and having the desktop window come
forward — is proven against the running product in bundles/FIXUP01/F/F-3/NOTES.md, because it
needs a real Electron window and a real Job Object.
"""
import json
import unittest

from shell.src.adapter import (
    _SCHEMA_PATH, AdapterError, _validate_against_schema, compile_adapter)
from shell.src.states import EXTERNAL, READY, STOPPED, ModuleRunner


def _adapter(open_block, module_id="fix"):
    return {
        "id": module_id,
        "display_name": "Fixture",
        "description": "open-capability fixture",
        "state_class": "runnable",
        "root": "C:/nonexistent-root",
        "runtime_writes": [],
        "launch": {
            "cwd": "C:/nonexistent-root",
            "argv": ["C:/nonexistent-root/app.exe"],
            "env_allowlist": ["SYSTEMROOT", "PATH", "TEMP", "TMP"],
            "env_set": {"PYTHONDONTWRITEBYTECODE": "1"},
        },
        "readiness": {"kind": "http", "url": "http://127.0.0.1:9/health",
                      "expect_status": 200, "timeout_s": 15, "poll_ms": 250},
        "identity": {"kind": "http_json", "url": "http://127.0.0.1:9/health",
                     "required_keys": ["status"]},
        "open": open_block,
        "stop": {"kind": "job_object", "grace_s": 2},
    }


def _runner(open_block):
    return ModuleRunner("fix", _adapter(open_block), supervisor=None)


class TestOpenEnablementFollowsCapability(unittest.TestCase):

    def test_open_kind_none_is_never_openable(self):
        """The exact defect: READY plus `open.kind: none` used to mean an enabled button."""
        r = _runner({"kind": "none"})
        for state in (READY, EXTERNAL):
            r.state = state
            self.assertFalse(
                r.can_open(),
                "a module declaring open.kind none reports can_open in {}; that is the enabled "
                "button wired to nothing (N-23)".format(state))
            self.assertEqual(r.to_dict()["can_open"], False)
        self.assertEqual(r.to_dict()["open_kind"], "none")

    def test_browser_module_is_openable_only_once_running(self):
        r = _runner({"kind": "browser", "url": "http://127.0.0.1:9/"})
        r.state = STOPPED
        self.assertFalse(r.can_open(), "Open offered for a module that is not running")
        r.state = READY
        self.assertTrue(r.can_open())
        r.state = EXTERNAL
        self.assertTrue(r.can_open())

    def test_focus_window_module_is_openable_once_running(self):
        r = _runner({"kind": "focus_window"})
        r.state = STOPPED
        self.assertFalse(r.can_open())
        r.state = READY
        self.assertTrue(r.can_open(),
                        "focus_window is the kind that makes SOW's Open performable; it must be "
                        "openable in READY")
        self.assertEqual(r.to_dict()["open_kind"], "focus_window")

    def test_a_browser_kind_carrying_no_url_is_openable_nowhere(self):
        """Belt and braces: even if such an adapter were reached, it offers no dead control."""
        r = _runner({"kind": "browser"})
        r.state = READY
        self.assertFalse(r.can_open())


class TestAdapterAdmitsExactlyTheThreeKinds(unittest.TestCase):
    """Validation runs the production path: schema first, then the compiler, exactly as
    load_all_adapters() does."""

    @classmethod
    def setUpClass(cls):
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            cls.schema = json.load(f)

    def _admit(self, open_block):
        adapter = _adapter(open_block)
        _validate_against_schema(adapter, self.schema)
        return compile_adapter(adapter)

    def test_focus_window_is_admitted(self):
        compiled = self._admit({"kind": "focus_window"})
        self.assertEqual(compiled["open"]["kind"], "focus_window")

    def test_browser_with_a_url_is_admitted(self):
        compiled = self._admit({"kind": "browser", "url": "http://127.0.0.1:9/"})
        self.assertEqual(compiled["open"]["url"], "http://127.0.0.1:9/")

    def test_unknown_kind_is_refused(self):
        with self.assertRaises(AdapterError):
            self._admit({"kind": "teleport"})

    def test_browser_without_url_is_refused(self):
        """A capability the adapter cannot supply is refused at load time, not at click time."""
        with self.assertRaises(AdapterError):
            self._admit({"kind": "browser"})

    def test_url_on_a_kind_that_cannot_use_one_is_refused(self):
        with self.assertRaises(AdapterError):
            self._admit({"kind": "none", "url": "http://127.0.0.1:9/"})
        with self.assertRaises(AdapterError):
            self._admit({"kind": "focus_window", "url": "http://127.0.0.1:9/"})


class TestShippedAdaptersDeclareHonestOpenBlocks(unittest.TestCase):
    """Every shipped adapter's Open must be performable, or declared absent."""

    def test_every_shipped_adapter_is_consistent(self):
        from shell.src.adapter import load_all_adapters
        for mid, adapter in load_all_adapters().items():
            if "error" in adapter:
                continue
            block = adapter.get("open") or {}
            kind = block.get("kind")
            self.assertIn(kind, ("browser", "focus_window", "none"),
                          "{}: unknown open.kind {!r}".format(mid, kind))
            if kind == "browser":
                self.assertTrue(block.get("url"),
                                "{}: declares open.kind browser with no url, which renders an "
                                "Open control the shell cannot perform".format(mid))
            else:
                self.assertFalse(block.get("url"),
                                 "{}: carries an open.url its kind cannot use".format(mid))


if __name__ == "__main__":
    unittest.main()
