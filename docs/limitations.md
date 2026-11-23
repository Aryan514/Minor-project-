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
- asyncua 1.1.8 has no server-side Acknowledge/Confirm logic for Alarms & Conditions. The outcome of the
  90-minute A&C time box will be recorded here at CP2.
- Write interception for TempHighLimit: the final choice between a value setter and a method will be
  recorded here at CP2.

## Future work

_(filled as items are deferred)_
