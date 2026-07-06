# Curriculum PDDL Instance Generation Pipeline

## TL;DR
> **Summary**: The reusable, TDD-backed `src/data_collect` generation pipeline is already implemented and smoke-tested; the remaining Phase 2 work is to validate the 15 existing finalized shards, merge them into `data/curriculum_pddl`, and add the missing minimal `examples/` benchmark slice that loads one real planning instance and emits proposal modality views.
> **Deliverables**: Completed `src/data_collect` package + CLI, YAML curriculum config, adapter layer for 15 mapped domains, deterministic candidate/selection pipeline, per-domain rendered shard outputs, final merged train/dev/test manifests, minimal `examples/planning_benchmark_slice/` package, pytest coverage, smoke/merge/example commands, documentation summary.
> **Effort**: XL
> **Parallel**: YES - 5 waves
> **Critical Path**: Completed generator pipeline → verify 15 finalized shards → merge final 3600-instance dataset → add `examples/` benchmark slice → final verification/docs

## Context
### Original Request
The user wants reusable scripts under `src/data_collect` to generate PDDL problem instances from `modules/pddl-generators`, with a curriculum from easy to hard so a VLA agent can learn the domains successfully.

Confirmed decisions:
- 15-domain curriculum.
- 200 train instances per domain.
- 20 dev + 20 test instances per domain.
- Total accepted target: `15 × (200+20+20) = 3600` rendered instances.
- Train difficulty quotas per domain: `70 easy / 80 medium / 50 hard`.
- Dev difficulty quotas per domain: `7 easy / 8 medium / 5 hard`.
- Test difficulty quotas per domain: `5 easy / 7 medium / 8 hard`.
- Rendering is required for accepted dataset instances.
- Use `uv venv .venv` for generator dependencies.
- Use TDD with `pytest`.

### Interview Summary
- User clarified this is for VLA learning, not just one representative problem per domain.
- User explicitly selected **200 per domain**, not 200 total.
- User selected **15-domain curriculum**, not all 23 Planimation domains.
- User selected **train + dev/test** generation now.
- User selected **rendering required** as an acceptance gate.

### Metis Review (gaps addressed)
Metis identified these risks and this plan addresses them explicitly:
- Difficulty must be defined as a contract, not hand-waved: this plan uses `hybrid_measured_percentile` after rendering, with target parameters recorded and measured bucket assigned from per-domain candidate pools.
- Rendering gate must be executable: accepted instances require `render_status=success`, at least one `trace.vfg.json`, at least one PNG frame, and per-instance `result.json` marking success.
- Generator heterogeneity must be isolated: this plan requires one adapter contract, per-domain adapters, isolated cwd, timeouts, stdout/stderr capture, and output normalization.
- Full generation is too expensive for pytest: this plan separates fast unit tests, small real-generator smoke tests, and full dataset generation.
- `modules/pddl-generators` must be treated as read-only: adapters call it but do not edit vendored files.

### Current Status Update
- Tasks 1-12 are completed and should remain historical completed work.
- `src.data_collect` already exposes `generate`, `inspect-tools`, and `merge-shards`.
- `doc/detailed_implementation_summary/phase2_curriculum_pddl_generation_summary.md` records: `45 passed`, all 15 adapters ready, optional missing `validate`, and a successful rendered smoke generation with 6 accepted instances.
- `data/curriculum_pddl_shards/` exists with 15 domain shard directories: `15puzzle`, `blocksworld`, `depot`, `driverlog`, `elevators`, `ferry`, `freecell`, `grid`, `gripper`, `logistics`, `snake`, `sokoban`, `storage`, `towers_of_hanoi`, `visitall`.
- Representative shard summaries (`data/curriculum_pddl_shards/15puzzle/summary.json` and `data/curriculum_pddl_shards/blocksworld/summary.json`) each report `accepted_total=240`, `domains_completed=1`, train/dev/test counts `200/20/20`, `render_failed_accepted=0`, and `duplicate_accepted_problem_hashes=0`.
- Final merged dataset root `data/curriculum_pddl/summary.json` is not present and remains the primary dataset-finalization gap.
- `examples/` currently only contains `examples/eval_protocol.md`; the original high-level Phase 2 requirement for a planning benchmark package under `examples/` remains unsatisfied.

### Updated Metis Review for Current Status
Metis identified these current-state risks and this plan now addresses them explicitly:
- Do **not** rerun the expensive full 15-domain generation if all finalized shards validate; prefer the existing `merge-shards` path.
- Do **not** assume all 15 shards match the two spot-checked summaries; verify every shard before merging.
- Keep optional external `validate` non-blocking unless the user explicitly changes the requirement.
- Separate dataset finalization from the missing `examples/` benchmark-slice package so completion evidence is unambiguous.
- Keep the benchmark slice minimal: load one real finalized instance and emit existing modality views; do not expand into training, model work, dashboards, or a full evaluation harness.

## Work Objectives
### Core Objective
Complete Phase 2 by finalizing the reproducible rendered curriculum dataset from existing per-domain shards and adding the minimal StarVLA-style planning benchmark slice under `examples/` that can load one real planning instance and emit the proposal's modality views.

### Deliverables
- `src/data_collect/` Python package.
- CLI entrypoint: `python -m src.data_collect generate ...` and `python -m src.data_collect inspect-tools ...`.
- Config file: `src/data_collect/configs/curriculum_15_domains.yaml`.
- Dependency/setup reference: `src/data_collect/configs/generator_dependencies.yaml` or equivalent documented dependency block consumed by `inspect-tools`.
- Domain adapter registry for 15 target domain mappings.
- Planimation render-profile mapping for every selected domain, derived from `data/pddl_instances/manifest.json` when available.
- Metadata schemas for accepted instances and rejected candidates.
- Deterministic split/bucket/seed policy.
- Rendering gate integrated with existing Planimation Phase 1 pipeline patterns.
- Pytest suite under `tests/data_collect/`.
- Documentation summary under `doc/detailed_implementation_summary/phase2_curriculum_pddl_generation_plan_or_summary.md`.
- Final merged dataset root under `data/curriculum_pddl/` produced from `data/curriculum_pddl_shards/` using `python -m src.data_collect merge-shards`.
- Minimal `examples/planning_benchmark_slice/` package that loads one finalized dataset instance and emits real modality views without dummy placeholders.

### Definition of Done (verifiable conditions with commands)
All commands below must be executed with:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && <command>
```

Required success commands:

```bash
python -m pytest tests/data_collect -q
```

```bash
python -m src.data_collect --help
```

```bash
python -m src.data_collect inspect-tools --config src/data_collect/configs/curriculum_15_domains.yaml
```

```bash
python -m src.data_collect generate --config src/data_collect/configs/curriculum_15_domains.yaml --output /tmp/curriculum_pddl_smoke --domains blocksworld,gripper --splits train --quota easy=1,medium=1,hard=1 --seed 123 --max-attempts-per-bucket 10 --require-rendering
```

```bash
python - <<'PY'
import json
from pathlib import Path

