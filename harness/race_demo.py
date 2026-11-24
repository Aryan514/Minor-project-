# harness/race_demo.py
# "Break-it" demo for the panel: N concurrent START pairs against (a) a deliberately UNSAFE check-then-act
# implementation that lives ONLY in this file, and (b) the real EquipmentCore with atomic decide-and-apply.
# The unsafe variant asks the same arbiter, releases the lock, sleeps 1 ms (injected on purpose to expose the
# race window) and only then applies. Prints "double winners: X/N" for each.
# Serves N1 (why decide-and-apply must be atomic).
"""python -m harness.race_demo [-n 200]"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from typing import Any, Callable

from equipment import arbiter
from equipment.audit import AuditLog
from equipment.config import Action, ControlState, Origin, ProcessingState
from equipment.core import EquipmentCore

# Both origins must be ALLOWED for a race to be possible. In ONLINE_REMOTE the policy already rejects UA_CLIENT, so
# even an unsafe core could never have two winners there. EQUIPMENT_OFFLINE + UA lease allows both OPERATOR and
# UA_CLIENT (same setup as tests/test_race.py), so only atomicity separates "one winner" from "two winners".
CONTENDERS = (Origin.OPERATOR, Origin.UA_CLIENT)
INJECTED_DELAY_S = 0.001


class UnsafeCore:
    """DELIBERATELY BROKEN. Check-then-act with the lock released between the check and the apply.

    Exists only in this demo script, never in equipment/. Same arbiter, same state model, same lock type as the
    real core; the ONLY difference is that the decision and the state change are not done under one lock.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.control_state = ControlState.EQUIPMENT_OFFLINE
        self.lease_ua = True
        self.processing = ProcessingState.IDLE

    def submit_start(self, origin: Origin) -> bool:
        """Check (under the lock) ... release ... wait 1 ms ... apply (under the lock again)."""
        with self._lock:
            decision = arbiter.decide(self.control_state, self.lease_ua, origin, Action.START)
            idle = self.processing == ProcessingState.IDLE
        time.sleep(INJECTED_DELAY_S)  # injected on purpose: widens the check-then-act window so the race is visible
        if decision.allowed and idle:
            with self._lock:
                self.processing = ProcessingState.EXECUTING
            return True
        return False

    def reset(self) -> None:
        """Back to IDLE for the next pair."""
        with self._lock:
            self.processing = ProcessingState.IDLE


def _pair(fn_a: Callable[[], bool], fn_b: Callable[[], bool]) -> tuple[bool, bool]:
    """Release two calls at the same instant (barrier) and return both results."""
    barrier = threading.Barrier(2)
    out: dict[int, bool] = {}

    def run(i: int, fn: Callable[[], bool]) -> None:
        barrier.wait()
        out[i] = fn()

    threads = [threading.Thread(target=run, args=(0, fn_a)), threading.Thread(target=run, args=(1, fn_b))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    return out[0], out[1]


def _tally(results: list[tuple[bool, bool]], label: str, t0: float) -> dict[str, Any]:
    winners = [a + b for a, b in results]
    return {"variant": label, "pairs": len(results), "double_winners": winners.count(2),
            "single_winner": winners.count(1), "no_winner": winners.count(0),
            "seconds": round(time.perf_counter() - t0, 2)}


def run_unsafe(n: int = 200) -> dict[str, Any]:
    """N pairs against the unsafe check-then-act variant."""
    core = UnsafeCore()
    t0 = time.perf_counter()
    results = []
    for _ in range(n):
        results.append(_pair(lambda: core.submit_start(CONTENDERS[0]), lambda: core.submit_start(CONTENDERS[1])))
        core.reset()
    return _tally(results, "UNSAFE check-then-act (1 ms injected gap, this script only)", t0)


def run_real(n: int = 200) -> dict[str, Any]:
    """N pairs against the real EquipmentCore (atomic decide-and-apply under one lock)."""
    core = EquipmentCore(AuditLog(None, keep_in_memory=False), initial_control_state=ControlState.EQUIPMENT_OFFLINE)
    assert core.set_lease(Origin.OPERATOR, True).ok
    t0 = time.perf_counter()
    results = []
    for _ in range(n):
        results.append(_pair(lambda: core.submit_command(CONTENDERS[0], "START").ok,
                             lambda: core.submit_command(CONTENDERS[1], "START").ok))
        assert core.submit_command(Origin.OPERATOR, "STOP").ok
    return _tally(results, "REAL EquipmentCore (atomic decide-and-apply)", t0)


def run_both(n: int = 200) -> dict[str, Any]:
    """Both variants with the same N and the same contenders."""
    return {"n": n, "contenders": [o.value for o in CONTENDERS],
            "setup": "EQUIPMENT_OFFLINE + UA lease: both OPERATOR and UA_CLIENT are allowed to START",
            "unsafe": run_unsafe(n), "real": run_real(n)}


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="Concurrent START pairs: unsafe check-then-act vs the real core")
    ap.add_argument("-n", type=int, default=200)
    args = ap.parse_args(argv)
    res = run_both(args.n)
    print(f"setup: {res['setup']}")
    for key in ("unsafe", "real"):
        r = res[key]
        print(f"{r['variant']}: double winners: {r['double_winners']}/{r['pairs']} "
              f"(single {r['single_winner']}, none {r['no_winner']}, {r['seconds']} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
