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

## CP5-core-scenarios

**Built:** `harness/checker.py` (I1–I6 + latency, markdown/CSV reports, `--self-test` with five corruption
cases), `harness/scenarios.py` (runner: fresh run_id, equipment with seed 42, both listening clients, barrier races
GEM-via-relay vs UA-session, clean shutdown with port check, checker, `results/`), scenarios S3 and S2,
`docs/invariants.md`, `tests/test_checker.py` + committed sample run `runs/sample_S3`.
Hardening for the scenarios: GEM T3 = 3 s and reply-function check (D20), dispatcher drained before the doors
stop, session markers `connecting`/`stopped` in both client logs, robust S6F11 decoding in the host (D23).

**Verified:**
- `python -m harness.scenarios S3`: 50/50 rounds GEM HCACK 0 + UA BadUserAccessDenied. In 3/50 rounds the UA request
  reached the core first and still lost (policy, not timing). LOCAL → GEM START HCACK 2. I1–I6 all PASS
  (163 window events on each side, 0 missing, 0 unexplained; I4 max 14 ms GEM / 89 ms UA).
- `python -m harness.scenarios S2`: alarm set after 19.1 s and cleared 4.4 s after STOP. Both clients saw alarm seqs
  77/98 exactly as the core did. I1–I4 and I6 PASS; I5 N/A.
- `python -m harness.checker runs/sample_S3 --self-test`: baseline clean. drop → I1+I6 (and I5, because the dropped
  event was a CEID 1005), swap → I2, change value → I3, delay → I4, double winner → I5. All flagged.
- `pytest`: 95 passed. No process or port left after each scenario (runner waits until 5000/4840/5100/5101 are free).

**Problems:**
1. First S3 run: I5 FAILED in rounds 1, 18, 21 ("2 accepted"). Investigation of the audit showed the reset STOP that
   follows a round had **the same `time_ns` value** as the round's end time (Windows clock granularity). The
   checker's time window therefore also caught the STOP. There was no double acceptance: the replies were clean in
   50/50 rounds. Root-cause fix in the checker: rounds are anchored on the core seq read before the barrier (D21).
   The invariant was not weakened, and the self-test proves a real double winner is still flagged.

## CP6-scenarios

**Built:** scenarios S5 (GEM host hard-killed for 10 s and restarted), S1 (60 s normal), S4 (10 barrier rounds of
EC conflict + OFFLINE/lease phase), S6 (GEM report redefinition + a second, narrow UA subscription), post-checks
for S4/S5, `results/summary.md` overview, latency p50/p95/max with the caveat in every summary.

**Verified:** `python -m harness.scenarios all` (one invocation for S3, S2, S5, S1, S4) + S6 rerun after a check fix.
All 11 invariant cells PASS or N/A for every scenario. Scenario checks 4/4, 5/5, 2/2, 10/10, 5/5.
- S5: the equipment detected the dead link 136 ms after the kill. The GEM door dropped 11 events, all logged
  `dropped_no_link`, and did not re-send them after reconnection (no spooling). UA missed 0. I6 PASS on both sides,
  meaning every loss is attributed.
- S4: REMOTE conflict 10/10 GEM wins, final limit 35 in core, GEM (S2F13) and UA. Leased UA write 45 → Good, GEM saw
  CEID 1006 with 201=45, GEM write → EAC 2.
- S6: GEM CEID 1007 fields {101,102} → {101} after the host's redefinition. The UA listener stayed at {101,102}, and a second UA
  subscription with an EventFilter got only {CEID, EventSeq}.
- Latency p50 GEM 0–2 ms, UA 38–69 ms (50 ms publishing interval); details in each `results/S*_summary.md`.
- `pytest` 95 passed. Checker self-test re-run on the refreshed sample run: all 6 rows OK.

