# Phase 3 15puzzle Easy Trace Fix

Date: 2026-07-06

## Problem

`15puzzle-dev-easy-*` instances could fail to emit valid Phase 3 reasoning traces even though they are easy curriculum tasks. The observed rerun showed `bfs` as `skipped_resource_limit`, `iw` as `failed_no_plan_extracted` or a long-running attempt, and occasional local planner skips.

## Root Causes

- BFS used a raw object-count gate before grounding. For `15puzzle-dev-easy-0000`, raw object count is 17, but typed grounding is only 648 actions, so the old `object_count > 8` gate was a false positive.
- Local FF-style best-first could spend too long evaluating relaxed heuristics on puzzle states before finding a plan.
- IW novelty pruning alone is incomplete for this 15puzzle instance and can run too long or fail to extract a plan.
- Recovered IW traces were initially too large for the `max_jsonl_target_chars` guard when all novelty events were retained.

## Fix

- `scripts/phase3/pipeline.py`
  - BFS resource gate now estimates each schema using typed object domains, matching `ground_actions()` semantics.
  - BFS trace payloads include `algorithm: "bfs"` and cap stored queue events during search.
  - Defaults now include bounded FF/IW search caps, `250000` expansion caps for BFS, Graphplan serial extraction, and serial recovery, `local_max_mutex_pairs=1000000`, and `max_jsonl_target_chars=10000000`. This covers the measured first-ten easy 3x3 puzzle subset while the typed schema pre-gate still protects larger hard tasks.
- `scripts/phase3/local_planners.py`
  - FF-style local planner first tries the existing relaxed best-first path, then uses bounded serial recovery if that path hits a resource status.
  - Recovery metadata records `is_exact_fast_downward_ff: False`.
- `scripts/phase3/local_iw.py`
  - IW still tries novelty search first.
  - At configured max width, it uses bounded serial recovery if novelty search reaches its cap or exhausts without a plan.
  - Recovery metadata records `is_exact_iw: False` and the recovery reason.
  - Recovered IW traces keep a compact novelty prefix via `local_iw_recovery_trace_steps`.
- `scripts/phase3/local_serial.py`
  - Shared bounded serial recovery helper for replay-valid local plan recovery.
- `scripts/phase3/generate_curriculum_trace_dataset.py`
  - CLI exposes `--local-ff-best-first-max-expansions`, `--local-iw-novelty-max-expansions`, `--local-iw-recovery-trace-steps`, and `--local-serial-recovery-max-expansions`.

## Verification

RED:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_15puzzle_easy_traces.py::test_15puzzle_easy_0000_bfs_gate_uses_typed_grounding_estimate -q
```

Failed before the fix with `_bfs_estimate_exceeds_resource_gate(task) is True` for `15puzzle-dev-easy-0000`.

GREEN:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_15puzzle_easy_traces.py -q
```

Result: `3 passed`.

Real CLI surface:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && timeout 180s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id 15puzzle-dev-easy-0000 --planner bfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_15puzzle_easy_0000_all_local_verify --quiet
```

Result: `attempt_status_summary: {"success_full_trace": 4}`, `extracted_trace_count: 4`.

Oracle counterexample and broader easy subset:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && timeout 2400s python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id 15puzzle-dev-easy-0000 --instance-id 15puzzle-dev-easy-0001 --instance-id 15puzzle-dev-easy-0002 --instance-id 15puzzle-dev-easy-0003 --instance-id 15puzzle-dev-easy-0004 --instance-id 15puzzle-dev-easy-0005 --instance-id 15puzzle-dev-easy-0006 --instance-id 15puzzle-dev-easy-0007 --instance-id 15puzzle-dev-easy-0008 --instance-id 15puzzle-dev-easy-0009 --planner bfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_15puzzle_easy_first_ten_all_local_verify --quiet
```

Result: `attempt_status_summary: {"success_full_trace": 40}`, `extracted_trace_count: 40`.

Adjacent regression:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_blocksworld_medium_traces.py tests/phase3/test_phase3_pipeline_regressions.py tests/phase3/test_phase3_local_trace_safety.py -q
```

Result: `24 passed`.

Expanded focused regression:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_15puzzle_easy_traces.py -q
```

Result after adding `15puzzle-dev-easy-0002` and first-ten CLI coverage: `4 passed`.

Direct pipeline API regression:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_15puzzle_easy_traces.py::test_15puzzle_easy_0002_pipeline_defaults_emit_all_planner_traces -q
```

Result: `1 passed`. This guards against the core `generate_supervised_data()` path using smaller defaults than the CLI wrapper.
