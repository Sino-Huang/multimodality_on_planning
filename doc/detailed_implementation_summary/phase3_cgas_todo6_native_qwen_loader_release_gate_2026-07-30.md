# Phase 3 CGAS Todo 6 Native Qwen Loader And Release Gate

Todo 6 adds a strict row-by-row Qwen loader preflight and a fail-closed release gate for `planning_cgas_v1`.

Implementation:

- `scripts/phase3/cgas_qwenvl_preflight.py` reads every emitted Qwen row, preserves the row `id` as `step_id`, calls the native loader message builder and tokenization path before constructing `LazySupervisedDataset`, and reports identity, message, tokenization, assistant-label, image-tensor, and image-grid counters.
- The same module exposes `loader_batch_smoke()` for the registered `planning_cgas_v1_train` alias using `LazySupervisedDataset` plus `DataCollatorForSupervisedDataset`.
- `scripts/phase3/cgas_release_gate.py` verifies source provenance, persisted alignment, certificates, Qwen conversion, and strict loader preflight before atomically publishing `release_manifest.json`.
- Release publication short-circuits on the first failed prerequisite so dependent failures do not hide the root failed report.

Commands used:

```bash
source ~/cd_vlaplan && PYTHONNOUSERSITE=1 python -m pytest -q tests/phase3/test_cgas_qwenvl_preflight.py tests/phase3/test_cgas_release_gate.py
source ~/cd_vlaplan && PYTHONNOUSERSITE=1 basedpyright scripts/phase3/cgas_qwenvl_preflight.py scripts/phase3/cgas_release_gate.py tests/phase3/test_cgas_qwenvl_preflight.py tests/phase3/test_cgas_release_gate.py
source ~/cd_vlaplan && PYTHONNOUSERSITE=1 python -m compileall -q scripts/phase3/cgas_qwenvl_preflight.py scripts/phase3/cgas_release_gate.py tests/phase3/test_cgas_qwenvl_preflight.py tests/phase3/test_cgas_release_gate.py
source ~/cd_vlaplan && PYTHONNOUSERSITE=1 python -m scripts.phase3.cgas_qwenvl_preflight --qwenvl-root data/planning_cgas_v1/qwenvl --image-root data/planning_cgas_v1/qwenvl/images --processor Qwen/Qwen2.5-VL-3B-Instruct --loader-smoke
source ~/cd_vlaplan && PYTHONNOUSERSITE=1 python -m scripts.phase3.cgas_release_gate --corpus-root data/planning_cgas_v1 --preflight-report .omo/evidence/task-6-cgas-dataloader-and-experiment-support/preflight.json
```

Manual QA evidence:

- `.omo/evidence/task-6-cgas-dataloader-and-experiment-support/preflight.json`
- `.omo/evidence/task-6-cgas-dataloader-and-experiment-support/loader-batch.json`
- `.omo/evidence/task-6-cgas-dataloader-and-experiment-support/corrupt-row.txt`
- `.omo/evidence/task-6-cgas-dataloader-and-experiment-support/release-refusal.txt`
- `.omo/evidence/task-6-cgas-dataloader-and-experiment-support/release-gate.txt`
- `data/planning_cgas_v1/release_manifest.json`

Environment fix and real processor result:

The earlier blocker was user-site `huggingface-hub 1.22.0` shadowing the confirmed `ada_vla` conda environment. Root installed compatible `huggingface-hub==0.36.2` in the conda environment; because the incompatible user-site package still exists, every real `transformers`/`AutoProcessor` command for this gate must include `PYTHONNOUSERSITE=1` after `source ~/cd_vlaplan`.

The repo-referenced local processor path `./playground/Pretrained_models/Qwen2.5-VL-3B-Instruct` is absent in this checkout, so the real smoke used the matching repository default model ID `Qwen/Qwen2.5-VL-3B-Instruct`. The strict preflight accepted all 12 emitted rows, reported zero identity/message/tokenization/empty-label/null-image/null-grid counters, and the registered loader/collator batch reported `pixel_values_non_null=true`, `image_grid_thw_non_null=true`, and 556 assistant label tokens. The release gate then published `data/planning_cgas_v1/release_manifest.json` with SHA-256 `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`.
