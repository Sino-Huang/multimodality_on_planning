# Finish Phase 1-3 Gaps

## TL;DR
> **Summary**: Close the audited Phase 1-3 gaps by turning the existing Planimation/curriculum/reader baseline into a Blocksworld-first research pipeline with scope-lock docs, zero-shot diagnostics, a minimal symbolic benchmark loop, algorithm-specific expert trajectories, modality serializers, and StarVLA data registration.
> **Deliverables**:
> - Phase 1 scope-lock + zero-shot diagnostic gate + frozen symbolic world-model decision.
> - Phase 2 benchmark-quality Blocksworld core and in-process benchmark loop.
> - Phase 3 BFS / Fast Forward / Iterated Width / Graphplan expert traces with modality serialization and dataset registration.
> - Tests, CLI smoke commands, evidence files, and detailed implementation summaries.
> **Effort**: Large
> **Parallel**: YES - 4 waves
> **Critical Path**: Task 1 → Task 2 → Task 3 → Tasks 5-8 → Task 9 → Task 10

## Context

### Original Request
User asked: "produce a plan to finish the gap in Phase 1-3" after a repo audit found Phase 1 incomplete, Phase 2 partial, and Phase 3 incomplete.

### Interview Summary
- No further user decisions are blocking; defaults below are applied to keep implementation narrow and verifiable.
- Phase 1 existing strength: Planimation corpus and rendering validation are implemented and tested.
- Phase 2 existing strength: `examples/planning_benchmark_slice` can load a real Blocksworld curriculum instance and emit PDDL/render/text views.
- Phase 3 existing strength: curriculum PDDL generation and merged dataset plumbing exist.
- Main missing work: explicit scope lock, zero-shot diagnostic gate, frozen world-model decision, non-trivial benchmark instance validation, benchmark loop, algorithm-specific expert trajectories, modality serializers, and StarVLA dataset registration.

### Metis Review (gaps addressed)
- Guard against treating raw PDDL/domain/problem files as expert demonstrations.
- Reject empty-goal and already-solved Blocksworld instances before diagnostics or expert generation.
- Keep Phase 1-3 acceptance Blocksworld-only; do not require all 15 curriculum domains.
- Separate zero-shot packaging/scoring from optional real-model execution.
- Require planner-state annotations for every expert trajectory.
- Use StarVLA's existing data registry discovery path instead of forking training loops.

### Oracle Review (architecture guardrails)
- P0 must be Blocksworld-first, not a general planning-platform buildout.
- Use a deterministic symbolic "world model v0" for Phase 1-3: canonical atoms, objects, legal actions, transitions, goals, state IDs, and render references.
- Planimation is an offline rendering source, not the environment authority.
- Expert generators should be local Blocksworld implementations for P0 unless local correctness proves insufficient.
- Artifact tests must not rely on large uncommitted `data/curriculum_pddl/**` outputs without fixture or generation fallback.

## Work Objectives

### Core Objective
Make Phases 1-3 of `doc/high_level_plans/research_execution_plan.md` actually completable by implementing the missing Blocksworld diagnostic, benchmark, expert-demonstration, serialization, and registration infrastructure with deterministic verification.

### Deliverables
- `doc/detailed_implementation_summary/phase1_scope_lock_and_diagnostic_summary.md`
- `examples/planning_benchmark_slice/` upgraded with Blocksworld core, validators, zero-shot tooling, expert generators, modality serializers, and benchmark loop commands.
- `tests/planning_benchmark/` or equivalent tests covering parsing, transitions, validation, zero-shot scoring, trajectories, serializers, and registry smoke.
- Minimal committed fixtures under `tests/fixtures/planning/` for fresh-checkout tests.
- Generated local evidence under `.sisyphus/evidence/phase1-3-*`.
- StarVLA data registry under `examples/planning_benchmark_slice/train_files/data_registry/data_config.py`.
- Optional generated local artifacts under `data/planning_artifacts/**` or `outputs/planning_artifacts/**` with artifact policy documented.

### Definition of Done (verifiable conditions with commands)
All commands must be run exactly with the repo-required environment prefix:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/test_planimation_phase1.py tests/data_collect tests/examples/test_planning_benchmark_slice.py tests/planning_benchmark -q
```

Expected: all tests pass or tests requiring large local datasets skip with a clear fixture-generation command.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.validate_instance --fixture tests/fixtures/planning/blocksworld_nontrivial.json --min-plan-length 2 --require-non-empty-goal --json
```

Expected: exits `0`; JSON reports `goal_is_empty=false`, `already_solved=false`, `min_plan_length_satisfied=true`, and legal actions are non-empty.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.zero_shot_build --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms bfs fast_forward iterated_width graphplan --modalities vision language vision_language vision_language_tool --output outputs/planning_artifacts/zero_shot_smoke --json
```

Expected: emits 16 prompt packages and gold scoring metadata; no modality leakage detected.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.generate_experts --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms bfs fast_forward iterated_width graphplan --output outputs/planning_artifacts/expert_smoke --json
```

