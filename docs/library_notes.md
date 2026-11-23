# Library notes (verified against installed source)

Every class or method listed here was read in the installed package source under
`.venv/Lib/site-packages/` on 2026-11-23. Paths below are relative to that folder. Nothing in this file is
taken from tutorials or memory.

| Package | Version | Location check |
|---|---|---|
| `secsgem` | 0.3.0 | `python -c "import secsgem; print(secsgem.__file__)"` → `.venv/Lib/site-packages/secsgem/__init__.py` |
| `asyncua` | 1.1.8 (latest 1.x on PyPI; 2.1.0 also exists but CLAUDE.md pins 1.x) | `asyncua/__init__.py` |
| `secsgem-driver` | **not installed** (`pip show secsgem-driver` → not found) | — |

---

## Part A — secsgem 0.3.0

### A.1 Settings and connection (`secsgem/hsms/settings.py`, `secsgem/common/settings.py`)

```python
import secsgem.common, secsgem.hsms
settings = secsgem.hsms.HsmsSettings(
    address="0.0.0.0", port=5000,
    connect_mode=secsgem.hsms.HsmsConnectMode.PASSIVE,     # equipment; host uses ACTIVE
    device_type=secsgem.common.DeviceType.EQUIPMENT,       # host: DeviceType.HOST
    session_id=0,                                           # = HSMS "device id"
)
```

- Unknown keyword arguments raise `ValueError` (`Settings._validate_args`). Allowed:
  `connect_mode, address, port, device_type, streams_functions, session_id, establish_communication_timeout`
  plus timeout args (`Timeouts(**kwargs)`).
- **Differs from old tutorials:** handlers take a single `settings` object, not `(address, port, active, session_id, name)`.
  The device id keyword is `session_id`.

### A.2 GEM equipment handler (`secsgem/gem/equipmenthandler.py`)

`GemEquipmentHandler(settings, initial_control_state="ATTEMPT_ONLINE", initial_online_control_state="REMOTE")`
is built from mixins: `AlarmCapability, ClockCapability, DataValueCapability, EquipmentConstantsCapability,
RemoteControlCapability, StateModelsCapability, CollectionEventCapability, StatusDataCollectionCapability, GemHandler`.

| Need | Member (verified) | File |
|---|---|---|
| Start / stop | `handler.enable()`, `handler.disable()` | `gem/handler.py` |
| Model name / revision | set `handler._mdln`, `handler._softrev` (no public setter) | `gem/handler.py` `__init__` |
| Comm state | `handler.communication_state.current` (`CommunicationState.COMMUNICATING` …); `waitfor_communicating(timeout)` | `gem/handler.py`, `gem/communication_state_machine.py` |
| Link up/down events | `handler.events.communicating` (HSMS selected), `handler.events.disconnected`, `handler.events.connected`; GEM-level `handler_communicating` fired on entering COMMUNICATING; override `on_connection_closed(connection)` | `hsms/protocol.py` (`events.fire("communicating"/"disconnected")`), `gem/handler.py` |
| Register an incoming S/F handler | define a method `_on_sXXfYY(self, handler, message)` on the subclass **or** `register_stream_function(stream, function, callback)` | `common/callbacks.py` (`CallbackHandler._call` looks up `"_on_" + name` on the target) |
| Decode a message | `self.settings.streams_functions.decode(message)` | used in every capability |
| Build a message | `self.stream_function(s, f)(data)` | `secs/handler.py` |
| Send | `send_and_waitfor_response(fn)` → `Message | None` (None if send failed or T3 timeout); `send_stream_function(fn)` → bool; `send_response(fn, system)` → bool | `common/protocol.py` |

### A.3 Status variables, data values, equipment constants

```python
from secsgem.gem import StatusVariable, DataValue, EquipmentConstant
from secsgem.secs.variables import F4, U1, U4, String
handler.status_variables[1] = StatusVariable(1, "ChamberTemp", "degC", F4)       # use_callback=True default
handler.data_values[101]    = DataValue(101, "EventSeq", U4)
handler.equipment_constants[201] = EquipmentConstant(201, "TempHighLimit", 20, 80, 40, "degC", F4)
```

- Values are fetched on demand through overridable callbacks:
  `on_sv_value_request(svid, status_variable) -> secs variable`,
  `on_dv_value_request(dvid, data_value) -> secs variable`,
  `on_ec_value_request(ecid, equipment_constant) -> secs variable`,
  `on_ec_value_update(ecid, equipment_constant, value)` (return value ignored).
  Files: `gem/status_data_collection_capability.py`, `gem/data_value_capability.py`, `gem/equipment_constants_capability.py`.
