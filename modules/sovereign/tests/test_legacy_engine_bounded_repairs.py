"""F-125 / F-126 - bounded repairs to the quarantined legacy engine, each pinned by a regression.

The legacy Phase-8/9 engine (cycle_runner_v3, broker_v21, synth_king, document_assembler, clu) and
the legacy quality/arbitration gate (quality_gate, claim_arbitrator) are NOT on the shipped product
route: the product never launches them and DeepExecutor refuses without SOVEREIGN_ALLOW_LEGACY_DEEP.
They still ship and can be run directly, so the clauses that admit a bounded correction are corrected
and tested here. Clauses left unrepaired are recorded as such in the remediation register; this file
does not pretend to cover them.

Every test runs against a temporary root and fakes every process and model boundary.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

import claim_arbitrator  # noqa: E402
import cycle_runner_v3 as runner  # noqa: E402
import quality_gate  # noqa: E402
from clu import clu_loop  # noqa: E402
from synthesis import synth_king  # noqa: E402


class _TempRoot(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="legacy-f125-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)


def _no_read_text(original):
    def guarded(self, *args, **kwargs):
        if self.name in {"cycle.log", "system.txt"}:
            raise AssertionError(f"appending to {self.name} must not read the whole file")
        return original(self, *args, **kwargs)
    return guarded


class LoggingIsAppendOnly(_TempRoot):
    """F-125(a) cycle log and F-125(g) synth_king system log: O(1) append, never read-rewrite."""

    def test_the_cycle_log_appends_without_reading_the_file(self) -> None:
        target = self.root / "logs" / "cycle.log"
        target.parent.mkdir(parents=True)
        target.write_text("first\n", encoding="utf-8")
        with mock.patch.object(Path, "read_text", _no_read_text(Path.read_text)):
            runner.append_text_atomic(target, "second\n")
            runner.append_text_atomic(target, "third\n")
        self.assertEqual("first\nsecond\nthird\n", target.read_text(encoding="utf-8"))

    def test_the_synth_king_system_log_appends_without_reading_the_file(self) -> None:
        target = self.root / "logs" / "system.txt"
        with mock.patch.object(Path, "read_text", _no_read_text(Path.read_text)):
            synth_king.append_log_line(target, {"stage": "a"})
            synth_king.append_log_line(target, {"stage": "b"})
        lines = target.read_text(encoding="utf-8").splitlines()
        self.assertEqual([{"stage": "a"}, {"stage": "b"}], [json.loads(line) for line in lines])

    def test_one_run_reads_the_system_log_once_while_it_is_unchanged(self) -> None:
        log = self.root / "system.txt"
        log.write_text(json.dumps({"session_id": "s1", "event": "x"}) + "\n", encoding="utf-8")
        runner._SYNTH_LOG_CACHE.clear()
        reads = []
        original = Path.read_text

        def counting(self, *a, **k):
            if self == log:
                reads.append(1)
            return original(self, *a, **k)

        with mock.patch.object(Path, "read_text", counting):
            for _ in range(3):
                runner.summarize_synth_stage_events(log, "s1")
            self.assertEqual(1, len(reads))
            with open(log, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"session_id": "s1", "event": "y", "pad": "z" * 10}) + "\n")
            runner.summarize_synth_stage_events(log, "s1")
        self.assertEqual(2, len(reads), "an append must invalidate the cached read")


class BulletsAreRecognised(unittest.TestCase):
    """F-125(i): the mojibake classes missed real U+2022 bullets and stripped '? ' / 'a-circumflex ' lines."""

    def test_both_splitters_recognise_a_real_bullet_and_keep_a_question_mark_line(self) -> None:
        for split in (runner.split_bullets, synth_king.split_bullets):
            with self.subTest(split=split.__module__):
                self.assertEqual(["alpha", "beta"], split("• alpha\n• beta"))
                items = split("- one\n? two")
                self.assertIn("one", items)
                self.assertIn("? two", items)


class CycleRunnerCli(_TempRoot):
    def _args(self, *extra: str):
        with mock.patch.object(sys, "argv", ["cycle_runner_v3.py", *extra]):
            return runner.parse_args()

    def test_the_stream_flag_is_meaningful(self) -> None:
        """F-125(e): --stream was store_true with default True, so it could not change anything."""
        self.assertTrue(self._args().stream)
        self.assertTrue(self._args("--stream").stream)
        self.assertFalse(self._args("--no-stream").stream)

    def _prepared_main(self):
        stack = [
            mock.patch.object(runner, "_resolve_root", lambda _r: self.root),
            mock.patch.object(runner, "run_preflight", lambda *_a, **_k: 0),
            mock.patch.object(runner, "_configure_runtime_integrity", lambda _r: None),
            mock.patch.object(sys, "argv", ["cycle_runner_v3.py", "--root", str(self.root),
                                            "--session-id", "s-lock"]),
        ]
        for patcher in stack:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _release_global_lock(self) -> None:
        handle = runner._CYCLE_LOCK_HANDLE
        runner._CYCLE_LOCK_HANDLE = None
        if handle is not None:
            handle.close()

    def test_a_stop_file_returns_non_zero_and_leaves_a_run_record(self) -> None:
        """F-125(c): STOP made every run return 0 with no record."""
        self._prepared_main()
        self.addCleanup(self._release_global_lock)
        (self.root / "STOP").write_text("", encoding="utf-8")
        self.assertNotEqual(0, runner.main())
        records = list((self.root / "runs").glob("stop-abort-*.json"))
        self.assertEqual(1, len(records))
        self.assertEqual("aborted", json.loads(records[0].read_text(encoding="utf-8"))["status"])

    def test_a_second_concurrent_cycle_is_refused_with_a_record(self) -> None:
        """F-125(b)/(h): concurrent cycles overwrote each other's shared IPC files."""
        self._prepared_main()
        held = runner.acquire_cycle_lock(self.root)
        self.assertIsNotNone(held)
        try:
            self.assertEqual(runner.CONCURRENT_CYCLE_EXIT, runner.main())
            self.assertEqual(1, len(list((self.root / "runs").glob("concurrent-refused-*.json"))))
        finally:
            held.close()
            self._release_global_lock()
        again = runner.acquire_cycle_lock(self.root)
        self.assertIsNotNone(again, "the lock is released with its handle - no stale lock")
        again.close()


