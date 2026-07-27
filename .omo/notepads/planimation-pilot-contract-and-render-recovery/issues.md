## 2026-07-25 Work initialization
- The `/start-work` hook failed to match the supplied `.md` suffix, but listed an exact unique plan stem; selection is unambiguous.
- Existing dirty `.omo/` state and the untracked launcher must not be overwritten or reverted.

## 2026-07-25 Wave 1 dispatch blocker
- All exposed `explore` workers enforced read-only scope and could not edit product/test files. Sessions: Graphplan `ses_067ced5aaffebWsPl93Xgs61R3`, profiles `ses_067ced22bffebML780YEAmyGu6`, launcher `ses_067ced10cffeyr1zo2AM5e8N3e`.
- The frozen-selection verifier lane timed out without an implementation receipt.
- Atlas is explicitly prohibited from writing product code, so execution is paused until an implementation-capable worker/task surface is available.

## 2026-07-25 Todo 4 verification observations
- The workspace `basedpyright` LSP client remained alive but timed out on repeated three-second diagnostics requests for the changed verifier and test files. Direct `basedpyright` completed with 0 errors, 0 warnings, 0 notes; `compileall` and scoped `git diff --check` also passed.
- The worktree was already dirty outside Todo 4, including Phase 3 reasoning, launcher, and other plan/test artifacts. Todo 4 did not alter those lanes.

## 2026-07-25 Todo 5 canary rejection
- Static gates passed with 111 focused tests, clean basedpyright/compileall/shell/diff checks, five extraction-bound Graphplan rows, and unchanged retained failure reasons.
- Fresh Gripper remote canary passed unchanged semantic validation with 13/13 covered sprites.
- Fresh Ferry remote rendering succeeded on attempt 1, but unchanged semantic validation rejected it as `expected_object_coverage_failed` with 5/6 sprites covered. Elevators and Logistics canaries were correctly not started.
- Todo 2 was reopened because structural profile tests did not prove actual Ferry expected-object coverage. Failure evidence is under `.omo/evidence/planimation-pilot-contract-and-render-recovery/task-5-planimation-pilot-contract-and-render-recovery/ferry-failed-attempt/`.

## 2026-07-25 Todo 5 Elevators canary rejection
- After the independently approved Ferry remediation, the focused suite passed 112 tests and every requested LSP/static gate was clean.
- Fresh Elevators remote rendering succeeded on attempt 1, but unchanged semantic validation rejected its VFG as `coincident_sprite_bounds` before PNG coverage evaluation. Logistics was correctly not started.
- Todo 2 was reopened again for a runtime-driven Elevators profile repair. Failure evidence is under `.omo/evidence/planimation-pilot-contract-and-render-recovery/task-5-planimation-pilot-contract-and-render-recovery/elevators-failed-attempt/`.

## 2026-07-25 Todo 5 resumed canary blocker
- The approved Ferry remediation recovered its fresh canary to 6/6 covered sprites, but the fresh retained Elevators canary remains `semantic_image_invalid: coincident_sprite_bounds` after renderer success on attempt 1. Its partial root was removed after copying all raw artifacts into `elevators-failed-attempt/`; Logistics was not started.

## 2026-07-25 Elevators remediation canary
- [active] One fresh retained-problem Elevators canary will be written to `.omo/evidence/planimation-pilot-contract-and-render-recovery/task-5-planimation-pilot-contract-and-render-recovery/elevators-repaired-global-lanes-attempt/` with endpoint `https://planimation.planning.domains`, `timeout_seconds=90`, and `max_attempts=3`. Do not retry outside that bounded run.

## 2026-07-25 Elevators remediation result
- [resolved] The one bounded canary completed on attempt 1 and passed unchanged semantic validation at `7/7` expected-object coverage. No additional Elevators render attempt or Logistics canary was started.

## 2026-07-25 Todo 5 final verification observation
- All four fresh canaries are semantically valid after the approved profile repairs. The only remaining verification-tool limitation is fresh LSP diagnostics timing out at the fixed 3-second harness deadline despite an alive client and a clean direct basedpyright run; independent review must assess this recorded limitation.

## 2026-07-25 Ferry shared-location canary resolution
- [resolved] The earlier intermediate-profile canary remains recorded as a fail-closed historical result: it rendered on attempt 1 but had `l2.y=false` and placed both cars at `(false, false)`.
- [resolved] One later explicitly authorized bounded canary tested the final y-anchored profile for the same state. It completed on attempt 1 and passed unchanged semantic validation at `6/6` expected-object coverage. Fresh trace bounds place `c0` and `c1` in distinct vertical lanes within `l2`.
- The final review receipt is `.omo/evidence/planimation-pilot-contract-and-render-recovery/task-5-planimation-pilot-contract-and-render-recovery/ferry-shared-location-final-y-anchor-attempt/done-claim.json`. No Todo 6 action was taken.
- Fresh LSP diagnostics for the Python regression test previously timed out at the fixed 3-second harness deadline. PDDL has no configured LSP server; direct basedpyright is clean.

## 2026-07-26T06:11:38Z Todo 7 verification observations
- [resolved] The source-manifest hash versus selected-subset hash mismatch no longer rejects an otherwise exact frozen subset. Complete record multiplicity remains part of the gate.
- [resolved] The historical 1.0-second-delay temporary fixture selected cache key `ad347eb66b12107b3630f86ae399c411` and made one remote request. Recovery used the exact zero-delay pilot config and cache key `45e2c4e6959e5c6b317384d94317d7b6`.
- Ruff was unavailable in the activated environment and wasn't installed. The retained source/test checks were otherwise clean: 21 focused tests passed, basedpyright reported no findings, and compileall plus `git diff --check` exited 0.

## 2026-07-26T06:34:29Z Todo 7 final Oracle finding
- [resolved] Oracle found a Medium documentation and contract-hardening gap: exact subset equality could not be described as sufficient when source provenance was missing or malformed. `_load_selection()` now requires exactly 64 lowercase hexadecimal characters and reports `invalid_frozen_selection` before subset fallback.
- [resolved] Negative coverage removes or uppercases the provenance value, recomputes the selection self-hash, and confirms promotion remains rejected. The validation branch also rejects wrong-length and other non-hexadecimal values.
