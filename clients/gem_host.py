# clients/gem_host.py
# Scripted GEM host (independent process, active HSMS to localhost:5000). --listen establishes
# communication, defines/links/enables a report for every CEID, enables alarms and logs each S6F11/S5F1
# to runs/<id>/gem_host.jsonl as {ts_ns, kind, id, seq, data}. One-shots --start/--stop/--set-limit/--status
# send S2F41/S2F15/S1F3 and log the reply code; if a listener is running they are relayed through it,
# because the equipment accepts only ONE HSMS session (docs/decisions.md D15).
# Serves N3 (receive-side log of the GEM interface).
"""Scripted SECS/GEM host (CLAUDE.md section 10)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import socket
import socketserver
import sys
import threading
import time
from typing import Any, Optional

import secsgem.common
import secsgem.gem
import secsgem.hsms

from equipment import config
from equipment.audit import JsonlWriter, latest_run_id, run_dir_for

RELAY_HOST = "127.0.0.1"
RELAY_PORT = 5101  # local relay into the listener's HSMS session (D15)
_SEQ_RE = re.compile(r"seq=(\d+)")


def _plain(value: Any) -> Any:
    """secsgem variable / list -> plain Python (JSON-friendly)."""
    if hasattr(value, "get"):
        value = value.get()
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, bytes):
        return value.hex()
    return value


class _HostHandler(secsgem.gem.GemHostHandler):
    """GemHostHandler whose S6F11 decoding never fails.

    The library looks up `report_subscriptions[rptid]` and raises KeyError (replying S6F0) for a report this
    process did not define itself. That happens after a host restart: the equipment still has the reports
    of the previous host session enabled and sends them before the new session has re-defined them.
    We fall back to our own fixed scheme (RPTID == CEID, VIDs from config.py) so every event is logged.
    """

    def _on_s06f11(self, handler: Any, message: Any) -> Any:
        del handler
        function = self.settings.streams_functions.decode(message)
        for report in function.RPT:
            rptid = report.RPTID.get()
            vids = self.report_subscriptions.get(rptid)
            if vids is None:
                try:
                    vids = list(config.collection_event(int(rptid)).report_vids)
                except (KeyError, ValueError):
                    vids = []
            values = report.V.get()
            if len(vids) != len(values):  # unknown layout: keep the values, mark the ids as positional
                vids = [f"pos{i}" for i in range(len(values))]
            self.events.fire("collection_event_received", {
                "ceid": function.CEID, "rptid": report.RPTID,
                "values": [{"dvid": vid, "value": val} for vid, val in zip(vids, values)],
                "handler": self.protocol, "peer": self})
        return self.stream_function(6, 12)(0)


class GemHost:
    """Thin wrapper around secsgem's GemHostHandler."""

    def __init__(self, host: str = config.HSMS_HOST_CONNECT_ADDRESS, port: int = config.HSMS_PORT) -> None:
        """Create the handler (call connect())."""
        settings = secsgem.hsms.HsmsSettings(
            address=host, port=port,
            connect_mode=secsgem.hsms.HsmsConnectMode.ACTIVE,
            device_type=secsgem.common.DeviceType.HOST,
            session_id=config.HSMS_SESSION_ID,
        )
        self.handler = _HostHandler(settings)
        self._lock = threading.Lock()  # one transaction at a time from this process

    def connect(self, timeout: float = 20.0) -> None:
        """Open HSMS and wait for GEM COMMUNICATING (S1F13/F14).

        On failure the handler is disabled before raising: secsgem's active-connect thread is not a daemon
        and would otherwise keep the process alive, retrying (and later grabbing the single HSMS session).
        """
        self.handler.enable()
        if not self.handler.waitfor_communicating(timeout):
            self.handler.disable()
            raise TimeoutError("GEM communication not established (is another GEM host connected?)")

    def close(self) -> None:
        """Close HSMS (safe to call twice)."""
        try:
            self.handler.disable()
        except Exception:  # noqa: BLE001 - already disabled
            pass

    def setup_reports(self) -> None:
        """Delete old reports, then define/link/enable one report per CEID (RPTID = CEID); enable alarms."""
        with self._lock:
            self.handler.clear_collection_events()
            for ce in config.COLLECTION_EVENTS:
                self.handler.subscribe_collection_event(ce.ceid, list(ce.report_vids), report_id=ce.ceid)
            for al in config.ALARMS:
                self.handler.enable_alarm(al.alid)

    def define_report(self, ceid: int, vids: list[int]) -> dict[str, Any]:
        """Replace the report of one CEID (S2F37 off, S2F35 unlink, S2F33 delete + define, S2F35, S2F37 on)."""
        h = self.handler
        with self._lock:
            h.send_and_waitfor_response(h.stream_function(2, 37)({"CEED": False, "CEID": [ceid]}))
            h.send_and_waitfor_response(h.stream_function(2, 35)({"DATAID": 0, "DATA": [{"CEID": ceid, "RPTID": []}]}))
            h.send_and_waitfor_response(h.stream_function(2, 33)({"DATAID": 0, "DATA": [{"RPTID": ceid, "VID": []}]}))
            h.subscribe_collection_event(ceid, vids, report_id=ceid)  # S2F33 + S2F35 + S2F37
        return {"action": "set-report", "ceid": ceid, "vids": vids, "code": 0}

    def action(self, name: str, value: Optional[float] = None, **extra: Any) -> dict[str, Any]:
        """Run one host action and return {'action', 'code', ...}."""
        if name == "set-report":
            return self.define_report(int(extra["ceid"]), [int(v) for v in extra["vids"]])
        with self._lock:
            if name in ("start", "stop"):
                reply = self.handler.send_remote_command(name.upper(), [])
                return {"action": name, "code": int(reply.HCACK.get()), "code_name": "HCACK"}
            if name == "set-limit":
                s2f16 = self.handler.send_and_waitfor_response(self.handler.stream_function(2, 15)(
                    [{"ECID": config.ECID_TEMP_HIGH_LIMIT, "ECV": secsgem.secs.variables.F4(float(value))}]))
                eac = self.handler.settings.streams_functions.decode(s2f16).get()
                return {"action": name, "value": value, "code": int(eac), "code_name": "EAC"}
            if name == "status":
                svids = [sv.svid for sv in config.STATUS_VARIABLES]
                values = self.handler.request_svs(svids)  # S1F3
                result = {sv.name: _plain(v) for sv, v in zip(config.STATUS_VARIABLES, values)}
                ecs = self.handler.request_ecs([ec.ecid for ec in config.EQUIPMENT_CONSTANTS])  # S2F13
                result.update({ec.name: _plain(v) for ec, v in zip(config.EQUIPMENT_CONSTANTS, ecs)})
                return {"action": name, "code": 0, "values": result}
            raise ValueError(f"unknown action {name}")


