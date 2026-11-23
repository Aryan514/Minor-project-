# equipment/config.py
# Single source of truth for every identifier, port and default used by the testbed.
# Both protocol doors (GEM and OPC UA), the core, the clients and the harness import
# from here, so the two interfaces can never disagree about what an ID means.
# Serves N1 (one core, one definition) and N2 (the GEM -> OPC UA mapping starts here).
"""Central configuration: SVIDs, DVIDs, ECIDs, CEIDs, ALIDs, RCMDs, ports, defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final

# --------------------------------------------------------------------------------------
# Tool identity
# --------------------------------------------------------------------------------------
TOOL_NAME: Final[str] = "Chamber1Tool"
MDLN: Final[str] = "CHAMBER-SIM"  # GEM model name (S1F2 / S1F14)
SOFTREV: Final[str] = "0.1"  # GEM software revision (S1F2 / S1F14)
MANUFACTURER: Final[str] = "Minor Project Testbed"

# --------------------------------------------------------------------------------------
# Network endpoints
# --------------------------------------------------------------------------------------
HSMS_ADDRESS: Final[str] = "0.0.0.0"  # equipment listens (passive) on all interfaces
HSMS_HOST_CONNECT_ADDRESS: Final[str] = "127.0.0.1"  # where the scripted GEM host connects
HSMS_PORT: Final[int] = 5000
HSMS_SESSION_ID: Final[int] = 0  # "device id"; secsgem 0.3.0 calls it session_id
GEM_T3_S: Final[float] = 3.0  # HSMS T3 reply timeout used by the GEM door (decision D20)

OPCUA_ENDPOINT: Final[str] = "opc.tcp://0.0.0.0:4840/semi-equipment/"
OPCUA_CLIENT_ENDPOINT: Final[str] = "opc.tcp://127.0.0.1:4840/semi-equipment/"
OPCUA_NAMESPACE_URI: Final[str] = "urn:minor-project:semi-equipment-mini"
OPCUA_SERVER_NAME: Final[str] = "Chamber1Tool OPC UA door"

# Local operator control socket (harness drives the console through it; docs/decisions.md D5)
CONTROL_HOST: Final[str] = "127.0.0.1"
CONTROL_PORT: Final[int] = 5100

# --------------------------------------------------------------------------------------
# Enumerations shared by core, arbiter and both doors
# --------------------------------------------------------------------------------------


class Origin(str, Enum):
    """Who issued a command (and who caused an event)."""

    GEM_HOST = "GEM_HOST"
    UA_CLIENT = "UA_CLIENT"
    OPERATOR = "OPERATOR"
    EQUIPMENT = "EQUIPMENT"  # internally caused events (samples, alarms)


class ControlState(int, Enum):
    """Simplified GEM control state (HOST_OFFLINE / ATTEMPT_ONLINE intentionally omitted).

    The numeric values are the GEM SVID 2 values.
    """

    EQUIPMENT_OFFLINE = 1
    ONLINE_LOCAL = 4
    ONLINE_REMOTE = 5


class ProcessingState(int, Enum):
    """Processing state; numeric values are the GEM SVID 3 values."""

    IDLE = 0
    EXECUTING = 1


class Action(str, Enum):
    """Write/command actions governed by the arbiter. Reads are never arbitrated."""

    START = "START"
    STOP = "STOP"
    EC_WRITE = "EC_WRITE"
    # Operator-console actions, also routed through the arbiter (docs/decisions.md D3)
    SET_CONTROL_STATE = "SET_CONTROL_STATE"
    SET_LEASE = "SET_LEASE"


class AuditKind(str, Enum):
    """Allowed values of the `kind` field in core_audit.jsonl."""

    SAMPLE = "sample"
    EVENT = "event"
    ALARM_SET = "alarm_set"
    ALARM_CLEAR = "alarm_clear"
    STATE = "state"
    AUTHORITY = "authority"
    COMMAND_OK = "command_ok"
    COMMAND_REJECTED = "command_rejected"
    EC_WRITE = "ec_write"
    EC_REJECTED = "ec_rejected"
    DROPPED = "dropped"  # dispatcher queue overflow (CLAUDE.md 6.3)


class SendOutcome(str, Enum):
    """Outcome recorded in the adapters' send-side logs (N3, invariant I6)."""

    SENT = "sent"
    DROPPED_NO_LINK = "dropped_no_link"
    DROPPED_DISABLED = "dropped_disabled"
    ERROR = "error"


# --------------------------------------------------------------------------------------
# GEM variable definitions
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StatusVariableDef:
    """A GEM status variable (SVID)."""

    svid: int
    name: str
    gem_format: str  # SECS-II format code, e.g. "F4", "U1", "A"
    unit: str


@dataclass(frozen=True)
class DataVariableDef:
    """A GEM data variable (DVID) - only meaningful inside an event report."""

    dvid: int
    name: str
    gem_format: str


@dataclass(frozen=True)
class EquipmentConstantDef:
    """A GEM equipment constant (ECID)."""

    ecid: int
    name: str
    gem_format: str
    unit: str
    min_value: float
    max_value: float
    default: float


