# Phase 3 Pytest Runtime Classification

- `pytest tests/phase3 -vv --durations=0` collects 106 items and stalls at `test_15puzzle_easy_first_ten_curriculum_trace_cli_defaults_emit_all_planner_traces`.
- A 600-second suite timeout and a 180-second isolated timeout both exit `124` without finishing the same node.
- The test launches the 10-instance, four-planner `generate_curriculum_trace_dataset.py` subprocess. Runtime process capture showed nested generator processes and orphaned generator process groups after outer pytest timeout.
- This generator imports `scripts.phase3.pipeline`, not Todo 2 `planimation_pairing`/`trace_contracts`; classify it as an independent pre-existing resource/cleanup issue. Do not alter Todo 2 contracts to address it.
- When reproducing, terminate only process groups created by the current debug run. Existing PPID-1 generators may belong to other sessions.
