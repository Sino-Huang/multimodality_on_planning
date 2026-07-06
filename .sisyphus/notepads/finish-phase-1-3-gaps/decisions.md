# Decisions

## 2026-06-24 Start Work
- Use current project directory; no worktree was requested.
- Replaced stale boulder state for `curriculum-pddl-instance-generation` because that plan has no unchecked top-level tasks.
- Active boulder plan is now `finish-phase-1-3-gaps`.
- Apply plan defaults unless implementation discovers a blocker: deterministic symbolic world model v0, direct Python benchmark loop, local experts, no Phase 4 model training.

## 2026-06-24 Task 1 Scope Lock
- Documented the Phase 1-3 acceptance boundary as Blocksworld-only P0, while keeping 15-domain curriculum support future-compatible but outside acceptance scope.
- Locked the decision IDs checked by tests: `blocksworld_p0_scope_decision`, `algorithm_matrix_decision`, `modality_matrix_decision`, `planimation_role_decision`, `frozen_world_model_decision`, `artifact_policy_decision`, and `zero_shot_gate_decision`.
- Kept Planimation as offline rendering and visualization only. Local deterministic symbolic Blocksworld code remains the environment authority for later tasks.

## 2026-06-24 Task 2 Blocksworld Core
- Kept the parser deliberately narrow: Blocksworld STRIPS with exactly `pickup`, `putdown`, `stack`, and `unstack`; malformed PDDL and missing/extra action vocabulary fail validation instead of falling back to broad PDDL behavior.
- Validation emits JSON stdout for `--json` on both success and structured failure, plus a concise stderr error line on failure for shell visibility.
- Minimum plan length validation uses local deterministic BFS over the symbolic transition system, not Planimation, external solvers, or generated curriculum data.

## 2026-06-24 Task 3 Zero-Shot Diagnostic
- Defined algorithm and modality constants once in `examples/planning_benchmark_slice/zero_shot.py` to avoid drift across builder, scorer, tests, and future serializers.
- Kept model-facing prompt content and evaluator-only `gold_scoring_metadata` as sibling top-level fields so hidden state IDs, legal actions, and scoring contracts are never mixed into the prompt boundary accidentally.
- Used minimal deterministic algorithm-fidelity contracts for the diagnostic gate: BFS requires FIFO queue/dequeue/enqueue terms, Fast Forward requires delete-relaxation heuristic/greedy terms, Iterated Width requires novelty/width/new terms, and Graphplan requires proposition/layer/mutex terms.

## 2026-06-24 Task 4 Benchmark Loop
- Chose direct Python as the Phase 2 P0 loop decision and documented that WebSocket/server-client evaluation is not required for Task 4.
- Kept invalid action failures under the code `illegal_action` for both malformed canonical action strings and syntactically valid actions that are illegal in the current state, matching the benchmark acceptance contract.
- Step logs store the observation before the action plus pre/post state IDs and terminal status, so later serializers can consume a simple benchmark trace without introducing the Phase 3 trajectory schema early.

## 2026-06-24 Task 5 Unified Expert Trajectory Schema
- Chose a namespaced schema shape where shared fields stay at the record root and planner-state annotations live under the exact algorithm key (`bfs`, `fast_forward`, `iterated_width`, `graphplan`). This keeps missing-field errors concise and avoids mixing algorithm internals into shared fields.
- Implemented deterministic canonicalization helpers for atoms, legal actions, novelty tables, mutex pairs, BFS frontier/visited lists, successors, heuristic successors, and Graphplan layers so future expert generators can produce byte-stable JSON.
- Kept `examples.planning_benchmark_slice.__main__` untouched, preserving the legacy default package CLI while adding `validate_trajectories` as a sibling module.
- Correction: BFS `frontier_before` and `frontier_after` are FIFO queues, so canonicalization must preserve their exact list order. Determinism for frontier fields must come from deterministic generation order, while set-like BFS fields such as `visited_before` and `visited_after` may still be sorted.

