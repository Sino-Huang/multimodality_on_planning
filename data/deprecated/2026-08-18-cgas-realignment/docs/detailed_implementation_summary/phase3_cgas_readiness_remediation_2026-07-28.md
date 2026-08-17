# Phase 3 CGAS Readiness Remediation

Date: 2026-07-28

## Summary

The CGAS readiness snapshot now fails closed when the historical BFS success
count is absent. The checked-in absent IW success count remains an explicit
zero because it represents the known current corpus state. The planning smoke
artifacts were regenerated from the documented fixture pipeline, and DOMINO
now has a unique dynamic registry type while DOMINO co-training retains the
RoboTwin-owned static type.

## Changes

- `scripts/phase3/cgas_readiness_snapshot.py` rejects a missing
  `planner_status_summary.bfs.success_full_trace` with a field-specific
  `InputContractError` before it creates output.
- `tests/phase3/test_cgas_readiness_snapshot.py` verifies the malformed nested
  BFS field causes a nonzero subprocess result and leaves no output file.
- `examples/DOMINO/train_files/data_registry/data_config.py` uses `domino` for
  DOMINO dynamic data and retains `robotwin` for RoboTwin static co-training.
- `tests/planning_benchmark/test_dataset_registry.py` asserts that dynamic and
  co-training robot type ownership remains distinct.

## Commands

Regenerate the ignored planning smoke artifacts:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.generate_experts --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms bfs fast_forward iterated_width graphplan --output outputs/planning_artifacts/expert_smoke --json
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.serialize_modalities --input outputs/planning_artifacts/expert_smoke --output outputs/planning_artifacts/dataset_smoke --modalities vision language vision_language vision_language_tool --json
```

Run the focused acceptance suite:

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_readiness_snapshot.py tests/planning_benchmark/test_dataset_registry.py
```

Expected result: `11 passed`.

Run the snapshot surface:

```bash
source ~/cd_vlaplan && python -m scripts.phase3.cgas_readiness_snapshot --output-path /tmp/cgas-readiness-snapshot.json
```

Expected facts: `current_bfs_examples` is `411`, `current_iw_examples` is `0`,
and `observation.status` is `observed_not_ready`.

## Verification

- The new regression was red before the production fix: the malformed BFS
  summary exited zero and wrote output.
- Focused verification passed with `11 passed`.
- Static diagnostics were clean for all changed Python files.
- The canonical generators produced four JSONL files with eight records each.
- The broad `tests/phase3 tests/planning_benchmark` sweep remains blocked by
  unrelated pre-existing collection failures, including missing
  `VIEW_ROOT` and test-support imports.