# ---------------------------------------------------------------------- listen mode
def listen(run_id: str, duration: Optional[float], echo: bool) -> None:
    """Connect, set up reports, log every S6F11 / S5F1 until duration elapses (or forever)."""
    writer = JsonlWriter(run_dir_for(run_id) / config.GEM_HOST_LOG_FILE)
    host = GemHost()

    def emit(rec: dict[str, Any]) -> None:
        writer.write(rec)
        if echo:
            print(json.dumps(rec, default=str), flush=True)

    # Each S6F11 report: RPTID == CEID (we defined it so), values in our VID order.
    def on_event(data: dict[str, Any]) -> None:
        now = time.time_ns()
        values = {str(v["dvid"]): _plain(v["value"]) for v in data["values"]}
        emit({"ts_ns": now, "kind": "event", "id": int(_plain(data["ceid"])),
              "seq": values.get(str(config.DVID_EVENT_SEQ)), "data": values})

    def on_alarm(data: dict[str, Any]) -> None:
        now = time.time_ns()
        alcd = _plain(data["code"])
        alcd = alcd[0] if isinstance(alcd, list) else alcd
        alcd = int.from_bytes(bytes.fromhex(alcd), "big") if isinstance(alcd, str) else int(alcd)
        text = str(_plain(data["text"]))
        m = _SEQ_RE.search(text)
        emit({"ts_ns": now, "kind": "alarm_set" if alcd & 0x80 else "alarm_clear", "id": int(_plain(data["alid"])),
              "seq": int(m.group(1)) if m else None, "data": {"alcd": alcd, "text": text}})

    host.handler.events.collection_event_received += on_event
    host.handler.events.alarm_received += on_alarm
    relay: Optional[socketserver.ThreadingTCPServer] = None
    # Session markers for the checker: "connecting" opens a session, "listening" = reports active.
    emit({"ts_ns": time.time_ns(), "kind": "connecting", "id": None, "seq": None, "data": os.getpid()})
    try:
        host.connect()
        host.setup_reports()
        emit({"ts_ns": time.time_ns(), "kind": "listening", "id": None, "seq": None, "data": "reports defined"})
        # GEM is event-driven: read the current SVs once (S1F3) so the host knows the starting state.
        snapshot = host.action("status")
        emit({"ts_ns": time.time_ns(), "kind": "status", "id": None,
              "seq": snapshot["values"].get("LastEventSeq"), "data": snapshot["values"]})
        relay = _start_relay(host, run_id)
        print(f"GEM host listening (run_id={run_id})", flush=True)
        end = None if duration is None else time.monotonic() + duration
        while end is None or time.monotonic() < end:
            time.sleep(0.2)
    finally:
        if relay is not None:
            relay.shutdown()
            relay.server_close()
        host.close()
        emit({"ts_ns": time.time_ns(), "kind": "stopped", "id": None, "seq": None, "data": None})
        writer.close()


