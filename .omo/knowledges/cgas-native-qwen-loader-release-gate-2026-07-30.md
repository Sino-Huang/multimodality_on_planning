# CGAS Native Qwen Loader Release Gate

- `LazySupervisedDataset.__getitem__` can retry the next row after a loader failure, so CGAS strict preflight must run `_build_messages()` and `preprocess_qwen_visual()` directly against every JSONL record before dataset construction.
- The Qwen row `id` is the originating `step_id`; native tensor batches do not preserve it, so preflight reports must record `checked_step_ids` and compare them with the Qwen manifest split `ids`.
- Fail-closed release publication should bind source, alignment, steps, Qwen, and loader-preflight artifacts in `release_manifest.json`, and should preserve any prior approved release on a failed prerequisite.
- User-site `huggingface-hub 1.22.0` can still shadow the conda env even after compatible `huggingface-hub==0.36.2` is installed in `ada_vla`; run real Qwen/Transformers commands as `source ~/cd_vlaplan && PYTHONNOUSERSITE=1 ...`.
- In this checkout `./playground/Pretrained_models/Qwen2.5-VL-3B-Instruct` is absent, so Todo 6 real-processor verification used the matching repo default model ID `Qwen/Qwen2.5-VL-3B-Instruct`.
- The accepted 2026-07-31 release evidence has 12 checked/emitted rows, zero strict preflight counters, loader batch `pixel_values` and `image_grid_thw` present, and `data/planning_cgas_v1/release_manifest.json` SHA-256 `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`.
