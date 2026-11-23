# tests/test_web_view.py
# The web dashboard must never show numbers different from the checker: a recorded run (runs/sample_S3) is fed
# record by record through the dashboard's data layer (exactly as replay mode does) and the invariant rows and
# counters it would display are compared with checker.py run directly on the files.
# Serves N3 (the visual layer is bound to the checker, not a second implementation).
"""Data-layer tests for harness.web_view."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import checker
from harness.web_view import ReplaySource, RunState, invariant_view

SAMPLE = Path(__file__).resolve().parent.parent / "runs" / "sample_S3"
pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample run not present")


def fed_state() -> RunState:
    """Feed every record of the sample run, in replay order, then mark the run finished."""
    src = ReplaySource(SAMPLE, speed=1.0, loop=False)
    state = RunState(SAMPLE, mode="replay")
    for _ts, key, rec in src.records:
        state.feed_record(key, rec)
    state.set_scenario(src.scenario, finished=True)
    return state


def test_page_counters_equal_checker_exactly() -> None:
    """Rows (invariant, side, status, detail), counters and overall equal checker.py's own output."""
    page = fed_state().invariants()
    run = checker.RunData.load(SAMPLE)
    results = checker.check_run(run)
    ref = invariant_view(run, results)
    assert page["rows"] == ref["rows"]
    assert page["counters"] == ref["counters"]
    assert page["overall"] == ref["overall"] == "PASS"
    # and the counters are the checker's metrics, not something re-derived
    by = {(r.invariant, r.side): r for r in results}
    for side in checker.SIDES:
        c = page["counters"][side]
        assert c["events_seen"] == len(run.received(side))
        assert c["missing"] == len(by[("I1", side)].metrics["missing"])
        assert c["out_of_order"] == by[("I2", side)].metrics["inversions"]
        assert c["value_mismatches"] == len(by[("I3", side)].metrics["mismatches"])
        assert c["unexplained_losses"] == len(by[("I6", side)].metrics["unexplained"])
    assert page["latency"] == {s: checker.latency(run, s) for s in checker.SIDES}


def test_timeline_marks_every_receipt() -> None:
    """Every event a client received appears as a tick in that side's timeline column."""
    state = fed_state()
    run = checker.RunData.load(SAMPLE)
    for side in checker.SIDES:
        received = {r["seq"] for r in run.received(side)}
        ticked = {seq for seq, row in state.timeline.items() if row[side] and "lat" in row[side]}
        assert ticked == received & set(state.timeline)


def test_mid_run_view_only_judges_settled_events() -> None:
    """Halfway through, the live window ends 2 s before the newest record, and nothing crashes."""
    src = ReplaySource(SAMPLE, speed=1.0, loop=False)
    state = RunState(SAMPLE, mode="replay")
    for _ts, key, rec in src.records[: len(src.records) // 2]:
        state.feed_record(key, rec)
    view = state.invariants()
    assert view["window_end_ns"] == state.now_ns - 2_000_000_000
    assert {r["invariant"] for r in view["rows"]} == {"I1", "I2", "I3", "I4", "I5", "I6"}
