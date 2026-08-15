# Phase 3 Parallel Jobs Generation

## Summary

Phase 3 data generation now supports process-based parallel planner attempts through `--jobs` on both `scripts/phase3/generate_curriculum_trace_dataset.py` and `python -m scripts.phase3.generate_supervised_data`, plus `jobs=` on `generate_supervised_data()`. The default remains `1`, preserving deterministic output ordering while still running each planner attempt in a bounded worker process.

Parallel execution is intentionally limited to planner-attempt computation. Worker processes return attempt, replay, and example records to the parent process. The parent process still performs deterministic sorting and all JSONL/report writes, which avoids concurrent writes to the same output root.

Planner attempts now also have parent-enforced wall-clock safety. The default per-attempt timeout is 1200 seconds through `--planner-attempt-timeout-seconds` / `planner_attempt_timeout_seconds`. When attempts for one domain accumulate 3600 seconds of actual planner-attempt timeouts through `--domain-timeout-seconds` / `domain_timeout_seconds`, later attempts for that domain are skipped with `status: skipped_resource_limit` and `resource_gate: domain_timeout_budget`. In parallel runs, the parent reserves each in-flight attempt's timeout budget before launch; reservation saturation defers same-domain work until an in-flight attempt finishes, while only actual accumulated timeout seconds trigger a permanent domain skip. Timed-out workers are isolated in their own process group and the parent terminates/kills the process group. External planner subprocesses are launched in their own process group, are killed on their own `planner_timeout`, and are also cleaned up by the worker's SIGTERM path when the parent attempt timeout fires first.

## Usage

```bash
source ~/cd_vlaplan && source .venv/bin/activate

python scripts/phase3/generate_curriculum_trace_dataset.py \
  --bucket easy \
  --bucket medium \
  --planner gbfs \
  --planner ff \
  --planner iw \
  --planner graphplan \
  --jobs 8 \
  --output-root outputs/phase3_curriculum_traces_upgraded_$(date +%Y%m%d_%H%M%S) \
  --quiet
```

Use `--jobs 1` for sequential execution. `--jobs 0` is rejected with `--jobs must be at least 1`.

The default timeout policy is equivalent to:

```bash
--planner-attempt-timeout-seconds 1200 \
--domain-timeout-seconds 3600
```

Use `0` for either timeout flag only when deliberately disabling that safety rail.

## Verification

RED tests before implementation:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_pipeline.py::test_generate_supervised_data_parallel_jobs_match_sequential_records tests/phase3/test_phase3_pipeline.py::test_generate_curriculum_trace_dataset_rejects_zero_jobs -q
```

Observed: both tests failed because `generate_supervised_data()` did not accept `jobs` and the CLI did not recognize `--jobs`.

GREEN verification after implementation:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_pipeline.py::test_generate_supervised_data_parallel_jobs_match_sequential_records tests/phase3/test_phase3_pipeline.py::test_generate_curriculum_trace_dataset_rejects_zero_jobs -q
```

Observed: `2 passed`.

Timeout TDD proof:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_pipeline.py -q -k 'parallel_jobs or timeout or accumulated or reserves_parallel or zero_jobs'
```

Observed RED before implementation: injected slow attempts could not be passed into the old runner API / no bounded timeout path existed. A later review RED found that reservation saturation skipped fast successful same-domain attempts under `jobs=4`, and that external planner descendants could survive parent attempt timeout or ignore SIGTERM. Observed GREEN after implementation and review hardening: `17 passed, 12 deselected in 25.26s`, with slow attempts recorded as `failed_planner_timeout`, later same-domain attempts skipped only after actual accumulated timeouts, reservation saturation deferring rather than permanently skipping fast work, subprocess children killed with the timed-out worker process group, external planner descendants killed through both parent-attempt-timeout and external-timeout paths, SIGTERM-resistant external children killed by SIGKILL escalation, negative API timeout limits rejected, and both CLIs rejecting `--jobs 0`.

Real CLI surface:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && OUT="tmp/phase3_jobs2_cli_smoke_$(date +%Y%m%d_%H%M%S)" && python scripts/phase3/generate_curriculum_trace_dataset.py --bucket easy --limit 1 --planner gbfs --planner ff --jobs 2 --output-root "$OUT" --quiet | tee "$OUT.summary.json" && python -m scripts.phase3.verify_replay_validated_examples --dataset-root "$OUT" && python -m scripts.phase3.verify_fidelity_labels --dataset-root "$OUT"
```

Observed: `success_full_trace: 2`, `extracted_trace_count: 2`, replay failures `0`, invalid fidelity labels `0`.

Timeout-flag CLI surface:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && OUT="tmp/phase3_timeout_cli_smoke_$(date +%Y%m%d_%H%M%S)" && python scripts/phase3/generate_curriculum_trace_dataset.py --bucket easy --limit 1 --planner gbfs --jobs 1 --planner-attempt-timeout-seconds 1200 --domain-timeout-seconds 3600 --output-root "$OUT" --quiet | tee "$OUT.summary.json"
```

Observed after review hardening: command exited `0` at `tmp/phase3_timeout_cli_smoke_20260708_155339` with `success_full_trace: 1` and `extracted_trace_count: 1`. Replay and fidelity validators reported `examples_with_failed_replay: 0`, `examples_without_replay_validation: 0`, and `invalid_external_full_trace_labels: 0`.

Regression verification:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_pipeline.py tests/phase3/test_phase3_gbfs.py -q
```

Observed after the final timeout scheduler fix: `26 passed` before review hardening; final focused timeout/jobs coverage is included in the `16 passed` command above.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3 -q
```

Observed after review hardening: `84 passed in 1223.84s (0:20:23)`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3 tests/phase3
```

Observed: exit code `0`.
