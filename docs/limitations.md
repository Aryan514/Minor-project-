# Limitations and future work

Living list. Every simplification, fallback or out-of-scope idea is recorded here as it comes up.

## Design simplifications (by intent, CLAUDE.md §4)

- **Simplified GEM control state.** Only EQUIPMENT_OFFLINE, ONLINE_LOCAL and ONLINE_REMOTE. HOST_OFFLINE and
  ATTEMPT_ONLINE are omitted. Control state is changed only by the operator console; host requests
  S1F15/S1F17 are refused (see `library_notes.md` Part C item 2).
- **Initial control state** is ONLINE_LOCAL (operator authority). CLAUDE.md does not fix it; scenarios switch
  to REMOTE explicitly with the console `remote` command.
- **Single simulated tool on one laptop (loopback).** No fab-scale or real-fab validation.
- **OPC UA security:** NoSecurity + anonymous for the demo only.
- **No GEM spooling.** secsgem 0.3.0 does not implement it, and OPC UA has no equivalent. This is measured
  in scenario S5, not fixed.

## Library constraints found at CP0 (see `library_notes.md` Part C)

- secsgem's built-in S2F41 / S2F15 / S1F15 / S1F17 handlers and `trigger_collection_events` are overridden
  or bypassed by the GEM adapter so that the core and arbiter stay the only authority.
- **OPC UA alarm (A&C time box outcome, CP2): partial A&C.** ALID 5001 is sent as `GemOffNormalAlarmType` events
  (a subtype of `OffNormalAlarmType` with `ALID` and `EventSeq`). They carry ActiveState/Id, Retain, ConditionName,
  ConditionId (`NodeId` = `Alarms/ChamberOverTemp`), Severity and Message, and `ConditionRefresh` replays the active
  alarm. **Not implemented:** the server-side condition state machine and the `Acknowledge`/`Confirm`/`Enable`
  methods. asyncua 1.1.8 has no server logic for them, so a client calling Acknowledge gets `BadNothingToDo`.
  `Alarms/ChamberOverTemp` is a plain object (ALID, AlarmText, Active), not a full `OffNormalAlarmType`
  instance. The `GemAlarmEventType` fallback is in the model and is used automatically only if the A&C
  event cannot be built.
- **TempHighLimit over OPC UA** is read-only. Writes use the `SetTempHighLimit(value)` method (decision D10).
  A generic UA client therefore cannot "write the variable"; it must call the method.

## Measurement scope (CP5–CP6)

- One simulated tool, one Windows laptop, loopback only, seed 42, scenario durations of 5–62 s. There are no fab-scale,
  network, long-duration or throughput results.
- One GEM host at a time (one HSMS session). Multi-host GEM and multiple concurrent UA clients with commands were not
  tested (S6 used a second, read-only UA subscription).
- OPC UA without security (NoSecurity, anonymous). No user/role model maps to the arbiter's origins: any UA client is
  `UA_CLIENT`.
- I4 uses T = 500 ms. A state change that happens less than T before a client is killed is not judged for that
  client (it could not have converged).
- A same-value EC write is not a UA data change (S4 finding). For UA, I4 checks that such writes leave the client
  value equal to the core value, rather than expecting a notification.

## Future work

- GEM spooling (S6F11 buffering while the link is down) and an OPC UA equivalent, such as buffered events or history
  read, so the S5 losses could be recovered rather than only attributed.
- Server-side Alarms & Conditions state machine (Acknowledge/Confirm) and a defined mapping of UA acknowledgement to
  the core. Today S5F2 and UA Acknowledge mean different things (`mapping.md`).
- Per-CEID UA event types (instead of a JSON `Payload`), so UA clients can filter individual DVs.
- Export of the model as a NodeSet2 XML for use in other tools.
- OPC UA security (signing/encryption, user tokens) and mapping UA users to arbiter origins.
- Full GEM control-state model (HOST_OFFLINE, ATTEMPT_ONLINE) and multi-host scenarios.
- Real ESP32 sensor runs (`--sensor serial`) and Wireshark captures per protocol (CLAUDE.md step 9).

## Observed at CP4 (to be measured properly by the scenarios)

- **GEM sees the temperature only at 1 Hz** (CEID 1007). OPC UA gets every 0.5 s sample as a data change. The
  live view therefore allows 1 °C difference on the temperature row. Exact value agreement is checked per seq.
- **UA latency is dominated by the subscription publishing interval** (50 ms in `ua_client`). CP4 run: UA p50 ≈ 37 ms
  vs GEM p50 < 1 ms on loopback. This reflects the client's chosen interval, not protocol speed, and must not be
  presented as "GEM is faster".
- **Clock resolution:** latencies are `time.time_ns()` differences between processes on one machine. Windows clock
  granularity makes values below ~1 ms unreliable.
- **Report definitions outlive the host session** (secsgem keeps them in the equipment handler). A later host
  session that did not define reports still receives S6F11 for the old ones. This is GEM-like behaviour, recorded
  for the report-scope discussion (S6).
