# S5 — results

- Run: `runs/S5_20261124-004956` (seed 42)
- Scenario: Disconnect: normal running, the GEM host process is killed for 10 s and restarted. Expected finding: GEM misses the events of the gap (no spooling), all attributed; UA misses none.
- Evaluation window: 33.4 s, 33 core events/alarms, 121 audit records in total

## Invariants

| Invariant | Side | Result | Detail |
|---|---|---|---|
| I1 | GEM | **PASS** | expected 22, received 22, missing 0, duplicates 0 |
| I1 | UA | **PASS** | expected 33, received 33, missing 0, duplicates 0 |
| I2 | GEM | **PASS** | 27 received, inversions 0, adjacent duplicates 0, gaps 1 (gaps are judged by I1/I6) |
| I2 | UA | **PASS** | 36 received, inversions 0, adjacent duplicates 0, gaps 0 (gaps are judged by I1/I6) |
| I3 | GEM | **PASS** | 27 compared, 0 mismatches |
| I3 | UA | **PASS** | 36 compared, 0 mismatches |
| I4 | GEM | **N/A** | no state change while the client listened |
| I4 | UA | **N/A** | no state change while the client listened |
| I5 | both | **N/A** | no conflict rounds in this scenario |
| I6 | GEM | **PASS** | 11 of 33 window events not received; causes {'dropped_no_link': 11} |
| I6 | UA | **PASS** | 0 of 33 window events not received; causes {} |

## Scenario-specific checks

| Check | Result | Detail |
|---|---|---|
| GEM missed the gap's events, every loss attributed by the GEM send log | **PASS** | {'dropped_no_link': 11} |
| UA missed no event | **PASS** | {} |

## Findings

- GEM link transitions after the kill (value, ms after kill): [('NOT_COMMUNICATING', 136), ('COMMUNICATING', 11029)]
- No spooling: while the GEM host was down the GEM door dropped 11 events ({'dropped_no_link': 11}); after reconnection they were NOT re-sent. The UA client, unaffected, missed 0.

## Latency (events)

| Side | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| GEM | 22 | 0.0 | 1.71 | 2.0 |
| UA | 33 | 50.75 | 67.37 | 75.17 |

> Latency = client receive time - core audit time, both `time.time_ns()` on the same laptop (loopback). The UA figure includes the client's 50 ms subscription publishing interval, and GEM sees the temperature only through the 1 Hz CEID 1007. These numbers describe this setup. They must not be read as one protocol being faster than the other.
