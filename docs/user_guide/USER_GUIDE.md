# Dashboard user guide: presenting the dual-interface testbed

For a student who has never used the dashboard and has to demonstrate the project to an evaluation panel.
Every screenshot here was taken from the real dashboard (http://localhost:8080) while its own buttons were pressed in
the order of Part B, on run `PANEL_20261124-182143` (simulated chamber, seed 42). That run's checker verdict was **PASS**.
The red numbered circles are added afterwards (`docs/user_guide/annotate.py`) and are referred to as ① ② … below.

What the project is, in one sentence: one simulated process chamber whose state lives in **one equipment core** and is
served **at the same time** over SECS/GEM (HSMS, port 5000) and OPC UA (port 4840). Every command from any side goes
through one **arbiter**, and a **checker** proves from the logs whether both sides saw the same truth.
This is a GEM-inspired testbed on one laptop (loopback). It is not GEM-compliant and has not been validated in a fab.

**Before the panel** (5 minutes earlier):

```powershell
cd D:\semi-dual-testbed
.venv\Scripts\python.exe -m harness.web_view --port 8080
```

Open http://localhost:8080 in the browser and make the window wide (1800 px or full screen). The page needs no internet.
Keep a second terminal ready for the fallback in Part C.

---

## Part A: Dashboard tour

### A.1 Header, control panel and architecture

![Header, control panel and architecture](img/A1_tour_header_control_arch.png)

| # | Element | What it shows | Where the data comes from | Colours |
|---|---|---|---|---|
| ① | **LIVE / REPLAY** badge | Whether the page follows a running system (LIVE) or plays back a finished run (REPLAY ×speed). | The dashboard's own mode. | Violet = informational. |
| ② | **run** badge | Folder name of the run being shown, `runs/<run id>/`. Panel runs are called `PANEL_<date>-<time>`. | Newest run folder. | — |
| ③ | **control** badge | The GEM control state: `ONLINE_REMOTE`, `ONLINE_LOCAL` or `EQUIPMENT_OFFLINE`. | Core audit log (`core_audit.jsonl`). | Blue = REMOTE (host in charge), green = LOCAL (operator in charge), amber = OFFLINE. |
| ④ | **processing** badge | `IDLE` or `EXECUTING` (heater on). | Core audit log. | Amber = EXECUTING. |
| ⑤ | **authority** badge | Who may currently command the tool: `GEM_HOST`, `OPERATOR` or `UA_CLIENT`. It follows from the control state and the maintenance lease. | Core audit log. | Violet. |
| ⑥ | **GEM link** badge | Whether the HSMS connection between equipment and GEM host is up (`COMMUNICATING`) or down (`NOT_COMMUNICATING`). | Equipment side of the GEM door. | Green = up, red = down (it flashes when the link drops). |
| ⑦ | **Tabs** | *Live* (this page), *Inside* (policy, model browser, race demo, A.4), *Results* (committed scenario results). | — | Blue = selected tab. |
| ⑧ | **Start system / Stop system** | Start launches the equipment, a listening GEM host and a listening OPC UA client, like the scripted demo. Stop shuts them all down, runs the checker on the run, and verifies that ports 5000/4840/5100/5101 were released. The text next to the buttons shows RUNNING/STOPPED. | `harness/control_panel.py`. | Buttons are greyed out when they cannot be used. |
| ⑨ | **tshark line / verdict line** | Live packet counts on ports 5000 and 4840 from tshark (Wireshark's command-line capture), shown if tshark is installed. After *Stop system* this line shows the checker verdict of the panel run. | tshark on the loopback adapter. | PASS green, FAIL red. |
| ⑩ | **GEM host row** | GEM START / GEM STOP send a real S2F41 remote command over HSMS. *Set limit (GEM)* sends S2F15 (equipment-constant write). *Kill GEM host* kills the host process (simulated crash). *Reconnect GEM host* starts it again. | Requests go through the listening GEM host's command port (5101), so they are real SECS-II messages. | — |
| ⑪ | **OPC UA client row** | UA Start / UA Stop call the OPC UA methods `Start()` / `Stop()`. *Set limit (UA)* calls `SetTempHighLimit(value)`. *Both START at once* fires a GEM START and a UA Start released by one barrier (the same mechanism as scenario S3). | Each press runs the real `clients.ua_client` program (an OPC UA Call on port 4840). | — |
| ⑫ | **Operator row** | REMOTE / LOCAL / OFFLINE change the control state. *Lease UA* / *Lease off* grant or revoke the maintenance lease (only possible in OFFLINE). | Equipment operator console socket (port 5100). | — |
| ⑬ | **Result box** | The real reply to the last button: HCACK (S2F42), EAC (S2F16), OPC UA StatusCode or console reply, plus the core's reason and the round-trip time. | The reply the protocol returned. | Green border = accepted, red border = rejected. |
| ⑭ | **Architecture** | One core with the arbiter, two "doors" (secsgem and asyncua) and their clients. Moving dots are messages. | Core audit log and the clients' receive logs. | Green dot = accepted command or delivered event, red dot = rejected command, amber dot = alarm. A dashed red link with "✕ dropped_no_link" means the door had an event but no connected host to send it to. |

Every button goes through an entry point that any outside client would use. The dashboard never calls the core
directly, so the arbiter treats a button press exactly like a real host or client.

### A.2 What each side sees, temperature, arbiter decisions, event timeline

![Columns, chart, arbiter feed and timeline](img/A2_tour_columns_chart_feed_timeline.png)

| # | Element | What it shows | Where the data comes from | Colours |
|---|---|---|---|---|
| ⑮ | **What each side sees** | Three columns of the same quantities: *GEM host sees* \| *Core (truth)* \| *OPC UA client sees*. Rows: temperature, control state, processing state, authority, TempHighLimit, alarm 5001, last event seq, last rejection, events received, GEM link. | Left: what the GEM host logged as received (`gem_host.jsonl`). Middle: the core audit log. Right: what the OPC UA client logged (`ua_client.jsonl`). | The core column is cyan. A **red** cell means that side currently disagrees with the core. |
| ⑯ | **Temperature row** | In this screenshot the GEM column is red: the GEM host had been killed, so its last temperature is stale while the core and OPC UA keep updating. That is exactly what the red highlight is for. | | |
| ⑰ | **GEM link row** | The link state as each side last reported it. A killed host cannot report that it died, so its own column still says COMMUNICATING (red, stale) while the core says NOT_COMMUNICATING. | | |
| ⑱ | **Core temperature** | Temperature over the last 120 s, the TempHighLimit (dashed red line) and periods where alarm 5001 was active (amber band). | Core audit samples. | Cyan line = temperature, dashed red = limit, amber = alarm active. |
| ⑲ | **Arbiter decisions** | Every command that reached the arbiter, newest first: time, audit seq, origin (GEM_HOST / UA_CLIENT / OPERATOR), action, ACCEPTED/REJECTED and the reason. | Core audit log (`command_ok`, `command_rejected`, `ec_write`, `ec_rejected`). | Rejected rows have a red background. |
| ⑳ | **Event timeline** | One row per event the core emitted (sequence number, core time, event name), and for each client whether and how fast it received it. | Core audit log + both receive logs + both send-side logs (`gem_adapter_send.jsonl`, `ua_adapter_send.jsonl`). | ✓ + latency = received. `…` = not yet received. Red **✕ dropped_no_link** = the door recorded that it could not send because no host was connected. Amber = alarm events. |
| ㉑ | **Dropped rows** | Events the GEM door could not deliver while the GEM host was down. There is no spooling, so they are lost, but every loss has a recorded cause (invariant I6). | | |

### A.3 On the wire and live invariants

![Wire panel and invariants](img/A3_tour_wire_invariants.png)

| # | Element | What it shows | Where the data comes from | Colours |
|---|---|---|---|---|
| ㉒ | **SECS-II on port 5000** | Every HSMS message, newest first, in SML (the standard text form of SECS-II). Examples: `S6F11 W` event report (equipment → host) with its full body, `S2F41 W` remote command, `S2F42` reply, `S5F1` alarm report, and HSMS control messages such as `Select.req` and `Linktest`. In an `S6F11` the first number is DATAID (set to the event's sequence number), followed by the CEID and the report values. | secsgem's own communication log inside the equipment (`gem_wire.jsonl`). | Green header = equipment → host, cyan header = host → equipment. |
| ㉓ | **OPC UA on port 4840** | The OPC UA service calls and notifications: sessions, CreateSubscription, CreateMonitoredItems, `Call` (Start/Stop/SetTempHighLimit), and every `Publish: DataChangeNotification` and `Publish: EventNotification`. | The OPC UA clients' own logs (`ua_wire_*.jsonl`). This is the client-API level, **not** decoded packets. Decoded packets are in `results/demo_capture.pcapng` (Wireshark). | Green header = client → server, cyan header = server → client. Status `Good` green, `Bad…` red. |
| ㉔ | **Live invariants** | The checker (`harness/checker.py`) run on the logs so far, per invariant and per side. I1 completeness, I2 order, I3 value agreement, I4 state convergence within 500 ms, I5 single winner in conflicts, I6 every loss explained. | The same checker code that judges the scenarios. | PASS green, FAIL red, N/A grey (for example I5 when no conflict round has happened yet). |
| ㉕ | **Counters** | Events received, missing, duplicates, out-of-order, value mismatches, losses with a recorded cause, unexplained losses, for GEM and UA. | Checker. | Red if a "bad" counter is above 0. "Losses with a recorded cause" may be above 0 and is still fine. |
| ㉖ | **Latency line** | p50/p95/max event latency per side (client receive time − core time). | Checker. | The OPC UA number includes the client's 50 ms publishing interval, so it is **not** a protocol speed comparison. |
| ㉗ | **Overall verdict** | PASS only if every applicable invariant passes. | Checker. | |

### A.4 Inside tab: policy, model browser, race demo

![Inside tab](img/A4_inside_policy_browser_race.png)

| # | Element | What it shows |
|---|---|---|
| ㉘ | **Inside tab** | Click it to see the three panels below. |
| ㉙ | **Control-authority policy** | Who may START / STOP / write the limit, for each control state. The table is **generated by calling the arbiter's own `decide()` function**, not copied from the documents. The row matching the current state is highlighted (blue frame). Green = allowed, red = rejected with the reason, amber = partly allowed (the operator's STOP-only safety override in REMOTE). |
| ㉚ | **Browse the server now** | Performs a real OPC UA browse of `opc.tcp://127.0.0.1:4840` (system must be running) and prints the address space: object and variable types, live values, engineering units, ranges and methods. |
| ㉛ | **GEM link tags** | `⟷ GEM SVID 1 (F4)` etc.: every GEM-mapped OPC UA variable carries its GEM ID, kind and format (properties GemId/GemKind/GemFormat), so a UA client can navigate from a UA node to the GEM ID. This is the GEM-derived draft information model (N2). |
| ㉜ | **Race demo** | 200 pairs of concurrent START commands, run twice. The *unsafe* variant (exists only in `harness/race_demo.py`) checks, releases the lock, waits 1 ms and then applies: both commands win almost every time. The *real* `EquipmentCore` decides and applies under one lock: never two winners. Both use the same arbiter in EQUIPMENT_OFFLINE + UA lease, where both contenders are allowed, so only atomicity makes the difference. It runs in-process and does not touch the running system. |

### A.5 Results tab

![Results tab](img/A5_results_tab.png)

| # | Element | What it shows |
|---|---|---|
| ㉝ | **Result files** | The committed results: `summary.md` (overview of all scenarios), `S1_summary.md` … `S6_summary.md`, `checker_self_test.md`. Click one to show it. |
| ㉞ | **Rendered summary** | The overview table per scenario and invariant (PASS green, FAIL red, N/A grey), read from `results/` on disk. These are the reported results, produced by `python -m harness.scenarios all`, not by the panel run. |

### A.6 Known harmless effects (say this if the panel asks about a red cell)

- **Brief red cells in the OPC UA column.** The OPC UA client receives data changes in batches every 50 ms (its
  publishing interval), while the core column updates immediately. Right after a change the UA cell can be red for up
  to about 0.1 s. Invariant I4 allows 500 ms and the measured maximum is far below that.
- **Red GEM cells after the GEM host is killed, and after Stop system.** A dead or stopped host cannot log anything
  more, so its column keeps the last values it received (for example `GEM link = COMMUNICATING`) while the core moved
  on. Red here means "this side is stale". That is what the view is meant to show, not a bug.
- **Empty or N/A invariants in the first 2 seconds.** The live checker only judges events older than 2 s, because younger
  ones may still be in flight. Right after *Start system* the invariants table is empty or N/A. I5 stays N/A until a
  *Both START at once* conflict has happened.
- **UA losses at start-up.** The OPC UA door can log 1–2 `dropped_no_link` events in the first second, before the client
  has subscribed. They have a recorded cause and are counted by I6, not as failures.
- **The GEM `I2 gaps 1` line after a reconnect.** The events missed while the host was down are a gap in its sequence.
  Gaps are judged by I1/I6 (every one explained), so I2 still passes.

---

## Part B: Demo script

About 6–8 minutes. Read the "What to say" column almost word for word. It is accurate and makes no claims about GEM
compliance or protocol speed. Screenshots of each step follow the table.

| Step | Click | What appears | What to say to the panel |
|---|---|---|---|
| 1 | **▶ Start system** | After ~5 s: `RUNNING`, GEM link COMMUNICATING, the three columns fill, the tshark packet counts start rising, temperature ~25 °C. | "One simulated chamber, one core. The same state is now served by a SECS/GEM interface on port 5000 and an OPC UA server on port 4840, and a real GEM host and a real OPC UA client are both connected." |
| 2 | **REMOTE** | Reply `OK seq=…`. control = ONLINE_REMOTE, authority = GEM_HOST, highlighted policy row changes. | "In ONLINE_REMOTE the GEM host holds command authority. The arbiter derives authority from the control state, and that rule is written down and tested." |
| 3 | **GEM START** | Reply `HCACK 0`. processing = EXECUTING on all three columns; temperature starts rising. | "That was a real S2F41 remote command over HSMS. HCACK 0 means accepted, and the OPC UA client sees the same state change." |
| 4 | *(wait ~15 s)* | Temperature crosses the 40 °C limit. Alarm 5001 = SET in all three columns, amber band on the chart, `ALID 5001 SET` in the timeline with ✓ for both sides. | "The over-temperature alarm arrives as S5F1 on the GEM side and as an alarm event on OPC UA. Both carry the same sequence number, which the checker uses to join the two sides." |
| 4a | *(scroll to "On the wire")* | Point at an `S6F11 W` on the left and the `Publish: EventNotification` on the right with the same number: in the S6F11 the first `<U1 …>` (DATAID) and the `<U4 …>` value are the seq; on OPC UA it is `"EventSeq": …` (figure B14). | "Here is proof that both protocols are real: the same event, sequence number 45, once as a SECS-II S6F11 report and once as an OPC UA EventNotification." |
| 5 | **UA Start** | Reply `StatusCode BadUserAccessDenied · reason: authority held by GEM_HOST`. A red row in Arbiter decisions; "Last rejection" updates on all three columns. | "The OPC UA client may not command the tool while the GEM host has authority. It gets a standard OPC UA status code, and the GEM host is told about the rejected attempt as well, through CEID 1005." |
| 6 | **GEM STOP** | `HCACK 0`, processing = IDLE, the temperature falls, and the alarm clears below 39 °C (hysteresis). | "Stopping cools the chamber. The alarm clears with 1 °C hysteresis, on both sides again." |
| 7 | **⚡ Both START at once** | `GEM HCACK 0 \| UA BadUserAccessDenied [conflict round … judged by I5]`. Two decisions with consecutive seqs in the feed. | "Both commands were released at the same instant. Decide-and-apply happens atomically under one lock, so exactly one can win, and the policy says it must be the GEM host. Scenario S3 does this 50 times, and the unit test 500 times." |
| 8 | *(GEM STOP to return to IDLE)*, then **LOCAL** | `OK`, control = ONLINE_LOCAL, authority = OPERATOR. | "Now the operator takes the tool into LOCAL." |
| 9 | **GEM START** | `HCACK 2 · reason: equipment in LOCAL`, a red row in the feed. | "HCACK 2 means 'cannot perform now'. The host is refused because the operator has authority, and the reason is recorded in the audit log." |
| 10 | **REMOTE** | Authority back to GEM_HOST. | "Back to remote control." |
| 11 | **Kill GEM host** | GEM link = NOT_COMMUNICATING (red, flashing). The GEM link on the diagram turns dashed red. | "I have just simulated a host crash. The OPC UA side is unaffected: a failure of one interface does not stop the core or the other interface." |
| 12 | *(wait 10 s)* | Timeline: every new event shows `✕ dropped_no_link` for GEM and ✓ for UA. The GEM column turns red (stale). | "Neither secsgem nor OPC UA spools events. Events the GEM side misses are lost, but the GEM door logs every one it could not send, so each loss has a recorded cause. That is invariant I6. GEM spooling is one of the semantic gaps we document." |
| 13 | **Reconnect GEM host** | `GEM host connected, reports defined again`. GEM link COMMUNICATING, ✓ marks for GEM again. | "The host reconnects, defines its reports again and receives new events. The old ones are not replayed." |
| 14 | *(optional)* **Inside** tab → **Browse the server now**, then **Run race demo** | Model tree with GEM IDs (SVID 1–5, ECID 201). Race result: unsafe 200/200 double winners, real 0/200. | "This is a live browse of our draft information model: every OPC UA variable carries its GEM ID. The race demo shows why the core must decide and apply atomically: with an artificial gap between check and apply, both commands win; in the real core never." |
| 15 | **Live** tab → **■ Stop system** | After ~10 s: `STOPPED`, `last panel run: checker PASS · ports released: True`. | "Stopping runs the same consistency checker as our scenarios on everything that just happened: completeness, order, value agreement, convergence within 500 ms, a single winner, and an explanation for every lost event." |

Run used for the screenshots: `PANEL_20261124-182143`. Replies observed (from `docs/user_guide/raw/run_log.txt`):

```
remote -> Operator console: remote | reply: OK seq=29 (27 ms)
gem_start -> GEM host: S2F41 START (via the GEM host's command port) | reply: HCACK 0 (29 ms)
ua_start -> UA client: Call Start() (ua_client one-shot) | reply: StatusCode BadUserAccessDenied · reason: authority held by GEM_HOST (582 ms)
gem_stop -> GEM host: S2F41 STOP | reply: HCACK 0 (7 ms)
both_start -> GEM S2F41 START + UA Call Start released by one barrier (like S3) | reply: GEM HCACK 0 | UA BadUserAccessDenied [conflict round (authority GEM_HOST) - judged by I5] · reason: authority held by GEM_HOST (28 ms)
gem_stop -> GEM host: S2F41 STOP | reply: HCACK 0 (46 ms)
local -> Operator console: local | reply: OK seq=153 (4 ms)
gem_start -> GEM host: S2F41 START (via the GEM host's command port) | reply: HCACK 2 · reason: equipment in LOCAL (42 ms)
remote -> Operator console: remote | reply: OK seq=174 (15 ms)
kill_gem -> Kill the GEM host process (simulated crash) | reply: GEM host process killed (HSMS link will drop) (155 ms)
reconnect_gem -> Start the GEM host again | reply: GEM host connected, reports defined again (444 ms)
```

### Step screenshots

**Step 1: Start system.** ① start button (greyed out once running), ② RUNNING message, ③ tshark packet counts,
④ GEM link up, ⑤ the three columns agree.
![Step 1](img/B01_start_system.png)

**Step 2: REMOTE.** ① button, ② reply `OK seq=…`, ③ control = ONLINE_REMOTE, ④ authority = GEM_HOST.
![Step 2](img/B02_remote.png)

**Step 3: GEM START.** ① button, ② reply HCACK 0, ③ processing = EXECUTING, ④ the same on all three columns.
![Step 3](img/B03_gem_start.png)

**Step 4: alarm 5001 active on both sides.** ① Alarm 5001 = SET on GEM, core and UA, ② the same last event seq on all
three, ③ amber alarm band above the dashed limit, ④ timeline.
![Step 4](img/B04_alarm_both_sides.png)

**Step 4a: the same seq on both wires.** ① SECS-II S6F11 (DATAID and DVID 101 = seq), ② OPC UA EventNotification with
`EventSeq` = the same number (both outlined in red by the capture script).
![Step 4a](img/B14_wire_same_seq.png)

**Step 5: UA Start rejected.** ① button, ② `BadUserAccessDenied` with reason, ③ Last rejection on all columns,
④ red row in Arbiter decisions.
![Step 5](img/B05_ua_start_rejected.png)

**Step 6: GEM STOP.** ① button, ② HCACK 0, ③ processing IDLE, ④ temperature falling.
![Step 6](img/B06_gem_stop.png)

**Step 7: Both START at once.** ① button, ② GEM HCACK 0 and UA BadUserAccessDenied, judged by I5, ③ two decisions with
consecutive seqs.
![Step 7](img/B07_both_start.png)

**Step 8: LOCAL.** ① button, ② reply, ③ ONLINE_LOCAL, ④ authority OPERATOR.
![Step 8](img/B08_local.png)

**Step 9: GEM START rejected in LOCAL.** ① button, ② `HCACK 2 · reason: equipment in LOCAL`, ③ red feed row.
![Step 9](img/B09_gem_start_rejected_local.png)

**Step 10: REMOTE again.**
![Step 10](img/B10_remote_again.png)

**Step 11: kill GEM host.** ① button, ② reply, ③ GEM link NOT_COMMUNICATING, ④ diagram link dashed red,
⑤ GEM link row (the host's own column is stale).
![Step 11](img/B11_kill_gem_host.png)

**Step 12: 10 s later.** ① the GEM temperature is stale (red), ② alarm state is stale on GEM, ③ `✕ dropped_no_link`
for GEM while UA keeps receiving.
![Step 12](img/B12_after_10s_disconnected.png)

**Step 13: Reconnect GEM host.** ① button, ② reply, ③ link up again, ④ newest events ✓ on both sides.
![Step 13](img/B13_gem_reconnected.png)

**Live invariants just before stopping.** ① overall verdict, ② per-invariant table, ③ counters.
![Invariants](img/B16_invariants_before_stop.png)

**Step 15: Stop system.** ① Stop button, ② STOPPED message, ③ the checker verdict and ports released, ④ the GEM link
badge is red after the stop (harmless, A.6).
![Step 15](img/B15_stop_system_verdict.png)

Checker verdict of this run (printed by *Stop system*):

```
verdict: PASS ports free: True
I1 GEM PASS expected 77, received 77, missing 0, duplicates 0
I1 UA PASS expected 90, received 90, missing 0, duplicates 0
I2 GEM PASS 81 received, inversions 0, adjacent duplicates 0, gaps 1 (gaps are judged by I1/I6)
I2 UA PASS 93 received, inversions 0, adjacent duplicates 0, gaps 0 (gaps are judged by I1/I6)
I3 GEM PASS 81 compared, 0 mismatches
I3 UA PASS 93 compared, 0 mismatches
I4 GEM PASS 10 changes, max 5.4 ms
I4 UA PASS 10 changes, max 63.6 ms
I5 both PASS 1 rounds, 1 clean; request from GEM reached the core first in 1/1 rounds
I6 GEM PASS 13 of 90 window events not received; causes {'dropped_no_link': 13}
I6 UA PASS 0 of 90 window events not received; causes {}
```

---

## Part C: If something goes wrong

| Problem | What you see | What to do |
|---|---|---|
| **Port busy** | *Start system* reports an error mentioning a port, or nothing starts. Ports 5000 (HSMS), 4840 (OPC UA), 5100 (console), 5101 (GEM host relay) must be free. Port 8080 is the dashboard itself. | Find the owner: `Get-NetTCPConnection -LocalPort 5000,4840,5100,5101 -State Listen \| Select LocalPort,OwningProcess`. If it is a leftover of this project (`python.exe` from `D:\semi-dual-testbed\.venv`), stop it with `taskkill /T /F /PID <pid>`. Do not kill unrelated Python programs. |
| **System won't start** | State stays STARTING, or goes back to STOPPED with an error. | Read `runs/<newest PANEL run>/equipment.out` and `equipment.log`. Close the dashboard (Ctrl+C in its terminal), check the ports as above, start the dashboard again and press *Start system* again. |
| **A button says "system not running"** | All command buttons are greyed out. | Press *Start system* first and wait for RUNNING. |
| **GEM commands time out after Kill GEM host** | Reply shows an error. | Press *Reconnect GEM host* first. |
| **Model browser shows an error** | "connection refused" | The browse needs the running system (OPC UA server on 4840). Start the system first. |
| **Live demo is not possible at all** | — | Switch to the **replay dashboard**. It plays back a committed real run and needs no equipment and no free ports except 8081: `.venv\Scripts\python.exe -m harness.web_view --replay runs/sample_S3 --speed 3 --loop --port 8081`, then open http://localhost:8081. It shows the same panels (header says REPLAY), without the control panel. |
| **Dashboard page is blank / "reconnecting…"** | The dashboard process ended. | Restart it (below) and reload the page. |

### How to restart each piece

Run every command from `D:\semi-dual-testbed`.

| Piece | Start | Stop |
|---|---|---|
| Live dashboard with control panel | `.venv\Scripts\python.exe -m harness.web_view --port 8080` | Ctrl+C in its terminal (it stops a running system too) |
| View-only live dashboard | `.venv\Scripts\python.exe -m harness.web_view --port 8080 --no-control` | Ctrl+C |
| Replay dashboard | `.venv\Scripts\python.exe -m harness.web_view --replay runs/sample_S3 --speed 3 --loop --port 8081` | Ctrl+C |
| Whole system without the dashboard (equipment + clients) | *Start system* button, or the scripted demo: `.venv\Scripts\python.exe -m harness.demo --web` | *Stop system*, or Ctrl+C in the demo |
| Equipment only | `.venv\Scripts\python.exe -m equipment.main` (type `help` at its console) | `quit` at its console |
| GEM host | `.venv\Scripts\python.exe -m clients.gem_host --listen` (or *Reconnect GEM host*) | Ctrl+C (or *Kill GEM host*) |
| OPC UA client | `.venv\Scripts\python.exe -m clients.ua_client --listen` | Ctrl+C |
| Race demo on the command line | `.venv\Scripts\python.exe -m harness.race_demo -n 200` | finishes by itself |
| Checker on any run | `.venv\Scripts\python.exe -m harness.checker runs/<run id>` | finishes by itself |

If a dashboard was started in the background (no terminal window), stop it by its port owner:
`Get-NetTCPConnection -LocalPort 8080 -State Listen` → `taskkill /T /F /PID <OwningProcess>`.

---

### How these screenshots were made

`docs/user_guide/raw/` holds the unannotated full-page captures and, next to each, the measured element positions
(`*.json`). They were taken by a headless Microsoft Edge that pressed the dashboard's own buttons through the browser
(no direct API calls). The only change made to the page during capture was hiding the fixed footer, so that it does not
overlap the full-page image. `raw/run_log.txt` lists every reply. `annotate.py` draws the callouts (Pillow), and
`build_pdf.py` produces `USER_GUIDE.html` and `USER_GUIDE.pdf` with the images embedded.
