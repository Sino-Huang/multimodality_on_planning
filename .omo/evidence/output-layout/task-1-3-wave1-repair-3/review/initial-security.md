# Wave 1 Output-Layout Repair 3: Defensive Filesystem-Security Review

> HISTORICAL FIRST-ROUND REVIEW: superseded by descriptor-bound final exact-tree and pathname-identity validation for the existing-view path. Preserve for audit history; do not treat this file as a current verdict.

## Scope and Method

This is an independent, fresh review of the current `scripts/phase3/output_layout*.py`
source and current focused tests. Repair 2's `review/security.md` was used only to
identify the three prior blockers to re-test: pre-rename source substitution,
post-publication exact-tree/pathname identity, and pre-read aggregate byte limits.
It was not used as current evidence.

No real repository `outputs/` path or content was listed, statted, opened, read,
hashed, created, renamed, or deleted. All executed tests and the direct substitution
probe used pytest-managed or `TemporaryDirectory` synthetic trees.

## Result

No exploitable high-severity filesystem finding was reproduced in the current code.

### Publication and Existing-View Integrity

- **Source-stage substitution before rename: PASS.** `publish()` validates the held
  private descriptor and the source pathname, performs `renameat2(RENAME_NOREPLACE)`,
  opens the final name with `O_DIRECTORY|O_NOFOLLOW`, then requires the held final
  descriptor to match the original private-stage identity. A direct synthetic probe
  replaced the private source name immediately before the no-replace call; creation
  rejected it with `OutputLayoutViewError` rather than returning success.
- **Exact-contract public-root replacement: PASS during the call.** The published
  root is retained as `PublishedStage`, and `validate_tree()` walks that held final
  descriptor. The final public pathname is independently checked against the held
  descriptor identity by `validate_published_pathname()` before success.
- **Replacement after final descriptor acquisition: PASS.** A focused regression
  test replaces the canonical name immediately after `publish()` obtains its final
  descriptor. The descriptor/pathname identity mismatch fails closed.
- **Existing-view identity assumptions: PASS during the call.** Preflight pins the
  output root, destination ancestors, existing links, and protected targets.
  `_revalidate_plan()` checks those pins through the held outputs descriptor before
  and after existing-view validation and per-link verification. A pre-existing
  parent/link replacement therefore fails rather than being accepted.
- **No-clobber: PASS.** New view publication and receipt initial publication use
  `renameat2(RENAME_NOREPLACE)`. A competing final root blocks publication rather
  than being overwritten.

### Traversal, Content, and Escape Controls

- **Snapshot and protected-content byte limits: PASS.** Both regular-file loops use
  `TraversalBudget.next_read_size()` before every read. The resulting request is
  capped to the remaining aggregate allowance; an oversized file cannot consume a
  full chunk after the budget is exhausted. Empty files do not probe EOF after an
  exact budget exhaustion.
- **Cumulative traversal bounds: PASS.** Snapshot and protected-content walks share
  cumulative entry and byte budgets across recursive descendants; stage scanning and
  fsync walking carry a cumulative entry budget and enforce depth limits. The limits
  are 100,000 entries and depth 128 for the relevant walkers.
- **Symlink and pathname escape: PASS.** Directory opens are descriptor-relative,
  `O_DIRECTORY|O_NOFOLLOW`, and identity-checked after open. Receipt-parent
  traversal rejects `.`/`..` and symlink components. Snapshot symlinks must normalize
  inside their root; protected target ancestors must be real directories.
- **Special-file nonblocking opens: PASS.** Snapshot regular-file and protected-file
  opens use both `O_NOFOLLOW` and `O_NONBLOCK`, then require a regular file by
  `fstat`. FIFOs, devices, and sockets are rejected rather than read or blocked on.

### Retention, Receipts, and Descriptors