Expected: emits one valid trajectory per algorithm; all steps validate against algorithm-specific schemas.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.serialize_modalities --input outputs/planning_artifacts/expert_smoke --output outputs/planning_artifacts/dataset_smoke --modalities vision language vision_language vision_language_tool --json
```

Expected: exactly four modality outputs; each has nonzero examples or a machine-readable skip reason for unavailable vision data.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
from starVLA.dataloader.gr00t_lerobot.registry import DATASET_NAMED_MIXTURES, ROBOT_TYPE_CONFIG_MAP
assert "planning_blocksworld_dev_smoke" in DATASET_NAMED_MIXTURES
assert "planning_blocksworld" in ROBOT_TYPE_CONFIG_MAP
print("planning dataset registry smoke passed")
PY
```

Expected stdout: `planning dataset registry smoke passed`.

### Must Have
- Blocksworld-only P0 closure for Phase 1-3.
- Non-trivial instance validation: reject empty goals and already-solved tasks.
- Deterministic symbolic world model v0.
- Zero-shot prompt/output schema and offline scorer.
- Local expert generators with planner-state annotations.
- Four modality serializers with leakage tests.
- StarVLA data registry smoke test.
- Detailed implementation summaries and evidence commands.

### Must NOT Have
- No Phase 4+ trainable planner model implementation.
- No full P0 multi-seed SFT matrix.
- No cross-task transfer tasks.
- No treating raw PDDL files, final plans only, or Planimation traces alone as expert demonstrations.
- No human visual confirmation as acceptance criteria.
- No requirement to complete all 15 curriculum domains for Phase 1-3 acceptance.
- No forking StarVLA training loops unless registry integration is proven impossible.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: tests-after with focused TDD inside each task; framework is `pytest` plus CLI JSON smoke tests.
- QA policy: Every task has agent-executed scenarios.
- Evidence: `.sisyphus/evidence/phase1-3-task-{N}-{slug}.{ext}`

## Execution Strategy

### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks for max parallelism.

Wave 1: Task 1 scope lock, Task 2 canonical Blocksworld core, Task 3 zero-shot diagnostic scaffolding.
Wave 2: Task 4 benchmark loop, Task 5 unified schema, Tasks 6-8 expert generators.
Wave 3: Task 9 modality serializers, Task 10 data registry, Task 11 docs/status/evidence.
Wave 4: Final verification wave F1-F4.

### Dependency Matrix (full, all tasks)
- Task 1 blocks all tasks by fixing scope, decisions, and acceptance boundaries.
- Task 2 blocks Tasks 3-10 because parsing/state/action/transition are shared.
- Task 3 depends on Tasks 1-2 and blocks Phase 1 closeout.
- Task 4 depends on Task 2 and provides benchmark loop validation for Tasks 6-9.
- Task 5 depends on Task 2 and blocks Tasks 6-10.
- Task 6 depends on Tasks 2 and 5.
- Task 7 depends on Tasks 2 and 5.
- Task 8 depends on Tasks 2 and 5.
- Task 9 depends on Tasks 2, 4, and 5-8.
- Task 10 depends on Task 9.
- Task 11 depends on Tasks 1-10.

