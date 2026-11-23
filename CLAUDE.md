# CLAUDE.md — Dual-Interface Semiconductor Equipment Testbed (SECS/GEM + OPC UA)

## 0. Context (read fully before writing any code)

Final-year minor project. **Deadline: 2 days.** Built from scratch; the repo is empty.
Developer: student on **Windows** (code must also run on Linux/macOS). The student must be able to
explain every file to an evaluation panel, so clarity beats cleverness.

### What we are building
One simulated semiconductor process tool (a single heated chamber, "Chamber1Tool"). Its state lives
in ONE equipment core and is served **simultaneously** through:
- a **SECS/GEM** equipment interface (HSMS over TCP, port 5000), using the `secsgem` library, and
- an **OPC UA** server (port 4840) with a **GEM-derived information model**, using the `asyncua` library.

A **control-authority arbiter** decides who may command the tool. A **consistency harness** proves
whether both interfaces observe the same truth, and where they diverge.

### Why it matters (one paragraph the code and docs must stay faithful to)
Fab hosts use SECS/GEM; newer systems (analytics, digital twins, sub-fab, non-semiconductor MES) use
OPC UA, so tools are increasingly asked to offer both. Prior work (Golra & Engel, IEEE ETFA 2021) mapped
GEM to OPC UA but explicitly did NOT study both interfaces in use simultaneously and omitted spooling.
Translators/gateways already exist (Agileo 2020, ErgoTech TransSECS, Sun et al. IEEE ICWCSG 2021), so we
are NOT building "just a gateway".

### The three novel contributions (everything must trace back to these)
- **N1 — Single-core dual-interface architecture + control-authority arbiter.** One authoritative core,
  two protocol adapters as thin "doors", one arbiter for every command from any origin, decision and
  state change applied atomically.
- **N2 — GEM-derived OPC UA draft information model + documented semantic mismatches** observed under
  simultaneous use (report scope, alarm-acknowledge meaning, spooling, command authority).
- **N3 — Cross-interface consistency test method**: a global sequence-numbered audit log as the oracle,
  send-side and receive-side logs on both protocols, and a checker that evaluates formal invariants under
  normal, conflict and fault scenarios.

## 1. Hard rules for Claude Code

1. **Scope is frozen.** Build only what is in this file. Anything else → `docs/limitations.md` as future work.
2. **Verify library APIs before using them.** `secsgem` 0.3.x differs from older tutorials. Read the installed
   package source (`python -c "import secsgem; print(secsgem.__file__)"`) and docs before writing handler code.
   Same for `asyncua` (events, alarms/conditions, methods, write callbacks). Never guess method names.
   Write a short `docs/library_notes.md` recording the exact classes/methods you used and where you found them.
3. **Runs with no hardware.** Default sensor = simulated. ESP32 is optional (`--sensor serial --port COM3`).
4. **Adapters own no state.** They read from the core and submit commands to it. Nothing else.
5. **Every command, from any origin, goes through the arbiter**: GEM RCMD, GEM EC write, UA method, UA write,
   operator console. No bypass paths. A test must prove this.
6. **Every state change is audited** with a global monotonic sequence number, assigned under the core lock.
7. **One build step at a time.** After each step: run it, run `pytest`, confirm, then commit. Stop at each
   checkpoint and print a short summary of what works.
8. **Honest naming only.** Never write "GEM compliant", "certified", "companion specification", "first",
   or "faster than". Use "GEM-inspired", "draft information model", "to our knowledge".
9. Type hints and docstrings everywhere. Each module starts with a 3–5 line comment: what it does and which
   novelty item (N1/N2/N3) it serves.
10. A failure in one adapter must never crash the core or the other adapter (catch, log, keep running).

## 2. Tech stack
- Python 3.11 or 3.12
- `secsgem==0.3.0` (HSMS + GEM handlers). WARNING: the unrelated package `secsgem-driver` also imports as
  `secsgem` — never install it.