- S1F3/F4, S1F11/F12, S2F13/F14, S2F29/F30 are handled by the library from these dictionaries.
- **Built-in defaults the library pre-registers** (must be removed or overridden — see "Differences" below):
  SVIDs 1001 Clock, 1002 ControlState, 1003 EventsEnabled, 1004 AlarmsEnabled, 1005 AlarmsSet;
  ECIDs 1 EstablishCommunicationsTimeout, 2 TimeFormat; CEIDs 1, 2, 3, 20, 21; RCMDs START, STOP.

### A.4 Collection events and reports (`gem/collection_event_capability.py`)

```python
from secsgem.gem import CollectionEvent
handler.collection_events[1007] = CollectionEvent(1007, "TempSample", [101, 102])
```

- S2F33 (define report), S2F35 (link), S2F37 (enable) are handled by the library and stored in
  `handler.registered_reports` (`{rptid: CollectionEventReport(rptid, vars)}`) and
  `handler.registered_collection_events` (`{ceid: CollectionEventLink(ce, [rptid…])}` with `.enabled`).
  S2F33 only accepts VIDs that are keys of `data_values` or `status_variables`.
- Sending an event: `trigger_collection_events([ceid])`. It **starts a new thread per call**, silently does
  nothing if the CEID is not linked/enabled, and builds the report values **at send time** by calling
  `_build_collection_event(ceid)` → `on_sv_value_request` / `on_dv_value_request`.
- Internal helper usable by our adapter: `_build_collection_event(ceid) -> [{"RPTID", "V": [...]}]`.

### A.5 Alarms (`gem/alarm.py`, `gem/alarm_capability.py`)

```python
from secsgem.gem import Alarm
handler.alarms[5001] = Alarm(5001, "ChamberOverTemp", "text", code, ce_on, ce_off)
handler.set_alarm(5001); handler.clear_alarm(5001)
```

- `Alarm(alid, name, text, code, ce_on, ce_off)` — `ce_on`/`ce_off` are CEIDs triggered on set/clear (required).
- `set_alarm` sends S5F1 with **the fixed `Alarm.text`** (ALCD = code | 0x80) only if the host enabled it via
  S5F3, then `trigger_collection_events([ce_on])`. S5F3/F5/F7 are handled by the library.

### A.6 Remote commands (`gem/remote_command.py`, `gem/remote_control_capability.py`)

- `RemoteCommand(rcmd, name, params, ce_finished)`, stored in `handler.remote_commands`.
- Library `_on_s02f41`: unknown RCMD → HCACK 1; otherwise it **always replies HCACK 4 (ACK_FINISH_LATER)
  first**, then calls `_on_rcmd_<NAME>(**params)`, then triggers `ce_finished`.

### A.7 Control state (`gem/control_state_machine.py`, `gem/state_models_capability.py`)

- The handler owns its own `ControlStateMachine` (OFFLINE / EQUIPMENT_OFFLINE / ATTEMPT_ONLINE / HOST_OFFLINE /
  ONLINE_LOCAL / ONLINE_REMOTE), changed by `control_switch_online_local()`, `control_switch_online_remote()`,
  `control_switch_offline()`, and **by the host** through S1F15 (request offline) and S1F17 (request online).
- `GemEquipmentHandler.on_connection_closed` switches this machine offline and back online on every disconnect.

### A.8 GEM host handler (`gem/hosthandler.py`) — for `clients/gem_host.py`

| Need | Method (verified) |
|---|---|
| Comm | `enable()`, `waitfor_communicating(timeout)` (S1F13 exchange is automatic) |
| Status | `request_svs([svid…])` (S1F3), `list_svs()` (S1F11) — in `secs/handler.py` |
| ECs | `request_ecs([...])` (S2F13), `set_ec(ecid, value)` / `set_ecs([[id, v]…])` (S2F15) — `secs/handler.py` |
| Reports | `subscribe_collection_event(ceid, [vid…], report_id=None)` = S2F33 + S2F35 + S2F37; `clear_collection_events()`; `disable_ceid_reports()` |
| Alarms | `enable_alarm(alid)` (S5F3), `list_alarms()` |
| Remote cmd | `send_remote_command(rcmd, params)` → decoded S2F42 |
| Receiving | events `collection_event_received` (data: `ceid, rptid, values=[{dvid, value}]`) and `alarm_received` (`code, alid, text`) via `handler.events.<name> += callback`; or override `_on_s06f11` / `_on_s05f01` |

Note: `_on_s06f11` looks up `self.report_subscriptions[rptid]`; a report not defined through
`subscribe_collection_event` raises `KeyError` inside the handler (the library then replies S6F0).

---

## Part B — asyncua 1.1.8

### B.1 Server setup (`asyncua/server/server.py`)

