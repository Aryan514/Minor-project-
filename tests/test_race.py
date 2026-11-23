# tests/test_race.py
# Concurrency stress: two threads released by a barrier submit conflicting commands at the same
# instant, 500 times. Exactly one may win each time, and in REMOTE the winner is always GEM_HOST.
# Also races the OPERATOR vs the leased UA_CLIENT (both allowed => only atomicity decides) and EC writes.
# Serves N1 (evidence that decide-and-apply is atomic: no check-then-act race).
"""Concurrent command stress tests for EquipmentCore."""

from __future__ import annotations

import threading

from equipment import config
from equipment.audit import AuditLog
from equipment.config import ControlState, Origin, ProcessingState
from equipment.core import CommandResult, EquipmentCore

ITERATIONS = 500
GEM, UA, OP = Origin.GEM_HOST, Origin.UA_CLIENT, Origin.OPERATOR


def race(fn_a, fn_b) -> tuple[CommandResult, CommandResult]:  # type: ignore[no-untyped-def]
    """Run two callables released by the same barrier; return (result_a, result_b)."""
    barrier = threading.Barrier(2)
    out: dict[str, CommandResult] = {}

    def run(key: str, fn) -> None:  # type: ignore[no-untyped-def]
        barrier.wait()
        out[key] = fn()

    threads = [threading.Thread(target=run, args=("a", fn_a)), threading.Thread(target=run, args=("b", fn_b))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    return out["a"], out["b"]


def test_remote_start_race_gem_always_wins() -> None:
    """REMOTE: GEM START vs UA START, 500x -> exactly one success, always GEM; UA gets the mapped rejection."""
    core = EquipmentCore(AuditLog(None, keep_in_memory=False), initial_control_state=ControlState.ONLINE_REMOTE)
    for _ in range(ITERATIONS):
        gem, ua = race(lambda: core.submit_command(GEM, "START"), lambda: core.submit_command(UA, "START"))
        assert [gem.ok, ua.ok].count(True) == 1
        assert gem.ok and gem.gem_code == config.HCACK_OK
        assert not ua.ok and ua.ua_status == "BadUserAccessDenied"
        assert core.snapshot()["processing_state"] == ProcessingState.EXECUTING.name
        assert core.submit_command(GEM, "STOP").ok  # reset for the next iteration


def test_offline_lease_start_race_exactly_one_wins() -> None:
    """OFFLINE+lease: OPERATOR and UA are BOTH allowed, so only atomicity prevents a double START."""
    core = EquipmentCore(AuditLog(None, keep_in_memory=False), initial_control_state=ControlState.EQUIPMENT_OFFLINE)
    assert core.set_lease(OP, True).ok
    winners = {OP: 0, UA: 0}
    for _ in range(ITERATIONS):
        op, ua = race(lambda: core.submit_command(OP, "START"), lambda: core.submit_command(UA, "START"))
        assert [op.ok, ua.ok].count(True) == 1
        loser = ua if op.ok else op
        assert loser.gem_code == config.HCACK_ALREADY_IN_STATE and loser.ua_status == "BadInvalidState"
        winners[OP if op.ok else UA] += 1
        assert core.submit_command(OP, "STOP").ok
    assert sum(winners.values()) == ITERATIONS


def test_remote_ec_write_race_only_gem_applied() -> None:
    """REMOTE: GEM writes 35 while UA writes 45, 500x -> final value always 35, UA always denied."""
    core = EquipmentCore(AuditLog(None, keep_in_memory=False), initial_control_state=ControlState.ONLINE_REMOTE)
    ecid = config.ECID_TEMP_HIGH_LIMIT
    for _ in range(ITERATIONS):
        assert core.submit_ec_write(GEM, ecid, 40.0).ok  # reset
        gem, ua = race(lambda: core.submit_ec_write(GEM, ecid, 35.0), lambda: core.submit_ec_write(UA, ecid, 45.0))
        assert gem.ok and not ua.ok and ua.gem_code == config.EAC_DENIED
        assert core.get_ec(ecid) == 35.0


def test_offline_lease_ec_race_last_writer_consistent() -> None:
    """Both allowed: the final value equals the value written by whichever write got the higher seq."""
    core = EquipmentCore(AuditLog(None, keep_in_memory=False), initial_control_state=ControlState.EQUIPMENT_OFFLINE)
    assert core.set_lease(OP, True).ok
    ecid = config.ECID_TEMP_HIGH_LIMIT
    for _ in range(ITERATIONS):
        op, ua = race(lambda: core.submit_ec_write(OP, ecid, 30.0), lambda: core.submit_ec_write(UA, ecid, 50.0))
        assert op.ok and ua.ok and op.seq != ua.seq
        expected = 30.0 if op.seq > ua.seq else 50.0
        assert core.get_ec(ecid) == expected
