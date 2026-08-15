# Phase 3 GBFS Replacement

Date: 2026-07-07

## Summary

Replaced the active Phase 3 BFS planner surface with GBFS. The public/default planner set is now `gbfs`, `ff`, `iw`, and `graphplan`; the old `bfs` label is rejected rather than treated as an alias.

## Implementation

- `scripts/phase3/pipeline.py` now exposes `DEFAULT_PLANNERS = ("gbfs", "ff", "iw", "graphplan")` and dispatches active GBFS attempts through `scripts/phase3/gbfs.py`.
- `scripts/phase3/gbfs.py` owns the focused GBFS implementation (`run_gbfs()`), trace constructor (`gbfs_trace()`), and estimated applicable-action resource pre-gate (`gbfs_estimate_exceeds_resource_gate()`).
- GBFS uses a simple unsatisfied-goal-count heuristic suitable for LLM-readable reasoning traces.
- GBFS trace payloads report `algorithm: "greedy_best_first"`, `heuristic_source: "unsatisfied_goal_count"`, `frontier_events`, selected-state atoms, successor heuristic values, and the tie-break rule.
- Resource keys moved from active `bfs_*` controls to `gbfs_max_applicable_actions`, `gbfs_max_expansions`, and `gbfs_max_depth`.
- The CLI exposes `--gbfs-max-applicable-actions`, `--gbfs-max-expansions`, and `--gbfs-max-depth` and inherits planner choices from the new defaults.
- The GBFS path keeps an estimated applicable-action pre-gate before full grounding. Attempts above `gbfs_max_applicable_actions` are reported as `skipped_resource_limit` with `resource_gate: "gbfs_estimated_applicable_actions"`.
- Shared local fallback caps in FF/IW/Graphplan/serial recovery now use the GBFS expansion/depth defaults.

## Test Coverage

- Added coverage that active defaults are `gbfs ff iw graphplan`.
- Added coverage that old `bfs` API selection raises `ValueError`.
- Added GBFS resource-limit and trace-metadata assertions.
- Added a regression that forces the GBFS estimate gate and verifies the diagnostic status/resource gate before full trace emission.
- Split GBFS-specific regressions into `tests/phase3/test_phase3_gbfs.py` so the main pipeline test file remains below the review-size ceiling.
- Updated Phase 3 pipeline, medium, blocksworld, 15puzzle, and trace-extraction safety tests to expect `gbfs` outputs.

## Verification Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_pipeline.py tests/phase3/test_phase3_pipeline_regressions.py -q
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_medium_trace_targets.py tests/phase3/test_phase3_blocksworld_medium_traces.py tests/phase3/test_phase3_local_trace_safety.py -q
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_15puzzle_easy_traces.py::test_15puzzle_easy_0002_pipeline_defaults_emit_all_planner_traces -q
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_pipeline.py::test_generate_supervised_data_gbfs_estimate_gate_rejects_large_grounding tests/phase3/test_phase3_pipeline.py::test_gbfs_resource_limit_returns_controlled_status -q
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3 -q
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3 tests/phase3
source ~/cd_vlaplan && source .venv/bin/activate && timeout 180s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id 15puzzle-dev-hard-0000 --planner gbfs --output-root tmp/phase3_gbfs_15puzzle_hard_verify --quiet
source ~/cd_vlaplan && source .venv/bin/activate && timeout 120s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id blocksworld-train-medium-0011 --planner gbfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_gbfs_blocksworld_medium_verify --quiet
```

Expected signal: focused tests pass; hard 15puzzle emits one GBFS `success_full_trace`; blocksworld medium emits four `success_full_trace` traces and four extracted trace files.

Final observed signals after the post-review corrections: GBFS gate focused tests `2 passed`; main focused Phase 3 subset `50 passed`; full `tests/phase3 -q` `69 passed`; compileall clean; `--planner bfs` rejected by argparse choices; fresh hard 15puzzle final root emitted `success_full_trace: 1`; fresh blocksworld final root emitted `success_full_trace: 4`; replay/fidelity validators were clean; planner-attempt validation reported `missing_attempt_records: 0` for both final roots.

Post-split verification after moving GBFS into `scripts/phase3/gbfs.py`: `pytest tests/phase3/test_phase3_gbfs.py tests/phase3/test_phase3_pipeline.py -q` reported `20 passed`; `pytest tests/phase3/test_phase3_gbfs.py tests/phase3/test_phase3_15puzzle_easy_traces.py::test_15puzzle_easy_local_planners_emit_replay_valid_plans -q` reported `6 passed`; full `pytest tests/phase3 -q` reported `69 passed`; compileall stayed clean; post-split hard 15puzzle and blocksworld final roots emitted `success_full_trace: 1` and `success_full_trace: 4` respectively; replay, fidelity, schema, and planner-attempt validators stayed clean.

Final reviewer follow-up fixed equal-heuristic goal-success tie-breaking: `run_gbfs()` now preserves the first generated goal successor when several goal successors are enumerated from one selected state, matching the documented generation-order tie-break. `tests/phase3/test_phase3_gbfs.py::test_gbfs_goal_successors_use_generation_order_tie_break` covers this case.

Final observed signals after that tie-break fix: `pytest tests/phase3/test_phase3_gbfs.py -q` reported `5 passed`; full `pytest tests/phase3 -q` reported `70 passed`; compileall stayed clean; fresh hard 15puzzle and blocksworld roots (`tmp/phase3_gbfs_15puzzle_hard_verify_tiebreak`, `tmp/phase3_gbfs_blocksworld_medium_verify_tiebreak`) emitted `success_full_trace: 1` and `success_full_trace: 4`; replay, fidelity, schema, and planner-attempt validators were clean with `missing_attempt_records: 0` for both roots.

Final Oracle-requested completion verification added a generated-example regression that checks actual emitted GBFS trace semantics: planner `gbfs`, trace `algorithm: "greedy_best_first"`, `heuristic_source: "unsatisfied_goal_count"`, non-empty `frontier_events`, replay-valid plan, and no `plan_recovery` for exact generated GBFS traces. After that assertion, full `pytest tests/phase3 -q` reported `71 passed`.

The preserved final representative roots are `tmp/phase3_gbfs_15puzzle_hard_verify_final_oracle` and `tmp/phase3_gbfs_blocksworld_medium_verify_final_oracle`. Direct trace-file inspection confirmed the hard 15puzzle and blocksworld GBFS traces both have `algorithm=greedy_best_first`, `heuristic_source=unsatisfied_goal_count`, non-empty frontier events (`500` and `454` respectively), and no `plan_recovery`. The final replay, fidelity, planner-attempt, and planner-attempt schema validators all remained clean.
