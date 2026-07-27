# Wave 1 Output-Layout Repair 2: Defensive Filesystem-Security Review

## Scope and Method

This is a fresh review of the current Repair 2 source and tests. The earlier
`review/security.md` and `review/code-quality.md` were not used as current
evidence or as a verdict source.

The review used static inspection only: the current `scripts/phase3/output_layout*.py`
implementation, its focused adversarial tests, codegraph call paths, and a static
search for terminal deletion primitives. No tests were executed.

## Ranked Findings

### High: An exact-contract racer tree can replace the published tree and pass final verification

`create_output_layout_view()` publishes the private stage, then validates the
public name through a newly resolved pathname in
`scripts/phase3/output_layout_view.py:57-59`. `publish()` verifies the original
stage identity, but discards the resulting final-name identity after its check in
`scripts/phase3/output_layout_view_stage.py:143-156`. The subsequent
`validate_existing()` only checks tree shape and link text
(`scripts/phase3/output_layout_view_stage.py:126-136`); `_verify_all_links()`
checks protected target identity and symlink resolution, not that the public
root is still the published stage (`scripts/phase3/output_layout_view.py:115-128`).

An attacker able to rename entries in the stage parent can replace the public
root after `renameat2(RENAME_NOREPLACE)` and before final validation with an
exact clone of the required directory/symlink tree. The clone has the expected
link text and resolves to the pinned targets, so final verification can return
success while the public namespace is attacker-owned. This violates exact-tree
publication and leaves the attacker able to mutate the view after return.

`tests/phase3/test_output_layout_view_races.py:278-305` only substitutes an
empty directory, which final validation rejects. It does not cover a complete
exact-contract replacement.

### High: Stage-source substitution is possible between identity check and no-replace publication

`publish()` performs a pathname `stat()` of `stage.name` at
`scripts/phase3/output_layout_view_stage.py:145`, then separately calls
`renameat2(..., RENAME_NOREPLACE)` at lines 147-152. A writer of the parent
directory can replace the source stage name in that interval. The no-replace
flag protects an existing destination but does not bind the source pathname to
the previously checked inode. The replacement can therefore be moved to the
public final name before the post-rename identity comparison reports an error
at lines 153-155.

The operation fails rather than silently accepting the substitution, but it
leaves the substituted object at the public name. There is no safe rollback of
that public name, by design, so this remains a publication-integrity failure.
No current test injects a source-stage replacement specifically between lines
145 and 147.

### High: The snapshot aggregate-byte cap is applied after a complete single-file read

`_add_regular_file()` in `scripts/phase3/output_layout_snapshot.py:178-214`
reads an entire regular file in its loop at lines 202-204. Its caller accounts
the file's bytes against `TraversalBudget` only after that read returns at
`scripts/phase3/output_layout_snapshot.py:108-111`. Consequently, one file
larger than the declared 1 GiB aggregate budget can consume its full read and
hashing cost before the budget rejects it. This defeats the budget as an
availability bound for a single oversized input.

`tests/phase3/test_output_layout_aggregate_budgets.py:24-31` proves eventual
rejection using a five-byte fixture and a four-byte cap, but cannot establish
pre-read enforcement. A regression should use an instrumented read function
and assert that reads do not exceed the remaining budget.

### Medium: `locate_missing_ancestor()` leaks a directory descriptor when `openat` fails

`scripts/phase3/output_layout_view_stage.py:58-74` duplicates the outputs
descriptor, then advances through existing ancestors. If `os.open()` at line
70 fails after the non-following `stat()` accepted the entry, execution exits
without closing the current duplicated descriptor. Repeated adversarial
ancestor replacement or permission failures can exhaust descriptors in the
calling process. The successful and explicit wrong-type paths close their
descriptors, so this is confined to the `openat` failure path. No focused test
exercises this failure and asserts closure.

### Medium: Retained-stage evidence is no-replace but not source-identity atomic

