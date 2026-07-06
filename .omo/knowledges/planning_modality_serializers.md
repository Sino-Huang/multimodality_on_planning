# Planning Modality Serializers

- Task 9 modality serialization lives in `examples/planning_benchmark_slice/modality_serializers.py` with CLI wrapper `serialize_modalities.py`.
- Inputs are Task 5 expert trajectory JSON/JSONL files loaded via `load_trajectory_records` and validated before serialization.
- Outputs are deterministic modality JSONL files named `vision.jsonl`, `language.jsonl`, `vision_language.jsonl`, and `vision_language_tool.jsonl`.
- Record boundary convention: `model_facing` is prompt input only; `supervised_target` holds `next_action` and `internal_state_update`; `evaluation_metadata` holds state IDs, atoms, legal actions, and source details.
- Vision-only leakage checks reject symbolic/PDDL/gold fields and SHA-256 state IDs in `model_facing`; language-only checks reject render/image/frame fields and path-like visual text.
- Tool modality copies algorithm scratchpads while stripping nested `selected_action` keys from `model_facing`.