root = Path('data/curriculum_pddl_shards')
expected = {
    '15puzzle', 'blocksworld', 'depot', 'driverlog', 'elevators',
    'ferry', 'freecell', 'grid', 'gripper', 'logistics', 'snake',
    'sokoban', 'storage', 'towers_of_hanoi', 'visitall',
}
domains = {p.name for p in root.iterdir() if p.is_dir()}
assert domains == expected, sorted(domains ^ expected)
for domain in sorted(expected):
    summary = json.loads((root / domain / 'summary.json').read_text())
    assert summary['accepted_total'] == 240, (domain, summary.get('accepted_total'))
    assert summary['domains_completed'] == 1, (domain, summary.get('domains_completed'))
    assert summary['accepted_by_split'] == {'dev': 20, 'test': 20, 'train': 200}, (domain, summary.get('accepted_by_split'))
    assert summary['render_failed_accepted'] == 0, domain
    assert summary['duplicate_accepted_problem_hashes'] == 0, domain
print('verified 15 domain shards')
PY
```

```bash
python -m src.data_collect merge-shards --shards-root data/curriculum_pddl_shards --output data/curriculum_pddl --force --json
```

Expected merged `data/curriculum_pddl/summary.json` values:
- `accepted_total: 3600`
- `domains_completed: 15`
- per domain: `train=200`, `dev=20`, `test=20`
- per domain train buckets: `easy=70`, `medium=80`, `hard=50`
- per domain dev buckets: `easy=7`, `medium=8`, `hard=5`
- per domain test buckets: `easy=5`, `medium=7`, `hard=8`
- `render_failed_accepted: 0`
- `duplicate_accepted_problem_hashes: 0`

```bash
python -m examples.planning_benchmark_slice --dataset data/curriculum_pddl --domain blocksworld --split dev --index 0 --json
```

Expected example output:
- real instance identifier from `data/curriculum_pddl/accepted_manifest.jsonl`
- domain PDDL view
- problem PDDL view
- rendered observation view with `render/trace.vfg.json` and at least one `render/frames/*.png`
- language/text description view derived from real metadata/PDDL, not a dummy placeholder

### Must Have
- Config-driven quotas, seed ranges, generator mappings, timeouts, output roots, rendering requirements, and max attempts.
- Config-driven Planimation animation-profile mapping for every selected domain; render readiness fails if a selected domain lacks a compatible profile.
- Deterministic candidate ID generation from `(global_seed, domain_id, split, target_bucket, attempt_index)`.
- Structured rejection logs for every rejected candidate.
- Normalized problem hash deduplication across all accepted splits.
- Per-instance metadata including generator command, generator cwd, stdout/stderr paths, PDDL hashes, render artifact paths, and measured difficulty.
- Resumable generation that skips already accepted instances unless `--force` is passed.
- Merge-first finalization: if all 15 finalized shards validate, produce the final dataset with `merge-shards` rather than rerunning the expensive generator.
- Runnable example benchmark slice under `examples/planning_benchmark_slice/` using real finalized data.

### Must NOT Have
- No VLA model training.
- No edits to `modules/pddl-generators`.
- No generated 3600-instance dataset committed unless explicitly requested later.
- No deletion or overwrite of `data/curriculum_pddl_shards/` without explicit user confirmation.
- No full regeneration of all PDDL instances if finalized shards already pass validation.
- No silent acceptance of unrendered instances.
- No network-hosted rendering dependency in unit tests.
- No human/manual visual inspection as acceptance criteria.
- No dummy placeholder data in the `examples/` benchmark slice.
- No VLA training loop, planner model, dashboard, or broad evaluation harness in this Phase 2 closeout.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: **TDD** with pytest.
- QA policy: Every implementation task has agent-executed scenarios.
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`.
- Fast tests use fake adapters/renderers.
- Smoke tests use a tiny real-generator/rendering quota.
- Full generation has already been split into per-domain shards; current completion uses explicit shard verification plus `merge-shards`, not normal pytest.

## Execution Strategy
### Parallel Execution Waves
Wave 1: Foundation contracts and tests — Tasks 1-3.
Wave 2: Generator adapters and environment checks — Tasks 4-6.
Wave 3: Rendering/difficulty/selection pipeline — Tasks 7-9.
Wave 4: CLI, docs, and generation controls — Tasks 10-12.
Wave 5: Dataset merge, benchmark slice, and verification — Tasks 13-15.

### Dependency Matrix (full, all tasks)
- Task 1 blocks Tasks 2-15.
- Task 2 blocks Tasks 4-11.
- Task 3 blocks Tasks 7-9 and 13.
- Task 4 blocks Tasks 5-6.
- Task 5 blocks Task 13.
- Task 6 blocks Task 13.
- Task 7 blocks Tasks 8-9 and 13.
- Task 8 blocks Task 13.
- Task 9 blocks Task 13.
- Task 10 blocks Tasks 11-15.
- Task 11 blocks Tasks 13 and 15.
- Task 12 blocks Tasks 13 and 15.
- Task 13 blocks Tasks 14-15.
- Task 14 blocks Task 15.

### Agent Dispatch Summary
- Wave 1: 3 tasks → quick/deep.
- Wave 2: 3 tasks → deep/unspecified-high.
- Wave 3: 3 tasks → deep/unspecified-high.
- Wave 4: 3 tasks → quick/writing.
- Wave 5: 3 tasks → unspecified-high/deep/quick.

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [x] 1. Define package skeleton, CLI contract, and test scaffolding

  **What to do**: Create `src/data_collect/` as a Python package with `__init__.py`, `__main__.py`, `cli.py`, and placeholder modules for config, adapters, rendering, selection, metadata, and hashing. Add `tests/data_collect/` with TDD test files. CLI must expose `generate` and `inspect-tools` subcommands even before full implementation.
  **Must NOT do**: Do not implement full generator logic in the CLI file. Do not generate real dataset files outside `/tmp` in tests.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: bounded skeleton + test setup.
  - Skills: `[]` - No specialized skill needed.
  - Omitted: `ui-ux-pro-max` - No UI work.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: Tasks 2-14 | Blocked By: none

  **References**:
  - Pattern: `scripts/planimation_phase1.py` - argparse utility style, summary/result conventions.
  - Test: `tests/test_planimation_phase1.py` - pytest style, tmp_path fixtures, manifest assertions.
  - Draft: `.sisyphus/drafts/curriculum-pddl-instance-generation.md` - confirmed requirements.

  **Acceptance Criteria**:
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect --help` exits `0` and lists `generate` and `inspect-tools`.
  - [ ] `source ~/cd_vlaplan && source .venv/bin/activate && python -m pytest tests/data_collect -q` exits `0` with skeleton tests passing.

  **QA Scenarios**:
  ```
  Scenario: CLI help works
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect --help
    Expected: exit code 0; output contains generate and inspect-tools
    Evidence: .sisyphus/evidence/task-1-cli-help.txt

  Scenario: Unknown subcommand fails cleanly
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect unknown-command
    Expected: nonzero exit; stderr contains usage or invalid choice
    Evidence: .sisyphus/evidence/task-1-cli-error.txt
  ```

  **Commit**: YES | Message: `feat(data): add curriculum generation package skeleton` | Files: `src/data_collect/**`, `tests/data_collect/**`

- [x] 2. Implement curriculum config schema, render-profile mapping, and 15-domain default YAML

  **What to do**: Add config loader and validation for `src/data_collect/configs/curriculum_15_domains.yaml`. The YAML must encode 15 domain mappings, quotas, bucket quotas, seed ranges, output policies, candidate multiplier, timeouts, rendering requirement defaults, and Planimation animation-profile mapping. Add a generator dependency spec under `src/data_collect/configs/generator_dependencies.yaml` or an equivalent config section that `inspect-tools` can read.
  **Must NOT do**: Do not hard-code quotas in orchestration logic; YAML is the source of truth.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: config drives all later work and must be exact.
  - Skills: `[]`.
  - Omitted: `github-cli` - No remote GitHub inspection needed.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: Tasks 4-11 | Blocked By: Task 1

  **References**:
  - Generator dirs: `modules/pddl-generators/blocksworld`, `logistics`, `grid`, `sokoban`, `hanoi`, `npuzzle`, `depots`, `driverlog`, `elevators`, `ferry`, `freecell`, `gripper`, `snake`, `storage`, `visitall`.
  - Existing manifest pattern: `data/pddl_instances/manifest.json` - instance/domain metadata style.
  - Metis directive: config-driven quotas, seed ranges, generator mappings.

  **Acceptance Criteria**:
  - [ ] Config validates 15 domains with mappings: `15puzzle→npuzzle`, `depot→depots`, `towers_of_hanoi→hanoi`, all others exact.
  - [ ] Config includes a render profile mapping for every selected domain; no selected domain has `render_profile_path=null`.
  - [ ] Config includes generator dependency declarations for Python packages and non-Python tools needed by selected adapters.
  - [ ] Per-domain target counts equal `train=200`, `dev=20`, `test=20`.
  - [ ] Per-domain bucket counts equal train `70/80/50`, dev `7/8/5`, test `5/7/8`.
  - [ ] Tests fail if any quota sum is inconsistent.

  **QA Scenarios**:
  ```
  Scenario: Default config validates
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect inspect-tools --config src/data_collect/configs/curriculum_15_domains.yaml --config-only
    Expected: exit code 0; output reports domains=15 and target_accepted_total=3600
    Evidence: .sisyphus/evidence/task-2-config-valid.txt

  Scenario: Invalid quota config fails
    Tool: Bash
    Steps: pytest tests/data_collect/test_config.py -q
    Expected: test covers a malformed tmp YAML where bucket sums do not match split quota and raises validation error
    Evidence: .sisyphus/evidence/task-2-config-tests.txt
  ```

  **Commit**: YES | Message: `feat(data): define curriculum generation config` | Files: `src/data_collect/configs/curriculum_15_domains.yaml`, `src/data_collect/config.py`, `tests/data_collect/test_config.py`

- [x] 3. Define metadata, hashing, rejection, and resumability contracts

  **What to do**: Implement dataclasses or typed dict helpers for accepted instance metadata, rejected candidate metadata, top-level summary, normalized PDDL hashing, deterministic instance IDs, and resume behavior. Instance ID format: `{domain_id}-{split}-{bucket}-{index:04d}`. Candidate ID format: `{domain_id}-{split}-{bucket}-attempt-{attempt_index:06d}`.
  **Must NOT do**: Do not use raw PDDL text hash alone as the only duplicate check; include normalized whitespace/comment-stripped hash at minimum.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: dataset integrity contract.
  - Skills: `[]`.
  - Omitted: `secret-guard` - No secrets expected.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: Tasks 7-9 and 13 | Blocked By: Task 1

  **References**:
  - Pattern: `scripts/planimation_phase1.py` - writes `summary.json` and per-instance `result.json`.
  - Metis directives: structured rejection reasons, normalized PDDL hashing, resumability.

  **Acceptance Criteria**:
  - [ ] Tests prove deterministic IDs from same seed/config.
  - [ ] Tests prove normalized PDDL hash ignores comments and whitespace differences.
  - [ ] Tests prove duplicate accepted hashes are rejected across train/dev/test.
  - [ ] Tests prove resume mode does not overwrite accepted metadata unless `--force`.

  **QA Scenarios**:
  ```
  Scenario: Duplicate normalized problem rejected
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_metadata.py::test_duplicate_normalized_hash_rejected -q
    Expected: exit code 0; duplicate rejection reason equals duplicate_hash
    Evidence: .sisyphus/evidence/task-3-duplicate-test.txt

  Scenario: Resume preserves accepted instance
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_metadata.py::test_resume_does_not_overwrite_without_force -q
    Expected: exit code 0; original result.json content remains unchanged
    Evidence: .sisyphus/evidence/task-3-resume-test.txt
  ```

  **Commit**: YES | Message: `feat(data): add curriculum metadata contracts` | Files: `src/data_collect/metadata.py`, `src/data_collect/hashing.py`, `tests/data_collect/test_metadata.py`

- [x] 4. Implement tool/environment inspection with hard capability reporting

  **What to do**: Implement `inspect-tools` to report availability and versions for `python`, `uv`, `make`, `g++`, `cmake`, generator paths, declared Python packages, planner/validator commands, animation-profile paths, and renderer prerequisites. It must not install tools automatically. It must print exact copy-pastable setup commands for missing declared Python packages using `uv pip install ...`, but leave execution to the user/executor. It must detect that final accepted generation with `--require-rendering` requires rendering capability.
  **Must NOT do**: Do not mutate `.venv` or install packages in `inspect-tools`; it is read-only.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: subprocess/path inspection.
  - Skills: `[]`.
  - Omitted: `git-master` - No git operation.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: Tasks 5-6 and 13 | Blocked By: Tasks 1-2

  **References**:
  - Environment check result: available `python`, `uv`, `make`, `g++`, `cmake`; missing `fast-downward`, `validate`, `scorpion.sif`.
  - Generator root: `modules/pddl-generators/README.md`, `modules/pddl-generators/build_all`, `modules/pddl-generators/tox.ini`.

  **Acceptance Criteria**:
  - [ ] `inspect-tools` exits `0` and writes JSON with tool statuses.
  - [ ] Missing Python packages are reported with an exact suggested `uv pip install ...` command.
  - [ ] Missing optional planner/validator is reported, not hidden.
  - [ ] Missing render profile path for a selected domain is reported as a hard readiness failure for `--require-rendering`.
  - [ ] Missing generator directory causes clear nonzero error.

  **QA Scenarios**:
  ```
  Scenario: Tool report emitted
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect inspect-tools --config src/data_collect/configs/curriculum_15_domains.yaml --json > /tmp/curriculum_tools.json
    Expected: exit code 0; JSON contains python, uv, make, g++, cmake, generator_root
    Evidence: .sisyphus/evidence/task-4-tools.json

  Scenario: Missing generator root fails
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_tools.py::test_missing_generator_root_fails -q
    Expected: exit code 0; error includes missing generator root path
    Evidence: .sisyphus/evidence/task-4-missing-root.txt
  ```

  **Commit**: YES | Message: `feat(data): add curriculum tool inspection` | Files: `src/data_collect/tools.py`, `tests/data_collect/test_tools.py`

- [x] 5. Build adapter interface and fake adapter TDD fixtures

  **What to do**: Define `GeneratorAdapter` contract with methods: `prepare()`, `generate_candidate(spec)`, `normalize_outputs(raw_result)`, and `supports_seed()`. Implement fake adapters for unit tests, including success, invalid PDDL, duplicate output, stdout-only output, and timeout simulation.
  **Must NOT do**: Do not write domain-specific command logic in the main generation loop.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: architecture boundary for heterogeneous generators.
  - Skills: `[]`.
  - Omitted: `frontend-codex` - No UI.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: Task 6 and 13 | Blocked By: Tasks 2-4

  **References**:
  - Metis directive: one adapter contract with per-domain command templates, cwd isolation, timeout, stdout/stderr capture.
  - Generator heterogeneity examples: `modules/pddl-generators/childsnack/child-snack-generator.py` outputs to stdout; `modules/pddl-generators/minigrid/mini_grid.py` writes files.

  **Acceptance Criteria**:
  - [ ] Unit tests prove fake adapter success produces normalized `domain.pddl` and `problem.pddl` paths.
  - [ ] Unit tests prove adapter timeout records `rejection_reason=generator_timeout`.
  - [ ] Unit tests prove stdout-only generator output is captured and normalized.

  **QA Scenarios**:
  ```
  Scenario: Fake adapter success path
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_adapters.py::test_fake_adapter_success -q
    Expected: exit code 0; normalized candidate has domain and problem paths
    Evidence: .sisyphus/evidence/task-5-fake-success.txt

  Scenario: Fake adapter timeout path
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_adapters.py::test_fake_adapter_timeout_rejection -q
    Expected: exit code 0; rejection reason generator_timeout is recorded
    Evidence: .sisyphus/evidence/task-5-timeout.txt
  ```

  **Commit**: YES | Message: `feat(data): define generator adapter contract` | Files: `src/data_collect/adapters/base.py`, `tests/data_collect/test_adapters.py`

- [x] 6. Implement 15 domain adapter mappings with smoke readiness matrix

  **What to do**: Implement domain adapters or command-template adapters for the 15 mappings. Each adapter must define generator path, build/prep command if needed, seed handling, domain file source, problem output discovery, and target-parameter presets. Add a readiness matrix emitted by `inspect-tools`.
  **Must NOT do**: Do not edit `modules/pddl-generators`. Do not silently skip a selected domain.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: heterogeneous generator integration.
  - Skills: `[]`.
  - Omitted: `secret-guard` - No secret handling.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: Task 13 | Blocked By: Task 5

  **References**:
  - Generator directories: `modules/pddl-generators/blocksworld`, `logistics`, `grid`, `sokoban`, `hanoi`, `npuzzle`, `depots`, `driverlog`, `elevators`, `ferry`, `freecell`, `gripper`, `snake`, `storage`, `visitall`.
  - Known generator examples: `modules/pddl-generators/snake/generate.py`, `visitall/grid.c`, `grid/README`, `miconic-simpleadl/README.txt`.

  **Acceptance Criteria**:
  - [ ] `inspect-tools` reports all 15 selected domains as `adapter_configured=true`.
  - [ ] For every selected domain, adapter metadata includes `generator_path`, `domain_file_source`, `seed_policy`, `output_policy`, `build_required`, and `smoke_supported`.
  - [ ] If a real generator cannot be invoked in this environment, the adapter must fail with a structured readiness error before full generation.

  **QA Scenarios**:
  ```
  Scenario: 15 adapters registered
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect inspect-tools --config src/data_collect/configs/curriculum_15_domains.yaml --json > /tmp/adapter_readiness.json
    Expected: exit code 0; JSON has 15 domains and adapter_configured=true for each
    Evidence: .sisyphus/evidence/task-6-adapter-readiness.json

  Scenario: No silent skipped domains
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_domain_registry.py::test_all_config_domains_have_adapters -q
    Expected: exit code 0; configured domain IDs equal adapter registry domain IDs
    Evidence: .sisyphus/evidence/task-6-registry-test.txt
  ```

  **Commit**: YES | Message: `feat(data): register curriculum domain adapters` | Files: `src/data_collect/adapters/**`, `tests/data_collect/test_domain_registry.py`

- [x] 7. Implement rendering gate contract using existing Planimation patterns

  **What to do**: Implement renderer interface with fake renderer tests and real Planimation renderer wrapper. Acceptance contract for final manifests: `render_status=success`, configured animation profile exists, `trace.vfg.json` exists and is non-empty, `frames/` contains at least one `.png`, and per-instance `result.json` exists. Reuse functions/patterns from `scripts/planimation_phase1.py` where safe; do not duplicate network logic without tests. Add a render-compatibility preflight per selected domain before full generation.
  **Must NOT do**: Do not allow accepted final instances with `render_status != success`. Do not require network/hosted service during unit tests.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: existing Planimation caveats and hard acceptance gate.
  - Skills: `[]`.
  - Omitted: `playwright` - Rendering is CLI/file based, not browser interaction.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: Tasks 8-9 and 13 | Blocked By: Tasks 3 and 5

  **References**:
  - Pattern: `scripts/planimation_phase1.py` - PDDL upload, VFG saving, local PNG fallback, output verification.
  - Docs: `doc/detailed_implementation_summary/phase1_planimation_all_domains_validation_summary.md` - hosted endpoint caveats and local renderer claim.
  - Outputs: `outputs/phase1_planimation_png_supported_minus_15puzzle/summary.json` - rendered result schema.

  **Acceptance Criteria**:
  - [ ] Fake renderer success produces `trace.vfg.json`, `frames/frame_000.png`, and result metadata.
  - [ ] Fake renderer failure rejects candidate with `rejection_reason=render_failed`.
  - [ ] Render preflight reports all 15 domains as render-profile configured before full generation starts.
  - [ ] Real rendering smoke command fails early if Planimation endpoint or render dependencies are unavailable, without accepted unrendered instances.

  **QA Scenarios**:
  ```
  Scenario: Fake renderer gates acceptance
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_rendering.py::test_fake_renderer_success_required_for_acceptance -q
    Expected: exit code 0; accepted instance has render_status success and png_count >= 1
    Evidence: .sisyphus/evidence/task-7-render-success.txt

  Scenario: Render failure rejected
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_rendering.py::test_render_failure_rejects_candidate -q
    Expected: exit code 0; render_failed candidate is not in accepted manifest
    Evidence: .sisyphus/evidence/task-7-render-failure.txt
  ```

  **Commit**: YES | Message: `feat(data): add curriculum rendering gate` | Files: `src/data_collect/rendering.py`, `tests/data_collect/test_rendering.py`

- [x] 8. Implement hybrid measured difficulty assignment and stratified selector

  **What to do**: Implement `hybrid_measured_percentile` difficulty policy. Generator target bucket controls candidate parameter preset; measured bucket is assigned after successful generation/rendering using available metrics in this order: render/VFG plan length if available, frame count, object count, grounded action count if available, PDDL object count/predicate count. Per domain and split, select candidates deterministically into bucket quotas using measured metrics. If `difficulty_target != difficulty_measured`, record both and select by measured bucket.
  **Must NOT do**: Do not silently label all generated instances by target bucket without measured evidence.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: core curriculum quality.
  - Skills: `[]`.
  - Omitted: `artistry` - Conventional algorithmic selection.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: Task 13 | Blocked By: Tasks 3 and 7

  **References**:
  - Research findings: difficulty proxies include plan length, object/goal counts, branching factor, dependency chain, visual complexity.
  - Metis directive: difficulty definition must be executable and recorded.

  **Acceptance Criteria**:
  - [ ] Tests assign easy/medium/hard by per-domain percentiles from synthetic metrics.
  - [ ] Tests preserve both `difficulty_target` and `difficulty_measured`.
  - [ ] Tests fill exact quotas and report incomplete buckets when candidate pool is insufficient.

  **QA Scenarios**:
  ```
  Scenario: Percentile difficulty assignment deterministic
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_difficulty.py::test_percentile_assignment_is_deterministic -q
    Expected: exit code 0; repeated input order produces same bucket assignments
    Evidence: .sisyphus/evidence/task-8-difficulty-deterministic.txt

  Scenario: Insufficient hard candidates reported
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_selection.py::test_incomplete_bucket_summary -q
    Expected: exit code 0; summary contains incomplete bucket with requested and accepted counts
    Evidence: .sisyphus/evidence/task-8-incomplete-bucket.txt
  ```

  **Commit**: YES | Message: `feat(data): add curriculum difficulty selection` | Files: `src/data_collect/difficulty.py`, `src/data_collect/selection.py`, `tests/data_collect/test_difficulty.py`, `tests/data_collect/test_selection.py`

- [x] 9. Implement candidate generation orchestration, rejection logs, and resumability

  **What to do**: Implement main generation loop with `max_attempts_per_bucket`, candidate multiplier, split/domain/bucket iteration, adapter execution, render gate, dedupe, selection, accepted manifests, rejected manifests, and resumability. Final accepted output layout: `data/curriculum_pddl/<domain_id>/<split>/<bucket>/<instance_id>/`.
  **Must NOT do**: Do not run full generation automatically in tests. Do not overwrite previous accepted instances without `--force`.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: core orchestrator and data integrity.
  - Skills: `[]`.
  - Omitted: `github-cli` - No GitHub work.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: Task 13 | Blocked By: Tasks 5, 7, 8

  **References**:
  - Existing layout: `outputs/phase1_planimation_vfg_all_domains/<domain>/<problem>/result.json`.
  - Metis guardrails: max attempts, rejection reason accounting, incomplete-status summary.

  **Acceptance Criteria**:
  - [ ] Orchestrator can generate a fake 2-domain × 3-bucket dataset with exact quotas.
  - [ ] Rejected candidates are written to `rejections.jsonl` with structured reasons.
  - [ ] Resume run with same config does not duplicate accepted instances.
  - [ ] `--force` intentionally overwrites output root after explicit flag.

  **QA Scenarios**:
  ```
  Scenario: Fake full orchestrator exact quotas
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_generate_orchestrator.py::test_fake_generation_exact_quotas -q
    Expected: exit code 0; summary accepted counts match requested quotas exactly
    Evidence: .sisyphus/evidence/task-9-fake-quotas.txt

  Scenario: Resume avoids duplication
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_generate_orchestrator.py::test_resume_no_duplicates -q
    Expected: exit code 0; second run has duplicate_accepted_problem_hashes=0 and no extra accepted records
    Evidence: .sisyphus/evidence/task-9-resume.txt
  ```

  **Commit**: YES | Message: `feat(data): orchestrate curriculum generation` | Files: `src/data_collect/generate.py`, `tests/data_collect/test_generate_orchestrator.py`

- [x] 10. Finalize CLI options and concrete commands

  **What to do**: Wire all CLI options: `--config`, `--output`, `--domains`, `--splits`, `--quota`, `--seed`, `--max-attempts-per-bucket`, `--require-rendering`, `--dry-run`, `--force`, `--json`. Ensure help text documents that accepted final manifests require rendering.
  **Must NOT do**: Do not leave placeholder options or undocumented behavior.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: CLI polish and tests.
  - Skills: `[]`.
  - Omitted: `frontend-claude` - No frontend.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: Tasks 11-14 | Blocked By: Task 9

  **References**:
  - Pattern: `scripts/planimation_phase1.py` - argparse commands and flags.
  - Acceptance commands in this plan.

  **Acceptance Criteria**:
  - [ ] `python -m src.data_collect generate --help` lists all required options.
  - [ ] CLI rejects `--require-rendering` combined with fake/no renderer for accepted final mode.
  - [ ] CLI supports smoke override: `--domains blocksworld,gripper --splits train --quota easy=1,medium=1,hard=1`.

  **QA Scenarios**:
  ```
  Scenario: Generate help lists options
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect generate --help
    Expected: exit code 0; output contains --config, --output, --require-rendering, --max-attempts-per-bucket
    Evidence: .sisyphus/evidence/task-10-generate-help.txt

  Scenario: Invalid quota override rejected
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/data_collect/test_cli.py::test_invalid_quota_override_rejected -q
    Expected: exit code 0; invalid quota string raises CLI error
    Evidence: .sisyphus/evidence/task-10-invalid-quota.txt
  ```

  **Commit**: YES | Message: `feat(data): finalize curriculum CLI` | Files: `src/data_collect/cli.py`, `tests/data_collect/test_cli.py`

- [x] 11. Add small real-generator/rendering smoke test command path

  **What to do**: Implement and document smoke path for `blocksworld,gripper`, train split only, one easy/medium/hard per domain, output `/tmp/curriculum_pddl_smoke`, seed `123`, max attempts `10`, rendering required. This command is the primary real integration gate before full generation.
  **Must NOT do**: Do not use all 15 domains in smoke tests. Do not require smoke artifacts to be committed.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: real generator + rendering integration can be flaky.
  - Skills: `[]`.
  - Omitted: `playwright` - CLI/file verification.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: Task 14 | Blocked By: Tasks 6, 7, 10

  **References**:
  - Selected smoke domains: `modules/pddl-generators/blocksworld`, `modules/pddl-generators/gripper`.
  - Existing Planimation smoke style: `outputs/phase1_planimation_png_grid/summary.json`.

  **Acceptance Criteria**:
  - [ ] Smoke command exits `0` when rendering prerequisites are available.
  - [ ] `/tmp/curriculum_pddl_smoke/summary.json` reports `accepted_total=6`.
  - [ ] Each accepted instance has a problem PDDL, result metadata, VFG trace, and at least one PNG frame.
  - [ ] If rendering prerequisites are unavailable, command fails before accepting any unrendered instances.

  **QA Scenarios**:
  ```
  Scenario: Real smoke generation succeeds or fails safely
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect generate --config src/data_collect/configs/curriculum_15_domains.yaml --output /tmp/curriculum_pddl_smoke --domains blocksworld,gripper --splits train --quota easy=1,medium=1,hard=1 --seed 123 --max-attempts-per-bucket 10 --require-rendering
    Expected: exit code 0 with accepted_total=6, OR nonzero before acceptance with clear missing rendering capability error
    Evidence: .sisyphus/evidence/task-11-smoke.txt

  Scenario: Smoke summary exact if successful
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
import json, pathlib
p=pathlib.Path('/tmp/curriculum_pddl_smoke/summary.json')
if p.exists():
    s=json.loads(p.read_text())
    assert s['accepted_total']==6
    assert s['render_failed_accepted']==0
print('checked')
PY
    Expected: exit code 0; prints checked
    Evidence: .sisyphus/evidence/task-11-smoke-summary.txt
  ```

  **Commit**: YES | Message: `test(data): add curriculum smoke path` | Files: `tests/data_collect/test_smoke_contract.py`, docs/command references

- [x] 12. Document generator setup, dataset schema, and non-commit artifact policy

  **What to do**: Add a phase-prefixed implementation/usage document under `doc/detailed_implementation_summary/phase2_curriculum_pddl_generation_summary.md`. Include exact commands, dependency notes, output layout, schema fields, generated-data git policy, and known Planimation rendering caveats.
  **Must NOT do**: Do not claim full dataset is generated until Task 13 succeeds.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: documentation deliverable.
  - Skills: `[]`.
  - Omitted: `secret-guard` - No secrets.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: Task 14 | Blocked By: Task 10

  **References**:
  - Existing doc: `doc/detailed_implementation_summary/phase1_planimation_all_domains_validation_summary.md`.
  - Root rules: `README.md` environment command pattern.
  - Metis scope guardrail: do not commit generated large datasets unless explicitly requested.

  **Acceptance Criteria**:
  - [ ] Document lists all commands needed to setup, test, smoke, and full-generate.
  - [ ] Document explicitly says generated dataset artifacts are local outputs unless user requests committing them.
  - [ ] Document records rendering required acceptance contract.

  **QA Scenarios**:
  ```
  Scenario: Documentation contains required commands
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
from pathlib import Path
p=Path('doc/detailed_implementation_summary/phase2_curriculum_pddl_generation_summary.md')
t=p.read_text()
for s in ['python -m pytest tests/data_collect -q','python -m src.data_collect inspect-tools','python -m src.data_collect generate','--require-rendering']:
    assert s in t
print('doc-ok')
PY
    Expected: exit code 0; prints doc-ok
    Evidence: .sisyphus/evidence/task-12-doc-check.txt

  Scenario: Doc states artifact policy
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
from pathlib import Path
t=Path('doc/detailed_implementation_summary/phase2_curriculum_pddl_generation_summary.md').read_text().lower()
assert 'do not commit' in t or 'local outputs' in t
print('policy-ok')
PY
    Expected: exit code 0; prints policy-ok
    Evidence: .sisyphus/evidence/task-12-policy-check.txt
  ```

  **Commit**: YES | Message: `docs(data): document curriculum generation workflow` | Files: `doc/detailed_implementation_summary/phase2_curriculum_pddl_generation_summary.md`

- [x] 13. Validate finalized shards and merge the final 15-domain curriculum dataset

  **What to do**: Treat the current `data/curriculum_pddl_shards/` directory as the preferred finalization source. First verify that all 15 expected direct child shard roots exist, each has `summary.json`, `accepted_manifest.jsonl`, and `rejections.jsonl`, and each summary reports `accepted_total=240`, `domains_completed=1`, train/dev/test counts `200/20/20`, `render_failed_accepted=0`, and `duplicate_accepted_problem_hashes=0`. If and only if all shards pass, run `python -m src.data_collect merge-shards --shards-root data/curriculum_pddl_shards --output data/curriculum_pddl --force --json`. Capture shard-verification output, merge output, and final summary verification as evidence.
  **Must NOT do**: Do not rerun the expensive full generator unless shard verification fails and the failure requires regeneration. Do not delete or mutate `data/curriculum_pddl_shards/`. Do not commit generated artifact files unless user explicitly asks. Do not make the optional missing `validate` binary a blocker.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: real generated artifacts, global merge integrity, and duplicate-hash checks.
  - Skills: `[]`.
  - Omitted: `git-master` - No commit unless user requests.

  **Parallelization**: Can Parallel: NO | Wave 5 | Blocks: Tasks 14-15 | Blocked By: Tasks 6-12

  **References**:
  - Existing shards root: `data/curriculum_pddl_shards/` - contains 15 expected domain shard directories.
  - Representative shard summaries: `data/curriculum_pddl_shards/15puzzle/summary.json`, `data/curriculum_pddl_shards/blocksworld/summary.json` - observed successful per-domain structure.
  - Merge CLI: `src/data_collect/cli.py:166-198` and `src/data_collect/cli.py:283-314` - `merge-shards` arguments and result output.
  - Merge implementation: `src/data_collect/merge.py:31-109` - verifies finalized shards, copies accepted instances, rewrites metadata, writes merged manifests/summary.
  - Test coverage: `tests/data_collect/test_merge_shards.py` - merge rebasing, duplicate-hash protection, existing-output behavior.

  **Acceptance Criteria**:
  - [ ] Shard verification script exits `0` and prints `verified 15 domain shards`.
  - [ ] Merge command exits `0` and writes `data/curriculum_pddl/summary.json`.
  - [ ] `data/curriculum_pddl/accepted_manifest.jsonl` exists and contains 3600 accepted entries.
  - [ ] `data/curriculum_pddl/rejections.jsonl` exists and contains structured rejection entries.
  - [ ] `data/curriculum_pddl/summary.json` reports `accepted_total=3600`, `domains_completed=15`, train/dev/test counts `3000/300/300`, `render_failed_accepted=0`, and `duplicate_accepted_problem_hashes=0`.
  - [ ] Re-running merge without `--force` or `--resume` against an existing `data/curriculum_pddl` fails clearly rather than silently overwriting.

  **QA Scenarios**:
  ```
  Scenario: Verify all finalized shards before merge
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
import json
from pathlib import Path
root = Path('data/curriculum_pddl_shards')
expected = {
    '15puzzle', 'blocksworld', 'depot', 'driverlog', 'elevators',
    'ferry', 'freecell', 'grid', 'gripper', 'logistics', 'snake',
    'sokoban', 'storage', 'towers_of_hanoi', 'visitall',
}
domains = {p.name for p in root.iterdir() if p.is_dir()}
assert domains == expected, sorted(domains ^ expected)
for domain in sorted(expected):
    shard = root / domain
    for filename in ['summary.json', 'accepted_manifest.jsonl', 'rejections.jsonl']:
        assert (shard / filename).exists(), shard / filename
    summary = json.loads((shard / 'summary.json').read_text())
    assert summary['accepted_total'] == 240, (domain, summary.get('accepted_total'))
    assert summary['domains_completed'] == 1, (domain, summary.get('domains_completed'))
    assert summary['accepted_by_split'] == {'dev': 20, 'test': 20, 'train': 200}, (domain, summary.get('accepted_by_split'))
    assert summary['render_failed_accepted'] == 0, domain
    assert summary['duplicate_accepted_problem_hashes'] == 0, domain
print('verified 15 domain shards')
PY
    Expected: exit code 0; prints verified 15 domain shards
    Evidence: .sisyphus/evidence/task-13-shard-verification.txt

  Scenario: Merge finalized shards
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect merge-shards --shards-root data/curriculum_pddl_shards --output data/curriculum_pddl --force --json
    Expected: exit code 0; JSON output contains summary_path ending in data/curriculum_pddl/summary.json and accepted_total=3600
    Evidence: .sisyphus/evidence/task-13-merge-shards.json

  Scenario: Final merged summary exact count check
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
import json
from pathlib import Path
s=json.loads(Path('data/curriculum_pddl/summary.json').read_text())
assert s['accepted_total']==3600
assert s['domains_completed']==15
assert s['render_failed_accepted']==0
assert s['duplicate_accepted_problem_hashes']==0
assert s['accepted_by_split']=={'dev': 300, 'test': 300, 'train': 3000}
assert len(s['accepted_by_domain'])==15
for domain,count in s['accepted_by_domain'].items():
    assert count==240, (domain, count)
manifest_lines = Path('data/curriculum_pddl/accepted_manifest.jsonl').read_text().splitlines()
assert len(manifest_lines)==3600, len(manifest_lines)
print('full-summary-ok')
PY
    Expected: exit code 0; prints full-summary-ok
    Evidence: .sisyphus/evidence/task-13-summary-check.txt

  Scenario: Existing merge target fails safely without force/resume
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect merge-shards --shards-root data/curriculum_pddl_shards --output data/curriculum_pddl
    Expected: nonzero exit; stderr says output root exists and requires --force or --resume
    Evidence: .sisyphus/evidence/task-13-existing-target-fails.txt
  ```

  **Commit**: NO | Message: `none` | Files: generated artifacts should remain local unless explicitly requested

- [x] 14. Add minimal planning benchmark slice under `examples/`

  **What to do**: Add a narrow runnable example package under `examples/planning_benchmark_slice/` that uses the finalized `data/curriculum_pddl` dataset. The package must load one accepted instance by `--domain`, `--split`, and zero-based `--index`, read real files referenced by the merged manifest, and emit modality views required by high-level Phase 2: initial/problem PDDL text, domain/action-vocabulary source, goal/problem view, rendered observation artifact paths, optional language/text description derived from real metadata/PDDL, and transition/action vocabulary metadata when available from the PDDL domain. Provide a README with exact command and output contract.
  **Must NOT do**: Do not create dummy placeholder source data. Do not add model training, planner inference, full evaluation, dashboards, or new generation logic. Do not make the example depend on `data/curriculum_pddl_shards/`; it must use the final merged dataset root.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: bounded example package/loader using existing merged artifacts.
  - Skills: `[]`.
  - Omitted: `ui-ux-pro-max` - No UI work.

  **Parallelization**: Can Parallel: NO | Wave 5 | Blocks: Task 15 | Blocked By: Task 13

  **References**:
  - High-level requirement: `doc/high_level_plans/research_execution_plan.md:79-113` - Phase 2 benchmark package and modality-view deliverable.
  - Final dataset root: `data/curriculum_pddl/accepted_manifest.jsonl`, `data/curriculum_pddl/summary.json`, per-instance `domain.pddl`, `problem.pddl`, `result.json`, `render/trace.vfg.json`, `render/frames/*.png`.
  - Existing examples surface: `examples/eval_protocol.md` - only current `examples/` artifact, so add a new package rather than modifying unrelated docs.
  - Dataset schema source: `src/data_collect/metadata.py` - accepted instance fields and render artifact metadata.

  **Acceptance Criteria**:
  - [ ] `examples/planning_benchmark_slice/` exists with a runnable module entrypoint and README.
  - [ ] `python -m examples.planning_benchmark_slice --dataset data/curriculum_pddl --domain blocksworld --split dev --index 0 --json` exits `0` after Task 13 and prints valid JSON.
  - [ ] JSON output includes a real instance identifier, `domain_pddl`, `problem_pddl`, `render_trace`, at least one `render_frame`, `goal_or_problem_view`, and `action_vocabulary` or a documented empty action-vocabulary reason derived from parsing/metadata.
  - [ ] The loader fails clearly when `data/curriculum_pddl/summary.json` is missing.
  - [ ] The loader fails clearly for invalid domain, invalid split, and out-of-range index.

  **QA Scenarios**:
  ```
  Scenario: Load one real Blocksworld dev instance
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice --dataset data/curriculum_pddl --domain blocksworld --split dev --index 0 --json > /tmp/planning_benchmark_slice.json
    Expected: exit code 0; JSON contains real instance_id, domain_pddl text, problem_pddl text, render_trace path, and render_frames list with at least one PNG
    Evidence: .sisyphus/evidence/task-14-example-blocksworld.json

  Scenario: Example output contract validates
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
import json
from pathlib import Path
payload=json.loads(Path('/tmp/planning_benchmark_slice.json').read_text())
for key in ['instance_id','domain','split','domain_pddl','problem_pddl','render_trace','render_frames','goal_or_problem_view']:
    assert key in payload, key
assert payload['domain']=='blocksworld'
assert payload['split']=='dev'
assert payload['domain_pddl'].lstrip().startswith('(define')
assert payload['problem_pddl'].lstrip().startswith('(define')
assert Path(payload['render_trace']).exists(), payload['render_trace']
assert payload['render_frames'] and Path(payload['render_frames'][0]).exists(), payload['render_frames'][:1]
print('example-contract-ok')
PY
    Expected: exit code 0; prints example-contract-ok
    Evidence: .sisyphus/evidence/task-14-example-contract.txt

  Scenario: Missing merged dataset fails clearly
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice --dataset /tmp/missing_curriculum_pddl --domain blocksworld --split dev --index 0 --json
    Expected: nonzero exit; stderr mentions missing summary.json or missing dataset root
    Evidence: .sisyphus/evidence/task-14-missing-dataset.txt

  Scenario: Invalid selection fails clearly
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice --dataset data/curriculum_pddl --domain not_a_domain --split dev --index 0 --json
    Expected: nonzero exit; stderr mentions invalid or unavailable domain
    Evidence: .sisyphus/evidence/task-14-invalid-domain.txt
  ```

  **Commit**: YES | Message: `feat(examples): add planning benchmark slice loader` | Files: `examples/planning_benchmark_slice/**`

- [x] 15. Final verification, update docs with actual results, and produce handoff summary

  **What to do**: Re-run fast tests, inspect-tools, smoke summary check if smoke artifacts are present, shard verification, merge summary check, and example benchmark-slice checks. Update `doc/detailed_implementation_summary/phase2_curriculum_pddl_generation_summary.md` with actual merged counts, the `merge-shards` command, the example benchmark command, artifact locations, and the exact remaining caveat that generated dataset artifacts stay local unless explicitly requested. Produce a final handoff explaining artifact locations and exact commands.
  **Must NOT do**: Do not mark complete if merged counts, rendering gate, duplicate-hash checks, or example loader checks fail. Do not claim VLA training, planner-model, or evaluation-suite results; this is Phase 2 dataset finalization plus minimal benchmark slice only.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: end-to-end verification and documentation closeout.
  - Skills: `[]`.
  - Omitted: `review-work` - Final verification wave below handles review.

  **Parallelization**: Can Parallel: NO | Wave 5 | Blocks: Final Verification Wave | Blocked By: Tasks 13-14

  **References**:
  - This plan’s Definition of Done.
  - Output root: `data/curriculum_pddl/summary.json`.
  - Example command: `python -m examples.planning_benchmark_slice --dataset data/curriculum_pddl --domain blocksworld --split dev --index 0 --json`.
  - Documentation target: `doc/detailed_implementation_summary/phase2_curriculum_pddl_generation_summary.md`.

  **Acceptance Criteria**:
  - [ ] `pytest tests/data_collect -q` exits `0`.
  - [ ] `inspect-tools` exits `0` and reports all 15 adapters configured.
  - [ ] Shard verification and merged summary exact count checks pass.
  - [ ] Planning benchmark slice command succeeds on a real finalized instance.
  - [ ] Documentation contains actual merged counts, merge command, example command, and artifact policy.

  **QA Scenarios**:
  ```
  Scenario: Final fast tests
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m pytest tests/data_collect -q
    Expected: exit code 0
    Evidence: .sisyphus/evidence/task-15-tests.txt

  Scenario: Final merged dataset check
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
import json
from pathlib import Path
s=json.loads(Path('data/curriculum_pddl/summary.json').read_text())
assert s['accepted_total']==3600
assert s['domains_completed']==15
assert s['accepted_by_split']=={'dev': 300, 'test': 300, 'train': 3000}
assert s['render_failed_accepted']==0
assert s['duplicate_accepted_problem_hashes']==0
print('merged-dataset-ok')
PY
    Expected: exit code 0; prints merged-dataset-ok
    Evidence: .sisyphus/evidence/task-15-merged-dataset.txt

  Scenario: Final example smoke
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice --dataset data/curriculum_pddl --domain blocksworld --split dev --index 0 --json
    Expected: exit code 0; JSON output contains real PDDL and render artifact views
    Evidence: .sisyphus/evidence/task-15-example-smoke.json

  Scenario: Final docs and summary agree
    Tool: Bash
    Steps: source ~/cd_vlaplan && source .venv/bin/activate && python - <<'PY'
import json
from pathlib import Path
s=json.loads(Path('data/curriculum_pddl/summary.json').read_text())
t=Path('doc/detailed_implementation_summary/phase2_curriculum_pddl_generation_summary.md').read_text()
assert str(s['accepted_total']) in t
assert '3600' in t
assert '--require-rendering' in t
assert 'merge-shards' in t
assert 'examples.planning_benchmark_slice' in t
print('closeout-ok')
PY
    Expected: exit code 0; prints closeout-ok
    Evidence: .sisyphus/evidence/task-15-closeout.txt
  ```

  **Commit**: YES | Message: `docs(data): record phase2 benchmark slice completion` | Files: `doc/detailed_implementation_summary/phase2_curriculum_pddl_generation_summary.md`, `examples/planning_benchmark_slice/**`; generated dataset files excluded unless user requests

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.
- [x] F1. Plan Compliance Audit — oracle
- [x] F2. Code Quality Review — unspecified-high
- [x] F3. Real Manual QA — unspecified-high
- [x] F4. Scope Fidelity Check — deep

## Commit Strategy
- Commit implementation/test/docs in logical batches after passing their task-specific tests.
- Do **not** commit `data/curriculum_pddl/**` generated artifacts unless the user explicitly asks.
- If generated output needs local preservation, keep it as workspace artifacts and document paths.

## Success Criteria
- `src/data_collect` exists and provides reusable generation CLI.
- 15-domain config exists and validates to exact `3600` target accepted instances.
- All unit tests pass.
- Smoke generation either succeeds exactly with 6 rendered instances or fails before acceptance with a clear missing-capability error.
- Final merged dataset succeeds with exact `3600` rendered accepted instances.
- No accepted instance has render failure.
- No duplicate normalized problem hashes across accepted train/dev/test.
- Minimal `examples/planning_benchmark_slice/` loads one real finalized instance and emits PDDL/render/text modality views.
- Documentation records commands, environment, output paths, actual counts, benchmark-slice command, and rendering caveats.
