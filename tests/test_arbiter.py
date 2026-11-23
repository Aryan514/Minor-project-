# tests/test_arbiter.py
# Full truth table of the control-authority policy: every (control_state x lease x origin x action)
# combination is checked against an independently written copy of the CLAUDE.md 6.4 table.
# Serves N1 (the authority policy is explicit and tested).
"""Exhaustive test of equipment.arbiter.decide."""

from __future__ import annotations

import itertools

import pytest

from equipment import arbiter
from equipment.config import Action, ControlState, Origin

GEM, UA, OP = Origin.GEM_HOST, Origin.UA_CLIENT, Origin.OPERATOR
START, STOP, EC = Action.START, Action.STOP, Action.EC_WRITE
COMMAND_ACTIONS = (START, STOP, EC)

# (control_state, effective_lease) -> origin -> {action: expected reason or None if allowed}
# Written out literally from CLAUDE.md 6.4 so the test does not reuse the implementation's logic.
EXPECTED: dict[tuple[ControlState, bool], dict[Origin, dict[Action, str | None]]] = {
    (ControlState.ONLINE_REMOTE, False): {
        GEM: {START: None, STOP: None, EC: None},
        UA: {START: "authority held by GEM_HOST", STOP: "authority held by GEM_HOST", EC: "authority held by GEM_HOST"},
        OP: {START: "authority held by GEM_HOST; operator may only STOP", STOP: None,
             EC: "authority held by GEM_HOST; operator may only STOP"},
    },
    (ControlState.ONLINE_LOCAL, False): {
        GEM: {START: "equipment in LOCAL", STOP: "equipment in LOCAL", EC: "equipment in LOCAL"},
        UA: {START: "equipment in LOCAL", STOP: "equipment in LOCAL", EC: "equipment in LOCAL"},
        OP: {START: None, STOP: None, EC: None},
    },
    (ControlState.EQUIPMENT_OFFLINE, False): {
        GEM: {START: "equipment OFFLINE", STOP: "equipment OFFLINE", EC: "equipment OFFLINE"},
        UA: {START: "no maintenance lease", STOP: "no maintenance lease", EC: "no maintenance lease"},
        OP: {START: None, STOP: None, EC: None},
    },
    (ControlState.EQUIPMENT_OFFLINE, True): {
        GEM: {START: "maintenance lease held by UA_CLIENT", STOP: "maintenance lease held by UA_CLIENT",
              EC: "maintenance lease held by UA_CLIENT"},
        UA: {START: None, STOP: None, EC: None},
        OP: {START: None, STOP: None, EC: None},
    },
}


def _effective_lease(state: ControlState, lease: bool) -> bool:
    """The lease only exists in EQUIPMENT_OFFLINE (it is revoked when leaving OFFLINE)."""
    return lease and state == ControlState.EQUIPMENT_OFFLINE


ALL_CASES = list(itertools.product(ControlState, (False, True), (GEM, UA, OP), COMMAND_ACTIONS))


def test_case_count_is_complete() -> None:
    """3 control states x 2 lease values x 3 origins x 3 actions = 54 combinations."""
    assert len(ALL_CASES) == 54


@pytest.mark.parametrize("state,lease,origin,action", ALL_CASES)
def test_policy_table(state: ControlState, lease: bool, origin: Origin, action: Action) -> None:
    """Every combination matches the CLAUDE.md policy table exactly (allowed flag and reason)."""
    expected_reason = EXPECTED[(state, _effective_lease(state, lease))][origin][action]
    decision = arbiter.decide(state, lease, origin, action)
    assert decision.allowed == (expected_reason is None)
    assert decision.reason == (expected_reason or "")


@pytest.mark.parametrize("state,lease", list(itertools.product(ControlState, (False, True))))
@pytest.mark.parametrize("action", [Action.SET_CONTROL_STATE, Action.SET_LEASE])
def test_operator_only_actions(state: ControlState, lease: bool, action: Action) -> None:
    """Control state and lease changes are allowed for the OPERATOR only, in every state."""
    assert arbiter.decide(state, lease, OP, action).allowed
    for origin in (GEM, UA):
        d = arbiter.decide(state, lease, origin, action)
        assert not d.allowed and d.reason == arbiter.REASON_OPERATOR_ONLY


def test_unknown_origin_rejected() -> None:
    """Internal origin EQUIPMENT can never command the tool."""
    for state, action in itertools.product(ControlState, COMMAND_ACTIONS):
        assert not arbiter.decide(state, True, Origin.EQUIPMENT, action).allowed


@pytest.mark.parametrize(
    "state,lease,holder",
    [
        (ControlState.ONLINE_REMOTE, False, GEM),
        (ControlState.ONLINE_REMOTE, True, GEM),
        (ControlState.ONLINE_LOCAL, False, OP),
        (ControlState.ONLINE_LOCAL, True, OP),
        (ControlState.EQUIPMENT_OFFLINE, False, OP),
        (ControlState.EQUIPMENT_OFFLINE, True, UA),
    ],
)
def test_authority_holder(state: ControlState, lease: bool, holder: Origin) -> None:
    """Authority column of the policy table."""
    assert arbiter.authority_holder(state, lease) == holder
