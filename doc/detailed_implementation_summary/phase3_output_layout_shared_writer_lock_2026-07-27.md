# Phase 3 Output Layout Shared Writer Lock

## Scope

This repository-only integration adds shared output-layout locking to the two Phase 3 writers. Lock selection does not depend on output-root existence or location, including temporary external test roots. No output-root validation or policy changed.

## Implementation

`generate_planimation_vlm.main` acquires `shared_output_layout_lock(Path(__file__).resolve().parents[2])` immediately before `build_pairing_manifest`. The context remains active through manifest-only return, replay rendering, render-only validation and return, VLM record construction, final validation and return, and exceptions.

`pipeline.generate_supervised_data` keeps planner validation, the jobs guard, and limits construction outside the lock. It acquires the same repository-derived lock immediately before `clear_output_root`, then retains it through `_write_reports`, normal return, and exceptions.

## Test Proofs

- Planimation lifecycle coverage proves render-only completion, full completion, and a late validation exception release only after the terminal operation.
- Pipeline lifecycle coverage proves report-return and report-exception paths retain the lock through `_write_reports`.
- Both tests use absent external temporary output roots, proving repository-only lock selection.
- Spawned Planimation and pipeline writers coexist under real shared `fcntl` locks.
- A causally synchronized real organizer `apply` exclusive attempt blocks before either writer releases, remains blocked after the first release, and acquires only after the second release.
- The initial TDD red run had 5 failures caused solely by missing writer acquisition; the contention test had no lock file.

## Commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_phase3_writer_output_layout_lock.py
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_lock.py tests/phase3/test_organize_outputs.py::test_writer_lock_blocks_organizer
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_planimation_pairing.py::test_generator_rejects_render_limit_in_production_mode tests/phase3/test_phase3_pipeline.py::test_generate_supervised_data_and_verifiers_on_fixture
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_phase3_writer_output_layout_lock.py::test_shared_writers_coexist_and_hold_organizer_until_both_release
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/generate_planimation_vlm.py scripts/phase3/pipeline.py tests/phase3/test_phase3_writer_output_layout_lock.py tests/phase3/phase3_writer_output_layout_lock_support.py tests/phase3/phase3_writer_output_layout_lock_planimation_support.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/generate_planimation_vlm.py scripts/phase3/pipeline.py tests/phase3/test_phase3_writer_output_layout_lock.py tests/phase3/phase3_writer_output_layout_lock_support.py tests/phase3/phase3_writer_output_layout_lock_planimation_support.py
source ~/cd_vlaplan && source .venv/bin/activate && python /home/sukaih/.cache/opencode/packages/oh-my-openagent@latest/node_modules/oh-my-openagent/dist/skills/programming/scripts/python/check-no-excuse-rules.py scripts/phase3/generate_planimation_vlm.py tests/phase3/test_phase3_writer_output_layout_lock.py tests/phase3/phase3_writer_output_layout_lock_support.py tests/phase3/phase3_writer_output_layout_lock_planimation_support.py
source ~/cd_vlaplan && source .venv/bin/activate && python /home/sukaih/.cache/opencode/packages/oh-my-openagent@latest/node_modules/oh-my-openagent/dist/skills/programming/scripts/python/check-no-excuse-rules.py scripts/phase3/generate_planimation_vlm.py scripts/phase3/pipeline.py tests/phase3/test_phase3_writer_output_layout_lock.py tests/phase3/phase3_writer_output_layout_lock_support.py tests/phase3/phase3_writer_output_layout_lock_planimation_support.py
GIT_MASTER=1 git diff --check
```

## Results

- Focused writer-lock suite: `6 passed`.
- Lock primitive tests plus the existing organizer writer-lock regression: `20 passed`.
- Adjacent existing writer characterization tests: `2 passed`.
- Exact spawned synthetic contention test: `1 passed`.
- Basedpyright target list: `0 errors, 0 warnings, 0 notes`, after two harmless unrecognized editor-setting notices.
- Compileall: exit 0.
- Four-file Planimation writer and focused-test no-excuse audit: `no violations in 4 file(s)`.
- Full no-excuse audit including legacy `pipeline.py`: seven pre-existing findings in that 553-line file for generic `ValueError`, broad exceptions, and module size. This task added no such violation and did not refactor them because they are outside scope.
- `GIT_MASTER=1 git diff --check`: exit 0.
- Basedpyright LSP diagnostics repeatedly timed out at the harness 3-second refresh window. Direct Basedpyright passed.
- Ruff was not installed in the mandated environment and returned `command not found`; no Ruff pass is claimed.
- Final Oracle re-review: no findings.

## Boundaries

No organizer or lock implementation or test file changed. No compatibility path, launcher, real output, unrelated dirty file, existing documentation, current plan, prerequisite evidence, or git state was touched. No commit was created. Task 4's writer-lock DoneClaim is confirmed.
