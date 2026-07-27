# Phase 3 Output-Layout Directory Lock Lane 1

## Scope

This lane completed evidence, knowledge, strict configuration, and validation receipts for the already-implemented repository-directory flock repair. It made no product change. In particular, it did not edit organizer or writer product files, compatibility files, root `.phase3-output-layout.lock`, plans, real outputs, or unrelated dirty files; it did not delete a root artifact or create a commit.

## Technical Repair Captured

The repository-only `shared_output_layout_lock(repository)` and `exclusive_output_layout_lock(repository)` API opens the repository directory using `O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW`. The directory must be an absolute, canonical, real directory. Before flock and after flock, named-path status and descriptor status are compared by device/inode identity, preventing a pathname replacement from changing the object protected by the descriptor.

The descriptor owns the complete context. After opening it, `acquired` starts as false. The implementation verifies descriptor identity, calls flock, sets acquired true only after flock returns, then performs post-acquisition verification and yields. A state-based outer `finally` conditionally unlocks when acquired, and a nested `finally` closes unconditionally. Interruption during flock closes without unlock. Interruption after flock returns unlocks and then closes. No broad catches, retries, fallbacks, nested locks, or legacy lock filename are used.

The existing historical lane strict configuration includes these six Python files under `typeCheckingMode: all`:

1. `scripts/phase3/output_layout_lock.py`
2. `tests/phase3/output_layout_lock_test_support.py`
3. `tests/phase3/test_output_layout_lock.py`
4. `tests/phase3/test_output_layout_lock_descriptor.py`
5. `tests/phase3/test_phase3_writer_output_layout_lock.py`
6. `.omo/evidence/output-layout/task-4-lock/manual_spawn_lock_qa.py`

The final focused lock suite spans `test_output_layout_lock.py`, `test_output_layout_lock_descriptor.py`, and `test_output_layout_lock_interruption.py`, with shared fixtures and process helpers in `output_layout_lock_test_support.py`. The existing strict config still defines its six-file historical lane scope. A separate interruption config defines a three-file scope. Compile and no-excuse validation covered eight named files, adding the interruption module to the earlier seven-file set. These config-defined Basedpyright checks are not presented as one all-files project check.

## Synthetic Testing

Focused tests and manual QA use synthetic temporary repositories only. The manual program uses `multiprocessing.get_context("spawn")`, pipe events, bounded polling, and cleanup in `finally`; it passed both the no-legacy-file-creation and legacy-path replacement-resistance checks. The shared writer contention test asserts that `.phase3-output-layout.lock` remains absent. Its support now supplies the canonical synthetic receipt path `outputs/deprecated/phase3/output_reorganization_20260726.json` to the real organizer `apply` entry point. No real output, writer, or organizer runtime path was accessed.

## Commands and Observed Results

```bash
source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp pytest -q --tb=short tests/phase3/test_output_layout_lock_interruption.py
# 4 passed; preserved RED receipt: 4 failed, 7 deselected

source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp pytest --collect-only -q tests/phase3/test_output_layout_lock.py tests/phase3/test_output_layout_lock_descriptor.py tests/phase3/test_output_layout_lock_interruption.py
# 32 tests collected

source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp pytest -q --tb=short tests/phase3/test_output_layout_lock.py tests/phase3/test_output_layout_lock_descriptor.py tests/phase3/test_output_layout_lock_interruption.py
# 32 passed in 8.44s

source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp python .omo/evidence/output-layout/task-4-lock/manual_spawn_lock_qa.py
# manual-spawn-lock-no-legacy-file-creation: PASS
# manual-spawn-lock-replacement-resistance: PASS

source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp uv run --no-project --with typing_extensions --with pytest pytest -q --tb=short tests/phase3/test_phase3_writer_output_layout_lock.py
# 6 passed in 2.81s

source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp uv run --no-project --with typing_extensions --with pytest pytest -q --tb=short tests/phase3/test_organize_outputs.py::test_writer_lock_blocks_organizer tests/phase3/test_organize_outputs_adversarial.py::test_exclusive_organizer_lock_blocks_second_preflight
# 2 passed in 2.47s

source ~/cd_vlaplan && source .venv/bin/activate && basedpyright --project .omo/evidence/output-layout/task-4-lock/pyrightconfig.json
# 0 errors, 0 warnings, 0 notes for config-defined six-file historical lane scope

source ~/cd_vlaplan && source .venv/bin/activate && basedpyright --project .omo/evidence/output-layout/task-4-lock/interruption-cleanup-follow-up-2026-07-27/pyrightconfig.json
# 0 errors, 0 warnings, 0 notes for config-defined three-file interruption scope

source ~/cd_vlaplan && source .venv/bin/activate && PYTHONPYCACHEPREFIX=/tmp/phase3-lock-pycache python -m compileall -q scripts/phase3/output_layout_lock.py tests/phase3/output_layout_lock_test_support.py tests/phase3/test_output_layout_lock.py tests/phase3/test_output_layout_lock_descriptor.py tests/phase3/test_output_layout_lock_interruption.py tests/phase3/test_phase3_writer_output_layout_lock.py tests/phase3/phase3_writer_output_layout_lock_support.py .omo/evidence/output-layout/task-4-lock/manual_spawn_lock_qa.py
# exit 0 for eight named Python files

source ~/cd_vlaplan && source .venv/bin/activate && python /home/sukaih/.cache/opencode/packages/oh-my-openagent@latest/node_modules/oh-my-openagent/dist/skills/programming/scripts/python/check-no-excuse-rules.py scripts/phase3/output_layout_lock.py tests/phase3/output_layout_lock_test_support.py tests/phase3/test_output_layout_lock.py tests/phase3/test_output_layout_lock_descriptor.py tests/phase3/test_output_layout_lock_interruption.py tests/phase3/test_phase3_writer_output_layout_lock.py tests/phase3/phase3_writer_output_layout_lock_support.py .omo/evidence/output-layout/task-4-lock/manual_spawn_lock_qa.py
# no violations in eight named Python files

source ~/cd_vlaplan && source .venv/bin/activate && command -v ruff
# no path; exit nonzero, so Ruff was unavailable and was not installed

GIT_MASTER=1 git diff --check
# exit 0 with no output; tracked diff only, not untracked-file whitespace
```

The active environment lacked `typing_extensions`. Writer and organizer tests used the temporary `uv run --no-project --with typing_extensions --with pytest` overlay shown above, after the required `source ~/cd_vlaplan && source .venv/bin/activate &&` prefix. No permanent dependency was installed, and no project environment or dependency file was changed.

Fresh latest command receipts are retained in `.omo/evidence/output-layout/task-4-lock/interruption-cleanup-follow-up-2026-07-27/`. Historical RED receipts, provisional failure receipts, and the earlier 28-test strict follow-up remain preserved. The 28-test results are superseded for final status, not deleted. Oracle rejected the first implementation over interruption cleanup; the state-based `finally` remediation is now red-to-green. The post-remediation Oracle re-review returned `APPROVE`, providing final Oracle approval for the implementation.

This evidence pass did not edit organizer or writer product files, access or change real outputs, change or delete the root `.phase3-output-layout.lock`, edit dependency files, or create a commit. Ruff remained unavailable and uninstalled, so it was not run. `GIT_MASTER=1 git diff --check` exited 0 with no output, with the stated limitation that it checks tracked diff only.
