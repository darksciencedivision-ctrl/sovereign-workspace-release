"""CR-026 — product shutdown must not forget workers still alive after the bounded drain."""
from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

SOVEREIGN = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOVEREIGN) not in sys.path:
    sys.path.insert(0, str(SOVEREIGN))

# Import as a package (server.py uses relative imports); the qualified name does not collide with
# shell's `server` module in the shared pytest session.
import sovereign_product.server as sovereign_server  # noqa: E402


def test_cr026_survivors_are_retained_and_reported():
    block = threading.Event()

    def stuck():
        block.wait(10)

    t_stuck = threading.Thread(target=stuck, name="worker-stuck", daemon=True)
    t_stuck.start()
    t_done = threading.Thread(target=lambda: None, name="worker-done", daemon=True)
    t_done.start()
    t_done.join()

    store_closed = {"v": False}
    cancel = threading.Event()
    fake = SimpleNamespace(
        _closed=threading.Event(),
        _workers=[t_stuck, t_done],
        _queue=queue.Queue(),
        _active_cancel={"job1": cancel},
        _shutdown_survivors=[],
        store=SimpleNamespace(close=lambda: store_closed.__setitem__("v", True)),
    )

    try:
        record = sovereign_server.ProductService.close(fake)
        # The stuck worker is alive after the bounded drain: it must be reported, not silently
        # dropped while shutdown claims success.
        assert record["clean"] is False
        assert "worker-stuck" in record["survivors"]
        assert "worker-stuck" in fake._shutdown_survivors
        # In-flight jobs were asked to cancel so cancellation-aware work can wind down.
        assert cancel.is_set()
        # The finished worker is forgotten; the survivor stays tracked.
        assert fake._workers == [t_stuck]
        # The store is still closed (per-thread connections), but shutdown is reported unclean.
        assert store_closed["v"] is True
    finally:
        block.set()
        t_stuck.join(timeout=2)


def test_cr026_clean_shutdown_reports_clean():
    t_done = threading.Thread(target=lambda: None, name="w", daemon=True)
    t_done.start(); t_done.join()
    fake = SimpleNamespace(
        _closed=threading.Event(), _workers=[t_done], _queue=queue.Queue(),
        _active_cancel={}, _shutdown_survivors=[],
        store=SimpleNamespace(close=lambda: None),
    )
    record = sovereign_server.ProductService.close(fake)
    assert record["clean"] is True and record["survivors"] == []
    assert fake._workers == []
