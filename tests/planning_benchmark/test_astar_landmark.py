from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.astar_controller import AStarController, AStarOperation
from examples.planning_benchmark_slice.astar_landmarks import LandmarkCountHeuristic
from examples.planning_benchmark_slice.astar_model_input import (
    build_astar_live_chat_messages,
    build_astar_live_model_input,
    build_astar_teacher_chat_messages,
    build_astar_teacher_model_input,
    build_bounded_astar_model_input,
    serialize_astar_message_prefix,
)
from examples.planning_benchmark_slice.episode_evidence import (
    EpisodeEvidenceError,
    read_episode_artifacts,
    replay_astar_trace_view,
    replay_episode_evidence,
    write_episode_evidence,
)
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority
from examples.planning_benchmark_slice.search_episode import replay_search_episode, run_search_episode
from examples.planning_benchmark_slice.strips_relaxation import UnsupportedSTRIPSTaskError
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "planning" / "landmark_progression.json"
UNSOLVABLE = ROOT / "tests" / "fixtures" / "planning" / "astar_unsolvable.json"
EQUALITY = ROOT / "tests" / "fixtures" / "planning" / "hmax_equality_unsupported.json"


def _authority(path: Path = FIXTURE) -> PDDLStateAuthority:
    payload = json.loads(path.read_text())
    return PDDLStateAuthority.from_pddl(payload["domain_pddl"], payload["problem_pddl"])


def _receipts(tmp_path: Path) -> tuple[GateReceipt, AuthorizationReceipt]:
    binding = ReceiptBinding("issue-61-landmarks", "test", tmp_path)
    gate = GateReceipt(binding, StopOutcome.PASS)
    return gate, AuthorizationReceipt(binding, gate.receipt_id)


def _apply(authority: PDDLStateAuthority, state, action_name: str):
    action = next(action for action in authority.applicable_actions(state) if action.name == action_name)
    return authority.apply(state, action).target_state


def test_landmark_catalog_intersects_first_achievers_and_tracks_progression() -> None:
    authority = _authority()
    heuristic = LandmarkCountHeuristic(authority)

    assert heuristic.catalog.to_dict() == {
        "edges": [["p", "g"], ["s", "p"]],
        "landmarks": ["g", "p", "s"],
    }
    initial = authority.initial_state
    progress = heuristic.initial(initial)
    assert heuristic.progress_payload(initial, progress) == {
        "accepted": ["s"],
        "needed_again": [],
        "unaccepted": ["g", "p"],
    }
    assert heuristic.value(initial, progress) == 2

    with_p = _apply(authority, initial, "make-p")
    accepted_p = heuristic.advance(progress, initial, with_p)
    assert heuristic.transition_payload(progress, accepted_p, initial, with_p) == {
        "newly_accepted": ["p"],
        "re_achieved": [],
    }
    dropped = _apply(authority, with_p, "drop-p")
    needed = heuristic.advance(accepted_p, with_p, dropped)
    assert heuristic.progress_payload(dropped, needed)["needed_again"] == ["p"]
    assert heuristic.value(dropped, needed) == 2
    restored = _apply(authority, dropped, "restore-p")
    restored_progress = heuristic.advance(needed, dropped, restored)
    assert heuristic.transition_payload(needed, restored_progress, dropped, restored)["re_achieved"] == ["p"]


def test_landmarks_reject_normalized_equality() -> None:
    with pytest.raises(UnsupportedSTRIPSTaskError, match="equality"):
        LandmarkCountHeuristic(_authority(EQUALITY))


@pytest.mark.parametrize(
    "effect",
    (
        "(when (ready) (done))",
        "(probabilistic 1 (done))",
        "(and (done) (increase (fuel) 1))",
    ),
)
def test_landmarks_reject_conditional_probabilistic_and_numeric_effects(effect: str) -> None:
    requirements = ":strips :fluents :conditional-effects :probabilistic-effects"
    domain = (
        f"(define (domain unsupported) (:requirements {requirements}) "
        "(:predicates (ready) (done)) (:functions (fuel)) "
        f"(:action step :parameters () :precondition (ready) :effect {effect}))"
    )
    problem = (
        "(define (problem unsupported-p) (:domain unsupported) "
        "(:init (ready) (= (fuel) 0)) (:goal (done)))"
    )
    authority = PDDLStateAuthority.from_pddl(domain, problem)

    with pytest.raises(UnsupportedSTRIPSTaskError, match=r"conditional|probabilistic|numeric"):
        LandmarkCountHeuristic(authority)


