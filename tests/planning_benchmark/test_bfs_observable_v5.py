from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from examples.planning_benchmark_slice.bfs_corpus import _rolling_delta_limit
from examples.planning_benchmark_slice.bfs_model_input import build_bounded_bfs_model_input_v4
from examples.planning_benchmark_slice.bfs_phase import load_bfs_phase_gate
from examples.planning_benchmark_slice.bfs_pilot import (
    ExactBFSResult,
    QualifiedCandidate,
    select_semantically_disjoint_tasks,
)
from examples.planning_benchmark_slice.model_search_episode import _parse_model_output, run_model_search_episode
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

REPO_ROOT = Path(__file__).resolve().parents[2]

DOMAIN = """
(define (domain observable)
  (:requirements :strips :typing)
  (:types passenger floor)
  (:predicates (lift-at ?f - floor) (origin ?p - passenger ?f - floor)
               (destination ?p - passenger ?f - floor) (connected ?a - floor ?b - floor)
               (served ?p - passenger))
  (:action a-board
    :parameters (?p - passenger ?f - floor)
    :precondition (and (lift-at ?f) (origin ?p ?f))
    :effect (served ?p))
  (:action z-move
    :parameters (?a - floor ?b - floor)
    :precondition (and (lift-at ?a) (connected ?a ?b))
    :effect (and (not (lift-at ?a)) (lift-at ?b))))
"""


def _problem(name: str, *, origin: str, destination: str) -> str:
    return f"""
(define (problem {name})
  (:domain observable)
  (:objects p0 - passenger f0 f1 - floor)
  (:init (lift-at f0) (origin p0 {origin}) (destination p0 {destination}) (connected f0 f1))
  (:goal (served p0)))
"""


def _projection(authority: PDDLStateAuthority, *, visited: frozenset[str] | None = None) -> dict[str, object]:
    state = authority.initial_state
    snapshot = SimpleNamespace(
        frontier=(state.state_id,),
        heuristics={},
        known_states={state.state_id: state},
        novelty={},
        provenance=(),
        visited=visited or frozenset((state.state_id,)),
    )
    model_input, _dropped = build_bounded_bfs_model_input_v4(
        authority=authority,
        goal_atoms=list(authority.goal_atoms or ()),
        observation={
            "frontier": [state.state_id],
            "modality": "text-state",
            "state_atoms": list(state.atoms),
            "state_id": state.state_id,
        },
        checkpoint=SimpleNamespace(authority_id=authority.authority_id, snapshot=snapshot),
        accepted_deltas=(),
        max_bytes=3_840,
    )
    return model_input


def test_elevator_static_facts_and_applicable_candidates_are_observable() -> None:
    at_lift = PDDLStateAuthority.from_pddl(DOMAIN, _problem("at-lift", origin="f0", destination="f1"))
    away = PDDLStateAuthority.from_pddl(DOMAIN, _problem("away", origin="f1", destination="f0"))

    visible_at_lift = _projection(at_lift)
    visible_away = _projection(away)

    assert visible_at_lift != visible_away
    assert visible_at_lift["task_context"] != visible_away["task_context"]
    assert visible_at_lift["task_context"]["initial_dynamic_atoms"] == ["lift-at(f0)"]
    assert visible_at_lift["task_context"]["canonical_goal"] == ["atom", "served", ["p0"]]
    at_lift_actions = [
        candidate["grounded_action"]["name"]
        for candidate in visible_at_lift["search_memory"]["successor_candidates"]
    ]
    away_actions = [
        candidate["grounded_action"]["name"]
        for candidate in visible_away["search_memory"]["successor_candidates"]
    ]
    assert at_lift_actions == ["a-board", "z-move"]
    assert away_actions == ["z-move"]


def test_visited_successor_remains_visible_without_a_retained_delta() -> None:
    authority = PDDLStateAuthority.from_pddl(DOMAIN, _problem("visited", origin="f0", destination="f1"))
    state = authority.initial_state
    first_action = authority.applicable_actions(state)[0]
    target_id = authority.preview_apply(state, first_action).target_state.state_id

    model_input = _projection(authority, visited=frozenset((state.state_id, target_id)))

    candidates = model_input["search_memory"]["successor_candidates"]
    assert model_input["search_memory"]["accepted_deltas"] == []
    assert candidates[0]["grounded_action"]["name"] == "a-board"
    assert candidates[0]["visited"] is True


def test_semantic_identity_ignores_object_fact_and_goal_ordering() -> None:
    domain = """
    (define (domain reorder) (:requirements :strips :typing) (:types ball room)
      (:predicates (at ?b - ball ?r - room) (linked ?a - room ?b - room) (done ?b - ball))
      (:action finish :parameters (?b - ball ?r - room)
        :precondition (and (at ?b ?r) (linked ?r ?r)) :effect (done ?b)))
    """
    first = """
    (define (problem first) (:domain reorder)
      (:objects b1 b2 - ball r1 r2 - room)
      (:init (at b1 r1) (at b2 r2) (linked r1 r1) (linked r2 r2))
      (:goal (and (done b1) (done b2))))
    """
    reordered = """
    (define (problem second) (:domain reorder)
      (:objects r2 r1 - room b2 b1 - ball)
      (:init (linked r2 r2) (at b2 r2) (linked r1 r1) (at b1 r1))
      (:goal (and (done b2) (done b1))))
    """
    assert (
        PDDLStateAuthority.from_pddl(domain, first).semantic_task_identity()
        == PDDLStateAuthority.from_pddl(domain, reordered).semantic_task_identity()
    )