### Agent Dispatch Summary (wave → task count → categories)
- Wave 1 → 3 tasks → writing, unspecified-high, deep.
- Wave 2 → 5 tasks → unspecified-high, deep.
- Wave 3 → 3 tasks → unspecified-high, writing.
- Wave 4 → 4 review tasks → oracle, unspecified-high, deep.

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [x] 1. Phase 1 Scope Lock and Decision Artifacts

  **What to do**: Create explicit Phase 1 decision artifacts documenting Blocksworld-only P0, algorithms, modalities, Planimation role, frozen symbolic world-model v0, artifact policy, and go/no-go zero-shot criteria. Add a lightweight checker test or CLI that validates the artifact contains the required fields. The scope-lock must state that 15-domain curriculum support is future-compatible but not Phase 1-3 acceptance scope.
  **Must NOT do**: Do not claim Phase 1 is complete until Tasks 2-3 pass. Do not broaden scope to all domains or Phase 4 training.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: documentation-heavy with exact technical decisions.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`git-master`] - No git operation required inside task.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11] | Blocked By: []

  **References**:
  - Plan rubric: `doc/high_level_plans/research_execution_plan.md:55-89` - Phase 1 criteria.
  - Proposal zero-shot protocol: `doc/research_proposal.md:156-215` - diagnostic gate source of truth.
  - Existing Phase 1 evidence: `doc/detailed_implementation_summary/phase1_planimation_all_domains_validation_summary.md` - Planimation validation to preserve.
  - Existing renderer: `scripts/planimation_phase1.py:120-151` - endpoint derivation pattern.

  **Acceptance Criteria**:
  - [ ] `doc/detailed_implementation_summary/phase1_scope_lock_and_diagnostic_summary.md` exists and names `blocksworld`, `bfs`, `fast_forward`, `iterated_width`, `graphplan`, `vision`, `language`, `vision_language`, `vision_language_tool`.
  - [ ] Artifact states: frozen world model v0 = deterministic symbolic representation; no learned encoder for Phase 1-3.
  - [ ] Artifact states: Planimation = offline rendering/visualization utility, not environment authority.
  - [ ] Checker command validates required keys and writes `.sisyphus/evidence/phase1-3-task-1-scope-lock.json`.

  **QA Scenarios**:
  ```
  Scenario: Scope lock validates
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.scope_lock validate --path doc/detailed_implementation_summary/phase1_scope_lock_and_diagnostic_summary.md --json > .sisyphus/evidence/phase1-3-task-1-scope-lock.json
    Expected: exit 0; JSON has valid=true and required_decisions_present=true
    Evidence: .sisyphus/evidence/phase1-3-task-1-scope-lock.json

  Scenario: Missing decision fails
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.scope_lock validate --path tests/fixtures/planning/scope_lock_missing_world_model.md --json
    Expected: nonzero exit; error mentions missing frozen_world_model_decision
    Evidence: .sisyphus/evidence/phase1-3-task-1-scope-lock-error.txt
  ```

  **Commit**: YES | Message: `docs(planning): lock phase 1-3 research scope` | Files: [`doc/detailed_implementation_summary/phase1_scope_lock_and_diagnostic_summary.md`, `examples/planning_benchmark_slice/scope_lock.py`, `tests/planning_benchmark/test_scope_lock.py`, `tests/fixtures/planning/*`]

- [x] 2. Canonical Blocksworld Symbolic Core and Non-Trivial Instance Gate

  **What to do**: Add Blocksworld parsing and deterministic symbolic world-model v0 under `examples/planning_benchmark_slice/`: parse PDDL objects/init/goal/action vocabulary, encode canonical atom sets, generate state IDs, compute legal actions, transition states, check goals, and validate non-trivial instances. Validation must reject empty goals (`(:goal (and))`), already-solved tasks, missing action vocabulary, malformed PDDL, missing render artifacts for vision-required paths, and tasks below minimum plan length when requested. Provide committed fixtures so tests do not require large local `data/curriculum_pddl/**` artifacts.
  **Must NOT do**: Do not implement arbitrary PDDL or all-domain support. Only support Blocksworld 4-operator STRIPS used by current generated examples.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: foundational symbolic state logic with correctness constraints.
  - Skills: [] - No external skill needed.
  - Omitted: [`playwright`] - No browser/UI.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [3, 4, 5, 6, 7, 8, 9, 10] | Blocked By: [1]

  **References**:
  - Existing loader: `examples/planning_benchmark_slice/__init__.py:113-199` - current payload fields to preserve.
  - Current test: `tests/examples/test_planning_benchmark_slice.py:25-53` - existing smoke expectations; note empty-goal caveat.
  - Current data schema: `src/data_collect/metadata.py:67-156` - accepted instance metadata shape.
  - Planimation evidence: `src/data_collect/rendering.py:110-152` - render outcome fields.

  **Acceptance Criteria**:
  - [ ] Blocksworld parser handles current `pickup`, `putdown`, `stack`, `unstack` domain.
  - [ ] Deterministic state IDs are stable across repeated runs and independent of PDDL atom order.
  - [ ] `validate_instance` rejects empty-goal fixture and accepts non-trivial fixture with min plan length >= 2.
  - [ ] Tests do not require `data/curriculum_pddl/**`; they use committed fixtures or skip with a clear generation command.

  **QA Scenarios**:
  ```
  Scenario: Non-trivial Blocksworld fixture validates
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.validate_instance --fixture tests/fixtures/planning/blocksworld_nontrivial.json --min-plan-length 2 --require-non-empty-goal --json > .sisyphus/evidence/phase1-3-task-2-valid-instance.json
    Expected: exit 0; goal_is_empty=false; already_solved=false; legal_actions_count > 0
    Evidence: .sisyphus/evidence/phase1-3-task-2-valid-instance.json

  Scenario: Empty goal is rejected
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.validate_instance --fixture tests/fixtures/planning/blocksworld_empty_goal.json --require-non-empty-goal --json
    Expected: nonzero exit; error code empty_goal
    Evidence: .sisyphus/evidence/phase1-3-task-2-empty-goal-error.json
  ```

  **Commit**: YES | Message: `feat(planning): add blocksworld symbolic core` | Files: [`examples/planning_benchmark_slice/blocksworld.py`, `examples/planning_benchmark_slice/validate_instance.py`, `tests/planning_benchmark/test_blocksworld_core.py`, `tests/fixtures/planning/*`]

