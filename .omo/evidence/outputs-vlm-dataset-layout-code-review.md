# Output-layout migration code review

## Result

- PASS/FAIL: FAIL
- codeQualityStatus: BLOCK
- recommendation: REQUEST_CHANGES
- Revision anchor: `feb0309a96e0e457e3b1f90d482ec8e020f59503`
- Scope: current untracked organizer, lock, journal, copy, consumers, and focused tests in the intentionally dirty worktree.

## Evidence

The requested ULW attempt directory was unavailable: `omo ulw-loop status --json` returned `ULW_LOOP_PLAN_MISSING`. This report uses the required fallback path.

The required manual QA command was run twice with `timeout 60s`:

```bash
source ~/cd_vlaplan && timeout 60s python -m scripts.phase3.organize_outputs verify --repo-root .
```

Neither attempt emitted `{"command": "verify", "ok": true}` before the timeout. The first was contended by an existing organizer lock holder; the repeat ran after it cleared and also did not finish within 60 seconds. The verifier processes were subsequently absent (`pgrep` returned no matching process). This fails the explicit manual-QA pass criterion.

Focused collection was bounded with `timeout 60s pytest --collect-only -q` over organizer, lock, rename, and view tests. It collected 21 tests but failed with five import errors. The bounded focused run also failed collection with the same organizer-helper and lock-import errors.

## Findings

### CRITICAL

None.

### HIGH

1. Directory relocation can overwrite a racing destination, so its advertised no-clobber guarantee is false. `rename_noreplace()` checks absence twice, then calls ordinary `os.rename()` ([output_layout_rename.py](/scratch/punim0478/sukaih/multimodality_on_planning/scripts/phase3/output_layout_rename.py:30), [output_layout_rename.py](/scratch/punim0478/sukaih/multimodality_on_planning/scripts/phase3/output_layout_rename.py:33)). On POSIX, `rename` replaces an existing destination; a creator between the second check and `os.rename` loses its object. The exclusive organizer lock only coordinates cooperative organizers, not arbitrary GPFS writers. This violates the migration's collision-abort/no-clobber requirement.

2. Relevant tests do not collect. [test_organize_outputs_hardening.py](/scratch/punim0478/sukaih/multimodality_on_planning/tests/phase3/test_organize_outputs_hardening.py:15) and [test_organize_outputs_semantics.py](/scratch/punim0478/sukaih/multimodality_on_planning/tests/phase3/test_organize_outputs_semantics.py:10) import a removed `receipt_path` helper. [test_output_layout_lock.py](/scratch/punim0478/sukaih/multimodality_on_planning/tests/phase3/test_output_layout_lock.py:14) imports `tests.phase3`, which is not importable. The retained view modules import deleted `VIEW_ROOT` from the new contract ([output_layout_view_types.py](/scratch/punim0478/sukaih/multimodality_on_planning/scripts/phase3/output_layout_view_types.py:8)). This rejects claims that focused migration tests collect or protect the current layout.

3. The required live verifier has no current successful, bounded run. It did not meet the specified 60-second, exit-0, exact-JSON criterion during this review. The provided stale QA record is not sufficient to override this direct failed verification.

### MEDIUM

1. The completed-apply lock claim is correct in production but not proved by its test. `apply()` enters `exclusive_output_layout_lock()` before checking `complete.json` ([organize_outputs.py](/scratch/punim0478/sukaih/multimodality_on_planning/scripts/phase3/organize_outputs.py:43), [organize_outputs.py](/scratch/punim0478/sukaih/multimodality_on_planning/scripts/phase3/organize_outputs.py:46)); it calls the internal locked-state verifier rather than acquiring again. But [test_organize_outputs.py](/scratch/punim0478/sukaih/multimodality_on_planning/tests/phase3/test_organize_outputs.py:68) is misleadingly named `returns_without_locking_again` while it never holds a competing lock. It only proves a completed subprocess exits, not that it waits for the lock and validates post-lock state. This is a brittle, false-confidence test under both skill perspectives.

2. Legacy `outputs/datasets` publication code and tests remain after the contract removed that topology. The broken import above prevents it from loading, while the stale view tests still assert `outputs/datasets` behavior ([test_output_layout_view.py](/scratch/punim0478/sukaih/multimodality_on_planning/tests/phase3/test_output_layout_view.py:17)). This is dead, incompatible migration surface and conflicts with exactly three live categories.

### LOW

None.

## Claim Validation

| Claim | Review result | Evidence |
| --- | --- | --- |
| Completed-apply locking | Production path validated; test evidence inadequate | `apply` locks before complete-state verification; test does not contend the lock. |
| No-clobber record-copy publication | Valid | `_copy_file` uses `os.link` and converts `FileExistsError` to a collision ([organize_outputs.py](/scratch/punim0478/sukaih/multimodality_on_planning/scripts/phase3/organize_outputs.py:257), [organize_outputs.py](/scratch/punim0478/sukaih/multimodality_on_planning/scripts/phase3/organize_outputs.py:262)). |
| No-clobber directory relocation | Rejected | Ordinary `os.rename` has an unavoidable destination-creation race. |
| Focused test collection | Rejected | 21 collected, five collection errors. |

## Skill-perspective Check

Ran before judging test relevance and maintainability: `omo:remove-ai-slops` and `omo:programming`.

- `remove-ai-slops`: violation. The retained legacy view tests and the non-contending completed-lock test provide stale or false confidence rather than exercising required observable behavior.
- `programming`: violation. Tests are brittle implementation/API mirrors, and the relocation path validates a condition that the subsequent ordinary rename cannot enforce atomically.

## Blockers

- Replace directory publication with a mechanism that cannot overwrite a destination created after validation, or explicitly serialize all possible writers through an enforceable boundary.
- Repair/remove stale view surface and make the focused organizer/lock tests collect.
- Add a real competing-lock completed-apply test and an adversarial racing-destination test that proves the directory winner is never overwritten.
- Produce the required bounded verifier success output.

## Cleanup

No data, project code, Git state, or processes were mutated by this review. The required report artifact is the only file written.
