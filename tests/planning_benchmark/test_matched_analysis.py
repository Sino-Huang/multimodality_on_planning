from types import SimpleNamespace

from examples.planning_benchmark_slice.matched_analysis import (
    failure_category,
    observed_prefix,
    paired_interval,
    solution_length,
)


def test_solution_cost_uses_provenance_path_not_total_search_transitions():
    edges = [SimpleNamespace(source_state_id=a, target_state_id=b) for a, b in (("s0", "a"), ("s0", "b"), ("b", "g"))]
    memory = SimpleNamespace(provenance=edges, visited={"s0", "a", "b", "g"}, state=lambda s: s)
    session = SimpleNamespace(
        result=lambda: {"goal_reached": True},
        algorithm="bfs",
        session=SimpleNamespace(context=SimpleNamespace(memory=memory)),
        authority=SimpleNamespace(initial_state=SimpleNamespace(state_id="s0"), is_goal=lambda s: s == "g"),
    )
    assert solution_length(session) == 2
    session.result = lambda: {"goal_reached": False}
    assert solution_length(session) is None


def test_diagnostics_preserve_schema_and_candidate_distinction():
    assert failure_category("Expecting value: line 1 column 1 (char 0)") == "json_syntax"
    assert failure_category("invalid fields in operation: missing=['exact_successor']") == "schema_or_shape"
    assert failure_category("successor candidate was already submitted") == "candidate_membership_or_duplicate"
    assert failure_category("BFS operation rejected; detailed validity rule not retained") == "search_rule_or_unresolved"


def test_common_cap_does_not_import_later_success_or_expand_short_trace():
    steps = [
        {"accepted": True, "terminal": False, "success": False, "expansions": 1},
        {"accepted": True, "terminal": True, "success": True, "expansions": 2},
    ]
    before = observed_prefix(steps, 1)
    assert before["censored_at_common_cap"] and not before["success_observed"]
    assert before["expansions"] == 1
    after = observed_prefix(steps, 20)
    assert after["observed_decisions"] == 2 and after["success_observed"]
    assert not after["censored_at_common_cap"]


def test_rejected_operation_remains_a_terminal_failure_in_prefix():
    result = observed_prefix([{"accepted": False, "terminal": True, "success": False, "expansions": 0}], 10)
    assert result["observed_decisions"] == result["invalid_operations"] == 1
    assert result["terminal_observed"] and not result["success_observed"]


def test_paired_bootstrap_uses_three_whole_problem_contrasts():
    interval = paired_interval([0, 0, 1])
    assert interval["whole_problems"] == 3
    assert interval["difference"] == 1 / 3
    assert interval["lower"] == 0 and interval["upper"] == 1
    assert paired_interval([0, 0, 0])["upper"] == 0
