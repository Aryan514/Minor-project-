# harness/web_view.py
# Live web dashboard for one run (stdlib only: http.server + Server-Sent Events; the page web_view.html is a
# single self-contained file with no CDN). It is READ-ONLY: it only tails the run's JSONL logs, exactly like
# live_view.py, and never talks to the core, the arbiter or ports 5000/4840/5100/5101. The invariants panel calls
# harness/checker.py on the records seen so far (no re-implementation). --replay plays a finished run back.
# Serves N3 (makes the consistency method visible) and N1/N2 (arbiter decisions and interface gaps live).
"""python -m harness.web_view [--run-dir runs/<id>] [--port 8080] | --replay runs/<id> [--speed 5] [--loop]"""

from __future__ import annotations

import argparse
import heapq
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

from equipment import config
from harness import checker
from harness.live_view import APPLIERS, ROWS, JsonlTail, Side, seed_core, values_agree

PAGE = Path(__file__).with_name("web_view.html")
# (source key, log file). Polled in this order so a core record is normally seen before its receipts.
SOURCES = (("core", config.CORE_AUDIT_FILE), ("gem_send", config.GEM_SEND_LOG_FILE),
           ("ua_send", config.UA_SEND_LOG_FILE), ("gem", config.GEM_HOST_LOG_FILE), ("ua", config.UA_CLIENT_LOG_FILE))
COMMAND_KINDS = {"command_ok": True, "command_rejected": False, "ec_write": True, "ec_rejected": False}
EVENT_KINDS = ("event", "alarm_set", "alarm_clear")
CEID_NAMES = {ce.ceid: ce.name for ce in config.COLLECTION_EVENTS}
LIVE_EDGE_NS = 2_000_000_000  # live: judge only events at least 2 s old (in-flight ones are not "missing")
KEEP_TIMELINE, KEEP_FEED, KEEP_TEMPS = 300, 200, 2400


# ====================================================================== data layer
def invariant_view(run: checker.RunData, results: list[checker.Result]) -> dict[str, Any]:
    """Rows + per-side counters shown on the page, derived ONLY from checker results (tested to match)."""
    by = {(r.invariant, r.side): r for r in results}
    counters: dict[str, dict[str, int]] = {}
    for side in checker.SIDES:
        i1, i2, i3, i6 = (by.get((k, side)) for k in ("I1", "I2", "I3", "I6"))
        m = lambda r, k, d=0: (r.metrics.get(k, d) if r is not None and r.metrics else d)  # noqa: E731
        counters[side] = {
            "events_seen": len(run.received(side)),
            "missing": len(m(i1, "missing", [])),
            "duplicates": len(m(i1, "duplicates", [])),
            "out_of_order": m(i2, "inversions"),
            "value_mismatches": len(m(i3, "mismatches", [])),
            "attributed_losses": m(i6, "lost") - len(m(i6, "unexplained", [])),
            "unexplained_losses": len(m(i6, "unexplained", [])),
        }
    rows = [{"invariant": r.invariant, "side": r.side, "status": r.status, "detail": r.detail} for r in results]
    return {"rows": rows, "counters": counters, "overall": checker.overall(results)}


