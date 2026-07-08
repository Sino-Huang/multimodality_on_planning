from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.phase3.pddl import GroundAction, PDDLTask, ground_actions, parse_task
from scripts.phase3.gbfs import run_gbfs
from scripts.phase3.pipeline import generate_supervised_data


DOMAIN = """
(define (domain tiny)
  (:requirements :strips :typing)
  (:types loc - object)
  (:predicates (at ?x - loc) (connected ?x ?y - loc))
  (:action move
    :parameters (?from ?to - loc)
    :precondition (and (at ?from) (connected ?from ?to))
    :effect (and (at ?to) (not (at ?from))))
)
"""

PROBLEM = """
(define (problem tiny-p1)
  (:domain tiny)
  (:objects a b - loc)
  (:init (at a) (connected a b))
  (:goal (and (at b)))
)
"""


def test_gbfs_resource_limit_returns_controlled_status(tmp_path: Path) -> None:
    domain, problem = _write_pddl(tmp_path)
    task = parse_task(domain, problem)
    grounded, _status = ground_actions(task, max_grounded_actions=100, max_grounded_atoms=100)

    _plan, trace, status = run_gbfs(task, grounded, limits={"gbfs_max_depth": 200, "gbfs_max_expansions": 0, "max_plan_length": 500, "max_trace_steps": 500})

    assert status == "skipped_resource_limit"
    assert trace["algorithm"] == "greedy_best_first"
    assert trace["heuristic_source"] == "unsatisfied_goal_count"
    assert trace["expansion_count"] == 1


