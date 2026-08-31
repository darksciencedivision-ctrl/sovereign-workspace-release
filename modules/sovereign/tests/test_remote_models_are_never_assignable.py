"""EPC-02 dyno finding — SOVEREIGN accepted a cloud-routed model into a role slot.

Found by driving the live system, not by reading it. `POST /v1/models/active` with
`glm-5.2:cloud` was ACCEPTED and the CRITIC slot held it. That model executes on Ollama Cloud:
selecting it sends inference off this host, which is provider spend, which is a mandatory STOP.

Two defects sat behind it, and the second is the one that would have bitten later:

  1. `update_model_assignments` never consulted the ceiling. The model was already marked
     `within_ceiling: False` in the very state the method reads, and it was assigned anyway.
     A verdict that is computed and then ignored is worse than no verdict — it makes the
     surrounding code look guarded.

  2. SOVEREIGN's ceiling refused the two cloud entries only INCIDENTALLY, because they report
     756B and 1.65T parameters. It had no concept of "holds no local weights". The operator
     has asked for his whole library to be reachable, and EPC-02 B-2 did exactly that in SOW —
     so the next widening of this ceiling would have made both cloud pointers selectable.

So the remote-execution refusal is deliberately NOT part of the size ceiling. A model over the
size ceiling is slow, and that is the operator's call to make. A model that runs elsewhere is a
bill, and stays refused however wide the ceiling is set. These tests hold that separation,
because it is the property that makes widening safe.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product import introspection as intro  # noqa: E402


def tags(*rows: dict) -> dict:
    return {"models": list(rows)}


def row(name: str, params: str, size: int) -> dict:
    return {"name": name, "size": size, "details": {"parameter_size": params}}


CLOUD = row("glm-5.2:cloud", "756B", 290)
BIG_LOCAL = row("qwen3:32b", "32.8B", 20_200_000_000)
SMALL_LOCAL = row("qwen3:8b", "8.2B", 5_200_000_000)


class RemoteModelsAreRefusedIndependentlyOfSize(unittest.TestCase):

    def test_a_cloud_pointer_is_marked_as_running_remotely(self) -> None:
        verdict = intro._ceiling_state("glm-5.2:cloud", "756B", 290)
        self.assertTrue(verdict["runs_remotely"])
        self.assertFalse(verdict["within_ceiling"])
        self.assertIn("leave this host", verdict["ceiling_reason"])

    def test_the_refusal_names_spend_rather_than_size(self) -> None:
        """The reason an operator reads must be the real one. Told it was 'too big', he would
        reasonably raise the ceiling — and that is exactly the action that must not admit it."""
        reason = intro._ceiling_state("glm-5.2:cloud", "756B", 290)["ceiling_reason"]
        self.assertIn("provider spend", reason)
        self.assertIn("at any ceiling", reason)

    def test_a_large_LOCAL_model_is_not_marked_remote(self) -> None:
        """The separation, from the other side: 32B is a performance question, not a spend one."""
        verdict = intro._ceiling_state("qwen3:32b", "32.8B", 20_200_000_000)
        self.assertFalse(verdict["runs_remotely"])

    def test_a_tiny_reported_size_is_what_distinguishes_them_not_the_name(self) -> None:
        """Matching on ':cloud' in the tag would be defeated by any differently-named pointer.
        The discriminator is bytes on disk, which the daemon reports and a name cannot fake."""
        disguised = intro._ceiling_state("perfectly-normal:8b", "8.2B", 412)
        self.assertTrue(disguised["runs_remotely"])

    def test_every_verdict_carries_the_flag(self) -> None:
        """A missing key would read as falsey at the call site and silently admit the model."""
        for name, params, size in (("a:8b", "8.2B", 5_000_000_000),
                                   ("b:70b", "70.6B", 42_000_000_000),
                                   ("c:x", "not-a-number", 5_000_000_000),
                                   ("d:cloud", "756B", 290)):
            self.assertIn("runs_remotely", intro._ceiling_state(name, params, size), name)

    def test_disk_sizes_come_from_the_same_enumeration_as_the_names(self) -> None:
        sizes = intro._model_disk_sizes(tags(CLOUD, BIG_LOCAL, SMALL_LOCAL))
        self.assertEqual(sizes["glm-5.2:cloud"], 290)
        self.assertEqual(sizes["qwen3:32b"], 20_200_000_000)

    def test_a_row_with_no_size_is_not_assumed_local(self) -> None:
        """Fail closed: an unreadable size must not sail through as a real local model."""
        sizes = intro._model_disk_sizes(tags({"name": "mystery:8b", "details": {}}))
        self.assertEqual(sizes.get("mystery:8b"), 0)
        self.assertTrue(intro._ceiling_state("mystery:8b", "8.2B", 0)["runs_remotely"])

    def test_the_threshold_is_far_below_any_real_model_and_far_above_a_pointer(self) -> None:
        """290 bytes vs 64 MB vs the smallest real model in the library at ~274 MB."""
        self.assertGreater(intro._MIN_LOCAL_WEIGHTS_BYTES, 1_000_000)
        self.assertLess(intro._MIN_LOCAL_WEIGHTS_BYTES, 274_000_000)


if __name__ == "__main__":
    unittest.main()
