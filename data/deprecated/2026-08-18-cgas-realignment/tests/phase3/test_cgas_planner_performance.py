from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType

import pytest

import scripts.phase3.local_iw as local_iw
import scripts.phase3.local_serial as local_serial
from scripts.phase3.cgas_partition_characterization import _planner_record, characterize_instances, load_accepted_blocksworld
from scripts.phase3.cgas_bfs import run_fifo_bfs
from scripts.phase3.local_planner_types import JSONValue, LocalPlannerRequest
from scripts.phase3.pddl import GroundAction, PDDLTask


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_characterization_disables_all_iw_recovery_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: an accepted row whose width-one IW currently exhausts novelty search.
    source = REPOSITORY_ROOT / "data/curriculum_pddl/accepted_manifest.jsonl"
    instance = next(
        row
        for row in load_accepted_blocksworld(source)
        if row.instance_id == "blocksworld-dev-easy-0001"
    )
    calls: list[str] = []

    def unexpected_serial(*_args) -> None:
        calls.append("bounded_serial_plan")
        raise AssertionError("characterization entered serial recovery")

    def unexpected_goal_recovery(*_args) -> None:
        calls.append("goal_regression")
        raise AssertionError("characterization entered goal-regression recovery")

    monkeypatch.setattr(local_iw, "bounded_serial_plan", unexpected_serial)
    monkeypatch.setattr(local_iw, "recover_goal_regression_plan", unexpected_goal_recovery)

    # When: characterization invokes native width-one IW under its fixed limits.
    row = characterize_instances((instance,))[0]

    # Then: exhaustion remains the native non-exact outcome with no recovery event.
    iw = row["iw_width_1"]
    assert isinstance(iw, dict)
    assert calls == []
    assert iw["exact_search"] == {
        "expansion_count": 15,
        "plan_length": 0,
        "status": "not_exact_solution",
    }


def test_non_characterization_iw_keeps_recovery_enabled_by_default() -> None:
    # Given: the same accepted task with a planner request that omits a recovery policy.
    source = REPOSITORY_ROOT / "data/curriculum_pddl/accepted_manifest.jsonl"
    instance = next(
        row
        for row in load_accepted_blocksworld(source)
        if row.instance_id == "blocksworld-dev-easy-0001"
    )
    from scripts.phase3.pddl import ground_actions, parse_task

    task = parse_task(instance.domain_path, instance.problem_path)
    grounded, status = ground_actions(task, max_grounded_actions=100_000, max_grounded_atoms=100_000)

    # When: the existing planner caller uses its current default limits.
    result = local_iw.run_iterated_width(
        LocalPlannerRequest(
            "iw",
            task,
            tuple(grounded),
            {
                "gbfs_max_depth": 128,
                "gbfs_max_expansions": 10_000,
                "local_iw_max_width": 1,
                "local_iw_novelty_max_expansions": 10_000,
                "local_iw_width": 1,
                "local_max_applicable_actions": 2_000,
                "max_plan_length": 128,
                "max_trace_steps": 10_000,
            },
        )
    )

    # Then: recovery remains the legacy default outside characterization.
    assert status is None
    assert result.status == "success_full_trace"
    assert "plan_recovery" in result.trace


def test_bfs_retained_trace_bytes_preserve_success_and_resource_limit_metrics() -> None:
    # Given: canonical linear searches with both successful and capped outcomes.
    task, actions = _linear_task()

    # When: each outcome runs once with complete retention and once with one snapshot.
    successful_full = run_fifo_bfs(
        task,
        actions,
        {"max_expansions": 10, "max_plan_length": 10, "max_trace_steps": 10},
    )
    successful_bounded = run_fifo_bfs(
        task,
        actions,
        {"max_expansions": 10, "max_plan_length": 10, "max_trace_steps": 1},
    )
    limited_full = run_fifo_bfs(
        task,
        actions,
        {"max_expansions": 1, "max_plan_length": 10, "max_trace_steps": 10},
    )
    limited_bounded = run_fifo_bfs(
        task,
        actions,
        {"max_expansions": 1, "max_plan_length": 10, "max_trace_steps": 1},
    )

    # Then: counts, statuses, plans, and every retained snapshot retain their exact bytes.
    assert (successful_bounded.plan, successful_bounded.status) == (
        successful_full.plan,
        "success_truncated_trace",
    )
    assert successful_bounded.trace["expansion_count"] == successful_full.trace["expansion_count"]
    assert _first_snapshot_bytes(successful_bounded.trace) == _first_snapshot_bytes(successful_full.trace)
    assert (limited_bounded.plan, limited_bounded.status) == (limited_full.plan, limited_full.status)
    assert limited_bounded.trace["expansion_count"] == limited_full.trace["expansion_count"]
    assert _first_snapshot_bytes(limited_bounded.trace) == _first_snapshot_bytes(limited_full.trace)


