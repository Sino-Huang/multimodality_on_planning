# Phase 3 Planimation Render Observability and Semantics

## Scope

This change stops an all-failing Blocksworld Planimation frame job, identifies the actual semantic failure chain, corrects the Blocksworld animation profile, strengthens the local semantic-image gate, and adds bounded progress reporting for subsequent runs.

## Root Causes

The Blocksworld animation profile declared `ontable`, whereas the current domain uses `on-table`. Planimation could not resolve tabled-block placement and returned fallback coordinates. Multiple sprites then shared the same default bounds, which the Phase 3 semantic gate rejected as `coincident_sprite_bounds`.

After correcting the animation predicate, Planimation returned six numeric, unique sprite bounds. The local coverage gate still rejected a visibly valid image because its perimeter-background heuristic used the maximum color range. A few neighboring board pixels inflated the allowance to 255, so no block pixel could satisfy the coverage threshold. The updated gate excludes known neighboring sprite regions from background sampling and uses a 98th-percentile variation threshold, while retaining the textured gradient, grid, and noise rejection tests.

## Observability

`scripts/phase3/generate_planimation_vlm.py` now emits JSON-line stderr events at render start, every configured interval, and render completion. The default interval is 100 states and is configured with `--progress-every`; `--quiet` suppresses these events. Each event reports processed state count, render status/cache summary, and at most three unique failure messages. Final result JSON remains on stdout for machine consumers.

## Reproduction Commands

Run one state with an outer time limit:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && timeout 120s python scripts/phase3/generate_planimation_vlm.py \
  --dataset-root outputs/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round \
  --output-root outputs/phase3_planimation_bounded_repro_20260721_2130 \
  --domain blocksworld --bucket easy --mode bounded-smoke --render-only \
  --render-limit 1 --timeout-seconds 90 --request-delay-seconds 0 --progress-every 1
```

Validate the retained real VFG/PNG pair locally:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -c 'from pathlib import Path; from scripts.phase3.render_semantics import validate_render_artifacts; root=Path("outputs/phase3_planimation_bounded_repro_20260721_2130/state_cache/blocksworld/blocksworld-dev-easy-0000/45e2c4e6959e5c6b317384d94317d7b6"); print(validate_render_artifacts(root / "trace.vfg.json", root / "frames" / "frame_000.png"))'
```

## Verification

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_planimation_pairing.py tests/phase3/test_render_semantics.py
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/planimation_pairing_contracts.py scripts/phase3/planimation_pairing_replay.py scripts/phase3/planimation_pairing.py scripts/phase3/generate_planimation_vlm.py scripts/phase3/render_semantics.py tests/phase3/test_planimation_pairing.py tests/phase3/test_render_semantics.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3 tests/phase3
git diff --check
```

Observed results: 57 focused tests passed; basedpyright reported zero errors; compileall and diff check completed successfully. `ruff` was unavailable in the activated `.venv`.