class RunState:
    """Everything the page shows, built incrementally from log records of one run.

    The raw record lists are kept exactly as checker.RunData expects them, so invariants are evaluated by
    checker.check_run itself.
    """

    def __init__(self, run_dir: Optional[Path], mode: str = "live") -> None:
        self.run_dir = run_dir
        self.mode = mode
        self.audit: list[dict[str, Any]] = []
        self.client: dict[str, list[dict[str, Any]]] = {"GEM": [], "UA": []}
        self.send: dict[str, list[dict[str, Any]]] = {"GEM": [], "UA": []}
        self.scenario: dict[str, Any] = {}
        self.finished = False  # scenario.json present (or replay at the end): use the scenario's own window
        self.sides = {"gem": Side(), "core": Side(), "ua": Side()}
        seed_core(self.sides["core"])
        self.timeline: dict[int, dict[str, Any]] = {}
        self._pending_rx: dict[int, list[tuple[str, dict[str, Any]]]] = {}
        self.feed: list[dict[str, Any]] = []
        self.temps: list[list[float]] = []
        self.limits: list[list[float]] = []
        self.alarms: list[list[Optional[int]]] = []
        self.link = "NOT_COMMUNICATING"
        self.now_ns = 0  # data time of the latest record (replay: virtual clock)
        self.version = 0

    # ---- feeding
    def feed_record(self, source: str, rec: dict[str, Any]) -> list[dict[str, Any]]:
        """Consume one log record; return UI delta items."""
        self.version += 1
        self.now_ns = max(self.now_ns, int(rec.get("ts_ns", 0)))
        items: list[dict[str, Any]] = []
        if source == "core":
            self.audit.append(rec)
            self._apply_side("core", rec)
            items += self._core_items(rec)
        elif source in ("gem", "ua"):
            side = "GEM" if source == "gem" else "UA"
            self.client[side].append(rec)
            self._apply_side(source, rec)
            items += self._rx_items(side, rec)
        elif source in ("gem_send", "ua_send"):
            side = "GEM" if source == "gem_send" else "UA"
            self.send[side].append(rec)
            if rec.get("outcome") != "sent":
                items += self._mark(side, rec["seq"], {"drop": rec.get("outcome")})
        return items

    def set_scenario(self, scenario: dict[str, Any], finished: bool) -> None:
        """Scenario metadata (name; window + rounds once finished)."""
        self.scenario = scenario
        self.finished = finished
        self.version += 1

    def _apply_side(self, key: str, rec: dict[str, Any]) -> None:
        try:
            APPLIERS[key](self.sides[key], rec)
        except (KeyError, TypeError, ValueError):
            pass

    def _core_items(self, r: dict[str, Any]) -> list[dict[str, Any]]:
        kind, ts = r["kind"], r["ts_ns"]
        out: list[dict[str, Any]] = []
        if kind == "sample":
            self.temps.append([ts, r["value"]])
            del self.temps[:-KEEP_TEMPS]
            out.append({"t": "temp", "ts": ts, "v": r["value"]})
        elif kind == "ec_write":
            self.limits.append([ts, r["value"]])
            out.append({"t": "limit", "ts": ts, "v": r["value"]})
        if kind in COMMAND_KINDS:
            row = {"ts": ts, "seq": r["seq"], "origin": r["origin"], "action": self._action(r),
                   "accepted": COMMAND_KINDS[kind], "reason": (r.get("extra") or {}).get("reason", "")}
            self.feed.append(row)
            del self.feed[:-KEEP_FEED]
            out.append({"t": "cmd", **row})
        elif kind == "state" and r["id"] == "GemCommunicationState":
            self.link = r["value"]
            out.append({"t": "link", "v": r["value"], "ts": ts})
        elif kind in ("alarm_set", "alarm_clear"):
            if kind == "alarm_set":
                self.alarms.append([ts, None])
            elif self.alarms and self.alarms[-1][1] is None:
                self.alarms[-1][1] = ts
            out.append({"t": "alarm", "on": kind == "alarm_set", "ts": ts})
        if kind in EVENT_KINDS:
            name = CEID_NAMES.get(int(r["id"]), str(r["id"])) if kind == "event" else f"ALID {r['id']} {kind[6:].upper()}"
            row = {"seq": r["seq"], "kind": kind, "id": r["id"], "name": name, "ts": ts,
                   "color": self._color(r), "GEM": None, "UA": None}
            self.timeline[r["seq"]] = row
            if len(self.timeline) > KEEP_TIMELINE * 2:
                for s in sorted(self.timeline)[:KEEP_TIMELINE]:
                    del self.timeline[s]
            out.append({"t": "ev", **row})
            for side, mark in self._pending_rx.pop(r["seq"], []):
                out += self._mark(side, r["seq"], mark)
        return out

    def _rx_items(self, side: str, rec: dict[str, Any]) -> list[dict[str, Any]]:
        if rec.get("kind") not in EVENT_KINDS or rec.get("seq") is None:
            return []
        seq = rec["seq"]
        row = self.timeline.get(seq)
        lat = None if row is None else round((rec["ts_ns"] - row["ts"]) / 1e6, 1)
        items = self._mark(side, seq, {"lat": lat, "rx_ts": rec["ts_ns"]})
        items.append({"t": "flow", "side": side, "color": row["color"] if row else "green"})
        return items

    def _mark(self, side: str, seq: int, mark: dict[str, Any]) -> list[dict[str, Any]]:
        row = self.timeline.get(seq)
        if row is None:  # receipt read before its core record: apply when the core record arrives
            self._pending_rx.setdefault(seq, []).append((side, mark))
            return []
        if "lat" in mark and mark["lat"] is None:
            mark = {**mark, "lat": round((mark["rx_ts"] - row["ts"]) / 1e6, 1)}
        if row[side] and "lat" in row[side] and "drop" in mark:
            return []  # received after all; a late "error" outcome does not override a receipt
        row[side] = mark
        out = [{"t": "mark", "seq": seq, "side": side, **mark}]
        if "drop" in mark:
            out.append({"t": "dropflash", "side": side})
        return out

    @staticmethod
    def _action(r: dict[str, Any]) -> str:
        if r["kind"] in ("ec_write", "ec_rejected"):
            return f"EC {r['id']} := {r['value']}"
        return f"{r['id']}" + (f" {r['value']}" if r.get("value") not in (None, "") else "")

    @staticmethod
    def _color(r: dict[str, Any]) -> str:
        if r["kind"] != "event":
            return "amber"
        return "red" if int(r["id"]) == config.CEID_COMMAND_REJECTED else "green"

    # ---- views
    def run_data(self) -> checker.RunData:
        """A checker.RunData over the records seen so far, with the window the checker should use now."""
        scenario = dict(self.scenario)
        if not self.finished:
            # Live / mid-replay: events younger than 2 s may still be in flight - judge them next time.
            scenario["t_end_ns"] = max(0, self.now_ns - LIVE_EDGE_NS)
            if self.audit:
                scenario.setdefault("t_start_ns", self.audit[0]["ts_ns"])
        return checker.RunData(self.run_dir or Path("."), self.audit, self.client, self.send, scenario)

    def invariants(self) -> dict[str, Any]:
        """checker.check_run on everything seen so far."""
        run = self.run_data()
        if not run.audit:
            return {"rows": [], "counters": {}, "overall": "N/A"}
        results = checker.check_run(run)
        view = invariant_view(run, results)
        view["latency"] = {s: checker.latency(run, s) for s in checker.SIDES}
        view["window_end_ns"] = run.window()[1]
        return view

    def columns(self) -> dict[str, Any]:
        """The three columns with per-cell agreement flags (same rules as live_view)."""
        cols: dict[str, Any] = {"rows": list(ROWS), "gem": {}, "core": {}, "ua": {}, "agree": {"gem": {}, "ua": {}}}
        for key in ("gem", "core", "ua"):
            side = self.sides[key]
            side.values["Events received"] = side.events
            cols[key] = dict(side.values)
        for key in ("gem", "ua"):
            for row in ROWS:
                cols["agree"][key][row] = values_agree(row, cols[key][row], cols["core"][row])
        return cols

    def header(self) -> dict[str, Any]:
        """Run id, scenario, equipment state badge."""
        core = self.sides["core"].values
        return {"run_id": self.run_dir.name if self.run_dir else None, "mode": self.mode,
                "scenario": self.scenario.get("scenario"), "description": self.scenario.get("description", ""),
                "control_state": core.get("ControlState"), "processing_state": core.get("ProcessingState"),
                "authority": core.get("Authority"), "link": self.link, "finished": self.finished,
                "now_ns": self.now_ns}

    def snapshot(self) -> dict[str, Any]:
        """Full page state (sent on connect and on run switch)."""
        seqs = sorted(self.timeline)[-KEEP_TIMELINE:]
        return {"header": self.header(), "columns": self.columns(), "feed": self.feed[-KEEP_FEED:],
                "timeline": [self.timeline[s] for s in seqs], "temps": self.temps, "limits": self.limits,
                "alarms": self.alarms, "limit0": config.equipment_constant(config.ECID_TEMP_HIGH_LIMIT).default}