## 2026-06-24 Task 6 BFS and IW Experts
- Generated expert trajectories as one JSON file per algorithm with Task 5 step records under `steps`; the generator summary reports one trajectory per algorithm while the validator counts the individual step records.
- BFS traces preserve FIFO `frontier_before`/`frontier_after` order from deterministic `BlocksworldProblem.legal_actions()` expansion and sort only set-like fields such as `visited_before` and `visited_after`.
- Iterated Width starts with width `k=1` for the Phase 1-3 Blocksworld fixture, records atoms/tuples plus novelty table before/after, and uses the same canonical legal-action ordering as the action tie-break.
- `generate_experts` intentionally supports only `bfs` and `iterated_width` for Task 6; `fast_forward` and `graphplan` fail with a structured unsupported-algorithm error for future tasks.

## 2026-06-24 Task 7 Fast Forward-Style Expert
- Implemented a documented P0 approximation named `deterministic_p0_hmax_relaxed_reachability`, not exact Fast Downward FF or full Hoffmann-Nebel relaxed-plan extraction.
- The approximation grounds the four Blocksworld operators, ignores delete effects during relaxed reachability, propagates h-max-style atom costs, and uses the deterministic supporter-action closure size as the heuristic value.
- Greedy successor selection is deterministic: sort every legal successor by lowest heuristic value, then by canonical action string (`min_heuristic_then_action_lexicographic`).

## 2026-06-24 Task 8 Graphplan Expert
- Implemented P0 Graphplan as deterministic Blocksworld proposition/action layer construction with explicit action-level mutex pairs only, matching the proposal feasibility simplification.
- Proposition layers are built from the union of concrete successor states for applicable actions, preserving the Task 5 valid fixture convention where the first initial-state layer contains `holding(a)`, `holding(b)`, and `holding(c)` but not `arm-empty`.
- Extraction metadata records `approximation=deterministic_p0_action_mutex_only_graphplan`, `mutex_scope=action_level_only`, `proposition_mutex_computed=false`, and selected successor IDs rather than claiming full Graphplan proposition-mutex/backward extraction.

## 2026-06-24 Task 9 Modality Serializers
- Kept modality records split into `model_facing`, `supervised_target`, and `evaluation_metadata`; only `model_facing` is prompt input.
- Vision-only prompts include render references or a skip reason but omit state IDs, PDDL/symbolic atoms, legal actions, and gold labels.
- Tool scratchpads copy algorithm-specific planner fields but recursively remove `selected_action` before entering `model_facing`; the gold next action remains in `supervised_target` and evaluator metadata.

## 2026-06-24 Task 10 StarVLA Registry
- Registered the Task 9 smoke JSONL files directly as mixture dataset entries instead of converting to LeRobot parquet, because Task 10 acceptance is registry auto-discovery only and explicitly excludes full training conversion or continuous action tensors.
- Kept `planning_blocksworld` on `EmbodimentTag.NEW_EMBODIMENT`, matching StarVLA's safe default for new/non-robot embodiments.
- Added optional-dependency guards to registry/package import paths so the exact `.venv` registry smoke can import `starVLA.dataloader.gr00t_lerobot.registry` without installing training dependencies; full environments still load the original configs when dependencies are present.

## 2026-06-24 Task 11 Documentation Closeout
- Kept the docs checker narrow and deterministic instead of adding a broad markdown linter. It checks only Phase 1-3 closeout documents, required evidence paths, and no-Phase-4-overclaim caveats.
- Marked Phase 1, Phase 2, and Phase 3 complete only for Blocksworld-only P0 in `doc/high_level_plans/research_execution_plan.md`; Phase 4 remains explicitly not complete.
- Documented generated smoke outputs under `outputs/planning_artifacts/**` as reproducible local artifacts that should not be committed as large generated data unless explicitly requested.
