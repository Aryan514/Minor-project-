# Dual-Interface Semiconductor Equipment Testbed (SECS/GEM + OPC UA)

One simulated semiconductor process tool (a heated chamber) whose state lives in **one equipment core** and is served
**at the same time** through SECS/GEM (HSMS, port 5000, `secsgem`) and OPC UA (port 4840, `asyncua`, GEM-derived draft
information model). A **control-authority arbiter** decides who may command the tool, every state change gets a global
sequence number, and a **checker** proves, from send- and receive-side logs, whether both interfaces saw the same truth
and why each lost message was lost. GEM-inspired testbed on one laptop (loopback); not GEM-compliant, not fab-validated.

| ID | Contribution | Read |
|---|---|---|
| N1 | Single-core dual-interface architecture + tested control-authority arbiter | `docs/architecture.md`, `docs/arbitration.md`, `docs/library_overrides.md` |
| N2 | GEM-derived draft OPC UA information model + semantic mismatches under simultaneous use | `docs/information_model.md`, `docs/mapping.md` |
| N3 | Consistency method: seq-numbered audit oracle, send/receive logs, invariants I1–I6, checker self-test | `docs/invariants.md`, `results/` |

Claims with evidence: `docs/novelty.md`. Panel questions: `docs/panel_qa.md`. Build log: `docs/progress.md`.
Presenting with the dashboard: `docs/user_guide/USER_GUIDE.md` (also `.pdf`), slide images in `docs/screenshots_for_slides/`.

## Install

Requires Python 3.11 or 3.12.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
```

Linux/macOS: `python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
Do **not** install `secsgem-driver`: it is an unrelated package that also imports as `secsgem`.
Expected: `101 passed`.

## Run the narrated panel demo

```powershell
python -m harness.demo
```

Press Enter between steps. It starts the equipment, the GEM host and the OPC UA client itself, and on Windows opens
the live view (GEM host sees | Core | OPC UA client sees) in a second window. Steps: browse the UA model → REMOTE →
GEM START → overtemp alarm on both (same seq) → simultaneous START (one wins) → LOCAL → GEM rejected → GEM host
killed for 10 s and reconnected → checker verdict on the demo run. Everything is shut down at the end, also on
Ctrl+C. `--auto` runs it without pauses, and `--no-live-window` skips the second window.

## Web dashboard (read-only, works offline)

```powershell
python -m harness.web_view                              # live: follows the newest run in runs/
python -m harness.web_view --run-dir runs/<id>          # live: one specific run
python -m harness.web_view --replay runs/sample_S3 --speed 5 --loop   # replay a finished run (no equipment needed)
python -m harness.demo --web                            # narrated demo with the dashboard instead of the terminal view
python -m harness.demo --web --auto --step-delay 8      # hands-free demo, 8 s pause before each step
```

Open http://localhost:8080 (`--port` to change). The page shows the architecture with message pulses (green accepted, red
rejected, amber alarm) and the GEM link state. It also has the three columns GEM | core | UA (disagreements in red), the
temperature chart with the limit and alarm periods, the arbiter decision feed, a per-seq event timeline (receive latency
or `dropped_no_link`), live invariants computed by `harness/checker.py`, and a Results tab. It only tails the run's
JSONL logs. It never connects to the equipment or its ports. Python standard library only, no CDN.

## Control panel (live dashboard)

`python -m harness.web_view` (live mode, bound to 127.0.0.1) shows a **Control panel**: *Start system* / *Stop system*
(equipment + GEM host + OPC UA client, like the demo) and command buttons: GEM START/STOP, UA Start/Stop, *Both START at
once*, set limit via GEM or UA, REMOTE/LOCAL/OFFLINE, Lease UA/off, Kill/Reconnect GEM host. Each button uses a real
protocol entry point (GEM host command port → S2F41/S2F15, `ua_client` → OPC UA Call, operator console), so the arbiter
decides exactly as for any external client. The result line shows the real reply (HCACK / EAC / StatusCode) and the
core's reason. *Stop system* runs the checker on the run. Also on the page: **On the wire** (SML of every SECS-II message
on port 5000, OPC UA service calls/notifications on 4840, tshark packet counts if installed). The **Inside** tab has the
policy table computed from the arbiter with the active row highlighted, a **model browser** (real OPC UA browse) and the
**race demo** (`python -m harness.race_demo`: 200 concurrent START pairs, unsafe check-then-act vs the real core).
`--no-control` gives a view-only page.

## Wireshark capture (shows that both protocols are real)

`results/demo_capture.pcapng` is a capture of one full demo, summarised in `results/capture_summary.md`
(HSMS message counts, OPC UA services, a decoded S6F11 and the decoded simultaneous START on the wire).

