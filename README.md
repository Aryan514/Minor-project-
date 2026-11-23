# Dual-Interface Semiconductor Equipment Testbed (SECS/GEM + OPC UA)

One simulated semiconductor process tool ("Chamber1Tool", a single heated chamber) whose state lives in
**one equipment core** and is served **at the same time** through:

- a **SECS/GEM** equipment interface (HSMS over TCP, port 5000), using `secsgem` 0.3.0, and
- an **OPC UA** server (port 4840) with a **GEM-derived draft information model**, using `asyncua`.

A **control-authority arbiter** decides who may command the tool, and a **consistency harness** checks
whether both interfaces see the same truth and where they diverge. Everything runs on one laptop with no
hardware (simulated sensor by default). This is a GEM-inspired testbed, not a GEM-compliant product.

> Status: **CP0 – scaffold.** Only configuration and library notes exist so far. See `CLAUDE.md` §16.

## Contributions

| ID | Contribution |
|---|---|
| N1 | Single-core dual-interface architecture + control-authority arbiter (atomic decide-and-apply) |
| N2 | GEM-derived draft OPC UA information model + documented semantic mismatches under simultaneous use |
| N3 | Cross-interface consistency test method: sequence-numbered audit oracle, send/receive logs, invariant checker |

## Install

Requires Python 3.11 or 3.12.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS: `python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.

Do **not** install `secsgem-driver`: it is an unrelated package that also imports as `secsgem`.

## Run

_To be filled in at CP2–CP4._

```powershell
python -m equipment.main --sensor sim          # equipment (both doors)
python -m clients.gem_host --listen            # scripted GEM host
python -m clients.ua_client --browse           # OPC UA client: show the model
python -m harness.live_view                    # side-by-side view
```

## Demo script

_To be filled in at CP7 (`python -m harness.demo`)._

## Results summary

_To be filled in from `results/` after the scenarios run (CP5–CP6). No numbers are reported before then._

## Repository layout

See `CLAUDE.md` §3. Key docs: `docs/architecture.md`, `docs/information_model.md`, `docs/mapping.md`,
`docs/arbitration.md`, `docs/invariants.md`, `docs/novelty.md`, `docs/library_notes.md`, `docs/limitations.md`.
