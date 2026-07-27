# Goal And Constraint Review - Wave 1 Security Hardening

Confidence: high (0.98).

## Scope Reviewed

- `.omo/plans/outputs-vlm-dataset-layout.md`, especially Wave 1 Todos 2-3,
  the fail-closed requirement, and the no-partial-fixture guardrail.
- `.omo/evidence/output-layout/task-1-3-security-hardening/DoneClaim.md` and
  its recorded Oracle residual-risk statement.
- The seven claimed changed production modules and the claimed affected tests,
  plus the focused race/adversarial tests that exercise the same paths.

## Verified Satisfied Constraints

- Snapshot and protected-content walkers bound their own recursion to 128
  directories and their per-directory entries to 100,000:
  `output_layout_snapshot.py:16-17,106-107,127-129` and
  `output_layout_view_content.py:14-15,66-67,92-94`.
- Public receipt reads use `O_NOFOLLOW | O_NONBLOCK`, reject non-regular
  descriptors, and require exact `0600` mode:
  `output_layout_receipt_io.py:63-83`. Receipt transaction sidecar reads also
  use no-follow/nonblocking opens and regular-file validation:
  `output_layout_receipt_transaction.py:14-16,153-180`.
- Receipt JSON object members and array elements are counted recursively before
  typed materialization, with a 100,000-item cap, and duplicate JSON keys are
  rejected: `output_layout_receipt_values.py:17-40,70-93,96-121`.
- The receipt transaction public path enforces `0600` on an existing receipt,
  and newly created transaction/swap files are created and chmodded to `0600`:
  `output_layout_receipt_transaction.py:24-28,129-141`.
- Post-construction private-stage cleanup checks device, inode, and file type
  before deleting recorded entries; unowned/replaced entries are retained in
  quarantine rather than deleted: `output_layout_view_stage.py:148-177,265-292`.
- Strict type checking passed for every claimed changed module and affected
  test using the strict `/tmp/opencode/output-layout-pyrightconfig.json` plus
  explicit paths: `0 errors, 0 warnings, 0 notes`. The repository's normal
  `pyrightconfig.json` is nevertheless configured with `typeCheckingMode` set
  to `off`, so the DoneClaim's default-config type-check statement is not
  independent strict-typing evidence.
- Focused verification passed: `19 passed in 0.56s` for the acceptance suite
  and FIFO/quarantine filesystem QA. Those tests use pytest `tmp_path`; the
  pre- and post-checks `git status --short -- outputs` were both empty. This
  review did not edit the plan, product modules, real `outputs/`, or commits.

## Blocking Issues

1. **Regular-file reads are not nonblocking on two reachable paths.**
   `output_layout_snapshot._add_regular_file` opens a file with
   `O_RDONLY | O_NOFOLLOW` only (`output_layout_snapshot.py:179-187`), and
   `output_layout_view_content._digest_file` does the same
   (`output_layout_view_content.py:98-103`). If a path is classified as a
   regular file and then replaced by a FIFO before `open`, both paths can block
   indefinitely before their post-open regular-file checks run. `O_NOFOLLOW`
   only prevents symlink following; it does not prevent this regular-file to
   FIFO race. This violates the stated nonblocking/no-follow regular-file-read
   and fail-closed requirements.

2. **Private-stage validation and fsync have no recursion or entry limits.**
   `_scan` recursively walks every directory via `os.listdir` with no depth or
   cardinality bound (`output_layout_view_stage.py:232-248`), and
   `_fsync_directory` repeats the same unbounded recursion
   (`output_layout_view_stage.py:251-262`). A concurrent same-user mutation of
   the private stage can therefore force unbounded work or a recursion failure
   during validation/fsync. This contradicts the requested bounded-recursion
   guarantee and is a fail-closed availability failure.

3. **Partial private-stage construction loses ownership accounting.**
   `create_tree` accumulates ownership only in a local list and returns it only
   after all directories and links were created (`output_layout_view_stage.py:85-100`).
   If a guard, mkdir, or symlink operation fails mid-build, the caller still
   holds the original `PrivateStage(entries=())`. Cleanup then cannot remove
   its already-created entries and `rmdir` of the quarantined stage fails
   (`output_layout_view_stage.py:175-177`). This violates Todo 3's required
   rollback of links created during a failed invocation and the plan guardrail
   against partial temporary roots. The conservative behavior avoids deleting
   ambiguous entries, but it does not complete ownership-safe cleanup.

## Oracle Findings Disposition

Oracle's recorded broader findings are blockers here, not out-of-scope
residual risks. The first two defects can respectively hang before a
regular-file validation check and consume unbounded recursion/work; the third
can retain an incomplete private stage after a failed operation. None is a
reliable fail-closed rejection that preserves the completed operation's
cleanup invariant. The public receipt FIFO and stage-child tests demonstrate
only the narrower receipt and fully-recorded-stage paths, so their success
does not resolve these cases.

VERDICT: FAIL
