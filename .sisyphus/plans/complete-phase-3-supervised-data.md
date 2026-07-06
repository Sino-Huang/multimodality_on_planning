# Complete Phase 3 Supervised Planning Data

## TL;DR
> **Summary**: Build a complete Phase 3 JSONL supervised planning dataset pipeline rooted in `data/curriculum_pddl`, with Planimation assets as vision supervision and BFS/FF/IW/Graphplan attempts as language/tool-use supervision. The pipeline must account for every accepted curriculum instance and every planner attempt, but emit supervised examples only from replay-validated successful traces/plans.
> **Deliverables**:
> - `data/phase3_supervised_planning/` generated corpus layout with JSONL splits, schemas, diagnostics, and reports.
> - Generic PDDL preflight, grounding, state transition, replay validation, and action normalization layer.
> - Local BFS full-trace adapter plus FF/IW/Graphplan external-plan/replay adapters with explicit skip diagnostics when executables or supported PDDL features are unavailable.
> - Per-instance and per-planner accounting diagnostics with controlled statuses.
> - Verification CLIs for manifest coverage, planner attempts, schema, replay, fidelity, splits, domain coverage, vision assets, smoke exclusion, and determinism.
> - Documentation summary under `doc/detailed_implementation_summary/phase3_complete_supervised_planning_data_summary.md`.
> **Effort**: XL
> **Parallel**: YES - 4 waves
> **Critical Path**: Task 1 → Task 2 → Task 3 → Task 6 → Task 9 → Task 11

## Context

### Original Request
The user rejected the previous answer that pointed to `outputs/planning_artifacts`: it is not the desired Phase 3 supervised training data. The corrected Phase 3 must use PDDL training data in `data/curriculum_pddl`, cover the range of curriculum domains rather than only Blocksworld, generate BFS/FF/IW/Graphplan traces from those problem instances, use those traces as language/tool-use supervision, and use Planimation outputs already stored in `data/curriculum_pddl` as vision supervision.

### Interview Summary
- Output root: `data/phase3_supervised_planning/`.
- Completion policy: attempt and account for every accepted curriculum instance and every planner; unsupported/timeouts/failures become machine-readable diagnostics.
- Supervision policy: emit examples only for successful replay-validated plans/traces.
- Trace fidelity policy: FF/IW/Graphplan `success_plan_replayed` examples count as valid supervised data when an external planner plan is replayed by the generic validator; records must disclose replay-level fidelity.
- Dataset target: schema-validated JSONL training-ready data, not StarVLA/LeRobot tensor conversion.

### Research Findings
- Curriculum config defines 15 domains and splits in `src/data_collect/configs/curriculum_15_domains.yaml:22-139`.
- The intended domains are `15puzzle`, `blocksworld`, `depot`, `driverlog`, `elevators`, `ferry`, `freecell`, `grid`, `gripper`, `logistics`, `snake`, `sokoban`, `storage`, `towers_of_hanoi`, `visitall` from `src/data_collect/configs/curriculum_15_domains.yaml:48-138`.
- Current planning slice loader contract already reads `accepted_manifest.jsonl`, resolves `domain.pddl`, `problem.pddl`, `render/trace.vfg.json`, frames, and fails on missing artifacts in `examples/planning_benchmark_slice/README.md:11-38`.
- Current smoke registry explicitly points to `outputs/planning_artifacts/dataset_smoke` and Blocksworld-only names in `examples/planning_benchmark_slice/train_files/data_registry/data_config.py:31-34` and `:99-105`; this must not be treated as final Phase 3.
- Current modality serializer preserves the desired `model_facing`, `supervised_target`, and `evaluation_metadata` separation in `examples/planning_benchmark_slice/modality_serializers.py:206-220`.
- Current trajectory schema has canonical algorithm names and algorithm-specific fields for BFS, FF, IW, and Graphplan in `examples/planning_benchmark_slice/trajectory_schema.py:14-58`.
- Existing BFS, FF, IW, and Graphplan experts import `BlocksworldProblem`, so they are Blocksworld-only: `examples/planning_benchmark_slice/experts/bfs.py:8-10`, `examples/planning_benchmark_slice/experts/fast_forward.py:7-9`, `examples/planning_benchmark_slice/experts/iterated_width.py:9-11`, `examples/planning_benchmark_slice/experts/graphplan.py:8-11`.
- Existing FF is explicitly a P0 Blocksworld approximation, not full FF, in `examples/planning_benchmark_slice/experts/fast_forward.py:27-42` and `:72-79`.
- Existing Graphplan is explicitly a P0 approximation with action-level mutex only in `examples/planning_benchmark_slice/experts/graphplan.py:41-49` and `:154-160`.
- Registry tests show smoke names, smoke paths, uniqueness checks, and optional dependency guard patterns in `tests/planning_benchmark/test_dataset_registry.py:28-76` and `:79-115`.

### Metis Review (gaps addressed)
- Added exact accounting requirements: one instance-level record per accepted manifest row and one planner-attempt record per `(accepted_instance, planner)`.
- Added exact controlled status taxonomies for planner attempts and vision validation.
- Added explicit no-fabrication and fidelity semantics.
- Added resource limits and deterministic generation guardrails.
- Added acceptance commands for coverage, planner attempts, schema, replay, fidelity labels, splits, domains, vision assets, smoke contamination, and determinism.
- Added guardrails for missing/corrupt Planimation assets, unsupported PDDL features, zero-length plans, duplicate plans, path portability, and large artifact handling.

## Work Objectives

### Core Objective
Implement a robust, auditable, multi-domain Phase 3 supervised planning data pipeline where `data/curriculum_pddl/accepted_manifest.jsonl` is the inclusion source, `data/curriculum_pddl` Planimation artifacts provide vision supervision, planner outputs provide language/tool-use supervision, and `data/phase3_supervised_planning/` contains generated JSONL examples plus complete diagnostics.

