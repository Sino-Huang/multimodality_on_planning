# Phase 3 GBFS Replacement

Date: 2026-07-07

## Summary

Active Phase 3 local search now uses `gbfs` instead of `bfs`. The old planner label is rejected through `generate_supervised_data()` and the CLI `--planner` choices rather than silently aliased.

## Implementation Notes

- `scripts/phase3/pipeline.py` sets `DEFAULT_PLANNERS = ("gbfs", "ff", "iw", "graphplan")` and dispatches active GBFS attempts through `scripts/phase3/gbfs.py`.
- `scripts/phase3/gbfs.py` owns `run_gbfs()`, `gbfs_trace()`, and `gbfs_estimate_exceeds_resource_gate()`.
- `run_gbfs()` uses greedy best-first search with an unsatisfied-goal-count heuristic, priority ordered by `(unsatisfied goals, plan length, generation order)`.
- GBFS traces use `algorithm: "greedy_best_first"`, `heuristic_source: "unsatisfied_goal_count"`, and `frontier_events` with selected-state and successor heuristic details.
- GBFS resource controls are `gbfs_max_applicable_actions`, `gbfs_max_expansions`, and `gbfs_max_depth`; shared local recovery/extraction fallbacks now use the GBFS expansion/depth defaults.
- GBFS preserves the old hard-instance resource-protection story with an estimated grounded-applicable-action pre-gate before full grounding. When the estimate exceeds `gbfs_max_applicable_actions`, the attempt records `skipped_resource_limit` with `resource_gate: "gbfs_estimated_applicable_actions"`.
- Recovery metadata for GBFS uses `is_exact_gbfs: false` when goal-regression recovery supplies the plan.

## Verification Signals

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_pipeline.py tests/phase3/test_phase3_pipeline_regressions.py -q
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_medium_trace_targets.py tests/phase3/test_phase3_blocksworld_medium_traces.py tests/phase3/test_phase3_local_trace_safety.py -q
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_15puzzle_easy_traces.py::test_15puzzle_easy_0002_pipeline_defaults_emit_all_planner_traces -q
source ~/cd_vlaplan && source .venv/bin/activate && timeout 180s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id 15puzzle-dev-hard-0000 --planner gbfs --output-root tmp/phase3_gbfs_15puzzle_hard_verify --quiet
source ~/cd_vlaplan && source .venv/bin/activate && timeout 120s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id blocksworld-train-medium-0011 --planner gbfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_gbfs_blocksworld_medium_verify --quiet
```

Observed during implementation: hard `15puzzle-dev-hard-0000` produced one `success_full_trace` GBFS trace, and blocksworld medium produced four `success_full_trace` traces for `gbfs ff iw graphplan`.

Final verification after the reviewer-found duplicate-state/resource-limit corrections and the GBFS pre-gate:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_pipeline.py tests/phase3/test_phase3_pipeline_regressions.py tests/phase3/test_phase3_medium_trace_targets.py tests/phase3/test_phase3_blocksworld_medium_traces.py tests/phase3/test_phase3_local_trace_safety.py -q
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3 -q
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3 tests/phase3
source ~/cd_vlaplan && source .venv/bin/activate && timeout 180s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id 15puzzle-dev-hard-0000 --planner gbfs --output-root tmp/phase3_gbfs_15puzzle_hard_verify_final --quiet
source ~/cd_vlaplan && source .venv/bin/activate && timeout 180s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id blocksworld-train-medium-0011 --planner gbfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_gbfs_blocksworld_medium_verify_final --quiet
```

Observed final pre-split signals: focused Phase 3 tests `50 passed`, full Phase 3 suite `69 passed`, compileall clean, hard 15puzzle GBFS `success_full_trace: 1`, blocksworld all-four `success_full_trace: 4`, replay/fidelity validators clean, and planner-attempt validators reported `missing_attempt_records: 0` for both final output roots.

