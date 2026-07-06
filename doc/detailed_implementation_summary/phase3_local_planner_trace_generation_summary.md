# Phase 3 Local Planner Trace Generation Summary

## Scope

This update extends the Phase 3 supervised planning pipeline with repo-local trace generation for the proposal P0 planners when the existing lightweight STRIPS parser can ground the instance. The implementation is split across `scripts/phase3/local_planners.py`, `scripts/phase3/local_iw.py`, `scripts/phase3/local_graphplan.py`, and `scripts/phase3/local_planner_types.py`, and is wired into `scripts/phase3/pipeline.py` after configured external planners are probed, so existing planner modules remain the first attempted source and local Python traces are the fallback when those modules are unavailable or do not produce a successful replayable plan.

The local planners are deterministic, replay-validated, and intended for small supported curriculum instances:

- `bfs`: existing queue/visited full trace remains unchanged.
- `ff`: FF-style/local delete-relaxation approximation using relaxed heuristic metadata and bounded best-first recovery when greedy successor choice dead-ends. It remains `is_exact_fast_downward_ff = false`.
- `iw`: configurable IW(k) novelty trace with expand/prune events and successor novelty decisions. It defaults to IW(3) with `local_iw_max_width=3`, and cheaper sweeps can lower width with `local_iw_width` / `--local-iw-width`.
- `graphplan`: local planning-graph trace with proposition/action layers, action mutex pairs, action-mutex-only extraction metadata, and a replay-validated serial extraction plan.

Unsupported PDDL features, search resource limits, oversized examples, and unsolved local attempts remain diagnostics. External planners configured with `PHASE3_FF_PLANNER`, `PHASE3_IW_PLANNER`, or `PHASE3_GRAPHPLAN_PLANNER` remain available as first-attempt final-plan sources and are labeled `success_plan_replayed` rather than `success_full_trace` when they do not expose internal traces.

Destructive output cleanup is guarded: Phase 3 generation refuses unsafe output roots such as the input root, any output root that contains the input root, repository root, current working directory, home directory, filesystem root, repo-local `data/`/`outputs/`/`tmp/` roots themselves, and paths outside repo-local `data/`, `outputs/`, or `tmp/`.

## Smoke Result

Small real-data smoke over one `blocksworld`, one `ferry`, and one `gripper` accepted curriculum instance:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.generate_supervised_data --input-root tmp/phase3_trace_smoke_input --output-root tmp/phase3_trace_smoke_output --planners bfs ff iw graphplan --json
```

Observed signal:

- `accepted_instances`: 3
- `planner_attempts`: 12
- `emitted_examples`: 7
- `fidelity_summary.success_full_trace`: 7
- `graphplan`: 2 local full-trace successes, 1 controlled resource-limit skip
- `bfs`: 2 local full-trace successes, 1 controlled resource-limit skip
- `ff`: 2 local full-trace successes, 1 controlled no-plan diagnostic
- `iw`: 1 local full-trace success, 2 controlled no-plan diagnostics

## Verification Commands

Focused RED-to-GREEN test:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_pipeline.py::test_generate_supervised_data_and_verifiers_on_fixture
```

Phase 3 suite:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3
```

Adjacent documented suites:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3 tests/planning_benchmark tests/data_collect
```

Final observed result after review-fix regressions for IW resource handling and metadata consistency: `168 passed in 10.35s`.

Small-smoke schema/replay/fidelity checks:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.validate_jsonl_schema --schema tmp/phase3_trace_smoke_output/schema/supervised_planning_example.schema.json --jsonl tmp/phase3_trace_smoke_output/train.jsonl --jsonl tmp/phase3_trace_smoke_output/dev.jsonl --jsonl tmp/phase3_trace_smoke_output/test.jsonl
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_replay_validated_examples --dataset-root tmp/phase3_trace_smoke_output
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_fidelity_labels --dataset-root tmp/phase3_trace_smoke_output
```

Full corpus regeneration command remains:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.generate_supervised_data --input-root data/curriculum_pddl --output-root data/phase3_supervised_planning --planners bfs ff iw graphplan --json
```

## Notes

`scripts/phase3/pipeline.py` is an inherited oversized module. New algorithmic code was split into `scripts/phase3/local_planners.py` for FF dispatch and relaxed traces, `scripts/phase3/local_iw.py` for IW(k) novelty search, `scripts/phase3/local_graphplan.py` for Graphplan-specific extraction/tracing, and `scripts/phase3/local_planner_types.py` for shared request/result/search-node dataclasses. The review-regression tests were also split into `tests/phase3/test_phase3_pipeline_regressions.py` so the primary pipeline test file stays under the 250 pure-LOC review ceiling.

Final line-count audit after the split:

```text
scripts/phase3/local_planner_types.py 21
scripts/phase3/local_graphplan.py 103
scripts/phase3/local_planners.py 156
scripts/phase3/io_utils.py 77
scripts/phase3/verifiers.py 183
tests/phase3/test_phase3_pipeline.py 236
tests/phase3/test_phase3_pipeline_regressions.py 61
```

After the final ancestor-output safety regression, the focused files remain within the review ceiling:

```text
scripts/phase3/io_utils.py 78
tests/phase3/test_phase3_pipeline_regressions.py 71
```

Post-review regression fixes added coverage for IW empty-initial-state expansion, IW `max_plan_length`, IW `local_max_applicable_actions`, merged resource-limit reporting in examples/replay diagnostics, and skipped oversized-example attempt metadata. After those fixes, focused line counts were:

```text
scripts/phase3/local_planners.py 161
scripts/phase3/pipeline.py 484
tests/phase3/test_phase3_pipeline_regressions.py 169
```

After the focused Blocksworld medium trace recovery and IW module split, focused line counts are:

```text
scripts/phase3/local_planners.py 185
scripts/phase3/local_iw.py 83
scripts/phase3/generate_curriculum_trace_dataset.py 141
tests/phase3/test_phase3_pipeline_regressions.py 236
tests/phase3/test_phase3_blocksworld_medium_traces.py 96
```

`scripts/phase3/pipeline.py` remains larger than 250 pure LOC because it owns the inherited end-to-end Phase 3 orchestration surface; this change avoids adding local planner algorithm code to it.
