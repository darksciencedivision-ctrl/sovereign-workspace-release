"""The retired demonstration approval queue, kept TEST-ONLY — Phase 17D `.events`.

Phase 16D's `build_governed_approval_queue` was the shell's drawer PRODUCER; the operator saw its
canned trio as if it were pending work (finding F2), so 17D replaced the producer with the
session-event fold (`tests/unit/test_session_approvals.py`). The builder survives here as a fixture,
under `tests/`, where no product import can reach it — it still exercises the real governed producers
(a real `LiveGovernedFlow.begin` plan + a real gate verdict, a real `CommandBroker` classification
mirrored into a real `ApprovalQueue`), which is the reason to keep it rather than delete it.

The property this file exists to hold: whatever it builds, it builds only for a test.
"""
from __future__ import annotations

from pathlib import Path

from tests.support.demo_approval_queue import build_governed_approval_queue

ROOT = Path(__file__).resolve().parents[2]
CONDUCTOR_DIR = ROOT / "conductor"


def test_governed_queue_has_the_three_real_kinds(tmp_path) -> None:
    q = build_governed_approval_queue(conductor_dir=CONDUCTOR_DIR, store_root=tmp_path)
    dm = q.drawer_model()
    assert dm["badge_count"] == 3
    by_kind = {r["kind"]: r for r in dm["pending"]}
    assert set(by_kind) == {"plan", "protected_action", "clarification"}
    # deterministic ids in enqueue order
    assert by_kind["plan"]["item_id"] == "ap-1"
    assert by_kind["protected_action"]["item_id"] == "ap-2"
    assert by_kind["clarification"]["item_id"] == "ap-3"
    # invariant 16 SHAPE: a clarification is never approvable into execution
    assert by_kind["clarification"]["approvable"] is False
    # the plan gate passed on the smoke objective ⇒ the plan is approvable (derived, not asserted)
    assert by_kind["plan"]["approvable"] is True
    # the protected action carries the broker's pending_id in ref (routes back to the broker)
    assert isinstance(by_kind["protected_action"]["ref"], str) and by_kind["protected_action"]["ref"]


def test_governed_queue_is_deterministic(tmp_path) -> None:
    """Same objective + fixed clock ⇒ identical drawer rows (item ids, kinds, approvable). The
    broker's random pending_id (`ref`) is the only non-governed field and is excluded."""
    a = build_governed_approval_queue(conductor_dir=CONDUCTOR_DIR, store_root=tmp_path / "a").drawer_model()
    b = build_governed_approval_queue(conductor_dir=CONDUCTOR_DIR, store_root=tmp_path / "b").drawer_model()
    strip = lambda dm: [{k: r[k] for k in ("item_id", "kind", "approvable", "origin")} for r in dm["pending"]]
    assert strip(a) == strip(b)


def test_the_demo_builder_is_not_importable_from_the_product_tree() -> None:
    """F2, stated as a location: the canned trio lives under tests/. Nothing in the shipped tree —
    control_plane/, tools/live/, apps/desktop/ — may import it."""
    def imports_it(text: str) -> bool:
        # an IMPORT of the fixture, not a prose mention of where it went
        return any(("demo_approval_queue" in line
                    and (line.lstrip().startswith(("import ", "from "))
                         or "require(" in line))
                   for line in text.splitlines())

    for tree in ("control_plane", "tools", "apps/desktop", "node_runtime", "voice_bridge"):
        for path in (ROOT / tree).rglob("*.py"):
            if "node_modules" in str(path):
                continue
            assert not imports_it(path.read_text(encoding="utf-8")), path
    for path in (ROOT / "apps" / "desktop").rglob("*.js"):
        if "node_modules" in str(path):
            continue
        assert not imports_it(path.read_text(encoding="utf-8")), path