@dataclass(frozen=True)
class CollectionEventDef:
    """A GEM collection event (CEID) and the variable IDs its report carries."""

    ceid: int
    name: str
    report_vids: tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AlarmDef:
    """A GEM alarm (ALID) with set threshold and clear hysteresis."""

    alid: int
    name: str
    text: str  # ALTX
    hysteresis: float  # clear when value < limit - hysteresis


# --- Status variables (SVIDs) ---------------------------------------------------------
SVID_CHAMBER_TEMP: Final[int] = 1
SVID_CONTROL_STATE: Final[int] = 2
SVID_PROCESSING_STATE: Final[int] = 3
SVID_AUTHORITY: Final[int] = 4
SVID_LAST_EVENT_SEQ: Final[int] = 5

STATUS_VARIABLES: Final[tuple[StatusVariableDef, ...]] = (
    StatusVariableDef(SVID_CHAMBER_TEMP, "ChamberTemp", "F4", "degC"),
    StatusVariableDef(SVID_CONTROL_STATE, "ControlState", "U1", ""),
    StatusVariableDef(SVID_PROCESSING_STATE, "ProcessingState", "U1", ""),
    StatusVariableDef(SVID_AUTHORITY, "Authority", "A", ""),
    StatusVariableDef(SVID_LAST_EVENT_SEQ, "LastEventSeq", "U4", ""),
)

# --- Data variables (DVIDs) -----------------------------------------------------------
DVID_EVENT_SEQ: Final[int] = 101  # audit seq: the checker's join key
DVID_EVENT_TEMP: Final[int] = 102
DVID_REJECT_REASON: Final[int] = 103
DVID_ORIGIN: Final[int] = 104

DATA_VARIABLES: Final[tuple[DataVariableDef, ...]] = (
    DataVariableDef(DVID_EVENT_SEQ, "EventSeq", "U4"),
    DataVariableDef(DVID_EVENT_TEMP, "EventTemp", "F4"),
    DataVariableDef(DVID_REJECT_REASON, "RejectReason", "A"),
    DataVariableDef(DVID_ORIGIN, "Origin", "A"),
)

# --- Equipment constants (ECIDs) ------------------------------------------------------
ECID_TEMP_HIGH_LIMIT: Final[int] = 201

EQUIPMENT_CONSTANTS: Final[tuple[EquipmentConstantDef, ...]] = (
    # Default 40 degC is ~2 degC above room temperature with the real ESP32 sensor.
    EquipmentConstantDef(ECID_TEMP_HIGH_LIMIT, "TempHighLimit", "F4", "degC", 20.0, 80.0, 40.0),
)

# --- Collection events (CEIDs) --------------------------------------------------------
CEID_CONTROL_STATE_CHANGED: Final[int] = 1001
CEID_PROCESSING_STARTED: Final[int] = 1002
CEID_PROCESSING_STOPPED: Final[int] = 1003
CEID_AUTHORITY_CHANGED: Final[int] = 1004
CEID_COMMAND_REJECTED: Final[int] = 1005
CEID_TEMP_HIGH_LIMIT_CHANGED: Final[int] = 1006
CEID_TEMP_SAMPLE: Final[int] = 1007

COLLECTION_EVENTS: Final[tuple[CollectionEventDef, ...]] = (
    CollectionEventDef(
        CEID_CONTROL_STATE_CHANGED, "ControlStateChanged", (DVID_EVENT_SEQ, DVID_ORIGIN, SVID_CONTROL_STATE)
    ),
    CollectionEventDef(CEID_PROCESSING_STARTED, "ProcessingStarted", (DVID_EVENT_SEQ, DVID_ORIGIN, DVID_EVENT_TEMP)),
    CollectionEventDef(CEID_PROCESSING_STOPPED, "ProcessingStopped", (DVID_EVENT_SEQ, DVID_ORIGIN, DVID_EVENT_TEMP)),
    CollectionEventDef(CEID_AUTHORITY_CHANGED, "AuthorityChanged", (DVID_EVENT_SEQ, DVID_ORIGIN, SVID_AUTHORITY)),
    CollectionEventDef(
        CEID_COMMAND_REJECTED, "CommandRejected", (DVID_EVENT_SEQ, DVID_ORIGIN, DVID_REJECT_REASON)
    ),
    CollectionEventDef(
        CEID_TEMP_HIGH_LIMIT_CHANGED, "TempHighLimitChanged", (DVID_EVENT_SEQ, DVID_ORIGIN, ECID_TEMP_HIGH_LIMIT)
    ),
    CollectionEventDef(CEID_TEMP_SAMPLE, "TempSample", (DVID_EVENT_SEQ, DVID_EVENT_TEMP)),
)
TEMP_SAMPLE_EVENT_PERIOD_S: Final[float] = 1.0  # CEID 1007 is emitted at 1 Hz

# --- Alarms (ALIDs) -------------------------------------------------------------------
ALID_CHAMBER_OVER_TEMP: Final[int] = 5001

