from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from examples.planning_benchmark_slice.blocksworld import BlocksworldAction, BlocksworldProblem, parse_blocksworld
from examples.planning_benchmark_slice.benchmark_loop import parse_action_text, shortest_action_plan
from examples.planning_benchmark_slice.experts.iterated_width import novelty_items as reference_novelty_items
from examples.planning_benchmark_slice.experts.iterated_width import iterated_width_plan
from examples.planning_benchmark_slice.validate_instance import load_fixture
from scripts.phase3.cgas_bfs import run_fifo_bfs
from scripts.phase3.local_iw import run_iterated_width
from scripts.phase3.local_planner_types import JSONValue, LocalPlannerRequest
from scripts.phase3.pddl import GroundAction, PDDLTask, ground_actions, parse_task


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
NONTRIVIAL_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json"
IW_FAILURE_FIXTURE_ROOT = REPOSITORY_ROOT / "data/curriculum_pddl/blocksworld/dev/easy/blocksworld-dev-easy-0001"


def test_bfs_initial_goal_reports_zero_expansions() -> None:
    # Given: the initial state already satisfies the goal.
    task = _task({"start"}, {"start"})

    # When: canonical BFS starts under a zero cap.
    result = run_fifo_bfs(task, (), _bfs_limits(max_expansions=0))

    # Then: initial-goal recognition does not consume an expansion.
    assert (result.plan, result.status, result.trace["expansion_count"]) == ((), "success_full_trace", 0)


def test_real_blocksworld_pddl_cgas_plans_match_independent_benchmark(tmp_path: Path) -> None:
    # Given: one checked-in PDDL fixture parsed independently by both planner models.
    fixture = load_fixture(NONTRIVIAL_FIXTURE)
    independent = parse_blocksworld(fixture.domain_pddl, fixture.problem_pddl)
    domain_path, problem_path = _write_pddl_fixture(tmp_path, fixture.domain_pddl, fixture.problem_pddl)
    cgas_task = parse_task(domain_path, problem_path)
    grounded, grounding_status = ground_actions(cgas_task, max_grounded_actions=1000, max_grounded_atoms=1000)
    assert grounding_status is None
    independent_bfs = shortest_action_plan(independent, independent.initial_state(), max_depth=10)
    independent_iw = iterated_width_plan(independent, independent.initial_state(), width=1, max_expansions=100)
    assert independent_bfs is not None
    assert independent_iw is not None

    # When: CGAS parses, grounds, and searches the same real PDDL fixture.
    bfs = run_fifo_bfs(cgas_task, tuple(grounded), _bfs_limits(max_expansions=100, max_plan_length=10))
    iw = run_iterated_width(_iw_request(cgas_task, tuple(grounded)))

    # Then: plans agree on validity and shortest width-one outcome without CGAS replay expectations.
    assert bfs.status == "success_full_trace"
    assert iw.status == "success_full_trace"
    assert len(bfs.plan) == len(independent_bfs) == independent.shortest_plan_length(max_depth=10) == 2
    assert len(iw.plan) == len(independent_iw) == 2
    assert _independent_plan_valid(independent, bfs.plan)
    assert _independent_plan_valid(independent, iw.plan)
    assert tuple(bfs.plan) == _benchmark_action_strings(independent_bfs)
    assert tuple(iw.plan) == _benchmark_action_strings(independent_iw)


