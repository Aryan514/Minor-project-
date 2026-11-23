# equipment/gem_adapter.py
# The SECS/GEM "door": a secsgem GemEquipmentHandler (passive HSMS, port 5000) that owns no equipment
# state. Reads (S1F3, S2F13) come from the core; commands (S2F41, S2F15, S1F15/F17) go to the core and
# its arbiter; events/alarms come from the dispatcher and are sent as S6F11/S5F1 on ONE worker thread in
# seq order, each outcome written to runs/<id>/gem_adapter_send.jsonl (sent / dropped_no_link / ...).
# Serves N1 (thin door, no bypass: see docs/library_overrides.md) and N2 (GEM side of the mapping).
"""SECS/GEM equipment adapter (CLAUDE.md section 7)."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

import secsgem.common
import secsgem.gem
import secsgem.hsms
import secsgem.secs
from secsgem.secs.variables import F4, U1, U4, Base, String

from equipment import config
from equipment.audit import JsonlWriter
from equipment.config import AuditKind, ControlState, Origin, SendOutcome
from equipment.core import EquipmentCore
from equipment.dispatcher import Dispatcher, Notification

_log = logging.getLogger(__name__)

SUBSCRIBER_NAME = "gem"
ALCD_SET_BIT = 0x80  # SEMI E5 ALCD bit 8 = alarm set
ALCD_CATEGORY = 4  # "parameter control error" category for an over-temperature alarm

_FORMATS: dict[str, type[Base]] = {"F4": F4, "U1": U1, "U4": U4, "A": String}


def _vid_format(vid: int) -> str:
    """SECS-II format code of any variable id (SVID, DVID or ECID) from config."""
    for sv in config.STATUS_VARIABLES:
        if sv.svid == vid:
            return sv.gem_format
    for dv in config.DATA_VARIABLES:
        if dv.dvid == vid:
            return dv.gem_format
    return config.equipment_constant(vid).gem_format


def encode(vid: int, value: Any) -> Base:
    """Python value -> typed SECS-II variable for this VID."""
    fmt = _vid_format(vid)
    if fmt == "A":
        return String("" if value is None else str(value))
    if fmt == "F4":
        return F4(float(value))
    return _FORMATS[fmt](int(value))


class _ServerConnection(secsgem.common.TcpServerConnection):
    """Passive TCP connection with two robustness fixes (library_overrides.md O9).

    1. After accepting a client, secsgem 0.3.0 calls shutdown() on the LISTENING socket, then close().
       On Windows shutdown() on a listening socket raises WinError 10057, so close() is never reached:
       the accept thread dies with a traceback and the listening socket leaks.
    2. disable() closes the listening socket and then waits until the thread clears
       `_stop_server_thread`. The library's select() error path then reads an unassigned variable
       (UnboundLocalError), the thread dies without clearing the flag, and disable() waits forever:
       the equipment process cannot shut down.
    We run the library's own thread function unchanged and only guarantee the cleanup it skips.
    """

    def _TcpServerConnection__server_thread(self) -> None:  # noqa: N802 - overrides a name-mangled method
        try:
            secsgem.common.TcpServerConnection._TcpServerConnection__server_thread(self)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - see class docstring; both cases end the accept thread anyway
            _log.debug("HSMS accept thread ended with an exception (expected on Windows / disable)", exc_info=True)
        finally:
            if self._server_sock is not None:
                try:
                    self._server_sock.close()
                except OSError:
                    pass
            self._stop_server_thread = False  # disable() waits for this flag


class _HsmsSettings(secsgem.hsms.HsmsSettings):
    """HsmsSettings that uses _ServerConnection for the passive side."""

    def create_connection(self) -> secsgem.common.Connection:
        """Connection class for this configuration."""
        if self.connect_mode == secsgem.hsms.HsmsConnectMode.PASSIVE:
            return _ServerConnection(self)
        return super().create_connection()


class _ChamberGemHandler(secsgem.gem.GemEquipmentHandler):  # pylint: disable=too-many-ancestors
    """GemEquipmentHandler with every state-changing or state-reading path redirected to the core.

    Each override is listed with its reason in docs/library_overrides.md.
    """

    def __init__(self, settings: secsgem.common.Settings, core: EquipmentCore) -> None:
        super().__init__(settings)
        self._core = core
        self._mdln = config.MDLN
        self._softrev = config.SOFTREV

    # --- reads: always served from the core ---------------------------------------------------------
    def on_sv_value_request(self, svid: Base, status_variable: secsgem.gem.StatusVariable) -> Base:
        """Single SV read (used by the library's report building) -> core value."""
        return encode(status_variable.svid, self._core.get_sv(status_variable.svid))

    def on_dv_value_request(self, dvid: Base, data_value: secsgem.gem.DataValue) -> Base:
        """DVs only have meaning inside an event; outside one we return the current equivalent."""
        if data_value.dvid == config.ECID_TEMP_HIGH_LIMIT:
            return encode(data_value.dvid, self._core.get_ec(config.ECID_TEMP_HIGH_LIMIT))
        if data_value.dvid == config.DVID_EVENT_TEMP:
            return encode(data_value.dvid, self._core.get_sv(config.SVID_CHAMBER_TEMP))
        if data_value.dvid == config.DVID_EVENT_SEQ:
            return encode(data_value.dvid, self._core.get_sv(config.SVID_LAST_EVENT_SEQ))
        return encode(data_value.dvid, "")

    def on_ec_value_request(self, ecid: Base, equipment_constant: secsgem.gem.EquipmentConstant) -> Base:
        """S2F13 -> core value."""
        return encode(equipment_constant.ecid, self._core.get_ec(equipment_constant.ecid))

    def _on_s01f03(self, handler: Any, message: secsgem.common.Message) -> Any:
        """S1F3: read all requested SVs in ONE core snapshot (atomic multi-SV read)."""
        del handler
        function = self.settings.streams_functions.decode(message)
        requested = [sv.get() for sv in function] if len(function) else [s.svid for s in config.STATUS_VARIABLES]
        known = [v for v in requested if v in self._status_variables]
        values = dict(zip(known, self._core.get_svs(known)))
        responses: list[Any] = []
        for svid in requested:
            if svid in values:
                responses.append(encode(svid, values[svid]))
            else:
                responses.append(secsgem.secs.variables.Array(self.settings.data_items.SV, []))
        return self.stream_function(1, 4)(responses)

    # --- commands: routed to the core / arbiter ----------------------------------------------------
    def _on_s02f41(self, handler: Any, message: secsgem.common.Message) -> Any:
        """S2F41 host command -> core.submit_command(GEM_HOST); reply S2F42 with the mapped HCACK."""
        del handler
        function = self.settings.streams_functions.decode(message)
        rcmd = function.RCMD.get()
        params = {p["CPNAME"]: p["CPVAL"] for p in function.PARAMS.get()}
        result = self._core.submit_command(Origin.GEM_HOST, str(rcmd), params)
        return self.stream_function(2, 42)({"HCACK": result.gem_code, "PARAMS": []})

    def _on_s02f15(self, handler: Any, message: secsgem.common.Message) -> Any:
        """S2F15 EC send -> core.submit_ec_write(GEM_HOST) per ECID; reply S2F16 with the first non-zero EAC."""
        del handler
        function = self.settings.streams_functions.decode(message)
        eac = config.EAC_OK
        for item in function:
            result = self._core.submit_ec_write(Origin.GEM_HOST, item.ECID.get(), item.ECV.get())
            if not result.ok and eac == config.EAC_OK:
                eac = result.gem_code
        return self.stream_function(2, 16)(eac)

    def _on_s01f15(self, handler: Any, message: secsgem.common.Message) -> Any:
        """S1F15 request OFFLINE: control state belongs to the operator. Ask the arbiter (it refuses)."""
        del handler, message
        result = self._core.set_control_state(Origin.GEM_HOST, ControlState.EQUIPMENT_OFFLINE)
        if result.ok:  # only possible if the policy is ever changed to allow it
            return self.stream_function(1, 16)(0)
        return self.stream_function(1, 0)()  # OFLACK has no refusal code -> transaction abort

    def _on_s01f17(self, handler: Any, message: secsgem.common.Message) -> Any:
        """S1F17 request ONLINE: routed to the arbiter; ONLACK 1 (not allowed) or 2 (already online)."""
        del handler, message
        result = self._core.set_control_state(Origin.GEM_HOST, ControlState.ONLINE_REMOTE)
        if result.ok:
            return self.stream_function(1, 18)(0)
        return self.stream_function(1, 18)(2 if result.gem_code == config.HCACK_ALREADY_IN_STATE else 1)

    def on_connection_closed(self, connection: Any) -> None:
        """Library hook (not called by secsgem 0.3.0); never touch the library's control state machine."""
        del connection


class GemAdapter:
    """Owns the secsgem handler, the dispatcher subscription and the GEM send-side log."""

    def __init__(self, core: EquipmentCore, dispatcher: Dispatcher, run_dir: Optional[Path],
                 address: str = config.HSMS_ADDRESS, port: int = config.HSMS_PORT) -> None:
        """Build and configure the handler (call start())."""
        self._core = core
        self._dispatcher = dispatcher
        self._send_log = JsonlWriter(run_dir / config.GEM_SEND_LOG_FILE if run_dir else None)
        settings = _HsmsSettings(
            address=address,
            port=port,
            connect_mode=secsgem.hsms.HsmsConnectMode.PASSIVE,
            device_type=secsgem.common.DeviceType.EQUIPMENT,
            session_id=config.HSMS_SESSION_ID,
            # T3 reply timeout 3 s instead of 45 s: a reply lost because the link died must not block the
            # single GEM worker for long (the events queued meanwhile are then attributed correctly). D20.
            t3=config.GEM_T3_S,
        )
        self.handler = _ChamberGemHandler(settings, core)
        self._configure_handler()
        self._link_lock = threading.Lock()
        self.handler.events.handler_communicating += self._on_communicating
        self.handler.events.disconnected += self._on_disconnected

    def _configure_handler(self) -> None:
        """Replace the library's default SVs/ECs/CEs/RCMDs with exactly what config.py defines."""
        h = self.handler
        h.status_variables.clear()
        for sv in config.STATUS_VARIABLES:
            h.status_variables[sv.svid] = secsgem.gem.StatusVariable(sv.svid, sv.name, sv.unit, _FORMATS[sv.gem_format])
        h.data_values.clear()
        for dv in config.DATA_VARIABLES:
            h.data_values[dv.dvid] = secsgem.gem.DataValue(dv.dvid, dv.name, _FORMATS[dv.gem_format])
        h.equipment_constants.clear()
        for ec in config.EQUIPMENT_CONSTANTS:
            h.equipment_constants[ec.ecid] = secsgem.gem.EquipmentConstant(
                ec.ecid, ec.name, ec.min_value, ec.max_value, ec.default, ec.unit, _FORMATS[ec.gem_format])
            # ECID 201 is reported inside CEID 1006, but S2F33 only accepts SVIDs/DVIDs as report VIDs:
            # mirror it as a data value with the same id (library_overrides.md O7).
            h.data_values[ec.ecid] = secsgem.gem.DataValue(ec.ecid, ec.name, _FORMATS[ec.gem_format])
        h.collection_events.clear()
        for ce in config.COLLECTION_EVENTS:
            h.collection_events[ce.ceid] = secsgem.gem.CollectionEvent(ce.ceid, ce.name, list(ce.report_vids))
        h.remote_commands.clear()
        for rcmd in config.REMOTE_COMMANDS:
            h.remote_commands[rcmd] = secsgem.gem.RemoteCommand(rcmd, rcmd.title(), [], 0)
        h.alarms.clear()
        for al in config.ALARMS:
            # ce_on/ce_off are required by the constructor but never used: we send S5F1 ourselves (O6).
            h.alarms[al.alid] = secsgem.gem.Alarm(al.alid, al.name, al.text, ALCD_CATEGORY, 0, 0)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        """Start listening on HSMS and subscribe to core notifications."""
        self._dispatcher.subscribe(SUBSCRIBER_NAME, self._on_notification)
        self.handler.enable()
        _log.info("GEM door listening on HSMS port %s (passive)", config.HSMS_PORT)

    def stop(self) -> None:
        """Stop HSMS."""
        try:
            self.handler.disable()
        except Exception:  # noqa: BLE001
            _log.exception("error while disabling GEM handler")
        self._send_log.close()

    @property
    def communicating(self) -> bool:
        """True if the GEM communication state is COMMUNICATING."""
        from secsgem.gem.communication_state_machine import CommunicationState

        return self.handler.communication_state.current == CommunicationState.COMMUNICATING

    # ------------------------------------------------------------------ link state -> core
    def _on_communicating(self, _: dict[str, Any]) -> None:
        self._core.set_gem_link(True)

    def _on_disconnected(self, _: dict[str, Any]) -> None:
        """HSMS link lost. secsgem 0.3.0 never calls on_connection_closed, so we reset comm state here (O8)."""
        with self._link_lock:
            try:
                if self.communicating:
                    self.handler.communication_state.communicationfail()
            except Exception:  # noqa: BLE001
                _log.exception("could not reset GEM communication state")
        self._core.set_gem_link(False)

    # ------------------------------------------------------------------ notifications -> S6F11 / S5F1
    def _on_notification(self, n: Notification) -> None:
        """Dispatcher worker thread (one per door): send in seq order, log every outcome."""
        if n.kind == AuditKind.EVENT.value:
            self._send_event(n)
        elif n.kind in (AuditKind.ALARM_SET.value, AuditKind.ALARM_CLEAR.value):
            self._send_alarm(n)

    def _send_event(self, n: Notification) -> None:
        ceid = int(n.id)
        if not self.communicating:
            self._log_send(n, SendOutcome.DROPPED_NO_LINK)
            return
        link = self.handler.registered_collection_events.get(ceid)
        if link is None or not link.enabled:
            self._log_send(n, SendOutcome.DROPPED_DISABLED)
            return
        try:
            reports = []
            for rptid in link.reports:
                report = self.handler.registered_reports[rptid]
                reports.append({"RPTID": rptid, "V": [self._report_value(vid, n.value) for vid in report.vars]})
            reply = self.handler.send_and_waitfor_response(
                self.handler.stream_function(6, 11)({"DATAID": n.seq, "CEID": ceid, "RPT": reports})
            )
            self._log_reply(n, reply, expected_function=12)
        except Exception as exc:  # noqa: BLE001 - rule 10
            _log.exception("S6F11 for seq %s failed", n.seq)
            self._log_send(n, SendOutcome.ERROR, str(exc))

    def _report_value(self, vid: Any, payload: dict[int, Any]) -> Base:
        """Value of one report VID: frozen event-time payload first, else the current core value."""
        vid = int(vid.get()) if hasattr(vid, "get") else int(vid)
        if vid in payload:
            return encode(vid, payload[vid])
        if vid in {sv.svid for sv in config.STATUS_VARIABLES}:
            return encode(vid, self._core.get_sv(vid))
        if vid == config.ECID_TEMP_HIGH_LIMIT:
            return encode(vid, self._core.get_ec(vid))
        return encode(vid, "" if _vid_format(vid) == "A" else 0)

    def _send_alarm(self, n: Notification) -> None:
        alid = int(n.id)
        alarm = self.handler.alarms[alid]
        is_set = n.kind == AuditKind.ALARM_SET.value
        alarm.set = is_set  # keep S5F5/S5F7 answers consistent with the core
        if not self.communicating:
            self._log_send(n, SendOutcome.DROPPED_NO_LINK)
            return
        if not alarm.enabled:
            self._log_send(n, SendOutcome.DROPPED_DISABLED)
            return
        try:
            alcd = alarm.code | (ALCD_SET_BIT if is_set else 0)
            text = f"{config.ALARMS[0].name} {'SET' if is_set else 'CLEAR'} T={float(n.value):.2f} seq={n.seq}"
            reply = self.handler.send_and_waitfor_response(
                self.handler.stream_function(5, 1)({"ALCD": alcd, "ALID": alid, "ALTX": text})
            )
            self._log_reply(n, reply, expected_function=2)
        except Exception as exc:  # noqa: BLE001 - rule 10
            _log.exception("S5F1 for seq %s failed", n.seq)
            self._log_send(n, SendOutcome.ERROR, str(exc))

    def _log_reply(self, n: Notification, reply: Any, expected_function: int) -> None:
        """`sent` only if the host acknowledged with the expected reply (S6F12 / S5F2).

        None = link lost or T3 timeout; function 0 = the host aborted the transaction (e.g. it could not
        decode the report). Both are logged as `error` so they count as attributed, not silent, losses.
        """
        if reply is None:
            self._log_send(n, SendOutcome.ERROR, "no reply (link lost or T3 timeout)")
        elif reply.header.function != expected_function:
            self._log_send(n, SendOutcome.ERROR, f"host replied S{reply.header.stream}F{reply.header.function}")
        else:
            self._log_send(n, SendOutcome.SENT)

    def _log_send(self, n: Notification, outcome: SendOutcome, detail: Optional[str] = None) -> None:
        rec: dict[str, Any] = {"seq": n.seq, "ts_ns": time.time_ns(), "kind": n.kind, "id": n.id,
                               "outcome": outcome.value}
        if detail:
            rec["detail"] = detail
        self._send_log.write(rec)