After the final module split, `scripts/phase3/gbfs.py` keeps the GBFS implementation under the review-size ceiling while `tests/phase3/test_phase3_gbfs.py` keeps the new GBFS-specific regressions separate from the broader pipeline tests. Post-split verification used:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_gbfs.py tests/phase3/test_phase3_pipeline.py -q
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_gbfs.py tests/phase3/test_phase3_15puzzle_easy_traces.py::test_15puzzle_easy_local_planners_emit_replay_valid_plans -q
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3 -q
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3 tests/phase3
source ~/cd_vlaplan && source .venv/bin/activate && timeout 180s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id 15puzzle-dev-hard-0000 --planner gbfs --output-root tmp/phase3_gbfs_15puzzle_hard_verify_post_split2 --quiet
source ~/cd_vlaplan && source .venv/bin/activate && timeout 180s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id blocksworld-train-medium-0011 --planner gbfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_gbfs_blocksworld_medium_verify_post_split2 --quiet
```

Observed post-split signals: pipeline/GBFS focused tests `20 passed`; 15puzzle local-planner focused tests `6 passed`; full Phase 3 suite `69 passed`; compileall clean; post-split hard 15puzzle root emitted `success_full_trace: 1`; post-split blocksworld all-four root emitted `success_full_trace: 4`; replay/fidelity/schema/planner-attempt validators were clean with `missing_attempt_records: 0` for both post-split roots.

Final reviewer follow-up fixed the goal-success tie-break in `run_gbfs()`: when multiple goal successors are generated from the same selected state, GBFS now preserves the first generated goal successor so the implementation matches the advertised `min_unsatisfied_goals_then_plan_length_then_generation_order` rule. Regression coverage is `test_gbfs_goal_successors_use_generation_order_tie_break` in `tests/phase3/test_phase3_gbfs.py`.

Final tie-break verification used:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_gbfs.py -q
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3 -q
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3 tests/phase3
source ~/cd_vlaplan && source .venv/bin/activate && timeout 180s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id 15puzzle-dev-hard-0000 --planner gbfs --output-root tmp/phase3_gbfs_15puzzle_hard_verify_tiebreak --quiet
source ~/cd_vlaplan && source .venv/bin/activate && timeout 180s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id blocksworld-train-medium-0011 --planner gbfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_gbfs_blocksworld_medium_verify_tiebreak --quiet
```

Observed final tie-break signals: focused GBFS tests `5 passed`; full Phase 3 suite `70 passed`; compileall clean; hard 15puzzle root emitted `success_full_trace: 1`; blocksworld all-four root emitted `success_full_trace: 4`; replay/fidelity/schema/planner-attempt validators were clean with `missing_attempt_records: 0` for both final roots.

Final Oracle-requested completion verification added a generated-example assertion that checks actual emitted GBFS trace semantics: `planner == "gbfs"`, `algorithm == "greedy_best_first"`, `heuristic_source == "unsatisfied_goal_count"`, non-empty `frontier_events`, replay-valid plan, and no `plan_recovery` for exact representative GBFS traces. The final full suite after that assertion was `71 passed`.

The preserved final representative roots are:

- `tmp/phase3_gbfs_15puzzle_hard_verify_final_oracle`
- `tmp/phase3_gbfs_blocksworld_medium_verify_final_oracle`

Direct trace-file inspection confirmed:

```text
tmp/phase3_gbfs_15puzzle_hard_verify_final_oracle/traces/15puzzle/dev/15puzzle-dev-hard-0000/gbfs.planner_trace.json: algorithm=greedy_best_first, heuristic_source=unsatisfied_goal_count, frontier_events=500, has_plan_recovery=false
tmp/phase3_gbfs_blocksworld_medium_verify_final_oracle/traces/blocksworld/train/blocksworld-train-medium-0011/gbfs.planner_trace.json: algorithm=greedy_best_first, heuristic_source=unsatisfied_goal_count, frontier_events=454, has_plan_recovery=false
```

Final Oracle-requested validation signals: hard 15puzzle `success_full_trace: 1` and `extracted_trace_count: 1`; blocksworld all-four `success_full_trace: 4` and `extracted_trace_count: 4`; replay validators had `examples_with_failed_replay: 0`; fidelity validators had `invalid_external_full_trace_labels: 0`; planner-attempt validators had `missing_attempt_records: 0`; planner-attempt schema validators had `invalid_rows: 0`.
