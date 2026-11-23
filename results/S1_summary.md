# S1 — results

- Run: `runs/S1_20261124-005043` (seed 42)
- Scenario: Normal operation: 60 s idle in ONLINE_LOCAL with periodic CEID 1007 (1 Hz).
- Evaluation window: 62.0 s, 62 core events/alarms, 205 audit records in total

## Invariants

| Invariant | Side | Result | Detail |
|---|---|---|---|
| I1 | GEM | **PASS** | expected 62, received 62, missing 0, duplicates 0 |
| I1 | UA | **PASS** | expected 62, received 62, missing 0, duplicates 0 |
| I2 | GEM | **PASS** | 66 received, inversions 0, adjacent duplicates 0, gaps 0 (gaps are judged by I1/I6) |
| I2 | UA | **PASS** | 66 received, inversions 0, adjacent duplicates 0, gaps 0 (gaps are judged by I1/I6) |
| I3 | GEM | **PASS** | 66 compared, 0 mismatches |
| I3 | UA | **PASS** | 66 compared, 0 mismatches |
| I4 | GEM | **N/A** | no state change while the client listened |
| I4 | UA | **N/A** | no state change while the client listened |
| I5 | both | **N/A** | no conflict rounds in this scenario |
| I6 | GEM | **PASS** | 0 of 62 window events not received; causes {} |
| I6 | UA | **PASS** | 0 of 62 window events not received; causes {} |

## Latency (events)

| Side | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| GEM | 62 | 0.0 | 2.05 | 2.27 |
| UA | 62 | 48.6 | 64.53 | 78.74 |

> Latency = client receive time - core audit time, both `time.time_ns()` on the same laptop (loopback). The UA figure includes the client's 50 ms subscription publishing interval, and GEM sees the temperature only through the 1 Hz CEID 1007. These numbers describe this setup. They must not be read as one protocol being faster than the other.