- [x] 3. Phase 1 Zero-Shot Diagnostic Packaging and Offline Scorer

  **What to do**: Implement zero-shot prompt package builder, output JSON schema validator, and deterministic scorer using the proposal criteria: syntactic validity, algorithmic fidelity, and action validity. Generate artifacts for all 4 algorithms × 4 modalities from a validated non-trivial Blocksworld fixture. Keep real VLM calls optional and out of acceptance. Add fixtures for valid output, parse error, illegal action, and algorithm-fidelity error.
  **Must NOT do**: Do not call GPUs or external model APIs in mandatory tests. Do not let Vision-only packages include PDDL atoms, state IDs, or symbolic goal text.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: schema/scoring correctness and modality leakage constraints.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`playwright`] - No UI.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [11] | Blocked By: [1, 2]

  **References**:
  - Proposal prompt format: `doc/research_proposal.md:160-192` - algorithm definitions, modality inputs, output JSON.
  - Proposal scoring: `doc/research_proposal.md:194-215` - success and error labels.
  - Existing payload builder: `examples/planning_benchmark_slice/__init__.py:178-199` - fields to reuse safely.

  **Acceptance Criteria**:
  - [ ] `zero_shot_build` emits 16 prompt packages for 4 algorithms × 4 modalities.
  - [ ] `zero_shot_diagnostic validate-schema` accepts valid fixture and rejects malformed fixture.
  - [ ] `zero_shot_diagnostic score` labels Pass, Algorithmic Error, Action Error, and Parse Error.
  - [ ] Modality leakage tests verify forbidden fields are absent per modality.

  **QA Scenarios**:
  ```
  Scenario: Build zero-shot prompt packages
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.zero_shot_build --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms bfs fast_forward iterated_width graphplan --modalities vision language vision_language vision_language_tool --output outputs/planning_artifacts/zero_shot_smoke --json > .sisyphus/evidence/phase1-3-task-3-zero-shot-build.json
    Expected: exit 0; package_count=16; leakage_errors=[]
    Evidence: .sisyphus/evidence/phase1-3-task-3-zero-shot-build.json

  Scenario: Illegal action is scored correctly
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.zero_shot_diagnostic score --input tests/fixtures/planning/zero_shot/bfs_illegal_action.json --json > .sisyphus/evidence/phase1-3-task-3-illegal-action.json
    Expected: score_label='Action Error'; syntactic_validity=true; action_validity=false
    Evidence: .sisyphus/evidence/phase1-3-task-3-illegal-action.json
  ```

  **Commit**: YES | Message: `feat(planning): add zero-shot diagnostic gate` | Files: [`examples/planning_benchmark_slice/zero_shot*.py`, `tests/planning_benchmark/test_zero_shot*.py`, `tests/fixtures/planning/zero_shot/*`]

- [x] 4. Minimal In-Process Benchmark Loop and Oracle Baseline

  **What to do**: Add a direct Python benchmark loop for validated Blocksworld instances. The loop must reset an instance, expose observations through the same core payload contract, accept actions, transition state, stop on goal or max steps, and record step logs. Add a deterministic oracle mode using local BFS for legal-action baseline, but keep model/server integration out of scope. Document that Phase 2 uses direct Python, not server/client.
  **Must NOT do**: Do not implement WebSocket serving or full StarVLA evaluation server in Phase 2.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: moderate implementation over existing example package.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`playwright`] - No browser.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [9, 11] | Blocked By: [1, 2]

  **References**:
  - Phase 2 rubric: `doc/high_level_plans/research_execution_plan.md:92-126` - benchmark slice deliverable.
  - Existing example CLI: `examples/planning_benchmark_slice/__main__.py:1-7` - package entrypoint pattern.
  - StarVLA external convention: `examples/eval_protocol.md` - future server/client direction, not required for P0.

  **Acceptance Criteria**:
  - [ ] `benchmark_loop run-oracle` solves the non-trivial fixture within max steps.
  - [ ] Step log includes observations, action, pre/post state IDs, legal-action check, terminal status.
  - [ ] Invalid action produces structured failure without crashing.
  - [ ] Documentation states direct Python loop is the Phase 2 decision.

  **QA Scenarios**:
  ```
  Scenario: Oracle solves non-trivial fixture
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.benchmark_loop run-oracle --fixture tests/fixtures/planning/blocksworld_nontrivial.json --max-steps 20 --json > .sisyphus/evidence/phase1-3-task-4-oracle-loop.json
    Expected: exit 0; solved=true; illegal_action_count=0; steps >= 2
    Evidence: .sisyphus/evidence/phase1-3-task-4-oracle-loop.json

  Scenario: Invalid action fails gracefully
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.benchmark_loop run-scripted --fixture tests/fixtures/planning/blocksworld_nontrivial.json --actions tests/fixtures/planning/actions_invalid.json --json
    Expected: nonzero exit; error code illegal_action; no traceback
    Evidence: .sisyphus/evidence/phase1-3-task-4-invalid-action.json
  ```

  **Commit**: YES | Message: `feat(planning): add blocksworld benchmark loop` | Files: [`examples/planning_benchmark_slice/benchmark_loop.py`, `tests/planning_benchmark/test_benchmark_loop.py`, `doc/detailed_implementation_summary/phase2_benchmark_loop_summary.md`]