class _RelayHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        req = json.loads(self.rfile.readline().decode("utf-8"))
        server: Any = self.server
        try:
            result = server.host.action(req["action"], req.get("value"), **req.get("extra", {}))
        except Exception as exc:  # noqa: BLE001
            result = {"action": req.get("action"), "error": str(exc)}
        self.wfile.write((json.dumps(result, default=str) + "\n").encode("utf-8"))


def _start_relay(host: GemHost, run_id: str) -> socketserver.ThreadingTCPServer:
    server = socketserver.ThreadingTCPServer((RELAY_HOST, RELAY_PORT), _RelayHandler)
    server.daemon_threads = True
    server.host = host  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, name="gem-relay", daemon=True).start()
    return server


# ---------------------------------------------------------------------- one-shot mode
def one_shot(run_id: str, action: str, value: Optional[float] = None) -> dict[str, Any]:
    """Run one action through the listener's session if one is running, else via a fresh HSMS session."""
    t0 = time.time_ns()
    try:
        with socket.create_connection((RELAY_HOST, RELAY_PORT), timeout=1.0) as sock:
            sock.settimeout(60)
            sock.sendall((json.dumps({"action": action, "value": value}) + "\n").encode("utf-8"))
            result = json.loads(sock.makefile("r", encoding="utf-8").readline())
            result["via"] = "listener"
    except (ConnectionRefusedError, socket.timeout, OSError):
        host = GemHost()
        try:
            host.connect()
            result = host.action(action, value)
            result["via"] = "own_session"
        finally:
            host.close()
    writer = JsonlWriter(run_dir_for(run_id) / "gem_host_actions.jsonl")
    writer.write({"ts_ns": time.time_ns(), "kind": "reply", "id": action, "seq": None,
                  "data": {**result, "sent_ns": t0}})
    writer.close()
    return result


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    p = argparse.ArgumentParser(description="Scripted SECS/GEM host for Chamber1Tool")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--listen", action="store_true")
    g.add_argument("--start", action="store_true")
    g.add_argument("--stop", action="store_true")
    g.add_argument("--set-limit", type=float, metavar="X")
    g.add_argument("--status", action="store_true", help="S1F3 read of SVIDs 1-5")
    p.add_argument("--run-id", default=None, help="default: runs/LATEST")
    p.add_argument("--duration", type=float, default=None)
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    run_id = args.run_id or latest_run_id() or "manual"
    try:
        if args.listen:
            listen(run_id, args.duration, echo=not args.quiet)
            return 0
        action = "start" if args.start else "stop" if args.stop else "status" if args.status else "set-limit"
        result = one_shot(run_id, action, args.set_limit)
        print(json.dumps(result, default=str))
        return 0 if result.get("code") == 0 else 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
