# tests/test_core.py
# Core invariants: strictly increasing seq, an audit line for every state change, reply-code
# mapping, alarm hysteresis, and the NO-BYPASS test (deny-all arbiter => nothing changes, from any
# origin and any entry point).
# Serves N1 (no bypass path around the arbiter) and N3 (the audit log is a complete oracle).
"""Tests for equipment.core.EquipmentCore."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from equipment import arbiter, config
from equipment.audit import AuditLog
from equipment.config import ControlState, Origin
from equipment.core import EquipmentCore
from equipment.dispatcher import Dispatcher, Notification
from equipment.sensors import SimulatedChamber

GEM, UA, OP = Origin.GEM_HOST, Origin.UA_CLIENT, Origin.OPERATOR


def make_core(tmp_path: Path | None = None, state: ControlState = ControlState.ONLINE_LOCAL) -> EquipmentCore:
    """Core with an in-memory (or file) audit log and no dispatcher."""
    audit = AuditLog(tmp_path / "core_audit.jsonl" if tmp_path else None)
    return EquipmentCore(audit, initial_control_state=state)


def records(core: EquipmentCore) -> list:
    """All audit records of a core (test helper)."""
    return core._audit.records  # noqa: SLF001


def exercise(core: EquipmentCore) -> None:
    """A mixed workload touching every command path, accepted and rejected."""
    core.on_sample(25.0)
    core.set_control_state(OP, ControlState.ONLINE_REMOTE)
    core.submit_command(GEM, "START")
    core.submit_command(UA, "STOP")  # rejected: authority
    core.submit_ec_write(GEM, config.ECID_TEMP_HIGH_LIMIT, 35.0)
    core.submit_ec_write(GEM, config.ECID_TEMP_HIGH_LIMIT, 99.0)  # rejected: range
    for t in (30.0, 36.0, 36.5, 34.5, 33.9):
        core.on_sample(t)
    core.submit_command(OP, "STOP")  # safety override in REMOTE
    core.set_control_state(OP, ControlState.EQUIPMENT_OFFLINE)
    core.set_lease(OP, True)
    core.submit_ec_write(UA, config.ECID_TEMP_HIGH_LIMIT, 45.0)
    core.submit_command(GEM, "START")  # rejected: lease held by UA
    core.submit_command(GEM, "FLY")  # unknown
    core.set_control_state(OP, ControlState.ONLINE_LOCAL)  # revokes lease


def test_seq_strictly_increasing_and_written_to_file(tmp_path: Path) -> None:
    """Seqs start at 1, have no gaps, and every line is flushed to the JSONL file."""
    core = make_core(tmp_path)
    exercise(core)
    seqs = [r.seq for r in records(core)]
    assert seqs == list(range(1, len(seqs) + 1))
    lines = (tmp_path / "core_audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["seq"] for line in lines] == seqs
    for line in lines:
        rec = json.loads(line)
        assert set(rec) == {"seq", "ts_ns", "kind", "id", "value", "origin", "extra"}
        assert rec["kind"] in {k.value for k in config.AuditKind}


def test_every_state_change_has_an_audit_line() -> None:
    """Replaying the audit log reproduces the final state exactly: no change happened unaudited."""
    core = make_core()
    exercise(core)
    replay = {"ControlState": "ONLINE_LOCAL", "ProcessingState": "IDLE", "LeaseUA": False,
              "Authority": "OPERATOR", "limit": 40.0, "temp": 25.0, "alarms": set()}
    for r in records(core):
        if r.kind == "state" and r.id in ("ControlState", "ProcessingState", "LeaseUA"):
            replay[r.id] = r.value
        elif r.kind == "authority":
            replay["Authority"] = r.value
        elif r.kind == "ec_write":
            replay["limit"] = r.value
        elif r.kind == "sample":
            replay["temp"] = r.value
        elif r.kind == "alarm_set":
            replay["alarms"].add(r.id)
        elif r.kind == "alarm_clear":
            replay["alarms"].discard(r.id)
    snap = core.snapshot()
    assert replay["ControlState"] == snap["control_state"]
    assert replay["ProcessingState"] == snap["processing_state"]
    assert replay["LeaseUA"] == snap["lease_ua"]
    assert replay["Authority"] == snap["authority"]
    assert replay["limit"] == snap["temp_high_limit"]
    assert replay["temp"] == snap["temp"]
    assert sorted(replay["alarms"]) == snap["alarms_active"]


def test_events_carry_their_own_seq_and_event_time_values() -> None:
    """DVID 101 inside every event payload equals the event's audit seq (the checker's join key)."""
    core = make_core()
    exercise(core)
    events = [r for r in records(core) if r.kind == "event"]
    assert events
    for e in events:
        assert e.value[config.DVID_EVENT_SEQ] == e.seq
        assert set(e.value) == set(config.collection_event(e.id).report_vids)


def test_every_rejection_emits_ceid_1005() -> None:
    """Rejections are audited and followed immediately by a CEID 1005 event naming the origin and reason."""
    core = make_core()
    exercise(core)
    recs = records(core)
    rejected = [i for i, r in enumerate(recs) if r.kind in ("command_rejected", "ec_rejected")]
    assert len(rejected) == 4
    for i in rejected:
        nxt = recs[i + 1]
        assert nxt.kind == "event" and nxt.id == config.CEID_COMMAND_REJECTED
        assert nxt.value[config.DVID_ORIGIN] == recs[i].origin
        assert nxt.value[config.DVID_REJECT_REASON] == recs[i].extra["reason"]


def test_reply_code_mapping() -> None:
    """HCACK / EAC / UA status mapping from CLAUDE.md 6.4."""
    core = make_core(state=ControlState.ONLINE_REMOTE)
    r = core.submit_command(GEM, "START")
    assert (r.ok, r.gem_code, r.ua_status) == (True, 0, "Good")
    r = core.submit_command(GEM, "START")
    assert (r.ok, r.gem_code, r.ua_status) == (False, 5, "BadInvalidState")
    r = core.submit_command(UA, "STOP")
    assert (r.ok, r.gem_code, r.ua_status) == (False, 2, "BadUserAccessDenied")
    r = core.submit_command(GEM, "JUMP")
    assert (r.ok, r.gem_code, r.ua_status) == (False, 1, "BadNotFound")
    r = core.submit_ec_write(GEM, 999, 30)
    assert (r.ok, r.gem_code, r.ua_status) == (False, 1, "BadNotFound")
    r = core.submit_ec_write(UA, config.ECID_TEMP_HIGH_LIMIT, 30)
    assert (r.ok, r.gem_code, r.ua_status) == (False, 2, "BadUserAccessDenied")
    r = core.submit_ec_write(GEM, config.ECID_TEMP_HIGH_LIMIT, 80.5)
    assert (r.ok, r.gem_code, r.ua_status) == (False, 3, "BadOutOfRange")
    r = core.submit_ec_write(GEM, config.ECID_TEMP_HIGH_LIMIT, "not a number")
    assert (r.ok, r.gem_code, r.ua_status) == (False, 3, "BadOutOfRange")
    r = core.submit_ec_write(GEM, config.ECID_TEMP_HIGH_LIMIT, 20)
    assert (r.ok, r.gem_code, r.ua_status) == (True, 0, "Good")
    assert core.get_ec(config.ECID_TEMP_HIGH_LIMIT) == 20.0


def test_lease_rules() -> None:
    """Lease only in OFFLINE; leaving OFFLINE revokes it and returns authority to the operator."""
    core = make_core(state=ControlState.ONLINE_LOCAL)
    assert not core.set_lease(OP, True).ok
    core.set_control_state(OP, ControlState.EQUIPMENT_OFFLINE)
    assert core.set_lease(OP, True).ok
    assert core.snapshot()["authority"] == "UA_CLIENT"
    core.set_control_state(OP, ControlState.ONLINE_REMOTE)
    snap = core.snapshot()
    assert snap["lease_ua"] is False and snap["authority"] == "GEM_HOST"


def test_alarm_hysteresis() -> None:
    """Set when temp > limit; stays set until temp < limit - 1.0; each transition audited once."""
    core = make_core()
    limit = core.get_ec(config.ECID_TEMP_HIGH_LIMIT)
    temps = [limit - 1, limit, limit + 0.01, limit + 5, limit - 0.5, limit - 1.0, limit - 1.01, limit + 0.5, limit - 2]
    states = []
    for t in temps:
        core.on_sample(t)
        states.append(bool(core.snapshot()["alarms_active"]))
    assert states == [False, False, True, True, True, True, False, True, False]
    kinds = [r.kind for r in records(core) if r.kind.startswith("alarm_")]
    assert kinds == ["alarm_set", "alarm_clear", "alarm_set", "alarm_clear"]


def test_temp_sample_event_at_1hz() -> None:
    """CEID 1007 is emitted at most once per ~second, not on every 0.5 s sample."""
    core = make_core()
    for _ in range(4):
        core.on_sample(25.0)
    n = sum(1 for r in records(core) if r.kind == "event" and r.id == config.CEID_TEMP_SAMPLE)
    assert n == 1  # four samples in a few microseconds -> only the first emits


def test_no_bypass_deny_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a deny-all arbiter, NO entry point from ANY origin changes state (rule 5)."""
    calls: list[tuple] = []

    def deny_all(control_state, lease_ua, origin, action):  # type: ignore[no-untyped-def]
        calls.append((origin, action))
        return arbiter.Decision(False, "deny-all test arbiter")

    monkeypatch.setattr(arbiter, "decide", deny_all)
    core = make_core(state=ControlState.EQUIPMENT_OFFLINE)
    before = core.snapshot()
    n_paths = 0
    for origin in (GEM, UA, OP):
        results = [
            core.submit_command(origin, "START"),
            core.submit_command(origin, "STOP"),
            core.submit_ec_write(origin, config.ECID_TEMP_HIGH_LIMIT, 30.0),
            core.set_control_state(origin, ControlState.ONLINE_REMOTE),
            core.set_lease(origin, True),
        ]
        n_paths += len(results)
        assert not any(r.ok for r in results)
    after = core.snapshot()
    for key in ("control_state", "processing_state", "authority", "lease_ua", "temp_high_limit", "alarms_active"):
        assert after[key] == before[key], key
    assert len(calls) == n_paths  # the arbiter was consulted on every single path
    changed = [r for r in records(core) if r.kind in ("state", "authority", "ec_write", "command_ok")]
    assert changed == []


def test_notifications_published_in_seq_order() -> None:
    """Everything audited is published to the dispatcher in the same seq order."""
    received: list[Notification] = []
    disp = Dispatcher()
    disp.subscribe("t", received.append)
    core = EquipmentCore(AuditLog(None), disp, SimulatedChamber())
    exercise(core)
    assert disp.wait_idle(5)
    disp.stop()
    assert [n.seq for n in received] == [r.seq for r in records(core)]
