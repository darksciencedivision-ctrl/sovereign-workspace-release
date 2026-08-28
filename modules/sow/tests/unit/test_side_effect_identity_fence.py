"""W-42 — no approval whose deciding identity is PRESUMED may become an executable side effect.

U207: `route_session_decision` fabricates `Identity(node_id="operator", role="operator")` when the
caller supplies none, and stamps `operator_identity_presumed: true`. The record is honest — nothing
on that path authenticates who is at the keyboard. What was missing is a fence: nothing stopped a
future executor reading such a decision and acting on it.

THIS UNIT DOES NOT AUTHENTICATE THE OPERATOR. U207 stays OPEN. W-42 constrains the blast radius of
the presumption; it does not remove it, and the register must keep saying so.

THE FENCE IS ONE FUNCTION AT THE NARROWEST BOUNDARY that can convert an approval into an effect,
NOT an `if operator_identity_presumed` scattered through approval types — that shape guarantees the
next approval type added forgets it.

THE TRAP THIS FILE IS WRITTEN AGAINST: no executor is attached today, so a test could "pass" simply
because nothing executes anything. That would prove a locked door secure by observing that nobody
installed hinges. So these tests drive the fence AS AN EXECUTOR WOULD — calling the exact function
any future executor must call to obtain eligibility — rather than asserting that no side effect
happened.
"""
from __future__ import annotations

import copy

import pytest

from control_plane.orchestration import session_approvals as sa
from control_plane.policy import Identity


def _presumed_decision() -> dict:
    """A decision recorded with NO authenticated operator — the U207 shape."""
    return sa._decision_base("item-1", "approve", identity_presumed=True)


def _bound_decision() -> dict:
    return sa._decision_base("item-1", "approve", identity_presumed=False)


# ---- 1, 6: recording is unaffected -------------------------------------------------------------

def test_a_presumed_operator_decision_is_still_RECORDABLE() -> None:
    """(1) + (6) The fence constrains EXECUTION, not the record. Record-only behaviour intact."""
    record = _presumed_decision()
    assert record["operator_identity_presumed"] is True
    assert record["self_authorized"] is False
    assert record["side_effects_owed"]["owed"] is True


# ---- 2, 3: the fence itself --------------------------------------------------------------------

def test_a_presumed_decision_CANNOT_authorize_a_side_effect() -> None:
    """(2) Driven through the eligibility boundary an executor must pass, not by observing absence."""
    verdict = sa.authorize_side_effect(_presumed_decision())
    assert verdict["eligible"] is False, (
        "a decision whose deciding identity was presumed was ruled eligible to execute"
    )


def test_the_refusal_NAMES_the_identity_provenance_fence() -> None:
    """(3) A refusal that does not say why sends the next reader looking for a bug."""
    verdict = sa.authorize_side_effect(_presumed_decision())
    # Matched case-INSENSITIVELY: the message emphasises PRESUMED in caps, and a test that pins the
    # casing of prose fails on a wording change that alters nothing it claims to check.
    reason = str(verdict.get("reason", "")).lower()
    assert "presumed" in reason and ("identity" in reason or "operator" in reason), reason
    assert "u207" in reason, "the refusal must point at the open debt it exists because of"


# ---- 4, 5: it cannot be talked around ----------------------------------------------------------

@pytest.mark.parametrize("mutation", [
    {"decision": "reject"},
    {"item_id": "item-99"},
    {"authority": "operator-only, honestly"},
    {"self_authorized": True},
    {"torn_down": False},
])
def test_changing_the_approval_PAYLOAD_does_not_bypass_the_fence(mutation) -> None:
    """(4) The fence keys on identity provenance, so payload edits are irrelevant to it."""
    record = {**_presumed_decision(), **mutation}
    assert sa.authorize_side_effect(record)["eligible"] is False


def test_a_FORGED_operator_role_without_authenticated_binding_does_not_bypass_it() -> None:
    """(5) The sharpest case: the caller asserts it is the operator, in the record itself."""
    forged = {**_presumed_decision(), "authority": "operator", "role": "operator",
              "operator": "operator", "identity": {"role": "operator", "node_id": "operator"}}
    assert sa.authorize_side_effect(forged)["eligible"] is False, (
        "a role string claiming 'operator' was accepted as authenticated binding"
    )
    # …and the flag itself must not be self-clearable by the same untrusted record.
    lying = {**_presumed_decision(), "operator_identity_presumed": False}
    verdict = sa.authorize_side_effect(lying)
    assert verdict["eligible"] is False, (
        "clearing `operator_identity_presumed` in the record was enough to gain eligibility — the "
        "fence trusts the record to describe its own provenance"
    )


# ---- 7: the owed marker cannot silently flip ---------------------------------------------------

def test_SIDE_EFFECTS_OWED_cannot_transition_to_executed_while_presumption_is_possible() -> None:
    """(7) Marking the debt discharged is itself a side effect and passes the same fence."""
    with pytest.raises(sa.SideEffectRefused) as exc:
        sa.mark_side_effect_executed(_presumed_decision(), effect="broker.execute")
    assert "U207" in str(exc.value)
    # The module-level marker is not mutated by an attempt.
    assert sa.SIDE_EFFECTS_OWED["owed"] is True


# ---- the positive side: the fence must be able to say yes --------------------------------------

def test_a_BOUND_operator_decision_is_eligible_so_the_fence_is_not_a_constant() -> None:
    """A fence that refuses everything is indistinguishable from no executor at all.

    This is the test that stops the whole unit being satisfied by `return False`. It is also why
    the fence takes provenance as an argument rather than reading a global.
    """
    verdict = sa.authorize_side_effect(_bound_decision(),
                                       operator=Identity("op-1", "operator", "proj"),
                                       operator_authenticated=True)
    assert verdict["eligible"] is True, verdict.get("reason")


def test_a_bound_decision_WITHOUT_an_authenticated_operator_is_still_refused() -> None:
    """Being recorded with an Identity is not the same fact as that identity being authenticated."""
    verdict = sa.authorize_side_effect(_bound_decision(),
                                       operator=Identity("op-1", "operator", "proj"),
                                       operator_authenticated=False)
    assert verdict["eligible"] is False


def test_a_non_operator_role_is_refused_even_when_authenticated() -> None:
    """Authentication answers WHO, not WHETHER they may. Invariant 1 still applies."""
    verdict = sa.authorize_side_effect(_bound_decision(),
                                       operator=Identity("w-1", "worker", "proj"),
                                       operator_authenticated=True)
    assert verdict["eligible"] is False
