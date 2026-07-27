# Filesystem Security Review

## Verdict

**FAIL.** The prior baseline's nonblocking-open, bounded-walk, partial-ownership, exact-sidecar-mode, and post-publication controls are present. However, a final exploitable check-to-use deletion interval remains in both quarantine cleanup implementations.

## Scope and method

This independent review covered repaired Wave 1 output-layout Todos 1-3. It inspected the current implementation and adversarial tests for descriptor opens, stage walking and fsync, partial-stage ownership and error preservation, quarantine deletion, publication identity checks, and recovery sidecar permissions. The prior `security.md` was treated as a failed baseline, not as evidence of the current state.

Focused temporary-fixture verification passed:

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q \
  tests/phase3/test_output_layout_snapshot_adversarial.py::test_snapshot_fifo_substitution_before_regular_file_open_is_nonblocking_and_normalized \
  tests/phase3/test_output_layout_view_races.py::test_private_stage_walkers_reject_synthetic_depth_and_entry_limits \
  tests/phase3/test_output_layout_view_races.py::test_partial_private_stage_construction_preserves_primary_failure_and_only_cleans_owned_entries \
  tests/phase3/test_output_layout_view_races.py::test_stage_cleanup_retains_racer_replacement_after_quarantine_validation \
  tests/phase3/test_output_layout_view_races.py::test_public_final_racer_substitution_after_publish_is_not_retained \
  tests/phase3/test_output_layout_receipt_adversarial.py::test_receipt_cleanup_retains_racer_sidecar_after_quarantine_validation \
  tests/phase3/test_output_layout_receipt_adversarial.py::test_recovery_sidecars_require_exact_private_mode_at_read_and_cleanup
```

Result: `17 passed in 0.35s`.

## Ranked findings

### High: final quarantine check-to-delete race can remove a racer replacement

**CWE-367: Time-of-check Time-of-use race condition.**

`scripts/phase3/output_layout_view_stage.py:249-264` checks an owned child entry's device, inode, and type with `os.stat(..., follow_symlinks=False)`, then separately calls `os.rmdir` or `os.unlink` by that entry name. `cleanup()` similarly checks the quarantined stage identity at lines 179-181 and separately calls `os.rmdir` at line 182. A concurrent actor able to mutate the same private-stage parent, such as a same-UID process, can replace the validated name after the final check and before the removal syscall. An empty directory replacement is removed by `rmdir`; a regular-file or symlink replacement is removed by `unlink`.

`scripts/phase3/output_layout_receipt_transaction.py:207-226` has the same terminal seam. `_read_entry()` validates the quarantined sidecar's digest and `(device, inode)` identity at lines 220-222, but `os.unlink(quarantine_name, ...)` at line 224 resolves the directory entry again. A same-privilege actor can install a regular-file or symlink replacement in that interval and have it unlinked.

The existing tests cover only an earlier seam. The stage test replaces `.cleanup` during the first post-rename `stat`, and the receipt test replaces `.remove` during the first post-rename `_read_entry`; both then fail at the later terminal validation before deletion. Neither test replaces the entry immediately before the final `rmdir` or `unlink` syscall. Descriptor-relative paths and `O_NOFOLLOW` constrain traversal, but do not pin a directory entry for a later name-based deletion.

**Impact and preconditions:** this is a no-clobber violation and unauthorized deletion of a replacement chosen by a concurrent actor that can rename/unlink/create under the relevant parent. The private stage's `0700` mode prevents ordinary other-UID actors, but not a same-UID concurrent process. Receipt-parent exploitability likewise depends on its actual directory permissions. The issue does not require symlink traversal or cross-filesystem behavior.

**Required regression:** hook the final `os.rmdir` and `os.unlink` dispatchers to move the validated temporary object aside, install a compatible racer replacement under its original quarantine name, then invoke the original syscall. Secure behavior must fail and retain the racer object.

## Positive controls

- **A. Nonblocking descriptor opens:** `output_layout_snapshot._add_regular_file()` and `output_layout_view_content._digest_file()` both use `O_NOFOLLOW | O_NONBLOCK`, then `fstat` the opened descriptor and reject anything not matching the expected regular-file identity. The focused FIFO substitution test passed for snapshot. The protected-content implementation uses the same flag construction and identity checks.
- **B. Bounded stage scan and fsync:** `output_layout_view_stage` supplies `WalkLimits(128, 100000)` to the shared descriptor-rooted walker. `scan()` and `fsync_tree()` reject excess depth and entries, use no-follow directory opens, and revalidate each opened child descriptor. All four depth/entry and scan/fsync parameter cases passed.
- **C. Partial ownership ledger and primary error:** `create_tree()` replaces `PrivateStage` after every created directory and symlink; `StageConstructionError` carries that current stage. `create_output_layout_view()` recovers it for cleanup while preserving the original construction failure. The focused test verified the primary synthetic error and retained an unowned racer child.
- **E. Publication mismatch handling:** `publish()` uses no-replace rename and verifies the final identity. A mismatch becomes `OutputLayoutViewError`; cleanup does not delete the substituted public object. The focused post-publish substitution test passed and showed that no complete canonical view is accepted.
- **F. Exact `0600` recovery sidecars:** new `.txn` and `.swap` entries are created with `O_EXCL` and explicitly `fchmod(0o600)`. `_read_entry()` rejects recovery sidecars whose exact mode differs from `0600`, including during cleanup/recovery. The eight transaction/swap and mode parameter combinations passed.

## Residual risks

- The reported high-severity final deletion window blocks PASS. A successful repair must eliminate or make safe the final name-resolution race, not merely add another immediately preceding check.
- Retaining a post-publication racer object intentionally avoids deleting it, but a racer can leave an incomplete `outputs/datasets` ancestor that causes future creation attempts to fail closed. This is an availability trade-off, not an accepted-view integrity failure.
- The snapshot and protected-content walkers bound topology but do not impose a cumulative byte or total-work budget. A writable protected tree containing many large regular files can still consume bounded-count but substantial hashing and fsync time. This is a residual availability risk rather than evidence of an unbounded-recursion defect.
- The snapshot FIFO seam has direct adversarial coverage. Equivalent protected-content FIFO substitution coverage is absent, though the current source uses the same nonblocking open and post-open type/identity verification pattern.

## Output non-mutation

This review did not access, enumerate, create, modify, or delete any real `outputs/` path or product output artifact. Source/test inspection was read-only. The executed tests used pytest `tmp_path` fixtures only, with bytecode generation and pytest caching disabled; their temporary files were not repository outputs. The only repository write made by this review is this requested evidence file.

VERDICT: FAIL