```python
from asyncua import Server, ua
server = Server(); await server.init()
server.set_endpoint("opc.tcp://0.0.0.0:4840/semi-equipment/")
server.set_server_name(...)
server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
idx = await server.register_namespace("urn:minor-project:semi-equipment-mini")
async with server: ...            # or await server.start() / await server.stop()
```

Default user manager is `PermissiveUserManager` (`server/user_managers.py`): anonymous clients get
`UserRole.User`, so client writes are only allowed on nodes whose `AccessLevel` **and** `UserAccessLevel`
have `CurrentWrite` (`AttributeService.write`, `server/address_space.py`).

### B.2 Types and instances

- `await server.create_custom_object_type(idx, name, basetype=ObjectIds.BaseObjectType, properties=[(name, VariantType)], variables=[...], methods=[...])`
- `await server.create_custom_variable_type(idx, name, basetype=ObjectIds.BaseVariableType, ...)`
- `await server.create_custom_event_type(idx, name, basetype=ObjectIds.BaseEventType, properties=[("CEID", ua.VariantType.UInt32), ...])`
- Nodes (`common/node.py`): `add_object(idx, name, objecttype=None)`, `add_variable(idx, name, val, varianttype=None, datatype=None)`,
  `add_property(...)`, `add_method(idx, name, callback, [in_types], [out_types])`, `add_reference(target, reftype, forward=True, bidirectional=True)`,
  `set_modelling_rule(mandatory)`, `set_writable(bool)`, `set_read_only()`, `write_value(value | ua.Variant | ua.DataValue)`.
- `write_value` accepts a full `ua.DataValue`, so `SourceTimestamp` can be set from the core timestamp:
  `ua.DataValue(ua.Variant(v, VariantType.Double), SourceTimestamp=ts)`.
- `ua.EUInformation` and `ua.Range` exist (`ua/uaprotocol_auto.py`) for `EngineeringUnits` / `EURange` properties.

### B.3 Custom events (`server/event_generator.py`)

```python
etype = await server.create_custom_event_type(idx, "GemCollectionEventType", ua.ObjectIds.BaseEventType,
            [("CEID", ua.VariantType.UInt32), ("EventSeq", ua.VariantType.UInt32),
             ("Origin", ua.VariantType.String), ("Payload", ua.VariantType.String)])
gen = await server.get_event_generator(etype, emitting_node=tool_node)
gen.event.CEID = 1007; gen.event.EventSeq = seq; ...
await gen.trigger(time_attr=core_ts, message="TempSample")
```

- `get_event_generator` sets `EventNotifier=SubscribeToEvents` on the emitting node and adds a `GeneratesEvent` reference.
- One `EventGenerator` holds **one mutable event object**; fields must be set and `trigger()` awaited without
  interleaving (our single UA dispatcher task guarantees this).
- `trigger()` is `async` → must run inside the server's asyncio loop.

### B.4 Alarms & Conditions

- Event classes exist (`common/event_objects.py`): `Condition`, `AcknowledgeableCondition`, `AlarmCondition`,
  `DiscreteAlarm`, `OffNormalAlarm`, limit alarms. `get_event_generator(ua.ObjectIds.OffNormalAlarmType, node)`
  builds an event with fields such as `ActiveState`, `ActiveState/Id`, `Retain`, `Severity`, `Message`.
- Server keeps condition events with `Retain=True` and a `NodeId` field in `SubscriptionService._conditions`
  and replays them on **`ConditionRefresh`**, which is implemented (`server/subscription_service.py`,
  linked in `server/internal_server.py`).
- **Not implemented server-side:** the condition state machine and the `Acknowledge` / `Confirm` /
  `Enable` / `Disable` methods (no method callbacks are linked for them in `server/`). A client calling
  Acknowledge gets `BadNothingToDo`. → Plan: emit `OffNormalAlarmType` events (ActiveState, Message=ALTX,
  Severity, Retain, plus our `ALID`/`EventSeq` fields via a subtype) and link our own Acknowledge only if the
  90-minute time box allows; otherwise fall back to `GemAlarmEventType` as CLAUDE.md §8.1 says. Record the outcome in `limitations.md`.

### B.5 Methods (`common/manage_nodes.py: create_method`, `server/address_space.py: MethodService._call`)

```python
from asyncua import uamethod
@uamethod
def start(parent): ...                 # sync: runs in a thread-pool executor; async def also accepted
node = await tool.add_method(idx, "Start", start, [], [])
```

- The callback may **return `ua.StatusCode(...)`** → that becomes the call's StatusCode (per call, not a service fault).
  Raising any exception → `BadUnexpectedError`. This is how Start()/Stop() return
  `BadUserAccessDenied` / `BadInvalidState`.

