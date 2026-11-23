# tests/test_dispatcher.py
# Dispatcher guarantees: per-subscriber seq order, a slow subscriber does not delay another one or the
# publisher, overflow drops the OLDEST item and reports it, and a crashing handler keeps its worker alive.
# Serves N1 (independent doors) and N3 (ordering behind invariant I2, loss attribution behind I6).
"""Tests for equipment.dispatcher.Dispatcher."""

from __future__ import annotations

import threading
import time

from equipment.audit import AuditLog
from equipment.config import ControlState
from equipment.core import EquipmentCore
from equipment.dispatcher import Dispatcher, Notification


def note(seq: int) -> Notification:
    """A minimal notification."""
    return Notification(seq, time.time_ns(), "event", 1007, {}, "EQUIPMENT")


def test_order_per_subscriber() -> None:
    """Each subscriber receives every notification in publish (seq) order."""
    disp = Dispatcher()
    got: dict[str, list[int]] = {"a": [], "b": []}
    disp.subscribe("a", lambda n: got["a"].append(n.seq))
    disp.subscribe("b", lambda n: got["b"].append(n.seq))
    for s in range(1, 2001):
        disp.publish(note(s))
    assert disp.wait_idle(10)
    disp.stop()
    assert got["a"] == list(range(1, 2001))
    assert got["b"] == list(range(1, 2001))


def test_slow_subscriber_does_not_delay_another() -> None:
    """A subscriber sleeping 1 s per item neither blocks publish() nor delays the fast subscriber."""
    disp = Dispatcher()
    fast_done = threading.Event()
    fast: list[int] = []

    def fast_handler(n: Notification) -> None:
        fast.append(n.seq)
        if len(fast) == 5:
            fast_done.set()

    disp.subscribe("slow", lambda n: time.sleep(1.0))
    disp.subscribe("fast", fast_handler)
    t0 = time.monotonic()
    for s in range(1, 6):
        disp.publish(note(s))
    publish_time = time.monotonic() - t0
    assert fast_done.wait(0.5), "fast subscriber was delayed by the slow one"
    assert publish_time < 0.05
    assert fast == [1, 2, 3, 4, 5]
    disp.stop(timeout=0.1)


def test_overflow_drops_oldest_and_reports() -> None:
    """A blocked subscriber overflows its bounded queue: oldest items dropped and reported, newest kept."""
    release = threading.Event()
    got: list[int] = []
    dropped: list[tuple[str, int]] = []
    disp = Dispatcher(on_drop=lambda name, n: dropped.append((name, n.seq)), maxsize=10)

    def blocked(n: Notification) -> None:
        release.wait(5)
        got.append(n.seq)

    disp.subscribe("blocked", blocked)
    disp.publish(note(1))
    time.sleep(0.1)  # worker now holds seq 1 and waits
    for s in range(2, 22):  # 20 more items into a queue of 10
        disp.publish(note(s))
    release.set()
    assert disp.wait_idle(5)
    disp.stop()
    assert [s for _, s in dropped] == list(range(2, 12))
    assert got == [1] + list(range(12, 22))


def test_overflow_is_audited_by_core() -> None:
    """When wired to the core, a queue overflow writes an audit record of kind 'dropped'."""
    release = threading.Event()
    disp = Dispatcher(maxsize=3)
    disp.subscribe("stuck", lambda n: release.wait(5))
    audit = AuditLog(None)
    core = EquipmentCore(audit, disp, initial_control_state=ControlState.ONLINE_LOCAL)
    for _ in range(10):
        core.on_sample(25.0)
    release.set()
    assert disp.wait_idle(5)
    disp.stop()
    dropped = [r for r in audit.records if r.kind == "dropped"]
    assert dropped and all(r.extra["subscriber"] == "stuck" for r in dropped)
    seqs = [r.seq for r in audit.records]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_handler_exception_keeps_worker_alive() -> None:
    """Rule 10: a subscriber that raises keeps receiving later notifications."""
    disp = Dispatcher()
    got: list[int] = []

    def flaky(n: Notification) -> None:
        if n.seq == 2:
            raise RuntimeError("boom")
        got.append(n.seq)

    disp.subscribe("flaky", flaky)
    for s in (1, 2, 3):
        disp.publish(note(s))
    assert disp.wait_idle(5)
    disp.stop()
    assert got == [1, 3]
