# Phase 3 Ferry Shared-Location Lanes

## Finding

For Ferry state `33b9c9648b4b132c94467949b8427b34`, both cars are `at l2`.
The retained stage-zero VFG gives `c0` and `c1` the same bounds, causing the
strict semantic validator to return `coincident_sprite_bounds`.

The `on` predicate is not involved in this state. The duplicate survives both
current and historical cache keys, so it is not a stale-cache-only issue.

## Correct Profile Contract

`distribute_within_objects_vertical` needs concrete x and y container origins.
Ferry locations already derive x but previously left y unset. The correct
combination is:

```lisp
(:predicate location
    :parameters (?l)
    :effect(
    (assign (?l x) (function distributex (objects ?l)))
    (equal (?l y) 0)
    )
)

(:predicate at
    :parameters (?c ?l)
    :effect (
    (assign (?c x y) (function distribute_within_objects_vertical (objects ?c ?l)(settings (spacebtw 20) (row_count 5))))
    )
)
```

With no `(?l y)` assignment, the renderer recognizes the distribution function
but emits each car at `(false, false)`.

## Verification

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_profile_regressions.py tests/phase3/test_render_semantics.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright tests/phase3/test_planimation_profile_regressions.py
```

Both focused pytest runs passed with `21 passed`; basedpyright reported no
errors, warnings, or notes. The Ferry post-`(:image` suffix must remain
`871681463f96a3bd8af434bccbf54b2d7f8cbf0bf4cf14e6117fbfddcdaea355`.

The intermediate distribution-only canary remains a retained fail-closed
result: without a location y-origin, it placed both cars at `(false, false)`.

## Final Canary Result

The explicitly authorized final canary completed in one actual attempt against
`https://planimation.planning.domains`. With profile SHA-256
`9295ea8b1ed5f60a05a98fcd5c2eac6c7cccef156c4572d59e5668300d4351b4`, the
unchanged semantic validator reported `success`,
`validated_expected_object_coverage`, and `6/6` coverage. The fresh trace puts
`c0` at `(345, 5)` and `c1` at `(345, 75)` within `l2`; their bounds are
distinct, non-overlapping, and in canvas. Review the immutable receipts in
`.omo/evidence/planimation-pilot-contract-and-render-recovery/task-5-planimation-pilot-contract-and-render-recovery/ferry-shared-location-final-y-anchor-attempt/`.

This resolves the Ferry remediation-verification blocker only. Todo 6 remains
unstarted and requires separate authorization before any resume.
