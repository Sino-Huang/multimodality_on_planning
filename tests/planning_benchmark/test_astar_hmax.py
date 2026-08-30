from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.astar_controller import AStarController, AStarOperation
from examples.planning_benchmark_slice.astar_hmax import HMaxHeuristic, UnsupportedHMaxTaskError
from examples.planning_benchmark_slice.astar_model_input import (
    build_astar_live_chat_messages,
    build_astar_live_model_input,
    build_astar_teacher_chat_messages,
    build_astar_teacher_model_input,
)
from examples.planning_benchmark_slice.episode_evidence import (
    EpisodeEvidenceError,
    materialize_episode_artifacts,
    read_episode_artifacts,
    read_episode_evidence,
    replay_astar_trace_view,
    replay_episode_evidence,
    write_episode_evidence,
)
from examples.planning_benchmark_slice.pddl_state import CanonicalState, PDDLStateAuthority
from examples.planning_benchmark_slice.search_episode import replay_search_episode, run_search_episode
from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    StopOutcome,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "planning" / "blocksworld_nontrivial.json"
EMPTY_GOAL = ROOT / "tests" / "fixtures" / "planning" / "blocksworld_empty_goal.json"
UNSOLVABLE = ROOT / "tests" / "fixtures" / "planning" / "astar_unsolvable.json"
EQUALITY = ROOT / "tests" / "fixtures" / "planning" / "hmax_equality_unsupported.json"


def _receipts(tmp_path: Path) -> tuple[GateReceipt, AuthorizationReceipt]:
    binding = ReceiptBinding("issue-60-astar", "test", tmp_path)
    gate = GateReceipt(binding, StopOutcome.PASS)
    return gate, AuthorizationReceipt(binding, gate.receipt_id)


def test_hmax_known_blocksworld_literal_values() -> None:
    payload = json.loads(FIXTURE.read_text())
    authority = PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])
    heuristic = HMaxHeuristic(authority)
    initial = authority.initial_state
    pickup = next(action for action in authority.applicable_actions(initial) if action.serialize() == "pickup(a)")
    holding_a = authority.apply(initial, pickup).target_state
    stack = next(action for action in authority.applicable_actions(holding_a) if action.serialize() == "stack(a,b)")
    goal = authority.apply(holding_a, stack).target_state

    assert heuristic(initial) == 2
    assert heuristic(holding_a) == 1
    assert heuristic(goal) == 0


def test_hmax_rejects_normalized_equality_preconditions() -> None:
    payload = json.loads(EQUALITY.read_text())
    authority = PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])

    with pytest.raises(UnsupportedHMaxTaskError, match="equality"):
        HMaxHeuristic(authority)


def test_controller_has_stable_f_priority_and_reopens_lower_g() -> None:
    domain = """(define (domain graph) (:requirements :strips) (:predicates (s) (a) (b) (c) (x))
      (:action s-a :parameters () :precondition (s) :effect (and (a) (not (s))))
      (:action s-b :parameters () :precondition (s) :effect (and (b) (not (s))))
      (:action b-c :parameters () :precondition (b) :effect (and (c) (not (b))))
      (:action c-x :parameters () :precondition (c) :effect (and (x) (not (c))))
      (:action a-x :parameters () :precondition (a) :effect (and (x) (not (a)))))"""
    problem = "(define (problem graph-p) (:domain graph) (:init (s)) (:goal (and (x) (a))))"
    authority = PDDLStateAuthority.from_pddl(domain, problem)

    class TinyAdapter:
        name = "tiny_test"

        def __call__(self, state) -> int:
            return 10 if "a" in state.atoms else 0

    controller = AStarController(authority, TinyAdapter(), accepted_delta_limit=2)
    assert controller.frontier_snapshot()[0]["priority"] == [0, 0]

    class ZeroAdapter:
        name = "zero_test"

        def __call__(self, state: CanonicalState) -> int:
            del state
            return 0

    tie_controller = AStarController(authority, ZeroAdapter(), accepted_delta_limit=2)
    tie_source = tie_controller.frontier_head_state_id()
    assert tie_source is not None
    tie_controller.start_expansion()
    for candidate in tie_controller.current_candidates():
        assert tie_controller.apply_operation(AStarOperation(tie_source, candidate.action)).accepted
    tie_controller.finish_expansion()
    assert [entry["generation_serial"] for entry in tie_controller.frontier_snapshot()] == [1, 2]

    reverse_controller = AStarController(authority, ZeroAdapter(), accepted_delta_limit=2)
    reverse_source = reverse_controller.frontier_head_state_id()
    assert reverse_source == tie_source
    assert reverse_source is not None
    reverse_controller.start_expansion()
    for candidate in reversed(reverse_controller.current_candidates()):
        assert reverse_controller.apply_operation(AStarOperation(reverse_source, candidate.action)).accepted
    reverse_controller.finish_expansion()
    assert reverse_controller.frontier_snapshot() == tie_controller.frontier_snapshot()

    def expand() -> str:
        state_id = controller.frontier_head_state_id()
        assert state_id is not None
        controller.start_expansion()
        for candidate in controller.current_candidates():
            result = controller.apply_operation(AStarOperation(state_id, candidate.action))
            assert result.accepted
        controller.finish_expansion()
        return state_id

    expand()  # s: equal-f successors retain canonical generation order
    first_two = controller.frontier_snapshot()
    assert [entry["f"] for entry in first_two] == [1, 11]
    expand()  # b
    expand()  # c
    closed_x = expand()  # x first at g=3
    expand()  # a, discovers x at g=2 and reopens it
    assert controller.best_g[closed_x] == 2
    assert closed_x not in controller.closed_g
    assert controller.frontier_head_state_id() == closed_x


