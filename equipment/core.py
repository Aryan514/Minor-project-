# equipment/core.py
# EquipmentCore: the ONE owner of equipment state. Every command from every door goes through
# submit_command / submit_ec_write / set_control_state / set_lease, which take one lock, ask the
# arbiter, check preconditions, apply, audit (with seq) and enqueue notifications before releasing.
# Serves N1 (single core, atomic decide-and-apply) and N3 (every change gets an audited seq).
"""The authoritative equipment core (CLAUDE.md section 6.2)."""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass
from typing import Any, Optional

from equipment import arbiter, config
from equipment.audit import AuditLog, AuditRecord
from equipment.config import Action, AuditKind, ControlState, Origin, ProcessingState
from equipment.dispatcher import Dispatcher, Notification
from equipment.sensors import Sensor

_log = logging.getLogger(__name__)

# Event kinds that clients must receive (invariant I1); everything else is state/bookkeeping.
CLIENT_VISIBLE_KINDS = frozenset({AuditKind.EVENT.value, AuditKind.ALARM_SET.value, AuditKind.ALARM_CLEAR.value})


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a command, with the reply code for each protocol already mapped.

    Attributes:
        ok: True if the command was applied.
        gem_code: HCACK (S2F42) for commands, EAC (S2F16) for EC writes.
        ua_status: OPC UA StatusCode name, e.g. "Good", "BadUserAccessDenied".
        reason: empty when ok, otherwise a human-readable rejection reason.
        seq: audit seq of the command_ok / command_rejected / ec_write / ec_rejected record.
    """

    ok: bool
    gem_code: int
    ua_status: str
    reason: str
    seq: int


class EquipmentCore:
    """Holds all state under one re-entrant lock; protocol doors only read it and submit commands."""

    def __init__(
        self,
        audit: AuditLog,
        dispatcher: Optional[Dispatcher] = None,
        sensor: Optional[Sensor] = None,
        initial_control_state: ControlState = config.INITIAL_CONTROL_STATE,
    ) -> None:
        """Create the core.

        Args:
            audit: where every state change is recorded with a seq.
            dispatcher: where notifications are enqueued (None = nobody listens, unit tests).
            sensor: used only to switch the heater on START/STOP.
            initial_control_state: control state at power-up.
        """
        self._lock = threading.RLock()
        self._audit = audit
        self._dispatcher = dispatcher
        self._sensor = sensor
        if dispatcher is not None:
            dispatcher.set_drop_callback(self._on_dispatch_drop)

        # ---- the equipment state (only modified under self._lock) ----
        self._temp: float = config.SIM_AMBIENT_C
        self._control_state: ControlState = initial_control_state
        self._processing_state: ProcessingState = config.INITIAL_PROCESSING_STATE
        self._lease_ua: bool = False
        self._authority: Origin = arbiter.authority_holder(self._control_state, self._lease_ua)
        self._ecs: dict[int, float] = {ec.ecid: float(ec.default) for ec in config.EQUIPMENT_CONSTANTS}
        self._alarms_active: set[int] = set()
        self._last_event_seq: int = 0
        self._last_rejection: Optional[dict[str, Any]] = None
        self._gem_link_up: bool = False
        self._last_temp_event_ns: Optional[int] = None

    # ------------------------------------------------------------------ reads (always allowed)
    def snapshot(self) -> dict[str, Any]:
        """A consistent copy of the whole state (taken under the lock)."""
        with self._lock:
            return {
                "temp": self._temp,
                "control_state": self._control_state.name,
                "control_state_id": int(self._control_state),
                "processing_state": self._processing_state.name,
                "processing_state_id": int(self._processing_state),
                "authority": self._authority.value,
                "lease_ua": self._lease_ua,
                "temp_high_limit": self._ecs[config.ECID_TEMP_HIGH_LIMIT],
                "alarms_active": sorted(self._alarms_active),
                "last_event_seq": self._last_event_seq,
                "last_rejection": dict(self._last_rejection) if self._last_rejection else None,
                "gem_link": "COMMUNICATING" if self._gem_link_up else "NOT_COMMUNICATING",
                "last_seq": self._audit.last_seq,
            }

    def get_sv(self, svid: int) -> Any:
        """Current value of a status variable (SVID 1..5)."""
        with self._lock:
            return self._sv_value(svid)

    def get_svs(self, svids: list[int]) -> list[Any]:
        """Several SVs read atomically (one lock acquisition, so they belong to the same instant)."""
        with self._lock:
            return [self._sv_value(s) for s in svids]

    def get_ec(self, ecid: int) -> float:
        """Current value of an equipment constant."""
        with self._lock:
            return self._ecs[ecid]

    # ------------------------------------------------------------------ commands (via arbiter)
    def submit_command(self, origin: Origin, rcmd: str, params: Optional[dict[str, Any]] = None) -> CommandResult:
        """START / STOP from any origin. Decide-and-apply is atomic under the core lock."""
        del params  # START/STOP take no parameters
        with self._lock:
            if rcmd not in config.REMOTE_COMMANDS:
                return self._reject(
                    origin, AuditKind.COMMAND_REJECTED, rcmd, None, f"unknown command {rcmd!r}",
                    config.HCACK_UNKNOWN_COMMAND, config.UA_STATUS_UNKNOWN,
                )
            action = Action(rcmd)
            decision = arbiter.decide(self._control_state, self._lease_ua, origin, action)
            if not decision.allowed:
                return self._reject(
                    origin, AuditKind.COMMAND_REJECTED, rcmd, None, decision.reason,
                    config.HCACK_CANNOT_PERFORM_NOW, config.UA_STATUS_AUTHORITY,
                )
            wanted = ProcessingState.EXECUTING if action == Action.START else ProcessingState.IDLE
            if self._processing_state == wanted:
                return self._reject(
                    origin, AuditKind.COMMAND_REJECTED, rcmd, None, f"already {wanted.name}",
                    config.HCACK_ALREADY_IN_STATE, config.UA_STATUS_WRONG_STATE,
                )
            ok = self._record(AuditKind.COMMAND_OK, rcmd, None, origin)
            self._processing_state = wanted
            self._record(AuditKind.STATE, "ProcessingState", wanted.name, origin, {"id": int(wanted)})
            self._set_heater(wanted == ProcessingState.EXECUTING)
            ceid = config.CEID_PROCESSING_STARTED if wanted == ProcessingState.EXECUTING else config.CEID_PROCESSING_STOPPED
            self._emit_event(ceid, origin)
            return CommandResult(True, config.HCACK_OK, config.UA_STATUS_OK, "", ok.seq)

    def submit_ec_write(self, origin: Origin, ecid: int, value: Any) -> CommandResult:
        """Write an equipment constant (GEM S2F15, UA SetTempHighLimit, console `limit`)."""
        with self._lock:
            try:
                ec = config.equipment_constant(int(ecid))
            except (KeyError, ValueError, TypeError):
                return self._reject(
                    origin, AuditKind.EC_REJECTED, ecid, value, f"unknown ECID {ecid}",
                    config.EAC_UNKNOWN_ECID, config.UA_STATUS_UNKNOWN,
                )
            decision = arbiter.decide(self._control_state, self._lease_ua, origin, Action.EC_WRITE)
            if not decision.allowed:
                return self._reject(
                    origin, AuditKind.EC_REJECTED, ec.ecid, value, decision.reason,
                    config.EAC_DENIED, config.UA_STATUS_AUTHORITY,
                )
            try:
                fvalue = float(value)
            except (TypeError, ValueError):
                fvalue = math.nan
            if not (ec.min_value <= fvalue <= ec.max_value):  # NaN fails this test too
                return self._reject(
                    origin, AuditKind.EC_REJECTED, ec.ecid, value,
                    f"{ec.name} must be within {ec.min_value}..{ec.max_value}",
                    config.EAC_OUT_OF_RANGE, config.UA_STATUS_RANGE,
                )
            self._ecs[ec.ecid] = fvalue
            rec = self._record(AuditKind.EC_WRITE, ec.ecid, fvalue, origin, {"name": ec.name})
            self._emit_event(config.CEID_TEMP_HIGH_LIMIT_CHANGED, origin)
            return CommandResult(True, config.EAC_OK, config.UA_STATUS_OK, "", rec.seq)

    def set_control_state(self, origin: Origin, new_state: ControlState) -> CommandResult:
        """Change the simplified GEM control state (operator console only, enforced by the arbiter)."""
        with self._lock:
            decision = arbiter.decide(self._control_state, self._lease_ua, origin, Action.SET_CONTROL_STATE)
            if not decision.allowed:
                return self._reject(
                    origin, AuditKind.COMMAND_REJECTED, Action.SET_CONTROL_STATE.value, new_state.name,
                    decision.reason, config.HCACK_CANNOT_PERFORM_NOW, config.UA_STATUS_AUTHORITY,
                )
            if new_state == self._control_state:
                return self._reject(
                    origin, AuditKind.COMMAND_REJECTED, Action.SET_CONTROL_STATE.value, new_state.name,
                    f"already {new_state.name}", config.HCACK_ALREADY_IN_STATE, config.UA_STATUS_WRONG_STATE,
                )
            ok = self._record(AuditKind.COMMAND_OK, Action.SET_CONTROL_STATE.value, new_state.name, origin)
            self._control_state = new_state
            self._record(AuditKind.STATE, "ControlState", new_state.name, origin, {"id": int(new_state)})
            self._emit_event(config.CEID_CONTROL_STATE_CHANGED, origin)
            if new_state != ControlState.EQUIPMENT_OFFLINE and self._lease_ua:
                self._lease_ua = False  # leaving OFFLINE revokes the maintenance lease
                self._record(AuditKind.STATE, "LeaseUA", False, origin, {"cause": "left EQUIPMENT_OFFLINE"})
            self._update_authority(origin)
            return CommandResult(True, config.HCACK_OK, config.UA_STATUS_OK, "", ok.seq)

    def set_lease(self, origin: Origin, on: bool) -> CommandResult:
        """Grant (`lease ua`) or revoke (`lease off`) the UA maintenance lease (operator only)."""
        with self._lock:
            label = "LEASE_UA" if on else "LEASE_OFF"
            decision = arbiter.decide(self._control_state, self._lease_ua, origin, Action.SET_LEASE)
            if not decision.allowed:
                return self._reject(
                    origin, AuditKind.COMMAND_REJECTED, label, on, decision.reason,
                    config.HCACK_CANNOT_PERFORM_NOW, config.UA_STATUS_AUTHORITY,
                )
            if on and self._control_state != ControlState.EQUIPMENT_OFFLINE:
                return self._reject(
                    origin, AuditKind.COMMAND_REJECTED, label, on, "lease only valid in EQUIPMENT_OFFLINE",
                    config.HCACK_CANNOT_PERFORM_NOW, config.UA_STATUS_WRONG_STATE,
                )
            if self._lease_ua == on:
                return self._reject(
                    origin, AuditKind.COMMAND_REJECTED, label, on, f"lease already {'granted' if on else 'off'}",
                    config.HCACK_ALREADY_IN_STATE, config.UA_STATUS_WRONG_STATE,
                )
            ok = self._record(AuditKind.COMMAND_OK, label, on, origin)
            self._lease_ua = on
            self._record(AuditKind.STATE, "LeaseUA", on, origin)
            self._update_authority(origin)
            return CommandResult(True, config.HCACK_OK, config.UA_STATUS_OK, "", ok.seq)

    # ------------------------------------------------------------------ equipment inputs
    def on_sample(self, temp: float) -> None:
        """New sensor reading: update SVID 1, evaluate the alarm, emit CEID 1007 at 1 Hz."""
        with self._lock:
            self._temp = float(temp)
            rec = self._record(AuditKind.SAMPLE, config.SVID_CHAMBER_TEMP, self._temp, Origin.EQUIPMENT)
            self._evaluate_alarm()
            period_ns = int(config.TEMP_SAMPLE_EVENT_PERIOD_S * 1e9)
            # 0.9 x period tolerance: with 0.5 s samples this yields one event every 2nd sample.
            if self._last_temp_event_ns is None or rec.ts_ns - self._last_temp_event_ns >= 0.9 * period_ns:
                self._last_temp_event_ns = rec.ts_ns
                self._emit_event(config.CEID_TEMP_SAMPLE, Origin.EQUIPMENT)

    def set_gem_link(self, up: bool) -> None:
        """GEM door reports HSMS/GEM communication up or down (mirrored to UA CommunicationState)."""
        with self._lock:
            if up == self._gem_link_up:
                return
            self._gem_link_up = up
            value = "COMMUNICATING" if up else "NOT_COMMUNICATING"
            self._record(AuditKind.STATE, "GemCommunicationState", value, Origin.EQUIPMENT)

    # ------------------------------------------------------------------ internals (lock held)
    def _sv_value(self, svid: int) -> Any:
        if svid == config.SVID_CHAMBER_TEMP:
            return self._temp
        if svid == config.SVID_CONTROL_STATE:
            return int(self._control_state)
        if svid == config.SVID_PROCESSING_STATE:
            return int(self._processing_state)
        if svid == config.SVID_AUTHORITY:
            return self._authority.value
        if svid == config.SVID_LAST_EVENT_SEQ:
            return self._last_event_seq
        raise KeyError(f"unknown SVID {svid}")

    def _record(
        self, kind: AuditKind, id_: Any, value: Any, origin: Origin | str,
        extra: Optional[dict[str, Any]] = None, seq: Optional[int] = None,
    ) -> AuditRecord:
        """Audit one change and enqueue it for every subscriber (lock held)."""
        origin_s = origin.value if isinstance(origin, Origin) else str(origin)
        rec = self._audit.append(kind.value, id_, value, origin_s, extra, seq=seq)
        if rec.kind in CLIENT_VISIBLE_KINDS:
            self._last_event_seq = rec.seq
        if self._dispatcher is not None:
            self._dispatcher.publish(
                Notification(rec.seq, rec.ts_ns, rec.kind, rec.id, rec.value, rec.origin, rec.extra)
            )
        return rec

    def _emit_event(self, ceid: int, origin: Origin, reason: str = "") -> AuditRecord:
        """Emit a collection event whose report values are frozen NOW (event time), incl. its own seq."""
        ce = config.collection_event(ceid)
        seq = self._audit.reserve()
        payload: dict[int, Any] = {}
        for vid in ce.report_vids:
            if vid == config.DVID_EVENT_SEQ:
                payload[vid] = seq
            elif vid == config.DVID_EVENT_TEMP:
                payload[vid] = self._temp
            elif vid == config.DVID_REJECT_REASON:
                payload[vid] = reason
            elif vid == config.DVID_ORIGIN:
                payload[vid] = origin.value
            elif vid in self._ecs:
                payload[vid] = self._ecs[vid]
            else:
                payload[vid] = self._sv_value(vid)
        return self._record(AuditKind.EVENT, ceid, payload, origin, {"name": ce.name}, seq=seq)

    def _reject(
        self, origin: Origin, kind: AuditKind, id_: Any, value: Any, reason: str, gem_code: int, ua_status: str,
    ) -> CommandResult:
        """Audit a rejection and tell BOTH doors about it via CEID 1005."""
        rec = self._record(kind, id_, value, origin, {"reason": reason, "gem_code": gem_code, "ua_status": ua_status})
        self._last_rejection = {"seq": rec.seq, "origin": str(origin.value if isinstance(origin, Origin) else origin),
                                "what": str(id_), "reason": reason}
        self._emit_event(config.CEID_COMMAND_REJECTED, origin, reason=reason)
        return CommandResult(False, gem_code, ua_status, reason, rec.seq)

    def _update_authority(self, origin: Origin) -> None:
        holder = arbiter.authority_holder(self._control_state, self._lease_ua)
        if holder != self._authority:
            self._authority = holder
            self._record(AuditKind.AUTHORITY, "Authority", holder.value, origin)
            self._emit_event(config.CEID_AUTHORITY_CHANGED, origin)

    def _evaluate_alarm(self) -> None:
        alarm = config.ALARMS[0]
        limit = self._ecs[config.ECID_TEMP_HIGH_LIMIT]
        active = alarm.alid in self._alarms_active
        if not active and self._temp > limit:
            self._alarms_active.add(alarm.alid)
            self._record(AuditKind.ALARM_SET, alarm.alid, self._temp, Origin.EQUIPMENT,
                         {"name": alarm.name, "text": alarm.text, "limit": limit})
        elif active and self._temp < limit - alarm.hysteresis:
            self._alarms_active.discard(alarm.alid)
            self._record(AuditKind.ALARM_CLEAR, alarm.alid, self._temp, Origin.EQUIPMENT,
                         {"name": alarm.name, "text": alarm.text, "limit": limit})

    def _set_heater(self, on: bool) -> None:
        if self._sensor is None:
            return
        try:
            self._sensor.set_heater(on)
        except Exception:  # noqa: BLE001 - a heater I/O error must not break the command path
            _log.exception("set_heater failed")

    def _on_dispatch_drop(self, subscriber: str, dropped: Notification) -> None:
        """Dispatcher overflow: audit the loss (kind=dropped). Not published, to avoid feedback loops."""
        with self._lock:
            self._audit.append(AuditKind.DROPPED.value, dropped.seq, dropped.kind, Origin.EQUIPMENT.value,
                               {"subscriber": subscriber})
