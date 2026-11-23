# harness/live_view.py
# Side-by-side terminal view for the panel: "GEM host sees" | "Core (truth)" | "OPC UA client sees".
# It only TAILS the three JSONL logs of a run (gem_host.jsonl, core_audit.jsonl, ua_client.jsonl), so it needs
# no protocol session of its own (HSMS allows only one) and shows exactly what each side actually received.
# Cells that disagree with the core are shown in red.
# Serves N3 (makes cross-interface consistency visible live).
"""Live three-column view of one run (python -m harness.live_view [--run-id X] [--once])."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.live import Live
from rich.table import Table

from equipment import config
from equipment.audit import latest_run_id

CONTROL_NAMES = {int(s): s.name for s in config.ControlState}
PROCESSING_NAMES = {int(s): s.name for s in config.ProcessingState}
ROWS = ("Temperature", "ControlState", "ProcessingState", "Authority", "TempHighLimit", "Alarm 5001",
        "Last event seq", "Last rejection", "Events received", "GEM link")


class JsonlTail:
    """Reads only the new complete lines of a growing JSONL file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._pos = 0
        self._partial = ""

    def read_new(self) -> list[dict[str, Any]]:
        """Return records appended since the last call (incomplete last line is kept for later)."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                f.seek(self._pos)
                chunk = f.read()
                self._pos = f.tell()
        except FileNotFoundError:
            return []
        data = self._partial + chunk
        lines = data.split("\n")
        self._partial = lines.pop()  # "" if the chunk ended with a newline
        out = []
        for line in lines:
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return out


@dataclass
class Side:
    """What one column currently believes."""

    values: dict[str, Any] = field(default_factory=lambda: {r: None for r in ROWS})
    events: int = 0
    last_ts_ns: Optional[int] = None

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value


def _rejection(origin: Any, reason: Any) -> str:
    return f"{origin}: {reason}"


def apply_core(side: Side, r: dict[str, Any]) -> None:
    """Update the core column from one audit record."""
    kind, rid, val = r["kind"], r["id"], r["value"]
    side.last_ts_ns = r["ts_ns"]
    if kind == "sample":
        side.set("Temperature", val)
    elif kind == "state" and rid == "ControlState":
        side.set("ControlState", val)
    elif kind == "state" and rid == "ProcessingState":
        side.set("ProcessingState", val)
    elif kind == "state" and rid == "GemCommunicationState":
        side.set("GEM link", val)
    elif kind == "authority":
        side.set("Authority", val)
    elif kind == "ec_write":
        side.set("TempHighLimit", val)
    elif kind in ("alarm_set", "alarm_clear"):
        side.set("Alarm 5001", "SET" if kind == "alarm_set" else "clear")
        side.set("Last event seq", r["seq"])
        side.events += 1
    elif kind == "event":
        side.set("Last event seq", r["seq"])
        side.events += 1
    elif kind in ("command_rejected", "ec_rejected"):
        side.set("Last rejection", _rejection(r["origin"], r["extra"].get("reason")))


def apply_gem(side: Side, r: dict[str, Any]) -> None:
    """Update the GEM column from one gem_host.jsonl record (only what GEM messages told the host)."""
    side.last_ts_ns = r["ts_ns"]
    kind, data = r["kind"], r.get("data") or {}
    if kind == "status":  # initial S1F3 read
        side.set("Temperature", round(float(data.get("ChamberTemp", 0)), 3))
        side.set("ControlState", CONTROL_NAMES.get(data.get("ControlState"), data.get("ControlState")))
        side.set("ProcessingState", PROCESSING_NAMES.get(data.get("ProcessingState"), data.get("ProcessingState")))
        side.set("Authority", data.get("Authority"))
        side.set("Last event seq", data.get("LastEventSeq"))
        if data.get("TempHighLimit") is not None:
            side.set("TempHighLimit", round(float(data["TempHighLimit"]), 3))
        side.set("GEM link", "COMMUNICATING")
    elif kind in ("alarm_set", "alarm_clear"):
        side.set("Alarm 5001", "SET" if kind == "alarm_set" else "clear")
        side.set("Last event seq", r["seq"])
        side.events += 1
    elif kind == "event":
        ceid = r["id"]
        side.set("Last event seq", r["seq"])
        side.events += 1
        temp = data.get(str(config.DVID_EVENT_TEMP))
        if temp is not None:
            side.set("Temperature", round(float(temp), 3))
        if ceid == config.CEID_CONTROL_STATE_CHANGED:
            side.set("ControlState", CONTROL_NAMES.get(data.get(str(config.SVID_CONTROL_STATE))))
        elif ceid == config.CEID_PROCESSING_STARTED:
            side.set("ProcessingState", "EXECUTING")
        elif ceid == config.CEID_PROCESSING_STOPPED:
            side.set("ProcessingState", "IDLE")
        elif ceid == config.CEID_AUTHORITY_CHANGED:
            side.set("Authority", data.get(str(config.SVID_AUTHORITY)))
        elif ceid == config.CEID_TEMP_HIGH_LIMIT_CHANGED:
            side.set("TempHighLimit", round(float(data.get(str(config.ECID_TEMP_HIGH_LIMIT))), 3))
        elif ceid == config.CEID_COMMAND_REJECTED:
            side.set("Last rejection", _rejection(data.get(str(config.DVID_ORIGIN)),
                                                  data.get(str(config.DVID_REJECT_REASON))))


_UA_VARS = {"Temperature": "Temperature", "ControlState": "ControlState", "ProcessingState": "ProcessingState",
            "Authority": "Authority", "TempHighLimit": "TempHighLimit", "CommunicationState": "GEM link"}


def apply_ua(side: Side, r: dict[str, Any]) -> None:
    """Update the UA column from one ua_client.jsonl record."""
    side.last_ts_ns = r["ts_ns"]
    kind, data = r["kind"], r.get("data") or {}
    if kind == "data":
        key = r["id"]
        if key in _UA_VARS:
            side.set(_UA_VARS[key], data.get("value"))
        elif key == "AlarmActive":
            side.set("Alarm 5001", "SET" if data.get("value") else "clear")
    elif kind in ("alarm_set", "alarm_clear"):
        side.set("Alarm 5001", "SET" if kind == "alarm_set" else "clear")
        side.set("Last event seq", r["seq"])
        side.events += 1
    elif kind == "event":
        side.set("Last event seq", r["seq"])
        side.events += 1
        if r["id"] == config.CEID_COMMAND_REJECTED:
            p = data.get("payload", {})
            side.set("Last rejection", _rejection(p.get(str(config.DVID_ORIGIN)), p.get(str(config.DVID_REJECT_REASON))))


def seed_core(side: Side) -> None:
    """The core starts from config.py values; the audit only records CHANGES, so seed the truth column."""
    side.set("ControlState", config.INITIAL_CONTROL_STATE.name)
    side.set("ProcessingState", config.INITIAL_PROCESSING_STATE.name)
    side.set("Authority", "OPERATOR")
    side.set("TempHighLimit", config.equipment_constant(config.ECID_TEMP_HIGH_LIMIT).default)
    side.set("Alarm 5001", "clear")
    side.set("GEM link", "NOT_COMMUNICATING")


def values_agree(row: str, a: Any, core: Any) -> bool:
    """Does a client's value agree with the core's? (shared by the terminal and the web view)"""
    if a is None or core is None or row in ("Events received", "Last event seq"):
        return True  # event counters legitimately differ (clients join later) - the checker judges those
    if isinstance(a, (int, float)) and isinstance(core, (int, float)):
        # GEM learns the temperature only from the 1 Hz CEID 1007 (heater: up to 0.8 degC/s), so a
        # 1-second-old GEM value is normal, not a disagreement. The checker judges exact values per seq.
        tol = 1.0 if row == "Temperature" else config.FLOAT_TOLERANCE
        return abs(float(a) - float(core)) <= tol
    return str(a) == str(core)


APPLIERS = {"gem": apply_gem, "core": apply_core, "ua": apply_ua}


class LiveView:
    """Holds the three tails and renders the table."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.tails = {
            "gem": JsonlTail(run_dir / config.GEM_HOST_LOG_FILE),
            "core": JsonlTail(run_dir / config.CORE_AUDIT_FILE),
            "ua": JsonlTail(run_dir / config.UA_CLIENT_LOG_FILE),
        }
        self.sides = {"gem": Side(), "core": Side(), "ua": Side()}
        seed_core(self.sides["core"])
        self._appliers = APPLIERS

    def poll(self) -> None:
        """Read whatever is new in the three files."""
        for key, tail in self.tails.items():
            for rec in tail.read_new():
                try:
                    self._appliers[key](self.sides[key], rec)
                except (KeyError, TypeError, ValueError):
                    pass  # a malformed line must never stop the view

    @staticmethod
    def _fmt(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    def _same(self, row: str, a: Any, core: Any) -> bool:
        return values_agree(row, a, core)

    def table(self) -> Table:
        """Render the current state."""
        t = Table(title=f"Chamber1Tool — run {self.run_dir.name}", expand=True)
        t.add_column("", style="bold")
        t.add_column("GEM host sees", justify="center")
        t.add_column("Core (truth)", justify="center", style="cyan")
        t.add_column("OPC UA client sees", justify="center")
        for side in self.sides.values():
            side.values["Events received"] = side.events
        for row in ROWS:
            core = self.sides["core"].values[row]
            cells = []
            for key in ("gem", "ua"):
                v = self.sides[key].values[row]
                text = self._fmt(v)
                cells.append(text if self._same(row, v, core) else f"[bold red]{text}[/]")
            t.add_row(row, cells[0], self._fmt(core), cells[1])
        now = time.time_ns()
        ages = []
        for key in ("gem", "core", "ua"):
            ts = self.sides[key].last_ts_ns
            ages.append("no data" if ts is None else f"{(now - ts) / 1e9:.1f} s ago")
        t.add_row("[dim]last update[/]", *(f"[dim]{a}[/]" for a in ages))
        return t


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    p = argparse.ArgumentParser(description="Live GEM | core | OPC UA view of one run")
    p.add_argument("--run-id", default=None, help="default: runs/LATEST")
    p.add_argument("--refresh", type=float, default=0.25, help="seconds between redraws")
    p.add_argument("--once", action="store_true", help="print one snapshot and exit (no live screen)")
    args = p.parse_args(argv)
    run_id = args.run_id or latest_run_id()
    if run_id is None:
        print("no run found: start `python -m equipment.main` first or pass --run-id", file=sys.stderr)
        return 1
    view = LiveView(Path.cwd() / config.RUNS_DIR / run_id)
    console = Console()
    if args.once:
        view.poll()
        console.print(view.table())
        return 0
    try:
        with Live(view.table(), console=console, refresh_per_second=max(1, int(1 / args.refresh)),
                  screen=False) as live:
            while True:
                view.poll()
                live.update(view.table())
                time.sleep(args.refresh)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