- **Retention-only cleanup: PASS.** Failed private view stages are retained under
  their original unique name and only fsync their parent; current cleanup has no
  terminal delete or rename. Direct-publication rollback reports retained entries
  rather than deleting names. Receipt sidecars use no-replace renames into retained
  evidence names, never a terminal unlink/rmdir/delete dispatch. A source race can
  at most cause an untrusted same-namespace object to be retained; it cannot clobber
  a destination or delete a racer object.
- **Receipt-sidecar safety: PASS.** Receipt and sidecar reads are no-follow,
  nonblocking, regular-file-only, exact mode `0600`, and capped at 16 MiB before and
  during reading. Sidecar creation is `O_CREAT|O_EXCL|O_NOFOLLOW`, mode `0600`, with
  file and parent fsync boundaries. Exchange-race recovery preserves a racer rather
  than overwriting it.
- **Descriptor closure: PASS.** The repaired `locate_missing_ancestor()` closes its
  duplicated descriptor if child `openat()` fails. Stage, snapshot, protected-content,
  and receipt paths close acquired descriptors in `finally` blocks or explicit error
  paths; focused descriptor-closure tests cover representative open/fstat/read
  failures.
- **Deletion-surface check: PASS.** A static search of active output-layout source
  found no `os.unlink`, `os.remove`, `os.rmdir`, `Path.unlink`, `Path.rmdir`, or
  recursive-delete use. The only namespace transitions found are the explicitly
  reviewed `renameat2` operations.

## Focused Validation

Executed in the project virtual environment, against synthetic temporary trees only:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q \
  tests/phase3/test_output_layout_view_exact_tree_race.py \
  tests/phase3/test_output_layout_aggregate_budgets.py \
  tests/phase3/test_output_layout_stage_construction_races.py::test_locate_missing_ancestor_closes_duplicated_descriptor_when_child_open_fails \
  tests/phase3/test_output_layout_view_races.py::test_public_final_racer_substitution_after_publish_is_not_retained \
  tests/phase3/test_output_layout_snapshot_adversarial.py::test_snapshot_fifo_substitution_before_regular_file_open_is_nonblocking_and_normalized \
  tests/phase3/test_output_layout_protected_content_security.py::test_protected_content_fifo_substitution_before_regular_file_open_is_nonblocking \
  tests/phase3/test_output_layout_acceptance_security.py::test_receipt_sidecar_racer_is_restored_after_quarantine_mismatch \
  tests/phase3/test_output_layout_receipt_adversarial.py::test_replacement_race_is_restored_without_clobbering_racer \
  tests/phase3/test_output_layout_view_adversarial.py::test_preexisting_link_and_parent_replacement_after_preflight_are_rejected
```

Result: `22 passed in 0.80s`.

An additional direct, in-memory Python probe replaced the private stage name at the
exact `RENAME_NOREPLACE` seam. It reported
`source-stage-substitution: rejected` and did not allow a successful view creation.

A broader synthetic-only run of 147 focused tests produced 145 passes and two stale
test failures that do not indicate a current product-path vulnerability:

1. `test_private_stage_cleanup_preserves_unowned_child` still expects the removed
   legacy `<stage>.cleanup` rename, while current cleanup deliberately retains the
   original private name without any pathname mutation.
2. `test_new_view_revalidates_protected_content_after_publication` monkeypatches
   `publish()` without returning the original `PublishedStage`, so downstream code
   receives `None` before it can perform the intended content-race assertion.

## Same-Permission Parent Namespace Boundary

This code detects and fails closed on replacements that occur while it still owns
pinned descriptors and before its final pathname-identity check. It cannot make a
pathname permanently immutable against an attacker who retains write/rename
permission on the same parent directory: that actor may replace the public view,
an accepted pre-existing exact-contract view, or retained evidence after the
operation returns. POSIX descriptor pinning cannot revoke that namespace authority.
Reliable persistence beyond the call requires a parent namespace inaccessible to
the attacker (or an external trusted ownership/attestation boundary); it cannot be
provided by a user-space no-clobber rename alone.

VERDICT: PASS
