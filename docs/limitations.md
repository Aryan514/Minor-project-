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

## Future work

_(filled as items are deferred)_

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
