# Phase 3 Output-Layout Directory Lock

`scripts/phase3/output_layout_lock.py` provides the repository-wide advisory lock used to coordinate Phase 3 output-layout access. Call `shared_output_layout_lock(repository)` for shared access and `exclusive_output_layout_lock(repository)` for exclusive access. The public API remains the symmetric, one-argument, repository-only API established by the historical red receipt.

- The lock opens the absolute, canonical, real repository directory with `O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW`; it neither uses nor creates `repository / ".phase3-output-layout.lock"`.
- Before flock and again after flock, the implementation compares the named repository's `lstat` and resolved identity with the descriptor's `fstat` device/inode identity. This rejects symlinks, non-directories, non-canonical paths, and pathname replacement between open and acquisition.
- The descriptor owns the full lock context. After open, `acquired` starts false. The implementation verifies, calls flock, sets acquired true only after flock returns, then performs post-acquisition verification and yields. Its state-based `finally` conditionally unlocks and then closes unconditionally. Interruption before acquisition closes without unlock; interruption after acquisition unlocks then closes.
- Neither context manager selects, validates, creates, or accesses `outputs/` or any real output root. Writer and organizer policy remain outside this lock primitive.
- Focused tests include legacy-path replacement resistance. Synthetic manual QA uses `multiprocessing.get_context("spawn")`, pipe events, bounded polling, and `finally` cleanup; it verifies both fresh shared/exclusive acquisition leave the legacy pathname absent and replacement cannot admit a shared contender while an exclusive directory lock is held.
- This lane does not edit organizer or writer product code and does not access real outputs. Existing stale legacy filesystem entries are not mutated.

The final focused split includes `tests/phase3/test_output_layout_lock.py`, `tests/phase3/test_output_layout_lock_descriptor.py`, `tests/phase3/test_output_layout_lock_interruption.py`, and `tests/phase3/output_layout_lock_test_support.py`. Collection found 32 tests across the three test modules, and the focused run passed all 32 in 8.44s. Earlier 28-test receipts remain preserved as prior evidence but are superseded for final status.

Final validation commands and results:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp pytest -q --tb=short tests/phase3/test_output_layout_lock_interruption.py
# 4 passed; preserved RED was 4 failed, 7 deselected
source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp pytest --collect-only -q tests/phase3/test_output_layout_lock.py tests/phase3/test_output_layout_lock_descriptor.py tests/phase3/test_output_layout_lock_interruption.py
# 32 tests collected
source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp pytest -q --tb=short tests/phase3/test_output_layout_lock.py tests/phase3/test_output_layout_lock_descriptor.py tests/phase3/test_output_layout_lock_interruption.py
# 32 passed in 8.44s
source ~/cd_vlaplan && source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp python .omo/evidence/output-layout/task-4-lock/manual_spawn_lock_qa.py
# both explicit PASS lines
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
# no violations in eight named files
source ~/cd_vlaplan && source .venv/bin/activate && command -v ruff
# unavailable; Ruff was not installed or run
GIT_MASTER=1 git diff --check
# exit 0 with no output; tracked diff only
```

The active environment lacked `typing_extensions`, so the writer and organizer commands used the temporary `uv` overlay shown above. No permanent dependency was installed, and no project environment or dependency file was changed. Ruff was unavailable and uninstalled, so it was not run. Fresh latest receipts are under `.omo/evidence/output-layout/task-4-lock/interruption-cleanup-follow-up-2026-07-27/`. The post-remediation Oracle re-review returned `APPROVE`, providing final Oracle approval for the implementation. No organizer or writer product file, real output, root `.phase3-output-layout.lock`, dependency file, or commit was changed.
