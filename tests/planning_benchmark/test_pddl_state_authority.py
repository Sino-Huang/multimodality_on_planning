from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.pddl_state import (
    CanonicalState,
    GroundedAction,
    InvalidActionError,
    PDDLStateAuthority,
    ReplayError,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "planning" / "blocksworld_nontrivial.json"

TYPED_CONDITIONAL_DOMAIN = """
(define (domain delegated-conditional)
  (:requirements :strips :typing :negative-preconditions :conditional-effects)
  (:types item)
  (:predicates (ready ?x - item) (blocked ?x - item) (marked ?x - item))
  (:action mark
    :parameters (?x - item)
    :precondition (and (ready ?x) (not (blocked ?x)))
    :effect (and (not (ready ?x))
                 (when (not (blocked ?x)) (marked ?x)))))
"""

TYPED_CONDITIONAL_PROBLEM = """
(define (problem delegated-conditional-problem)
  (:domain delegated-conditional)
  (:objects a b - item)
  (:init (ready a) (ready b) (blocked b))
  (:goal (marked a)))
"""


def _authority() -> PDDLStateAuthority:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])


def test_loads_canonical_initial_state_with_deterministic_identity() -> None:
    authority = _authority()

    expected_atoms = (
        "arm-empty",
        "clear(a)",
        "clear(b)",
        "clear(c)",
        "on-table(a)",
        "on-table(b)",
        "on-table(c)",
    )
    expected_id = json.dumps(list(expected_atoms), separators=(",", ":"), ensure_ascii=True)

    assert authority.domain_name == "blocksworld-4ops"
    assert authority.problem_name == "bw-nontrivial-3"
    assert authority.initial_state == CanonicalState(expected_atoms, authority_id=authority.authority_id)
    assert authority.initial_state.state_id == expected_id
    assert authority.initial_state.authority_id == authority.authority_id


def test_rejects_same_content_state_owned_by_different_authority() -> None:
    authority = _authority()
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    foreign = PDDLStateAuthority.from_pddl(
        payload["domain_pddl"],
        payload["problem_pddl"]
        .replace("bw-nontrivial-3", "bw-nontrivial-3-foreign")
        .replace("(on a b)", "(on b a)"),
    )

    assert foreign.initial_state.state_id == authority.initial_state.state_id
    assert foreign.initial_state.authority_id != authority.initial_state.authority_id
    with pytest.raises(ValueError, match="different authority"):
        authority.applicable_actions(foreign.initial_state)


def test_authority_identity_uses_normalized_pddl_semantics() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    original = PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])
    whitespace_equivalent = PDDLStateAuthority.from_pddl(
        f"\n  {payload['domain_pddl']}\n",
        f"\n\n{payload['problem_pddl']}  \n",
    )

    assert whitespace_equivalent.authority_id == original.authority_id
    assert whitespace_equivalent.initial_state == original.initial_state


def test_typed_negative_precondition_and_conditional_effect_delegate_to_plado() -> None:
    authority = PDDLStateAuthority.from_pddl(TYPED_CONDITIONAL_DOMAIN, TYPED_CONDITIONAL_PROBLEM)
    mark_a = GroundedAction("mark", ("a",))

    assert authority.applicable_actions(authority.initial_state) == (mark_a,)
    with pytest.raises(InvalidActionError, match="mark\\(b\\)"):
        authority.apply(authority.initial_state, GroundedAction("mark", ("b",)))

    transition = authority.apply(authority.initial_state, mark_a)

    assert transition.target_state.atoms == ("marked(a)", "ready(b)")
    assert authority.is_goal(transition.target_state) is True


def test_validates_and_applies_grounded_action_with_provenance() -> None:
    authority = _authority()
    pickup_a = GroundedAction("pickup", ("a",))

    assert authority.applicable_actions(authority.initial_state) == (
        GroundedAction("pickup", ("a",)),
        GroundedAction("pickup", ("b",)),
        GroundedAction("pickup", ("c",)),
    )

    transition = authority.apply(authority.initial_state, pickup_a)

    assert transition.source_state == authority.initial_state
    assert transition.action == pickup_a
    assert transition.target_state.atoms == ("clear(b)", "clear(c)", "holding(a)", "on-table(b)", "on-table(c)")
    assert transition.provenance.authority_id == authority.authority_id
    assert transition.provenance.source_state_id == transition.source_state.state_id
    assert transition.provenance.target_state_id == transition.target_state.state_id
    assert transition.transition_id == transition.provenance.provenance_id

    with pytest.raises(InvalidActionError, match="pickup\\(a\\)"):
        authority.apply(transition.target_state, pickup_a)


def test_reuses_one_grounded_applicable_action_map_per_canonical_state(monkeypatch) -> None:
    authority = _authority()
    original = authority._applicable
    applicable_calls = 0

    def counted(state):
        nonlocal applicable_calls
        applicable_calls += 1
        return original(state)

    monkeypatch.setattr(authority, "_applicable", counted)
    actions = authority.applicable_actions(authority.initial_state)
    transitions = tuple(authority.preview_apply(authority.initial_state, action) for action in actions)

    assert len(transitions) == len(actions)
    assert applicable_calls == 1


def test_replay_exactly_reproduces_trajectory_and_rejects_tampering() -> None:
    recorder = _authority()
    pickup = recorder.apply(recorder.initial_state, GroundedAction("pickup", ("a",)))
    stack = recorder.apply(pickup.target_state, GroundedAction("stack", ("a", "b")))

    replay = _authority()
    assert replay.replay((pickup, stack)) == (
        replay.initial_state,
        pickup.target_state,
        stack.target_state,
    )
    assert replay.is_goal(stack.target_state) is True

    with pytest.raises(ReplayError, match="target state"):
        replay.replay((pickup, replace(stack, target_state=pickup.target_state)))