- Interface: **Adapter for loopback traffic capture** (`\Device\NPF_Loopback`; needs Npcap with loopback support).
- Capture filter: `tcp port 5000 or tcp port 4840`
- Open the file in Wireshark. OPC UA decodes by itself. For HSMS use *Analyze → Decode As…* → TCP port `5000` → `HSMS`.
  Command line: `tshark -r results\demo_capture.pcapng -d tcp.port==5000,hsms -Y hsms`
- To capture a new demo yourself (tshark is in `D:\Wireshark` on this laptop), start this, run the demo in a second
  terminal, then stop tshark with Ctrl+C:
  ```powershell
  & "D:\Wireshark\tshark.exe" -i \Device\NPF_Loopback -f "tcp port 5000 or tcp port 4840" -w results\my_capture.pcapng
  ```

OPC UA runs without security in this testbed, so both payloads are readable. The capture shows that the protocols are
real. It is not an overhead or speed comparison.

## Run the scenarios

```powershell
python -m harness.scenarios all          # S3, S2, S5, S1, S4, S6 (about 5 minutes)
python -m harness.scenarios S3 S2        # or a selection
python -m harness.checker runs/sample_S3 --self-test   # prove the checker flags corruptions
```

Each scenario uses a fresh `runs/<scenario>_<time>/` (seed 42) and writes `results/<scenario>_summary.md`,
`results/<scenario>_invariants.csv` and the overview `results/summary.md`. Ports 5000/4840/5100/5101 must be free.

## Results summary (runs of 2026-11-24, `results/summary.md`)

| Scenario | What | I1 | I2 | I3 | I4 | I5 | I6 | Checks | Key observation |
|---|---|---|---|---|---|---|---|---|---|
| S3 | 50 concurrent GEM START vs UA Start (REMOTE) | PASS | PASS | PASS | PASS | **PASS** | PASS | 4/4 | 50/50 single winner (GEM). UA arrived first in 3/50 and still lost |
| S2 | alarm set/clear | PASS | PASS | PASS | PASS | N/A | PASS | 5/5 | set/clear seqs 77/98 identical on core, GEM, UA |
| S5 | GEM host killed 10 s | PASS | PASS | PASS | N/A | N/A | **PASS** | 2/2 | GEM lost 11 events, all `dropped_no_link` (no spooling). UA lost 0 |
| S1 | 60 s normal | PASS | PASS | PASS | N/A | N/A | PASS | — | 62/62 events on both sides |
| S4 | EC conflict + maintenance lease | PASS | PASS | PASS | PASS | **PASS** | PASS | 10/10 | finding: a same-value write is a GEM event but no UA data change |
| S6 | GEM report redefinition | PASS | PASS | PASS | N/A | N/A | PASS | 5/5 | GEM report change is global. UA field selection is per subscription |

Each invariant cell covers both sides (GEM and UA): see `results/summary.md` for the per-side table.
Event latency p50: GEM 0–2 ms, UA 38–69 ms. UA includes the client's 50 ms publishing interval, and GEM sees the
temperature only via the 1 Hz CEID 1007, so the numbers **do not show that one protocol is faster**.

## Manual run (4 terminals)

```powershell
python -m equipment.main                 # 1: equipment + operator console (type help)
python -m clients.gem_host --listen      # 2: GEM host, logs every S6F11/S5F1
python -m clients.ua_client --listen     # 3: OPC UA client, logs every data change/event
python -m harness.live_view              # 4: side-by-side view
```

Then, from another terminal: `python -m equipment.console remote`, `python -m clients.gem_host --start`,
`python -m clients.ua_client --start` (→ BadUserAccessDenied), `python -m clients.gem_host --stop`,
`python -m equipment.console quit`. Also `python -m clients.ua_client --browse`,
`python -m clients.gem_host --status`, `--set-limit X` on either client.
The equipment accepts one HSMS session. While `gem_host --listen` runs, one-shot `gem_host` commands are relayed
through it.

## Logs of a run (`runs/<id>/`)

| File | Written by | Content |
|---|---|---|
| `core_audit.jsonl` | core | every state change / event / alarm with a global `seq` (the oracle) |
| `gem_adapter_send.jsonl`, `ua_adapter_send.jsonl` | doors | per event: `sent` / `dropped_no_link` / `dropped_disabled` / `error` |
| `gem_host.jsonl`, `ua_client.jsonl` | listening clients | everything received, `{ts_ns, kind, id, seq, data}` |
| `scenario.json` | scenario runner | window, conflict rounds, scenario checks, findings |

`runs/sample_S3/` is a committed real run used by the checker self-test.

## Repository layout

`equipment/` (core, arbiter, dispatcher, audit, sensors, both doors, console, main), `clients/` (GEM host, OPC UA
client), `harness/` (checker, scenarios, live view, web dashboard, demo), `tests/` (101 tests), `results/`, `docs/`.
Limitations and future work: `docs/limitations.md`.
