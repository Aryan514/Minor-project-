# S2 — results

- Run: `runs/S2_20261124-004245` (seed 42)
- Scenario: Alarm: REMOTE, GEM START, wait for ALID 5001 set, GEM STOP, wait for clear.
- Evaluation window: 26.6 s, 32 core events/alarms, 111 audit records in total

## Invariants

| Invariant | Side | Result | Detail |
|---|---|---|---|
| I1 | GEM | **PASS** | expected 32, received 32, missing 0, duplicates 0 |
| I1 | UA | **PASS** | expected 32, received 32, missing 0, duplicates 0 |
| I2 | GEM | **PASS** | 37 received, inversions 0, adjacent duplicates 0, gaps 0 (gaps are judged by I1/I6) |
| I2 | UA | **PASS** | 36 received, inversions 0, adjacent duplicates 0, gaps 0 (gaps are judged by I1/I6) |
| I3 | GEM | **PASS** | 37 compared, 0 mismatches |
| I3 | UA | **PASS** | 36 compared, 0 mismatches |
| I4 | GEM | **PASS** | 4 changes, max 4.7 ms |
| I4 | UA | **PASS** | 4 changes, max 71.6 ms |
| I5 | both | **N/A** | no conflict rounds in this scenario |
| I6 | GEM | **PASS** | 0 of 32 window events not received; causes {} |
| I6 | UA | **PASS** | 0 of 32 window events not received; causes {} |

## Scenario-specific checks

| Check | Result | Detail |
|---|---|---|
| console remote | **PASS** |  |
| GEM START -> HCACK 0 | **PASS** | {'action': 'start', 'code': 0, 'code_name': 'HCACK'} |
| GEM STOP -> HCACK 0 | **PASS** | {'action': 'stop', 'code': 0, 'code_name': 'HCACK'} |
| GEM saw alarm set+clear with the core's seqs | **PASS** | [('alarm_set', 77), ('alarm_clear', 98)] vs core [('alarm_set', 77), ('alarm_clear', 98)] |
| UA saw alarm set+clear with the core's seqs | **PASS** | [('alarm_set', 77), ('alarm_clear', 98)] vs core [('alarm_set', 77), ('alarm_clear', 98)] |

## Latency (events)

| Side | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| GEM | 32 | 0.16 | 3.61 | 4.66 |
| UA | 32 | 36.83 | 66.1 | 71.56 |

> Latency = client receive time - core audit time, both `time.time_ns()` on the same laptop (loopback). The UA figure includes the client's 50 ms subscription publishing interval, and GEM sees the temperature only through the 1 Hz CEID 1007. These numbers describe this setup. They must not be read as one protocol being faster than the other.
