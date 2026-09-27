"""Data-cost panel selection: seed order, stratum isolation and renaming-equivalence exclusion."""

from examples.planning_benchmark_slice.data_cost_panel import select_strata
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority

DOMAIN = """(define (domain mini)
  (:requirements :strips)
  (:predicates (on ?x ?y) (clear ?x) (table ?x))
  (:action lift :parameters (?x ?y)
    :precondition (and (on ?x ?y) (clear ?x))
    :effect (and (table ?x) (clear ?y) (not (on ?x ?y)))))"""


def context(a, b, c):
    problem = f"""(define (problem p) (:domain mini)
      (:objects {a} {b} {c})
      (:init (on {a} {b}) (on {b} {c}) (table {c}) (clear {a}))
      (:goal (and (table {a}) (table {b}))))"""
    return PDDLStateAuthority.from_pddl(DOMAIN, problem).task_context()


def other(a, b, c):
    problem = f"""(define (problem p) (:domain mini)
      (:objects {a} {b} {c})
      (:init (on {a} {b}) (table {b}) (table {c}) (clear {a}) (clear {c}))
      (:goal (and (table {a}))))"""
    return PDDLStateAuthority.from_pddl(DOMAIN, problem).task_context()


def candidate(seed, eligible=True):
    return dict(seed=seed, reference_eligible=eligible, reason="eligible" if eligible else "exact_reference_failed:bfs")


def test_renamed_training_task_is_excluded_and_selection_never_crosses_strata():
    contexts = {1: context("x1", "x2", "x3"), 2: other("a", "b", "c"), 3: other("q", "r", "s"), 4: other("m", "n", "o")}
    groups = [
        # Seed 0 fails references; seed 1 is a renamed training task; seed 2 is first admissible.
        dict(domain="mini", stratum="compact", candidates=[candidate(0, False), candidate(1), candidate(2)]),
        # Its only eligible seed renames the task already selected above.
        dict(domain="mini", stratum="expanded", candidates=[candidate(3)]),
        dict(domain="other", stratum="compact", candidates=[candidate(4, False)]),
    ]
    strata, missing = select_strata(groups, [context("t1", "t2", "t3")], lambda c: contexts[c["seed"]])

    assert strata[0]["selected"]["seed"] == 2
    assert [d["disposition"] for d in strata[0]["decisions"]] == [
        "exact_reference_failed:bfs",
        "historical_object_renaming_overlap",
        "selected",
    ]
    assert strata[1]["selected"] is None
    assert strata[1]["decisions"][0]["disposition"] == "within_panel_object_renaming_overlap"
    # Exhausted strata stay missing; no seed is borrowed from a neighbouring stratum.
    assert strata[2]["selected"] is None
    assert [(m["domain"], m["stratum"]) for m in missing] == [("mini", "expanded"), ("other", "compact")]
