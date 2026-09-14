"""Unseen-task isolation distinguishes new structure from renamed instances."""

import copy

from examples.planning_benchmark_slice.task_isomorphism import same_instance


def context(a="a", b="b"):
    return dict(
        objects_by_type={"object": [a, b]},
        static_initial_facts=[f"edge({a},{b})"],
        initial_dynamic_atoms=[f"at({a})"],
        initial_dynamic_fluents=[],
        canonical_goal=["atom", "at", [b]],
    )


def test_object_names_do_not_create_unseen_instances():
    assert same_instance(context(), context("renamed1", "renamed2"))
    different = context()
    different["canonical_goal"] = ["atom", "at", ["a"]]
    assert not same_instance(context(), different)
    different = context()
    different["initial_dynamic_atoms"] = ["at(b)"]
    assert not same_instance(context(), different)


def test_argument_order_fluents_and_quantified_scope_are_preserved():
    left = context()
    right = context()
    right["static_initial_facts"] = ["edge(b,a)"]
    assert not same_instance(left, right)
    left["initial_dynamic_fluents"] = ["cost(a)=1"]
    right = copy.deepcopy(left)
    right["initial_dynamic_fluents"] = ["cost(a)=2"]
    assert not same_instance(left, right)
    left["canonical_goal"] = [
        "forall",
        [["?x", "object"]],
        ["exists", [["?y", "object"]], ["atom", "edge", ["?x", "?y"]]],
    ]
    right = copy.deepcopy(left)
    right["canonical_goal"] = [
        "forall",
        [["?u", "object"]],
        ["exists", [["?v", "object"]], ["atom", "edge", ["?u", "?v"]]],
    ]
    assert same_instance(left, right)
    right["canonical_goal"] = [
        "exists",
        [["?u", "object"]],
        ["forall", [["?v", "object"]], ["atom", "edge", ["?u", "?v"]]],
    ]
    assert not same_instance(left, right)
