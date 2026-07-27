# Filesystem Migration Security Review

Status: FAIL

Scope: current dirty worktree relative to revision `feb0309a96e0e457e3b1f90d482ec8e020f59503`, with focus on `scripts.phase3.organize_outputs` and its filesystem helpers. The implementation files under review are untracked relative to the revision anchor.

## Findings

### CRITICAL

None.

### HIGH

1. Destination-absence checks do not make the GPFS ordinary rename no-clobber. `rename_noreplace` checks the destination twice and then calls ordinary `os.rename` ([output_layout_rename.py:30](/scratch/punim0478/sukaih/multimodality_on_planning/scripts/phase3/output_layout_rename.py:30), [output_layout_rename.py:33](/scratch/punim0478/sukaih/multimodality_on_planning/scripts/phase3/output_layout_rename.py:33)). A competing creator can create a destination after line 31 and before line 33; POSIX rename then replaces that entry. This can destroy a racing writer's directory/data and violates the required no-overwrite migration invariant. The test at [test_output_layout_rename.py:47](/scratch/punim0478/sukaih/multimodality_on_planning/tests/phase3/test_output_layout_rename.py:47) claims the destination before the second check, not in the vulnerable post-check window, so it does not exercise the race.

2. Journal pathname construction can traverse a symlinked intermediate component. `write_record` creates its parent with pathname-based `directory.mkdir(parents=True, exist_ok=True)` and opens the final record with a pathname ([output_layout_journal.py:25](/scratch/punim0478/sukaih/multimodality_on_planning/scripts/phase3/output_layout_journal.py:25)-[output_layout_journal.py:42](/scratch/punim0478/sukaih/multimodality_on_planning/scripts/phase3/output_layout_journal.py:42)). `O_NOFOLLOW` protects only the final filename, not a replacement `outputs/deprecated` or `receipts` directory. An attacker able to modify the working tree can redirect append-only journal writes outside the repository during migration, defeating the claimed path-traversal defense and contaminating an arbitrary writable directory.

### MEDIUM

1. Required manual verification was not successful. The required bounded command did not produce `{"command":"verify","ok":true}`. A subsequent bounded run exited `124`, while multiple `organize_outputs verify` processes remained blocked, including a process in uninterruptible `D` state. The final state cannot be approved because the required verifier has not established the postconditions and hung verifiers contradict the cleanup requirement. This is an operational data-safety risk during interruption/recovery rather than proof that the already-migrated payload changed.

### LOW

None.

## Evidence

- Current top-level `outputs/` entries were exactly `deprecated`, `image_frames`, and `reasoning_traces`.
- `outputs/deprecated/receipts/output-reorganization-20260727/` contained `prepared.json`, fifteen `move-*.json` records, `records.json`, and `complete.json`, all mode 0600.
- The live verification requirement failed: no required success JSON was observed; the bounded probe returned exit 124. Existing verifier processes were not terminated because this was a read-only review.

## Skill Perspective Check

Ran: `omo:remove-ai-slops` and `omo:programming` were loaded before judging test relevance and maintainability.

`remove-ai-slops`: violated by the misleading race test that only mirrors the second pre-rename check instead of exercising the observable no-clobber guarantee. `programming`: violated by the brittle implementation-mirroring test and by validation/path safety not being preserved at the filesystem boundary; the journal reverts to pathname parsing after hardened descriptor traversal exists elsewhere.

## Recommendation

`codeQualityStatus`: BLOCK

`recommendation`: REQUEST_CHANGES

`blockers`:

- Make data-root publication no-clobber across the final destination race, or explicitly serialize all possible destination writers with an enforceable lock and prove that guarantee.
- Create/open journal parents through pinned no-follow directory descriptors; reject an intermediate symlink replacement.
- Resolve the hung verifier condition and demonstrate the exact required command exits 0 with `{"command":"verify","ok":true}` and leaves no verifier process.
