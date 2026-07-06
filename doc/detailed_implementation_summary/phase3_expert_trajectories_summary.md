# Phase 3 Expert Trajectories and Modality Closeout Summary

## Scope

This closeout covers the Blocksworld-only P0 Phase 3 path for expert trajectory generation, modality serialization, and StarVLA registry smoke integration. It is evidence for the proposal-aligned Phase 3 demonstration pipeline, not for Phase 4 model training.

The locked Phase 1-3 acceptance scope remains Blocksworld-only P0. The 15-domain curriculum PDDL work in `doc/detailed_implementation_summary/phase2_curriculum_pddl_generation_summary.md` documents curriculum generation for future expansion. It is not itself proof of Phase 3 expert demonstrations.

## Implemented expert families

The expert trajectory pipeline writes step-level JSON or JSONL records with algorithm-specific namespaces. Raw PDDL files, final plans only, and Planimation traces alone do not count as expert demonstrations.

Implemented P0 families:

- `bfs`, deterministic breadth first search with FIFO frontier and visited-state fields.
- `fast_forward`, a documented P0 approximation named `deterministic_p0_hmax_relaxed_reachability`.
- `iterated_width`, deterministic novelty-based exploration with novelty table fields.
- `graphplan`, a documented P0 simplification named `deterministic_p0_action_mutex_only_graphplan` with action mutexes only.

The Fast Forward implementation is not exact Fast Downward FF. The Graphplan implementation is not full Hoffmann-Nebel Graphplan with proposition mutexes and complete backward extraction.

## Unified trajectory schema

The shared schema is `planning_expert_trajectory_v1`. Common fields stay at the record root, and planner-state annotations live under the exact algorithm key: `bfs`, `fast_forward`, `iterated_width`, or `graphplan`.

Verification command:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.validate_trajectories --input outputs/planning_artifacts/expert_smoke --json
```

Expected signal: exit code 0, `valid=true`, and two step records for each of `bfs`, `fast_forward`, `iterated_width`, and `graphplan` when using the committed non-trivial fixture.

Evidence:

- `.sisyphus/evidence/phase1-3-task-5-schema-valid.json`
- `.sisyphus/evidence/phase1-3-task-5-schema-error.json`
- `.sisyphus/evidence/phase1-3-task-6-bfs-iw.json`
- `.sisyphus/evidence/phase1-3-task-7-validator.json`
- `.sisyphus/evidence/phase1-3-task-8-validator.json`

## Generation command

The combined expert smoke path is:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.generate_experts --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms bfs fast_forward iterated_width graphplan --output outputs/planning_artifacts/expert_smoke --json
```

Expected signal: exit code 0, `valid=true`, one generated trajectory file per algorithm, and selected actions `pickup(a)` then `stack(a,b)` for the committed fixture.

Observed evidence:

- `.sisyphus/evidence/phase1-3-task-6-bfs-iw.json`
- `.sisyphus/evidence/phase1-3-task-6-determinism.txt`
- `.sisyphus/evidence/phase1-3-task-7-ff.json`
- `.sisyphus/evidence/phase1-3-task-7-tiebreak.txt`
- `.sisyphus/evidence/phase1-3-task-8-graphplan.json`
- `.sisyphus/evidence/phase1-3-task-8-mutex.txt`

## Modality serializers

Task 9 serializes expert records into the four locked modalities: `vision`, `language`, `vision_language`, and `vision_language_tool`.

The record boundary is explicit:

- `model_facing` is the only prompt input.
- `supervised_target` contains gold next-action and internal-state targets.
- `evaluation_metadata` contains evaluator-only state and provenance.

Vision-only examples must not leak symbolic state IDs, PDDL, legal actions, or selected actions into `model_facing`. Language-only examples must not include render or image paths. Vision-bearing examples may report `no_render_artifacts` when smoke trajectories lack image files, instead of fabricating images.

Verification command:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.serialize_modalities --input outputs/planning_artifacts/expert_smoke --output outputs/planning_artifacts/dataset_smoke --modalities vision language vision_language vision_language_tool --json
```

Expected signal: exit code 0, `valid=true`, `record_count=32`, no leakage errors, and 8 records per modality.

Evidence:

- `.sisyphus/evidence/phase1-3-task-9-serialize.json`
- `.sisyphus/evidence/phase1-3-task-9-vision-leakage.txt`

## StarVLA registry smoke

Task 10 registers the planning smoke dataset through StarVLA auto-discovery. It registers robot type `planning_blocksworld` and mixture `planning_blocksworld_dev_smoke` from `examples/planning_benchmark_slice/train_files/data_registry/data_config.py`.

Verification command:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
from starVLA.dataloader.gr00t_lerobot.registry import DATASET_NAMED_MIXTURES, ROBOT_TYPE_CONFIG_MAP
assert "planning_blocksworld_dev_smoke" in DATASET_NAMED_MIXTURES
assert "planning_blocksworld" in ROBOT_TYPE_CONFIG_MAP
print("planning dataset registry smoke passed")
PY
```

Expected and observed output:

```text
planning dataset registry smoke passed
```

Evidence:

- `.sisyphus/evidence/phase1-3-task-10-registry.txt`
- `.sisyphus/evidence/phase1-3-task-10-registry-collision.txt`

## Artifact policy

Generated smoke outputs under `outputs/planning_artifacts/**` are reproducible local artifacts. Commit small source files, tests, docs, and `.sisyphus/evidence/**` records when requested by the workflow, but do not commit large generated data unless the user explicitly requests it.

## Phase 3 closeout verification

Docs closeout commands:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.docs_check --phase 1 2 3 --json > .sisyphus/evidence/phase1-3-task-11-docs-check.json
```

Expected signal: exit code 0 and JSON with `valid=true`, `phase_results.1.valid=true`, `phase_results.2.valid=true`, and `phase_results.3.valid=true`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.docs_check --no-phase4-claims --json > .sisyphus/evidence/phase1-3-task-11-no-overclaim.json
```

Expected signal: exit code 0 and JSON with `valid=true` and `no_phase4_claims.valid=true`.

## Caveats preserved

- Phase 1-3 closeout is Blocksworld-only P0.
- The benchmark loop is a direct Python loop, not a WebSocket or server-client requirement.
- Planimation is offline rendering and visualization, not environment authority.
- Zero-shot diagnostic packaging and scoring are offline. This closeout does not claim real VLM, GPU, API, or external-service execution.
- No Phase 4 training, model implementation, or SFT run is complete yet.
- `phase2_curriculum_pddl_generation_summary.md` documents curriculum PDDL generation, not Phase 3 expert demonstrations.
