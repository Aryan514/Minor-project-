# GEM → OPC UA mapping and observed gaps (N2)

"Status" says what is implemented. "Observed" is what the scenarios measured when both interfaces were used **at
the same time** on one tool. The semantic gaps are findings of this project, not defects to hide.

| GEM concept | Our OPC UA construct | Fit | Status | Semantic gap | Observed |
|---|---|---|---|---|---|
| SVID (S1F3/F4) | `GemMappedVariableType` variable + GemId/GemKind/GemFormat + EngineeringUnits | full | SVIDs 1–5 | GEM unit string ("degC") vs `EUInformation` (UNECE code CEL) | S1–S6: values agree with the core (I3 PASS). UA gets every 0.5 s temperature sample as a data change; GEM sees the temperature only in the 1 Hz CEID 1007 or on request (S1F3). |
| DVID | Event field (`EventSeq`) and `Payload` | partial | DVIDs 101–104 | only meaningful at event time; no variable | I3 PASS on all 7 CEIDs in every scenario |
| ECID (S2F13/F15) | Read-only variable + method `SetTempHighLimit` via arbiter | full | ECID 201 | EAC (0/1/2/3) vs StatusCode; **a re-write of the same value is a CEID 1006 event in GEM but produces no UA data-change notification** | S4: 10/10 conflicts GEM wins, final 35 on core/GEM/UA; leased UA write seen by GEM as CEID 1006. **Finding:** 1 same-value write was invisible on UA (DataChangeTrigger StatusValue) while GEM reported it. |
| Report define/link/enable (S2F33/35/37) | Event subscription + EventFilter select clauses | partial | library's dynamic reports | **GEM reports are global state of the GEM interface on the tool; UA field selection is per client** | S6: one GEM host redefined CEID 1007's report → every later S6F11 for 1007 lost EventTemp. The UA listener's fields stayed {101,102}. A second UA subscription selected only {CEID, EventSeq} without affecting the first. Report definitions also **outlive the host session**: after a host restart the old reports keep firing until redefined (D23). |
| Event report (S6F11/F12) | `GemCollectionEventType` | full | all 7 CEIDs, DATAID = seq | S6F12 is a per-message acknowledgement; UA has no application-level ack (publish acks are transport-level) | I1/I2 PASS in every scenario (e.g. S1: 62/62 on both sides, 0 inversions) |
| Alarm (S5F1/F2) | `GemOffNormalAlarmType` (OffNormalAlarmType subtype) | partial | set/clear with ALID + EventSeq | **S5F2 = "message received"; UA Acknowledge = "an operator has seen it"**. asyncua implements no server-side Acknowledge/Confirm, so the UA acknowledge path does not exist here. | S2 and demo: the set/clear seqs are identical on core, GEM (S5F1 text `seq=n`) and UA (EventSeq), e.g. 77/98 in S2 |
| Remote command (S2F41/F42) | Methods `Start`/`Stop` | full | RCMD START/STOP | **ONLINE_REMOTE authority has no UA equivalent** → arbiter (N1) | S3: 50/50 concurrent START pairs, GEM always won in REMOTE (I5 PASS), and in 3/50 rounds the UA request had arrived first. LOCAL → HCACK 2. |
| Control state | `ControlState`/`ControlStateId` + CEID 1001 | partial | 3-state simplified model | simplified (no HOST_OFFLINE/ATTEMPT_ONLINE); host S1F15/S1F17 refused (operator-only, D3) | I4 PASS: GEM ≤ 17 ms, UA ≤ 91 ms (S3, 104 changes) |
| Communication state | `GemInterface/CommunicationState` | — | mirrored from HSMS link | GEM-only concept, exposed to UA as information | S5: NOT_COMMUNICATING audited 136 ms after the host was killed |
| Spooling | — | none | not implemented | UA has no spool; secsgem does not implement GEM spooling | **S5: 11 events dropped while the GEM host was down, all logged `dropped_no_link`, none re-sent after reconnection. UA missed 0.** |

## Summary of the semantic mismatches found under simultaneous use

1. **Report scope.** A GEM report change by one host is global; a UA filter is private to its subscription (S6).
2. **Alarm acknowledgement means different things.** S5F2 acknowledges a message; UA Acknowledge records an operator
   action. Neither maps onto the other, and in this stack the UA acknowledge is not even implemented.
3. **"Changed" events vs value changes.** GEM fires CEID 1006 for every accepted EC write. A UA data-change subscription
   only reports a *different* value, so a same-value write is invisible on UA (S4).
4. **Spooling.** GEM defines spooling (not implemented by secsgem). UA has no concept of it. In both cases, data
   produced while a client is disconnected is lost to that client (S5). The design's job is to make the loss
   **attributable** (I6), which it does.
5. **Command authority.** GEM has one; UA has none. The arbiter supplies one rule for both (S3, S4).
6. **Delivery timing differs by construction.** UA delivers in publishing-interval batches (50 ms in our client);
   GEM sends each S6F11 immediately. The measured latencies reflect configuration, not protocol quality.
