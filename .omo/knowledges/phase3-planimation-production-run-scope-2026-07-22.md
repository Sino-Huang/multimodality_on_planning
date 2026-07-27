# Phase 3 Planimation Production Run Scope

## Active run

- Output root: `outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800`.
- Active renderer at the time of this note: PID `6711`.
- The run covers the six production domains and `easy`/`medium` buckets from `outputs/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round`.
- A read-only reconstruction of transitions from the existing pairing manifest found 2,328 eligible pairs and 537,696 expected render states:
  - `blocksworld`: 316,786
  - `elevators`: 87,308
  - `ferry`: 21,870
  - `gripper`: 35,412
  - `logistics`: 48
  - `towers_of_hanoi`: 76,272
- The live renderer had reached 50,100 states when this count was calculated. It must finish before another process writes to this output root.
- PID `6711` was intentionally stopped with `SIGTERM` before completion. Its final validation and release verification did not run; restarting the command below reuses valid cache entries and retries incomplete or invalid states.

## Cache-backed recovery

- `scripts/phase3/planimation_pairing_rendering.py::_cache_identity()` includes `profile_sha256`; changing `data/pddl_instances/elevators/elevators_ap.pddl` changes only affected elevators cache keys.
- `_validated_cache()` accepts a record only when the cache metadata, derived problem hash, VFG, PNG, dimensions, and semantic receipt all still validate.
- Failed records are not valid cache hits, so a same-command replay after the active renderer exits preserves valid records and rerenders failed or profile-invalidated states.
- Do not start replay while PID `6711` is active.

## Post-exit commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.generate_planimation_vlm \
  --dataset-root outputs/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round \
  --output-root outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800 \
  --domain blocksworld --domain elevators --domain ferry --domain gripper --domain logistics --domain towers_of_hanoi \
  --bucket easy --bucket medium --progress-every 100 --request-delay-seconds 0 --mode production

source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/verify_planimation_vlm.py \
  --output-root outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800 \
  --mode release
```

The release verifier must report no invalid persisted records before this output is considered releasable.

## Fast Pilot

- `temp_fast_planimation_render.sh` prepares the deterministic `stratified-pilot` selection and renders it into a new output root before running release verification.
- The selection contains 52 pairs, 331 plan transitions, and 2,568 total render states including search-traversal frames.
- The script refuses to run if a full `generate_planimation_vlm` process still writes to the original output root or if the pilot output root already exists.
- Stop the full renderer before running the pilot. Separate output roots avoid manifest collisions, but concurrent use of the same remote Planimation service would compete for the limiting resource.