def test_invalid_operation_is_charged_retained_and_does_not_repair() -> None:
    payload = json.loads(FIXTURE.read_text())
    authority = PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])
    controller = AStarController(authority, HMaxHeuristic(authority), accepted_delta_limit=2)
    controller.start_expansion()
    before = controller.snapshot()
    result = controller.apply_raw_output('{"source_state_id":"invented"}')

    assert not result.accepted
    assert result.budget_charge == 1
    assert result.raw_output == '{"source_state_id":"invented"}'
    assert controller.snapshot() == before
    assert controller.invalid_operation_count == 1
    assert controller.decision_evidence() == (
        {
            "budget_charge": 1,
            "raw_model_output": '{"source_state_id":"invented"}',
            "trusted_runtime_result": result.runtime_result,
        },
    )


def test_invalid_operation_exhausts_controller_budget_once_and_stops() -> None:
    payload = json.loads(FIXTURE.read_text())
    authority = PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])
    controller = AStarController(
        authority,
        HMaxHeuristic(authority),
        accepted_delta_limit=2,
        max_budget=1,
    )
    controller.start_expansion()
    raw = '{"source_state_id":"invented"}'

    rejected = controller.apply_raw_output(raw)
    stopped = controller.apply_raw_output(raw)

    assert rejected.budget_charge == 1
    assert controller.budget_used == 1
    assert controller.budget_exhausted
    assert stopped.budget_charge == 0
    assert stopped.runtime_result["status"] == "budget_exhausted"
    assert [item["raw_model_output"] for item in controller.decision_evidence()] == [raw, raw]
    assert controller.snapshot()["active_state_id"] == authority.initial_state.state_id


def test_teacher_and_live_use_one_canonical_input_and_message_prefix() -> None:
    payload = json.loads(FIXTURE.read_text())
    authority = PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])
    controller = AStarController(authority, HMaxHeuristic(authority), accepted_delta_limit=2)

    teacher_input = build_astar_teacher_model_input(authority, controller)
    live_input = build_astar_live_model_input(authority, controller)
    assert teacher_input == live_input
    assert teacher_input["task_context"] == authority.task_context()
    assert teacher_input["successor_candidates"]
    assert all(
        {
            "target_state_id",
            "best_cost",
            "closed",
            "dominated",
            "frontier",
            "pruned",
            "g",
            "h",
            "f",
        }
        <= item.keys()
        for item in teacher_input["successor_candidates"]
    )
    search_memory = teacher_input["search_memory"]
    assert not {"best_g", "best_cost", "closed", "frontier"} & search_memory.keys()
    assert {"best_cost_count", "closed_count", "frontier_count", "frontier_head"} <= search_memory.keys()
    live = build_astar_live_chat_messages(live_input)
    teacher = build_astar_teacher_chat_messages(teacher_input, "answer")
    assert teacher[:-1] == live

    controller.start_expansion()
    for candidate in controller.current_candidates():
        assert controller.apply_operation(AStarOperation(controller.active_state_id or "", candidate.action)).accepted
    controller.finish_expansion()
    bounded = build_astar_live_model_input(authority, controller)
    assert len(bounded["accepted_deltas"]) == 2


