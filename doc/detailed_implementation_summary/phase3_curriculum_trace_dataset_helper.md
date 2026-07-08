# Phase 3 Curriculum Trace Dataset Helper

This note records the helper script for generating planner trace datasets from all accepted instances in `data/curriculum_pddl`.

## Script

```text
scripts/phase3/generate_curriculum_trace_dataset.py
```

The script calls the existing Phase 3 `generate_supervised_data` pipeline, then extracts each emitted example's `supervised_target.planner_trace` into a browsable trace tree:

```text
<output-root>/traces/<domain>/<split>/<instance_id>/<planner>.planner_trace.json
<output-root>/traces/<domain>/<split>/<instance_id>/<planner>.full_example.json
```

By default it uses local full-trace fallbacks by clearing `PHASE3_FF_PLANNER`, `PHASE3_IW_PLANNER`, and `PHASE3_GRAPHPLAN_PLANNER`. Pass `--use-external-planners` to keep those environment variables. The helper prints JSON-lines progress events to stderr for each instance/planner attempt; pass `--quiet` only if you intentionally want to suppress those logs.

The batch helper uses bounded local defaults that are high enough for `blocksworld-train-medium-0011`: GBFS defaults to `--gbfs-max-applicable-actions 2000`, IW defaults to `--local-iw-width 3` with `--local-iw-max-width 3`, and Graphplan defaults to `--local-max-applicable-actions 2000` plus `--local-graphplan-max-expansions 250000`. Lower these only for cheaper broad sweeps where medium instances may skip.

## Full Curriculum Command

Run this from the repository root when ready to collect traces for all accepted curriculum instances:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --output-root outputs/phase3_curriculum_traces
```

Expected signal: the script prints a JSON summary with `output_root`, `trace_dir`, `input_instance_count`, `extracted_trace_count`, `attempt_status_summary`, and the Phase 3 generation report.
During the run, stderr should continuously show progress records such as `attempt_started` and `attempt_finished` with `attempt_number`, `total_attempts`, `domain`, `instance_id`, `planner`, and `status`.

## Smoke Command

Run this first if you want a cheap validation before the full job:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id blocksworld-dev-easy-0004 --output-root tmp/phase3_curriculum_trace_dataset_smoke
```

Expected signal from the verified smoke run: `input_instance_count: 1`, `extracted_trace_count: 4`, and `attempt_status_summary: {"success_full_trace": 4}`.

## Useful Filters

Generate one domain only:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --domain blocksworld --output-root outputs/phase3_curriculum_traces_blocksworld
```

Generate a small sample:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --limit 10 --output-root tmp/phase3_curriculum_trace_dataset_sample
```

Generate only selected planners:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --planner ff --planner iw --output-root outputs/phase3_curriculum_traces_ff_iw
```

Generate the focused `blocksworld-train-medium-0011` four-trace rerun:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id blocksworld-train-medium-0011 --planner gbfs --planner ff --planner iw --planner graphplan --output-root tmp/phase3_bwm0011_all_local_verify --quiet
```

Expected signal: `extracted_trace_count: 4` and `attempt_status_summary: {"success_full_trace": 4}`.

The focused command is also covered by a subprocess regression:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_blocksworld_medium_traces.py::test_blocksworld_medium_0011_curriculum_trace_cli_defaults_emit_all_planner_traces
```

Expected signal: the CLI exits 0, reports four `success_full_trace` attempts, and writes four planner trace files.

## Verification Performed

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/generate_curriculum_trace_dataset.py
```

Expected signal: exit code `0` with no output.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_curriculum_trace_dataset.py --instance-id blocksworld-dev-easy-0004 --output-root tmp/phase3_curriculum_trace_dataset_smoke
```

Expected signal: four extracted traces and four `success_full_trace` attempts.

## Hang Fix Verification

The local Graphplan implementation now applies `local_max_applicable_actions` during serial extraction before successor expansion, caches sorted grounded actions once per request, and honors `local_graphplan_max_expansions` separately from active GBFS. Regression coverage:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_phase3_pipeline_regressions.py::test_graphplan_extraction_enforces_applicable_action_cap tests/phase3/test_phase3_pipeline_regressions.py::test_graphplan_extraction_uses_graphplan_specific_expansion_cap tests/phase3/test_phase3_pipeline_regressions.py::test_generate_supervised_data_reports_planner_progress
```

Expected signal: `3 passed`.