def test_real_blocksworld_pddl_iw_one_failure_matches_independent_novelty_search() -> None:
    # Given: the existing small PDDL fixture whose shortest independent plan is wider than IW(1) novelty.
    independent = parse_blocksworld(
        (IW_FAILURE_FIXTURE_ROOT / "domain.pddl").read_text(encoding="utf-8"),
        (IW_FAILURE_FIXTURE_ROOT / "problem.pddl").read_text(encoding="utf-8"),
    )
    cgas_task = parse_task(IW_FAILURE_FIXTURE_ROOT / "domain.pddl", IW_FAILURE_FIXTURE_ROOT / "problem.pddl")
    grounded, grounding_status = ground_actions(cgas_task, max_grounded_actions=100_000, max_grounded_atoms=100_000)
    assert grounding_status is None
    independent_plan = iterated_width_plan(independent, independent.initial_state(), width=1, max_expansions=10_000)
    assert independent_plan is None
    assert independent.shortest_plan_length(max_depth=20) == 4

    # When: native CGAS IW(1) searches the grounded real fixture with recovery disabled.
    result = run_iterated_width(
        _iw_request(cgas_task, tuple(grounded), max_expansions=10_000)
    )

    # Then: both independent and native width-one searches fail without claiming the task is unsolvable.
    assert (result.plan, result.status) == ([], "failed_no_plan_extracted")
    assert "plan_recovery" not in result.trace


def test_bfs_uses_sorted_actions_and_fifo_frontier_order() -> None:
    # Given: reverse-grounded actions whose lexically first branch reaches the goal first.
    task = _task({"start"}, {"goal"})
    actions = (
        _action("to-b", {"start"}, {"b"}),
        _action("finish-a", {"a"}, {"goal"}),
        _action("to-a", {"start"}, {"a"}),
        _action("finish-b", {"b"}, {"goal"}),
    )

    # When: BFS runs with complete trace retention.
    result = run_fifo_bfs(task, actions, _bfs_limits())

    # Then: sorted generation and FIFO dequeue select the a branch.
    assert result.plan == ("(to-a)", "(finish-a)")
    assert result.trace["expansion_count"] == 2
    expansions = _records(result.trace, "expansions")
    assert expansions[0]["actions_considered"] == ["(to-a)", "(to-b)"]
    assert "frontier_after" not in expansions[0]


def test_bfs_allows_goal_on_final_permitted_expansion() -> None:
    # Given: a one-step goal that needs the first expansion.
    task = _task({"start"}, {"goal"})

    # When: the only expansion is permitted by the cap.
    result = run_fifo_bfs(task, (_action("finish", {"start"}, {"goal"}),), _bfs_limits(max_expansions=1))

    # Then: the goal is accepted at the cap, not rejected before it.
    assert (result.plan, result.status, result.trace["expansion_count"]) == (("(finish)",), "success_full_trace", 1)


def test_bfs_reports_one_beyond_expansion_cap() -> None:
    # Given: a two-step linear task whose second dequeued node exceeds the cap.
    task, actions = _linear_task()

    # When: BFS permits only the root expansion.
    result = run_fifo_bfs(task, actions, _bfs_limits(max_expansions=1))

    # Then: the attempted over-cap dequeue is observable as cap plus one.
    assert (result.plan, result.status, result.trace["expansion_count"]) == ((), "skipped_resource_limit", 2)


def test_bfs_zero_cap_rejects_a_noninitial_goal() -> None:
    # Given: a goal available only through one successor.
    task = _task({"start"}, {"goal"})

    # When: no expansion is permitted.
    result = run_fifo_bfs(task, (_action("finish", {"start"}, {"goal"}),), _bfs_limits(max_expansions=0))

    # Then: BFS stops at the attempted root dequeue without inspecting successors.
    assert (result.plan, result.status, result.trace["expansion_count"]) == ((), "skipped_resource_limit", 1)


def test_bfs_visited_duplicate_is_not_enqueued_or_accepted_as_goal() -> None:
    # Given: two branches that reach the same non-goal state.
    task = _task({"start"}, {"missing"})
    actions = (
        _action("to-a", {"start"}, {"a"}),
        _action("to-b", {"start"}, {"b"}),
        _action("a-to-common", {"a"}, {"common"}),
        _action("b-to-common", {"b"}, {"common"}),
    )

    # When: BFS drains the graph.
    result = run_fifo_bfs(task, actions, _bfs_limits())

    # Then: the duplicate successor is trace-visible but cannot enqueue or terminate search.
    assert result.status == "failed_no_plan_extracted"
    expansions = _records(result.trace, "expansions")
    duplicate = _records(expansions[2], "successors")[0]
    assert duplicate["was_visited"] is True
    assert duplicate["enqueued"] is False
    assert duplicate["is_goal"] is False


