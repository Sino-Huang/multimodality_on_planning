# Phase 3 Parallel Jobs Generation

- Added native `--jobs` support to `scripts/phase3/generate_curriculum_trace_dataset.py` and `python -m scripts.phase3.generate_supervised_data`; default is `1` for deterministic one-at-a-time launch behavior.
- `generate_supervised_data(..., jobs=N)` now supports process-based planner attempts for all `N >= 1`; even `jobs=1` uses a bounded worker process so local planners cannot hang the parent indefinitely.
- The implementation keeps output writing parent-only: workers return attempt/replay/example records, and the parent sorts and writes diagnostics, split JSONL, and reports.
- `--jobs 0` is rejected with `--jobs must be at least 1`.
- Planner attempts have parent-enforced wall-clock safety: default `--planner-attempt-timeout-seconds 1200` and default `--domain-timeout-seconds 3600`.
- A timed-out attempt records `status: failed_planner_timeout` with `resource_gate: planner_attempt_timeout`.
- After one domain accumulates the actual domain timeout budget, later attempts for that domain record `status: skipped_resource_limit` with `resource_gate: domain_timeout_budget`.
- Parallel scheduling reserves each in-flight attempt's timeout seconds against its domain before launch. Reservation saturation defers same-domain work while other attempts finish; it does not permanently skip work unless actual accumulated timeouts have reached the domain budget.
- Timed-out workers run in their own process group; the parent terminates/kills the process group so child subprocesses launched inside an attempt are not orphaned.
- External planner subprocesses launched through `_external_plan()` also run in a separate process group and are group-killed on their own `planner_timeout`. If the parent attempt timeout fires first, the worker SIGTERM handler kills the active external planner process group before the worker exits.
- Programmatic negative timeout values now raise `ValueError`; `0` remains the explicit disable value.
- TDD proof: the new tests first failed because `jobs` was unsupported and `--jobs` was unrecognized, then passed after implementation.
- Key regression test: `tests/phase3/test_phase3_pipeline.py::test_generate_supervised_data_parallel_jobs_match_sequential_records` confirms `jobs=2` produces byte-identical planner attempts, replay rows, and split JSONL against `jobs=1` on the fixture.
- Timeout tests: `tests/phase3/test_phase3_pipeline.py::test_run_planner_jobs_times_out_slow_attempt`, `tests/phase3/test_phase3_pipeline.py::test_run_planner_jobs_blocks_domain_after_accumulated_timeouts`, `tests/phase3/test_phase3_pipeline.py::test_run_planner_jobs_reserves_parallel_domain_timeout_budget`, `tests/phase3/test_phase3_pipeline.py::test_run_planner_jobs_defers_reserved_domain_budget_until_actual_timeout`, `tests/phase3/test_phase3_pipeline.py::test_run_planner_jobs_kills_child_process_group_on_timeout`, `tests/phase3/test_phase3_pipeline.py::test_run_planner_jobs_kills_external_planner_group_on_parent_timeout`, `tests/phase3/test_phase3_pipeline.py::test_external_planner_timeout_kills_child_process_group`, `tests/phase3/test_phase3_pipeline.py::test_external_planner_timeout_kills_sigterm_resistant_child`, and `tests/phase3/test_phase3_pipeline.py::test_run_planner_jobs_rejects_negative_timeout_limits` cover timeout, domain-budget skip, parallel reservation throttling, attempt subprocess cleanup, external planner subprocess cleanup, SIGKILL escalation, and API validation behavior.
- Real CLI smoke command:
  ```bash
  source ~/cd_vlaplan && source .venv/bin/activate && OUT="tmp/phase3_jobs2_cli_smoke_$(date +%Y%m%d_%H%M%S)" && python scripts/phase3/generate_curriculum_trace_dataset.py --bucket easy --limit 1 --planner gbfs --planner ff --jobs 2 --output-root "$OUT" --quiet | tee "$OUT.summary.json" && python -m scripts.phase3.verify_replay_validated_examples --dataset-root "$OUT" && python -m scripts.phase3.verify_fidelity_labels --dataset-root "$OUT"
  ```
- Observed smoke signal: `success_full_trace: 2`, `extracted_trace_count: 2`, replay failures `0`, invalid fidelity labels `0`.
- Timeout CLI knobs smoke command:
  ```bash
  source ~/cd_vlaplan && source .venv/bin/activate && OUT="tmp/phase3_timeout_cli_smoke_$(date +%Y%m%d_%H%M%S)" && python scripts/phase3/generate_curriculum_trace_dataset.py --bucket easy --limit 1 --planner gbfs --jobs 1 --planner-attempt-timeout-seconds 1200 --domain-timeout-seconds 3600 --output-root "$OUT" --quiet | tee "$OUT.summary.json"
  ```
- Observed timeout smoke signal: output root `tmp/phase3_timeout_cli_smoke_20260708_155339`, `success_full_trace: 1`, `extracted_trace_count: 1`, replay failures `0`, missing replay validation `0`, invalid fidelity labels `0`.
- Focused timeout/jobs/external-planner regression after review hardening: `pytest tests/phase3/test_phase3_pipeline.py -q -k 'external_planner or jobs or timeout or negative or reserved'` -> `17 passed, 12 deselected in 25.26s`.
- Full Phase 3 regression after review hardening: `pytest tests/phase3 -q` -> `84 passed in 1223.84s (0:20:23)`.
