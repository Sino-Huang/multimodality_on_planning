# Learnings

## 2026-06-24 Start Work
- Active plan: `.sisyphus/plans/finish-phase-1-3-gaps.md`.
- P0 scope must remain Blocksworld-only for Phase 1-3 closure.
- Existing Planimation/curriculum/planning-slice tests are baseline safeguards and must keep passing.
- Raw PDDL/domain/problem files do not count as expert demonstrations.
- Empty-goal Blocksworld instances must be rejected before zero-shot or expert generation.

## 2026-06-24 Task 1 Scope Lock
- The scope-lock checker is intentionally term based, not prose-format based. It validates explicit decision IDs in `doc/detailed_implementation_summary/phase1_scope_lock_and_diagnostic_summary.md`.
- `python -m examples.planning_benchmark_slice.scope_lock validate --path <artifact> --json` keeps the existing planning slice CLI convention: JSON stdout on success, clear stderr on validation failure, nonzero exit for missing decisions.
- The negative fixture `tests/fixtures/planning/scope_lock_missing_world_model.md` is fresh-checkout safe and does not depend on `data/curriculum_pddl/**`.

## 2026-06-24 Task 2 Blocksworld Core
- The Task 2 symbolic core lives in sibling modules under `examples/planning_benchmark_slice/` and does not modify the existing default `python -m examples.planning_benchmark_slice` JSON contract.
- Canonical Blocksworld atoms are strings such as `arm-empty`, `clear(a)`, `on-table(a)`, and `on(a,b)`; state IDs are SHA-256 hashes over sorted JSON atom lists, making them independent of PDDL atom order.
- The committed non-trivial fixture `tests/fixtures/planning/blocksworld_nontrivial.json` has shortest local symbolic plan length 2: `pickup(a)` then `stack(a,b)`.

## 2026-06-24 Task 3 Zero-Shot Diagnostic
- Zero-shot prompt packages live in separate modules (`zero_shot.py`, `zero_shot_build.py`, `zero_shot_diagnostic.py`) and preserve the legacy `python -m examples.planning_benchmark_slice` facade.
- The builder uses the Task 2 validator/parser and emits deterministic package IDs from the fixture `instance_id`, algorithm, and modality, e.g. `blocksworld-dev-fixture-0000__bfs__vision`.
- Offline scoring follows the proposal priority order: unparseable or schema-invalid output is `Parse Error`; syntactically valid illegal actions are `Action Error`; legal actions with missing algorithm contract terms are `Algorithmic Error`; all criteria true is `Pass`.

## 2026-06-24 Task 4 Benchmark Loop
- The benchmark loop lives in `examples/planning_benchmark_slice/benchmark_loop.py` as a sibling CLI module, preserving the default `python -m examples.planning_benchmark_slice` output contract.
- `BlocksworldBenchmarkLoop` exposes a small reset/observe/step interface over the Task 2 symbolic core. Observations use `planning_benchmark_observation_v1` with state atoms, state IDs, goals, and legal actions.
- The oracle baseline recomputes deterministic local BFS over `BlocksworldProblem.legal_actions()` and `transition()`; the non-trivial fixture solves with `pickup(a)` then `stack(a,b)`.

## 2026-06-24 Task 5 Unified Expert Trajectory Schema
- Canonical expert trajectory records are step-level JSON/JSONL objects grouped by `trajectory_id`; they are not model-training conversations or modality-specific serializer outputs.
- The validator accepts either a single `.json`/`.jsonl` file or a directory tree of trajectory files and emits deterministic sorted JSON reports.
- Required algorithm namespaces are `bfs`, `fast_forward`, `iterated_width`, and `graphplan`; missing fields report assertable paths such as `bfs.frontier_before`.
- Valid committed fixtures under `tests/fixtures/planning/trajectories/valid/` cover all four locked algorithms, with the IW fixture intentionally stored as JSONL to exercise both input formats.

