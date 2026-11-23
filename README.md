# Dual-Interface Semiconductor Equipment Testbed (SECS/GEM + OPC UA)

One simulated semiconductor process tool ("Chamber1Tool", a single heated chamber) whose state lives in
**one equipment core** and is served **at the same time** through:

- a **SECS/GEM** equipment interface (HSMS over TCP, port 5000), using `secsgem` 0.3.0, and
- an **OPC UA** server (port 4840) with a **GEM-derived draft information model**, using `asyncua` 1.1.8.

A **control-authority arbiter** decides who may command the tool, and every state change is written to a
sequence-numbered audit log that serves as the oracle for cross-interface consistency checks. Everything runs on
one laptop with no hardware (simulated sensor by default). This is a GEM-inspired testbed, not a GEM-compliant
product.

> Status: **CP4 – dual interface demo-able.** Core, arbiter, both doors, clients and live view work together.
> Scenarios/checker (CP5–CP6) and the full docs (CP7) are next. Build log: `docs/progress.md`.

## Contributions

| ID | Contribution | Where |
|---|---|---|
| N1 | Single-core dual-interface architecture + control-authority arbiter (atomic decide-and-apply) | `equipment/core.py`, `arbiter.py`, `dispatcher.py`, `docs/library_overrides.md` |
| N2 | GEM-derived draft OPC UA information model + documented semantic mismatches | `equipment/opcua_model.py`, `docs/library_notes.md` |
| N3 | Cross-interface consistency method: seq-numbered audit oracle, send/receive logs, invariants | `equipment/audit.py`, adapter send logs, client receive logs |

## Install

Requires Python 3.11 or 3.12.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS: `python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
Do **not** install `secsgem-driver`: it is an unrelated package that also imports as `secsgem`.

## Run the dual-interface demo (4 terminals, all in the repo folder with the venv activated)

1. **Equipment** (both doors + operator console). Type `help` for commands:
   ```powershell
   python -m equipment.main
   ```
   It prints `READY run_id=<id>` and writes all logs to `runs/<id>/`. Clients and the live view find that run
   automatically through `runs/LATEST`.
2. **GEM host** (connects, defines reports for all CEIDs, enables the alarm, logs every S6F11/S5F1):
   ```powershell
   python -m clients.gem_host --listen
   ```
3. **OPC UA client** (subscribes to all mapped variables and Chamber1Tool events):
   ```powershell
   python -m clients.ua_client --listen
   ```
4. **Live view** (GEM host sees | Core (truth) | OPC UA client sees):
   ```powershell
   python -m harness.live_view
   ```

Then drive the scenario from a fifth terminal (or type the console commands into terminal 1):

```powershell
python -m equipment.console remote        # operator: ONLINE_REMOTE -> authority GEM_HOST
python -m clients.gem_host --start        # S2F41 START -> HCACK 0, heater on
python -m clients.ua_client --start       # UA Start -> BadUserAccessDenied (CEID 1005 on BOTH sides)
# wait ~19 s: temperature crosses 40 degC -> ALID 5001 set on both sides (same seq)
python -m clients.gem_host --stop         # S2F41 STOP -> HCACK 0, cools, alarm clears
python -m equipment.console local         # operator takes authority back
python -m clients.gem_host --start        # now HCACK 2 ("equipment in LOCAL")
python -m equipment.console quit          # stops the equipment cleanly
```

Other useful commands:

```powershell
python -m clients.ua_client --browse      # self-describing model with GEM IDs
python -m clients.gem_host --status       # S1F3 + S2F13 snapshot
python -m clients.ua_client --set-limit 45   # SetTempHighLimit method (TempHighLimit itself is read-only)
python -m clients.gem_host --set-limit 35    # S2F15 -> EAC
python -m equipment.console status        # full core state as JSON
python -m pytest -q                       # 93 unit/stress tests
```

The equipment accepts **one** HSMS session. While `gem_host --listen` runs, the one-shot `gem_host` commands are
relayed through its session (`"via": "listener"` in the reply); otherwise they open their own session.

## Logs of a run (`runs/<id>/`)

| File | Written by | Content |
|---|---|---|
| `core_audit.jsonl` | core | every state change / event / alarm with a global `seq` (the oracle) |
| `gem_adapter_send.jsonl`, `ua_adapter_send.jsonl` | doors | per event: `sent` / `dropped_no_link` / `dropped_disabled` / `error` |
| `gem_host.jsonl`, `ua_client.jsonl` | listening clients | everything received, `{ts_ns, kind, id, seq, data}` |
| `*_actions.jsonl` | one-shot clients | reply codes (HCACK / EAC / StatusCode) |
| `equipment.log` | equipment | diagnostic log |

## Results summary

_To be filled in from `results/` after the scenarios run (CP5–CP6). No numbers are reported before then._

## Documentation

`docs/progress.md` (build log), `docs/decisions.md`, `docs/library_notes.md`, `docs/library_overrides.md`,
`docs/limitations.md`. Architecture, information model, mapping, arbitration, invariants and novelty docs follow at CP7.
