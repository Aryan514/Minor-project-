# Consistency invariants I1–I6 (N3)

The checker (`harness/checker.py`) evaluates these definitions on the logs of one run. The **oracle** is the core
audit log: every event and alarm has a global, strictly increasing sequence number `seq`, assigned under the core
lock. Each side is judged against that oracle by joining on `seq`. The seq travels inside every message: DVID 101
EventSeq in S6F11, `seq=<n>` in the S5F1 text, and the `EventSeq` field of every OPC UA event.

## Notation

| Symbol | Meaning | Source |
|---|---|---|
| `E` | core records of kind `event`, `alarm_set`, `alarm_clear` | `core_audit.jsonl` |
| `ts(e)`, `seq(e)` | core timestamp and seq of a record | `core_audit.jsonl` |
| `W = [t_start, t_end]` | evaluation window: from "both clients listening" to "scenario actions done + 2 s settle" (teardown excluded) | `scenario.json` |
| `E_W` | `{e ∈ E : ts(e) ∈ W}` | |
| `R_c` | records of client `c ∈ {GEM, UA}` with kind event/alarm, **in arrival order** | `gem_host.jsonl`, `ua_client.jsonl` |
| sessions of `c` | a log is split at each `connecting` record. A session is *listening* from its `listening` record (GEM: reports defined/linked/enabled, alarm enabled; UA: subscriptions created) to its `stopped` record, or for a killed client to its last record | client logs |
| `L_c(t)` | true if some session of `c` was listening at time `t` | |
| `S_c(seq)` | send-side outcome of the door for that seq: `sent`, `dropped_no_link`, `dropped_disabled`, `error` | `gem_adapter_send.jsonl`, `ua_adapter_send.jsonl` |
| `T` | 500 ms convergence bound (`config.STATE_CONVERGENCE_T_MS`) | |
| `ε` | 1e-3 float tolerance (`config.FLOAT_TOLERANCE`) | |

## Definitions

**I1 Completeness.** For each client `c`, let `X_c = {seq(e) : e ∈ E_W, L_c(ts(e))}`. Every `s ∈ X_c` occurs in
`R_c`, and no seq occurs in `R_c` more than once.
*Fail if* `X_c \ seqs(R_c) ≠ ∅` (missing) or any duplicate exists.

**I2 Order.** For each client, the seqs of `R_c` in arrival order are strictly increasing.
*Reported:* inversions (`s_{i+1} < s_i`), adjacent duplicates, and gaps (consecutive arrivals that skip a core
event). *Fail if* inversions > 0 or duplicates > 0. Gaps are judged by I1 (while connected) and I6 (otherwise).

**I3 Value agreement.** For every received record `r` with core record `e = E[seq(r)]`:
kind(r) = kind(e) and ID(r) = ID(e) (CEID or ALID), and for each report VID `v` present in both,
`|value_r(v) − value_e(v)| ≤ ε` for numbers and equality otherwise. GEM values are read from the S6F11 report,
UA values from the `Payload` field. Because each side is compared to the core, GEM = core = UA follows.
*Fail if* any mismatch. VIDs that a side's report simply does not contain (e.g. after a GEM host redefined a report,
S6) are counted separately as **fields absent**, not as disagreement.

**I4 State convergence.** For every core change `x` in `W` of ControlState, ProcessingState, Authority or
TempHighLimit, and every client listening at `ts(x)` and still listening `T` later: the client reports the new
value within `T`.
- GEM: the first S6F11 with seq > seq(x) that carries the new value (CEID 1001/SVID 2, 1002/1003, 1004/SVID 4,
  1006/ECID 201).
- UA: the data-change notification of the matching variable whose `SourceTimestamp` equals `ts(x)` (the UA door
  writes every value with the core timestamp, so the join is exact) and whose value is the new value.
*Fail if* the observation is later than `T` or never happens.

**I5 Single winner.** For every conflict round `k` of a scenario (S3: START vs Start, S4: S2F15 vs SetTempHighLimit),
take the first record per origin (GEM_HOST, UA_CLIENT) of the round's action after `seq_before_k` (the core's last
seq read just before the barrier released both requests). Exactly one is accepted. The winner is the policy's
authority holder (GEM_HOST in ONLINE_REMOTE). The reply codes are the mapped ones (winner HCACK/EAC 0 or `Good`;
UA loser `BadUserAccessDenied`, GEM loser HCACK/EAC 2). The rejection is immediately followed by a CEID 1005 whose
Origin is the loser, and **both** clients received that CEID 1005 seq.

**I6 Loss attribution.** For each client `c` and every `e ∈ E_W` that `c` did not receive (connected or not), the
loss is *explained* if `S_c(seq(e)) ∈ {dropped_no_link, dropped_disabled, error}` or the core audited a dispatcher
overflow (`kind=dropped`) of that seq for that door. *Fail if* any loss is unexplained, e.g. the door logged
`sent` but the client never received it, or the door never processed the seq.

**Latency (reported, not an invariant).** For each received event in `W`: `ts_client − ts(e)` in ms, as p50/p95/max per
side. Both clocks are `time.time_ns()` on the same machine. The UA figure includes the client's 50 ms publishing
interval. GEM sees temperatures only via the 1 Hz CEID 1007. The figures must not be read as one protocol being faster.

## Why the windows are defined this way

- `W` excludes start-up and teardown. Events created while the equipment is shutting down can be triggered but
  never published, which would be a test artefact, not an interface property.
- I1 only expects events while a client was listening. I6 covers every other loss and requires a recorded
  cause for each one. Together they say: *nothing is lost silently.*
- I5 rounds are anchored on seq, not wall-clock time. On Windows many records share one `time_ns` value, and the
  first S3 run showed that a time window cannot separate a round from the reset command that follows it.

## Proof that the checker can fail

`python -m harness.checker runs/sample_S3 --self-test` (also run by `tests/test_checker.py`) corrupts a temporary
copy of a real run in five known ways. Each must be flagged by the invariant it violates. Result:
`results/checker_self_test.md`.

| Corruption | Must fail |
|---|---|
| remove one received GEM event that the door logged as `sent` | I1 GEM, I6 GEM |
| swap two consecutive UA events | I2 UA |
| add 1.0 °C to one GEM EventTemp | I3 GEM |
| delay one UA state notification by 2 s | I4 UA |
| turn the rejected command of one conflict round into an accepted one | I5 |