def test_same_world_state_has_distinct_landmark_progress_nodes() -> None:
    authority = _authority()
    heuristic = LandmarkCountHeuristic(authority)
    controller = AStarController(authority, heuristic, accepted_delta_limit=4, max_budget=8)
    initial_node = controller.frontier_head_state_id()
    assert initial_node is not None
    controller.start_expansion()
    make_p = controller.current_candidates()[0]
    assert controller.apply_operation(AStarOperation(initial_node, make_p.action)).accepted
    controller.finish_expansion()

    p_node = controller.frontier_head_state_id()
    assert p_node is not None
    controller.start_expansion()
    reset = next(candidate for candidate in controller.current_candidates() if candidate.action.name == "reset-p")
    assert reset.target_state.state_id == authority.initial_state.state_id
    assert reset.target_node_id != initial_node
    assert controller.apply_operation(AStarOperation(p_node, reset.action)).accepted
    assert controller.visited_count > len(controller.states)
    next_input = build_astar_live_model_input(authority, controller)
    assert next_input["search_memory"]["visited_count"] == controller.visited_count


def test_landmark_teacher_live_input_is_bounded_markov_sufficient() -> None:
    authority = _authority()
    controller = AStarController(authority, LandmarkCountHeuristic(authority), accepted_delta_limit=2)

    teacher_input = build_astar_teacher_model_input(authority, controller)
    live_input = build_astar_live_model_input(authority, controller)
    assert teacher_input == live_input
    assert teacher_input["heuristic_context"] == {
        "edges": [["p", "g"], ["s", "p"]],
        "landmarks": ["g", "p", "s"],
    }
    assert teacher_input["current"]["progression"]["accepted"] == ["s"]
    candidate = teacher_input["successor_candidates"][0]
    assert {"target_node_id", "target_state_id", "progression", "progression_delta"} <= candidate.keys()
    assert not {"best_g", "closed", "frontier"} & teacher_input["search_memory"].keys()
    assert build_astar_teacher_chat_messages(teacher_input, "answer")[:-1] == build_astar_live_chat_messages(
        live_input
    )
    system_contract = build_astar_live_chat_messages(live_input)[0]["content"]
    assert "h_max" not in system_contract
    assert "declared heuristic" in system_contract


def test_landmark_bounded_teacher_live_bytes_truncate_only_oldest_deltas() -> None:
    authority = _authority()
    controller = AStarController(authority, LandmarkCountHeuristic(authority), accepted_delta_limit=4)
    controller.start_expansion()
    for candidate in controller.current_candidates():
        assert controller.apply_operation(AStarOperation(controller.active_state_id or "", candidate.action)).accepted
    controller.finish_expansion()

    full = build_bounded_astar_model_input(authority, controller, max_bytes=1_000_000)
    one_delta = deepcopy(full)
    one_delta["accepted_deltas"] = full["accepted_deltas"][-1:]
    limit = len(json.dumps(one_delta, sort_keys=True, separators=(",", ":")).encode())
    bounded = build_bounded_astar_model_input(authority, controller, max_bytes=limit)
    assert bounded["accepted_deltas"] == full["accepted_deltas"][-1:]
    assert {key: value for key, value in bounded.items() if key != "accepted_deltas"} == {
        key: value for key, value in full.items() if key != "accepted_deltas"
    }
    teacher_bytes = json.dumps(
        build_astar_teacher_chat_messages(bounded, "answer")[:-1], sort_keys=True, separators=(",", ":")
    ).encode()
    live_bytes = json.dumps(build_astar_live_chat_messages(bounded), sort_keys=True, separators=(",", ":")).encode()
    assert teacher_bytes == live_bytes
    assert serialize_astar_message_prefix(bounded) == build_astar_live_chat_messages(bounded)
    with pytest.raises(ValueError, match="required facts"):
        build_bounded_astar_model_input(authority, controller, max_bytes=1)