def test_generate_supervised_data_gbfs_estimate_gate_rejects_large_grounding(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_gbfs_gate_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    output_root = fixture_root / "phase3"

    summary = generate_supervised_data(input_root, output_root, planners=("gbfs",), limits={"gbfs_max_applicable_actions": 0})["summary"]
    attempts = [json.loads(line) for line in (output_root / "diagnostics" / "planner_attempts.jsonl").read_text(encoding="utf-8").splitlines() if line]

    assert summary["emitted_examples"] == 0
    assert attempts[0]["status"] == "skipped_resource_limit"
    assert attempts[0]["resource_gate"] == "gbfs_estimated_applicable_actions"
    shutil.rmtree(fixture_root)


def test_generate_supervised_data_emits_exact_gbfs_trace_fields(tmp_path: Path) -> None:
    fixture_root = Path("tmp") / f"phase3_gbfs_trace_{tmp_path.name}"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    input_root = _fixture_dataset(fixture_root, with_frame=True)
    output_root = fixture_root / "phase3"

    summary = generate_supervised_data(input_root, output_root, planners=("gbfs",))["summary"]
    row = json.loads((output_root / "train.jsonl").read_text(encoding="utf-8"))
    trace = row["supervised_target"]["planner_trace"]
    replay = json.loads((output_root / "diagnostics" / "replay_validation.jsonl").read_text(encoding="utf-8"))

    assert summary["emitted_examples"] == 1
    assert row["planner"] == "gbfs"
    assert trace["algorithm"] == "greedy_best_first"
    assert trace["heuristic_source"] == "unsatisfied_goal_count"
    assert trace["frontier_events"]
    assert "plan_recovery" not in trace
    assert replay["replay_ok"] is True
    assert replay["goal_satisfied"] is True
    shutil.rmtree(fixture_root)


def test_gbfs_continues_after_overlong_low_heuristic_branch() -> None:
    task = _synthetic_task(init=("s",), goal=(("g1",), ("g2",)))
    grounded = [
        _action("bad1", pre=("s",), add=(("g1",), ("b1",)), delete=(("s",),)),
        _action("bad2", pre=("b1",), add=(("g1",), ("b2",)), delete=(("b1",),)),
        _action("bad3", pre=("b2",), add=(("g1",), ("b3",)), delete=(("b2",),)),
        _action("good1", pre=("s",), add=(("a",),), delete=(("s",),)),
        _action("good2", pre=("a",), add=(("g1",), ("g2",)), delete=(("a",),)),
    ]

    plan, trace, status = run_gbfs(task, grounded, limits={"gbfs_max_depth": 10, "gbfs_max_expansions": 20, "max_plan_length": 2, "max_trace_steps": 20})

    assert status == "success_full_trace"
    assert plan == ["(good1)", "(good2)"]
    assert any(successor.get("resource_limited") is True for event in trace["frontier_events"] for successor in event["successor_heuristics"])


def test_gbfs_keeps_shorter_duplicate_state_path() -> None:
    task = _synthetic_task(init=("s",), goal=(("g1",), ("g2",)))
    grounded = [
        _action("bad1", pre=("s",), add=(("g1",), ("b1",)), delete=(("s",),)),
        _action("bad2", pre=("b1",), add=(("g1",), ("b2",)), delete=(("b1",),)),
        _action("bad3", pre=("b2",), add=(("g1",), ("x",)), delete=(("b2",),)),
        _action("good1", pre=("s",), add=(("a",),), delete=(("s",),)),
        _action("good2", pre=("a",), add=(("g1",), ("x",)), delete=(("a",),)),
        _action("finish", pre=("x",), add=(("g2",),), delete=()),
    ]

    plan, _trace, status = run_gbfs(task, grounded, limits={"gbfs_max_depth": 10, "gbfs_max_expansions": 20, "max_plan_length": 3, "max_trace_steps": 20})

    assert status == "success_full_trace"
    assert plan == ["(good1)", "(good2)", "(finish)"]


def test_gbfs_goal_successors_use_generation_order_tie_break() -> None:
    task = _synthetic_task(init=("s",), goal=(("g",),))
    grounded = [
        _action("first", pre=("s",), add=(("g",),), delete=()),
        _action("second", pre=("s",), add=(("g",),), delete=()),
    ]

    plan, trace, status = run_gbfs(task, grounded, limits={"gbfs_max_depth": 10, "gbfs_max_expansions": 20, "max_plan_length": 3, "max_trace_steps": 20})

    assert status == "success_full_trace"
    assert plan == ["(first)"]
    assert trace["frontier_events"][0]["selected_goal_successor"]["action"] == "(first)"


def _write_pddl(root: Path) -> tuple[Path, Path]:
    domain = root / "domain.pddl"
    problem = root / "problem.pddl"
    domain.write_text(DOMAIN, encoding="utf-8")
    problem.write_text(PROBLEM, encoding="utf-8")
    return domain, problem


def _synthetic_task(*, init: tuple[str, ...], goal: tuple[tuple[str, ...], ...]) -> PDDLTask:
    return PDDLTask(
        domain_name="synthetic",
        problem_name="synthetic",
        objects_by_type={},
        init=frozenset((atom,) for atom in init),
        goal=frozenset(goal),
        actions=(),
        unsupported_features=(),
    )


def _action(name: str, *, pre: tuple[str, ...], add: tuple[tuple[str, ...], ...], delete: tuple[tuple[str, ...], ...]) -> GroundAction:
    return GroundAction(name=name, args=(), preconditions=frozenset((atom,) for atom in pre), add_effects=frozenset(add), del_effects=frozenset(delete))


def _fixture_dataset(root: Path, *, with_frame: bool) -> Path:
    instance = root / "data" / "tiny" / "train" / "easy" / "tiny-train-easy-0000"
    render = instance / "render"
    frames = render / "frames"
    frames.mkdir(parents=True)
    domain, problem = _write_pddl(instance)
    (render / "result.json").write_text('{"status":"success"}\n', encoding="utf-8")
    (render / "trace.vfg.json").write_text('{"actions":["(move a b)"]}\n', encoding="utf-8")
    if with_frame:
        (frames / "frame_000.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    input_root = root / "data"
    (input_root / "summary.json").write_text('{"accepted_total":1}\n', encoding="utf-8")
    row = {
        "index": 0,
        "domain_id": "tiny",
        "instance_id": "tiny-train-easy-0000",
        "split": "train",
        "bucket": "easy",
        "domain_path": str(domain),
        "problem_path": str(problem),
        "render_result_path": str(render / "result.json"),
    }
    (input_root / "accepted_manifest.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    return input_root
