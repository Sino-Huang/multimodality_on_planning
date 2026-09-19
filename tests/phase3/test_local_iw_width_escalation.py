from __future__ import annotations

from collections.abc import Mapping

from scripts.phase3.local_iw import run_iterated_width
from scripts.phase3.local_planner_types import JSONValue, LocalPlannerRequest
from scripts.phase3.pddl import Atom, GroundAction, PDDLTask


# A task that pure width-1 novelty search provably cannot solve, but width 2 can.
#
# Every depth-1 branch puts one goal atom into the novelty table on its own:
#
#   {p} --take-x--> {x}          {x} is expanded, so (x) enters the table
#   {p} --take-y--> {y}          {y} is expanded, so (y) enters the table
#   {p} --take-z--> {z} --join--> {x,y}
#
# Successors are generated in canonical action order, so the branch names matter:
# take-z sorts after take-x and take-y, which is what puts {z} last in the FIFO
# frontier. By the time {z} is expanded and `join` generates the goal state
# {x,y}, both of its singleton features are already seen. At width 1 the
# successor is judged non-novel and is never enqueued, so the goal is generated
# and then discarded without being recognised. At width 2 the pair feature (x,y)
# is still novel, the successor is enqueued, and the goal is found.

Fixture = tuple[PDDLTask, tuple[GroundAction, ...]]


def test_width_one_alone_cannot_solve_the_width_two_fixture() -> None:
    # Given: the fixture above, with escalation pinned off at max width 1.
    request = _request(_width_two_fixture(), max_width=1)

    # When: IW runs with no recovery to fall back on.
    result = run_iterated_width(request)

    # Then: novelty search exhausts without ever recognising the goal it generated.
    assert (result.plan, result.status) == ([], "failed_no_plan_extracted")
    assert result.trace["width"] == 1


def test_escalation_to_width_two_solves_what_width_one_cannot() -> None:
    # Given: the same fixture, now permitted to escalate 1 -> 2.
    request = _request(_width_two_fixture(), max_width=2)

    # When: IW runs true iterative width.
    result = run_iterated_width(request)

    # Then: the goal is reached by pure novelty search, with no recovery fallback.
    assert result.status == "success_full_trace"
    assert result.plan == ["(take-z)", "(join)"]
    assert "plan_recovery" not in result.trace


def test_escalation_records_the_width_transition_it_took() -> None:
    # Given: a fixture that forces one escalation step.
    request = _request(_width_two_fixture(), max_width=2)

    # When: IW solves it at the second width.
    result = run_iterated_width(request)

    # Then: the trace names the solving width and the sequence of widths attempted,
    # so the certificate records a transition rather than a constant.
    assert result.trace["width"] == 2
    assert result.trace["width_sequence"] == [1, 2]


def test_solving_width_is_stamped_on_the_emitted_events() -> None:
    # Given: a fixture solved only after escalating.
    request = _request(_width_two_fixture(), max_width=2)

    # When: IW escalates and emits its trace events.
    result = run_iterated_width(request)

    # Then: events from the solving pass carry that pass's width, not the start width.
    decisions = {event["width_decision"] for event in _events(result.trace)}
    assert "width_2_novel" in decisions
    assert not any(str(decision).startswith("width_1_") for decision in decisions)


def test_escalation_stops_at_max_width_and_reports_every_width_tried() -> None:
    # Given: a task no width up to 2 can solve, because the goal atom is unreachable.
    request = _request(_unreachable_fixture(), max_width=2)

    # When: IW exhausts both widths.
    result = run_iterated_width(request)

    # Then: it fails without exceeding max width, and reports both attempts.
    assert (result.plan, result.status) == ([], "failed_no_plan_extracted")
    assert result.trace["width_sequence"] == [1, 2]


def test_no_escalation_when_the_start_width_already_solves() -> None:
    # Given: a task width 1 solves on its own, with escalation available but unneeded.
    request = _request(_width_one_fixture(), max_width=2)

    # When: IW runs.
    result = run_iterated_width(request)

    # Then: it solves at width 1 and never escalates.
    assert result.status == "success_full_trace"
    assert result.trace["width"] == 1
    assert result.trace["width_sequence"] == [1]