**Problems / findings:**
1. **S4 I4 UA FAIL on first run**, "seq 18 TempHighLimit=40.0 never observed". Root cause: the first reset wrote 40.0
   while the limit already was 40.0. GEM reports every accepted write (CEID 1006), but OPC UA's default
   DataChangeTrigger (StatusValue) sends no notification when the value does not change. **This is a real semantic
   mismatch, recorded as a finding** (S4 summary, `docs/mapping.md`). I4 was refined, not relaxed: a same-value
   write is not a state change, so for UA the check becomes "the value the client holds equals the core value". That
   is still checked, and a wrong value still fails. The first refinement looked up the value too late (it saw the next
   round's real change). Fixed by bounding the lookup at the next change of the same variable.
2. **S6 crashed while saving scenario.json** (a Python `set` in a check detail is not JSON). Fixed (`sorted(...)`,
   `default=str`). Processes and ports had still been cleaned up.
3. **S6 check failed once** (one CEID 1007 with the old report counted as "after"). Cause: the check split the events at
   the moment the redefinition was *requested*, so an event already in flight was misclassified. Fixed by comparing
   only events received before the request and after the redefinition completed.

## CP7-docs

**Built:** `harness/demo.py` (narrated, Enter between steps, one-line explanation per step; `--auto`,
`--no-live-window`), `docs/architecture.md` (mermaid diagram + component roles + threads), `docs/information_model.md`,
`docs/mapping.md` (status + observed + six semantic mismatches), `docs/arbitration.md`, `docs/novelty.md` (numbers
copied from `results/` only), `docs/panel_qa.md` (12 questions), `docs/limitations.md` (measurement scope + future
work), README (5-line summary, install, demo, scenarios, results table).

**Verified:**
- `python -m harness.demo --auto --no-live-window`: all 8 steps. Alarm seq 79 identical on core, GEM (S5F1 text) and UA
  (EventSeq). Race: GEM HCACK 0 / UA BadUserAccessDenied, loser's CEID 1005 received by both. LOCAL → HCACK 2. GEM host
  killed 10 s → 11 events `dropped_no_link`. Checker verdict on the demo run: overall PASS. All ports released.
- Interactive mode (Enter fed through stdin) **with** the live view opened in its own console window on Windows: same
  result, overall PASS, live-view window closed by the demo, 0 python processes and no ports left afterwards.
- Every number in `novelty.md`, `mapping.md`, `panel_qa.md` and README was checked against `results/*.md`.
  Repo-wide scan for "compliant / certified / companion specification / first / faster than": only negated or
  ordinary uses.
- `pytest`: 95 passed.

**Problems:** in `--auto` mode the GEM host is killed less than 500 ms after the last state changes, so I4 judged
fewer changes for GEM (5) than for UA (8). This is correct behaviour (I4 does not judge a client that could not have
converged before it was killed). With a presenter pressing Enter the gap is seconds.

## Web dashboard (after CP7)

**Built:** `harness/web_view.py` (data layer `RunState`, `LiveSource` that follows the newest run or a given folder,
`ReplaySource` with `--speed`/`--loop`, SSE hub, HTTP server on 127.0.0.1), `harness/web_view.html` (one self-contained
page: header badges, SVG architecture with pulses and GEM-link flash, three columns with disagreement highlighting,
canvas temperature chart with limit + alarm shading, arbiter feed, per-seq event timeline with latency /
dropped markers, live invariants + counters, Results tab with a small markdown renderer, footer "Simulated chamber,
loopback, single laptop"). `tests/test_web_view.py` (3 tests). `demo.py --web [--web-port] [--no-browser]`. `live_view.py`
refactored to share `seed_core`/`values_agree`/`APPLIERS` with the dashboard.

**Verified:**
- `pytest`: 98 passed. `test_page_counters_equal_checker_exactly` feeds `runs/sample_S3` record by record (as replay
  does) and requires the rows (invariant, side, status, detail), counters, overall and latency to equal `checker.py` run on
  the files.
- Replay `--replay runs/sample_S3 --speed 1`: SSE stream carried 153 arbiter decisions, 167 timeline events, 333 receipt
  marks, 332 pulses and invariant updates; final invariants PASS with the checker's counters. The page has no external URL.
  `/api/results` serves all 8 result files. Checked visually in a browser: header, diagram, columns, chart, feed,
  timeline, invariants, Results tab.
- Live: the dashboard ran in follow-newest mode while `python -m harness.scenarios S2 --out .pytest_tmp/webcheck` ran. It
  switched to the new run by itself (2 snapshots), streamed link up → REMOTE → START → alarm on → STOP → alarm off →
  link down, and its final invariants (from `/api/state`) were identical to `checker.check_run` on that run (statuses and
  detail strings).
- `python -m harness.demo --auto --web --no-browser`: dashboard started before the equipment. The stream showed the GEM
  link dropping when the host was killed and coming back 10 s later. Demo overall PASS. Afterwards ports
  5000/4840/5100/5101/8080 were free and no python process was left.

**Problems:**
1. A finished replay kept publishing a delta every 200 ms and re-running the checker every second, because the source
   handed over `scenario.json` on every poll after the end. It now hands it over once.
2. The first live check seemed to show an SSE stream that stopped after the first snapshot. Cause: my verification probe
   set a 1 s socket timeout, and a timeout inside a buffered `readline()` breaks the reader. The probe was rewritten
   (reader thread, no timeout); the server was fine.
3. While cleaning up after a test I tried to kill every `python.exe`. The command was blocked as too broad. I then
   stopped only the dashboard by the PID that owned port 8080.

## Wireshark capture + demo pacing

**Built:** `demo.py --step-delay N` (D27; default 6 s, `--auto` only). The scenario runner's readiness check no longer
connects to the HSMS port (D28). `results/demo_capture.pcapng` + `results/capture_summary.md`. README section.

**Verified:**
- Tools: TShark 4.6.10 at `D:\Wireshark\tshark.exe` (not in `C:\Program Files`). `tshark -D` entry 8 =
  `\Device\NPF_Loopback` "Adapter for loopback traffic capture". A 3 s test capture worked without Administrator rights.
- Capture: `tshark -i \Device\NPF_Loopback -f "tcp port 5000 or tcp port 4840" -w results\demo_capture.pcapng`
  around `python -m harness.demo --web --auto`. tshark was stopped with Ctrl+Break (exit 0, 3837 packets, 509 996 bytes,
  97.9 s). Demo overall PASS.
- `-Y hsms` gave 0 frames, because Wireshark does not map port 5000 to HSMS. `-d tcp.port==5000,hsms -Y hsms` gave 300 frames =
  290 data messages (S1F13 4, S1F3 2, S2F13 2, S2F33 16, S2F35 14, S2F37 16, S2F41 5, S5F3 2, S5F1 2, S6F11 82,
  plus their replies) + 10 control messages (Select, Linktest, Separate).
- `-Y opcua`: 1596 frames (Read 286, Publish 230, Browse 200, Call 1, CreateSubscription 1, …).
- Decoded S6F11 frame 924 = DATAID 18, CEID 1007, EventSeq 18, EventTemp 24.972, identical to the GEM host's log
  record seq 18. Decoded CallResponse: ServiceResult Good, method StatusCode BadUserAccessDenied. The simultaneous
  START is visible on the wire: S2F41 START at .905177, HCACK 00 back, Call Start 3.5 ms later, refused.
- Replay dashboard started on port 8081 (left running on purpose). GET / served the page; 10 s of `/events` carried
  46 deltas (342 decisions, 375 events, 751 receipt marks) and 10 invariant updates.
- `pytest`: 98 passed.

**Problems:**
1. **First capture attempt: the demo failed** ("timed out after 60 s waiting for GEM host listening"). The capture
   itself showed why. The runner's readiness probe connected to port 5000 and closed within 1 ms (FIN, RST) while
   secsgem was sending Select.req. That consumed the single HSMS session, and afterwards port 5000 answered every SYN
   with RST, including the real GEM host's. The same probe had been harmless in earlier runs, so the Npcap loopback
   capture's timing exposed a latent harness bug. Fix in the harness only: wait for the equipment's READY line, and never
   probe the HSMS port of a running equipment (D28). The secsgem behaviour is recorded in `library_notes.md` Part E
   and `limitations.md`. GEM door unchanged.
2. A leftover `python.exe` after the failed attempt turned out to be an unrelated application of the user
   (`cfm_station.py`). It was left alone, and process checks now look only at this project's ports and processes.
- **Live demo watched by the student in the browser** (`python -m harness.demo --web --auto --step-delay 8 --no-browser`,
  run `DEMO_20261124-024251`): alarm seq 148 identical on core, GEM (S5F1) and UA (EventSeq). Race: GEM HCACK 0 / UA
  BadUserAccessDenied, loser's CEID 1005 (seq 184) received by both. LOCAL → HCACK 2. GEM host killed 10 s → 11 events
  `dropped_no_link`. Checker: I1–I6 all PASS, overall PASS. Afterwards ports 5000/4840/5100/5101/8080 were free; only the
  intentional replay dashboard (8081) and an unrelated user application were running.

## Dashboard: control panel, wire panel, model browser, policy, race demo

**Built:** `harness/control_panel.py` (P1 system start/stop + 14 commands via protocol entry points; P3 browse; P4
policy table from `arbiter.decide`; tshark packet counter), `equipment/wire_log.py` + hooks in `equipment/main.py` and
`clients/gem_host.py` (P2 SECS-II SML wire log), UA wire logging + `browse_tree()` in `clients/ua_client.py`,
`harness/race_demo.py` (P5), page sections Control / On the wire / Inside tab (policy, model browser, race),
`tests/test_control_panel.py` (3 tests). No core, arbiter, adapter or checker code changed.

**Verified** (dashboard live on 8080, every endpoint driven by an HTTP client, then key buttons pressed in a browser):
- Start system → `PANEL_20261124-144639` running. Real replies with the core's reasons: GEM START in LOCAL → HCACK 2
  "equipment in LOCAL"; after REMOTE → HCACK 0, again → HCACK 5 "already EXECUTING"; UA Start → BadUserAccessDenied
  "authority held by GEM_HOST"; GEM limit 81 → EAC 3 (range), 35 → EAC 0; UA limit 45 in REMOTE → BadUserAccessDenied;
  OFFLINE + lease → UA limit 45 Good, GEM limit 30 → EAC 2 "maintenance lease held by UA_CLIENT"; Both START at once
  in REMOTE → GEM HCACK 0 / UA BadUserAccessDenied, under lease → GEM HCACK 2 / UA Good; Kill / Reconnect GEM host
  worked. POST without `X-Panel` → 403. Commands before start → "start the system first".
- Wire panel: 200 SECS-II messages with SML (e.g. S6F11 W with DATAID/CEID/EventSeq/EventTemp, S6F12) and 166 UA
  records (Publish notifications, Call with status). Model browser: real browse, 25 nodes, 6 GEM-mapped variables
  with units. Policy table equals `docs/arbitration.md` and highlights the active row. Race demo: unsafe 200/200 double
  winners, real core 0/200 (CLI `python -m harness.race_demo`: same numbers). tshark counter: 434 packets on 5000,
  1980 on 4840.
- Stop system → **checker PASS** on the panel-driven run (I1–I6 PASS, I5 with 2 panel conflict rounds, GEM
  5 losses all `dropped_no_link` from the kill). A second run driven by browser button presses
  (`PANEL_20261124-144724`): checker PASS. Ports free afterwards.
- `pytest`: 101 passed.

**Problems:**
1. A shell heredoc could not carry the long patch scripts (quoting). The patches were written as files and applied.
2. "Both START at once" pressed in LOCAL would make I5 fail, because both are rejected by policy and that is not a conflict.
   Rule D31: such presses are shown but not counted as conflict rounds.
3. The local clock was 14:40 when this task started, so the "stop by 5:00 AM" timebox had already passed. Worked to the
   stated 2-hour timebox instead.