class _FakePopen:
    instances: list = []

    def __init__(self, command, **kwargs):
        self.command = command
        self.kwargs = kwargs
        self.pid = 4242
        self.returncode = 0
        self.timeouts = list(getattr(_FakePopen, "timeouts", []))
        _FakePopen.instances.append(self)

    def communicate(self, timeout=None):
        if self.timeouts:
            self.timeouts.pop(0)
            raise subprocess.TimeoutExpired(self.command, timeout)
        return "", ""

    def kill(self):
        pass


class BrokerInvocation(_TempRoot):
    def setUp(self) -> None:
        super().setUp()
        _FakePopen.instances = []
        _FakePopen.timeouts = []

    def _run(self):
        return runner.run_broker(self.root, self.root / "broker.ps1", "topic", self.root / "topic.txt",
                                 "s1", 5, True, False)

    def test_the_broker_runs_the_debate_under_this_interpreter(self) -> None:
        """F-125(k): broker.ps1 defaulted to bare `python` from PATH."""
        with mock.patch.object(runner, "_powershell_exe", lambda: "powershell.exe"), \
                mock.patch.object(runner.subprocess, "Popen", _FakePopen):
            self._run()
        command = _FakePopen.instances[0].command
        self.assertEqual(sys.executable, command[command.index("-PythonExe") + 1])

    def test_a_timeout_kills_the_broker_tree_not_only_the_child(self) -> None:
        """F-125(d): subprocess.run(timeout=) killed only powershell.exe; the Python grandchildren
        kept writing the shared files."""
        _FakePopen.timeouts = ["first communicate times out"]
        killed = []
        with mock.patch.object(runner, "_powershell_exe", lambda: "powershell.exe"), \
                mock.patch.object(runner.subprocess, "Popen", _FakePopen), \
                mock.patch.object(runner, "_terminate_owned_tree", killed.append):
            with self.assertRaises(subprocess.TimeoutExpired):
                self._run()
        self.assertEqual([4242], killed)


