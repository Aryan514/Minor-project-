# Control-authority arbitration (N1)

A tool with two command interfaces needs an explicit answer to "who may command it right now?". SECS/GEM has an
answer for one host (the ONLINE_REMOTE/LOCAL control state). OPC UA has none of its own; authority is left to
the application. Our arbiter (`equipment/arbiter.py`) is a **pure function**:

```
decide(control_state, lease_ua, origin, action) -> Decision(allowed, reason)
```

It is called by the core **while holding the core lock**, and the state change is applied under the same lock. The
decision therefore cannot be invalidated between "check" and "act".

## Policy table

Actions START, STOP, EC_WRITE (TempHighLimit):

| Control state | Authority holder | GEM_HOST | UA_CLIENT | OPERATOR |
|---|---|---|---|---|
| ONLINE_REMOTE | GEM_HOST | allowed | rejected: "authority held by GEM_HOST" | STOP only (safety override); else "authority held by GEM_HOST; operator may only STOP" |
| ONLINE_LOCAL | OPERATOR | rejected: "equipment in LOCAL" | rejected: "equipment in LOCAL" | allowed |
| EQUIPMENT_OFFLINE | OPERATOR | rejected: "equipment OFFLINE" | rejected: "no maintenance lease" | allowed |
| EQUIPMENT_OFFLINE + lease | UA_CLIENT | rejected: "maintenance lease held by UA_CLIENT" | allowed | allowed |

Actions SET_CONTROL_STATE and SET_LEASE (decision D3): OPERATOR only, in every state. A GEM host asking to go
online/offline (S1F17/S1F15) is therefore refused and the attempt is audited.

Rules around the table:
- Reads (S1F3, S2F13, browse, read, subscribe) are never arbitrated.
- The lease (`lease ua`) is valid only in EQUIPMENT_OFFLINE. Leaving OFFLINE revokes it. A lease flag in another state is
  ignored by the arbiter.
- Preconditions after the arbiter: START when EXECUTING / STOP when IDLE → "already …" (HCACK 5 / BadInvalidState);
  EC value outside 20..80 → EAC 3 / BadOutOfRange; unknown RCMD/ECID → HCACK 1 / EAC 1 / BadNotFound.
- Every change of authority is audited (`kind=authority`) and announced as CEID 1004 + UA `Authority`.
- **Every rejection is announced on both interfaces** (CEID 1005 with Origin and RejectReason). A GEM host learns
  that an OPC UA client tried to command the tool, and vice versa.

## Reply-code mapping

| Outcome | S2F42 HCACK | S2F16 EAC | OPC UA StatusCode |
|---|---|---|---|
| accepted | 0 | 0 | Good |
| unknown command / ECID | 1 | 1 | BadNotFound |
| not allowed (authority) | 2 | 2 | BadUserAccessDenied |
| wrong state | 2 (lease/state) or 5 (already in state) | — | BadInvalidState |
| out of range | — | 3 | BadOutOfRange |

## Rationale

- **REMOTE means the fab host is in charge.** That is the GEM meaning of ONLINE_REMOTE, so the OPC UA side is read-only
  for commands while the tool is REMOTE. OPC UA keeps full read access, which is what analytics and digital-twin
  consumers need.
- **Operator safety override.** The operator may always STOP, even in REMOTE. Equipment safety beats host authority.
- **Maintenance lease for OPC UA.** A UA client can command the tool only when the operator has explicitly taken it
  OFFLINE and granted a lease. This is the only way UA gets authority, and it shuts the GEM host out.
- **Policy, not timing.** The winner of a conflict is decided by the policy, never by which request arrived first.
  S3 shows it: in 3 of 50 rounds the UA request reached the core *first* and still lost (`results/S3_summary.md`).

## Evidence

| What | Where | Result |
|---|---|---|
| All 54 (state × lease × origin × action) combinations + operator-only actions | `tests/test_arbiter.py` | pass |
| No bypass: deny-all arbiter → nothing changes from any of 15 entry points | `tests/test_core.py::test_no_bypass_deny_all` | pass |
| 500-iteration barrier races (REMOTE GEM vs UA; OFFLINE+lease OPERATOR vs UA; EC writes) | `tests/test_race.py` | exactly one winner every time |
| 50 cross-protocol barrier races over real HSMS + OPC UA | `results/S3_summary.md` | I5 PASS 50/50 |
| 10 cross-protocol EC conflicts + lease phase | `results/S4_summary.md` | I5 PASS 10/10, 10/10 scenario checks |
