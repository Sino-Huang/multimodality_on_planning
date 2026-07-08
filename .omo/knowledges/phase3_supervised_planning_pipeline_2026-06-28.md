# Phase 3 supervised planning pipeline (2026-06-28)

- Dedicated package: `scripts/phase3/`.
- Main generation command:
  `source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.generate_supervised_data --input-root data/curriculum_pddl --output-root data/phase3_supervised_planning --planners gbfs ff iw graphplan --json`
- Output root: `data/phase3_supervised_planning/` with split JSONL, `generation_manifest.json`, `summary.json`, schemas, diagnostics, and reports.
- Inclusion source: only `data/curriculum_pddl/accepted_manifest.jsonl`; generated records use repo-relative paths.
- Historical generated corpus: 3,600 accepted instances, 14,400 planner attempts, 411 replay-validated BFS `success_full_trace` examples. As of the 2026-07-07 GBFS replacement, active regeneration uses `gbfs`; the old `bfs` planner label is rejected rather than aliased.
- External FF/IW/Graphplan commands are configured by `PHASE3_FF_PLANNER`, `PHASE3_IW_PLANNER`, and `PHASE3_GRAPHPLAN_PLANNER`; FF/IW also probe `modules/downward/fast-downward.py --show-aliases` for FF/IW-style aliases. If no usable command/alias exists, attempts produce `skipped_planner_unavailable` diagnostics.
- Schema validation dispatches by generated schema title (`supervised_planning_example`, `planner_attempt`, `instance_accounting`) and each generated schema validates its corresponding JSONL rows with `invalid_rows = 0`.
- Registry names: `planning_phase3_supervised_jsonl` robot/data type and `planning_phase3_supervised_all` mixture in `examples/planning_benchmark_slice/train_files/data_registry/data_config.py`.
- Verification command bundle is documented in `doc/detailed_implementation_summary/phase3_complete_supervised_planning_data_summary.md`.