- `asyncua` latest 1.x (pin exact version via `pip freeze` into `requirements.txt`)
- `pyserial`, `pytest`, `rich` (terminal demo view)
- External viewing tools (not deps): UaExpert, Wireshark (has HSMS and OPC UA dissectors)

## 3. Repository layout
```
.
├── CLAUDE.md
├── README.md                    # install, run, demo script, results summary
├── requirements.txt
├── equipment/
│   ├── __init__.py
│   ├── config.py                # ALL IDs, ports, defaults (single source of truth)
│   ├── audit.py                 # sequence counter + JSONL audit writer          (N3)
│   ├── core.py                  # EquipmentCore: state, alarms, events, dispatch  (N1)
│   ├── arbiter.py               # pure authority policy                          (N1)
│   ├── dispatcher.py            # per-adapter ordered event queues               (N1)
│   ├── sensors.py               # SimulatedChamber, SerialESP32
│   ├── gem_adapter.py           # secsgem equipment door                         (N1, N2)
│   ├── opcua_model.py           # builds the GEM-derived address space           (N2)
│   ├── opcua_adapter.py         # asyncua server door                            (N1, N2)
│   ├── console.py               # operator console
│   └── main.py                  # python -m equipment.main [--sensor sim|serial]
├── clients/
│   ├── gem_host.py              # scripted GEM host, JSONL receive log           (N3)
│   └── ua_client.py             # scripted OPC UA client, JSONL receive log      (N3)
├── harness/
│   ├── scenarios.py             # S1..S6 runner                                  (N3)
│   ├── checker.py               # invariant checks → results/                    (N3)
│   ├── live_view.py             # side-by-side terminal view: GEM | core | UA
│   └── demo.py                  # narrated panel demo
├── firmware/esp32_ds18b20/esp32_ds18b20.ino
├── tests/
│   ├── test_arbiter.py          # full truth table
│   ├── test_core.py             # invariants, audit, no-bypass
│   ├── test_race.py             # concurrent command stress                      (N1 evidence)
│   └── test_dispatcher.py       # ordering, slow-consumer isolation
├── runs/<run_id>/               # JSONL logs (gitignored except one sample run)
├── results/                     # checker outputs (committed)
└── docs/
    ├── architecture.md          # diagram (mermaid) + component roles
    ├── information_model.md     # address-space tree + design decisions          (N2)
    ├── mapping.md               # GEM → OPC UA mapping + observed gaps           (N2)
    ├── arbitration.md           # policy table + rationale                       (N1)
    ├── invariants.md            # formal definitions I1..I6                      (N3)
    ├── novelty.md               # claim → code → test → evidence (filled from results)
    ├── library_notes.md
    └── limitations.md
```

## 4. Equipment definition (single source: `equipment/config.py`)

### Status variables (SVIDs)
| SVID | Name | GEM fmt | Unit | Notes |
|---|---|---|---|---|
| 1 | ChamberTemp | F4 | degC | from sensor |
| 2 | ControlState | U1 | — | 1=EQUIPMENT_OFFLINE, 4=ONLINE_LOCAL, 5=ONLINE_REMOTE |
| 3 | ProcessingState | U1 | — | 0=IDLE, 1=EXECUTING |
| 4 | Authority | A | — | GEM_HOST / OPERATOR / UA_CLIENT |
| 5 | LastEventSeq | U4 | — | last audit seq |