def test_semantic_selection_replaces_a_cross_split_collision() -> None:
    def candidate(split: str, identity: str, order: str) -> QualifiedCandidate:
        return QualifiedCandidate(
            candidate_id=f"{split}-{order}",
            domain_id="gripper",
            split=split,
            size_tier="easy",
            seed=1,
            normalized_problem=order,
            domain_pddl="domain",
            problem_pddl="problem",
            authority_domain_pddl="domain",
            authority_problem_pddl="problem",
            authority_transformations=(),
            result=ExactBFSResult(1, True, ("move",), ("state",)),
            semantic_task_id=identity,
        )

    selected = select_semantically_disjoint_tasks(
        [candidate("train", "same", "a"), candidate("dev", "same", "a"), candidate("dev", "replacement", "b")]
    )
    assert selected[("gripper", "easy", "train")].semantic_identity == "same"
    assert selected[("gripper", "easy", "dev")].semantic_identity == "replacement"


def test_strict_output_contract_rejects_missing_extra_and_runtime_owned_fields() -> None:
    operation = {"operation_type": "retire_frontier", "state_id": "s"}
    valid = json.dumps({"canonical_rationale": "done", "runtime_result": None, "typed_operation": operation})
    assert _parse_model_output(valid)[1] is None
    for invalid in (
        json.dumps({"canonical_rationale": "done", "typed_operation": operation}),
        json.dumps({"canonical_rationale": "done", "runtime_result": {}, "typed_operation": operation}),
        json.dumps(
            {"canonical_rationale": "done", "extra": 1, "runtime_result": None, "typed_operation": operation}
        ),
    ):
        assert _parse_model_output(invalid)[1] is not None


def test_required_observable_input_is_never_truncated_to_meet_token_budget() -> None:
    authority = PDDLStateAuthority.from_pddl(DOMAIN, _problem("tokens", origin="f0", destination="f1"))
    state = authority.initial_state
    snapshot = SimpleNamespace(
        frontier=(state.state_id,),
        heuristics={},
        known_states={state.state_id: state},
        novelty={},
        provenance=(),
        visited=frozenset((state.state_id,)),
    )
    with pytest.raises(ValueError, match="required model input"):
        build_bounded_bfs_model_input_v4(
            authority=authority,
            goal_atoms=list(authority.goal_atoms or ()),
            observation={
                "frontier": [state.state_id],
                "modality": "text-state",
                "state_atoms": list(state.atoms),
                "state_id": state.state_id,
            },
            checkpoint=SimpleNamespace(authority_id=authority.authority_id, snapshot=snapshot),
            accepted_deltas=(),
            max_bytes=3_840,
            max_input_tokens=1,
            token_counter=lambda _model_input: 2,
        )


def test_v6_corpus_uses_the_frozen_accepted_delta_limit() -> None:
    phase_gate = load_bfs_phase_gate(
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_freeze_v6.json",
        REPO_ROOT / "configs" / "experiments" / "bfs_phase_authorization_v6.json",
    )

    assert _rolling_delta_limit(phase_gate) == phase_gate.freeze["budgets"]["accepted_delta_limit"] == 16


def test_invalid_exit_with_goal_at_frontier_head_is_not_success(tmp_path: Path) -> None:
    fixture = tmp_path / "task.json"
    fixture.write_text(
        json.dumps(
            {
                "domain_pddl": DOMAIN,
                "instance_id": "goal-at-head-invalid",
                "problem_pddl": _problem("goal-at-head-invalid", origin="f0", destination="f1"),
            }
        ),
        encoding="utf-8",
    )
    binding = ReceiptBinding("v5", "invalid-goal-head", tmp_path / "evidence")
    gate = GateReceipt(binding, StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding, gate.receipt_id)
    calls = 0

    def policy(model_input: dict[str, object]) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            return "not-json"
        candidate = model_input["search_memory"]["successor_candidates"][0]
        return json.dumps(
            {
                "canonical_rationale": "first canonical successor",
                "runtime_result": None,
                "typed_operation": {
                    "action": candidate["grounded_action"],
                    "evaluate_target": False,
                    "frontier_intent": {"retire_source": True, "target_position": 0},
                    "source_state_id": model_input["observation"]["state_id"],
                    "visit_target": True,
                },
            }
        )

    episode = run_model_search_episode(
        fixture,
        algorithm="bfs",
        modality="text-state",
        arm="process_sft",
        model_identity={"decoding": "greedy", "memoize_identical_inputs": True},
        policy=policy,
        max_expansions=4,
        max_input_bytes=3_840,
        max_output_tokens=384,
        accepted_delta_limit=16,
        model_input_projection="bounded_bfs_search_memory_v4",
        seed=17,
        gate_receipt=gate,
        authorization_receipt=authorization,
    )

    assert episode["result"]["termination_reason"] == "deterministic_invalid_operation"
    assert episode["result"]["goal_reached"] is False
    assert episode["result"]["invariant_valid_success"] is False