class DocumentAssembler(_TempRoot):
    def setUp(self) -> None:
        super().setUp()
        import document_assembler  # noqa: PLC0415
        self.da = document_assembler

    def test_a_query_that_writes_nothing_cannot_return_the_previous_result(self) -> None:
        """F-125(f): result.txt was never cleared, so the previous query's memories came back."""
        praxis = self.root / "praxis"
        praxis.mkdir()
        (praxis / "praxis_query.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
        (praxis / "result.txt").write_text('[{"content": "STALE MEMORY"}]', encoding="utf-8")
        results, error = self.da._praxis_query("q", self.root, None)
        self.assertIsNone(results)
        self.assertIn("not found", error)

    def test_the_ollama_call_ignores_ambient_proxies(self) -> None:
        """F-125(f) / F-016: requests.post honoured HTTP(S)_PROXY for a loopback call."""
        try:
            import requests  # noqa: PLC0415
        except ImportError:
            self.skipTest("requests is not installed in this interpreter")
        seen = {}

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"response": "ok"}

        class _Session:
            trust_env = True

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def post(self, url, **kwargs):
                seen["trust_env"] = self.trust_env
                return _Resp()

        with mock.patch.object(requests, "Session", _Session), \
                mock.patch.object(requests, "post", side_effect=AssertionError("module-level post used")):
            self.da._ollama_generate("p", "s1", "http://127.0.0.1:11434", "m", None)
        self.assertIs(False, seen.get("trust_env"))


class CluFindsTheRunnerRecords(_TempRoot):
    def test_the_clu_reads_runs_session_json(self) -> None:
        """F-125(m): the CLU globbed runs/cycle-*.json; the runner writes runs/<session_id>.json."""
        runs = self.root / "runs"
        runs.mkdir()
        (runs / "s-42.json").write_text(json.dumps({"session_id": "s-42", "status": "completed"}),
                                        encoding="utf-8")
        (runs / "stop-abort-x.json").write_text(json.dumps({"status": "aborted", "session_id": ""}),
                                                encoding="utf-8")
        self.assertEqual("completed", clu_loop.latest_run_record(self.root).get("status"))
        self.assertEqual("s-42", clu_loop.latest_run_record(self.root, "s-42").get("session_id"))


class QualityGateFailsClosed(_TempRoot):
    def _evaluate(self):
        return quality_gate.evaluate(synthesis="CLAIM: x\nFINAL_SYNTHESIS: y", session_id="s1",
                                     confidence=0.99, root=str(self.root), dialog_text=None,
                                     convergence=0.99)

    def test_missing_dialog_fails_even_beside_an_executed_stale_artifact(self) -> None:
        """F-126(a)/(b): an existing arbitration artifact was reused and the gate passed on form."""
        arbitration = self.root / "arbitration"
        arbitration.mkdir()
        (arbitration / "s1.json").write_text(json.dumps({"executed": True, "analysis_status": "completed"}),
                                             encoding="utf-8")
        result = self._evaluate()
        self.assertFalse(result.get("passed"))
        self.assertTrue(any("not executed" in str(r) for r in result.get("reasons", [])), result.get("reasons"))

    def test_re_running_the_same_session_does_not_raise(self) -> None:
        """F-126(c): allow_overwrite=False raised FileExistsError on a second run of a session id."""
        self._evaluate()
        self.assertFalse(self._evaluate().get("passed"))