### Deliverables
- New Phase 3 package/CLI namespace: `scripts/phase3/`. All commands in this plan assume importable modules under that exact namespace.
- Generated output layout:
  ```text
  data/phase3_supervised_planning/
    generation_manifest.json
    summary.json
    train.jsonl
    dev.jsonl
    test.jsonl
    schema/
      supervised_planning_example.schema.json
      planner_attempt.schema.json
      instance_accounting.schema.json
    diagnostics/
      instance_accounting.jsonl
      planner_attempts.jsonl
      replay_validation.jsonl
      vision_validation.jsonl
      pddl_feature_preflight.jsonl
    reports/
      domain_coverage.json
      split_coverage.json
      planner_status_summary.json
      fidelity_summary.json
  ```
- Verification CLIs:
  - `python -m scripts.phase3.verify_manifest_coverage`
  - `python -m scripts.phase3.verify_planner_attempts`
  - `python -m scripts.phase3.validate_jsonl_schema`
  - `python -m scripts.phase3.verify_replay_validated_examples`
  - `python -m scripts.phase3.verify_fidelity_labels`
  - `python -m scripts.phase3.verify_splits`
  - `python -m scripts.phase3.verify_domain_coverage`
  - `python -m scripts.phase3.verify_vision_assets`
  - `python -m scripts.phase3.verify_no_smoke_sources`
  - `python -m scripts.phase3.verify_determinism`
- Test coverage under `tests/phase3/` or the closest existing test namespace.
- Summary documentation under `doc/detailed_implementation_summary/phase3_complete_supervised_planning_data_summary.md` with exact commands and status.

### Definition of Done (verifiable conditions with commands)
All commands use the required environment prefix.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.generate_supervised_data --input-root data/curriculum_pddl --output-root data/phase3_supervised_planning --planners bfs ff iw graphplan --json
```
Expected: exits `0`; writes the output layout above; reports accepted instance count, per-planner status counts, emitted examples, and diagnostics paths.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_manifest_coverage --accepted-manifest data/curriculum_pddl/accepted_manifest.jsonl --diagnostics data/phase3_supervised_planning/diagnostics/instance_accounting.jsonl
```
Expected: exits `0`; reports `missing_from_diagnostics = 0` and `unexpected_extra_instances = 0`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_planner_attempts --accepted-manifest data/curriculum_pddl/accepted_manifest.jsonl --planner-attempts data/phase3_supervised_planning/diagnostics/planner_attempts.jsonl --planners bfs ff iw graphplan
```
Expected: exits `0`; reports `missing_attempt_records = 0` and counts by planner/status.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.validate_jsonl_schema --schema data/phase3_supervised_planning/schema/supervised_planning_example.schema.json --jsonl data/phase3_supervised_planning/train.jsonl --jsonl data/phase3_supervised_planning/dev.jsonl --jsonl data/phase3_supervised_planning/test.jsonl
```
Expected: exits `0`; reports `invalid_rows = 0`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_replay_validated_examples --dataset-root data/phase3_supervised_planning
```
Expected: exits `0`; reports `examples_without_replay_validation = 0` and `examples_with_failed_replay = 0`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_fidelity_labels --dataset-root data/phase3_supervised_planning
```
Expected: exits `0`; no FF/IW/Graphplan external-plan-only examples are labeled `success_full_trace`; replay-only examples are labeled `success_plan_replayed`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_splits --accepted-manifest data/curriculum_pddl/accepted_manifest.jsonl --dataset-root data/phase3_supervised_planning
```
Expected: exits `0`; reports no train/dev/test overlap and split counts matching manifest split labels.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_domain_coverage --accepted-manifest data/curriculum_pddl/accepted_manifest.jsonl --dataset-root data/phase3_supervised_planning --domains 15puzzle blocksworld depot driverlog elevators ferry freecell grid gripper logistics snake sokoban storage towers_of_hanoi visitall
```
Expected: exits `0`; all 15 domains are present in diagnostics.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_vision_assets --dataset-root data/phase3_supervised_planning
```
Expected: exits `0`; reports `missing_frames = 0` and `unreadable_frames = 0` for examples with `vision_supervision_available = true`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_no_smoke_sources --dataset-root data/phase3_supervised_planning --forbidden-path outputs/planning_artifacts --forbidden-path examples/planning_benchmark_slice/experts
```
Expected: exits `0`; reports `forbidden_references = 0`.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_determinism --dataset-root data/phase3_supervised_planning --manifest data/phase3_supervised_planning/generation_manifest.json
```
Expected: exits `0`; stable example IDs, split assignments, and canonical plan hashes.

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3 tests/planning_benchmark tests/data_collect
```
Expected: exits `0`; no regressions in existing planning benchmark and data collection tests.

### Must Have
- Use `data/curriculum_pddl/accepted_manifest.jsonl` as the authoritative inclusion source.
- Never infer accepted instances by directory listing alone.
- Reconcile every accepted manifest row against required files: `domain.pddl`, `problem.pddl`, `render/result.json`, `render/trace.vfg.json`, and `render/frames/*.png`.
- Create diagnostics for missing/corrupt files instead of silently skipping.
- Create per-planner attempt records for BFS, FF, IW, and Graphplan, even when skipped or failed.
- Use generic replay validation as final correctness gate before supervised example emission.
- Preserve `model_facing`, `supervised_target`, `evaluation_metadata` in every example.
- Use portable relative paths in JSONL and diagnostics; absolute `/data/scratch/...` paths are forbidden in generated records.
- Include stable IDs: `domain`, `instance_id`, `split`, `planner`, `example_id`, `plan_hash`.
- Include provenance: accepted manifest path, source domain/problem paths, Planimation artifact paths, planner command, planner version if available, generation config, and schema version.
- Encode zero-length plans as valid success if the initial state satisfies the goal.

### Must NOT Have
- Must not use `outputs/planning_artifacts/**` as final Phase 3 source or output root.
- Must not promote Blocksworld-only smoke experts as multi-domain Phase 3 planners.
- Must not mutate source files under `data/curriculum_pddl`.
- Must not fabricate FF/IW/Graphplan internal search traces from final plans.
- Must not label external final-plan-only outputs as `success_full_trace`.
- Must not emit supervised examples from failed replay validation.
- Must not require manual frame inspection or manual acceptance.
- Must not implement StarVLA/LeRobot tensor conversion in this phase.
- Must not build a new full planner research system beyond the required local BFS and generic replay/validation layer.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.

