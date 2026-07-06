# Phase 3 FF Relaxed Trace Upgrade

This note records the Phase 3 Fast Forward trace-fidelity upgrade completed for the local planner fallback.

## What changed

`scripts/phase3/local_planners.py` now emits richer FF-style trace supervision instead of scalar-only heuristic records. The local `ff` trace includes:

- Top-level `goal_atoms` so the trace is interpretable without joining external task context.
- Top-level `planner_source: local_delete_relaxed_hmax_supporter_closure` to distinguish the local fallback from an exact Fast Downward FF planner.
- Per-step `current_heuristic` with `heuristic_source`, `heuristic_value`, `relaxed_proposition_layers`, `relaxed_action_layers`, and `relaxed_plan`.
- Per-step `relaxation_metadata` with `ignored_delete_effects: true`, `approximation: local_delete_relaxed_hmax_supporter_closure`, and `is_exact_fast_downward_ff: false`.
- `selected_successor` and `successor_heuristics` entries carrying successor states, heuristic values, goal status, relaxed plans, and relaxed-plan actions.

The regression test `test_fast_forward_trace_records_relaxed_planning_graph_and_selected_relaxed_plan` in `tests/phase3/test_phase3_pipeline_regressions.py` locks this trace shape.

## Interpretation

Oracle judged the upgraded trace **adequate with caveats** for SFT supervision of FF-like delete-relaxation behavior. It is suitable for supervising: compute delete-relaxed reachability, extract a relaxed-plan proxy, rank successors by relaxed-plan length, and choose the best action.

The trace should still be described as **FF-style** or **local delete-relaxation approximation**, not exact Fast Downward FF. The implementation does not include canonical FF enforced hill-climbing or helpful-action pruning, and the trace explicitly records `is_exact_fast_downward_ff: false`.

Fast Downward fallback remains external-first only: Phase 3 will use `PHASE3_FF_PLANNER` or `PHASE3_IW_PLANNER` if configured. The repository-local Fast Downward alias probe does not expose usable `ff` or `iw` aliases in the checked environment, so `ff` and `iw` default to local fallbacks unless explicit executable paths are supplied.

## Generated artifact

The upgraded trace was regenerated at:

```text
outputs/phase3_traces/blocksworld-dev-easy-0004/traces/ff.planner_trace.json
```

The generator emitted all four planner traces with `success_full_trace` fidelity for `blocksworld-dev-easy-0004`.

## Verification commands

Run these from the repository root:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_pipeline_regressions.py::test_fast_forward_trace_records_relaxed_planning_graph_and_selected_relaxed_plan
```

Expected signal: `1 passed`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3
```

Expected signal: `40 passed`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3 tests/planning_benchmark tests/data_collect
```

Expected signal: `169 passed`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3 tests/phase3
```

Expected signal: exit code `0` with no output.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python tests/phase3/generate_single_instance_traces.py --instance-id blocksworld-dev-easy-0004
```

Expected signal: JSON report with `emitted_examples: 4`, `fidelity_summary: {"success_full_trace": 4}`, and extracted planners `bfs`, `ff`, `graphplan`, and `iw`.