- [x] 5. Unified Expert Trajectory Schema and Validator

  **What to do**: Define canonical trajectory JSON/JSONL schema with shared fields and algorithm-specific required fields. Shared fields: `trajectory_id`, `algorithm`, `domain`, `instance_id`, `step_index`, `state_id`, `state_atoms`, `goal_atoms`, `legal_actions`, `selected_action`, `is_terminal`, `metadata`. Algorithm fields: BFS frontier/visited/dequeued/successors; FF heuristic values/tie-break; IW width/novelty table/decision; Graphplan layers/actions/mutexes/extraction. Add schema validator CLI and tests.
  **Must NOT do**: Do not design a model-training format here; this is canonical expert data only.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: schema correctness shared by all expert generators.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`github-cli`] - No remote inspection needed.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [6, 7, 8, 9, 10] | Blocked By: [1, 2]

  **References**:
  - Phase 3 rubric: `doc/high_level_plans/research_execution_plan.md:129-167` - trajectory deliverable.
  - Proposal algorithm details: `doc/research_proposal.md:220-413` - fields by algorithm.
  - Current metadata limitation: `src/data_collect/metadata.py:67-156` - accepted instances are not trajectories.
  - External sanity: Taskography trajectory distinction - raw PDDL vs `(states, plan)` traces.

  **Acceptance Criteria**:
  - [ ] Validator accepts one valid fixture per algorithm.
  - [ ] Validator rejects missing BFS frontier, FF heuristic, IW novelty, and Graphplan mutex/layer fields.
  - [ ] Schema has deterministic serialization order for novelty tables and sets.

  **QA Scenarios**:
  ```
  Scenario: Valid schema fixtures pass
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.validate_trajectories --input tests/fixtures/planning/trajectories/valid --json > .sisyphus/evidence/phase1-3-task-5-schema-valid.json
    Expected: exit 0; valid=true; algorithms_validated includes bfs, fast_forward, iterated_width, graphplan
    Evidence: .sisyphus/evidence/phase1-3-task-5-schema-valid.json

  Scenario: Missing algorithm field fails
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.validate_trajectories --input tests/fixtures/planning/trajectories/invalid_missing_bfs_frontier --json
    Expected: nonzero exit; error mentions bfs.frontier_before
    Evidence: .sisyphus/evidence/phase1-3-task-5-schema-error.json
  ```

  **Commit**: YES | Message: `feat(planning): define expert trajectory schema` | Files: [`examples/planning_benchmark_slice/trajectory_schema.py`, `examples/planning_benchmark_slice/validate_trajectories.py`, `tests/planning_benchmark/test_trajectory_schema.py`, `tests/fixtures/planning/trajectories/*`]

- [x] 6. BFS and Iterated Width Expert Generators

  **What to do**: Implement local BFS and IW expert generators on top of the canonical Blocksworld core and trajectory schema. BFS must record FIFO frontier before/after, dequeued state, visited sets, generated successors, selected action, and deterministic action tie-break. IW must record width `k`, atoms/tuples, novelty table before/after, novel item, prune/expand decision, and selected action when expanding.
  **Must NOT do**: Do not use generic final plans without planner-state annotations. Do not allow nondeterministic set ordering.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: algorithmic correctness and trace determinism.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`playwright`] - No UI.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [9] | Blocked By: [2, 5]

  **References**:
  - Proposal BFS details: `doc/research_proposal.md:220-265` - queue externalization fields.
  - Proposal IW details: `doc/research_proposal.md:309-369` - novelty table fields.
  - External pattern: Powerlifted novelty tables (`achieved_atoms`, `atom_mapping`) - use as sanity check.

  **Acceptance Criteria**:
  - [ ] BFS generator creates at least one valid trajectory for non-trivial fixture.
  - [ ] IW generator creates at least one valid trajectory for non-trivial fixture.
  - [ ] Repeated runs produce byte-identical JSON for same input.
  - [ ] Schema validator passes generated outputs.

  **QA Scenarios**:
  ```
  Scenario: BFS/IW smoke generation
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.generate_experts --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms bfs iterated_width --output outputs/planning_artifacts/expert_bfs_iw_smoke --json > .sisyphus/evidence/phase1-3-task-6-bfs-iw.json
    Expected: exit 0; bfs.trajectory_count=1; iterated_width.trajectory_count=1
    Evidence: .sisyphus/evidence/phase1-3-task-6-bfs-iw.json

  Scenario: Determinism check
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.generate_experts --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms bfs iterated_width --output /tmp/planning_expert_run_a --json && python -m examples.planning_benchmark_slice.generate_experts --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms bfs iterated_width --output /tmp/planning_expert_run_b --json && diff -r /tmp/planning_expert_run_a /tmp/planning_expert_run_b
    Expected: exit 0; no diff
    Evidence: .sisyphus/evidence/phase1-3-task-6-determinism.txt
  ```

  **Commit**: YES | Message: `feat(planning): generate bfs and iw expert traces` | Files: [`examples/planning_benchmark_slice/experts/bfs.py`, `examples/planning_benchmark_slice/experts/iterated_width.py`, `examples/planning_benchmark_slice/generate_experts.py`, `tests/planning_benchmark/test_experts_bfs_iw.py`]