- Test decision: tests-after with focused unit tests for each new module plus end-to-end smoke fixtures. TDD is preferred for validator/schema modules where interfaces are clear.
- QA policy: Every task has happy-path and failure/edge-case scenarios with concrete commands.
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`.

## Architecture Decisions

### Generic Validator Authority
The generic PDDL parser/grounder/replay validator is the correctness authority for all emitted examples. Planner adapters only produce candidate traces/plans. A candidate becomes supervised data only when replay validation confirms every action is applicable and the final state satisfies the goal.

### No Fabrication and Fidelity Semantics
Controlled planner statuses:
- `success_full_trace`: actual search/trace internals were captured, e.g. BFS queue/visited/successor events.
- `success_plan_replayed`: planner produced a final plan; generic validator replayed it into state transitions; no claim of internal search trace.
- `skipped_planner_unavailable`
- `skipped_unsupported_pddl`
- `skipped_grounding_limit`
- `skipped_resource_limit`
- `failed_parse_domain`
- `failed_parse_problem`
- `failed_grounding`
- `failed_planner_timeout`
- `failed_planner_error`
- `failed_no_plan_extracted`
- `failed_action_normalization`
- `failed_replay_invalid_action`
- `failed_replay_goal_not_satisfied`
- `failed_vision_missing`
- `failed_schema_validation`

Controlled vision statuses:
- `vision_available_step_aligned`
- `vision_available_unaligned`
- `vision_missing_result_json`
- `vision_missing_trace_vfg`
- `vision_missing_frames`
- `vision_unreadable_frames`
- `vision_action_mismatch`
- `vision_not_required_for_text_only_example`

### Resource Limits
Implement config defaults in `generation_manifest.json` and CLI flags:
- Planner timeout: `60` seconds per planner attempt.
- Parser/grounding timeout: `60` seconds per instance.
- Max grounded actions: `100000`.
- Max grounded atoms: `100000`.
- BFS max expansions: `50000`.
- BFS max depth: `200`.
- Max plan length: `500`.
- Max trace steps emitted per example: `500`.
- Max JSONL target characters per example: `65536`; longer successful plans remain diagnostics-only with `skipped_resource_limit` for supervision emission.

### Supported PDDL Fragment
Initial supported fragment for replay validation: typed STRIPS with objects, constants, positive predicates, conjunctive positive preconditions, add/delete effects, and conjunctive positive goals. Preflight must detect and classify unsupported constructs including negative preconditions, quantified preconditions/effects, conditional effects, derived predicates, numeric fluents, disjunction, equality semantics requiring special handling, and non-STRIPS constructs.

### External Planner Adapter Contract
Every external planner adapter must define:
- input domain/problem file paths,
- command template,
- timeout,
- expected stdout/stderr/plan-file behavior,
- action extraction rule,
- version capture command if available,
- controlled failure mapping,
- exact normalization rule into canonical action strings,
- replay validation handoff.

FF/IW/Graphplan adapters may produce `success_plan_replayed` when they provide a valid plan; they may only produce `success_full_trace` if true internal trace extraction is implemented and verified.

Default planner lookup rules are fixed:
- FF adapter first tries `PHASE3_FF_PLANNER`; if unset, it tries repo-relative `modules/downward/fast-downward.py` with a Fast-Forward-style alias/config if available; if no executable command is available, emit `skipped_planner_unavailable`.
- IW adapter first tries `PHASE3_IW_PLANNER`; if unset, it tries repo-relative `modules/downward/fast-downward.py` with an IW-style alias/config if available; if no executable command is available, emit `skipped_planner_unavailable`.
- Graphplan adapter first tries `PHASE3_GRAPHPLAN_PLANNER`; if unset, it emits `skipped_planner_unavailable` unless a repo-local Graphplan executable is discovered by an explicit config file added by the implementer.
- Environment variable values are command paths only, not secrets. Record the resolved command path and arguments in diagnostics using repo-relative paths when possible.

### Duplicate Plan Policy
Preserve multiple planner examples for the same instance even if `plan_hash` is identical, because planner/source labels are distinct supervision metadata. Deduplication is not performed in Phase 3; downstream filtering can use `plan_hash`.

## Execution Strategy

### Parallel Execution Waves
Wave 1: Tasks 1-5 foundation: corpus accounting, schema/status contract, PDDL preflight, generic validator, vision validation.
Wave 2: Tasks 6-9 planner adapters and example builder: BFS, external planner adapters, JSONL builder, reporting/determinism.
Wave 3: Tasks 10-12 integration: registry JSONL config, verification CLIs/tests, docs/status.
Wave 4: Final verification wave F1-F4.

### Dependency Matrix
- Task 1 blocks Tasks 3, 5, 8, 9, 11.
- Task 2 blocks Tasks 6, 7, 8, 9, 10, 11.
- Task 3 blocks Tasks 4, 6, 7, 8, 11.
- Task 4 blocks Tasks 6, 7, 8, 11.
- Task 5 blocks Task 8 and Task 11.
- Task 6 blocks Task 8 and Task 11.
- Task 7 blocks Task 8 and Task 11.
- Task 8 blocks Tasks 9, 10, 11.
- Task 9 blocks Task 11.
- Task 10 blocks Task 11.
- Task 11 blocks Task 12 and final verification.
- Task 12 blocks final verification.

### Agent Dispatch Summary
- Wave 1 → 5 tasks → categories: deep, quick, deep, deep, quick.
- Wave 2 → 4 tasks → categories: deep, deep, deep, unspecified-high.
- Wave 3 → 3 tasks → categories: quick, unspecified-high, writing.
- Wave 4 → 4 final reviews → oracle, unspecified-high, unspecified-high, deep.

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. Build curriculum manifest and instance accounting loader

  **What to do**: Implement the Phase 3 loader that reads `data/curriculum_pddl/accepted_manifest.jsonl` as the sole accepted-instance source, validates `summary.json` and `rejections.jsonl` presence when available, resolves per-instance `domain.pddl`, `problem.pddl`, `render/result.json`, `render/trace.vfg.json`, and `render/frames/*.png`, and writes `data/phase3_supervised_planning/diagnostics/instance_accounting.jsonl`. Each accepted row must produce exactly one accounting record with source paths, split, domain, asset availability, and controlled vision status. Do not use directory listing as inclusion source.

  **Must NOT do**: Must not mutate `data/curriculum_pddl`; must not use `outputs/planning_artifacts`; must not silently skip missing files.

  **Recommended Agent Profile**:
  - Category: `deep` - Requires careful source-of-truth semantics and manifest/path reconciliation.
  - Skills: [] - No specialized skill required.
  - Omitted: [`git-master`] - No git operation required.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 3, 5, 8, 9, 11 | Blocked By: none

  **References**:
  - Pattern: `examples/planning_benchmark_slice/README.md:11-38` - Existing accepted-manifest loader/output/failure contract.
  - Config: `src/data_collect/configs/curriculum_15_domains.yaml:22-47` - Expected split totals per domain.
  - Config: `src/data_collect/configs/curriculum_15_domains.yaml:48-138` - Canonical 15-domain list.

  **Acceptance Criteria**:
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.build_instance_accounting --input-root data/curriculum_pddl --output-root data/phase3_supervised_planning --json` exits `0` and writes `diagnostics/instance_accounting.jsonl`.
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_manifest_coverage --accepted-manifest data/curriculum_pddl/accepted_manifest.jsonl --diagnostics data/phase3_supervised_planning/diagnostics/instance_accounting.jsonl` exits `0` with `missing_from_diagnostics = 0`.
  - [ ] Unit tests include missing `domain.pddl`, missing `render/frames`, and duplicate instance ID across domains.

  **QA Scenarios**:
  ```
  Scenario: Accepted manifest coverage
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_manifest_coverage --accepted-manifest data/curriculum_pddl/accepted_manifest.jsonl --diagnostics data/phase3_supervised_planning/diagnostics/instance_accounting.jsonl
    Expected: Exit 0; missing_from_diagnostics = 0; unexpected_extra_instances = 0.
    Evidence: .sisyphus/evidence/task-1-manifest-coverage.txt

  Scenario: Missing render artifact is diagnostic, not silent skip
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_instance_accounting.py -k missing_render_artifact
    Expected: Exit 0; test asserts controlled vision status such as vision_missing_frames or vision_missing_trace_vfg.
    Evidence: .sisyphus/evidence/task-1-missing-render.txt
  ```

  **Commit**: NO | Message: `feat(phase3): add curriculum instance accounting` | Files: implementation and tests only

- [ ] 2. Define Phase 3 schemas, status taxonomy, and output contract

  **What to do**: Implement pure-Python stdlib validation for `supervised_planning_example`, `planner_attempt`, and `instance_accounting` using schema constants in `scripts/phase3/schema.py`; do not add new third-party dependencies. Materialize equivalent JSON Schema documents under `data/phase3_supervised_planning/schema/` during generation. Enforce controlled planner statuses and vision statuses exactly as defined in this plan. Every example must have `model_facing`, `supervised_target`, and `evaluation_metadata`.

  **Must NOT do**: Must not allow free-text primary statuses; must not store absolute local paths; must not embed supervised target inside `model_facing`.

  **Recommended Agent Profile**:
  - Category: `quick` - Mostly schema/data-contract implementation with existing patterns.
  - Skills: [] - No specialized skill required.
  - Omitted: [`secret-guard`] - No secret handling.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 6, 7, 8, 9, 10, 11 | Blocked By: none

  **References**:
  - Pattern: `examples/planning_benchmark_slice/trajectory_schema.py:14-58` - Required field and algorithm-specific validation pattern.
  - Pattern: `examples/planning_benchmark_slice/modality_serializers.py:206-220` - Existing `model_facing` / metadata structure.
  - Pattern: `examples/planning_benchmark_slice/modality_serializers.py:114-203` - Leakage validation strategy.

  **Acceptance Criteria**:
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.validate_jsonl_schema --schema data/phase3_supervised_planning/schema/supervised_planning_example.schema.json --jsonl data/phase3_supervised_planning/train.jsonl --jsonl data/phase3_supervised_planning/dev.jsonl --jsonl data/phase3_supervised_planning/test.jsonl` exits `0` after dataset generation.
  - [ ] Tests reject unknown planner status, unknown vision status, absolute path values, and missing `evaluation_metadata`.

  **QA Scenarios**:
  ```
  Scenario: Schema accepts valid generated examples
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.validate_jsonl_schema --schema data/phase3_supervised_planning/schema/supervised_planning_example.schema.json --jsonl data/phase3_supervised_planning/train.jsonl --jsonl data/phase3_supervised_planning/dev.jsonl --jsonl data/phase3_supervised_planning/test.jsonl
    Expected: Exit 0; invalid_rows = 0.
    Evidence: .sisyphus/evidence/task-2-schema-validation.txt

  Scenario: Invalid status is rejected
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_schema.py -k invalid_status
    Expected: Exit 0; invalid planner/vision statuses fail validation.
    Evidence: .sisyphus/evidence/task-2-invalid-status.txt
  ```

  **Commit**: NO | Message: `feat(phase3): define supervised planning schemas` | Files: implementation and tests only

- [ ] 3. Implement PDDL feature preflight and canonical action normalization

  **What to do**: Add a preflight scanner for every accepted instance/domain that records supported and unsupported PDDL constructs into `diagnostics/pddl_feature_preflight.jsonl`. Implement canonical action string normalization shared by planner adapters and replay validator. The scanner must classify unsupported constructs without crashing the full build.

  **Must NOT do**: Must not assume all 15 domains are STRIPS-compatible; must not let an external planner success bypass generic replay compatibility.

  **Recommended Agent Profile**:
  - Category: `deep` - Multi-domain PDDL feature classification is failure-prone.
  - Skills: [] - No specialized skill required.
  - Omitted: [`playwright`] - No browser/UI work.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 4, 6, 7, 8, 11 | Blocked By: 1

  **References**:
  - Source: `src/data_collect/configs/curriculum_15_domains.yaml:48-138` - Domains to preflight.
  - Pattern: `examples/planning_benchmark_slice/trajectory_schema.py:84-128` - Canonicalization pattern.

  **Acceptance Criteria**:
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.preflight_pddl_features --input-root data/curriculum_pddl --accounting data/phase3_supervised_planning/diagnostics/instance_accounting.jsonl --output data/phase3_supervised_planning/diagnostics/pddl_feature_preflight.jsonl --json` exits `0`.
  - [ ] Output includes one preflight row per accepted instance and controlled unsupported-feature lists.
  - [ ] Tests cover typed STRIPS success, unsupported negative precondition, unsupported conditional effect, and action case/parenthesis normalization.

  **QA Scenarios**:
  ```
  Scenario: Preflight all accounted instances
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.preflight_pddl_features --input-root data/curriculum_pddl --accounting data/phase3_supervised_planning/diagnostics/instance_accounting.jsonl --output data/phase3_supervised_planning/diagnostics/pddl_feature_preflight.jsonl --json
    Expected: Exit 0; JSON reports rows_written equals accepted instance accounting count.
    Evidence: .sisyphus/evidence/task-3-pddl-preflight.txt

  Scenario: Unsupported feature maps to controlled status
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_pddl_preflight.py -k unsupported_feature_status
    Expected: Exit 0; unsupported constructs become skipped_unsupported_pddl in planner attempts.
    Evidence: .sisyphus/evidence/task-3-unsupported-feature.txt
  ```

  **Commit**: NO | Message: `feat(phase3): add pddl preflight and action normalization` | Files: implementation and tests only

- [ ] 4. Implement generic PDDL grounding, transition, and replay validator

  **What to do**: Implement typed STRIPS grounding and replay validation over the supported PDDL fragment. Validator must parse initial state/goals, ground applicable actions within resource limits, apply add/delete effects, validate action sequences, handle zero-length plans, and emit `diagnostics/replay_validation.jsonl` rows. It is the only correctness authority for supervised emission.

  **Must NOT do**: Must not accept a planner output without replay; must not continue past resource limits without controlled status; must not implement unsupported PDDL features as partial guesses.

  **Recommended Agent Profile**:
  - Category: `deep` - Core correctness-critical symbolic layer.
  - Skills: [] - No specialized skill required.
  - Omitted: [`frontend-codex`] - No UI work.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 6, 7, 8, 11 | Blocked By: 3

  **References**:
  - Pattern: `examples/planning_benchmark_slice/experts/bfs.py:80-138` - Existing state ID, successor, and action transition recording pattern, but Blocksworld-only.
  - Pattern: `examples/planning_benchmark_slice/trajectory_schema.py:131-196` - Validation result payload pattern.

  **Acceptance Criteria**:
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_replay_validator.py` exits `0`.
  - [ ] Tests cover valid plan replay, invalid precondition, goal not satisfied, zero-length solved instance, action normalization failure, and grounding limit.
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_replay_validated_examples --dataset-root data/phase3_supervised_planning` exits `0` after dataset generation.

  **QA Scenarios**:
  ```
  Scenario: Valid replay reaches goal
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_replay_validator.py -k valid_plan_reaches_goal
    Expected: Exit 0; replay_ok true and goal_satisfied true.
    Evidence: .sisyphus/evidence/task-4-valid-replay.txt

  Scenario: Invalid action cannot become supervision
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_replay_validator.py -k invalid_action_rejected
    Expected: Exit 0; invalid action maps to failed_replay_invalid_action and no example is emitted.
    Evidence: .sisyphus/evidence/task-4-invalid-action.txt
  ```

  **Commit**: NO | Message: `feat(phase3): add generic replay validator` | Files: implementation and tests only

- [ ] 5. Validate Planimation vision supervision assets and alignment

  **What to do**: Implement vision validation that checks `render/result.json`, `render/trace.vfg.json`, frame existence/readability, frame count, action count, and best-effort step alignment. Write `diagnostics/vision_validation.jsonl`. Examples may set `vision_supervision_available = true` only for readable assets; step-aligned status requires verified action/frame alignment.

  **Must NOT do**: Must not regenerate Planimation outputs; must not claim vision completeness if frames are missing/unreadable/misaligned; must not require manual inspection.

  **Recommended Agent Profile**:
  - Category: `quick` - File/path/image validation with clear contract.
  - Skills: [] - No specialized skill required.
  - Omitted: [`playwright`] - No browser needed.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 8, 11 | Blocked By: 1

  **References**:
  - Source contract: `examples/planning_benchmark_slice/README.md:18-25` - Render trace/frames in loader output.
  - Failure contract: `examples/planning_benchmark_slice/README.md:29-38` - Missing render artifact behavior.

  **Acceptance Criteria**:
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_vision_assets --dataset-root data/phase3_supervised_planning` exits `0` after generation.
  - [ ] Tests cover missing `result.json`, missing `trace.vfg.json`, missing frames, unreadable image, and action/frame mismatch.

  **QA Scenarios**:
  ```
  Scenario: Vision assets are readable for vision-enabled examples
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_vision_assets --dataset-root data/phase3_supervised_planning
    Expected: Exit 0; missing_frames = 0 and unreadable_frames = 0 for examples with vision_supervision_available = true.
    Evidence: .sisyphus/evidence/task-5-vision-assets.txt

  Scenario: Missing frames degrade vision status
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_vision_validation.py -k missing_frames
    Expected: Exit 0; status is vision_missing_frames and no vision-complete example is emitted.
    Evidence: .sisyphus/evidence/task-5-missing-frames.txt
  ```

  **Commit**: NO | Message: `feat(phase3): validate planimation vision assets` | Files: implementation and tests only

- [ ] 6. Implement local BFS full-trace adapter over generic validator

  **What to do**: Implement a multi-domain local BFS adapter on top of the generic grounded state layer. Record true full trace fields: queue/frontier events, visited hashes, dequeued state, successor generation, selected plan, expansion count, resource-limit status. Emit `success_full_trace` only when the full BFS trace is captured and replay passes. For large instances, emit controlled timeout/resource/grounding statuses without blocking other planners.

  **Must NOT do**: Must not reuse Blocksworld-only `BlocksworldProblem` as the multi-domain engine; must not sort or corrupt queue semantics; must not require BFS success for dataset completeness.

  **Recommended Agent Profile**:
  - Category: `deep` - Search implementation with resource limits and trace correctness.
  - Skills: [] - No specialized skill required.
  - Omitted: [`git-master`] - No git operation required.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 8, 11 | Blocked By: 2, 3, 4

  **References**:
  - Existing smoke pattern: `examples/planning_benchmark_slice/experts/bfs.py:37-68` - BFS trajectory flow, but Blocksworld-only.
  - Queue trace fields: `examples/planning_benchmark_slice/experts/bfs.py:80-120` - Frontier/visited/successor fields.
  - Guardrail from prior rejection: preserve FIFO semantics; do not sort `frontier_before` or `frontier_after`.

  **Acceptance Criteria**:
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_bfs_adapter.py` exits `0`.
  - [ ] BFS success attempt rows use `success_full_trace` only when queue/visited/successor trace exists and replay validates.
  - [ ] BFS resource-limit rows do not emit supervised examples.

  **QA Scenarios**:
  ```
  Scenario: BFS emits full trace on small supported fixture
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_bfs_adapter.py -k full_trace_success
    Expected: Exit 0; status success_full_trace; replay_ok true; FIFO frontier order preserved.
    Evidence: .sisyphus/evidence/task-6-bfs-full-trace.txt

  Scenario: BFS grounding/search limit is controlled
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_bfs_adapter.py -k resource_limit
    Expected: Exit 0; status skipped_resource_limit or skipped_grounding_limit; no supervised example emitted.
    Evidence: .sisyphus/evidence/task-6-bfs-resource-limit.txt
  ```

  **Commit**: NO | Message: `feat(phase3): add generic bfs trace adapter` | Files: implementation and tests only

- [ ] 7. Implement FF, IW, and Graphplan external planner adapters with replay validation

  **What to do**: Implement adapters for FF, IW, and Graphplan using the fixed lookup rules in the External Planner Adapter Contract section: `PHASE3_FF_PLANNER`, `PHASE3_IW_PLANNER`, `PHASE3_GRAPHPLAN_PLANNER`, with Fast Downward fallback only for FF/IW when the repo-local command exists. Each adapter must detect unavailable binaries, record exact command/version/timeout/stdout/stderr digest, extract a canonical action list, normalize actions, replay through the generic validator, and map outcomes to controlled statuses. If exact internal traces are unavailable, successful outputs must be `success_plan_replayed`.

  **Must NOT do**: Must not claim external final-plan-only output is full trace; must not fail the whole dataset if a binary is missing; must not parse planner output into supervision without replay.

  **Recommended Agent Profile**:
  - Category: `deep` - External adapter failure modes and replay integration are complex.
  - Skills: [] - No specialized skill required.
  - Omitted: [`github-cli`] - No remote GitHub inspection required.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 8, 11 | Blocked By: 2, 3, 4

  **References**:
  - Existing FF limitation: `examples/planning_benchmark_slice/experts/fast_forward.py:27-42` and `:72-79` - P0 approximation, not true FF.
  - Existing IW limitation: `examples/planning_benchmark_slice/experts/iterated_width.py:45-81` - Blocksworld-only generator.
  - Existing Graphplan limitation: `examples/planning_benchmark_slice/experts/graphplan.py:41-49` and `:154-160` - P0 action-mutex-only approximation.
  - External planner candidate root: `modules/downward` - Vendored planner exists but explicit trace extraction is not assumed.

  **Acceptance Criteria**:
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_external_planner_adapters.py` exits `0`.
  - [ ] Missing planner binaries produce `skipped_planner_unavailable` records.
  - [ ] Timeout produces `failed_planner_timeout` or `skipped_resource_limit` according to adapter phase.
  - [ ] Valid extracted plan replay produces `success_plan_replayed` and emitted examples.
  - [ ] Invalid extracted plan produces replay failure status and no example.

  **QA Scenarios**:
  ```
  Scenario: External planner replay success emits replay fidelity
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_external_planner_adapters.py -k replay_success
    Expected: Exit 0; status success_plan_replayed; validation_authority is generic_replay_validator.
    Evidence: .sisyphus/evidence/task-7-external-replay-success.txt

  Scenario: Missing planner binary is nonfatal diagnostic
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_external_planner_adapters.py -k planner_unavailable
    Expected: Exit 0; status skipped_planner_unavailable; dataset generation continues for other planners.
    Evidence: .sisyphus/evidence/task-7-planner-unavailable.txt
  ```

  **Commit**: NO | Message: `feat(phase3): add external planner replay adapters` | Files: implementation and tests only

- [ ] 8. Build JSONL supervised example emitter and split writer

  **What to do**: Implement the main generation CLI that joins instance accounting, PDDL preflight, planner attempt results, replay validation, and vision validation into split JSONL files: `train.jsonl`, `dev.jsonl`, `test.jsonl`. Each row is one `(instance_id, planner)` supervised example for successful replay-validated attempts. Preserve duplicate plans across planners. Include `trace_fidelity`, `vision_supervision_available`, portable source paths, and modality-safe `model_facing`.

  **Must NOT do**: Must not emit examples for failed/skipped attempts; must not leak target actions into vision-only `model_facing`; must not derive splits nondeterministically.

  **Recommended Agent Profile**:
  - Category: `deep` - Central data product assembly with leakage and split correctness.
  - Skills: [] - No specialized skill required.
  - Omitted: [`ui-ux-pro-max`] - No UI work.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 9, 10, 11 | Blocked By: 1, 2, 4, 5, 6, 7

  **References**:
  - Pattern: `examples/planning_benchmark_slice/modality_serializers.py:44-104` - JSONL serialization and summary counts.
  - Pattern: `examples/planning_benchmark_slice/modality_serializers.py:114-203` - Modality leakage checks.
  - Pattern: `examples/planning_benchmark_slice/modality_serializers.py:206-220` - Record construction fields.

  **Acceptance Criteria**:
  - [ ] Main generation command exits `0` and writes split JSONL plus summary files.
  - [ ] Schema validation command exits `0` with `invalid_rows = 0`.
  - [ ] Split verification exits `0` with no overlaps.
  - [ ] No smoke references verification exits `0`.

  **QA Scenarios**:
  ```
  Scenario: Generate JSONL training-ready corpus
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.generate_supervised_data --input-root data/curriculum_pddl --output-root data/phase3_supervised_planning --planners bfs ff iw graphplan --json
    Expected: Exit 0; train.jsonl, dev.jsonl, test.jsonl, summary.json, generation_manifest.json are written.
    Evidence: .sisyphus/evidence/task-8-generate-corpus.txt

  Scenario: No smoke artifact contamination
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_no_smoke_sources --dataset-root data/phase3_supervised_planning --forbidden-path outputs/planning_artifacts --forbidden-path examples/planning_benchmark_slice/experts
    Expected: Exit 0; forbidden_references = 0.
    Evidence: .sisyphus/evidence/task-8-no-smoke.txt
  ```

  **Commit**: NO | Message: `feat(phase3): emit supervised planning jsonl corpus` | Files: implementation and tests only

- [ ] 9. Add reports, summaries, and deterministic generation manifest

  **What to do**: Write `generation_manifest.json`, `summary.json`, and reports for domain coverage, split coverage, planner status summary, and fidelity summary. Record config, resource limits, stable sorting rules, planner versions/commands, generated file digests, and allowed nondeterministic fields. Implement deterministic re-run verification.

  **Must NOT do**: Must not include absolute local paths; must not include timestamps in fields used for determinism comparisons unless explicitly ignored.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Cross-cutting reproducibility/reporting.
  - Skills: [] - No specialized skill required.
  - Omitted: [`playwright`] - No browser/UI work.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 11 | Blocked By: 1, 8

  **References**:
  - Pattern: `examples/planning_benchmark_slice/modality_serializers.py:64-104` - Summary payload counts and output paths.
  - Source: `src/data_collect/configs/curriculum_15_domains.yaml:22-47` - Split totals expected from config.

  **Acceptance Criteria**:
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_domain_coverage --accepted-manifest data/curriculum_pddl/accepted_manifest.jsonl --dataset-root data/phase3_supervised_planning --domains 15puzzle blocksworld depot driverlog elevators ferry freecell grid gripper logistics snake sokoban storage towers_of_hanoi visitall` exits `0`.
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_determinism --dataset-root data/phase3_supervised_planning --manifest data/phase3_supervised_planning/generation_manifest.json` exits `0`.

  **QA Scenarios**:
  ```
  Scenario: Domain coverage report includes all domains
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_domain_coverage --accepted-manifest data/curriculum_pddl/accepted_manifest.jsonl --dataset-root data/phase3_supervised_planning --domains 15puzzle blocksworld depot driverlog elevators ferry freecell grid gripper logistics snake sokoban storage towers_of_hanoi visitall
    Expected: Exit 0; all 15 domains present in diagnostics.
    Evidence: .sisyphus/evidence/task-9-domain-coverage.txt

  Scenario: Determinism verification passes
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_determinism --dataset-root data/phase3_supervised_planning --manifest data/phase3_supervised_planning/generation_manifest.json
    Expected: Exit 0; stable IDs, split assignment, ordering, and plan hashes.
    Evidence: .sisyphus/evidence/task-9-determinism.txt
  ```

  **Commit**: NO | Message: `feat(phase3): add coverage reports and determinism checks` | Files: implementation and tests only

- [ ] 10. Add JSONL registry/config integration without tensor conversion

  **What to do**: Add or update registry/config surfaces so the Phase 3 JSONL corpus can be discovered as JSONL training-ready data, while explicitly avoiding StarVLA/LeRobot tensor conversion. Use names that cannot collide with the smoke Blocksworld names, such as `planning_phase3_supervised_jsonl` and `planning_phase3_supervised_all`. Ensure registry discovery still preserves optional dependency allowlist behavior.

  **Must NOT do**: Must not alter final output root; must not replace smoke tests unless needed; must not claim continuous robot action tensor support.

  **Recommended Agent Profile**:
  - Category: `quick` - Registry/config extension using existing tests.
  - Skills: [] - No specialized skill required.
  - Omitted: [`git-master`] - No git operation required.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 11 | Blocked By: 2, 8

  **References**:
  - Existing smoke registry: `examples/planning_benchmark_slice/train_files/data_registry/data_config.py:31-34` and `:91-105`.
  - Existing registry tests: `tests/planning_benchmark/test_dataset_registry.py:28-76`.
  - Optional dependency guard tests: `tests/planning_benchmark/test_dataset_registry.py:79-115`.

  **Acceptance Criteria**:
  - [ ] Registry tests for new Phase 3 names pass.
  - [ ] Existing smoke registry tests still pass.
  - [ ] New config points to `data/phase3_supervised_planning/train.jsonl`, `dev.jsonl`, and `test.jsonl`, not `outputs/planning_artifacts`.

  **QA Scenarios**:
  ```
  Scenario: Phase 3 JSONL registry names are discovered
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/planning_benchmark/test_dataset_registry.py -k phase3
    Expected: Exit 0; phase3 JSONL mixture and robot/data type names are unique and discovered.
    Evidence: .sisyphus/evidence/task-10-phase3-registry.txt

  Scenario: Optional dependency guards still reraises internal imports
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/planning_benchmark/test_dataset_registry.py -k missing_imports
    Expected: Exit 0; internal ModuleNotFoundError is not swallowed.
    Evidence: .sisyphus/evidence/task-10-registry-import-guards.txt
  ```

  **Commit**: NO | Message: `feat(phase3): register supervised planning jsonl dataset` | Files: implementation and tests only

- [ ] 11. Implement full verification CLI suite and regression tests

  **What to do**: Implement all verification CLIs listed in Definition of Done and comprehensive tests under `tests/phase3/`. Include happy and failure fixtures for manifest coverage, planner attempts, schema, replay, fidelity labels, split integrity, domain coverage, vision assets, smoke exclusion, determinism, zero-length plans, duplicate plans, unsupported PDDL, resource limits, and missing planner binaries. Test fixtures are allowed only as explicit tests and must be clearly marked as fixtures, not production data.

  **Must NOT do**: Must not rely on manual inspection; must not use dummy production data; must not skip expensive full-corpus checks without a smoke alternative and a full command.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Broad verification harness across all pipeline components.
  - Skills: [] - No specialized skill required.
  - Omitted: [`playwright`] - No browser/UI work.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: 12, final verification | Blocked By: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10

  **References**:
  - Pattern: `tests/planning_benchmark/test_dataset_registry.py:28-115` - Existing planning tests and import-guard regression style.
  - Pattern: `examples/planning_benchmark_slice/trajectory_schema.py:174-209` - Validation summary payload style.

  **Acceptance Criteria**:
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3 tests/planning_benchmark tests/data_collect` exits `0`.
  - [ ] Every Definition of Done verification command exits `0` on generated corpus.
  - [ ] Failure tests prove invalid examples do not enter JSONL.

  **QA Scenarios**:
  ```
  Scenario: Full Phase 3 and regression tests pass
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3 tests/planning_benchmark tests/data_collect
    Expected: Exit 0; all Phase 3 tests and existing planning/data_collect regressions pass.
    Evidence: .sisyphus/evidence/task-11-full-tests.txt

  Scenario: Verification suite detects seeded invalid replay
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_verify_replay_validated_examples.py -k detects_failed_replay
    Expected: Exit 0; verifier rejects generated row with failed replay metadata.
    Evidence: .sisyphus/evidence/task-11-detect-failed-replay.txt
  ```

  **Commit**: NO | Message: `test(phase3): add supervised data verification suite` | Files: implementation and tests only

- [ ] 12. Document complete Phase 3 status, commands, and scope boundaries

  **What to do**: Create `doc/detailed_implementation_summary/phase3_complete_supervised_planning_data_summary.md` documenting the new corpus root, generation command, verification commands, status taxonomy, fidelity semantics, known unsupported/failed planner counts, and explicit distinction from the old Blocksworld smoke artifacts. If `doc/high_level_plans/research_execution_plan.md` currently marks Phase 3 complete only for Blocksworld/P0, update wording to distinguish old smoke completion from complete multi-domain Phase 3 status after verification passes.

  **Must NOT do**: Must not claim universal planner success; must not claim Phase 4 training is done; must not omit commands required to regenerate/verify.

  **Recommended Agent Profile**:
  - Category: `writing` - Documentation and status clarity.
  - Skills: [] - No specialized skill required.
  - Omitted: [`github-cli`] - No remote GitHub inspection required.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: final verification | Blocked By: 11

  **References**:
  - Prior smoke docs: `examples/planning_benchmark_slice/README.md:39-79` - Old smoke commands and scope, must be distinguished from complete Phase 3.
  - User rule in repository README: implementation summaries should be saved in `doc/detailed_implementation_summary` with commands.

  **Acceptance Criteria**:
  - [ ] Documentation includes exact generation command and all verification commands from Definition of Done.
  - [ ] Documentation states `outputs/planning_artifacts/**` is smoke/prototype only, not final Phase 3.
  - [ ] Documentation includes final per-status counts from `data/phase3_supervised_planning/summary.json`.

  **QA Scenarios**:
  ```
  Scenario: Documentation contains required commands and corpus root
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_docs_phase3_summary.py
    Expected: Exit 0; doc mentions data/phase3_supervised_planning, generate_supervised_data, and all verifier module names.
    Evidence: .sisyphus/evidence/task-12-docs-summary.txt

  Scenario: Documentation does not overclaim planner completeness
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_docs_phase3_summary.py -k no_overclaim
    Expected: Exit 0; doc distinguishes attempted/accounted complete from all-planners-successful.
    Evidence: .sisyphus/evidence/task-12-docs-no-overclaim.txt
  ```

  **Commit**: NO | Message: `docs(phase3): document complete supervised planning corpus` | Files: docs and tests only

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.

- [ ] F1. Plan Compliance Audit — oracle
  - Verify the implementation satisfies every Must Have/Must NOT Have and every task acceptance criterion.
  - Required evidence: `.sisyphus/evidence/f1-plan-compliance.md`.

- [ ] F2. Code Quality Review — unspecified-high
  - Review maintainability, schema design, parser/validator boundaries, adapter failure handling, deterministic output, and registry import guards.
  - Required evidence: `.sisyphus/evidence/f2-code-quality.md`.

- [ ] F3. Real Manual QA — unspecified-high
  - Execute the full generation command and every Definition of Done verifier command in the environment; inspect generated summaries and diagnostics by command output only.
  - Required evidence: `.sisyphus/evidence/f3-real-qa.md`.

- [ ] F4. Scope Fidelity Check — deep
  - Confirm no Phase 4 training, no LeRobot tensor conversion, no mutation of `data/curriculum_pddl`, no reliance on `outputs/planning_artifacts`, and no fabricated traces.
  - Required evidence: `.sisyphus/evidence/f4-scope-fidelity.md`.

## Commit Strategy
- Do not commit unless the user explicitly requests it.
- If asked to commit, use small reviewable commits by wave:
  - `feat(phase3): add curriculum accounting and schemas`
  - `feat(phase3): add pddl replay validation and planner adapters`
  - `feat(phase3): emit supervised planning jsonl corpus`
  - `test(phase3): add verification suite`
  - `docs(phase3): document complete supervised planning corpus`
- Before any commit, run secret scan/guard per repo policy and inspect git status/diff/log.

## Success Criteria
- Every row in `data/curriculum_pddl/accepted_manifest.jsonl` appears in `diagnostics/instance_accounting.jsonl`.
- Every accepted instance has BFS, FF, IW, and Graphplan attempt records.
- Every emitted JSONL example validates against schema and replay validation.
- All 15 domains are represented in diagnostics.
- Unsupported/timeouts/failures are explicit machine-readable statuses, not missing rows.
- FF/IW/Graphplan final-plan-only examples are labeled `success_plan_replayed`, not `success_full_trace`.
- Vision-enabled examples reference readable Planimation assets using portable relative paths.
- Generated records contain no references to `outputs/planning_artifacts/**` or Blocksworld-only smoke expert source paths.
- Full test and verifier suite passes with zero manual inspection.
- Documentation clearly states generated corpus root, commands, status counts, fidelity semantics, and scope exclusions.
