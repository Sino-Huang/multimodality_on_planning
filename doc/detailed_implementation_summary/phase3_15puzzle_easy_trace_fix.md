# Phase 3 15puzzle Easy Trace Fix

Date: 2026-07-06

## Summary

Updated the Phase 3 local trace generation path so simple typed 15puzzle instances can produce replay-valid reasoning traces for all four configured search algorithms. As of the 2026-07-07 GBFS replacement, the active configured set is `gbfs`, `ff`, `iw`, and `graphplan`; old `bfs` selection is rejected rather than aliased.

The motivating failure was the rerun of `outputs/phase3_curriculum_traces_rerun`, where easy 15puzzle attempts showed `bfs` skipped by resource limits and `iw` failing or running too long. Runtime inspection of `15puzzle-dev-easy-0000` showed 17 raw objects but only 648 typed grounded actions, so the old BFS raw-object gate was too coarse for typed simple tasks.

## Historical BFS-Era Changes

- `scripts/phase3/pipeline.py`
  - Replaced the raw BFS object-count gate with a typed schema grounding estimate.
  - Added `algorithm: "bfs"` to BFS traces.
  - Capped BFS queue-event retention during search.
  - Added defaults for bounded FF/IW caps, raised BFS/Graphplan/recovery caps to `250000` expansions for small typed tasks admitted by the pre-gate, and aligned pipeline JSON/mutex defaults with the CLI wrapper.
- `scripts/phase3/local_planners.py`
  - Added bounded serial recovery after FF-style best-first hits its cap.
  - Marked recovery as non-exact Fast Downward FF in trace metadata.
- `scripts/phase3/local_iw.py`
  - Added bounded serial recovery at configured max IW width after novelty cap/exhaustion.
  - Marked recovery as non-exact IW in trace metadata.
  - Compacted recovered IW novelty traces to stay under JSONL size limits.
- `scripts/phase3/local_serial.py`
  - Added shared bounded serial plan recovery used by local FF and IW.
- `scripts/phase3/generate_curriculum_trace_dataset.py`
  - Added CLI knobs for FF/IW/recovery caps.
- `tests/phase3/test_phase3_15puzzle_easy_traces.py`
  - Added regression coverage for typed BFS gating, replay-valid local planner plans, and real CLI all-four trace extraction.

Current active Phase 3 generation uses the GBFS replacement documented in `phase3_gbfs_replacement.md`: `gbfs`, `ff`, `iw`, and `graphplan` are the active planner set, and old `bfs` selection is rejected rather than aliased.

## Commands

RED proof:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_15puzzle_easy_traces.py::test_15puzzle_easy_0000_bfs_gate_uses_typed_grounding_estimate -q
```

Observed pre-fix failure: `_bfs_estimate_exceeds_resource_gate(task)` returned `True` for `15puzzle-dev-easy-0000`.

Focused GREEN proof:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_15puzzle_easy_traces.py -q
```

Expected result: `3 passed`.

Real CLI surface:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && timeout 180s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id 15puzzle-dev-easy-0000 --planner gbfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_15puzzle_easy_0000_all_local_verify --quiet
```

Expected signal: exit code `0`, `attempt_status_summary` equals `{"success_full_trace": 4}`, and `extracted_trace_count` equals `4`.

Oracle counterexample and first-ten easy subset:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && timeout 2400s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id 15puzzle-dev-easy-0000 --instance-id 15puzzle-dev-easy-0001 --instance-id 15puzzle-dev-easy-0002 --instance-id 15puzzle-dev-easy-0003 --instance-id 15puzzle-dev-easy-0004 --instance-id 15puzzle-dev-easy-0005 --instance-id 15puzzle-dev-easy-0006 --instance-id 15puzzle-dev-easy-0007 --instance-id 15puzzle-dev-easy-0008 --instance-id 15puzzle-dev-easy-0009 --planner gbfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_15puzzle_easy_first_ten_all_local_verify --quiet
```

Expected signal: exit code `0`, `attempt_status_summary` equals `{"success_full_trace": 40}`, and `extracted_trace_count` equals `40`.

Expanded focused tests:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_15puzzle_easy_traces.py -q
```

Expected result: `4 passed`.

Direct pipeline API regression:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_15puzzle_easy_traces.py::test_15puzzle_easy_0002_pipeline_defaults_emit_all_planner_traces -q
```

Expected result: `1 passed`.

Adjacent regression:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_blocksworld_medium_traces.py tests/phase3/test_phase3_pipeline_regressions.py tests/phase3/test_phase3_local_trace_safety.py -q
```

Expected result: all tests pass.

## Notes

FF and IW recoveries are intentionally labeled as non-exact local recoveries. They provide replay-valid reasoning traces for simple tasks without pretending to be canonical Fast Downward FF or exact IW when the local approximations need bounded serial recovery.
