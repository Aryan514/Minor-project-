# Claims → code → tests → evidence

Every number below is copied from `results/` (scenario runs of 2026-11-24, seed 42, one Windows laptop, loopback).
Nothing is estimated.

| Claim | Code | Tests | Evidence |
|---|---|---|---|
| **N1** Single core serving SECS/GEM (HSMS) and OPC UA simultaneously, with an explicit control-authority arbiter and atomic decide-and-apply | `equipment/core.py`, `arbiter.py`, `dispatcher.py`, `gem_adapter.py`, `opcua_adapter.py`; `docs/library_overrides.md` (14 library defaults that would bypass the arbiter, duplicate state or break an invariant, each overridden) | `test_arbiter.py` (54 combinations + operator-only actions), `test_core.py::test_no_bypass_deny_all` (15 entry points), `test_race.py` (4 × 500 barrier races), `test_dispatcher.py`: **95 tests pass** | **S3**: I5 PASS, 50/50 concurrent GEM-START / UA-Start pairs had exactly one winner (GEM, as REMOTE prescribes); the UA request had reached the core first in 3/50 rounds and still lost; the CEID 1005 of every loser reached both clients; LOCAL → HCACK 2. **S4**: I5 PASS 10/10 EC conflicts, final limit 35 on core, GEM and UA; leased UA write applied and seen by GEM; GEM write under lease → EAC 2 (10/10 scenario checks). |
| **N2** GEM-derived draft OPC UA information model + semantic mismatches observed under simultaneous use | `equipment/opcua_model.py`, `docs/information_model.md`, `docs/mapping.md` | `ua_client --browse` output (types, instance, GemId/GemKind/GemFormat on every mapped node) | **S6**: a GEM report redefinition changed every later S6F11 for CEID 1007 (fields {101,102} → {101}). The UA listener's fields were unchanged, and a second UA subscription chose its own 2 fields (5/5 checks). **S4**: a same-value EC write was a CEID 1006 event on GEM but produced no UA data change. **S5**: no spooling on either side. **Alarm ack**: S5F2 (message receipt) ≠ UA Acknowledge (operator action); not implemented by asyncua. |
| **N3** Cross-interface consistency method: seq-numbered audit oracle + send-side and receive-side logs on both protocols + checker of formal invariants under normal, conflict and fault scenarios | `equipment/audit.py`, door send logs, client receive logs, `harness/checker.py`, `harness/scenarios.py`, `docs/invariants.md` | `test_checker.py`: the checker passes the real sample run and **flags all 5 injected corruptions** (drop → I1+I6, swap → I2, value → I3, delay → I4, double winner → I5): `results/checker_self_test.md` | **S1** (62 s normal): 62/62 events on both sides, 0 inversions, 0 value mismatches. **S2** (alarm): set/clear seqs 77/98 identical on core, GEM and UA; I4 PASS. **S5** (fault): 11 GEM losses, all attributed `dropped_no_link` (I6 PASS), UA 0 losses; link loss detected 136 ms after the kill. Across S1–S6: **351 window events per side, 0 unexplained losses, 0 value mismatches, 0 order inversions.** |

## Measured latency (event receive time − core audit time)

| Scenario | GEM p50 / p95 / max (ms) | UA p50 / p95 / max (ms) |
|---|---|---|
| S1 normal | 0.0 / 2.05 / 2.27 | 48.6 / 64.53 / 78.74 |
| S2 alarm | 0.0 / 2.5 / 6.08 | 50.5 / 58.34 / 78.96 |
| S3 conflict | 0.0 / 7.82 / 17.08 | 46.97 / 75.23 / 90.69 |
| S4 EC conflict | 2.0 / 6.16 / 13.45 | 37.65 / 69.01 / 71.91 |
| S5 disconnect | 0.0 / 1.71 / 2.0 | 50.75 / 67.37 / 75.17 |
| S6 report scope | 0.0 / 2.07 / 2.75 | 69.38 / 71.72 / 74.84 |

**Caveat (must accompany these numbers):** both clocks are `time.time_ns()` on one machine, and Windows clock granularity
makes sub-millisecond values (the GEM p50 of 0.0) unreliable. The UA figure includes the client's 50 ms subscription
publishing interval, a configuration choice. GEM sees the temperature only through the 1 Hz CEID 1007. These figures
**do not show that one protocol is faster** than the other.

## Positioning against prior work

To our knowledge, based on our literature search: Golra & Engel (IEEE ETFA 2021) mapped GEM concepts to an OPC UA
information model, but did not study both interfaces in use at the same time and left out spooling. Agileo (2020),
ErgoTech TransSECS and Sun et al. (IEEE ICWCSG 2021) describe translation/gateway prototypes, where one protocol is
converted into the other. This work differs in three ways:
1. both interfaces are served natively by one equipment core;
2. command authority across the two interfaces is defined explicitly and tested, including concurrent conflicts;
3. cross-interface consistency is *measured* against a sequence-numbered oracle, with every loss attributed.

The scope is one simulated tool on one laptop (loopback). It is not fab-scale and makes no GEM compliance claim.