- [x] 7. Fast Forward-Style Expert Generator

  **What to do**: Implement a deterministic FF-style greedy heuristic expert for Blocksworld with documented simplification. It must compute delete-relaxation-inspired heuristic values for successors or a documented symbolic approximation, record heuristic values, selected successor/action, tie-break rule, relaxed-plan metadata if available, and failure reason if no successor is legal. Document exact approximation in code and implementation summary.
  **Must NOT do**: Do not call this full Fast Downward FF unless actual delete-relaxation semantics are implemented or clearly documented as a P0 approximation.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: heuristic definition must be explicit and testable.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`github-cli`] - External examples already collected.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [9] | Blocked By: [2, 5]

  **References**:
  - Proposal FF details: `doc/research_proposal.md:266-308` - delete-relaxation heuristic intent.
  - External pattern: Fast Downward `ff()` and FF relaxed plan extraction - use as sanity check.

  **Acceptance Criteria**:
  - [ ] FF-style generator emits valid trajectory with `successor_heuristics`, `selected_successor_id`, `selected_action`, `heuristic_value`, and `tie_break_rule`.
  - [ ] Heuristic calculation is deterministic and tested on at least three fixture states.
  - [ ] Implementation summary states whether it is exact delete-relaxation or documented approximation.

  **QA Scenarios**:
  ```
  Scenario: FF smoke generation
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.generate_experts --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms fast_forward --output outputs/planning_artifacts/expert_ff_smoke --json > .sisyphus/evidence/phase1-3-task-7-ff.json
    Expected: exit 0; fast_forward.trajectory_count=1; every step has successor_heuristics
    Evidence: .sisyphus/evidence/phase1-3-task-7-ff.json

  Scenario: FF tie-break deterministic
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/planning_benchmark/test_expert_fast_forward.py::test_fast_forward_tie_break_is_stable -q
    Expected: test passes
    Evidence: .sisyphus/evidence/phase1-3-task-7-tiebreak.txt
  ```

  **Commit**: YES | Message: `feat(planning): generate fast-forward expert traces` | Files: [`examples/planning_benchmark_slice/experts/fast_forward.py`, `tests/planning_benchmark/test_expert_fast_forward.py`, `doc/detailed_implementation_summary/phase3_fast_forward_approximation_summary.md`]

- [x] 8. Graphplan Expert Generator

  **What to do**: Implement simplified Graphplan over Blocksworld with proposition layers, applicable action layers, action mutex pairs, next proposition layers, goal-present-without-mutex status, and optional extraction steps. Match the proposal's feasibility simplification: action-level mutex only is acceptable if documented.
  **Must NOT do**: Do not silently omit mutexes or call a plain planning graph "Graphplan" without layer/mutex annotations.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: constraint/layer reasoning is algorithmically subtle.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`playwright`] - No UI.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [9] | Blocked By: [2, 5]

  **References**:
  - Proposal Graphplan details: `doc/research_proposal.md:370-414` - layer/mutex requirements and simplification.
  - External pattern: Graphplan stores layers, mutex props/actions, and backward frontier.

  **Acceptance Criteria**:
  - [ ] Graphplan generator emits proposition layers, action layers, mutex pairs, next layers, and goal status.
  - [ ] Tests verify at least one known mutex pair in a fixture state.
  - [ ] Schema validator passes generated Graphplan output.

  **QA Scenarios**:
  ```
  Scenario: Graphplan smoke generation
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.generate_experts --fixture tests/fixtures/planning/blocksworld_nontrivial.json --algorithms graphplan --output outputs/planning_artifacts/expert_graphplan_smoke --json > .sisyphus/evidence/phase1-3-task-8-graphplan.json
    Expected: exit 0; graphplan.trajectory_count=1; layer_count > 0; mutex_pairs recorded
    Evidence: .sisyphus/evidence/phase1-3-task-8-graphplan.json

  Scenario: Graphplan mutex test
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/planning_benchmark/test_expert_graphplan.py::test_action_mutex_pairs_are_recorded -q
    Expected: test passes
    Evidence: .sisyphus/evidence/phase1-3-task-8-mutex.txt
  ```

  **Commit**: YES | Message: `feat(planning): generate graphplan expert traces` | Files: [`examples/planning_benchmark_slice/experts/graphplan.py`, `tests/planning_benchmark/test_expert_graphplan.py`]

