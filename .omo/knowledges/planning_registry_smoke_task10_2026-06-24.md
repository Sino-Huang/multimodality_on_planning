# Planning registry smoke conventions

- StarVLA registry auto-discovery scans `examples/*/train_files/data_registry/data_config.py` and merges top-level `ROBOT_TYPE_CONFIG_MAP`, optional legacy `ROBOT_TYPE_TO_EMBODIMENT_TAG`, and `DATASET_NAMED_MIXTURES` into `starVLA.dataloader.gr00t_lerobot.registry` at import time.
- The Phase 1-3 planning smoke dataset is registered in `examples/planning_benchmark_slice/train_files/data_registry/data_config.py` as robot type `planning_blocksworld` and mixture `planning_blocksworld_dev_smoke`.
- The planning mixture intentionally points to repo-relative Task 9 JSONL artifacts under `outputs/planning_artifacts/dataset_smoke/`: `language.jsonl`, `vision.jsonl`, `vision_language.jsonl`, and `vision_language_tool.jsonl`.
- For lightweight registry smoke environments that lack training dependencies, keep registry-only imports free of hard `torch`/`numpy`/`pydantic` requirements. The full training path should still load real StarVLA configs when those dependencies are installed.
- Required smoke command:
  `source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY' ... import DATASET_NAMED_MIXTURES, ROBOT_TYPE_CONFIG_MAP ... PY`