class OneEmbeddingClientPerArbitration(_TempRoot):
    def test_analyze_dialog_shares_one_lazily_built_client(self) -> None:
        """F-126(d): every comparison built a fresh client, so its per-text cache never hit."""
        seen = []

        def fake_cluster(records, embedding_client=None, manifest=None, root=None):
            seen.append(embedding_client)
            return [], []

        def fake_conflicts(clusters, links, embedding_client=None, manifest=None, root=None):
            seen.append(embedding_client)
            return [], [], []

        with mock.patch.object(claim_arbitrator, "load_semantic_matching_config", lambda **_k: {}), \
                mock.patch.object(claim_arbitrator, "cluster_claims", fake_cluster), \
                mock.patch.object(claim_arbitrator, "build_unresolved_conflicts", fake_conflicts), \
                mock.patch.object(claim_arbitrator, "build_manifest_embedding_client",
                                  side_effect=AssertionError("built before first use")):
            try:
                claim_arbitrator.analyze_dialog(dialog_text="", session_id="s1", root=self.root)
            except AssertionError:
                raise
            except Exception:  # noqa: BLE001 - later stages are not under test
                pass
        self.assertEqual(2, len(seen))
        self.assertIsNotNone(seen[0])
        self.assertIs(seen[0], seen[1])

    def test_the_shared_client_builds_once_and_delegates(self) -> None:
        built = []

        class _Client:
            def embed(self, text):
                return f"v:{text}"

        def build(root, manifest):
            built.append(root)
            return _Client()

        shared = claim_arbitrator._SharedEmbeddingClient(self.root, None)
        with mock.patch.object(claim_arbitrator, "build_manifest_embedding_client", build):
            self.assertEqual("v:a", shared.embed("a"))
            self.assertEqual("v:b", shared.embed("b"))
        self.assertEqual(1, len(built))


@unittest.skipUnless(os.name == "nt", "broker_once.ps1 is a Windows PowerShell helper")
class BrokerOnceHelper(_TempRoot):
    """F-125(l), executed for real against a stub broker."""

    STUB = textwrap.dedent(r"""
        param([string]$Root)
        $topic = Get-Content -Raw -LiteralPath (Join-Path $Root 'broker_v21\inbox\topic.txt')
        $synth = Join-Path $Root 'praxis\logs\synthesis.txt'
        Set-Content -LiteralPath $synth -Value ("TOPIC_SEEN_AT_START: " + $topic.Trim())
        $deadline = (Get-Date).AddSeconds(30)
        while (-not (Test-Path -LiteralPath (Join-Path $Root 'STOP')) -and (Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 100
        }
    """)

    def _run(self, topic: str) -> subprocess.CompletedProcess:
        stub = self.root / "stub_broker.ps1"
        stub.write_text(self.STUB, encoding="utf-8")
        helper = MODULE_ROOT / "broker_v21" / "broker_once.ps1"
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper),
             "-BrokerPath", str(stub), "-Root", str(self.root), "-Topic", topic, "-TimeoutSec", "30"],
            capture_output=True, text=True, timeout=120)

    def test_an_operator_stop_is_honoured_not_deleted(self) -> None:
        (self.root / "STOP").write_text("operator", encoding="utf-8")
        completed = self._run("new topic")
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("operator", (self.root / "STOP").read_text(encoding="utf-8"))
        self.assertFalse((self.root / "praxis" / "logs" / "synthesis.txt").exists(), "broker must not start")

    def test_the_run_sees_its_own_topic_ignores_stale_synthesis_and_leaves_no_stop(self) -> None:
        inbox = self.root / "broker_v21" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "topic.txt").write_text("OLD TOPIC", encoding="utf-8")
        synth = self.root / "praxis" / "logs" / "synthesis.txt"
        synth.parent.mkdir(parents=True)
        synth.write_text("STALE SYNTHESIS FROM A PREVIOUS RUN", encoding="utf-8")
        completed = self._run("NEW TOPIC")
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("TOPIC_SEEN_AT_START: NEW TOPIC", synth.read_text(encoding="utf-8-sig"))
        self.assertIn("STALE SYNTHESIS", (synth.parent / "synthesis.txt.prev").read_text(encoding="utf-8"))
        self.assertFalse((self.root / "STOP").exists(), "no STOP latch may be left behind")


class BrokerNativeCallIsNotTerminatedByStderr(unittest.TestCase):
    """F-125(k): the python call must not run under EAP=Stop, where PS 5.1 turns stderr into a
    terminating NativeCommandError. Structural pin: the call site sits inside a Continue block."""

    def test_the_python_call_runs_under_continue(self) -> None:
        text = (MODULE_ROOT / "broker_v21" / "broker.ps1").read_text(encoding="utf-8")
        call = text.index("& $PythonExe @argList 2>&1")
        before = text[:call]
        self.assertGreater(before.rfind("$ErrorActionPreference = 'Continue'"),
                           before.rfind('$ErrorActionPreference = "Stop"'))


if __name__ == "__main__":
    unittest.main()
