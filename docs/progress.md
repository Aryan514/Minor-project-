# Build progress log

One entry per checkpoint: what was built, how it was verified, and problems hit.

## CP0-scaffold

- Repo layout, pinned `requirements.txt` (secsgem 0.3.0, asyncua 1.1.8), `equipment/config.py`, README skeleton,
  `docs/library_notes.md` written from the installed library source.

## CP1-core

**Built:** `equipment/audit.py` (seq counter + flushed JSONL), `equipment/arbiter.py` (pure policy),
`equipment/core.py` (EquipmentCore with atomic decide-and-apply), `equipment/dispatcher.py` (bounded
per-subscriber queues + workers), `equipment/sensors.py` (SimulatedChamber, SerialESP32, SamplingThread),
tests `test_arbiter.py`, `test_core.py`, `test_race.py`, `test_dispatcher.py`.

**Verified:**
- `python -m pytest -q` → `93 passed`. This covers all 54 arbiter combinations plus the operator-only actions,
  the no-bypass deny-all test (15 entry points), 4 × 500 race iterations, and dispatcher order/isolation/overflow.
- End-to-end sim run (core + SimulatedChamber, seed 42): REMOTE → GEM START → alarm 5001 set after 19.0 s of model
  time at 40.21 °C → GEM STOP → alarm cleared at 38.92 °C (below 40 − 1.0). With the real-time SamplingThread,
  CEID 1007 is emitted once per second.

**Problems:** pytest could not open the Windows system temp dir (`PermissionError: [WinError 5]`). Fixed with
`pytest.ini --basetemp=.pytest_tmp` (decision D9). No code or test was weakened.

## CP2-opcua

**Built:** `equipment/opcua_model.py` (types first: GemMappedVariableType, ChamberType, SemiEquipmentType,
GemCollectionEventType, GemOffNormalAlarmType, GemAlarmEventType fallback; then the Chamber1Tool instance by
instantiation), `equipment/opcua_adapter.py` (server door, methods Start/Stop/SetTempHighLimit, send-side log),
`equipment/console.py` (stdin console + control socket 127.0.0.1:5100), `equipment/main.py`, `clients/ua_client.py`.

**Verified** (run `cp2-check`, `python -m equipment.main --no-gem --no-console`):
- `python -m clients.ua_client --browse` printed the full tree from the server. It shows types and `<-> GEM SVID 1 (F4)` on
  each GEM-mapped variable (SVIDs 1–5, ECID 201), plus the three event types and their fields.
- Method calls via `ua_client`: Start in LOCAL → `BadUserAccessDenied`; console `offline` + `lease ua`;
  Start → `Good`; Start again → `BadInvalidState`; `--set-limit 99` → `BadOutOfRange`; `--set-limit 20` → `Good`
  (alarm set); Stop → `Good`; `--set-limit 45` → `Good` (alarm cleared).
- Listener (`--listen`): received the 24 of 24 core events/alarms in its window. Missing 0, duplicates 0, in order.
  It saw CEIDs 1001–1007 including three CEID 1005 rejections with reason text, plus alarm 5001 set (seq 82) and clear (seq 98)
  through the **Alarms & Conditions** path (GemOffNormalAlarmType, `ActiveState/Id`).
- UA send-side log: 25 `sent`, 27 `dropped_no_link` (events before any client subscribed).
- Console `quit` shut the process down. Ports 4840/5100 were free afterwards.
- `pytest`: 93 passed.

**Problems:**
1. `BadNodeIdUnknown` after instantiation. Nested declarations (GemId under each mapped variable,
   `Chamber1.Temperature`) were not copied, because asyncua's `instantiate` does not copy `HasModellingRule`. Fixed by
   marking the whole type tree Mandatory (`_mark_tree_mandatory`), and doing it for ChamberType *before*
   ChamberType is instantiated inside SemiEquipmentType.
2. `Server.create_custom_variable_type` creates an ObjectType (library quirk), so the VariableType is created with
   `add_variable_type`.

## CP3-gem

**Built:** `equipment/gem_adapter.py` (GemEquipmentHandler subclass + GemAdapter, overrides O1–O9 in
`docs/library_overrides.md`), `clients/gem_host.py` (listener with JSONL log + relay port, one-shots).
`main.py` now starts the GEM door and cleans up even if startup fails half-way.