def test_frozen_policy_at_max_width_one_keeps_the_existing_trace_shape() -> None:
    # Given: the frozen approved policy, which pins local_iw_max_width to 1.
    request = _request(_width_one_fixture(), max_width=1)

    # When: IW runs under it.
    result = run_iterated_width(request)

    # Then: the trace carries no escalation field at all, so the 558 existing
    # streams and every recorded trace field keep their meaning.
    assert result.status == "success_full_trace"
    assert "width_sequence" not in result.trace
    assert set(result.trace) == {
        "algorithm",
        "events",
        "expansion_count",
        "trace_complete",
        "trace_contract_version",
        "width",
    }


def test_escalation_reports_expansions_separately_for_each_width_tried() -> None:
    # Given: a fixture that exhausts width 1 before solving at width 2.
    request = _request(_width_two_fixture(), max_width=2)

    # When: IW escalates.
    result = run_iterated_width(request)

    # Then: the cost of every attempt is visible, not just the solving one. The
    # width-1 pass is real work and Phase A has to count it.
    by_width = result.trace["expansion_count_by_width"]
    assert isinstance(by_width, list)
    assert len(by_width) == 2
    assert all(count > 0 for count in by_width)
    assert by_width[-1] == result.trace["expansion_count"]


def test_escalation_is_off_unless_explicitly_requested() -> None:
    # Given: a caller that sets a start width but leaves local_iw_max_width unset,
    # so it falls back to DEFAULT_LOCAL_IW_MAX_WIDTH=3. Several existing call sites
    # do exactly this (tests/phase3/test_phase3_blocksworld_medium_traces.py among
    # them), and inferring escalation from max_width > start_width would silently
    # convert them from fixed-width to escalating runs.
    task, actions = _width_two_fixture()
    request = LocalPlannerRequest(
        "iw",
        task,
        actions,
        {
            "gbfs_max_expansions": 50,
            "local_iw_novelty_max_expansions": 50,
            "local_iw_recovery": 0,
            "local_iw_width": 1,
            "local_max_applicable_actions": 10,
            "max_plan_length": 10,
            "max_trace_steps": 50,
        },
    )

    # When: IW runs without opting in to escalation.
    result = run_iterated_width(request)

    # Then: it stays at width 1 and fails, exactly as it did before escalation existed.
    assert (result.plan, result.status) == ([], "failed_no_plan_extracted")
    assert result.trace["width"] == 1
    assert "width_sequence" not in result.trace


def _width_two_fixture() -> Fixture:
    return _fixture(
        initial={"p"},
        goal={"x", "y"},
        actions=(
            _action("take-x", {"p"}, {"x"}, {"p"}),
            _action("take-y", {"p"}, {"y"}, {"p"}),
            _action("take-z", {"p"}, {"z"}, {"p"}),
            _action("join", {"z"}, {"x", "y"}, {"z"}),
        ),
    )


def _width_one_fixture() -> Fixture:
    return _fixture(initial={"p"}, goal={"x"}, actions=(_action("take-x", {"p"}, {"x"}, {"p"}),))


def _unreachable_fixture() -> Fixture:
    return _fixture(initial={"p"}, goal={"unreachable"}, actions=(_action("take-x", {"p"}, {"x"}, {"p"}),))


def _fixture(*, initial: set[str], goal: set[str], actions: tuple[GroundAction, ...]) -> Fixture:
    task = PDDLTask(
        "fixture",
        "width-escalation",
        {},
        frozenset(_atoms(initial)),
        frozenset(_atoms(goal)),
        (),
        (),
    )
    return task, actions


def _action(name: str, preconditions: set[str], add_effects: set[str], del_effects: set[str]) -> GroundAction:
    return GroundAction(
        name,
        (),
        frozenset(_atoms(preconditions)),
        frozenset(_atoms(add_effects)),
        frozenset(_atoms(del_effects)),
    )


def _atoms(names: set[str]) -> tuple[Atom, ...]:
    return tuple((name,) for name in sorted(names))


def _request(fixture: Fixture, *, max_width: int) -> LocalPlannerRequest:
    task, actions = fixture
    return LocalPlannerRequest(
        "iw",
        task,
        actions,
        {
            "gbfs_max_expansions": 50,
            "local_iw_escalate": 1,
            "local_iw_max_width": max_width,
            "local_iw_novelty_max_expansions": 50,
            "local_iw_recovery": 0,
            "local_iw_width": 1,
            "local_max_applicable_actions": 10,
            "max_plan_length": 10,
            "max_trace_steps": 50,
        },
    )


def _events(trace: Mapping[str, JSONValue]) -> list[Mapping[str, JSONValue]]:
    events = trace["events"]
    assert isinstance(events, list)
    return [event for event in events if isinstance(event, Mapping)]
