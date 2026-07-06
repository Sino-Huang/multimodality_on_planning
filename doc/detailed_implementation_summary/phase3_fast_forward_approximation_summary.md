# Phase 3 Fast Forward-Style Expert Approximation Summary

## Scope

Task 7 adds a deterministic Blocksworld-only Fast Forward-style expert generator at
`examples/planning_benchmark_slice/experts/fast_forward.py` and registers it through
`examples.planning_benchmark_slice.generate_experts` as the `fast_forward` algorithm.
The implementation reuses the canonical Task 2 symbolic world model and the Task 5
trajectory schema; it does not introduce a second planner state representation.

## Approximation decision

This is **not exact Fast Downward FF** and is **not full Hoffmann-Nebel relaxed-plan
extraction**. It is documented in code as the P0 approximation
`deterministic_p0_hmax_relaxed_reachability`.

For each concrete Blocksworld state, the generator:

1. Grounds the supported four Blocksworld operators: `pickup`, `putdown`, `stack`, and `unstack`.
2. Starts from the current concrete atom set.
3. Ignores delete effects during relaxed reachability propagation.
4. Propagates deterministic h-max-style atom costs over positive preconditions.
5. Recursively traces deterministic supporter actions for unsatisfied goals.
6. Uses the number of unique supporter actions as the approximate relaxed-plan length / heuristic value.

Unreachable goals use a large finite sentinel in metadata so generated JSON remains deterministic and schema-valid.
For the committed non-trivial fixture, the approximation yields the greedy plan `pickup(a)` then `stack(a,b)`.

## Recorded trace fields

Each Fast Forward step stores the required Task 5 namespace fields under `fast_forward`:

- `heuristic_value`
- `successor_heuristics`
- `selected_successor_id`
- `tie_break_rule`
- `relaxed_plan_metadata`

It also records `selected_action` and `failure_reason` in the namespace. The root `selected_action` mirrors the selected namespace action for compatibility with existing trajectory consumers. `failure_reason` is `no_legal_successor` only when a non-goal state has no legal successor; otherwise it is `null`.

## Deterministic selection rule

Every legal successor is evaluated. The selected successor/action is the first item after sorting by:

1. lowest approximate heuristic value;
2. canonical action string lexicographic order.

The emitted `tie_break_rule` is `min_heuristic_then_action_lexicographic`.

## Verification commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/planning_benchmark/test_expert_fast_forward.py -q
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.generate_experts --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms fast_forward --output outputs/planning_artifacts/expert_ff_smoke --json > .sisyphus/evidence/phase1-3-task-7-ff.json
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.validate_trajectories --input outputs/planning_artifacts/expert_ff_smoke --json
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/planning_benchmark/test_expert_fast_forward.py::test_fast_forward_tie_break_is_stable -q > .sisyphus/evidence/phase1-3-task-7-tiebreak.txt
```

Expected outcome: all commands exit `0`; the generator summary reports `fast_forward.trajectory_count=1`, selected actions `pickup(a)` then `stack(a,b)`, and trajectory validation reports `valid=true` with two `fast_forward` records.