ALARMS: Final[tuple[AlarmDef, ...]] = (
    AlarmDef(ALID_CHAMBER_OVER_TEMP, "ChamberOverTemp", "Chamber temperature above TempHighLimit", 1.0),
)
ALARM_SEVERITY_UA: Final[int] = 700  # OPC UA Severity (1..1000) used for ALID 5001

# --- Remote commands (RCMDs) ----------------------------------------------------------
RCMD_START: Final[str] = "START"
RCMD_STOP: Final[str] = "STOP"
REMOTE_COMMANDS: Final[tuple[str, ...]] = (RCMD_START, RCMD_STOP)

# --------------------------------------------------------------------------------------
# Reply-code mappings (CLAUDE.md section 6.4)
# --------------------------------------------------------------------------------------
# S2F42 HCACK
HCACK_OK: Final[int] = 0
HCACK_UNKNOWN_COMMAND: Final[int] = 1
HCACK_CANNOT_PERFORM_NOW: Final[int] = 2
HCACK_ALREADY_IN_STATE: Final[int] = 5

# S2F16 EAC
EAC_OK: Final[int] = 0
EAC_UNKNOWN_ECID: Final[int] = 1
EAC_DENIED: Final[int] = 2
EAC_OUT_OF_RANGE: Final[int] = 3

# OPC UA StatusCode names (resolved to asyncua.ua.StatusCodes in the UA door)
UA_STATUS_OK: Final[str] = "Good"
UA_STATUS_AUTHORITY: Final[str] = "BadUserAccessDenied"
UA_STATUS_WRONG_STATE: Final[str] = "BadInvalidState"
UA_STATUS_RANGE: Final[str] = "BadOutOfRange"
UA_STATUS_UNKNOWN: Final[str] = "BadNotFound"

# --------------------------------------------------------------------------------------
# Initial equipment state
# --------------------------------------------------------------------------------------
INITIAL_CONTROL_STATE: Final[ControlState] = ControlState.ONLINE_LOCAL
INITIAL_PROCESSING_STATE: Final[ProcessingState] = ProcessingState.IDLE

# --------------------------------------------------------------------------------------
# Simulated chamber (CLAUDE.md section 5)
# --------------------------------------------------------------------------------------
SIM_SAMPLE_PERIOD_S: Final[float] = 0.5
SIM_AMBIENT_C: Final[float] = 25.0
SIM_HEATER_TARGET_C: Final[float] = 60.0
SIM_HEAT_RATE_C_PER_S: Final[float] = 0.8
SIM_COOL_RATE_C_PER_S: Final[float] = 0.5
SIM_NOISE_C: Final[float] = 0.05
SIM_DEFAULT_SEED: Final[int] = 42

# --------------------------------------------------------------------------------------
# Serial ESP32 sensor (optional)
# --------------------------------------------------------------------------------------
SERIAL_BAUD: Final[int] = 115200
SERIAL_HEATER_ON: Final[bytes] = b"H1\n"
SERIAL_HEATER_OFF: Final[bytes] = b"H0\n"

# --------------------------------------------------------------------------------------
# Dispatcher, logging, harness
# --------------------------------------------------------------------------------------
DISPATCHER_QUEUE_SIZE: Final[int] = 10_000
RUNS_DIR: Final[str] = "runs"
RESULTS_DIR: Final[str] = "results"
CORE_AUDIT_FILE: Final[str] = "core_audit.jsonl"
GEM_SEND_LOG_FILE: Final[str] = "gem_adapter_send.jsonl"
UA_SEND_LOG_FILE: Final[str] = "ua_adapter_send.jsonl"
GEM_HOST_LOG_FILE: Final[str] = "gem_host.jsonl"
UA_CLIENT_LOG_FILE: Final[str] = "ua_client.jsonl"

STATE_CONVERGENCE_T_MS: Final[int] = 500  # invariant I4 window
FLOAT_TOLERANCE: Final[float] = 1e-3  # invariant I3 tolerance


# --------------------------------------------------------------------------------------
# Lookup helpers
# --------------------------------------------------------------------------------------
def all_variable_ids() -> set[int]:
    """Return every SVID, DVID and ECID; used to check report VIDs and catch ID collisions."""
    return (
        {sv.svid for sv in STATUS_VARIABLES}
        | {dv.dvid for dv in DATA_VARIABLES}
        | {ec.ecid for ec in EQUIPMENT_CONSTANTS}
    )


def collection_event(ceid: int) -> CollectionEventDef:
    """Return the CollectionEventDef for a CEID, or raise KeyError."""
    for ce in COLLECTION_EVENTS:
        if ce.ceid == ceid:
            return ce
    raise KeyError(f"unknown CEID {ceid}")


def equipment_constant(ecid: int) -> EquipmentConstantDef:
    """Return the EquipmentConstantDef for an ECID, or raise KeyError."""
    for ec in EQUIPMENT_CONSTANTS:
        if ec.ecid == ecid:
            return ec
    raise KeyError(f"unknown ECID {ecid}")