def test_iw_counts_total_expansions_when_trace_retention_is_zero() -> None:
    # Given: a native two-step IW task under complete and zero event retention.
    task, actions = _linear_task()
    full = local_iw.run_iterated_width(_iw_request(task, actions, max_trace_steps=10))
    bounded = local_iw.run_iterated_width(_iw_request(task, actions, max_trace_steps=0))

    # When: canonical width-one IW finds the same plan through both retention policies.
    assert (full.plan, bounded.plan) == (["(advance-0)", "(advance-1)"], ["(advance-0)", "(advance-1)"])

    # Then: the total count is stable while zero retention is explicitly truncated.
    assert full.status == "success_full_trace"
    assert bounded.status == "success_truncated_trace"
    assert full.trace["expansion_count"] == bounded.trace["expansion_count"] == 2
    assert full.trace["trace_complete"] is True
    assert bounded.trace["trace_complete"] is False
    assert full.trace["events"] != []
    assert bounded.trace["events"] == []


def test_characterization_rejects_successful_iw_with_zero_retained_events() -> None:
    # Given: a native successful IW trace whose zero event budget is explicitly incomplete.
    task, actions = _linear_task()
    result = local_iw.run_iterated_width(_iw_request(task, actions, max_trace_steps=0))

    # When: characterization projects that successful search into its planner record.
    record = _planner_record(
        "scripts.phase3.local_iw.run_iterated_width",
        result.plan,
        result.trace,
        result.status,
        {"goal_satisfied": True, "replay_ok": True},
        True,
    )

    # Then: zero retained events remain a bounded, source-ineligible result.
    assert record["characterization_outcome"] == "exact_search_bounded_trace"
    assert record["source_eligibility"] == "ineligible_bounded_trace"
    retained_trace = record["retained_trace"]
    assert isinstance(retained_trace, dict)
    assert retained_trace["retained_expansion_count"] == 0


@pytest.mark.parametrize("planner_module", [local_iw, local_serial])
def test_local_planners_sort_grounded_actions_once(
    monkeypatch: pytest.MonkeyPatch,
    planner_module: ModuleType,
) -> None:
    # Given: a two-expansion linear task with intentionally reverse-grounded actions.
    task, actions = _linear_task()
    request = LocalPlannerRequest(
        "iw",
        task,
        actions,
        {
            "gbfs_max_depth": 10,
            "gbfs_max_expansions": 10,
            "local_iw_max_width": 1,
            "local_iw_novelty_max_expansions": 10,
            "local_iw_width": 1,
            "local_max_applicable_actions": 10,
            "max_plan_length": 10,
            "max_trace_steps": 0,
        },
    )
    original_sorted = sorted
    grounded_sorts = 0

    def observed_sorted(values, *args, **kwargs):
        nonlocal grounded_sorts
        if values is actions:
            grounded_sorts += 1
        return original_sorted(values, *args, **kwargs)

    monkeypatch.setattr(planner_module, "sorted", observed_sorted, raising=False)

    # When: each local planner traverses the canonical linear state graph.
    if planner_module is local_iw:
        result = local_iw.run_iterated_width(request)
        plan = result.plan
    else:
        plan, _trace, status = local_serial.bounded_serial_plan(request, frozenset(task.init))
        assert status == "success_full_trace"

    # Then: canonical action selection is unchanged and grounded ordering happens once.
    assert plan == ["(advance-0)", "(advance-1)"]
    assert grounded_sorts == 1


def _linear_task() -> tuple[PDDLTask, tuple[GroundAction, ...]]:
    task = PDDLTask(
        domain_name="linear",
        problem_name="two-steps",
        objects_by_type={},
        init=frozenset({("state-0",)}),
        goal=frozenset({("state-2",)}),
        actions=(),
        unsupported_features=(),
    )
    actions = tuple(
        GroundAction(
            f"advance-{index}",
            (),
            frozenset({(f"state-{index}",)}),
            frozenset({(f"state-{index + 1}",)}),
            frozenset({(f"state-{index}",)}),
        )
        for index in reversed(range(2))
    )
    return task, actions


def _iw_request(task: PDDLTask, actions: tuple[GroundAction, ...], *, max_trace_steps: int) -> LocalPlannerRequest:
    return LocalPlannerRequest(
        "iw",
        task,
        actions,
        {
            "gbfs_max_depth": 10,
            "gbfs_max_expansions": 10,
            "local_iw_max_width": 1,
            "local_iw_novelty_max_expansions": 10,
            "local_iw_recovery": 0,
            "local_iw_width": 1,
            "local_max_applicable_actions": 10,
            "max_plan_length": 10,
            "max_trace_steps": max_trace_steps,
        },
    )


def _first_snapshot_bytes(trace: dict[str, JSONValue]) -> str:
    expansions = trace["expansions"]
    assert isinstance(expansions, list)
    return json.dumps(expansions[0], sort_keys=True, separators=(",", ":"))