- [x] 9. Four Modality Serializers and Leakage Tests

  **What to do**: Serialize canonical trajectories into four outputs: `vision`, `language`, `vision_language`, `vision_language_tool`. Vision-only may include image/frame references and non-symbolic task framing but must not include PDDL atoms/state IDs. Language-only may include parsed symbolic/natural-language state/goal/action text but not render paths/images. VLA includes both. VLA+Tool includes scratchpad state/update fields (queue, visited, heuristic, novelty table, graph layers as appropriate). Add leakage tests and JSONL output summaries.
  **Must NOT do**: Do not leak hidden gold labels into model-facing fields. Keep gold labels in separate metadata/eval fields.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: data formatting and rigorous negative tests.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`ui-ux-pro-max`] - No UI design.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: [10, 11] | Blocked By: [4, 5, 6, 7, 8]

  **References**:
  - Proposal modality table: `doc/research_proposal.md:174-182` - modality-specific inputs.
  - Existing payload fields: `examples/planning_benchmark_slice/__init__.py:178-199` - source fields to split.
  - StarVLA modality pattern: existing `examples/*/train_files/modality.json` files - follow naming conventions where applicable.

  **Acceptance Criteria**:
  - [ ] Serializer emits four JSONL outputs from expert smoke trajectories.
  - [ ] Leakage tests prove forbidden fields are absent per modality.
  - [ ] VLA+Tool includes algorithm-specific scratchpad state and update target.
  - [ ] Serializer summary reports counts per algorithm and modality.

  **QA Scenarios**:
  ```
  Scenario: Serialize all modalities
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.serialize_modalities --input outputs/planning_artifacts/expert_smoke --output outputs/planning_artifacts/dataset_smoke --modalities vision language vision_language vision_language_tool --json > .sisyphus/evidence/phase1-3-task-9-serialize.json
    Expected: exit 0; modality_outputs=[vision, language, vision_language, vision_language_tool]; leakage_errors=[]
    Evidence: .sisyphus/evidence/phase1-3-task-9-serialize.json

  Scenario: Vision-only leakage test
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/planning_benchmark/test_modality_serializers.py::test_vision_only_has_no_symbolic_state_ids_or_pddl -q
    Expected: test passes
    Evidence: .sisyphus/evidence/phase1-3-task-9-vision-leakage.txt
  ```

  **Commit**: YES | Message: `feat(planning): serialize expert traces by modality` | Files: [`examples/planning_benchmark_slice/serialize_modalities.py`, `examples/planning_benchmark_slice/modality_serializers.py`, `tests/planning_benchmark/test_modality_serializers.py`]

- [x] 10. StarVLA Planning Dataset Registration

  **What to do**: Add planning dataset registry under `examples/planning_benchmark_slice/train_files/data_registry/data_config.py` using StarVLA's auto-discovery pattern. Register `planning_blocksworld` robot/data type and `planning_blocksworld_dev_smoke` named mixture pointing to serialized smoke JSONL outputs. Add minimal training config or README entry only if needed for discovery; no full training run required.
  **Must NOT do**: Do not force LeRobot continuous action tensors if JSONL/conversation-style registration is the correct first path. Do not modify core dataloader discovery unless unavoidable.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: integration with existing registry conventions.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`git-master`] - No git operation inside task.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: [11] | Blocked By: [9]

  **References**:
  - Registry discovery: `starVLA/dataloader/gr00t_lerobot/registry.py:89-149` - auto-discovery pattern.
  - Existing registry examples: `examples/LIBERO/train_files/data_registry/data_config.py` - expected shape.
  - Plan Phase 3 registry requirement: `doc/high_level_plans/research_execution_plan.md:156-162`.

  **Acceptance Criteria**:
  - [ ] `examples/planning_benchmark_slice/train_files/data_registry/data_config.py` exists and imports cleanly.
  - [ ] Registry smoke command sees `planning_blocksworld_dev_smoke` and `planning_blocksworld`.
  - [ ] README documents how to regenerate smoke JSONL before registry smoke if outputs are untracked.

  **QA Scenarios**:
  ```
  Scenario: Registry smoke passes
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
from starVLA.dataloader.gr00t_lerobot.registry import DATASET_NAMED_MIXTURES, ROBOT_TYPE_CONFIG_MAP
assert "planning_blocksworld_dev_smoke" in DATASET_NAMED_MIXTURES
assert "planning_blocksworld" in ROBOT_TYPE_CONFIG_MAP
print("planning dataset registry smoke passed")
PY
    Expected: stdout contains planning dataset registry smoke passed
    Evidence: .sisyphus/evidence/phase1-3-task-10-registry.txt

  Scenario: Registry name collision test
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/planning_benchmark/test_dataset_registry.py::test_planning_registry_names_are_unique -q
    Expected: test passes
    Evidence: .sisyphus/evidence/phase1-3-task-10-registry-collision.txt
  ```

  **Commit**: YES | Message: `feat(planning): register blocksworld planning dataset` | Files: [`examples/planning_benchmark_slice/train_files/data_registry/data_config.py`, `examples/planning_benchmark_slice/train_files/README.md`, `tests/planning_benchmark/test_dataset_registry.py`]

