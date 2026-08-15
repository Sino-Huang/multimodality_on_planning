# Phase 3 Planimation Used-PDDL-URL Contract Repair

## Issue

Successful fresh Planimation state renders persist the remote upload endpoint as `used_pddl_url`. Strict state-render validation rejected that legitimate field because it was absent from the optional persisted-record schema.

## Repair

- Added `used_pddl_url` to `STATE_OPTIONAL_FIELDS`.
- Validated it as optional nonempty text when present.
- Added an end-to-end regression test covering a successful renderer result through persisted-output validation.

## Verification

```bash
source ~/cd_vlaplan
source .venv/bin/activate
python -m pytest -q tests/phase3/test_planimation_pairing.py
python -m pytest -q tests/phase3/test_verify_planimation_vlm.py
basedpyright scripts/phase3/planimation_persisted_contracts.py tests/phase3/test_planimation_pairing.py
python -m compileall -q scripts/phase3 tests/phase3
git diff --check
```

Observed results: `48 passed`, `9 passed`, `0 errors, 0 warnings, 0 notes`, and a clean diff check. Ruff was unavailable in the active environment, so it was not installed or run.

## Bounded Smoke Command

```bash
source ~/cd_vlaplan
source .venv/bin/activate
python -m scripts.phase3.generate_planimation_vlm \
  --dataset-root outputs/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round \
  --output-root outputs/phase3_planimation_smoke_blocksworld_20260722_001817 \
  --domain blocksworld --bucket easy --render-limit 1 \
  --progress-every 1 --request-delay-seconds 0 \
  --mode bounded-smoke --render-only
```

The smoke run produced one successful state render and `errors: []` for 5,434 pairing records.

## Production Launch

The long-running production render was started in:

`outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800`

It targets Blocksworld, Elevators, Ferry, Gripper, Logistics, and Towers of Hanoi over the easy and medium buckets, with progress events every 100 rendered states. Logs are in that output root's `diagnostics/` directory.