def test_exact_landmark_episode_persists_materializes_and_independently_replays(tmp_path: Path) -> None:
    gate, authorization = _receipts(tmp_path)
    episode = run_search_episode(
        FIXTURE, "astar_landmark_count", "text-state", "exact", 16, gate, authorization
    )

    assert episode["result"]["goal_reached"] is True
    assert episode["result"]["exact_reference_decision_count"] == episode["result"]["decision_count"]
    assert episode["result"]["decision_count"] != episode["result"]["expansion_count"]
    assert replay_search_episode(episode["evidence"]) == episode
    path = tmp_path / "landmark.json.gz"
    write_episode_evidence(path, episode)
    assert replay_episode_evidence(path) == episode
    loaded, task, trace = read_episode_artifacts(path)
    assert loaded == episode
    assert replay_astar_trace_view(task, trace)["result"] == episode["result"]


def test_landmark_replay_does_not_call_production_progression(tmp_path: Path, monkeypatch) -> None:
    gate, authorization = _receipts(tmp_path)
    episode = run_search_episode(
        FIXTURE, "astar_landmark_count", "text-state", "exact", 16, gate, authorization
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("production landmark progression was called during replay")

    monkeypatch.setattr(LandmarkCountHeuristic, "advance", forbidden)
    assert replay_search_episode(episode["evidence"]) == episode


def test_landmark_replay_accepts_and_retains_semantic_noncanonical_raw_json(tmp_path: Path) -> None:
    authority = _authority()
    controller = AStarController(authority, LandmarkCountHeuristic(authority), accepted_delta_limit=2)
    source = controller.frontier_head_state_id()
    assert source is not None
    controller.start_expansion()
    candidate = controller.current_candidates()[0]
    submitted_raw = json.dumps(
        {"source_state_id": source, "action": {"name": candidate.action.name, "args": list(candidate.action.args)}},
        indent=2,
    )
    accepted = controller.apply_raw_output(submitted_raw)
    assert accepted.accepted and accepted.raw_output == submitted_raw

    gate, authorization = _receipts(tmp_path)
    episode = run_search_episode(
        FIXTURE, "astar_landmark_count", "text-state", "exact", 16, gate, authorization
    )
    operation = episode["evidence"]["events"][0]["decisions"][0]["operation"]
    raw = json.dumps(
        {"source_state_id": operation["source_state_id"], "action": operation["action"]},
        indent=2,
    )
    episode["evidence"]["events"][0]["decisions"][0]["raw_model_output"] = raw

    replayed = replay_search_episode(episode["evidence"])

    assert replayed["evidence"]["events"][0]["decisions"][0]["raw_model_output"] == raw


@pytest.mark.parametrize("field", ("catalog", "progression", "node_id", "h"))
def test_independent_landmark_replay_rejects_tampering(tmp_path: Path, field: str) -> None:
    gate, authorization = _receipts(tmp_path)
    episode = run_search_episode(
        FIXTURE, "astar_landmark_count", "text-state", "exact", 16, gate, authorization
    )
    changed = deepcopy(episode["evidence"])
    if field == "catalog":
        changed["header"]["request"]["landmark_catalog"]["landmarks"].append("invented")
    elif field == "progression":
        changed["events"][0]["decisions"][0]["trusted_runtime_result"]["progression"]["accepted"] = []
    elif field == "node_id":
        changed["events"][0]["decisions"][0]["trusted_runtime_result"]["target_node_id"] = "invented"
    else:
        changed["events"][0]["decisions"][0]["trusted_runtime_result"]["h"] += 1

    with pytest.raises((EpisodeEvidenceError, ValueError), match=r"landmark|A\*|invariant|replay"):
        replay_search_episode(changed)


@pytest.mark.parametrize(
    ("fixture", "budget", "termination", "goal"),
    (
        (FIXTURE, 1, "expansion_budget", False),
        (UNSOLVABLE, 8, "frontier_exhausted", False),
    ),
)
def test_landmark_episode_budget_and_exhaustion(
    tmp_path: Path,
    fixture: Path,
    budget: int,
    termination: str,
    goal: bool,
) -> None:
    gate, authorization = _receipts(tmp_path)
    episode = run_search_episode(
        fixture, "astar_landmark_count", "text-state", "exact", budget, gate, authorization
    )
    assert episode["result"]["termination"] == termination
    assert episode["result"]["goal_reached"] is goal
    assert replay_search_episode(episode["evidence"]) == episode
