# Output-Layout Wave 1 Repair 3 Code-Quality Review

> HISTORICAL FIRST-ROUND REVIEW: superseded by the import repairs, production typing cleanup, and durable full-scope Repair 3 Basedpyright configuration. Preserve for audit history; do not treat this file as a current verdict.

## Scope and Method

Inspected every current in-scope Python module: 18 files matching
`scripts/phase3/output_layout_*.py` and 17 files matching
`tests/phase3/test_output_layout_*.py`, including the stated Repair 3 surface.
No real output artifacts were opened or inspected, and no product files were
modified.

The review traced the contract -> preflight -> view/stage/filesystem lane and
the inventory -> receipt -> transaction/recovery lane. It checked descriptor
ownership, no-follow access, error translation, runtime signatures and callers,
annotations/suppressions, function/class size, bounded traversal behavior, and
adversarial/race-test coverage.

## Major Findings

1. **FAIL: the focused suite is not collectable in the project environment.**
   Three in-scope test modules import helpers through a `tests.phase3` package
   that is not importable here, so their security/recovery coverage never runs:
   - `tests/phase3/test_output_layout_protected_content_security.py:10`
   - `tests/phase3/test_output_layout_receipt_recovery_adversarial.py:11`
   - `tests/phase3/test_output_layout_view_content_races.py:9`

   Both `pytest -q tests/phase3/test_output_layout_*.py` and the same command
   with the repository added to `PYTHONPATH` stop at collection with three
   `ModuleNotFoundError: No module named 'tests.phase3'` errors. These modules
   cover protected-content publication, receipt recovery, and content-race
   boundaries, so this blocks meaningful red-to-green verification of critical
   cross-lane behavior.

2. **FAIL: a runnable acceptance/security test contradicts the current cleanup
   implementation.** `output_layout_view_stage.cleanup` deliberately retains a
   failed private-stage pathname without mutation at
   `scripts/phase3/output_layout_view_stage.py:180-190`. In contrast,
   `tests/phase3/test_output_layout_acceptance_security.py:291-298` requires the
   unowned child to be available below a renamed `<stage>.cleanup` directory.
   The focused runnable subset therefore fails
   `test_private_stage_cleanup_preserves_unowned_child` with `FileNotFoundError`
   at line 298. Either the implementation violates the acceptance contract or
   the test still asserts superseded behavior; in either case Repair 3 does not
   provide a consistent, passing cleanup contract.

## Verified Positives

- The reviewed implementation uses explicit descriptor lifetimes in the
  snapshot, receipt, transaction, view, stage, content-token, and filesystem
  paths. The examined close paths are guarded by `finally` blocks or translated
  close helpers; no broad or empty catches were found.
- Exceptions are domain-specific and generally preserve causes. The view lane
  revalidates pins across preflight, construction, publication, and final link
  verification. Receipt writes use private sidecars, bounded reads, atomic
  rename/exchange, and parent fsync boundaries.
- Static scans found no `typing.Any`, suppression directives, or bare
  `except` handlers. AST inspection found every function/class at or below 250
  LOC and every in-scope implementation and test file at or below 250 pure LOC.
- Traversal work is bounded by entry, depth, and byte budgets. The runnable
  adversarial suite covers aggregate budgets, symlink/type substitutions,
  descriptor races, recovery states, and exact-tree validation.

## Commands and Results

| Command | Result |
| --- | --- |
| `source ~/cd_vlaplan && python -m compileall -q scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py` | Passed. |
| `source ~/cd_vlaplan && basedpyright --level error scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py` | 0 errors, warnings, and notes. |
| `source ~/cd_vlaplan && pytest -q tests/phase3/test_output_layout_*.py` | Blocked during collection by the three import failures above. |
| Runnable 14-file focused subset | 192 passed, 1 failed: the cleanup-contract mismatch above. |

## Minor Residual Risks

- `pyrightconfig.json:17` sets `typeCheckingMode` to `off`. The direct
  basedpyright invocation was clean and the source scan found no escape hatches,
  but the repository configuration does not enforce strict checking in ordinary
  developer runs.
- The available environment does not contain `ruff`, so Ruff linting could not
  be independently executed. This does not change the verdict.
- LSP diagnostics reported five unused-parameter hints in the synthetic race
  doubles in `tests/phase3/test_output_layout_retention_dispatch_races.py:24-36`.
  They are low-risk test-maintenance noise, not runtime defects.

VERDICT: FAIL
