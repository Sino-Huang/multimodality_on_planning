# CGAS Qwen-VL Todo 5 Strict Conversion

- Todo 5 Qwen conversion should consume only `verify_steps()`-accepted `planning_cgas_v1` steps and emit one native Qwen JSONL row per accepted step.
- The human turn allowlist is exactly `domain`, `planner`, and `task_text`, prefixed by exactly one `<image>` token.
- Target-only denied fields are `route_label`, `planner_trace`, and `replay_transitions`; reject them in human payloads and in `model_input` before writing output.
- Assistant targets are parseable canonical JSON with only `action` and `certificate`.
- Dedicated Qwen dataset nicknames are `planning_cgas_v1_train` and `planning_cgas_v1_dev`; do not register `planning_cgas_v1_test`.
- Manual QA evidence for the current implementation is under `.omo/evidence/task-5-cgas-dataloader-and-experiment-support/manual-qa-20260730182736/`.
