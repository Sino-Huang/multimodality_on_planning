## Phase 3 Local Planner Blocksworld 0011 Fix

- `scripts/phase3/local_iw.py` now reads `local_iw_width` from planner limits, defaulting through callers to IW(1), and writes the configured width into IW traces.
- IW novelty is generated for atom tuples from size 1 through the configured width. Width 1 and 2 still fail `blocksworld-train-medium-0011`; width 3 reaches a replay-valid 10-step plan.
- IW widths below 1 are treated as a resource-limit skip instead of silently running a degenerate novelty search.
- IW widths above `local_iw_max_width` are also treated as `skipped_resource_limit`. The default cap is 3, which preserves the `blocksworld-train-medium-0011` recovery path while preventing unbounded novelty tuple generation.
- IW trace event count remains capped by `max_trace_steps`; large novelty tables are serialized with a bounded prefix so pipeline examples stay under `max_jsonl_target_chars` while preserving the trace fields.
- Local FF remains labeled `local_delete_relaxed_hmax_supporter_closure` and `is_exact_fast_downward_ff = False`. It now uses bounded best-first search ordered by plan depth with relaxed-heuristic/action tie-breaking, then rebuilds the existing per-step trace payload along the selected plan.
- `scripts/phase3/pipeline.py` includes `local_iw_width: 3`, `local_iw_max_width: 3`, and `local_graphplan_max_expansions: 250000` in `RESOURCE_LIMITS`; `scripts/phase3/generate_curriculum_trace_dataset.py` exposes those defaults through `--local-iw-width`, `--local-iw-max-width`, and `--local-graphplan-max-expansions`.
- `scripts/phase3/local_planners.py` uses a local `assert_never` helper instead of importing `typing.assert_never`, so the module imports under the project Python 3.10 environment.
- Trace extraction rejects unsafe manifest-derived path components for `domain`, `split`, `instance_id`, and `planner` before writing `<output-root>/traces/...` files.

Verification command used:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_blocksworld_medium_traces.py tests/phase3/test_phase3_pipeline_regressions.py::test_fast_forward_trace_records_relaxed_planning_graph_and_selected_relaxed_plan tests/phase3/test_phase3_pipeline_regressions.py::test_iw_expands_empty_initial_state_with_zero_precondition_action tests/phase3/test_phase3_pipeline_regressions.py::test_iw_enforces_max_plan_length tests/phase3/test_phase3_pipeline_regressions.py::test_iw_enforces_applicable_action_cap tests/phase3/test_phase3_pipeline_regressions.py::test_iw_rejects_width_below_one
```

Expected result: all selected tests pass.

Post-review blocker verification used after adding the IW cap, Python 3.10 import fix, and trace path hardening:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_local_trace_safety.py tests/phase3/test_phase3_pipeline_regressions.py::test_iw_rejects_width_below_one tests/phase3/test_phase3_blocksworld_medium_traces.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3 tests/phase3
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/planning_benchmark tests/data_collect
source ~/cd_vlaplan && python -c "from scripts.phase3.local_planners import run_local_planner; print(run_local_planner.__name__)"
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id blocksworld-train-medium-0011 --planner gbfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_bwm0011_all_local_verify --quiet
```

Expected result: focused safety tests pass, compileall exits 0, `tests/phase3` passes, `tests/planning_benchmark tests/data_collect` passes, Python 3.10 import smoke prints `run_local_planner`, and exact CLI reports `attempt_status_summary: {"success_full_trace": 4}` plus `extracted_trace_count: 4`. As of the 2026-07-07 GBFS replacement, the active planner label is `gbfs`; old `bfs` CLI selection is rejected rather than aliased.
