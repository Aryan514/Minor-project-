# S4 — results

- Run: `runs/S4_20261124-005157` (seed 42)
- Scenario: EC conflict: REMOTE, GEM sets 35 while UA sets 45 (10 barrier rounds) -> only GEM applied; then OFFLINE + lease ua: UA sets 45 -> applied and seen by GEM as CEID 1006; GEM write -> EAC 2.
- Evaluation window: 4.5 s, 43 core events/alarms, 117 audit records in total

## Invariants

| Invariant | Side | Result | Detail |
|---|---|---|---|
| I1 | GEM | **PASS** | expected 43, received 43, missing 0, duplicates 0 |
| I1 | UA | **PASS** | expected 43, received 43, missing 0, duplicates 0 |
| I2 | GEM | **PASS** | 47 received, inversions 0, adjacent duplicates 0, gaps 0 (gaps are judged by I1/I6) |
| I2 | UA | **PASS** | 47 received, inversions 0, adjacent duplicates 0, gaps 0 (gaps are judged by I1/I6) |
| I3 | GEM | **PASS** | 47 compared, 0 mismatches |
| I3 | UA | **PASS** | 47 compared, 0 mismatches |
| I4 | GEM | **PASS** | 28 changes, max 13.4 ms |
| I4 | UA | **PASS** | 27 changes, max 70.9 ms; 1 same-value EC re-write(s): no UA notification by design, client already held the core value |
| I5 | both | **PASS** | 10 rounds, 10 clean; request from GEM reached the core first in 10/10 rounds |
| I6 | GEM | **PASS** | 0 of 43 window events not received; causes {} |
| I6 | UA | **PASS** | 0 of 43 window events not received; causes {} |

## Scenario-specific checks

| Check | Result | Detail |
|---|---|---|
| console remote | **PASS** |  |
| REMOTE conflict: final limit 35 in core, GEM (S2F13) and UA | **PASS** | core 35.0, GEM 35.0, UA 35.0 |
| console offline | **PASS** |  |
| console lease ua | **PASS** |  |
| leased UA SetTempHighLimit(45) -> Good | **PASS** | Good |
| GEM host received CEID 1006 with 201=45 (UA's change) | **PASS** | [{'101': 89, '104': 'UA_CLIENT', '201': 45.0}] |
| leased: GEM S2F15 -> EAC 2 | **PASS** | {'action': 'set-limit', 'value': 30.0, 'code': 2, 'code_name': 'EAC'} |
| final limit 45 in core and UA | **PASS** |  |
| console lease off | **PASS** |  |
| console local | **PASS** |  |

## Findings

- Semantic mismatch: 1 accepted EC write(s) re-wrote TempHighLimit with the value it already had. GEM reported each one as CEID 1006 (an event per accepted write). The OPC UA client got no data-change notification (default DataChangeTrigger StatusValue reports value changes only), so a UA client cannot observe such a write through the variable. The core and both sides still agreed on the value (I4 PASS).

## Latency (events)

| Side | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| GEM | 43 | 2.0 | 6.16 | 13.45 |
| UA | 43 | 37.65 | 69.01 | 71.91 |

> Latency = client receive time - core audit time, both `time.time_ns()` on the same laptop (loopback). The UA figure includes the client's 50 ms subscription publishing interval, and GEM sees the temperature only through the 1 Hz CEID 1007. These numbers describe this setup. They must not be read as one protocol being faster than the other.
