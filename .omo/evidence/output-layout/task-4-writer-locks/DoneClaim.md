# DoneClaim: Task 4 Shared Writer Locks

**Status: CONFIRMED.** Task 4 completed the repository-only shared writer-lock integration for both Phase 3 writers.

`generate_planimation_vlm.main` acquires `shared_output_layout_lock(Path(__file__).resolve().parents[2])` immediately before `build_pairing_manifest`. It holds the lock through manifest-only return, render-only validation and return, record generation, final validation and return, and exceptions.

`pipeline.generate_supervised_data` keeps planner validation, the jobs guard, and limits construction outside the lock. It acquires the same repository-derived shared lock immediately before `clear_output_root`, then holds it through `_write_reports`, normal return, and exceptions.

Lock selection is independent of whether the output root exists and where it is located. The focused tests use absent temporary external output roots. No output-root policy changed.

## Proof

- The initial TDD red run had 5 behavioral failures caused solely by missing writer acquisition. The contention test had no lock file.
- The final focused suite passed all Planimation render-only, full, and late-validation failure cases, plus pipeline report-return and report-exception cases: `6 passed`.
- Spawned Planimation and pipeline writers acquired real shared locks concurrently. A causally synchronized organizer exclusive attempt, using the real organizer `apply`, blocked before either writer released, remained blocked after the first release, and acquired only after the second release.
- The contention proof exercised the actual `fcntl` lock primitives through `shared_output_layout_lock` and `exclusive_output_layout_lock`, not recording doubles.
- The lock primitive tests plus the existing organizer writer-lock regression reported `20 passed`.
- Adjacent existing writer characterization tests reported `2 passed`.
- Direct synthetic contention QA by the exact spawned test reported `1 passed`.
- Basedpyright on the target list reported `0 errors, 0 warnings, 0 notes` after two harmless unrecognized editor-setting notices.
- `python -m compileall -q` exited 0.
- The no-excuse audit of the Planimation writer and all three new focused test files reported `no violations in 4 file(s)`.
- A full no-excuse command that also included legacy `pipeline.py` reported seven pre-existing issues in that 553-line file: generic `ValueError`, broad exceptions, and oversized-module findings. This task added no pipeline violation, and those legacy issues were not refactored because they are outside scope.
- `GIT_MASTER=1 git diff --check` exited 0.
- Basedpyright LSP diagnostics repeatedly timed out at the harness 3-second refresh window. Direct Basedpyright passed.
- Ruff was unavailable in the mandated active environment with `command not found`; no Ruff pass is claimed.
- Final Oracle re-review found no findings.

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

## Scope

No organizer or lock implementation or test file changed. No compatibility path, launcher, real output, unrelated dirty file, existing documentation, current plan, prerequisite evidence, or git state was touched. No output-root policy changed, and no commit was created.
