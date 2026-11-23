# equipment/dispatcher.py
# Fan-out of core notifications to subscribers (GEM door, OPC UA door, live view).
# One bounded FIFO queue + one worker thread per subscriber: the core only enqueues (never blocks),
# each subscriber sees notifications in seq order, and a slow or dead subscriber cannot delay others.
# Serves N1 (one core, independent doors) and N3 (ordering guarantee behind invariant I2).
"""Per-subscriber ordered, bounded notification queues (CLAUDE.md section 6.3)."""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from equipment.config import DISPATCHER_QUEUE_SIZE

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Notification:
    """What the core tells subscribers. Mirrors one audit record."""

    seq: int
    ts_ns: int
    kind: str
    id: Any
    value: Any
    origin: str
    extra: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[Notification], None]
DropCallback = Callable[[str, Notification], None]


class _Subscriber:
    """A queue and the worker thread that drains it into the subscriber's handler."""

    def __init__(self, name: str, handler: Handler, maxsize: int, on_drop: Optional[DropCallback]) -> None:
        self.name = name
        self._handler = handler
        self._maxsize = maxsize
        self._on_drop = on_drop
        self._queue: deque[Notification] = deque()
        self._cond = threading.Condition()
        self._busy = False
        self._stopping = False
        self.delivered = 0
        self.dropped = 0
        self._thread = threading.Thread(target=self._run, name=f"dispatch-{name}", daemon=True)
        self._thread.start()

    def put(self, notification: Notification) -> None:
        """Enqueue without blocking; on overflow drop the OLDEST item and report it."""
        dropped: Optional[Notification] = None
        with self._cond:
            if len(self._queue) >= self._maxsize:
                dropped = self._queue.popleft()
                self.dropped += 1
            self._queue.append(notification)
            self._cond.notify()
        if dropped is not None and self._on_drop is not None:
            try:
                self._on_drop(self.name, dropped)
            except Exception:  # noqa: BLE001 - never let reporting break publishing
                _log.exception("drop callback failed for %s", self.name)

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._queue and not self._stopping:
                    self._cond.wait()
                if self._stopping and not self._queue:
                    return
                item = self._queue.popleft()
                self._busy = True
            try:
                self._handler(item)
            except Exception:  # noqa: BLE001 - rule 10: a failing subscriber must not die or affect others
                _log.exception("subscriber %s failed on seq %s", self.name, item.seq)
            finally:
                with self._cond:
                    self._busy = False
                    self.delivered += 1
                    self._cond.notify_all()

    def wait_idle(self, timeout: float) -> bool:
        """Block until the queue is empty and the handler is not running (tests / shutdown)."""
        with self._cond:
            return self._cond.wait_for(lambda: not self._queue and not self._busy, timeout)

    def stop(self, timeout: float) -> None:
        """Ask the worker to finish what is queued and exit."""
        with self._cond:
            self._stopping = True
            self._cond.notify_all()
        self._thread.join(timeout)


class Dispatcher:
    """Publishes core notifications to every subscriber's own queue."""

    def __init__(self, on_drop: Optional[DropCallback] = None, maxsize: int = DISPATCHER_QUEUE_SIZE) -> None:
        """Create a dispatcher.

        Args:
            on_drop: called as on_drop(subscriber_name, notification) when a queue overflows
                (the core uses it to write an audit record of kind "dropped").
            maxsize: per-subscriber queue bound (CLAUDE.md: 10 000).
        """
        self._on_drop = on_drop
        self._maxsize = maxsize
        self._subs: dict[str, _Subscriber] = {}
        self._lock = threading.Lock()

    def set_drop_callback(self, on_drop: DropCallback) -> None:
        """Set the overflow callback (the core installs itself here)."""
        self._on_drop = on_drop
        for sub in self._subs.values():
            sub._on_drop = on_drop  # noqa: SLF001 - same module

    def subscribe(self, name: str, handler: Handler) -> None:
        """Register a subscriber; its handler runs on a dedicated worker thread."""
        with self._lock:
            if name in self._subs:
                raise ValueError(f"subscriber {name!r} already registered")
            self._subs[name] = _Subscriber(name, handler, self._maxsize, self._on_drop)

    def publish(self, notification: Notification) -> None:
        """Enqueue to every subscriber. Never blocks on a subscriber."""
        with self._lock:
            subs = list(self._subs.values())
        for sub in subs:
            sub.put(notification)

    def stats(self) -> dict[str, dict[str, int]]:
        """Delivered/dropped counters per subscriber."""
        with self._lock:
            return {n: {"delivered": s.delivered, "dropped": s.dropped} for n, s in self._subs.items()}

    def wait_idle(self, timeout: float = 5.0) -> bool:
        """Wait until every subscriber queue is drained."""
        with self._lock:
            subs = list(self._subs.values())
        return all(s.wait_idle(timeout) for s in subs)

    def stop(self, timeout: float = 2.0) -> None:
        """Stop all workers (queued items are still delivered first, up to `timeout` each)."""
        with self._lock:
            subs = list(self._subs.values())
            self._subs.clear()
        for s in subs:
            s.stop(timeout)
