# Lane 1 Directory-Lock Repair Done Claim

## Evidence Basis

Historical failures remain preserved and unmodified: [01-red-focused-pytest.txt](01-red-focused-pytest.txt) records 11 focused pre-repair failures, [02-red-manual-spawn.txt](02-red-manual-spawn.txt) records the pre-repair manual QA failure, [red-pytest.txt](../red-pytest.txt) records the original missing-module collection failure, and [red-api-ordering.txt](../red-api-ordering.txt) records the obsolete two-argument API failure. The earlier [green-validation.txt](../green-validation.txt) is retained as historical validation rather than overwritten.

The latest successful results are recorded in the [interruption-cleanup follow-up DoneClaim](../interruption-cleanup-follow-up-2026-07-27/DoneClaim.md) and its linked receipts. The earlier [strict-validation follow-up DoneClaim](../strict-validation-follow-up-2026-07-27/DoneClaim.md), including its 28-test results, remains preserved as prior evidence but is superseded for final status by the 32-case interruption follow-up. This directory's [14-basedpyright.txt](14-basedpyright.txt) and [16-no-excuse.txt](16-no-excuse.txt) remain preserved as provisional failure evidence.

## Claims Supported by the Receipts

- The latest split collected 32 focused tests across the public, descriptor, and interruption modules; all 32 passed in 8.44s. The dedicated interruption run passed 4 cases after the preserved RED run failed 4 with 7 deselected. Manual spawned QA printed both explicit PASS lines, the writer overlay suite passed 6 tests in 2.81s, and the two organizer overlay regressions passed in 2.47s.
- The repair preserves the one-argument repository-only shared and exclusive API demonstrated by the historical API-ordering red receipt. It locks a safely opened directory descriptor, not a legacy `.phase3-output-layout.lock` file; manual QA confirms fresh shared and exclusive acquisition create no legacy file and that replacing a legacy pathname cannot bypass a held exclusive directory lock.
- Descriptor ownership covers the lock context. After open, `acquired` is false. Identity is verified, flock runs, and acquired becomes true only after flock returns. Post-acquisition verification and yield follow. A state-based `finally` conditionally unlocks, then closes unconditionally. This covers KeyboardInterrupt without broad catches, retries, fallbacks, nested locks, or legacy locks.
- All validation behavior in this lane is synthetic-only. No real output path was accessed; stale legacy entries were not mutated; no organizer or writer product file was edited; and no root artifact was deleted. No commit was created.
- Compilation exited 0 across eight named files, and the no-excuse audit found no violations in those eight files. The existing strict config and interruption config each emitted 0 errors, 0 warnings, and 0 notes for their config-defined six-file historical lane scope and three-file interruption scope. These were not a single all-files project check.
- The active environment lacked `typing_extensions`. Writer and organizer tests used a temporary `uv run --no-project --with typing_extensions --with pytest` overlay after the required environment prefix. No permanent dependency was installed, and no project environment or dependency file was changed.
- Ruff remained unavailable and uninstalled. No Ruff check was run.
- `GIT_MASTER=1 git diff --check` exited 0 with no output. It checks tracked diff only and therefore does not validate untracked-file whitespace.
- Oracle rejected the first implementation over interruption cleanup. The state-based `finally` remediation is now red-to-green and fully validated. The post-remediation Oracle re-review returned `APPROVE`, providing final Oracle approval for the implementation.
