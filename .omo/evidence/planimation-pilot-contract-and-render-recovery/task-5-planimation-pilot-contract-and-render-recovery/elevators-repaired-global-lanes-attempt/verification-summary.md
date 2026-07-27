# Elevators Global Passenger Lane Verification

## Root Cause and Delta

The retained state contains `(origin p0 f2)`, `(origin p1 f0)`, `(destin p1 f2)`, `(lift-at f2)`, and `(served p1)`. The old floor-local origin rule gave each lone passenger `x=0`. Because `served` correctly retained p1's x while moving it to f2, p0 and p1 had identical bounds `(0.059, 0.118, 0.476, 0.535)`. The unchanged validator rejected that VFG as `coincident_sprite_bounds` before PNG coverage evaluation.

The only profile delta is in `data/pddl_instances/elevators/elevators_ap.pddl`:

```lisp
(assign (?p x) (function distributex (objects ?p)))
```

This replaces the floor-local `distribute_within_objects_horizontal (objects ?p ?f)` assignment. `served` remains free of x assignment and `boarded` retains its lift-local placement rule.

## Red, Green, and Immutable Inputs

- Added `test_elevators_served_passengers_use_distinct_global_origin_lanes` in `tests/phase3/test_planimation_profile_regressions.py`.
- Red command:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_planimation_profile_regressions.py::test_elevators_served_passengers_use_distinct_global_origin_lanes
```

- Red result: `1 failed`; the required global-origin assignment was absent from the old profile.
- Green result: `1 passed` after the one-expression profile repair.
- Full focused suite was executed twice:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_planimation_profile_regressions.py tests/phase3/test_render_semantics.py
```

- Results: `20 passed in 0.69s` and `20 passed in 0.93s`.
- `basedpyright tests/phase3/test_planimation_profile_regressions.py`: `0 errors, 0 warnings, 0 notes`.
- `python -m compileall -q tests/phase3/test_planimation_profile_regressions.py` and scoped `git diff --check` exited successfully.
- Post-`(:image` SHA-256 remains `98eabfd7f6a20104385a146aee971c6331c00514a81254280fc7a1c1f8f39a19`.
- `scripts/phase3/render_semantics.py` SHA-256 remains `89738283d69ea51e2885eff3f421528d3940d05e7848b61595d1816528b3a8ae`.
- Retained problem SHA-256 remains `7ee8eff3be2074b0c283021b7e8400bc9f85f45331d2ef778a2d58f78e462c71`.

## Fresh Remote Canary

- Endpoint: `https://planimation.planning.domains`.
- Timeout: `90` seconds. Maximum attempts: `3`. Actual attempts: `1`.
- Result: `status=success`, `reason=validated_expected_object_coverage`, `sprite_count=7`, `covered_sprite_count=7`.
- Expected stage-zero sprites: `p0`, `p1`, `f0`, `f1`, `f2`, `f3`, `lift`.
- Passenger bounds: `p0=[0.059, 0.118, 0.476, 0.535]`; `p1=[0.176, 0.235, 0.476, 0.535]`; no bounds are coincident.
- `p1` remains `img-happy`; direct image inspection shows two separate passengers on f2, all four floors, and the lift without clipping.
- Raw artifacts are `result.json`, `remote-metadata.json`, `semantic-receipt.json`, `trace.vfg.json`, and `frames/frame_000.png` in this directory.
