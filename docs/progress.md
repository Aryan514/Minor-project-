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