### B.6 Intercepting client writes (TempHighLimit)

Three mechanisms exist; findings:

| Mechanism | Verified behaviour | Usable? |
|---|---|---|
| `server.set_attribute_value_setter(nodeid, setter)` | `setter(node_data, attr, datavalue)` is **sync** and replaces the store step; its return value is ignored (write reports Good). Raising `ua.UaStatusCodeError` propagates to `uaprocessor` → whole request answered with a **ServiceFault** carrying that code. Also invoked for the server's own `write_value` calls. | Works, but the status is a service fault, not a per-node result, and server-side updates must bypass it. |
| `server.subscribe_server_callback(CallbackType.PreWrite, fn)` | Called before the write with the request params; cannot veto or set per-node status. | No (cannot reject cleanly). |
| Method `SetTempHighLimit(value)` | Per-call `ua.StatusCode` return (B.5). | Yes, reliable. |

Decision deferred to CP2 with a quick test: preferred is the writable variable with
`set_attribute_value_setter` (so UaExpert can write it directly) if the ServiceFault code reaches the client
as the right `ua.UaStatusCodeError` subclass; otherwise make the variable read-only and expose
`SetTempHighLimit(value)` (CLAUDE.md §8.2 fallback). Either way the write goes through `core.submit_ec_write`.

### B.7 Client side (`client/client.py`, `common/subscription.py`) — for `clients/ua_client.py`

- `async with Client(url) as c:`; `c.get_node(...)`, `await node.get_child([f"{idx}:Name", ...])`, `await node.call_method(f"{idx}:Start")`.
- `sub = await c.create_subscription(period_ms, handler)`; `await sub.subscribe_data_change(nodes)`;
  `await sub.subscribe_events(sourcenode, evtypes=[our_event_types])` — event types must be passed so the
  generated `EventFilter` selects our custom fields.
- Handler callbacks: `datachange_notification(node, val, data)`, `event_notification(event)`, `status_change_notification(status)`.

---

## Part C — Differences from what CLAUDE.md assumes (to handle in later steps)

1. **asyncua version.** Latest is 2.1.0; CLAUDE.md says "latest 1.x", so we pin `asyncua==1.1.8`.
2. **secsgem owns a control state machine.** `GemEquipmentHandler` has its own GEM control state, changed by host
   S1F15/S1F17 and by link loss (A.7). That would be a second owner of state and a **bypass path** (rule 5).
   → The GEM adapter will override `_on_s01f15`/`_on_s01f17` (reply with a refusal, audit the attempt, do not change
   state) and serve SVID 2 from the core only. Library SVID 1002 ControlState and CEIDs 1/2/3/20/21 are removed
   from the dictionaries so a host cannot read a second, diverging control state.
3. **S2F41 always answers HCACK 4.** The library replies "acknowledged, finish later" before running the command,
   so HCACK 0/2/5 from the arbiter cannot be returned. → Override `_on_s02f41` to call `core.submit_command` and
   reply with the mapped HCACK.
4. **S2F15 has its own range check and no authority hook.** It returns EAC 1/3 itself and `on_ec_value_update`
   cannot reject. → Override `_on_s02f15` to call `core.submit_ec_write` and reply with the mapped EAC.
5. **`trigger_collection_events` breaks ordering and value agreement.** One new thread per event (no ordering
   between events → I2), values read at send time instead of event time (→ I3), and silent drops when not
   enabled (→ I6 needs explicit `dropped_disabled`). → The adapter will build each S6F11 itself on its single
   dispatcher worker thread from the values carried in the notification, check link/enable state first and log
   the outcome to `gem_adapter_send.jsonl`.
6. **`set_alarm` sends a fixed ALTX** and needs `ce_on`/`ce_off` CEIDs. CLAUDE.md wants `seq=<n>` in the S5F1 text
   and no extra CEIDs. → The adapter sends S5F1 itself (ALCD bit 0x80 for set) with `seq=<n>` in ALTX and keeps
   `handler.alarms[5001]` only for S5F3/S5F5 bookkeeping.
7. **ECID 201 cannot appear in an S2F33 report.** CEID 1006 lists ECID 201 in its report, but secsgem only accepts
   VIDs that are SVIDs or DVIDs. → Register a data value with VID 201 mirroring the constant (same ID, so the
   report matches CLAUDE.md §4); document in `mapping.md`.
8. **Host-side S6F11 decoding requires `subscribe_collection_event`.** The scripted host must define its reports
   through that call (or override `_on_s06f11`), otherwise received events raise `KeyError`.
9. **OPC UA alarm acknowledge is not implemented by asyncua** (B.4); write interception gives a ServiceFault rather
   than a per-node status (B.6). Both are recorded as candidate entries for `limitations.md`.