**Verified** (run `cp3-final`, both doors up, `python -m equipment.main --no-console`):
- S1F13/F14: the listener reached COMMUNICATING. The core audited `GemCommunicationState = COMMUNICATING`, mirrored to UA.
- S2F33/35/37: one report per CEID defined, linked and enabled. S5F3 enabled ALID 5001.
- S1F3 (`--status`): SVIDs 1–5 from the core (ChamberTemp, ControlState 4/5, ProcessingState, Authority, LastEventSeq).
- S2F41: START in LOCAL → HCACK 2; after console `remote` → HCACK 0; again → HCACK 5. STOP → HCACK 0.
- S2F15: 81 → EAC 3, 21 → EAC 0 (alarm set), 45 → EAC 0 (alarm cleared).
- S6F11: 51/51 core events received in the listener window. Missing 0, duplicates 0, in seq order. Every report
  carries DVID 101 EventSeq, and CEID 1006 carries ECID 201 (`{'201': 21.0}`).
- S5F1: `ChamberOverTemp SET T=26.18 seq=52` (ALCD 0x84) and `CLEAR … seq=67` (ALCD 0x04), matching the audit.
- Send log: 52 `sent`, 8 `dropped_no_link` (no host connected).
- Reconnect: after the listener left, two more host sessions connected. The link state alternated in the audit.
- Host with no equipment running exits after ~21 s instead of hanging. `quit` stops the equipment with and without a
  connected host. Ports 4840/5000/5100/5101 free, 0 tracebacks in the equipment output.
- `pytest`: 93 passed.

**Problems:**
1. Tracebacks `WinError 10057` from secsgem's accept thread after each connect, and the listening socket leaked.
   Cause: `shutdown()` on a listening socket fails on Windows. → O9 override.
2. `quit` hung when no host had connected. Cause: secsgem `disable()` waits for a flag that its dying accept thread
   never clears (`UnboundLocalError` in the `select()` error path). Found by testing shutdown with and without a host.
   → same O9 override guarantees close + flag reset.
3. A later run could not establish GEM communication. Cause: two `gem_host --listen` processes from an earlier failed
   test were still alive. When `connect()` timed out they raised before disabling the handler, and secsgem's
   non-daemon connect thread kept retrying, grabbing the single HSMS session as soon as the equipment started.
   Fixed in `gem_host.py` (disable on failure, cleanup in `finally`). The leaked processes were killed.

## CP4-dual

**Built:** `harness/live_view.py` (rich three-column view: GEM host sees | Core (truth) | OPC UA client sees; tails
the run's JSONL logs; disagreeing cells shown red). `gem_host --listen` now logs an initial S1F3 + S2F13 snapshot.
README run instructions.

**Verified** (run `cp4-dual`, scripted end-to-end check). Equipment + `gem_host --listen` + `ua_client --listen` running together:
1. LOCAL: live view shows ControlState ONLINE_LOCAL / Authority OPERATOR / limit 40 identical in all three columns.
2. Console `remote` → GEM START → HCACK 0. Alarm 5001 set in the core after 18.8 s at 40.18 °C.
3. UA Start while REMOTE → `BadUserAccessDenied`. CEID 1005 (seq 93, origin UA_CLIENT, "authority held by GEM_HOST")
   received by **both** clients.
4. Live view at that moment: EXECUTING / GEM_HOST / Alarm SET / last seq 98 / same last rejection in all three columns.
5. GEM STOP → HCACK 0. Alarm cleared after 6.5 s at 38.92 °C. Live view shows IDLE / clear in all columns.
6. Log cross-check: GEM 42/42 and UA 42/42 events in their windows. Missing 0, duplicates 0, in order, 0 value
   mismatches vs the core payload (1e-3). Alarm seqs 89/122 identical in core, GEM and UA.
7. State changes visible on GEM within 1.3–14.5 ms (CEIDs 1001/1004/1002/1003) and on UA within 46–49 ms
   (variable data changes, 50 ms publishing interval).
8. `quit` → equipment exit code 0. No listening ports left (5000/4840/5100/5101).
- `pytest`: 93 passed.

**Problems:**
1. The first verification run printed no live-view table. Cause: my verification script decoded the child's UTF-8
   box-drawing output as cp1252. Fixed in the script (`encoding="utf-8"`). The view itself was fine.
2. The core column could not show TempHighLimit before the first write, because the audit has only changes. The core
   column is now seeded from `config.py` start values (D18), and the GEM snapshot now includes S2F13 (D19).
3. The GEM temperature legitimately lags by up to 1 s (1 Hz events). The live-view tolerance for that row is now
   1 °C, so a normal lag is not shown as a disagreement.
