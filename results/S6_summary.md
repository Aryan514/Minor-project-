# S6 — results

- Run: `runs/S6_20261124-005257` (seed 42)
- Scenario: Report scope: the GEM host redefines CEID 1007's report to drop EventTemp; the UA listener's event fields must stay unchanged; a second UA subscription selects only 2 fields.
- Evaluation window: 18.0 s, 18 core events/alarms, 73 audit records in total

## Invariants

| Invariant | Side | Result | Detail |
|---|---|---|---|
| I1 | GEM | **PASS** | expected 18, received 18, missing 0, duplicates 0 |
| I1 | UA | **PASS** | expected 18, received 18, missing 0, duplicates 0 |
| I2 | GEM | **PASS** | 22 received, inversions 0, adjacent duplicates 0, gaps 0 (gaps are judged by I1/I6) |
| I2 | UA | **PASS** | 22 received, inversions 0, adjacent duplicates 0, gaps 0 (gaps are judged by I1/I6) |
| I3 | GEM | **PASS** | 22 compared, 0 mismatches; report fields absent (not values that disagree): {1007: 12} per CEID |
| I3 | UA | **PASS** | 22 compared, 0 mismatches |
| I4 | GEM | **N/A** | no state change while the client listened |
| I4 | UA | **N/A** | no state change while the client listened |
| I5 | both | **N/A** | no conflict rounds in this scenario |
| I6 | GEM | **PASS** | 0 of 18 window events not received; causes {} |
| I6 | UA | **PASS** | 0 of 18 window events not received; causes {} |

## Scenario-specific checks

| Check | Result | Detail |
|---|---|---|
| set-report accepted | **PASS** | {'action': 'set-report', 'ceid': 1007, 'vids': [101], 'code': 0} |
| GEM CEID 1007 fields before redefinition = {101, 102} | **PASS** | [['101', '102']] |
| GEM CEID 1007 fields after redefinition = {101} | **PASS** | [['101']] |
| UA listener CEID 1007 fields unchanged {101, 102} | **PASS** | before [('101', '102')], after [('101', '102')] |
| 2nd UA subscription received only the 2 fields it selected | **PASS** | {'ok': True, 'events': 8, 'fields': ['CEID', 'EventSeq']} |

## Findings

- GEM report definitions (S2F33/35/37) live on the equipment and apply to the GEM interface as a whole: the redefinition by one host changed what every later S6F11 for CEID 1007 carries. OPC UA field selection is a per-subscription EventFilter: one UA client narrowing its fields did not change another UA client's fields.

## Latency (events)

| Side | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| GEM | 18 | 0.0 | 2.07 | 2.75 |
| UA | 18 | 69.38 | 71.72 | 74.84 |

> Latency = client receive time - core audit time, both `time.time_ns()` on the same laptop (loopback). The UA figure includes the client's 50 ms subscription publishing interval, and GEM sees the temperature only through the 1 Hz CEID 1007. These numbers describe this setup. They must not be read as one protocol being faster than the other.