# ====================================================================== sources
def newest_run(base: Path) -> Optional[Path]:
    """runs/LATEST if it points to an existing folder, else the most recently modified run folder."""
    runs = base / config.RUNS_DIR
    try:
        latest = (runs / "LATEST").read_text(encoding="utf-8").strip()
        if latest and (runs / latest).is_dir():
            return runs / latest
    except OSError:
        pass
    dirs = [d for d in runs.glob("*") if d.is_dir() and (d / config.CORE_AUDIT_FILE).exists()]
    return max(dirs, key=lambda d: d.stat().st_mtime) if dirs else None


class LiveSource:
    """Tails the five logs of a run folder (or follows the newest run if no folder was given)."""

    def __init__(self, run_dir: Optional[Path], base: Path) -> None:
        self.fixed = run_dir
        self.base = base
        self.run_dir: Optional[Path] = None
        self.tails: dict[str, JsonlTail] = {}
        self._scenario_mtime = 0.0

    def target(self) -> Optional[Path]:
        """Which folder should be tailed now."""
        if self.fixed is not None:
            return self.fixed if self.fixed.is_dir() else None
        return newest_run(self.base)

    def poll(self) -> tuple[Optional[Path], list[tuple[str, dict[str, Any]]], Optional[dict[str, Any]]]:
        """(run_dir if it changed, new records, scenario.json if it appeared/changed)."""
        target = self.target()
        switched = None
        if target is not None and target != self.run_dir:
            self.run_dir = target
            self.tails = {key: JsonlTail(target / name) for key, name in SOURCES}
            self._scenario_mtime = 0.0
            switched = target
        if self.run_dir is None:
            return None, [], None
        recs = [(key, r) for key, tail in self.tails.items() for r in tail.read_new()]
        scenario = None
        sc = self.run_dir / "scenario.json"
        try:
            mtime = sc.stat().st_mtime
            if mtime != self._scenario_mtime:
                self._scenario_mtime = mtime
                scenario = json.loads(sc.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        return switched, recs, scenario


class ReplaySource:
    """Plays a finished run back from its logs at `speed` x real time."""

    def __init__(self, run_dir: Path, speed: float, loop: bool) -> None:
        self.run_dir = run_dir
        self.speed = max(0.1, speed)
        self.loop = loop
        streams = [[(r.get("ts_ns", 0), i, key, r) for r in checker.load_jsonl(run_dir / name)]
                   for i, (key, name) in enumerate(SOURCES)]
        # heapq.merge keeps each file's own order (arrival order matters for I2) while interleaving by time.
        self.records = [(ts, key, r) for ts, _i, key, r in heapq.merge(*streams, key=lambda x: x[0])]
        try:
            self.scenario = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.scenario = {}
        self._restart()

    def _restart(self) -> None:
        self._scenario_sent = False
        self.pos = 0
        self.t0_data = self.records[0][0] if self.records else 0
        self.t0_wall = time.monotonic()
        self.started = True

    @property
    def done(self) -> bool:
        """All records played."""
        return self.pos >= len(self.records)

    def virtual_now(self) -> int:
        """Data time the replay has reached."""
        return int(self.t0_data + (time.monotonic() - self.t0_wall) * self.speed * 1e9)

    def poll(self) -> tuple[Optional[Path], list[tuple[str, dict[str, Any]]], Optional[dict[str, Any]]]:
        """Records whose data time has been reached."""
        switched = None
        if self.done and self.loop:
            self._restart()
            switched = self.run_dir
        elif self.started and self.pos == 0:
            switched = self.run_dir
        self.started = False
        now = self.virtual_now()
        out = []
        while self.pos < len(self.records) and self.records[self.pos][0] <= now:
            _ts, key, r = self.records[self.pos]
            out.append((key, r))
            self.pos += 1
        hand_over = self.done and not self._scenario_sent  # give scenario.json to the state exactly once
        if hand_over:
            self._scenario_sent = True
        return switched, out, (self.scenario if hand_over else None)


# ====================================================================== broadcast hub + pump
class Hub:
    """Ordered message log for SSE clients (each client follows by message id)."""

    def __init__(self, keep: int = 4000) -> None:
        self.cond = threading.Condition()
        self.messages: list[tuple[int, str, str]] = []
        self.next_id = 1
        self.keep = keep

    def publish(self, event: str, data: Any) -> None:
        """Append one message and wake the SSE handlers."""
        payload = json.dumps(data, default=str)
        with self.cond:
            self.messages.append((self.next_id, event, payload))
            self.next_id += 1
            del self.messages[:-self.keep]
            self.cond.notify_all()

    def since(self, last_id: int, timeout: float) -> list[tuple[int, str, str]]:
        """Messages after last_id (waits up to timeout for new ones)."""
        with self.cond:
            if not self.messages or self.messages[-1][0] <= last_id:
                self.cond.wait(timeout)
            return [m for m in self.messages if m[0] > last_id]


class Dashboard:
    """Owns the source, the state, the hub and the pump thread."""

    def __init__(self, source: Any, mode: str) -> None:
        self.source = source
        self.mode = mode
        self.lock = threading.Lock()
        self.state = RunState(None, mode)
        self.hub = Hub()
        self.stop = threading.Event()
        self._inv_version = -1
        self._last_inv: Optional[dict[str, Any]] = None
        self.thread = threading.Thread(target=self._pump, name="web-view-pump", daemon=True)

    def snapshot(self) -> tuple[int, dict[str, Any]]:
        """(hub id, full state) taken atomically, so a client continues exactly after it."""
        with self.lock:
            with self.hub.cond:
                last = self.hub.next_id - 1
            snap = self.state.snapshot()
            snap["invariants"] = self._last_inv
            snap["speed"] = getattr(self.source, "speed", None)
            return last, snap

    def _pump(self) -> None:
        last_inv = 0.0
        while not self.stop.is_set():
            try:
                self._tick()
                if time.monotonic() - last_inv >= 1.0:
                    last_inv = time.monotonic()
                    self._invariants()
            except Exception as exc:  # noqa: BLE001 - the dashboard must keep running
                self.hub.publish("error", {"message": repr(exc)})
            self.stop.wait(0.2)

    def _tick(self) -> None:
        switched, recs, scenario = self.source.poll()
        with self.lock:
            if switched is not None:
                self.state = RunState(switched, self.mode)
                self._last_inv = None
                self.hub.publish("reset", {"run_id": switched.name})
            if not recs and scenario is None and switched is None:
                if isinstance(self.source, ReplaySource) and not self.source.done:
                    self.state.now_ns = self.source.virtual_now()
                return
            items: list[dict[str, Any]] = []
            for key, rec in recs:
                items += self.state.feed_record(key, rec)
            if isinstance(self.source, ReplaySource):
                self.state.now_ns = max(self.state.now_ns, min(self.source.virtual_now(),
                                                               self.source.records[-1][0] if self.source.records else 0))
            if scenario is not None:
                finished = "t_end_ns" in scenario and (not isinstance(self.source, ReplaySource) or self.source.done)
                self.state.set_scenario(scenario, finished)
            if not self.state.scenario and isinstance(self.source, ReplaySource):
                self.state.scenario = {k: self.source.scenario.get(k) for k in ("scenario", "description")
                                       if k in self.source.scenario}
            self.hub.publish("delta", {"items": items, "header": self.state.header(), "columns": self.state.columns()})

    def _invariants(self) -> None:
        with self.lock:
            if self.state.version == self._inv_version:
                return
            self._inv_version = self.state.version
            inv = self.state.invariants()
            self._last_inv = inv
        self.hub.publish("inv", inv)


# ====================================================================== HTTP
def results_listing(base: Path) -> list[dict[str, str]]:
    """results/summary.md first, then scenario summaries, then the checker self-test."""
    res = base / config.RESULTS_DIR
    names = ["summary.md"] + sorted(p.name for p in res.glob("S*_summary.md")) + ["checker_self_test.md"]
    out = []
    for name in names:
        p = res / name
        if p.exists():
            out.append({"name": name, "text": p.read_text(encoding="utf-8")})
    return out


def make_handler(dash: Dashboard, base: Path) -> type[BaseHTTPRequestHandler]:
    """Request handler bound to one dashboard."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:  # quiet console
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/state":
                _id, snap = dash.snapshot()
                self._send(200, json.dumps(snap, default=str).encode("utf-8"), "application/json")
            elif path == "/api/results":
                self._send(200, json.dumps(results_listing(base)).encode("utf-8"), "application/json")
            elif path == "/events":
                self._sse()
            else:
                self._send(404, b"not found", "text/plain")

        def _sse(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            last, snap = dash.snapshot()
            try:
                self._event("snapshot", json.dumps(snap, default=str))
                idle = time.monotonic()
                while not dash.stop.is_set():
                    msgs = dash.hub.since(last, timeout=1.0)
                    if msgs and msgs[0][0] > last + 1 and last != 0 and len(msgs) >= dash.hub.keep:
                        last, snap = dash.snapshot()  # fell behind the buffer: start over
                        self._event("snapshot", json.dumps(snap, default=str))
                        continue
                    for mid, event, payload in msgs:
                        if event == "reset":
                            last, snap = dash.snapshot()
                            self._event("snapshot", json.dumps(snap, default=str))
                            break
                        self._event(event, payload)
                        last = mid
                    if time.monotonic() - idle > 15:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                        idle = time.monotonic()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return

        def _event(self, event: str, payload: str) -> None:
            self.wfile.write(f"event: {event}\ndata: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()

    return Handler


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="Live web dashboard (read-only, stdlib only)")
    ap.add_argument("--run-dir", default=None, help="runs/<id>; default: follow the newest run")
    ap.add_argument("--replay", default=None, metavar="RUN_DIR", help="replay a finished run instead of tailing")
    ap.add_argument("--speed", type=float, default=5.0, help="replay speed factor (default 5)")
    ap.add_argument("--loop", action="store_true", help="replay: start again at the end")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="open the page in the default browser")
    args = ap.parse_args(argv)
    if args.port in (config.HSMS_PORT, 4840, config.CONTROL_PORT, 5101):
        ap.error("that port belongs to the system under test")
    base = Path.cwd()
    if args.replay:
        rd = checker.resolve_run(args.replay)
        if not (rd / config.CORE_AUDIT_FILE).exists():
            ap.error(f"no run found at {rd}")
        dash = Dashboard(ReplaySource(rd, args.speed, args.loop), mode="replay")
    else:
        rd = checker.resolve_run(args.run_dir) if args.run_dir else None
        dash = Dashboard(LiveSource(rd, base), mode="live")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(dash, base))
    server.daemon_threads = True
    dash.thread.start()
    url = f"http://localhost:{args.port}/"
    what = f"replay of {rd.name} at {args.speed}x" if args.replay else (f"run {rd.name}" if rd else "newest run")
    print(f"web view: {url}  ({what}; read-only; Ctrl+C to stop)", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        dash.stop.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
