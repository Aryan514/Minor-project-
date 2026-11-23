# equipment/arbiter.py
# The control-authority policy as one pure function: given the control state, the maintenance
# lease and who is asking for what, decide allow/reject and why. No I/O, no state, no locks:
# the core calls it while holding its lock, so the decision and the state change are atomic.
# Serves N1 (explicit, tested control-authority policy for dual-interface equipment).
"""Pure control-authority policy (CLAUDE.md section 6.4)."""

from __future__ import annotations

from dataclasses import dataclass

from equipment.config import Action, ControlState, Origin

# Reason strings (also sent to clients as DVID 103 RejectReason / UA rejection text).
REASON_GEM_AUTHORITY = "authority held by GEM_HOST"
REASON_OPERATOR_STOP_ONLY = "authority held by GEM_HOST; operator may only STOP"
REASON_LOCAL = "equipment in LOCAL"
REASON_OFFLINE = "equipment OFFLINE"
REASON_NO_LEASE = "no maintenance lease"
REASON_LEASE_HELD = "maintenance lease held by UA_CLIENT"
REASON_OPERATOR_ONLY = "control state and lease are changed by the OPERATOR only"
REASON_UNKNOWN_ORIGIN = "unknown origin"

# Actions only the operator console may perform (see docs/decisions.md D3).
OPERATOR_ONLY_ACTIONS = frozenset({Action.SET_CONTROL_STATE, Action.SET_LEASE})


@dataclass(frozen=True)
class Decision:
    """Result of an authority decision."""

    allowed: bool
    reason: str = ""


ALLOW = Decision(True, "")


def authority_holder(control_state: ControlState, lease_ua: bool) -> Origin:
    """Who holds command authority in a given state (published as SVID 4 / UA Authority)."""
    if control_state == ControlState.ONLINE_REMOTE:
        return Origin.GEM_HOST
    if control_state == ControlState.EQUIPMENT_OFFLINE and lease_ua:
        return Origin.UA_CLIENT
    return Origin.OPERATOR


def decide(control_state: ControlState, lease_ua: bool, origin: Origin, action: Action) -> Decision:
    """Decide whether `origin` may perform `action` right now.

    Policy table (CLAUDE.md 6.4); the lease only counts in EQUIPMENT_OFFLINE (it is revoked when
    leaving OFFLINE, so a lease flag in any other state is ignored).

    Args:
        control_state: current simplified GEM control state.
        lease_ua: True if the UA maintenance lease is granted.
        origin: who sends the command.
        action: what is requested.

    Returns:
        Decision(allowed, reason). `reason` is empty when allowed.
    """
    if origin not in (Origin.GEM_HOST, Origin.UA_CLIENT, Origin.OPERATOR):
        return Decision(False, REASON_UNKNOWN_ORIGIN)

    if action in OPERATOR_ONLY_ACTIONS:
        return ALLOW if origin == Origin.OPERATOR else Decision(False, REASON_OPERATOR_ONLY)

    if control_state == ControlState.ONLINE_REMOTE:
        if origin == Origin.GEM_HOST:
            return ALLOW
        if origin == Origin.UA_CLIENT:
            return Decision(False, REASON_GEM_AUTHORITY)
        # OPERATOR: safety override - STOP only
        return ALLOW if action == Action.STOP else Decision(False, REASON_OPERATOR_STOP_ONLY)

    if control_state == ControlState.ONLINE_LOCAL:
        if origin == Origin.OPERATOR:
            return ALLOW
        return Decision(False, REASON_LOCAL)

    # EQUIPMENT_OFFLINE
    if origin == Origin.OPERATOR:
        return ALLOW
    if lease_ua:
        if origin == Origin.UA_CLIENT:
            return ALLOW
        return Decision(False, REASON_LEASE_HELD)
    if origin == Origin.GEM_HOST:
        return Decision(False, REASON_OFFLINE)
    return Decision(False, REASON_NO_LEASE)
