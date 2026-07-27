# Output-Layout Security Hardening Context Review

## Scope And Method

This is an independent repository-context review of the Wave 1 hardening. It
does not change product code or a real `outputs/` path.

Sources searched:

- Plan and draft: `.omo/plans/outputs-vlm-dataset-layout.md` and
  `.omo/drafts/outputs-vlm-dataset-layout.md`.
- Knowledge and documentation: `.omo/knowledges/phase3-output-layout-wave1-security-hardening-2026-07-27.md`,
  `.omo/knowledges/phase3-output-layout-receipt-fixed-sidecar-verification-2026-07-27.md`,
  `.omo/knowledges/filesystem-publication-review-criteria.md`, and
  `doc/detailed_implementation_summary/phase3_output_layout_wave1_security_hardening_2026-07-27.md`.
- Existing review evidence: `DoneClaim.md`, the recorded red baseline
  `01-focused-red-pytest.txt`, final suite receipt
  `43-final-output-layout-suite-pytest.txt`, and manual QA receipt
  `49-final-manual-filesystem-qa.txt` in this task directory.
- Current source, imports, callers, and adjacent tests under `scripts/phase3/`
  and `tests/phase3/`, using Codegraph and `rg`.
- Local Git history with read-only `GIT_MASTER=1 git log` and `git show` for
  predecessor filesystem code (`io_utils.py`, `rollout_gate_promotion.py`) and
  the new output-layout paths.

GitHub and Notion were not searched: they are not needed for this local
repository-context finding and no local integration was available. No real
`outputs/` path was opened for mutation.

## Required Context

Todo 2 requires deterministic snapshots to fail on special files and receipt
persistence to use a same-directory `0600` temporary regular file, no-clobber
or validated replacement, file and parent-directory `fsync`, symlink rejection,
and stale-temp handling (plan lines 124-129). Todo 3 requires a relative-link
view that fails without overwrite and rolls back links created by a failed
invocation (plan lines 133-138). The draft separately requires refusal of
overwrites, symlink traversal, dirty collisions, and classification drift
(draft lines 41-47).

The review criteria require race-free creation, interruption cleanup, and
collision/concurrency tests; it distinguishes atomic visibility from durability
(`filesystem-publication-review-criteria.md` lines 5-11). The Wave 1 knowledge
adds no-follow/nonblocking receipt reads, strict `0600` public receipts,
bounded snapshot/content traversal, and identity-owned private-stage cleanup
(`phase3-output-layout-wave1-security-hardening-2026-07-27.md` lines 3-18).

## Consumer And Test Surface

The changed Wave 1 files named by `DoneClaim.md` lines 8-22 are currently
untracked, so they have no direct committed file history. The local history
search found only predecessor Phase 3 commits `31dfbef` and `1adc829` for the
older I/O and promotion modules; it found no committed `renameat2` or
`O_NOFOLLOW` output-layout implementation. This is a history limitation, not
by itself a failure.

`create_output_layout_view()` has no production caller outside the
output-layout module graph; its callers are the output-layout view tests.
`snapshot_tree()` is consumed by `output_layout_inventory.py` and adjacent
tests. Receipt read/write functions are consumed by the inventory module and
receipt/inventory/security tests. This is consistent with Todo 4 still being
the deferred organizer/CLI integration point (plan lines 142-147), so no
unmapped production consumer was found.

The adjacent test suite is broad: it covers link and parent symlink races,
publication collisions, receipt replacement races, fixed-sidecar recovery,
depth limits for snapshot/content paths, and retained unowned stage children.
The recorded evidence shows the expected red baseline of seven failures before
hardening and a later `172 passed` suite result. The receipts establish test
chronology, but neither receipt supplies coverage for the two gaps below.

The evidence directory contains the combined Wave 1 receipt rather than the
separate Todo 2 and Todo 3 acceptance directories requested by the plan. No
Todo 4 organizer/locking receipt or final F1-F4 review artifact is present.
That does not turn the absent Todo 4 integration into a missed current caller:
the plan assigns concurrent organizers, shared-lock writers, uncooperative
writers, and other cross-process races to Todo 4. It does prevent treating this
synthetic Wave 1 result as an integrated migration approval.

The final command-line type-check receipt also reports two unrecognized
configuration settings, despite `DoneClaim.md` reporting clean diagnostics.
The difference is an evidence-quality concern; it is not needed for the
security verdict below.

## Oracle-Finding Mapping

`DoneClaim.md` lines 94-99 records five broader Oracle findings as intentionally
out of scope. They cannot all be treated as deferred because several are already
within Todos 2-3:

- Publication-name races overlap Todo 3's no-overwrite rule. The current private
  stage uses `RENAME_NOREPLACE` and verifies the stage identity before and after
  publication (`output_layout_view_stage.py` lines 132-145); staged-name race
  tests exist. This specific finding is materially addressed.
- Regular-file-to-FIFO races overlap Todo 2's requirement to fail on special
  files and Todo 3's protected-content verification. They remain unresolved:
  snapshot reads open a presumed regular file with `O_RDONLY | O_NOFOLLOW` but
  without `O_NONBLOCK` (`output_layout_snapshot.py` lines 170-187), and
  protected-content reads do the same (`output_layout_view_content.py` lines
  98-107). A replacement from a regular file to a FIFO after `stat` but before
  `open` can block instead of fail closed before the later regular-file check.
  Receipt and sidecar reads do include `O_NONBLOCK`
  (`output_layout_receipt_transaction.py` lines 14-17 and 153-180), confirming
  the missing protection is specific to snapshot/content readers.
- Partial-stage ledger loss overlaps Todo 3's required rollback. `create_tree`
  records owned entries only in a local list and returns the updated immutable
  `PrivateStage` only after the full operation succeeds
  (`output_layout_view_stage.py` lines 85-100). The caller assigns that returned
  value only after the call completes (`output_layout_view.py` lines 44-48).
  A mid-creation exception therefore leaves the caller with an empty-entry
  stage; cleanup loops only over that empty ledger before attempting to remove
  the nonempty quarantine directory (`output_layout_view_stage.py` lines
  148-177). The adjacent test named
  `test_primary_failure_aggregates_all_rollback_cleanup_failures` asserts only
  that the public `outputs/datasets` path is absent, not that the hidden private
  stage was removed (`test_output_layout_view_adversarial.py` lines 218-243).
- Sidecar mode and descriptor-cleanup gaps are partially addressed by
  `O_EXCL`, `0600`, no-follow, and nonblocking fixed-sidecar operations. The
  plan and current evidence do not demonstrate the broader Oracle issue is
  completely closed, but this review does not need to decide it because the two
  previous required gaps already fail the gate.
- Stage scan/fsync recursion remains uncapped in `_scan` and `fsync_tree`
  (`output_layout_view_stage.py` lines 232-262), while snapshot and protected
  content readers have explicit entry and depth caps. The plan does not state a
  separate stage-resource limit, so this is recorded as an unresolved hardening
  concern rather than an independent Todo 2-3 blocker.

## Blockers

1. Add a regression that replaces a regular snapshot/protected-content target
   with a FIFO immediately before descriptor open, then make both paths fail
   closed without blocking.
2. Preserve an incrementally durable ownership ledger, or scan and verify the
   private stage safely during failure cleanup, so an exception after partial
   stage creation removes only owned entries and leaves no hidden stage behind.
3. Re-run the focused security and complete output-layout suites after those
   regressions pass; record the new receipts beside this review.

VERDICT: FAIL
