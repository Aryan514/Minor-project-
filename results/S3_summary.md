# S3 — results

- Run: `runs/S3_20261124-004213` (seed 42)
- Scenario: Command conflict: REMOTE; GEM START and UA Start released by one barrier, 50 rounds (GEM STOP between); then LOCAL and GEM START must get HCACK 2.
- Evaluation window: 7.8 s, 163 core events/alarms, 455 audit records in total

## Invariants

| Invariant | Side | Result | Detail |
|---|---|---|---|
| I1 | GEM | **PASS** | expected 163, received 163, missing 0, duplicates 0 |
| I1 | UA | **PASS** | expected 163, received 163, missing 0, duplicates 0 |
| I2 | GEM | **PASS** | 167 received, inversions 0, adjacent duplicates 0, gaps 0 (gaps are judged by I1/I6) |
| I2 | UA | **PASS** | 166 received, inversions 0, adjacent duplicates 0, gaps 0 (gaps are judged by I1/I6) |
| I3 | GEM | **PASS** | 167 compared, 0 mismatches |
| I3 | UA | **PASS** | 166 compared, 0 mismatches |
| I4 | GEM | **PASS** | 104 changes, max 14.4 ms |
| I4 | UA | **PASS** | 104 changes, max 89.4 ms |
| I5 | both | **PASS** | 50 rounds, 50 clean; request from GEM reached the core first in 47/50 rounds |
| I6 | GEM | **PASS** | 0 of 163 window events not received; causes {} |
| I6 | UA | **PASS** | 0 of 163 window events not received; causes {} |

## Scenario-specific checks

| Check | Result | Detail |
|---|---|---|
| console remote | **PASS** |  |
| 50/50 rounds: GEM HCACK 0 and UA BadUserAccessDenied | **PASS** | 50 clean |
| console local | **PASS** |  |
| LOCAL: GEM START -> HCACK 2 | **PASS** | {'action': 'start', 'code': 2, 'code_name': 'HCACK'} |

## Latency (events)

| Side | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| GEM | 163 | 0.0 | 8.16 | 14.44 |
| UA | 163 | 52.79 | 78.16 | 89.38 |

> Latency = client receive time - core audit time, both `time.time_ns()` on the same laptop (loopback). The UA figure includes the client's 50 ms subscription publishing interval, and GEM sees the temperature only through the 1 Hz CEID 1007. These numbers describe this setup. They must not be read as one protocol being faster than the other.