- [x] 11. Documentation Closeout and Execution Plan Status Update

  **What to do**: Add detailed implementation summaries for Phase 1-3 closure. Update `doc/high_level_plans/research_execution_plan.md` only after all verification passes: mark Phase 1, Phase 2, and Phase 3 complete with evidence links and caveats. Preserve older summaries but clarify that `phase2_curriculum_pddl_generation_summary.md` is curriculum generation, not Phase 3 expert demos. Document artifact policy for generated local outputs.
  **Must NOT do**: Do not mark complete based on partial evidence. Do not commit generated large data unless explicitly requested.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: docs and status closeout.
  - Skills: [] - No specialized skill needed.
  - Omitted: [`git-master`] - Commit can be handled after review.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: [] | Blocked By: [1, 3, 4, 5, 6, 7, 8, 9, 10]

  **References**:
  - Existing summaries: `doc/detailed_implementation_summary/phase1_planimation_all_domains_validation_summary.md`, `doc/detailed_implementation_summary/phase2_curriculum_pddl_generation_summary.md`.
  - Execution plan: `doc/high_level_plans/research_execution_plan.md`.
  - Evidence directory: `.sisyphus/evidence/`.

  **Acceptance Criteria**:
  - [ ] Summary docs include exact commands run and expected/observed outputs.
  - [ ] Execution plan status notes include evidence paths for Phases 1-3.
  - [ ] Docs preserve caveats: Blocksworld-only P0, direct Python loop, local artifacts policy, no Phase 4 training yet.

  **QA Scenarios**:
  ```
  Scenario: Documentation references evidence
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.docs_check --phase 1 2 3 --json > .sisyphus/evidence/phase1-3-task-11-docs-check.json
    Expected: exit 0; all referenced evidence files exist
    Evidence: .sisyphus/evidence/phase1-3-task-11-docs-check.json

  Scenario: Execution plan is not overclaiming
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice.docs_check --no-phase4-claims --json
    Expected: exit 0; no Phase 4+ completion claims
    Evidence: .sisyphus/evidence/phase1-3-task-11-no-overclaim.json
  ```

  **Commit**: YES | Message: `docs(planning): close phase 1-3 implementation gaps` | Files: [`doc/detailed_implementation_summary/phase1_scope_lock_and_diagnostic_summary.md`, `doc/detailed_implementation_summary/phase2_benchmark_loop_summary.md`, `doc/detailed_implementation_summary/phase3_expert_trajectories_summary.md`, `doc/high_level_plans/research_execution_plan.md`]

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.
- [x] F1. Plan Compliance Audit — oracle
- [x] F2. Code Quality Review — unspecified-high
- [x] F3. Real Manual QA — unspecified-high
- [x] F4. Scope Fidelity Check — deep

## Commit Strategy
- Use small commits matching task boundaries where possible.
- Never commit generated large data under `data/curriculum_pddl/**`, `data/planning_artifacts/**`, or `outputs/planning_artifacts/**` unless the user explicitly requests it.
- Commit fixtures, tests, source code, docs, and summaries only.
- Suggested final squashed commit if the user wants one docs/features commit: `feat(planning): close phase 1-3 research pipeline gaps`.

## Success Criteria
- Existing Planimation, data collection, and planning slice tests still pass.
- Phase 1 has explicit scope lock, zero-shot gate, and frozen symbolic world-model decision.
- Phase 2 has a validated non-trivial Blocksworld benchmark loop using direct Python.
- Phase 3 has expert trajectories for BFS, Fast Forward, Iterated Width, and Graphplan with algorithm-specific planner-state annotations.
- Four modality outputs are generated and leakage-tested.
- StarVLA registry sees the planning dataset mixture.
- `doc/high_level_plans/research_execution_plan.md` is updated only after all above verification passes.
