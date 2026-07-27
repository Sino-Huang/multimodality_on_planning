# Wave 1 Repair 3 Done Claim

Repair 3 closes the two Repair 2 security blockers and the review-discovered integration drift for Todos 1-3.

The publisher now returns and retains a descriptor-bound `PublishedStage`, validates the exact published tree and protected targets through that held descriptor, compares the canonical pathname identity with the held identity, and performs one last exact-tree scan before success. The idempotent existing-view branch applies the same final ordering while retaining the existing root and immediate parent descriptors. Failed private stages remain at their original unique private name without rename or deletion. Snapshot and protected-content readers request no more than the remaining byte budget plus one detection byte, including exactly-at-limit and zero-byte-at-limit behavior. The duplicated traversal descriptor is closed when a child open fails.

Legacy tests now match the Repair 3 retention contract, publication monkeypatches propagate `PublishedStage`, and sibling-test helper imports resolve consistently under pytest and Basedpyright.

Verification:
- Existing-view post-link mutation regression: failed before the fix and passes after it.
- Existing-view and first-publication post-pathname mutation regressions: failed before the fix and pass after it.
- Full output-layout suite: 213 passed.
- Strict Basedpyright: 0 errors, 0 warnings, 0 notes.
- Compileall: exit 0.
- No-excuse audit: no violations in all 18 output-layout production files.
- `git diff --check`: exit 0.
- Manual synthetic API QA: 15 links resolved, descriptor-bound second invocation idempotent, temporary tree cleaned.

Scope boundary:
- No real `outputs/` content was created, moved, rewritten, or deleted.
- All five fresh Repair 3 review lanes passed.
- Todo 4 integration is unblocked; all historical-root relocation remains blocked until Todo 4 passes.
