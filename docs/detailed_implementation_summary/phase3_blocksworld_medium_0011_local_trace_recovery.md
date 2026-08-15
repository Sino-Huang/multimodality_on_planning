# Phase 3 Blocksworld Medium 0011 Local Trace Recovery

This note records the focused local-trace recovery for `blocksworld-train-medium-0011`.

## Problem

The instance already had replay-valid BFS and Graphplan plans under suitable limits, but local FF and IW did not emit traces under the earlier local algorithms:

- BFS solved the instance with a 10-action plan.
- Graphplan originally needed `local_graphplan_max_expansions` raised above the old batch default of `5000`; the default is now `250000` so this instance is allowed by default.
- IW(1) and IW(2) failed to extract a plan; IW(3) was required.
- The earlier local FF greedy path reached a local dead end after `(unstack b2 b1)`, `(putdown b2)`, `(pickup b2)`.

## Implementation

- `scripts/phase3/local_iw.py` now owns local IW(k) search and trace emission. `local_iw_width` defaults to 3 through `scripts/phase3/pipeline.py`, and `scripts/phase3/generate_curriculum_trace_dataset.py` exposes `--local-iw-width` for cheaper override sweeps.
- IW(k) search now has a separate `local_iw_max_width` resource cap, defaulting to 3. This preserves the focused IW(3) recovery while rejecting unbounded novelty tuple generation as `skipped_resource_limit`.
- `scripts/phase3/local_planners.py` keeps FF as an FF-style/local delete-relaxation approximation. It uses bounded best-first recovery guided by the existing relaxed heuristic and then emits the selected plan through the existing per-step relaxed-trace fields.
- `scripts/phase3/local_planners.py` remains explicit that FF is not canonical Fast Downward FF: traces keep `planner_source: local_delete_relaxed_hmax_supporter_closure` and per-step `is_exact_fast_downward_ff: false`.
- `scripts/phase3/local_planners.py` uses a local Python 3.10-compatible `assert_never` helper instead of importing `typing.assert_never`.
- `scripts/phase3/generate_curriculum_trace_dataset.py` rejects unsafe trace path components from generated JSONL rows before writing extracted planner traces.
- Graphplan internals were not changed for this instance; the focused rerun uses a higher explicit cap.

## Focused Command

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id blocksworld-train-medium-0011 --planner gbfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_bwm0011_all_local_verify --quiet
```

Expected signal: four extracted traces and four `success_full_trace` attempts. As of the 2026-07-07 GBFS replacement, the active command uses `gbfs`; old `bfs` selection is intentionally rejected.

## Regression Coverage

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_blocksworld_medium_traces.py
```

Expected signal: IW(1)/IW(2) remain insufficient, IW(3) succeeds and replays, FF succeeds and replays, Graphplan needs the higher cap, and the one-instance pipeline emits all four local traces.

Post-review safety regressions:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_local_trace_safety.py tests/phase3/test_phase3_pipeline_regressions.py::test_iw_rejects_width_below_one tests/phase3/test_phase3_blocksworld_medium_traces.py
```

Expected signal: oversized IW width skips before search, malicious trace path components are rejected, lower-bound IW validation still holds, and the exact blocksworld instance still emits valid traces.

Full verification used after the safety hardening:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3 tests/phase3
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/planning_benchmark tests/data_collect
source ~/cd_vlaplan && python -c "from scripts.phase3.local_planners import run_local_planner; print(run_local_planner.__name__)"
```
