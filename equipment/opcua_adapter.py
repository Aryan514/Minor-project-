# equipment/opcua_adapter.py
# The OPC UA "door": an asyncua server exposing the GEM-derived model. It owns no equipment state:
# it mirrors core notifications into variables/events (in seq order, via its own dispatcher queue)
# and turns UA method calls (Start, Stop, SetTempHighLimit) into core commands with origin UA_CLIENT.
# Writes a send-side log (runs/<id>/ua_adapter_send.jsonl) for loss attribution (invariant I6).
# Serves N1 (thin door, every command via core/arbiter) and N2 (UA side of the mapping).
"""OPC UA server adapter (CLAUDE.md section 8.2)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from asyncua import Server, ua
from asyncua.common.event_objects import BaseEvent
from asyncua.server.event_generator import EventGenerator

from equipment import config
from equipment.audit import JsonlWriter
from equipment.config import AuditKind, Origin, SendOutcome
from equipment.core import CommandResult, EquipmentCore
from equipment.dispatcher import Dispatcher, Notification
from equipment.opcua_model import UaModel, build_model

_log = logging.getLogger(__name__)

SUBSCRIBER_NAME = "opcua"


def ns_to_datetime(ts_ns: int) -> datetime:
    """Core timestamp (ns since epoch) -> timezone-aware UTC datetime for SourceTimestamp."""
    return datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc)


def status_code(name: str) -> ua.StatusCode:
    """StatusCode from its name, e.g. 'BadUserAccessDenied' (names come from CommandResult.ua_status)."""
    return ua.StatusCode(getattr(ua.StatusCodes, name))


class OpcUaAdapter:
    """asyncua server door for one EquipmentCore."""

    def __init__(
        self,
        core: EquipmentCore,
        dispatcher: Dispatcher,
        run_dir: Optional[Path],
        endpoint: str = config.OPCUA_ENDPOINT,
    ) -> None:
        """Prepare the adapter (call `await start()` inside the asyncio loop)."""
        self._core = core
        self._dispatcher = dispatcher
        self._endpoint = endpoint
        self._send_log = JsonlWriter(run_dir / config.UA_SEND_LOG_FILE if run_dir else None)
        self._server: Optional[Server] = None
        self._model: Optional[UaModel] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ce_gen: Optional[EventGenerator] = None
        self._alarm_gen: Optional[EventGenerator] = None
        self.alarm_mode = "unset"  # "alarms_and_conditions" or "fallback_event"
        self._baseline_seq = 0

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        """Build the address space, publish the current state, start serving, subscribe to the core."""
        self._loop = asyncio.get_running_loop()
        server = Server()
        await server.init()
        server.set_endpoint(self._endpoint)
        server.set_server_name(config.OPCUA_SERVER_NAME)
        server.set_security_policy([ua.SecurityPolicyType.NoSecurity])  # demo only (limitations.md)
        idx = await server.register_namespace(config.OPCUA_NAMESPACE_URI)
        self._server = server
        self._model = model = await build_model(server, idx)

        # Methods -> core (sync callbacks: asyncua runs them in a thread pool, so the core lock never
        # blocks the event loop).
        server.link_method(model.methods["Start"], self._method_factory("START"))
        server.link_method(model.methods["Stop"], self._method_factory("STOP"))
        server.link_method(model.methods["SetTempHighLimit"], self._set_limit_method)
        await model.variables["TempHighLimit"].set_read_only()  # writes only via SetTempHighLimit (D10)

        self._ce_gen = await server.get_event_generator(model.collection_event_type, emitting_node=model.tool)
        await self._init_alarm_generator()

        # Subscribe first, then take the snapshot: anything older than the snapshot is not re-applied.
        self._dispatcher.subscribe(SUBSCRIBER_NAME, self._on_notification)
        await self._publish_snapshot()
        await server.start()
        _log.info("OPC UA door listening on %s (alarm mode: %s)", self._endpoint, self.alarm_mode)

    async def stop(self) -> None:
        """Stop serving."""
        if self._server is not None:
            try:
                await self._server.stop()
            except Exception:  # noqa: BLE001
                _log.exception("error while stopping OPC UA server")
        self._send_log.close()

    async def _init_alarm_generator(self) -> None:
        """Prefer an OffNormalAlarmType-derived condition event; fall back to GemAlarmEventType."""
        assert self._server is not None and self._model is not None
        try:
            gen = await self._server.get_event_generator(self._model.alarm_event_type, emitting_node=self._model.tool)
            ev = gen.event
            for name in ("ActiveState", "ActiveState/Id", "Retain", "ConditionName", "NodeId", "ALID", "EventSeq"):
                if not hasattr(ev, name):
                    raise AttributeError(f"A&C event lacks field {name}")
            self._alarm_gen = gen
            self.alarm_mode = "alarms_and_conditions"
        except Exception as exc:  # noqa: BLE001 - documented fallback (CLAUDE.md 8.1)
            _log.warning("A&C alarm event unavailable (%s); using GemAlarmEventType fallback", exc)
            self._alarm_gen = await self._server.get_event_generator(
                self._model.alarm_fallback_event_type, emitting_node=self._model.tool
            )
            self.alarm_mode = "fallback_event"

    async def _publish_snapshot(self) -> None:
        """Write the current core state into the variables (initial values)."""
        snap = self._core.snapshot()
        self._baseline_seq = snap["last_seq"]
        ts = time.time_ns()
        await self._write("ControlState", snap["control_state"], ua.VariantType.String, ts)
        await self._write("ControlStateId", snap["control_state_id"], ua.VariantType.Byte, ts)
        await self._write("ProcessingState", snap["processing_state"], ua.VariantType.String, ts)
        await self._write("ProcessingStateId", snap["processing_state_id"], ua.VariantType.Byte, ts)
        await self._write("Authority", snap["authority"], ua.VariantType.String, ts)
        await self._write("CommunicationState", snap["gem_link"], ua.VariantType.String, ts)
        await self._write("LastEventSeq", snap["last_event_seq"], ua.VariantType.UInt32, ts)
        await self._write("Temperature", snap["temp"], ua.VariantType.Double, ts)
        await self._write("TempHighLimit", snap["temp_high_limit"], ua.VariantType.Double, ts)
        await self._write("AlarmActive", bool(snap["alarms_active"]), ua.VariantType.Boolean, ts)

    # ------------------------------------------------------------------ methods (commands -> core)
    def _method_factory(self, rcmd: str) -> Callable[..., ua.StatusCode]:
        def method(parent: ua.NodeId, *args: Any) -> ua.StatusCode:
            del parent, args
            result = self._core.submit_command(Origin.UA_CLIENT, rcmd)
            return self._result_status(result)

        return method

    def _set_limit_method(self, parent: ua.NodeId, *args: Any) -> ua.StatusCode:
        del parent
        if not args:
            return ua.StatusCode(ua.StatusCodes.BadArgumentsMissing)
        value = args[0].Value if isinstance(args[0], ua.Variant) else args[0]
        result = self._core.submit_ec_write(Origin.UA_CLIENT, config.ECID_TEMP_HIGH_LIMIT, value)
        return self._result_status(result)

    @staticmethod
    def _result_status(result: CommandResult) -> ua.StatusCode:
        return status_code(result.ua_status)

    # ------------------------------------------------------------------ notifications (core -> UA)
    def _on_notification(self, n: Notification) -> None:
        """Dispatcher worker thread: hop into the asyncio loop and wait, preserving seq order."""
        if self._loop is None or self._loop.is_closed():
            return
        fut = asyncio.run_coroutine_threadsafe(self._handle(n), self._loop)
        try:
            fut.result(timeout=10)
        except Exception:  # noqa: BLE001 - rule 10: never let the door crash the core
            _log.exception("OPC UA door failed on seq %s", n.seq)
            if n.kind in (AuditKind.EVENT.value, AuditKind.ALARM_SET.value, AuditKind.ALARM_CLEAR.value):
                self._log_send(n, SendOutcome.ERROR)

    async def _handle(self, n: Notification) -> None:
        stale = n.seq <= self._baseline_seq  # already contained in the initial snapshot
        kind = n.kind
        if kind == AuditKind.SAMPLE.value and not stale:
            await self._write("Temperature", n.value, ua.VariantType.Double, n.ts_ns)
        elif kind == AuditKind.STATE.value and not stale:
            await self._apply_state(n)
        elif kind == AuditKind.AUTHORITY.value and not stale:
            await self._write("Authority", n.value, ua.VariantType.String, n.ts_ns)
        elif kind == AuditKind.EC_WRITE.value and not stale:
            await self._write("TempHighLimit", n.value, ua.VariantType.Double, n.ts_ns)
        elif kind == AuditKind.EVENT.value:
            await self._fire_collection_event(n)
        elif kind in (AuditKind.ALARM_SET.value, AuditKind.ALARM_CLEAR.value):
            await self._fire_alarm(n)

    async def _apply_state(self, n: Notification) -> None:
        if n.id == "ControlState":
            await self._write("ControlState", n.value, ua.VariantType.String, n.ts_ns)
            await self._write("ControlStateId", n.extra["id"], ua.VariantType.Byte, n.ts_ns)
        elif n.id == "ProcessingState":
            await self._write("ProcessingState", n.value, ua.VariantType.String, n.ts_ns)
            await self._write("ProcessingStateId", n.extra["id"], ua.VariantType.Byte, n.ts_ns)
        elif n.id == "GemCommunicationState":
            await self._write("CommunicationState", n.value, ua.VariantType.String, n.ts_ns)

    async def _fire_collection_event(self, n: Notification) -> None:
        assert self._ce_gen is not None
        if not self._has_event_subscriber():
            self._log_send(n, SendOutcome.DROPPED_NO_LINK)
            await self._write("LastEventSeq", n.seq, ua.VariantType.UInt32, n.ts_ns)
            return
        ev = self._ce_gen.event
        ev.CEID = ua.Variant(int(n.id), ua.VariantType.UInt32)
        ev.EventSeq = ua.Variant(int(n.value.get(config.DVID_EVENT_SEQ, n.seq)), ua.VariantType.UInt32)
        ev.Origin = ua.Variant(n.origin, ua.VariantType.String)
        ev.Payload = ua.Variant(json.dumps({str(k): v for k, v in n.value.items()}), ua.VariantType.String)
        ev.Severity = 100
        await self._ce_gen.trigger(time_attr=ns_to_datetime(n.ts_ns), message=n.extra.get("name", str(n.id)))
        self._log_send(n, SendOutcome.SENT)
        await self._write("LastEventSeq", n.seq, ua.VariantType.UInt32, n.ts_ns)

    async def _fire_alarm(self, n: Notification) -> None:
        assert self._alarm_gen is not None and self._model is not None
        active = n.kind == AuditKind.ALARM_SET.value
        await self._write("AlarmActive", active, ua.VariantType.Boolean, n.ts_ns)
        if not self._has_event_subscriber():
            self._log_send(n, SendOutcome.DROPPED_NO_LINK)
            await self._write("LastEventSeq", n.seq, ua.VariantType.UInt32, n.ts_ns)
            return
        ev: BaseEvent = self._alarm_gen.event
        text = f"{n.extra.get('text', '')} (T={float(n.value):.2f} degC, limit={n.extra.get('limit')})"
        ev.SourceNode = self._model.alarm_node.nodeid
        ev.SourceName = config.ALARMS[0].name
        ev.Severity = config.ALARM_SEVERITY_UA
        ev.ALID = ua.Variant(int(n.id), ua.VariantType.UInt32)
        ev.EventSeq = ua.Variant(n.seq, ua.VariantType.UInt32)
        if self.alarm_mode == "alarms_and_conditions":
            ev.ConditionName = config.ALARMS[0].name
            ev.NodeId = self._model.alarm_node.nodeid  # ConditionId, used by ConditionRefresh
            ev.Retain = active  # retained while active -> replayed on ConditionRefresh
            setattr(ev, "ActiveState", ua.LocalizedText("Active" if active else "Inactive"))
            setattr(ev, "ActiveState/Id", active)
            if hasattr(ev, "EnabledState/Id"):
                setattr(ev, "EnabledState", ua.LocalizedText("Enabled"))
                setattr(ev, "EnabledState/Id", True)
        else:
            ev.Active = active
            ev.Text = text
        await self._alarm_gen.trigger(time_attr=ns_to_datetime(n.ts_ns), message=text)
        self._log_send(n, SendOutcome.SENT)
        await self._write("LastEventSeq", n.seq, ua.VariantType.UInt32, n.ts_ns)

    # ------------------------------------------------------------------ helpers
    async def _write(self, key: str, value: Any, vtype: ua.VariantType, ts_ns: int) -> None:
        """Write a variable with SourceTimestamp = core timestamp."""
        assert self._model is not None
        dv = ua.DataValue(
            Value=ua.Variant(value, vtype),
            SourceTimestamp=ns_to_datetime(ts_ns),
            ServerTimestamp=datetime.now(timezone.utc),
        )
        await self._model.variables[key].write_value(dv)

    def _has_event_subscriber(self) -> bool:
        """True if at least one client monitors events on Chamber1Tool (else the event reaches nobody).

        Uses asyncua internals (SubscriptionService.subscriptions / MonitoredItemService._monitored_events);
        see docs/library_notes.md B.8.
        """
        assert self._server is not None and self._model is not None
        try:
            subs = self._server.iserver.subscription_service.subscriptions
            tool = self._model.tool.nodeid
            return any(tool in sub.monitored_item_srv._monitored_events for sub in subs.values())  # noqa: SLF001
        except Exception:  # noqa: BLE001 - if internals change, assume someone listens
            return True

    def _log_send(self, n: Notification, outcome: SendOutcome) -> None:
        self._send_log.write({"seq": n.seq, "ts_ns": time.time_ns(), "kind": n.kind, "id": n.id,
                              "outcome": outcome.value})
