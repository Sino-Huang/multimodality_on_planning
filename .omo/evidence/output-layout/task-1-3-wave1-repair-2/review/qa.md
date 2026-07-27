# Wave 1 Repair 2 QA

## Scope

Fresh hands-on QA of the Phase 3 output-layout Wave 1 Repair 2 deliverable.
No product or test source was modified. No real output content was read,
hashed, written, moved, or deleted. The authorized protected-target lstat
coverage ran only through the selected test case.

## Environment

- Repository: `/data/scratch/projects/punim0478/sukaih/multimodality_on_planning`
- Python: `.venv/bin/python` (Python 3.11.14)
- Test runner: `.venv/bin/pytest`
- Type checker: `basedpyright` from the initialized `ada_vla` environment

## Commands And Results

1. Complete requested output-layout suite, including the authorized
   protected-target revalidation/lstat coverage:

   ```bash
   source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_*.py
   ```

   Result: exit 0; `200 passed in 2.03s`.

2. Strict Basedpyright using the dedicated temporary strict project:

   ```bash
   source ~/cd_vlaplan && source .venv/bin/activate && basedpyright --project /tmp/opencode/output-layout-pyrightconfig.json scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
   ```

   Result: exit 0; `0 errors, 0 warnings, 0 notes`.

3. Bytecode compilation:

   ```bash
   source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
   ```

   Result: exit 0; no output.

4. No-excuse rules:

   ```bash
   source ~/cd_vlaplan && source .venv/bin/activate && python /home/sukaih/.cache/opencode/packages/oh-my-openagent@latest/node_modules/oh-my-openagent/dist/skills/programming/scripts/python/check-no-excuse-rules.py scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
   ```

   Result: exit 0; `no violations in 35 file(s)`.

5. Pure-LOC measurement over the same 35 source and test files:

   ```bash
   max_file=''; max_lines=0; total_lines=0; file_count=0; over_limit=0; for file in scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py; do lines=$(awk '!/^[[:space:]]*$/ && !/^[[:space:]]*#/ { count += 1 } END { print count + 0 }' "$file"); total_lines=$((total_lines + lines)); file_count=$((file_count + 1)); if [ "$lines" -gt "$max_lines" ]; then max_lines=$lines; max_file=$file; fi; if [ "$lines" -gt 250 ]; then over_limit=$((over_limit + 1)); fi; done; printf 'files=%s total_pure_loc=%s max_pure_loc=%s max_file=%s files_over_250=%s\n' "$file_count" "$total_lines" "$max_lines" "$max_file" "$over_limit"
   ```

   Result: exit 0; `files=35 total_pure_loc=4203 max_pure_loc=243 max_file=scripts/phase3/output_layout_snapshot.py files_over_250=0`.

6. Focused retention dispatch, exact-tree publication, aggregate-budget,
   authorized protected-target revalidation/lstat, descriptor-close, and
   sidecar-mode checks:

   ```bash
   source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_retention_dispatch_races.py tests/phase3/test_output_layout_view_exact_tree_race.py tests/phase3/test_output_layout_aggregate_budgets.py tests/phase3/test_output_layout_protected_content_security.py::test_new_view_revalidates_protected_content_after_publication tests/phase3/test_output_layout_receipt_adversarial.py::test_open_receipt_closes_descriptor_when_fstat_fails tests/phase3/test_output_layout_receipt_recovery_adversarial.py::test_oversized_sidecar_read_closes_descriptor tests/phase3/test_output_layout_receipt_recovery_adversarial.py::test_recovery_sidecars_require_exact_private_mode_at_read_and_cleanup tests/phase3/test_output_layout_receipt_recovery_adversarial.py::test_new_transaction_and_swap_sidecars_are_mode_0600_before_cleanup
   ```

   Result: exit 0; `20 passed in 0.44s`.

7. Synthetic receipt lifecycle and fixed-sidecar recovery checks:

   ```bash
   source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_receipt_adversarial.py::test_initial_crashes_leave_only_fixed_sidecar_protocol_state tests/phase3/test_output_layout_receipt_adversarial.py::test_retry_recovers_create_interrupted_after_transaction_fsync tests/phase3/test_output_layout_receipt_adversarial.py::test_retry_recovers_replace_interrupted_after_transaction_fsync tests/phase3/test_output_layout_receipt_adversarial.py::test_retry_reconciles_fixed_transaction_states_without_unnecessary_exchange tests/phase3/test_output_layout_receipt_adversarial.py::test_repeated_replacements_remove_fixed_sidecars_and_displaced_receipt_bytes
   ```

   Result: exit 0; `13 passed in 0.32s`.

8. Whitespace integrity:

   ```bash
   GIT_MASTER=1 git diff --check
   ```

   Result: exit 0; no output.

## Cleanup Receipt

- Test selection and execution finished with exit 0 for every required gate.
- `/tmp/opencode/output-layout-*` contained only the pre-existing strict
  Basedpyright configuration; no QA-created output-layout fixture directory
  remained.
- The workspace was already dirty before this QA pass. No product or test
  source files were changed by this work; the only intended artifact is this
  evidence file.
- The full suite and focused protected-target case are the only authorized
  coverage that may perform lstat-style validation. This QA pass made no
  manual access to real output contents.

## Gaps

- This is fixture-driven regression and static analysis, not a production
  filesystem-fault-injection run against real outputs; that omission is
  intentional to preserve the protected-target constraint.
- Strict Basedpyright relies on `/tmp/opencode/output-layout-pyrightconfig.json`
  because the repository-level `pyrightconfig.json` sets type checking off.
- An initial compileall wrapper used the zsh-reserved name `status` for an exit
  variable and exited before reporting a result. The exact compileall command
  above was rerun immediately and passed with exit 0.

VERDICT: PASS
