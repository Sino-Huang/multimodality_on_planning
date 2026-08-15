# Phase 3 CGAS Partition Selection

## Result

`planning_cgas_v1` selection is a local `draft_for_owner_review`, not a production or approved partition. The verified characterization bundle was parsed through `parse_bundle()` after validating its SHA-256 `942d7be93ad0eb0ec6580bfe380fb8f09141662140ffc3d3c98e7f09a10ddaf4` and run fingerprint `0856e76571643362abb70551ff9d4e02e2d585f7384fc3ac0adb64df240d893a`.

The draft fails closed with `failure=structural_ood_ineligible`. Of 481 rows, only 24 rows are paired-exact and complete (all four-object); every 12-object row is ineligible because at least one BFS/IW source trace is incomplete. No roles are assigned, `records` is empty, `owner_approved` is false, and no approval digest exists.

## Policy

- Require both BFS and width-1 IW to be replay-valid, goal-satisfying, exact, and complete-trace eligible.
- Structural OOD is the union of all 12-object rows, complete 90th-percentile BFS/IW horizon ties, complete 90th-percentile BFS/IW expansion-count branching ties, and whole SHA-256 ordered composition groups until at least 20 rows and 10 signatures are present.
- Whole composition signatures have one role only. Calibration must be exactly 39 rows; its group order is deterministic farthest-point Gower sampling. Remaining whole groups use deterministic approximate 80/10/10 train/dev/test allocation with dev and test each at least 20 rows.
- Every draft binds source, characterization-artifact, implementation, and policy SHA-256 values and audits identity uniqueness plus composition-role leakage.

## Retained Artifacts

- `.omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft.json`
- `.omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft-rerun.json`

Both draft bytes have SHA-256 `409f712797f8f02d49fe6d6b5a5b4e7a444f38c54e2cdefcbd4e0e9e7214630d`.

## Verification

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_partition_selection.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_partition_selection.py tests/phase3/test_cgas_partition_selection.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_partition_selection --bundle tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas --output .omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft.json
source ~/cd_vlaplan && sha256sum .omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft.json .omo/evidence/cgas-partition-characterization/planning_cgas_v1-draft-rerun.json
```

Focused tests: `7 passed`. Basedpyright: `0 errors, 0 warnings, 0 notes`. The deterministic rerun hashes are identical.

## Owner Review Instructions

Do not approve or promote this draft. Review the recorded exclusions and `structural_ood_ineligible` failure. A successor characterization must provide paired-exact complete BFS and IW records for every 12-object row, then rerun the selector and verify a role-bearing draft with 39 calibration rows, disjoint complete role coverage, no composition leakage, and dev/test counts of at least 20. Owner approval remains an explicit later action and is intentionally not represented by an artifact here.
