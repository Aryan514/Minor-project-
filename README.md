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
Expected: `95 passed`.

## Run the narrated panel demo

```powershell
python -m harness.demo
```

Press Enter between steps. It starts the equipment, the GEM host and the OPC UA client itself, and on Windows opens
the live view (GEM host sees | Core | OPC UA client sees) in a second window. Steps: browse the UA model → REMOTE →
GEM START → overtemp alarm on both (same seq) → simultaneous START (one wins) → LOCAL → GEM rejected → GEM host
killed for 10 s and reconnected → checker verdict on the demo run. Everything is shut down at the end, also on
Ctrl+C. `--auto` runs it without pauses, and `--no-live-window` skips the second window.

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
client), `harness/` (checker, scenarios, live view, demo), `tests/` (95 tests), `results/`, `docs/`.
Limitations and future work: `docs/limitations.md`.