`cleanup()` checks the stage pathname and open descriptor at
`scripts/phase3/output_layout_view_stage.py:162-166`, then separately renames
the pathname to `<stage>.cleanup` with `RENAME_NOREPLACE` at lines 167-173. A
racer can replace the checked source name between those operations; the racer
object is then retained under the cleanup name. The identity check after the
rename detects this, but only after the namespace transition and before the
parent `fsync` at line 176. Thus the code does not delete the racer, but it
cannot promise that the retained name is durable evidence of the owned stage.

The analogous receipt-sidecar path first validates a digest and then renames
the pathname at `scripts/phase3/output_layout_receipt_transaction.py:206-216`.
It uses `RENAME_NOREPLACE` and its callers fsync the parent immediately after
the transition (`:131-137`), but it likewise lacks an atomic source-identity
binding. The current tests cover collision and preservation behavior, not a
source replacement in this exact validation-to-rename window.

## Positive Controls

- A static search of the active `scripts/phase3/output_layout*.py` source found
  no `os.unlink`, `os.rmdir`, `os.remove`, `Path.unlink`, `Path.rmdir`, or
  recursive-delete call. There is no terminal cleanup pathname capable of
  deleting a racer object in the current output-layout implementation.
- Direct-publication rollback intentionally retains rather than removes names:
  `scripts/phase3/output_layout_view_fs.py:200-218` returns a retention
  failure instead of dispatching deletion.
- Private-stage cleanup uses descriptor-relative
  `renameat2(RENAME_NOREPLACE)` and fsyncs the parent on a successful verified
  transition (`scripts/phase3/output_layout_view_stage.py:159-176`). Receipt
  sidecars are similarly moved with `RENAME_NOREPLACE`; each successful
  `_remove_entry()` caller fsyncs the parent
  (`scripts/phase3/output_layout_receipt_transaction.py:123-137`). These
  controls prevent destination clobbering and avoid terminal deletion.
- Descriptor-rooted traversal uses `dir_fd`, `O_DIRECTORY`, and `O_NOFOLLOW`.
  Stage/content/snapshot walks recheck directory identity after opening and
  reject unsupported stage or protected-content entry types, including FIFO,
  devices, and sockets (`output_layout_view_walk.py:40-55`,
  `output_layout_view_content.py:36-50`, and `output_layout_snapshot.py:105-123`).
- Receipt and recovery-sidecar reads are regular-file-only, no-follow,
  nonblocking, bounded to 16 MiB, and require private `0600` mode
  (`scripts/phase3/output_layout_receipt_io.py:55-83` and
  `scripts/phase3/output_layout_receipt_transaction.py:164-197`). Creation
  uses `O_EXCL|O_NOFOLLOW`, `0600`, file fsync, and parent fsync
  (`scripts/phase3/output_layout_receipt_transaction.py:140-152`).
- Existing tests exercise protected-content FIFO substitution, special-file
  rejection, descriptor closure on several error paths, sidecar modes,
  no-clobber initial publication, parent replacement, crash boundaries, and
  post-fsync extra stage entries. The static review did not rely on those tests
  being executed.

## Residual Risks and Coverage Limits

- This report is static-only. No concurrency PoC or filesystem crash test was
  run, so kernel/filesystem-specific rename and fsync behavior remains outside
  the evidence.
- The real repository protected targets were deliberately not inspected. The
  real-target test `tests/phase3/test_output_layout_view.py:76-86` was excluded
  because it performs `lstat()` on those paths.
- The no-delete conclusion covers the current output-layout implementation.
  Tests still monkeypatch historical `os.rmdir` and `os.unlink` dispatch seams
  (`tests/phase3/test_output_layout_retention_dispatch_races.py:12-70`), but
  those functions are not reached by the current implementation.
- Aggregate entry/depth controls and protected-content incremental byte
  accounting are present. The snapshot's per-file byte-accounting gap above is
  the remaining aggregate-exhaustion blocker.

## Non-Mutation Statement

No real protected `outputs/` path or content was listed, statted, read,
hashed, opened, created, renamed, or deleted during this review. No test was
executed. The only repository mutation performed by this task is this evidence
report.

VERDICT: FAIL
