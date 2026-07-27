# Phase 3 Ferry Shared-Location Lane Remediation

## Scope

This remediation addresses the Ferry full-pilot state
`33b9c9648b4b132c94467949b8427b34` for
`ferry-dev-easy-0000`. No domain/problem PDDL, existing cache entry, or
semantic-validator logic was changed.

## Diagnosis

Both state facts `(at c0 l2)` and `(at c1 l2)` resolve to the same stage-zero
car bounds. The current cache key `84b7d426976a5d2acb7e0ea89f056f69` records
the exact duplicate pair at `(0.679, 0.868, 0.038, 0.17)`. The historical key
`beb1b18d1e76532e3f3e12beda158fad` has the same positional collision, proving
that this is not caused by the later 100x70 car geometry change.

The original `at` rule only assigned car x from its location. The first repair
attempt used `distribute_within_objects_vertical`; its one fresh bounded
canary rendered successfully but returned `coincident_sprite_bounds` because
the location y-coordinate was unset. The fresh VFG showed both cars at
`(false, false)`.

## Final Change

`data/pddl_instances/ferry/ap.pddl` now:

1. Anchors each location with `(equal (?l y) 0)`.
2. Assigns each `at` car to a vertical lane within its location using the
   existing Gripper distribution primitive.

`tests/phase3/test_planimation_profile_regressions.py` includes a regression
derived from the actual recorded `c0`/`c1` bounds. It preserves the validator's
fail-closed duplicate receipt and locks both parts of the final profile
contract.

The immutable Ferry post-`(:image` suffix was restored after every profile
edit and verifies as:

```text
871681463f96a3bd8af434bccbf54b2d7f8cbf0bf4cf14e6117fbfddcdaea355
```

## Verification

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_profile_regressions.py tests/phase3/test_render_semantics.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright tests/phase3/test_planimation_profile_regressions.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3 tests/phase3
git diff --check
```

The focused pytest suite passed twice with `21 passed` each time. Basedpyright
reported 0 errors, 0 warnings, and 0 notes; compileall and diff checks passed.

## Remote Canary Result

The intermediate distribution-only remote run remains retained evidence: it
completed in one attempt but tested a profile with no location y-origin, so its
trace recorded both cars at `(false, false)` and failed closed.

One later explicitly authorized bounded remote canary used endpoint
`https://planimation.planning.domains`, timeout 90 seconds, and a maximum of
three attempts for the final y-anchored profile. It completed successfully in
one actual attempt. The remote metadata records profile SHA-256
`9295ea8b1ed5f60a05a98fcd5c2eac6c7cccef156c4572d59e5668300d4351b4`; the
unchanged validator returned `success`, `validated_expected_object_coverage`,
and `6/6` coverage for a `1024x1024` frame.

The new trace places `c0` at `(345, 5)` with bounds `(0.689, 0.877, 0.047,
0.179)` and `c1` at `(345, 75)` with bounds `(0.689, 0.877, 0.179, 0.311)`.
They are distinct vertical lanes within `l2`, in canvas, and non-overlapping.
The review-ready receipt is at:

```text
.omo/evidence/planimation-pilot-contract-and-render-recovery/task-5-planimation-pilot-contract-and-render-recovery/ferry-shared-location-final-y-anchor-attempt/done-claim.json
```

No Todo 6 work was resumed, and existing cache entries were not mutated.