def test_bfs_rejects_plan_one_step_beyond_plan_length_limit() -> None:
    # Given: a one-action goal and a zero-length plan limit.
    task = _task({"start"}, {"goal"})

    # When: BFS generates the prohibited successor plan.
    result = run_fifo_bfs(task, (_action("finish", {"start"}, {"goal"}),), _bfs_limits(max_plan_length=0))

    # Then: the boundary returns the canonical resource-limit result.
    assert (result.plan, result.status, result.trace["expansion_count"]) == ((), "skipped_resource_limit", 1)


def test_iw_singleton_features_match_independent_width_one_fixture() -> None:
    # Given: a one-atom root and a novel one-atom goal successor.
    task = _task({"start"}, {"goal"})
    action = _action("finish", {"start"}, {"goal"})

    # When: native IW runs at width one without recovery.
    result = run_iterated_width(_iw_request(task, (action,)))

    # Then: its exact singleton delta matches the independently enumerated width-one feature set.
    events = _records(result.trace, "events")
    assert _singleton_features({"start"}) == reference_novelty_items(["(start)"], width=1)
    assert events[0]["novel_item"] == "(start)"
    assert events[0]["seen_feature_delta"] == ["(start)"]
    assert "novelty_table_before" not in events[0]
    assert "novelty_table_after" not in events[0]
    assert result.plan == ["(finish)"]


def test_iw_updates_singleton_table_then_prunes_non_novel_node() -> None:
    # Given: queued qr and r states, where expanding qr makes r non-novel.
    task = _task({"p"}, {"missing"})
    actions = (
        _action("to-qr", {"p"}, {"q", "r"}),
        _action("to-r", {"p"}, {"r"}),
    )

    # When: native IW exhausts the novelty graph.
    result = run_iterated_width(_iw_request(task, actions))

    # Then: each expansion records only its exact growth and the prune records none.
    events = _records(result.trace, "events")
    assert [event["decision"] for event in events] == ["expand", "expand", "prune"]
    assert [event["seen_feature_delta"] for event in events] == [["(p)"], ["(q)", "(r)"], []]
    assert all("novelty_table_before" not in event for event in events)
    assert all("novelty_table_after" not in event for event in events)


def test_iw_prunes_duplicate_visited_successor() -> None:
    # Given: two canonical actions that generate the same novel state from the root.
    task = _task({"p"}, {"missing"})
    actions = (
        _action("first", {"p"}, {"q"}),
        _action("second", {"p"}, {"q"}),
    )

    # When: width-one IW considers both successors.
    result = run_iterated_width(_iw_request(task, actions))

    # Then: the second is a novel feature duplicate but a visited-state revisit, so it is not queued.
    events = _records(result.trace, "events")
    duplicate = _records(events[0], "successors")[1]
    assert duplicate == {"action": "(second)", "event_kind": "revisit", "is_goal": False, "is_novel": True, "enqueued": False}


def test_iw_rejects_non_novel_goal_successor() -> None:
    # Given: r enters the table before q can generate the q-and-r goal state.
    task = _task({"p"}, {"q", "r"})
    actions = (
        _action("seed-r", {"p"}, {"r"}),
        _action("to-q", {"p"}, {"q"}),
        _action("finish", {"q"}, {"q", "r"}),
    )

    # When: IW reaches a goal whose singleton features were already observed.
    result = run_iterated_width(_iw_request(task, actions))

    # Then: novelty is required before goal acceptance, so native search exhausts.
    events = _records(result.trace, "events")
    goal_successor = _records(events[2], "successors")[0]
    assert goal_successor["is_goal"] is True
    assert goal_successor["is_novel"] is False
    assert goal_successor["enqueued"] is False
    assert (result.plan, result.status) == ([], "failed_no_plan_extracted")


