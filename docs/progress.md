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
