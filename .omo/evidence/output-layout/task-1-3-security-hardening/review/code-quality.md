# Independent Code-Quality Review: Wave 1 Output-Layout Todos 1-3

## Scope And Method

Reviewed all 17 current `scripts/phase3/output_layout_*.py` modules and all
11 focused `tests/phase3/test_output_layout_*.py` modules. The review covered
typing, module size and ownership, exception/resource semantics, deterministic
fixtures, traversal budgets, cleanup ownership, quarantine retention,
publication mismatch handling, and exact `0600` receipt-sidecar behavior.

All source and test inspection was read-only. Test execution was limited to
synthetic `tmp_path` fixtures. No command listed, read, wrote, or otherwise
accessed a real `outputs/` path. The single repository-output test was
explicitly deselected.

## Blocking Findings

1. **HIGH - Oversized receipt recovery sidecars leak file descriptors.**
   `scripts/phase3/output_layout_receipt_transaction.py:163-198` opens a
   sidecar descriptor, then raises `OutputLayoutInventoryError` for an initial
   or streamed size-limit breach at lines 179-186. Only `OSError` is caught
   before the normal close at line 192, so these domain-error exits bypass the
   close. Repeated recovery attempts against an oversized `.txn`, `.swap`, or
   `.remove` sidecar can exhaust descriptors. Put the descriptor close in an
   unconditional `finally` and add a regression that proves close-on-oversize.

2. **HIGH - Cleanup can delete a racer-owned object after identity validation.**
   The receipt path validates the quarantined sidecar at
   `output_layout_receipt_transaction.py:220-222` and then unlinks the name at
   line 224. Private-stage cleanup has the same post-check windows at
   `output_layout_view_stage.py:179-182` and `249-262`. A same-user racer can
   replace the validated name between its final check and `unlink` or `rmdir`.
   This violates partial ownership and conservative quarantine retention.
   Existing adversarial tests replace objects before the terminal validation,
   not in this final window. Retain ambiguous quarantine evidence instead of
   deleting through a pathname whose identity cannot still be proved.

3. **HIGH - Publication can succeed with a tree that no longer matches the
   exact contract.** `create_output_layout_view()` validates the private tree
   before fsync and publication (`output_layout_view.py:51-56`).
   `output_layout_view_walk.fsync_tree()` ignores regular files, symlinks, and
   special entries rather than rejecting them (`output_layout_view_walk.py:58-71`),
   and final verification checks only expected links (`output_layout_view.py:118-125`).
   An extra entry inserted after `validate_tree()` can therefore survive to the
   published view and still yield success. Revalidate the complete pinned
   private tree immediately before publication and add an extra-entry race
   regression.

4. **MEDIUM - Traversal limits do not bound total work and eagerly materialize
   oversized directories.** Snapshot, protected-content, and private-stage
   walkers cap depth and entries per directory, but do not carry one aggregate
   work budget across recursion. `output_layout_view_walk.py:74-78` first
   materializes all names with `os.listdir()` and only then tests the local
   limit. A shallow, broad adversarial tree can still consume excessive memory,
   CPU, hashing, and fsync work. Use incremental `scandir()` plus a shared
   aggregate entry/work budget.

5. **MEDIUM - The strict typing gate fails in focused test code, and one named
   race regression does not exercise its intended seam.** With strict
   Basedpyright, `tests/phase3/test_output_layout_view_adversarial.py` reports:
   an unused `original_verify` at line 144, an undefined `original_validate`
   at line 157, and unused `error_info` at line 195. The test named
   `test_final_verification_rejects_created_destination_ancestor_replacement`
   attempts to rename a final view root that does not yet exist, so it raises
   before reaching the intended saved validator call. Repair the fixture and
   assert the intended post-construction/pre-publication race behavior.

6. **MEDIUM - Three focused test modules exceed the required 250 pure-LOC
   ceiling.** The measured counts are 299 for
   `test_output_layout_receipt_adversarial.py`, 283 for
   `test_output_layout_acceptance_security.py`, and 267 for
   `test_output_layout_view_races.py`. No `SIZE_OK` rationale is present.
   Split each by one behavior family before adding further cases.

## Non-Blocking Findings And Residual Risks

- `output_layout_receipt_transaction_values.py:92` contains
  `# noqa: MATCH_OK`. The default branch correctly rejects untrusted JSON
  variants, but this remains a linter suppression and does not meet a literal
  no-suppressions policy.
- Production source is otherwise well-separated: receipt I/O, transaction
  values, snapshots, view planning, staging, filesystem mutation, and walker
  concerns have distinct owners. All 17 production modules are at or below
  250 pure LOC; the largest are receipt transaction (244), snapshot (235), and
  view stage (217), so the first two are in the warning band.
- No bare `except`, `except Exception`, `except BaseException`, `type: ignore`,
  `pyright: ignore`, `Any`, or `cast()` was found in the production set. The
  remaining `OSError` cleanup suppression in `output_layout_view.py:67-74`
  preserves the primary error, but hides the retained-quarantine cleanup
  failure from callers.
- Current tests use `tmp_path` and deterministic monkeypatched race seams; no
  sleep, wall-clock, or random dependency was found. The repository-coupled
  test remains intentionally excluded from this review because it reads real
  protected targets beneath `outputs/`.
- Exact `0600` is enforced in source: sidecars are created with `0o600` and
  `fchmod(0o600)` (`output_layout_receipt_transaction.py:139-151`) and read
  only at exact `0600` (`:163-180`). Current tests reject insecure sidecars,
  but do not directly observe newly created `.txn` and `.swap` modes before
  cleanup; add that narrow regression when repairing the descriptor leak.

## Commands And Results

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_acceptance_security.py
# 19 passed in 0.34s

source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_*.py -k 'not test_real_repository_has_all_fifteen_protected_view_targets'
# 189 passed, 1 deselected in 1.65s

source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_*.py -k 'not test_real_repository_has_all_fifteen_protected_view_targets'
# 189 passed, 1 deselected in 1.71s

source ~/cd_vlaplan && source .venv/bin/activate && basedpyright --project /tmp/opencode/output-layout-pyrightconfig.json scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
# 3 errors, 0 warnings, 0 notes; all three are in test_output_layout_view_adversarial.py.

source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
# Exit 0.
```

The repository `pyrightconfig.json` sets `typeCheckingMode` to `off`, so its
zero-diagnostic LSP scan is not a strict typing gate. The strict temporary
review configuration was pre-existing under `/tmp/opencode`; it was read, not
created or modified, and the explicit command above exposed the three test
errors.

The two passing pytest runs establish deterministic behavior for the safe,
synthetic suite only. They do not cover the descriptor leak, the final
cleanup race, or a mutation between stage validation and publication.

## Verdict Basis

The repair set correctly adds no-follow/nonblocking regular-file opens,
per-directory traversal limits, incremental stage ownership, exact `0600`
sidecar checks, and several deterministic race regressions. The remaining
resource leak and same-user TOCTOU windows directly violate the requested
exception, ownership, quarantine-retention, and publication-mismatch
requirements. Strict test typing and focused test-module size gates also fail.

VERDICT: FAIL
