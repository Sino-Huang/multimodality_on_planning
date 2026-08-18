# Phase 3 CGAS Todo 5 Strict Qwen-VL Conversion

Todo 5 now keeps Qwen conversion fail-closed at the model-input boundary. The converter rejects target-only fields such as `route_label`, `planner_trace`, and `replay_transitions` when they appear in the future model input before emitting a Qwen row. The focused conversion test fixture now rebuilds current authoritative source, alignment, and step roots from the Todo 2-4 builders so stale fixture identities do not mask Todo 5 regressions.

The Qwen registry exposes only the dedicated train/dev aliases:

- `planning_cgas_v1_train` -> `./data/planning_cgas_v1/qwenvl/train.jsonl`
- `planning_cgas_v1_dev` -> `./data/planning_cgas_v1/qwenvl/dev.jsonl`

Both use `./data/planning_cgas_v1/qwenvl/images` as the dedicated image `data_path`. `planning_cgas_v1_test` remains unregistered.

Commands used:

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_qwenvl_conversion.py tests/planning_benchmark/test_dataset_registry.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_qwenvl.py scripts/phase3/cgas_qwenvl_contracts.py tests/phase3/test_cgas_qwenvl_conversion.py starVLA/dataloader/qwenvl_llavajson/qwen_data_config.py tests/planning_benchmark/test_dataset_registry.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_qwenvl.py scripts/phase3/cgas_qwenvl_contracts.py tests/phase3/test_cgas_qwenvl_conversion.py starVLA/dataloader/qwenvl_llavajson/qwen_data_config.py tests/planning_benchmark/test_dataset_registry.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_qwenvl --source-root .omo/evidence/task-5-cgas-dataloader-and-experiment-support/manual-qa-20260730182736/source --alignment-root .omo/evidence/task-5-cgas-dataloader-and-experiment-support/manual-qa-20260730182736/alignment --corpus-root .omo/evidence/task-5-cgas-dataloader-and-experiment-support/manual-qa-20260730182736/corpus
source ~/cd_vlaplan && python -m scripts.phase3.cgas_qwenvl --verify --source-root .omo/evidence/task-5-cgas-dataloader-and-experiment-support/manual-qa-20260730182736/source --alignment-root .omo/evidence/task-5-cgas-dataloader-and-experiment-support/manual-qa-20260730182736/alignment --corpus-root .omo/evidence/task-5-cgas-dataloader-and-experiment-support/manual-qa-20260730182736/corpus
```

Evidence root: `.omo/evidence/task-5-cgas-dataloader-and-experiment-support/manual-qa-20260730182736/`.
