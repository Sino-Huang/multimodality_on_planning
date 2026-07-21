# Phase 3 Todo 6: Validated Replay Rendering

Implemented semantic render receipts for Phase 3 replay frames. The gate decodes PNGs, validates VFG stage-zero sprite coordinates, rejects boolean/non-numeric, out-of-canvas, degenerate, and coincident bounds, and requires per-sprite expected-object coverage.

Replay rendering now emits one pre-action frame per action plus a diagnostic terminal frame. VLM construction accepts only the contiguous pre-action sequence; zero-action solved cases emit one initial/terminal full frame and no step rows. Missing step zero cannot become a full record.

Verification commands:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_render_semantics.py tests/phase3/test_planimation_pairing.py tests/phase3/test_traversal_state_projection.py tests/phase3/test_traversal_trace_contracts.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/render_semantics.py scripts/phase3/planimation_pairing.py tests/phase3/test_render_semantics.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/render_semantics.py scripts/phase3/planimation_pairing.py tests/phase3/test_render_semantics.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_planimation_vlm.py --help
```

Observed result: focused suite `48 passed in 0.51s`; basedpyright reported zero errors/warnings/notes; compilation and CLI help exited zero. Receipt details and hashes are in `.omo/evidence/phase3-task-6-render-validation.json`.

The fixture-local renderer smoke wrote one `100x100` PNG from a concrete VFG in `tmp/phase3_task6_render_smoke`; semantic validation accepted one covered sprite. Its trace and PNG SHA-256 values are retained in the evidence receipt.
