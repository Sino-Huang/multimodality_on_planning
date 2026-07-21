# Phase 3 Planimation Render Observability and Semantics

## Confirmed Failure Chain

1. The legacy Blocksworld animation profile used `(:predicate ontable ...)`, but the current domain declares and emits `(on-table ...)`.
2. Planimation therefore assigned tabled blocks fallback `x=false`, `y=false` coordinates and identical default bounds.
3. `scripts/phase3/render_semantics.py` correctly rejected those VFGs as `semantic_image_invalid: coincident_sprite_bounds`.
4. After the profile predicate correction, VFG bounds became numeric and distinct. A second false rejection remained because the local coverage calculation used the maximum RGB range of its perimeter samples. A few pixels from an adjacent board/block made the texture allowance 255 and made coverage impossible.
5. The semantic gate now excludes declared neighboring-sprite bounds from its local background samples and uses a 98th-percentile variation threshold. The retained real Blocksworld artifact validates with all six sprites covered.

## Progress Reporting

`generate_planimation_vlm.py` now writes JSON-line render events to stderr:

- `state_render_started`
- `state_render_progress` at `--progress-every` intervals (default 100)
- `state_render_finished`

Events contain processed-state count, cache/status summary, and at most three distinct failure messages. Final machine-readable JSON remains on stdout. Use `--quiet` to suppress stderr events.

## Bounded Reproduction

```bash
source ~/cd_vlaplan && source .venv/bin/activate && timeout 120s python scripts/phase3/generate_planimation_vlm.py \
  --dataset-root outputs/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round \
  --output-root outputs/phase3_planimation_bounded_repro_20260721_2130 \
  --domain blocksworld --bucket easy --mode bounded-smoke --render-only \
  --render-limit 1 --timeout-seconds 90 --request-delay-seconds 0 --progress-every 1
```

Validate a retained cached render without another remote request:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -c 'from pathlib import Path; from scripts.phase3.render_semantics import validate_render_artifacts; root=Path("outputs/phase3_planimation_bounded_repro_20260721_2130/state_cache/blocksworld/blocksworld-dev-easy-0000/45e2c4e6959e5c6b317384d94317d7b6"); print(validate_render_artifacts(root / "trace.vfg.json", root / "frames" / "frame_000.png"))'
```