def test_exact_astar_episode_persists_and_mechanically_replays(tmp_path: Path) -> None:
    gate, authorization = _receipts(tmp_path)
    episode = run_search_episode(
        FIXTURE, "astar_hmax", "text-state", "exact", 64, gate, authorization
    )

    assert episode["result"]["goal_reached"] is True
    assert episode["result"]["termination"] == "goal_reached"
    assert episode["result"]["exact_reference_decision_count"] == episode["result"]["decision_count"]
    assert episode["result"]["decision_count"] != episode["result"]["expansion_count"]
    assert episode["result"]["budget_used"] == episode["result"]["expansion_count"]
    assert all(event["heuristic"]["name"] == "h_max" for event in episode["evidence"]["events"])
    assert all(event["invariants"]["hold"] is True for event in episode["evidence"]["events"])
    assert replay_search_episode(episode["evidence"]) == episode

    path = tmp_path / "astar.json.gz"
    write_episode_evidence(path, episode)
    assert read_episode_evidence(path) == episode
    assert replay_episode_evidence(path) == episode
    loaded, task, trace = read_episode_artifacts(path)
    direct_task, direct_trace = materialize_episode_artifacts(episode["evidence"])
    assert loaded == episode
    assert (task, trace) == (direct_task, direct_trace)
    trace_view = replay_astar_trace_view(task, trace)
    assert trace_view["result"] == episode["result"]
    assert trace_view["record_count"] == episode["result"]["expansion_count"]

    tampered = deepcopy(episode)
    tampered["evidence"]["events"][0]["heuristic"]["value"] += 1
    with pytest.raises((EpisodeEvidenceError, ValueError), match=r"A\*|heuristic|invariant"):
        replay_search_episode(tampered["evidence"])


@pytest.mark.parametrize(
    "tamper",
    ("priority", "serial", "best_g", "status", "reopen", "termination"),
)
def test_independent_replay_rejects_controller_defect_shaped_tampering(
    tmp_path: Path,
    tamper: str,
) -> None:
    gate, authorization = _receipts(tmp_path)
    episode = run_search_episode(FIXTURE, "astar_hmax", "text-state", "exact", 64, gate, authorization)
    changed = deepcopy(episode["evidence"])
    if tamper == "priority":
        changed["events"][0]["frontier_after"][0]["priority"][1] += 7
    elif tamper == "serial":
        changed["events"][0]["frontier_after"][0]["generation_serial"] += 7
    elif tamper == "best_g":
        changed["events"][0]["frontier_after"][0]["g"] += 1
    elif tamper == "status":
        changed["events"][0]["decisions"][0]["trusted_runtime_result"]["status"] = "dominated"
    elif tamper == "reopen":
        changed["result"]["reopen_count"] += 1
    else:
        changed["result"]["termination"] = "frontier_exhausted"

    with pytest.raises((EpisodeEvidenceError, ValueError), match=r"A\*|invariant|replay"):
        replay_search_episode(changed)


@pytest.mark.parametrize(
    ("fixture", "budget", "termination", "goal", "expansions"),
    (
        (EMPTY_GOAL, 4, "goal_reached", True, 0),
        (UNSOLVABLE, 8, "frontier_exhausted", False, 2),
        (FIXTURE, 1, "expansion_budget", False, 1),
    ),
)
def test_astar_terminates_only_at_popped_goal_exhaustion_or_budget(
    tmp_path: Path,
    fixture: Path,
    budget: int,
    termination: str,
    goal: bool,
    expansions: int,
) -> None:
    gate, authorization = _receipts(tmp_path)
    episode = run_search_episode(
        fixture, "astar_hmax", "text-state", "exact", budget, gate, authorization
    )

    assert episode["result"]["termination"] == termination
    assert episode["result"]["goal_reached"] is goal
    assert episode["result"]["expansion_count"] == expansions
    assert replay_search_episode(episode["evidence"]) == episode
