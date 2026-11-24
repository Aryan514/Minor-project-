# tests/test_control_panel.py
# Fast checks of the dashboard's new back-end pieces that need no running system: the policy table is the
# arbiter's own output, the race demo separates the unsafe check-then-act variant from the real atomic core, and
# the SECS wire handler records secsgem's SML log lines.
# Serves N1 (policy + atomicity evidence shown on the panel is computed, not drawn) and N3 (wire log).
"""Tests for harness.control_panel, harness.race_demo and equipment.wire_log."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import secsgem.hsms
from secsgem.secs.functions import SecsS02F41

from equipment import arbiter
from equipment.config import Action, ControlState, Origin
from equipment.wire_log import SecsWireHandler
from harness import race_demo
from harness.control_panel import policy_table


def test_policy_table_is_the_arbiter() -> None:
    """Every cell of the panel's table agrees with arbiter.decide."""
    rows = policy_table()
    assert [r["state"] for r in rows] == ["ONLINE_REMOTE", "ONLINE_LOCAL", "EQUIPMENT_OFFLINE",
                                          "EQUIPMENT_OFFLINE + lease"]
    for r in rows:
        state = ControlState[r["control_state"]]
        for origin in (Origin.GEM_HOST, Origin.UA_CLIENT, Origin.OPERATOR):
            allowed = [a for a in (Action.START, Action.STOP, Action.EC_WRITE)
                       if arbiter.decide(state, r["lease"], origin, a).allowed]
            kind = r["cells"][origin.value]["kind"]
            assert kind == ("ok" if len(allowed) == 3 else "no" if not allowed else "part")
    assert rows[0]["cells"]["OPERATOR"]["text"] == "STOP only"  # safety override in REMOTE


def test_race_demo_unsafe_breaks_real_does_not() -> None:
    """The injected check-then-act gap produces double winners; the real core never does."""
    unsafe, real = race_demo.run_unsafe(30), race_demo.run_real(30)
    assert unsafe["double_winners"] > 0
    assert real["double_winners"] == 0 and real["single_winner"] == 30


def test_secs_wire_handler_records_sml(tmp_path: Path) -> None:
    """A secsgem-style '> message\\nSML' record becomes one JSONL wire record with stream/function and SML."""
    path = tmp_path / "wire.jsonl"
    handler = SecsWireHandler(path, side="equipment")
    function = SecsS02F41({"RCMD": "START", "PARAMS": []})
    header = secsgem.hsms.HsmsStreamFunctionHeader(7, 2, 41, True, 0)
    message = secsgem.hsms.HsmsMessage(header, function.encode())
    record = logging.LogRecord("communication", logging.INFO, __file__, 1, "> %s\n%s", (message, function), None)
    handler.emit(record)
    handler.close()
    rec = json.loads(path.read_text(encoding="utf-8").strip())
    assert (rec["dir"], rec["stream"], rec["function"], rec["wbit"], rec["system"]) == ("out", 2, 41, True, 7)
    assert '<A "START">' in rec["sml"]