## 2026-06-24 Task 6 BFS and IW Experts
- The non-trivial Blocksworld fixture generates deterministic BFS and IW selected actions `pickup(a)` then `stack(a,b)`, matching the Task 4 oracle shortest plan.
- `python -m examples.planning_benchmark_slice.generate_experts --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms bfs iterated_width --output <dir> --json` writes `blocksworld-dev-fixture-0000__bfs.json` and `blocksworld-dev-fixture-0000__iterated_width.json`.
- Generated BFS/IW files validate through `python -m examples.planning_benchmark_slice.validate_trajectories --input <dir> --json`; for the non-trivial fixture the validator reports two BFS records and two IW records.
- Byte determinism was verified by comparing two fresh `/tmp` output directories with `diff -r`; no output path or timestamp is embedded in generated trajectory JSON.

## 2026-06-24 Task 7 Fast Forward-Style Expert
- The Fast Forward-style expert is registered as `fast_forward` in `examples/planning_benchmark_slice/experts/__init__.py` while `graphplan` remains unsupported for Task 8.
- The non-trivial fixture generates two Fast Forward records with selected actions `pickup(a)` then `stack(a,b)`, and validates through the Task 5 trajectory validator with `by_algorithm.fast_forward=2`.
- The Fast Forward namespace records `heuristic_value`, `successor_heuristics`, `selected_successor_id`, `selected_action`, `tie_break_rule`, `relaxed_plan_metadata`, and `failure_reason` for each generated step.

## 2026-06-24 Task 8 Graphplan Expert
- The Graphplan expert is registered as `graphplan` in `examples/planning_benchmark_slice/experts/__init__.py` and generated by the shared `generate_experts` CLI alongside BFS/IW/Fast Forward.
- Generated Graphplan trajectories for the non-trivial fixture select `pickup(a)` then `stack(a,b)` and validate as two Task 5 step records under `planning_expert_trajectory_v1`.
- The smoke summary now reports Graphplan-specific `layer_count`, `mutex_pair_count`, and per-step `goal_present_without_mutex` statuses so evidence can assert layer/mutex generation without opening the trajectory file.

## 2026-06-24 Task 9 Modality Serializers
- `serialize_modalities` consumes Task 5 `generate_experts` JSON/JSONL trajectory records through `load_trajectory_records` and validates them before writing modality JSONL files.
- The required smoke fixture produces 8 expert steps total (2 per algorithm) and serializer output has 8 records per modality, 32 records total.
- Vision-bearing records now report machine-readable `no_render_artifacts` skip reasons when source trajectories do not reference render paths, rather than fabricating images.

## 2026-06-24 Task 10 StarVLA Registry
- StarVLA auto-discovers benchmark registry files from `examples/*/train_files/data_registry/data_config.py` and merges top-level `ROBOT_TYPE_CONFIG_MAP` and `DATASET_NAMED_MIXTURES` into `starVLA.dataloader.gr00t_lerobot.registry` on import.
- The planning smoke registry uses robot type `planning_blocksworld` and mixture `planning_blocksworld_dev_smoke`, with four repo-relative JSONL entries under `outputs/planning_artifacts/dataset_smoke/`.
- In the local `.venv`, registry-only imports need to skip training configs whose optional dependencies (`torch`, `numpy`, `pydantic`, etc.) are absent; the planning registry therefore has lightweight fallbacks for modality config and no-op transform objects.

## 2026-06-24 Task 11 Documentation Closeout
- `examples.planning_benchmark_slice.docs_check` validates Phase 1-3 closeout docs by checking existing evidence paths plus required caveat/status phrases.
- The new Phase 3 summary is `doc/detailed_implementation_summary/phase3_expert_trajectories_summary.md`; it separates expert trajectories from the older 15-domain curriculum PDDL generation summary.
- Required Task 11 evidence files are `.sisyphus/evidence/phase1-3-task-11-docs-check.json` and `.sisyphus/evidence/phase1-3-task-11-no-overclaim.json`, both with `valid=true`.
