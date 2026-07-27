# Output-layout Wave 1 Repair 3 QA

> HISTORICAL FIRST-ROUND REVIEW: superseded by the 211-test build and durable full-scope Repair 3 Basedpyright configuration. Preserve for audit history; do not treat this file as a current verdict.

## Scope and isolation

- Leaf QA execution only. No product or test files were edited.
- All Python commands used the required environment prefix: `source ~/cd_vlaplan && source .venv/bin/activate &&`.
- No real output was manually inspected or mutated. The only real-output metadata access was the authorized read-only `lstat` test.
- The synthetic driver used `TemporaryDirectory(prefix="output-layout-qa-")`; it created only a temporary synthetic repository and its cleanup completed automatically on context exit.

## Pre-existing worktree state

Captured before creating this review file:

```text
WORKTREE_ENTRIES=517 MODIFIED_OR_STAGED=11 UNTRACKED=506
```

The 11 modified tracked paths were `.omo/boulder.json`, two `.omo` state/knowledge files, five `scripts/phase3/planimation_*.py` files, and three existing `tests/phase3/test_*` files. The untracked set included the output-layout implementation/tests and pre-existing `.omo` evidence/state trees. This QA created only this `qa.md` review file.

## Results

| Check | Exact command (after required prefix) | Exit | Result |
|---|---|---:|---|
| Full output-layout suite, including authorized `lstat` test | `pytest -q tests/phase3/test_output_layout_*.py` | 1 | 208 passed, 2 failed, 2.46s |
| Focused Repair 3 races/budgets | `pytest -q tests/phase3/test_output_layout_aggregate_budgets.py tests/phase3/test_output_layout_retention_dispatch_races.py tests/phase3/test_output_layout_stage_construction_races.py tests/phase3/test_output_layout_view_content_races.py tests/phase3/test_output_layout_view_exact_tree_race.py tests/phase3/test_output_layout_view_races.py` | 0 | 32 passed, 0.89s |
| Authorized protected-target `lstat` test | `pytest -q tests/phase3/test_output_layout_view.py::test_real_repository_has_all_fifteen_protected_view_targets` | 0 | 1 passed, 0.21s |
| Strict basedpyright | `basedpyright --project /tmp/opencode/output-layout-pyrightconfig.json scripts/phase3/output_layout*.py tests/phase3/test_output_layout_*.py` | 1 | 4 errors, 0 warnings, 0 notes |
| Compileall | `python -m compileall -q scripts/phase3/output_layout*.py tests/phase3/test_output_layout_*.py` | 0 | Completed silently |
| No-excuse checker discovery/execution | `candidate=$(rg --files \| rg '(^\|/)check-no-excuse-rules\\.py$' \|\| true); if [ -n "$candidate" ]; then python "$candidate" scripts/phase3/output_layout*.py tests/phase3/test_output_layout_*.py; else printf '%s\\n' 'NO_EXCUSE_CHECKER_NOT_FOUND'; exit 127; fi` | 127 | No repository checker was found; output: `NO_EXCUSE_CHECKER_NOT_FOUND` |
| Pure LOC | Python line counter excluding blank/comment-only lines over 35 output-layout source/test files | 0 | Maximum 247 pure LOC in `scripts/phase3/output_layout_snapshot.py`; no file exceeded 250 |
| Whitespace errors | `git diff --check` | 0 | Clean (`GIT_DIFF_CHECK_EXIT=0`) |

## Blocking failures

1. `tests/phase3/test_output_layout_acceptance_security.py::test_private_stage_cleanup_preserves_unowned_child` failed: the expected `<stage>.cleanup/racer-owned` file was absent after `output_layout_view_stage.cleanup(stage)`.
2. `tests/phase3/test_output_layout_protected_content_security.py::test_new_view_revalidates_protected_content_after_publication` failed: `output_layout_view_stage.publish` returned `None`, after which `validate_tree` raised `AttributeError: 'NoneType' object has no attribute 'identity'` instead of the required `OutputLayoutViewError`.
3. Basedpyright reported unresolved local imports and consequent unknown types in `test_output_layout_stage_construction_races.py` and `test_output_layout_view_exact_tree_race.py` for `test_output_layout_view_races` and `test_output_layout_view`.
4. The required no-excuse checker is unavailable in the repository, so that gate could not execute.

## Synthetic manual driver

Executed an inline `python -c` driver in a `TemporaryDirectory`. It seeded each target from `OUTPUT_LAYOUT_VIEW_LINKS`, called `create_output_layout_view(repo)` twice, and verified all 15 destinations are symlinks with exact stored target text and unchanged `(st_dev, st_ino)` pairs. It then lowered `output_layout_snapshot._MAX_TOTAL_BYTES` to 4 for a 5-byte temporary file and asserted `snapshot_tree` raised `OutputLayoutInventoryError` whose cause contained `byte budget` before restoring the limit.

```text
MANUAL_DRIVER_PASS links=15 idempotent_inode_pairs=15 budget_failure=byte_budget temp_cleanup=TemporaryDirectory
```

VERDICT: FAIL
