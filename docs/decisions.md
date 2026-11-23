# Design decisions and deviations from CLAUDE.md

Every place where the implementation had to choose something CLAUDE.md leaves open, or deviates from it,
is recorded here with the reason.

| ID | Decision | Reason |
|---|---|---|
| D1 | `asyncua==1.1.8` (not 2.x). | CLAUDE.md §2 says "latest 1.x"; approved by the student at CP0. |
| D2 | Initial control state is `ONLINE_LOCAL` (authority OPERATOR). | Not fixed by CLAUDE.md; approved at CP0. Scenarios switch to REMOTE with the console. |
| D3 | Control-state changes and the lease are also routed through `arbiter.decide` with two extra actions, `SET_CONTROL_STATE` and `SET_LEASE` (allowed for OPERATOR only, in every state). | Rule 5 says every command from any origin goes through the arbiter, including the operator console. CLAUDE.md §4 says control state is "changed by the operator console". Encoding this in the arbiter makes the no-bypass test cover console commands too. The §6.4 table for START/STOP/EC_WRITE is unchanged. |
| D4 | A state change writes separate audit records: `command_ok` (the accepted command), then `state`/`authority`/`ec_write` (the change), then `event` (the CEID). Each has its own seq. The event's DVID 101 `EventSeq` is the seq of the **event** record. `CommandResult.seq` is the seq of the `command_ok`/`*_rejected` record. | Keeps one record per fact, so the audit log can be replayed to reconstruct state (tested in `test_core.py`). The checker joins client data on the event seq. |
| D5 | The harness drives the operator console through a local TCP control socket `127.0.0.1:5100` (one text command per line, one reply line). | CLAUDE.md §9 lets us pick "a small local control socket or command file". A socket gives the harness the command result synchronously; a file would need polling. |
| D6 | `LastEventSeq` (SVID 5) is the seq of the last record of kind `event`, `alarm_set` or `alarm_clear`. It is derived, not separately audited. | Auditing it would create a record for every record. |
| D7 | Unknown RCMD / unknown ECID are rejected **before** the arbiter is consulted (there is no action to decide on). They are still audited as rejections and emit CEID 1005. | Nothing changes, so no bypass is possible. |
| D8 | Rejection codes for operator console commands reuse the HCACK mapping (2 = not allowed / wrong state, 5 = already in requested state). | Gives one uniform `CommandResult` for every command. |
| D9 | `pytest.ini` sets `--basetemp=.pytest_tmp`. | On this Windows machine pytest cannot open the system temp folder (`PermissionError`). Tests are unchanged. |
