from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from distillery.common import ContractError
from ops import PromotionRouter
from ops.promotion import PROMOTION_AUTHORITY_UNAVAILABLE
from tests.test_ops_and_train import build_bundle


class PromotionBoundaryTests(unittest.TestCase):
    def _router(self, directory: str):
        root = Path(directory)
        prior, candidate = build_bundle(root, "prior"), build_bundle(root, "candidate")
        router_path = root / "router.json"
        prior_state = {"bundle": prior, "promoted_at": "before", "authority": "operator"}
        router_path.write_text(json.dumps(prior_state), encoding="utf-8")
        return PromotionRouter(router_path), prior, candidate, prior_state

    def test_synthetic_fixture_rejected_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            router, prior, candidate, _ = self._router(directory)
            candidate = dict(candidate)
            candidate["evidence_class"] = "SYNTHETIC_FIXTURE_ONLY"
            before = router.current()
            hg7 = {"finalized": True, "passed": True, "bundle_hash": candidate["bundle_hash"]}
            with self.assertRaises(ContractError) as caught:
                router.promote(
                    candidate,
                    hg7_evidence=hg7,
                    human_decision={"decision": "PROMOTE", "authority": "human-op"},
                    readiness_check=lambda _: True,
                )
            self.assertIn("synthetic-fixture", str(caught.exception).lower())
            self.assertEqual(router.current()["bundle"]["bundle_hash"], before["bundle"]["bundle_hash"])
            self.assertEqual(router.current()["bundle"]["bundle_hash"], prior["bundle_hash"])

    def test_missing_and_unknown_evidence_class_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            router, prior, candidate, _ = self._router(directory)
            hg7 = {"finalized": True, "passed": True, "bundle_hash": candidate["bundle_hash"]}
            with self.assertRaises(ContractError):
                router.promote(
                    dict(candidate),
                    hg7_evidence=hg7,
                    human_decision={"decision": "PROMOTE", "authority": "human-op"},
                    readiness_check=lambda _: True,
                )
            unknown = dict(candidate)
            unknown["evidence_class"] = "NOT_A_CLASS"
            with self.assertRaises(ContractError):
                router.promote(
                    unknown,
                    hg7_evidence=hg7,
                    human_decision={"decision": "PROMOTE", "authority": "human-op"},
                    readiness_check=lambda _: True,
                )
            self.assertEqual(router.current()["bundle"]["bundle_hash"], prior["bundle_hash"])

    def test_measured_candidate_still_contained_without_trusted_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            router, prior, candidate, _ = self._router(directory)
            measured = dict(candidate)
            measured["evidence_class"] = "MEASURED"
            hg7 = {"finalized": True, "passed": True, "bundle_hash": measured["bundle_hash"]}
            with self.assertRaisesRegex(ContractError, PROMOTION_AUTHORITY_UNAVAILABLE):
                router.promote(
                    measured,
                    hg7_evidence=hg7,
                    human_decision={"decision": "PROMOTE", "authority": "human-op"},
                    readiness_check=lambda _: True,
                )
            self.assertEqual(router.current()["bundle"]["bundle_hash"], prior["bundle_hash"])

    def test_rollback_still_restores_prior(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            router, prior, candidate, prior_state = self._router(directory)
            router._atomic_write({"bundle": candidate, "promoted_at": "later", "authority": "operator"})
            recovered = router.rollback(prior_state)
            self.assertEqual(recovered["status"], "ROLLED_BACK")
            self.assertEqual(router.current()["bundle"]["bundle_hash"], prior["bundle_hash"])