### Data variables (DVIDs, valid only inside event reports)
| DVID | Name | Fmt |
|---|---|---|
| 101 | EventSeq | U4 (audit seq — the checker's join key) |
| 102 | EventTemp | F4 |
| 103 | RejectReason | A |
| 104 | Origin | A (who caused the event) |

### Equipment constants (ECIDs)
| ECID | Name | Fmt | Unit | Min | Max | Default |
|---|---|---|---|---|---|---|
| 201 | TempHighLimit | F4 | degC | 20 | 80 | 40 (≈2 °C above room temp with real ESP32) |

### Collection events (CEIDs)
| CEID | Name | Report (DVIDs/SVIDs) |
|---|---|---|
| 1001 | ControlStateChanged | 101, 104, SVID2 |
| 1002 | ProcessingStarted | 101, 104, 102 |
| 1003 | ProcessingStopped | 101, 104, 102 |
| 1004 | AuthorityChanged | 101, 104, SVID4 |
| 1005 | CommandRejected | 101, 104, 103 |
| 1006 | TempHighLimitChanged | 101, 104, ECID201 |
| 1007 | TempSample (every 1 s) | 101, 102 |

### Alarm (ALID)
| ALID | Name | Set | Clear |
|---|---|---|---|
| 5001 | ChamberOverTemp | temp > TempHighLimit | temp < TempHighLimit − 1.0 (hysteresis) |
Alarm set/clear are also audited and carry a seq on both interfaces.

### Remote commands (RCMDs)
| RCMD | Effect | Valid when |
|---|---|---|
| START | IDLE → EXECUTING (heater on) | ProcessingState == IDLE |
| STOP | EXECUTING → IDLE (heater off) | ProcessingState == EXECUTING |

### Simplified GEM control state (document the simplification)
EQUIPMENT_OFFLINE, ONLINE_LOCAL, ONLINE_REMOTE only (HOST_OFFLINE, ATTEMPT_ONLINE omitted). Changed by the
operator console. Each change emits CEID 1001 and updates UA ControlState.

## 5. Sensors (`sensors.py`)
Common interface: `read() -> float`, `set_heater(on: bool)`.
- `SimulatedChamber`: sample every 0.5 s, ambient 25.0 °C. Heater on → rises toward 60 °C at ~0.8 °C/s.
  Heater off → decays toward ambient at ~0.5 °C/s. Noise ±0.05. Seedable (`--seed`) for reproducible runs.
  Result: START → temperature crosses 40 → ALID 5001 set on both sides → STOP → cools → alarm clears.
- `SerialESP32`: reads JSON lines `{"seq":n,"t_ms":ms,"temp_c":x}` at 115200; heater → sends "H1\n"/"H0\n"
  (LED). If the port disappears: log, mark sensor fault, keep the core running.

## 6. Core architecture (N1) — the heart of the project

### 6.1 `audit.py`
- Global monotonic `seq` (int, starts at 1). JSONL file `runs/<run_id>/core_audit.jsonl`.
- Record: `{seq, ts_ns, kind, id, value, origin, extra}`; `ts_ns = time.time_ns()`.
- `kind` ∈ `sample | event | alarm_set | alarm_clear | state | authority | command_ok | command_rejected | ec_write | ec_rejected`.
- Flush each line (the harness reads files after a run; crash-safety matters more than speed).

### 6.2 `core.py` — `EquipmentCore`
- The ONLY owner of state: SVIDs, ECIDs, control state, processing state, authority, active alarms, lease flag.
- One `threading.RLock` guards all state (secsgem uses threads; asyncua uses asyncio).
- **Atomic decide-and-apply:** `submit_command(origin, rcmd, params)` and `submit_ec_write(origin, ecid, value)`
  acquire the lock, call the arbiter, check state preconditions, apply the change, assign seq(s), write audit,
  enqueue notifications — all before releasing. This guarantees two simultaneous STARTs cannot both succeed
  (no check-then-act race). Return `CommandResult(ok, gem_code, ua_status, reason, seq)`.
- `on_sample(temp)` updates SVID1, evaluates alarm hysteresis, emits CEID 1007 at 1 Hz.
- Notifications are published to the dispatcher in seq order while holding the lock (enqueue only; delivery
  happens on adapter threads/tasks).

### 6.3 `dispatcher.py`
- One FIFO queue + one worker per subscriber (GEM adapter, UA adapter, live view). The core only enqueues.
- Guarantees: per-subscriber delivery in seq order; a slow, blocked or disconnected subscriber cannot block
  the core or other subscribers (bounded queue, size 10 000; on overflow drop oldest and audit `kind=dropped`).
- UA subscriber hops into the asyncio loop via `loop.call_soon_threadsafe`.

### 6.4 `arbiter.py` — pure function, no I/O
`decide(control_state, lease_ua, origin, action) -> Decision(allowed: bool, reason: str)`
Origins: `GEM_HOST`, `UA_CLIENT`, `OPERATOR`. Actions: `START`, `STOP`, `EC_WRITE`.

| Control state | Authority | GEM_HOST | UA_CLIENT | OPERATOR |
|---|---|---|---|---|
| ONLINE_REMOTE | GEM_HOST | allowed | rejected: "authority held by GEM_HOST" | STOP only (safety override) |
| ONLINE_LOCAL | OPERATOR | rejected: "equipment in LOCAL" | rejected: "equipment in LOCAL" | allowed |
| EQUIPMENT_OFFLINE | OPERATOR | rejected: "equipment OFFLINE" | rejected: "no maintenance lease" | allowed |
| EQUIPMENT_OFFLINE + lease | UA_CLIENT | rejected: "maintenance lease held by UA_CLIENT" | allowed | allowed |

- Reads (S1F3, browse, read, subscribe) are always allowed — the arbiter only governs writes/commands.
- Lease: console `lease ua` valid only in EQUIPMENT_OFFLINE; `lease off` revokes; leaving OFFLINE revokes.
- Authority changes → audit `authority` + CEID 1004 + UA Authority variable.
- Rejections → audit `command_rejected`/`ec_rejected` + CEID 1005 on both interfaces (both sides learn about
  the other side's rejected attempt — this is part of the N1 design).
- Code mapping:
  - S2F42 HCACK: 0 ok; 1 unknown RCMD; 2 cannot perform now (authority/state); 5 already in requested state.
  - S2F16 EAC: 0 ok; 1 unknown ECID; 2 denied (authority); 3 out of range.
  - UA: authority → `BadUserAccessDenied`; wrong state → `BadInvalidState`; range → `BadOutOfRange`; unknown → `BadNotFound`.

## 7. GEM door (`gem_adapter.py`) — N1/N2
- `secsgem` `GemEquipmentHandler` (verify exact 0.3.0 API). Passive HSMS, port 5000, device id 0,
  MDLN "CHAMBER-SIM", SOFTREV "0.1". Register SVIDs, ECIDs, CEIDs (with DVIDs), ALID 5001 from `config.py`.
- Supports: S1F1/F2, S1F3/F4, S1F11/F12, S1F13/F14, S2F13/F14, S2F15/F16 (→ core.submit_ec_write),
  S2F33/F35/F37 (library's dynamic reports), S2F41/F42 (→ core.submit_command), S5F1 out, S6F11 out.
- Every S6F11 includes DVID 101 EventSeq; S5F1 text includes `seq=<n>`.
- **Send-side log** `runs/<id>/gem_adapter_send.jsonl`: for every event/alarm the adapter receives from the
  dispatcher, log `{seq, ts_ns, kind, id, outcome}` with outcome ∈ `sent | dropped_no_link | dropped_disabled | error`.
  This makes the "no spooling" finding provable (events lost while the host was disconnected are logged as
  `dropped_no_link`), and distinguishes adapter loss from network/client loss.
- Track GEM communication state (link up/down) and mirror it to UA `GemInterface/CommunicationState`.

## 8. OPC UA door + information model — N1/N2

### 8.1 `opcua_model.py` (pure model construction, documented in docs/information_model.md)
Namespace URI `urn:minor-project:semi-equipment-mini`. Build in code (no NodeSet tooling in this sprint).
Create **types first, then the instance** (so it is a reusable model, not ad-hoc nodes):
- ObjectType `SemiEquipmentType`; ObjectType `ChamberType`.
- VariableType or property convention `GemMappedVariable`: every GEM-mapped variable carries properties
  `GemId` (UInt32), `GemKind` ("SVID"/"ECID"), `GemFormat` (e.g. "F4").
- EventType `GemCollectionEventType` (subtype of BaseEventType): fields `CEID` UInt32, `EventSeq` UInt32,
  `Origin` String, `Payload` String (JSON of report values).
- Alarm: try a real Alarms & Conditions instance (OffNormalAlarmType or AlarmConditionType via asyncua) with
  ActiveState, Message=ALTX, Severity, plus `ALID` and `EventSeq`. **Time box 90 minutes.** If asyncua support
  is insufficient, fall back to `GemAlarmEventType` (BaseEventType subtype: `ALID`, `Active` Bool, `EventSeq`,
  `Text`) and record the fallback honestly in limitations.md.

Instance tree:
```
Objects/Chamber1Tool (SemiEquipmentType)
├── Identification/ Manufacturer, Model="CHAMBER-SIM", SoftwareRevision="0.1"
├── GemInterface/
│   ├── ControlState (String) + ControlStateId (Byte; = SVID 2)
│   ├── Authority (String; = SVID 4)
│   ├── CommunicationState (String: GEM link COMMUNICATING / NOT_COMMUNICATING)
│   └── LastEventSeq (UInt32; = SVID 5)
├── ProcessingState (String) + ProcessingStateId (Byte; = SVID 3)
├── Chamber1 (ChamberType)
│   └── Temperature (Double, EngineeringUnits EUInformation degC, EURange 0..100; GemId=1, SVID)
├── EquipmentConstants/
│   └── TempHighLimit (Double, writable; EURange 20..80; GemId=201, ECID) — writes routed to arbiter
├── Alarms/ChamberOverTemp (ALID 5001)
└── Methods: Start(), Stop()  → core.submit_command(origin=UA_CLIENT); return mapped StatusCode
```
- The Temperature node also gets a non-hierarchical reference or property linking to its GEM ID so a client
  can navigate UA node ↔ GEM ID (document how).
- Every value update sets `SourceTimestamp` from the core ts.

### 8.2 `opcua_adapter.py`
- asyncua server on `opc.tcp://0.0.0.0:4840/semi-equipment/`, NoSecurity + anonymous for the demo (documented).
- UA writes to TempHighLimit must be intercepted and routed through `core.submit_ec_write` (verify the asyncua
  mechanism for write interception; if not reliable, expose a `SetTempHighLimit(value)` Method and make the
  variable read-only — document the choice).
- **Send-side log** `runs/<id>/ua_adapter_send.jsonl` with the same shape as the GEM send log.

## 9. Operator console (`console.py`)
stdin thread. Commands: `remote`, `local`, `offline`, `lease ua`, `lease off`, `start`, `stop`, `limit <x>`,
`status`, `quit`. All go through the core/arbiter with origin OPERATOR. The harness drives the same functions
via a small local control socket or command file (choose the simplest reliable option, document it).

## 10. Clients (independent processes)
- `clients/gem_host.py`: secsgem `GemHostHandler`, active to localhost:5000. `--listen`: establish comm,
  define/link/enable reports for all CEIDs, enable alarms, log every S6F11/S5F1 to `runs/<id>/gem_host.jsonl`
  as `{ts_ns, kind, id, seq, data}`. One-shot actions: `--start`, `--stop`, `--set-limit X` (log the reply code).
- `clients/ua_client.py`: asyncua client; subscribes to all mapped variables and to events from Chamber1Tool.
  Logs to `runs/<id>/ua_client.jsonl` same shape. One-shot: `--start`, `--stop`, `--set-limit X`, `--browse`
  (prints the discovered tree with GEM IDs — used in the demo to show self-description).

## 11. Invariants (N3) — define in docs/invariants.md, check in checker.py
- **I1 Completeness:** every core event/alarm seq is received by each connected client exactly once.
- **I2 Order:** each client receives seqs in increasing order (count inversions, gaps, duplicates).
- **I3 Value agreement:** for each seq, value/ID on GEM side == UA side == core (float tolerance 1e-3).
- **I4 State convergence:** after any state change, both sides report the same ControlState/ProcessingState/
  Authority within T = 500 ms.
- **I5 Single winner:** for concurrent conflicting commands, exactly one is accepted; the loser gets the
  mapped rejection code and a CEID 1005 visible on both sides.
- **I6 Loss attribution:** every event missing at a client is explained by the send-side log
  (`dropped_no_link`, etc.); unexplained losses are failures.
Also report latency (client ts − core ts) p50/p95/max per side.

## 12. Scenarios (`harness/scenarios.py`, `python -m harness.scenarios S1|...|all`)
Each run: fresh `run_id`, start equipment (sim sensor, fixed seed), start both listening clients, execute,
stop all, run checker → `results/<scenario>_summary.md` + CSV.

| ID | Scenario | Checks |
|---|---|---|
| S1 | Normal: 60 s idle + periodic CEID 1007 | I1, I2, I3, latency |
| S2 | Alarm: REMOTE, GEM START, wait overtemp, GEM STOP, wait clear | I1–I4 for ALID 5001 set/clear |
| S3 | Command conflict: REMOTE; GEM START + UA Start fired at the same instant (barrier), 50 repetitions (STOP between) | I5 each time; HCACK 0 vs BadUserAccessDenied; then `local` → GEM START gets HCACK 2 |
| S4 | EC conflict: REMOTE, GEM sets 35 & UA sets 45 concurrently → only GEM applied, final 35 on both; then `offline`, `lease ua`, UA sets 45 → applied, GEM sees CEID 1006 | I4, I5 |
| S5 | Disconnect: S1 running, kill GEM host 10 s, reconnect | I6; count GEM-missed vs UA-missed (expected finding: GEM misses all `dropped_no_link`, no spooling) |
| S6 | Report scope (N2 mismatch): GEM host redefines the report for CEID 1007 to drop EventTemp; UA client's event fields must be unchanged | records the "GEM report global vs UA filter per-client" gap |

Priority if short on time: S3 > S2 > S5 > S1 > S4 > S6. Never drop S3.

## 13. Unit and stress tests (must pass before each checkpoint commit)
- `test_arbiter.py`: every (control_state × lease × origin × action) combination vs the policy table.
- `test_core.py`: seq strictly increasing; every state change has an audit line; every submit path calls the
  arbiter (monkeypatch arbiter to deny-all and assert nothing changes from any origin — the no-bypass test);
  alarm hysteresis.
- `test_race.py`: 500 iterations of two threads calling `submit_command(START)` from GEM_HOST and UA_CLIENT
  through a barrier (state reset between) — assert exactly one success each time, and that the policy winner is
  always GEM_HOST in REMOTE. Also concurrent EC writes.
- `test_dispatcher.py`: ordering per subscriber; a subscriber that sleeps 1 s per item does not delay another.

## 14. Demo assets
- `harness/live_view.py` (rich): three live columns — "GEM host sees" | "Core (truth)" | "OPC UA client sees"
  — showing temp, control state, authority, last seq, alarms, last rejection. This is the main panel visual.
- `harness/demo.py`: narrated, step-by-step (press Enter between steps): browse model → REMOTE → GEM START →
  overtemp alarm on both → simultaneous START (one wins) → LOCAL → GEM rejected → kill GEM host → reconnect →
  show checker summary. Prints a one-line explanation before each step.

## 15. ESP32 firmware (optional, only after CP7)
OneWire + DallasTemperature; DS18B20 data on GPIO 4 with 4.7 kΩ pull-up to 3.3 V. Every 500 ms print
`{"seq":n,"t_ms":millis(),"temp_c":x}` at 115200. "H1"/"H0" toggles LED on GPIO 2.

## 16. Build order (2-day sprint) — stop and summarise at each checkpoint

**Day 1**
1. Scaffold, `requirements.txt`, `config.py`, README skeleton; inspect secsgem 0.3.0 + asyncua APIs →
   `docs/library_notes.md`. Commit `CP0-scaffold`.
2. `audit.py`, `arbiter.py`, `core.py`, `dispatcher.py`, `sensors.py` (sim) + all unit/race tests passing.
   Commit `CP1-core`.
3. `opcua_model.py`, `opcua_adapter.py`, `main.py`, `console.py`; verify with `ua_client.py --browse` and a
   method call. Commit `CP2-opcua`.
4. `gem_adapter.py`; verify with `gem_host.py`: S1F13, S1F3, reports, S6F11 with EventSeq, S2F41, S5F1.
   Commit `CP3-gem`.
5. Both doors live simultaneously; console `remote` → GEM START → alarm on both → STOP. `live_view.py`.
   Commit `CP4-dual` ← MINIMUM DEMO-ABLE STATE.

**Day 2**
6. checker + S3, S2. Commit `CP5-core-scenarios`.
7. S5, S1, S4, S6 (in that order, as time allows). Commit `CP6-scenarios`.
8. `demo.py`; docs (architecture with mermaid diagram, information_model, mapping, arbitration, invariants,
   limitations); fill `docs/novelty.md` from actual results. Commit `CP7-docs`.
9. Optional: ESP32 serial mode; one Wireshark capture per protocol saved in `results/`.

## 17. docs/novelty.md template (fill with real results, never invent numbers)
| Claim | Code | Tests | Evidence |
|---|---|---|---|
| N1 single core + arbiter, atomic decide-and-apply | core.py, arbiter.py, dispatcher.py | test_arbiter, test_core (no-bypass), test_race | S3, S4 summaries (I5 pass rate) |
| N2 GEM-derived draft UA model + mismatches | opcua_model.py, mapping.md | ua_client --browse output | S6 summary, mapping.md "gap" column |
| N3 consistency method (seq oracle + send/receive logs + invariants) | audit.py, checker.py, invariants.md | checker self-test on a sample run | S1, S2, S5 summaries |

Prior-art positioning paragraph: Golra & Engel 2021 (GEM-level mapping; did not study simultaneous use;
omitted spooling); Agileo 2020 / ErgoTech / Sun et al. 2021 (translation/gateway prototypes). Our work differs
by serving both natively from one core, defining and testing command authority, and measuring cross-interface
consistency. Use "to our knowledge, based on our literature search".

## 18. docs/mapping.md table (fill "status" and "observed" from the implementation)
| GEM concept | Our OPC UA construct | Fit | Semantic gap |
|---|---|---|---|
| SVID (S1F3/F4) | Variable + GemId/GemFormat + EngineeringUnits | full | GEM unit string vs EUInformation |
| DVID | Event field | partial | only meaningful at event time |
| ECID (S2F13/F15) | Writable variable/method via arbiter | full | EAC vs StatusCode |
| Report define/link/enable (S2F33/35/37) | Event subscription + field filter | partial | GEM reports global on the tool; UA filters per client (S6) |
| Event report (S6F11/F12) | GemCollectionEventType | full | S6F12 ack has no UA equivalent |
| Alarm (S5F1/F2) | Alarm condition / GemAlarmEventType | partial | S5F2 = message receipt; UA Acknowledge = operator acknowledgement |
| Remote command (S2F41/F42) | Method | full | ONLINE_REMOTE authority rule has no UA equivalent → arbiter (N1) |
| Control state | State variables + events | partial | simplified state model |
| Spooling | — | none | UA has no spool; secsgem doesn't implement GEM spooling (S5) |

## 19. Claims allowed / not allowed
Allowed: "single-core architecture serving SECS/GEM (HSMS) and OPC UA simultaneously on one simulated tool";
"GEM-derived draft OPC UA information model"; "explicit, tested control-authority policy for dual-interface
equipment"; "measured cross-interface consistency on one laptop (loopback), not fab-scale".
Not allowed: GEM compliance/certification; companion specification; OPC UA better/faster than SECS/GEM;
first-ever bridge; real-fab validation.
