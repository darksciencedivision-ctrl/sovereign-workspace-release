"""The 18D `.close` node-registration REPORT — the producer behind the in-Electron receipt.

Why this file exists at all: at the 18D `.amendment` gate the validator found that the shipped OWED
block had no red-able test — every rule ran only at in-Electron emit time and every test asserted
against a synthetic fixture, so replacing a claim with a stronger one left all three suites green
(U296). These tests drive the REAL `build_report()` and then break each of its `ok` conjuncts in
turn, so every claim the receipt makes has a way to go red in the ordinary suite.

The report reads the operator's real switch (read-only) and runs the real governed session under a
fixture switch in a scratch directory. It executes no CLI and makes no live call, which is why it is
safe in a deterministic suite — and `test_no_child_is_ever_spawned` is the assertion, not the
comment.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

import tools.live.emit_provider_node_registration as E
from adapters.frontier.antigravity import ANTIGRAVITY_ADAPTER
from adapters.frontier.grok_build import GROK_ADAPTER


def _file_fingerprint(path: Path) -> str | None:
    """Content digest, or `None` for "the file is not there".

    `None` here means ABSENT, not "not measured": absence is the fresh-clone state of the
    operator's live switch and has to compare equal to itself, while any create, delete or edit —
    including one that preserves byte length — has to compare unequal."""
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def report() -> dict:
    return E.build_report()


class TestTheReportMeasuresTheAmendment:
    def test_it_is_ok_on_this_host_and_says_what_it_measured(self, report: dict) -> None:
        assert report["schema"] == "provider_node_registration@1.0"
        assert report["ok"] is True
        assert report["cli_executed"] is False and report["live_model_call"] is False
        # the deployment profile it ran under is PUBLISHED — a reader never infers it
        assert report["deployment_profile"] == (
            (os.environ.get("SOVEREIGN_DEPLOYMENT_PROFILE") or "cloud").strip() or "cloud")

    def test_both_providers_are_admitted_by_the_successor_schema(self, report: dict) -> None:
        assert report["vocabulary"]["admits"] == {GROK_ADAPTER: "node@1.1",
                                                  ANTIGRAVITY_ADAPTER: "node@1.1"}
        # the frozen file is still the provenance for a frozen member, and the fence still refuses
        assert report["vocabulary"]["frozen_member_example"]["claude_code"] == "node@1.0"
        assert report["vocabulary"]["unadmitted_example"][E.UNADMITTED_ID] is None

    @pytest.mark.parametrize("provider", [GROK_ADAPTER, ANTIGRAVITY_ADAPTER])
    def test_each_provider_registers_a_validated_record_and_closes_it(
            self, report: dict, provider: str) -> None:
        r = report["registrations"][provider]
        assert r["registered"] is True and r["error"] is None
        assert r["node_record"]["validated_against"] == "node@1.1"
        assert r["node_record"]["adapter_schema_version"] == "node@1.1"
        assert r["record_document"]["adapter"] == provider
        assert r["record_document"]["subscription_ref"] == f"{provider}_subscription"
        # the terminal was held for exactly the session, and the record was closed with it
        assert r["lease_in_use_during"] == 1 and r["lease_in_use_after"] == 0
        assert r["node_state_during"] == "SPAWNING" and r["node_state_after"] == "TERMINATED"
        assert r["teardown"]["lease_released"] is True
        assert r["teardown"]["node_exit_recorded"] is True
        assert r["log"]["chain_ok"] is True and r["log"]["kinds"] == ["spawn", "transition", "exit"]
        assert r["log"]["path_is_scratch"] is True

    def test_the_fence_still_refuses_what_no_version_admits(self, report: dict) -> None:
        ref = report["refusals"]
        assert ref["unadmitted_adapter"]["refused"] is True
        assert E.UNADMITTED_ID in ref["unadmitted_adapter"]["reason"]
        assert ref["unsupervised_session"]["refused"] is True
        assert ref["unsupervised_session"]["gate"] == "node_registration_unsupervised"
        assert ref["not_spawned_by_supervisor"]["refused"] is True
        assert ref["refusals_are_auditable"] is True and ref["refusal_rows"] >= 1

    def test_the_operators_own_switch_is_reported_consistently(self, report: dict) -> None:
        """The substitution, visible in the same document as the thing it substitutes for.

        CONDITIONAL on purpose (spec-audit MEDIUM-6): the first version asserted the switch was
        closed, so the moment the operator performed the very action directive §17 is waiting for,
        this deterministic test would have gone red on a legitimate operator action. What must
        hold either way is that the report is CONSISTENT with itself, and that it says WHICH file
        it read (gate-validator MEDIUM-3). The receipt's verdict is where an opened switch is
        refused, and it is tested there."""
        real = report["real_switch"]
        assert real["readable"] is True
        assert isinstance(real["path"], str) and real["path"]
        assert real["env_var"] == "SOVEREIGN_LIVE_OPERATION_CONFIG"
        assert real["fail_closed_for_op12"] is (real["op12_authorized"] == [])
        assert all(p in real["providers"] for p in real["op12_authorized"])
        assert set(report["fixture_scope"]["providers"]) >= set(real["providers"])

    def test_the_report_says_which_switch_file_it_read_and_flags_an_env_override(
            self, monkeypatch, tmp_path) -> None:
        """`load_live_authorization()` honours SOVEREIGN_LIVE_OPERATION_CONFIG ahead of the repo
        default and this report inherits its parent's environment, so "the operator's switch" was
        a claim about a file the document did not name — the validator produced a receipt saying
        `register_row: OP-12` for a fixture in %TEMP%."""
        cfg = tmp_path / "op12.json"
        cfg.write_text(json.dumps(E.FIXTURE_SCOPE), encoding="utf-8")
        monkeypatch.setenv("SOVEREIGN_LIVE_OPERATION_CONFIG", str(cfg))
        real = E._real_switch()
        assert real["env_override"] is True
        assert real["path"] == str(cfg)
        assert real["op12_authorized"] == [GROK_ADAPTER, ANTIGRAVITY_ADAPTER]

    def test_the_deployment_profile_is_the_hosts_and_an_air_gapped_host_refuses(
            self, monkeypatch, tmp_path) -> None:
        """The gate this report used to answer for itself. A self-manufactured `cloud` loader made
        invariant 20's air-gap half structurally unreachable inside the artifact that claimed "the
        whole gate chain ran" (spec-audit MAJOR-1, U91's shape)."""
        from control_plane.profiles.loader import ProfileViolation

        monkeypatch.setenv("SOVEREIGN_DEPLOYMENT_PROFILE", "offline_airgapped")
        with pytest.raises(ProfileViolation) as exc:
            E._register_one(GROK_ADAPTER, tmp_path)
        assert "offline" in str(exc.value).lower()

    @pytest.mark.parametrize("provider", [GROK_ADAPTER, ANTIGRAVITY_ADAPTER])
    def test_the_ix3_allowance_is_one_however_the_fixture_is_written(
            self, report: dict, provider: str) -> None:
        """The fixture says `terminals_per_subscription: 2` and the code-pinned per-provider cap
        says 1. The report ASSERTS the 1 rather than displaying it (spec-audit MINOR-9)."""
        assert report["fixture_scope"]["terminals_per_subscription"] == 2
        assert report["registrations"][provider]["allowance"] == 1

    def test_the_node_log_is_held_exclusively_and_handed_back(self, report: dict) -> None:
        assert report["refusals"]["concurrent_log_holder"]["refused"] is True
        assert report["refusals"]["concurrent_log_holder"]["gate"] == "node_log_locked"
        assert report["refusals"]["lock_released"] is True
        for reg in report["registrations"].values():
            assert reg["log"]["lock_released"] is True

    def test_the_injected_inputs_are_all_named(self, report: dict) -> None:
        """The claim that broke at review: "the substitution is exactly one thing" while four
        inputs were injected and two gates were answered by the report itself."""
        assert len(report["injected"]) == 4
        assert any("deployment profile" in s for s in report["not_injected"])
        assert any("terms determination" in s for s in report["not_injected"])
        for phrase in ("FOUR inputs are injected", "NOT injected", "NO CLI IS EXECUTED"):
            assert phrase in report["substitution"]

    def test_the_operators_durable_store_is_untouched_measured_by_CONTENT(
            self, report: dict) -> None:
        """`exists` + `size` misses any edit that preserves byte length, while the claim is "never
        opened" (spec-audit MINOR-8). A file that exists must carry a real digest, or "unchanged"
        is comparing two absences of a measurement."""
        store = report["durable_store"]
        assert store["unchanged"] is True
        assert store["before"] == store["after"]
        for state in (store["before"], store["after"]):
            for entry in state.values():
                if entry.get("exists") is True:
                    assert isinstance(entry["sha256"], str) and len(entry["sha256"]) == 64
        # Registering into a scratch log did not touch the operator's own. This used to assert
        # `store["after"]["node_event_log"]["exists"] is False`, and that went RED at 18E without a
        # line of product code changing: the OPERATOR ran their own live recon probe on 2026-08-02
        # and it wrote the first durable node@1.1 records for both providers — the very outcome
        # 18D built. "Absent" was never the claim; "untouched" is, and it is measured above by
        # digest, which holds whether the file exists or not. The positive half — that the records
        # this report makes go to a SCRATCH log — is asserted from the other side.
        for reg in report["registrations"].values():
            assert reg["log"]["path_is_scratch"] is True

    def test_no_credential_name_carries_a_value_anywhere_in_the_document(
            self, report: dict) -> None:
        blob = json.dumps(report)
        for name in ("XAI_API_KEY", "GROK_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                     "ANTIGRAVITY_API_KEY"):
            assert f'"{name}":' not in blob


class TestEveryOkConjunctCanGoRed:
    """One test per `ok` conjunct. A verdict whose failure branch nothing exercises is a verdict
    that has never been observed to fail (U296)."""

    def test_a_vocabulary_that_no_longer_admits_a_provider_fails(self, monkeypatch) -> None:
        monkeypatch.setattr(E, "adapter_version_map",
                            lambda: {"claude_code": "node@1.0", ANTIGRAVITY_ADAPTER: "node@1.1"})
        assert E.build_report()["ok"] is False

    def test_an_unadmitted_id_that_became_admitted_fails(self, monkeypatch) -> None:
        real = E.adapter_version_map()
        monkeypatch.setattr(E, "adapter_version_map",
                            lambda: {**real, E.UNADMITTED_ID: "node@1.1"})
        assert E.build_report()["ok"] is False

    def test_a_registration_that_did_not_happen_fails(self, monkeypatch) -> None:
        """One conjunct at a time: the fake result is COMPLETE except for `registered`, so a green
        report can only mean the `registered` rule stopped deciding. The first version returned a
        stub missing three fields, and every other conjunct failed it instead — the mutation that
        deleted this rule stayed GREEN and nothing noticed."""
        real = E._register_one
        monkeypatch.setattr(E, "_register_one",
                            lambda p, s: {**real(p, s), "registered": False})
        assert E.build_report()["ok"] is False

    def test_a_registration_that_errored_fails(self, monkeypatch) -> None:
        real = E._register_one
        monkeypatch.setattr(E, "_register_one", lambda p, s: {**real(p, s), "error": "boom"})
        assert E.build_report()["ok"] is False

    def test_a_widened_ix3_allowance_fails(self, monkeypatch) -> None:
        """I-X3 is asserted, not displayed: an OP-12 subscription that started reporting 2
        terminals must turn the report red (spec-audit MINOR-9)."""
        real = E._register_one

        def widened(provider, scratch):
            return {**real(provider, scratch), "allowance": 2}

        monkeypatch.setattr(E, "_register_one", widened)
        assert E.build_report()["ok"] is False

    @pytest.mark.parametrize("key", ["unadmitted_adapter", "unsupervised_session",
                                     "not_spawned_by_supervisor", "concurrent_log_holder"])
    def test_a_fence_that_stopped_refusing_fails(self, monkeypatch, key: str) -> None:
        real = E._refusals

        def weakened(scratch: Path) -> dict:
            out = real(scratch)
            out[key] = {"refused": False}
            return out

        monkeypatch.setattr(E, "_refusals", weakened)
        assert E.build_report()["ok"] is False

    def test_an_unauditable_refusal_fails(self, monkeypatch) -> None:
        real = E._refusals

        def weakened(scratch: Path) -> dict:
            out = real(scratch)
            out["refusals_are_auditable"] = False
            return out

        monkeypatch.setattr(E, "_refusals", weakened)
        assert E.build_report()["ok"] is False

    def test_a_touched_durable_store_fails(self, monkeypatch) -> None:
        seen: list[int] = []

        def moving() -> dict:
            seen.append(1)
            return {"node_event_log": {"size": len(seen)}}

        monkeypatch.setattr(E, "_durable_store", moving)
        report = E.build_report()
        assert report["durable_store"]["unchanged"] is False and report["ok"] is False


class TestItSpendsNothing:
    def test_no_child_is_ever_spawned(self, monkeypatch) -> None:
        """The report opens governed sessions for two live frontier providers. It must not run
        one. `subprocess.Popen` is the choke point every spawn path in this repo goes through."""
        import subprocess

        def refuse(*a, **kw):      # pragma: no cover — the assertion is that it is never reached
            raise AssertionError(f"the registration report spawned a child: {a!r}")

        monkeypatch.setattr(subprocess, "Popen", refuse)
        assert E.build_report()["ok"] is True

    def test_the_fixture_switch_never_reaches_the_operators_config(self, tmp_path: Path) -> None:
        """The one substitution is a file in a scratch directory read by the REAL loader. It must
        never be written where the operator's switch lives (which is gitignored and never
        committed — this build does not write it, at all)."""
        import tempfile

        switch = Path(E.REPO_ROOT) / "config" / "live_operation.json"
        before = _file_fingerprint(switch)

        def snapshot() -> str | None:
            return _file_fingerprint(switch)

        with tempfile.TemporaryDirectory() as tmp:
            out = E._register_one(GROK_ADAPTER, Path(tmp))
            assert out["registered"] is True
            assert list(Path(tmp).glob("*live_operation.json"))   # the fixture, in the scratch dir
        # The claim is "this build never writes the operator's switch", so measure the operator's
        # switch across the call. It used to be spelled `GROK_ADAPTER not in switch.read_text()`,
        # which is a claim about the file's CONTENT rather than about who wrote it — and it went RED
        # at 18E because the OPERATOR themselves widened the switch to OP-12 scope on 2026-08-01,
        # exactly as directive §17 asks them to. A test that fails when the operator exercises their
        # own authority was testing the wrong thing (the audit-R4 non-hermetic class).
        assert snapshot() == before

    @pytest.mark.parametrize("change", ["create", "modify", "delete"])
    def test_the_untouched_measurement_can_actually_go_red(self, tmp_path: Path,
                                                           change: str) -> None:
        """The discriminating power of the comparison above, proved where it is safe to prove it.

        The test above cannot be mutation-tested the honest way — the mutation would be "write to
        the operator's real switch", and this build does not write that file under any
        circumstances. So the comparator is exercised on a scratch file instead: it must catch a
        create, a modification that preserves byte length, and a delete. A test whose failure
        branch has never been observed is a test that has never been observed to work."""
        target = tmp_path / "live_operation.json"
        if change != "create":
            target.write_text('{"live_operation_authorized": true }', encoding="utf-8")
        before = _file_fingerprint(target)
        if change == "create":
            target.write_text("{}", encoding="utf-8")
        elif change == "modify":
            target.write_text('{"live_operation_authorized": false}', encoding="utf-8")
        else:
            target.unlink()
        assert _file_fingerprint(target) != before