def test_iw_exhaustion_has_empty_frontier_and_no_recovery() -> None:
    # Given: a novel root with no applicable action and recovery disabled.
    task = _task({"p"}, {"missing"})

    # When: native IW drains its singleton frontier.
    result = run_iterated_width(_iw_request(task, ()))

    # Then: it reports strict native exhaustion with no recovery payload.
    assert (result.plan, result.status, result.trace["expansion_count"]) == ([], "failed_no_plan_extracted", 1)
    assert "plan_recovery" not in result.trace
    events = _records(result.trace, "events")
    assert events[0]["frontier_size_after"] == 0


def test_iw_native_cap_count_differs_from_independent_strict_cap_reference() -> None:
    # Given: a two-node novelty path and a cap of one.
    task, actions = _linear_task()

    # When: native IW performs its post-increment cap check.
    result = run_iterated_width(_iw_request(task, actions, max_expansions=1))

    # Then: it reports cap plus one; the independent example IW uses `expansions < max_expansions`.
    assert (result.status, result.trace["expansion_count"]) == ("skipped_resource_limit", 2)


def _task(initial: set[str], goal: set[str]) -> PDDLTask:
    return PDDLTask("fixture", "semantic-parity", {}, frozenset((atom,) for atom in initial), frozenset((atom,) for atom in goal), (), ())


def _action(name: str, preconditions: set[str], add_effects: set[str]) -> GroundAction:
    return GroundAction(
        name,
        (),
        frozenset((atom,) for atom in preconditions),
        frozenset((atom,) for atom in add_effects),
        frozenset((atom,) for atom in preconditions),
    )


def _linear_task() -> tuple[PDDLTask, tuple[GroundAction, ...]]:
    task = _task({"state-0"}, {"state-2"})
    return task, (_action("advance-1", {"state-1"}, {"state-2"}), _action("advance-0", {"state-0"}, {"state-1"}))


def _bfs_limits(*, max_expansions: int = 10, max_plan_length: int = 10) -> dict[str, int]:
    return {"max_expansions": max_expansions, "max_plan_length": max_plan_length, "max_trace_steps": 10}


def _iw_request(task: PDDLTask, actions: tuple[GroundAction, ...], *, max_expansions: int = 10) -> LocalPlannerRequest:
    return LocalPlannerRequest("iw", task, actions, {"gbfs_max_expansions": 10, "local_iw_max_width": 1, "local_iw_novelty_max_expansions": max_expansions, "local_iw_recovery": 0, "local_iw_width": 1, "local_max_applicable_actions": 10, "max_plan_length": 10, "max_trace_steps": 10})


def _singleton_features(atoms: set[str]) -> tuple[tuple[str, ...], ...]:
    return tuple((f"({atom})",) for atom in sorted(atoms))


def _records(record: Mapping[str, JSONValue], key: str) -> list[Mapping[str, JSONValue]]:
    value = record[key]
    assert isinstance(value, list)
    assert all(isinstance(item, Mapping) for item in value)
    return [item for item in value if isinstance(item, Mapping)]


def _write_pddl_fixture(root: Path, domain: str, problem: str) -> tuple[Path, Path]:
    domain_path = root / "domain.pddl"
    problem_path = root / "problem.pddl"
    domain_path.write_text(domain, encoding="utf-8")
    problem_path.write_text(problem, encoding="utf-8")
    return domain_path, problem_path


def _benchmark_action_strings(actions: tuple[BlocksworldAction, ...]) -> tuple[str, ...]:
    return tuple(f"({action.name} {' '.join(action.args)})" for action in actions)


def _independent_plan_valid(problem: BlocksworldProblem, actions: Sequence[str]) -> bool:
    state = problem.initial_state()
    for action_text in actions:
        words = action_text.strip("()").split()
        action = parse_action_text(f"{words[0]}({','.join(words[1:])})")
        if action not in problem.legal_actions(state):
            return False
        state = problem.transition(state, action)
    return problem.is_goal(state)
