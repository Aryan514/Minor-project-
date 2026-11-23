# clients/ua_client.py
# Scripted OPC UA client (independent process). --listen subscribes to every mapped variable and to
# the events of Chamber1Tool and writes each notification to runs/<id>/ua_client.jsonl as
# {ts_ns, kind, id, seq, data}; --browse prints the self-describing model with GEM IDs;
# --start / --stop / --set-limit X call the methods and log the returned StatusCode.
# Serves N3 (receive-side log of the UA interface) and N2 (shows the model is self-describing).
"""OPC UA test client (CLAUDE.md section 10)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Optional

from asyncua import Client, Node, ua

from equipment import config
from equipment.audit import JsonlWriter, latest_run_id, run_dir_for

# Variables subscribed in --listen mode (keys match equipment.opcua_model.VAR_PATHS).
LISTEN_VARS = {
    "ControlState": "GemInterface.ControlState",
    "ControlStateId": "GemInterface.ControlStateId",
    "Authority": "GemInterface.Authority",
    "CommunicationState": "GemInterface.CommunicationState",
    "LastEventSeq": "GemInterface.LastEventSeq",
    "ProcessingState": "ProcessingState",
    "ProcessingStateId": "ProcessingStateId",
    "Temperature": "Chamber1.Temperature",
    "TempHighLimit": "EquipmentConstants.TempHighLimit",
    "AlarmActive": "Alarms.ChamberOverTemp.Active",
}


def _dt_ns(dt: Any) -> Optional[int]:
    """datetime -> ns since epoch (None-safe)."""
    return int(dt.timestamp() * 1e9) if dt is not None else None


class _Handler:
    """Subscription callbacks: write every notification to the JSONL receive log."""

    def __init__(self, writer: JsonlWriter, names: dict[ua.NodeId, str], type_kinds: dict[ua.NodeId, str],
                 echo: bool) -> None:
        self._w = writer
        self._names = names
        self._type_kinds = type_kinds
        self._echo = echo

    def _emit(self, rec: dict[str, Any]) -> None:
        self._w.write(rec)
        if self._echo:
            print(json.dumps(rec, default=str), flush=True)

    def datachange_notification(self, node: Node, val: Any, data: Any) -> None:
        """A subscribed variable changed."""
        dv = data.monitored_item.Value
        self._emit({"ts_ns": time.time_ns(), "kind": "data", "id": self._names.get(node.nodeid, str(node.nodeid)),
                    "seq": None, "data": {"value": val, "source_ts_ns": _dt_ns(dv.SourceTimestamp)}})

    def event_notification(self, event: Any) -> None:
        """An event from Chamber1Tool arrived."""
        now = time.time_ns()
        kind = self._type_kinds.get(event.EventType, "event_other")
        if kind == "event":
            payload = json.loads(event.Payload) if getattr(event, "Payload", None) else {}
            self._emit({"ts_ns": now, "kind": "event", "id": event.CEID, "seq": event.EventSeq,
                        "data": {"origin": event.Origin, "payload": payload, "time_ns": _dt_ns(event.Time)}})
        elif kind == "alarm":
            active = getattr(event, "ActiveState/Id", None)
            if active is None:
                active = getattr(event, "Active", None)
            self._emit({"ts_ns": now, "kind": "alarm_set" if active else "alarm_clear", "id": event.ALID,
                        "seq": event.EventSeq, "data": {"active": active, "message": str(event.Message.Text),
                                                         "severity": event.Severity, "time_ns": _dt_ns(event.Time)}})

    def status_change_notification(self, status: Any) -> None:
        """Subscription status change (e.g. server going away)."""
        self._emit({"ts_ns": time.time_ns(), "kind": "status", "id": None, "seq": None, "data": str(status)})


async def _tool(client: Client) -> tuple[Node, int]:
    idx = await client.get_namespace_index(config.OPCUA_NAMESPACE_URI)
    return client.get_node(ua.NodeId(config.TOOL_NAME, idx)), idx


async def _event_types(client: Client, idx: int) -> dict[str, Node]:
    """Find our event types by browsing the standard type tree (no hard-coded numeric ids)."""
    base = client.get_node(ua.ObjectIds.BaseEventType)
    off_normal = client.get_node(ua.ObjectIds.OffNormalAlarmType)
    return {
        "event": await base.get_child(f"{idx}:GemCollectionEventType"),
        "alarm": await off_normal.get_child(f"{idx}:GemOffNormalAlarmType"),
        "alarm_fallback": await base.get_child(f"{idx}:GemAlarmEventType"),
    }


async def listen(url: str, run_id: str, duration: Optional[float], echo: bool) -> None:
    """Subscribe to everything and log until `duration` elapses (or forever)."""
    writer = JsonlWriter(run_dir_for(run_id) / config.UA_CLIENT_LOG_FILE)
    # Session markers for the checker: "connecting" opens a session, "listening" = subscriptions active.
    writer.write({"ts_ns": time.time_ns(), "kind": "connecting", "id": None, "seq": None, "data": os.getpid()})
    async with Client(url) as client:
        tool, idx = await _tool(client)
        names: dict[ua.NodeId, str] = {}
        nodes: list[Node] = []
        for key, path in LISTEN_VARS.items():
            node = client.get_node(ua.NodeId(f"{config.TOOL_NAME}.{path}", idx))
            names[node.nodeid] = key
            nodes.append(node)
        etypes = await _event_types(client, idx)
        type_kinds = {etypes["event"].nodeid: "event", etypes["alarm"].nodeid: "alarm",
                      etypes["alarm_fallback"].nodeid: "alarm"}
        handler = _Handler(writer, names, type_kinds, echo)
        sub = await client.create_subscription(50, handler)  # 50 ms publishing interval
        await sub.subscribe_data_change(nodes, queuesize=100)
        await sub.subscribe_events(tool, list(etypes.values()), queuesize=1000)
        writer.write({"ts_ns": time.time_ns(), "kind": "listening", "id": None, "seq": None, "data": url})
        print(f"UA client listening (run_id={run_id})", flush=True)
        try:
            if duration is None:
                while True:
                    await asyncio.sleep(3600)
            else:
                await asyncio.sleep(duration)
        finally:
            writer.write({"ts_ns": time.time_ns(), "kind": "stopped", "id": None, "seq": None, "data": None})
            writer.close()


async def call(url: str, run_id: str, action: str, value: Optional[float] = None) -> str:
    """Call Start / Stop / SetTempHighLimit once; return and log the StatusCode name."""
    writer = JsonlWriter(run_dir_for(run_id) / "ua_client_actions.jsonl")
    async with Client(url) as client:
        tool, idx = await _tool(client)
        method = {"start": "Start", "stop": "Stop", "set-limit": "SetTempHighLimit"}[action]
        args = [ua.Variant(float(value), ua.VariantType.Double)] if action == "set-limit" else []
        t0 = time.time_ns()
        try:
            await tool.call_method(f"{idx}:{method}", *args)
            status = "Good"
        except ua.UaStatusCodeError as exc:
            status = _status_name(exc.code)
        writer.write({"ts_ns": time.time_ns(), "kind": "reply", "id": method, "seq": None,
                      "data": {"status": status, "value": value, "sent_ns": t0}})
        writer.close()
        return status


def _status_name(code: int) -> str:
    """Numeric StatusCode -> its name (e.g. 0x801F0000 -> 'BadUserAccessDenied')."""
    for name, val in vars(ua.StatusCodes).items():
        if isinstance(val, int) and val == code:
            return name
    return hex(code)


async def browse(url: str) -> None:
    """Print the Chamber1Tool tree with type definitions and GEM IDs (self-description demo)."""
    async with Client(url) as client:
        tool, idx = await _tool(client)

        async def walk(node: Node, depth: int) -> None:
            for child in await node.get_children():
                name = (await child.read_browse_name()).Name
                if name in ("GemId", "GemKind", "GemFormat"):
                    continue  # shown inline on the parent
                ncls = await child.read_node_class()
                line = "  " * depth + f"{name} [{ncls.name}]"
                if ncls == ua.NodeClass.Variable:
                    line += f" = {await child.read_value()!r}"
                    gem = {}
                    for prop in ("GemId", "GemKind", "GemFormat"):
                        try:
                            gem[prop] = await (await child.get_child(f"{idx}:{prop}")).read_value()
                        except ua.UaStatusCodeError:
                            pass
                    if gem:
                        line += f"   <-> GEM {gem['GemKind']} {gem['GemId']} ({gem['GemFormat']})"
                if ncls in (ua.NodeClass.Object, ua.NodeClass.Variable):
                    tdef = await child.read_type_definition()
                    if tdef is not None and tdef.NamespaceIndex == idx:
                        line += f"   type={(await client.get_node(tdef).read_browse_name()).Name}"
                print(line)
                if ncls == ua.NodeClass.Object or name in ("Temperature", "TempHighLimit"):
                    await walk(child, depth + 1)

        tdef = await tool.read_type_definition()
        print(f"{config.TOOL_NAME} [Object] type={(await client.get_node(tdef).read_browse_name()).Name}  ns={idx} "
              f"({config.OPCUA_NAMESPACE_URI})")
        await walk(tool, 1)
        etypes = await _event_types(client, idx)
        print("Event types:")
        for key, node in etypes.items():
            fields = [(await p.read_browse_name()).Name for p in await node.get_properties()]
            print(f"  {(await node.read_browse_name()).Name}: {', '.join(fields)}")


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    p = argparse.ArgumentParser(description="Scripted OPC UA client for Chamber1Tool")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--listen", action="store_true")
    g.add_argument("--browse", action="store_true")
    g.add_argument("--start", action="store_true")
    g.add_argument("--stop", action="store_true")
    g.add_argument("--set-limit", type=float, metavar="X")
    p.add_argument("--url", default=config.OPCUA_CLIENT_ENDPOINT)
    p.add_argument("--run-id", default=None, help="default: runs/LATEST")
    p.add_argument("--duration", type=float, default=None, help="--listen: seconds (default forever)")
    p.add_argument("--quiet", action="store_true", help="--listen: do not echo records")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    run_id = args.run_id or latest_run_id() or "manual"
    try:
        if args.browse:
            asyncio.run(browse(args.url))
        elif args.listen:
            asyncio.run(listen(args.url, run_id, args.duration, echo=not args.quiet))
        else:
            action = "start" if args.start else "stop" if args.stop else "set-limit"
            status = asyncio.run(call(args.url, run_id, action, args.set_limit))
            print(status)
            return 0 if status == "Good" else 2
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
